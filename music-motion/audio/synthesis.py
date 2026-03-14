"""Audio synthesis functions for generating waveforms."""

import numpy as np
from ..utils.constants import AUDIO_SAMPLE_RATE


def generate_sine_wave(freq: float, frames: int, phase: float = 0.0) -> tuple:
    """
    Generate a sine wave.
    
    Args:
        freq: Frequency in Hz
        frames: Number of frames to generate
        phase: Initial phase in radians
        
    Returns:
        Tuple of (audio_samples, new_phase)
    """
    t = np.arange(frames, dtype=np.float32)
    phase_increment = 2.0 * np.pi * freq / AUDIO_SAMPLE_RATE
    phases = phase + phase_increment * t
    
    # Keep phase from growing without bound
    new_phase = float((phases[-1] + phase_increment) % (2.0 * np.pi))
    
    samples = np.sin(phases).astype(np.float32)
    return samples, new_phase


def generate_sawtooth_wave(freq: float, frames: int, phase: float = 0.0) -> tuple:
    """
    Generate a sawtooth wave.
    
    Args:
        freq: Frequency in Hz
        frames: Number of frames to generate
        phase: Initial phase in radians
        
    Returns:
        Tuple of (audio_samples, new_phase)
    """
    t = np.arange(frames, dtype=np.float32)
    phase_increment = 2.0 * np.pi * freq / AUDIO_SAMPLE_RATE
    phases = phase + phase_increment * t
    
    # Keep phase from growing without bound
    new_phase = float((phases[-1] + phase_increment) % (2.0 * np.pi))
    
    # Generate sawtooth: 2.0 * (phase / (2π) % 1.0) - 1.0
    samples = (2.0 * (phases / (2.0 * np.pi) % 1.0) - 1.0).astype(np.float32)
    return samples, new_phase


def morph_waveforms(sine_wave: np.ndarray, sawtooth_wave: np.ndarray, timbre_norm: float) -> np.ndarray:
    """
    Morph between sine and sawtooth waveforms based on timbre.
    
    Args:
        sine_wave: Sine wave samples
        sawtooth_wave: Sawtooth wave samples
        timbre_norm: Normalized timbre value in [0, 1]
                     - 0.0 = full sine (warm)
                     - 1.0 = full sawtooth (bright)
        
    Returns:
        Morphed waveform samples
    """
    return (1.0 - timbre_norm) * sine_wave + timbre_norm * sawtooth_wave

