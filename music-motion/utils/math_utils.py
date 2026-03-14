"""Mathematical utility functions for IMU data processing."""

import math
from .constants import MAX_TILT_DEG


def map_tilt_to_position(roll_deg: float, pitch_deg: float, max_tilt_deg: float = MAX_TILT_DEG) -> tuple:
    """
    Map roll/pitch in degrees to normalized position (0.0 to 1.0).
    
    This matches the logic from imu_tkinter.py's _map_tilt_to_canvas():
    - Clamp roll and pitch to ±max_tilt_deg
    - Normalize to [-1, 1]
    - Map to position with roll controlling X (left/right)
    - Pitch controlling Y (up/down, inverted)
    
    Args:
        roll_deg: Roll angle in degrees (X-axis tilt, left/right)
        pitch_deg: Pitch angle in degrees (Y-axis tilt, forward/back)
        max_tilt_deg: Maximum tilt in degrees for full deflection (default: MAX_TILT_DEG)
        
    Returns:
        Tuple of (x, y) normalized positions (0.0 to 1.0)
    """
    # Clamp to maximum tilt range
    roll = max(-max_tilt_deg, min(max_tilt_deg, roll_deg))
    pitch = max(-max_tilt_deg, min(max_tilt_deg, pitch_deg))
    
    # Normalize to [-1, 1]
    roll_norm = roll / max_tilt_deg
    pitch_norm = pitch / max_tilt_deg
    
    # Map to normalized position [0.0, 1.0]
    # Roll: positive (tilt right) → move right (increase x)
    x = 0.5 + roll_norm * 0.5
    
    # Pitch: positive (tilt forward) → move up (decrease y, inverted)
    # This matches imu_tkinter.py: "Pitch up (positive) moves dot UP, so subtract"
    y = 0.5 - pitch_norm * 0.5
    
    return x, y


def calculate_angle(a, b, c):
    """
    Calculate the angle between three landmark points.
    
    Args:
        a: First point (landmark with x, y attributes)
        b: Vertex point (landmark with x, y attributes)
        c: Third point (landmark with x, y attributes)
        
    Returns:
        Angle in degrees
    """
    # Calculate vectors from vertex to other points
    vector_ab = [a.x - b.x, a.y - b.y]
    vector_cb = [c.x - b.x, c.y - b.y]
    
    # Calculate dot product
    dot_product = vector_ab[0] * vector_cb[0] + vector_ab[1] * vector_cb[1]
    
    # Calculate magnitudes
    magnitude_ab = math.sqrt(vector_ab[0] ** 2 + vector_ab[1] ** 2)
    magnitude_cb = math.sqrt(vector_cb[0] ** 2 + vector_cb[1] ** 2)
    
    # Calculate cosine of angle
    if magnitude_ab == 0 or magnitude_cb == 0:
        return 0
    
    cos_angle = dot_product / (magnitude_ab * magnitude_cb)
    
    # Clamp to valid range for arccos
    cos_angle = max(-1.0, min(1.0, cos_angle))
    
    # Convert to degrees
    angle = math.degrees(math.acos(cos_angle))
    return angle


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, value))


def normalize(value: float, min_val: float, max_val: float) -> float:
    """Normalize a value from [min_val, max_val] to [0, 1]."""
    if max_val == min_val:
        return 0.0
    return (value - min_val) / (max_val - min_val)


def denormalize(value: float, min_val: float, max_val: float) -> float:
    """Denormalize a value from [0, 1] to [min_val, max_val]."""
    return min_val + value * (max_val - min_val)

