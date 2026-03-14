"""Audio effects processing (EQ, filters, limiting)."""

import numpy as np
from ..utils.constants import (
    AUDIO_SAMPLE_RATE, AUDIO_BLOCK_SIZE, N_BANDS, BAND_EDGES,
    MAX_GAIN_DB, EQ_SMOOTHING_ALPHA, MAX_ROLL_TIMBRE_DEG_METHOD_G
)


def build_band_index(block_size: int = AUDIO_BLOCK_SIZE, sample_rate: int = AUDIO_SAMPLE_RATE) -> np.ndarray:
    """
    Precompute which EQ band each FFT bin belongs to.
    
    Args:
        block_size: Audio block size (default: AUDIO_BLOCK_SIZE)
        sample_rate: Sample rate in Hz (default: AUDIO_SAMPLE_RATE)
        
    Returns:
        band_index: int array of length (block_size//2 + 1)
                    where band_index[k] is in [0, N_BANDS-1]
    """
    freqs = np.fft.rfftfreq(block_size, d=1.0 / sample_rate)
    band_index = np.zeros_like(freqs, dtype=np.int32)
    
    for k, f in enumerate(freqs):
        # Default band = 0 (lowest)
        idx = 0
        for band_i, (low, high) in enumerate(BAND_EDGES):
            if f >= low and f < high:
                idx = band_i
                break
            # If frequency exceeds the last band's upper edge, clamp to last band
            if f >= BAND_EDGES[-1][1]:
                idx = len(BAND_EDGES) - 1
                break
        band_index[k] = idx
    
    return band_index


def compute_band_gains_db(roll_deg: float, max_roll_deg: float = MAX_ROLL_TIMBRE_DEG_METHOD_G) -> np.ndarray:
    """
    Map IMU roll angle (degrees) to a 7-element array of EQ band gains in dB.
    
    Uses nonlinear tanh() mapping to avoid extreme harshness at extremes.
    
    Behavior (tilt EQ):
      - roll = -max_angle  → lows cut, highs boosted (thin/bright)
      - roll = 0           → flat EQ (0 dB)
      - roll = +max_angle  → lows boosted, highs cut (warm/bassy)
    
    Args:
        roll_deg: Roll angle in degrees
        max_roll_deg: Maximum roll angle for full EQ range
        
    Returns:
        Array of 7 band gains in dB
    """
    # Clamp roll to [-max_angle, +max_angle]
    roll_clamped = max(-max_roll_deg, min(max_roll_deg, roll_deg))
    
    # Nonlinear softening curve using tanh
    raw_norm = roll_clamped / max_roll_deg  # -1..+1
    tilt_norm = np.tanh(raw_norm * 1.2)  # soft clipping at ends
    
    # Band positions from low (-1) to high (+1)
    mid = (N_BANDS - 1) / 2.0
    gains_db = np.zeros(N_BANDS, dtype=np.float32)
    
    for i in range(N_BANDS):
        # band_pos ~ [-1, 1]
        band_pos = (i - mid) / mid
        # Tilt EQ: negative tilt_norm = tilt left
        # We want:
        #   left tilt → lows down, highs up
        #   right tilt → lows up, highs down
        gain_db = MAX_GAIN_DB * (-tilt_norm) * band_pos
        gains_db[i] = gain_db
    
    return gains_db


def gains_db_to_linear(gains_db: np.ndarray) -> np.ndarray:
    """Convert dB gains to linear multipliers."""
    return np.power(10.0, gains_db / 20.0, dtype=np.float32)


def apply_soft_limiter(block: np.ndarray, threshold: float = 0.95, ratio: float = 0.3) -> np.ndarray:
    """
    Apply soft limiting to prevent clipping.
    
    Args:
        block: Audio block to limit
        threshold: Start limiting at this fraction of full scale (default: 0.95)
        ratio: Compression ratio (default: 0.3, gentle)
        
    Returns:
        Limited audio block
    """
    abs_block = np.abs(block)
    over_threshold = abs_block > threshold
    
    if np.any(over_threshold):
        # Soft knee compression
        excess = abs_block - threshold
        compressed_excess = excess * ratio
        limited_abs = threshold + compressed_excess
        
        # Preserve sign and apply limiting
        limited = np.sign(block) * np.minimum(abs_block, limited_abs)
    else:
        limited = block
    
    # Final safety: hard clip at ±1.0 if still needed
    return np.clip(limited, -1.0, 1.0)


def apply_motion_eq(
    block: np.ndarray,
    roll_deg: float,
    band_index: np.ndarray,
    smoothed_gains_db: np.ndarray,
    max_roll_deg: float = MAX_ROLL_TIMBRE_DEG_METHOD_G,
    smoothing_alpha: float = EQ_SMOOTHING_ALPHA,
    block_size: int = AUDIO_BLOCK_SIZE
) -> tuple:
    """
    Apply the motion-controlled multi-band EQ to a 1D numpy audio block (mono).
    
    Uses FFT-based per-bin scaling with:
    - Nonlinear tanh mapping (in compute_band_gains_db)
    - Exponential smoothing of gains over time
    - Soft limiter to prevent clipping
    
    Args:
        block: Mono audio block to process
        roll_deg: Roll angle in degrees
        band_index: Precomputed band index array
        smoothed_gains_db: Current smoothed gains (will be updated)
        max_roll_deg: Maximum roll angle for full EQ range
        smoothing_alpha: Exponential smoothing factor
        block_size: Audio block size
        
    Returns:
        Tuple of (processed_block, updated_smoothed_gains_db)
    """
    # Ensure float32
    x = block.astype(np.float32, copy=False)
    
    # Compute raw band gains in dB
    raw_gains_db = compute_band_gains_db(roll_deg, max_roll_deg)
    
    # Smooth gains over time using exponential smoothing
    # smoothed = alpha * new + (1 - alpha) * old
    updated_smoothed_gains_db = (
        smoothing_alpha * raw_gains_db +
        (1.0 - smoothing_alpha) * smoothed_gains_db
    )
    
    # Convert smoothed gains to linear
    gains_lin = gains_db_to_linear(updated_smoothed_gains_db)
    
    # Get per-bin gain via precomputed band index
    bin_gains = gains_lin[band_index]
    
    # FFT
    X = np.fft.rfft(x)
    
    # Apply per-bin gains
    X_filtered = X * bin_gains
    
    # iFFT
    y = np.fft.irfft(X_filtered, n=block_size).astype(np.float32)
    
    # Apply soft limiter
    y = apply_soft_limiter(y)
    
    return y, updated_smoothed_gains_db

