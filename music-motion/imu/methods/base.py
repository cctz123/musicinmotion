"""Base class for IMU control methods with audio."""

import numpy as np
import sounddevice as sd
from ...imu.visualization.base import ImuSquareWidget
from ...audio.player import AudioStream
from ...audio.utils import (
    map_pitch_to_frequency, map_roll_to_pan, map_yaw_to_pan,
    compute_equal_power_panning
)
from ...audio.synthesis import generate_sine_wave
from ...utils.constants import (
    AUDIO_SAMPLE_RATE, AUDIO_BLOCK_SIZE, BASE_FREQ, MAX_FREQ,
    MAX_ROLL_PAN_DEG, AUDIO_AMP, MAX_TILT_DEG
)


class BaseImuMethod(ImuSquareWidget):
    """Base class for IMU methods with audio support.
    
    Provides common audio stream management and basic audio generation.
    Subclasses should override audio_callback() or start_audio() for custom behavior.
    """
    
    AUDIO_SAMPLE_RATE = AUDIO_SAMPLE_RATE
    AUDIO_BLOCK_SIZE = AUDIO_BLOCK_SIZE
    BASE_FREQ = BASE_FREQ
    MAX_FREQ = MAX_FREQ
    MAX_ROLL_PAN_DEG = MAX_ROLL_PAN_DEG
    AUDIO_AMP = AUDIO_AMP
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_stream = None
        self.current_roll = 0.0
        self.current_pitch = 0.0
        self.current_yaw = 180.0  # Default to center (180° = center pan)
        self.audio_phase = 0.0
    
    def start_audio(self):
        """Start the audio stream. Override in subclasses for custom behavior."""
        if self.audio_stream is not None:
            return  # Already started
        
        audio_player = AudioStream(
            sample_rate=self.AUDIO_SAMPLE_RATE,
            block_size=self.AUDIO_BLOCK_SIZE,
            channels=2
        )
        audio_player.start(self._audio_callback)
        self.audio_stream = audio_player
    
    def _audio_callback(self, outdata, frames, time_info, status):
        """Internal audio callback. Override in subclasses."""
        if status:
            print("Audio status:", status)
        outdata.fill(0)
    
    def stop_audio(self):
        """Stop the audio stream."""
        if self.audio_stream is not None:
            self.audio_stream.stop()
            self.audio_stream = None
        self.audio_phase = 0.0
    
    def set_angles_for_audio(self, roll_deg: float, pitch_deg: float, yaw_deg: float = None):
        """Update angles for audio generation (separate from visual position).
        
        Args:
            roll_deg: Roll angle in degrees
            pitch_deg: Pitch angle in degrees
            yaw_deg: Yaw angle in degrees (0-360°), optional
        """
        self.current_roll = roll_deg
        self.current_pitch = pitch_deg
        if yaw_deg is not None:
            self.current_yaw = yaw_deg

