"""Audio utility functions for conversions and mappings."""

import numpy as np
from ..utils.constants import (
    BASE_FREQ, MAX_FREQ, MAX_TILT_DEG, MAX_ROLL_PAN_DEG,
    MAX_ROLL_TIMBRE_DEG, MAX_PITCH_VOLUME_DEG, MAX_ROLL_TIMBRE_DEG_METHOD_G
)


def map_pitch_to_frequency(pitch_deg: float, max_tilt_deg: float = MAX_TILT_DEG) -> float:
    """
    Map pitch angle to frequency.
    
    Args:
        pitch_deg: Pitch angle in degrees
        max_tilt_deg: Maximum tilt in degrees
        
    Returns:
        Frequency in Hz
    """
    pitch_clamped = max(-max_tilt_deg, min(max_tilt_deg, pitch_deg))
    # Map [-max_tilt_deg, +max_tilt_deg] -> [0, 1]
    norm = (pitch_clamped + max_tilt_deg) / (2 * max_tilt_deg)
    freq = BASE_FREQ + (MAX_FREQ - BASE_FREQ) * norm
    return freq


def map_roll_to_pan(roll_deg: float, max_roll_deg: float = MAX_ROLL_PAN_DEG) -> float:
    """
    Map roll angle to stereo pan position.
    
    Args:
        roll_deg: Roll angle in degrees
        max_roll_deg: Maximum roll angle for full pan
        
    Returns:
        Pan value in [-1, 1] where -1 = full left, +1 = full right
    """
    roll_clamped = max(-max_roll_deg, min(max_roll_deg, roll_deg))
    pan = roll_clamped / max_roll_deg
    return pan


def map_yaw_to_pan(yaw_deg: float) -> float:
    """
    Map yaw angle (0-360°) to stereo pan position.
    
    Args:
        yaw_deg: Yaw angle in degrees (0-360°)
        
    Returns:
        Pan value in [-1, 1] where -1 = full left, +1 = full right
    """
    # Convert yaw from 0-360° to -1 to +1 for panning
    # 0° = full left, 180° = center, 360° = full right
    yaw_normalized = (yaw_deg - 180.0) / 180.0
    pan = max(-1.0, min(1.0, yaw_normalized))
    return pan


def map_roll_to_timbre(roll_deg: float, max_roll_deg: float = MAX_ROLL_TIMBRE_DEG) -> float:
    """
    Map roll angle to normalized timbre value.
    
    Args:
        roll_deg: Roll angle in degrees
        max_roll_deg: Maximum roll angle for full timbre range
        
    Returns:
        Normalized timbre value in [0, 1]
        - 0.0 = full left roll → warm/mellow
        - 0.5 = neutral roll → neutral timbre
        - 1.0 = full right roll → bright/sharp
    """
    roll_clamped = max(-max_roll_deg, min(max_roll_deg, roll_deg))
    timbre_norm = (roll_clamped + max_roll_deg) / (2 * max_roll_deg)
    return timbre_norm


def map_pitch_to_volume(pitch_deg: float, max_pitch_deg: float = MAX_PITCH_VOLUME_DEG) -> float:
    """
    Map pitch angle to normalized volume value.
    
    Args:
        pitch_deg: Pitch angle in degrees
        max_pitch_deg: Maximum pitch angle for full volume range
        
    Returns:
        Normalized volume value in [0, 1]
        - 0.0 = full backward pitch → muted
        - 0.5 = neutral pitch → 50% volume
        - 1.0 = full forward pitch → full volume
    """
    pitch_clamped = max(-max_pitch_deg, min(max_pitch_deg, pitch_deg))
    volume_norm = (pitch_clamped + max_pitch_deg) / (2 * max_pitch_deg)
    return volume_norm


def compute_equal_power_panning(pan: float) -> tuple:
    """
    Compute equal-power stereo panning gains.
    
    Args:
        pan: Pan value in [-1, 1] where -1 = full left, +1 = full right
        
    Returns:
        Tuple of (left_gain, right_gain)
    """
    left_gain = np.sqrt((1.0 - pan) / 2.0)
    right_gain = np.sqrt((1.0 + pan) / 2.0)
    return left_gain, right_gain

