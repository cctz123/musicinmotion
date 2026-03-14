"""Method C: Pitch + Pan - Basic audio with pitch and panning control."""

import numpy as np
import sounddevice as sd
from ...imu.visualization.base import ImuSquareWidget
from ...audio.utils import map_pitch_to_frequency, map_roll_to_pan, compute_equal_power_panning
from ...audio.synthesis import generate_sine_wave
from ...utils.constants import (
    AUDIO_SAMPLE_RATE, AUDIO_BLOCK_SIZE, BASE_FREQ, MAX_FREQ,
    MAX_ROLL_PAN_DEG, AUDIO_AMP, MAX_TILT_DEG
)


class ImuSquareSoundWidget(ImuSquareWidget):
    """Widget that displays a blue square with audio (Pitch + Pan).
    
    Extends ImuSquareWidget to add audio generation:
    - Visual: Same as Method B (blue square)
    - Audio: Pitch controls frequency, roll controls stereo panning
    - Uses same tilt mapping as Method B for visual
    - Uses extended roll range for audio panning (MAX_ROLL_PAN_DEG = 45.0°)
    """
    
    # Audio configuration
    AUDIO_SAMPLE_RATE = AUDIO_SAMPLE_RATE
    AUDIO_BLOCK_SIZE = AUDIO_BLOCK_SIZE
    BASE_FREQ = BASE_FREQ
    MAX_FREQ = MAX_FREQ
    MAX_ROLL_PAN_DEG = MAX_ROLL_PAN_DEG
    AUDIO_AMP = AUDIO_AMP
    MAX_TILT_DEG = MAX_TILT_DEG
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_stream = None
        self.current_roll = 0.0
        self.current_pitch = 0.0
        self.audio_phase = 0.0
        
    def start_audio(self):
        """Start the audio stream."""
        if self.audio_stream is not None:
            return
        
        def audio_callback(outdata, frames, time_info, status):
            try:
                if status:
                    print("Audio status:", status)
                
                roll_deg = self.current_roll
                pitch_deg = self.current_pitch
                
                # Pitch mapping
                freq = map_pitch_to_frequency(pitch_deg, self.MAX_TILT_DEG)
                
                # Pan mapping
                pan = map_roll_to_pan(roll_deg, self.MAX_ROLL_PAN_DEG)
                
                # Generate sine wave
                mono, self.audio_phase = generate_sine_wave(freq, frames, self.audio_phase)
                mono *= self.AUDIO_AMP
                
                # Equal-power stereo panning
                left_gain, right_gain = compute_equal_power_panning(pan)
                
                outdata[:, 0] = mono * left_gain
                outdata[:, 1] = mono * right_gain
            except Exception as e:
                print(f"Error in Pitch + Pan audio callback: {e}")
                import traceback
                traceback.print_exc()
                outdata.fill(0)
        
        try:
            self.audio_stream = sd.OutputStream(
                samplerate=self.AUDIO_SAMPLE_RATE,
                channels=2,
                blocksize=self.AUDIO_BLOCK_SIZE,
                callback=audio_callback,
            )
            self.audio_stream.start()
            print(f"Audio stream started successfully")
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            import traceback
            traceback.print_exc()
            self.audio_stream = None
    
    def stop_audio(self):
        """Stop the audio stream."""
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        self.audio_phase = 0.0
    
    def set_angles_for_audio(self, roll_deg: float, pitch_deg: float):
        """Update angles for audio generation."""
        self.current_roll = roll_deg
        self.current_pitch = pitch_deg

