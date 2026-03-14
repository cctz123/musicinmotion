"""Shared constants for the music-motion application."""

# Audio constants
AUDIO_SAMPLE_RATE = 44100
AUDIO_BLOCK_SIZE = 256  # Power of 2 for FFT

# IMU visualization constants
MAX_TILT_DEG = 5.0  # Maximum tilt in degrees for full deflection
SQUARE_SIZE = 40  # Square size in pixels
TARGET_TOLERANCE_DEG = 0.3  # Target zone: ±0.3 degree (circle turns green)
TARGET_CIRCLE_RADIUS = 30  # Radius of target circle in pixels

# Audio synthesis constants
BASE_FREQ = 220.0   # A3-ish
MAX_FREQ = 880.0    # A5-ish
AUDIO_AMP = 0.15    # Base amplitude

# Panning constants
MAX_ROLL_PAN_DEG = 45.0  # Full panning at ±45° roll

# Volume control constants
VOLUME_MIN = 0.0      # Minimum volume (muted)
VOLUME_MAX = 1.0      # Maximum volume
AMP_MIN = 0.0         # Minimum amplitude
AMP_MAX = 0.5         # Maximum amplitude
VOLUME_STEP = 0.1     # Volume increment/decrement step (10% of range)

# Motion-based volume constants (Method D)
ACCEL_THRESHOLD_HIGH = 1.2  # Z-acceleration threshold for volume up (g)
ACCEL_THRESHOLD_LOW = 0.8   # Z-acceleration threshold for volume down (g)
MEASUREMENT_COOLDOWN = 2.0  # Seconds to wait after last volume adjustment

# Timbre control constants
MAX_ROLL_TIMBRE_DEG = 45.0  # Full timbre range at ±45° roll (Method F)
MAX_PITCH_VOLUME_DEG = 5.0  # Full volume range at ±5° pitch (Method G)
MAX_ROLL_TIMBRE_DEG_METHOD_G = 10.0  # Full timbre range at ±10° roll (Method G)

# EQ constants (Method G)
MAX_GAIN_DB = 6.0           # Maximum gain per band in dB
EQ_SMOOTHING_ALPHA = 0.15   # Exponential smoothing factor (0-1, lower = smoother)
N_BANDS = 7

# Frequency bands (Hz) - 7 bands
BAND_EDGES = [
    (20, 60),       # Sub bass
    (60, 250),      # Bass
    (250, 500),     # Lower mids
    (500, 2000),    # Mids
    (2000, 4000),   # Upper mids
    (4000, 6000),   # Presence
    (6000, 20000),  # Brilliance
]

# UI constants
VOLUME_INDICATOR_HEIGHT = 120  # Height for control bars
USER_VOLUME_INDICATOR_HEIGHT = 50  # Height for Volume bar at bottom
EQ_BARS_AREA_HEIGHT = 300  # Height for 7 EQ bars in center

# Audio file path
AUDIO_FILE = "music/music.mp3"

