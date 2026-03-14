"""Model 1: Dual-Arm Timbre Sculptor - Body-as-instrument control."""

import numpy as np
import sounddevice as sd
from pathlib import Path
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtCore import Qt, QSize
from ...audio.synthesis import generate_sine_wave
from ...audio.effects import (
    build_band_index, gains_db_to_linear,
    apply_motion_eq, apply_soft_limiter
)
from ...utils.constants import (
    AUDIO_SAMPLE_RATE, AUDIO_BLOCK_SIZE, BASE_FREQ,
    MAX_GAIN_DB, EQ_SMOOTHING_ALPHA, N_BANDS, BAND_EDGES, AUDIO_FILE
)


class Model1Widget(QWidget):
    """Model 1: Dual-Arm Timbre Sculptor widget.
    
    Implements TICKET-MMM-MODEL-1:
    - Timbre: MediaPipe arm heights → EQ bands (left arm = low-freq, right arm = high-freq)
    - Loudness: Left IMU acceleration → volume envelope
    - Character/Texture: Right IMU acceleration → distortion/saturation
    """
    
    # Audio configuration
    AUDIO_SAMPLE_RATE = AUDIO_SAMPLE_RATE
    AUDIO_BLOCK_SIZE = AUDIO_BLOCK_SIZE
    BASE_FREQ = BASE_FREQ
    
    # Timbre control (MediaPipe arm heights)
    # Left arm height → low-frequency timbre weight
    # Right arm height → high-frequency brightness
    # Using wrist y position directly (0-1 range, inverted)
    ARM_HEIGHT_MIN = 0.0   # Wrist at bottom of frame
    ARM_HEIGHT_MAX = 1.0   # Wrist at top of frame
    MAX_GAIN_DB = MAX_GAIN_DB
    EQ_SMOOTHING_ALPHA = EQ_SMOOTHING_ALPHA
    
    # Loudness control (Left IMU acceleration)
    ACCEL_MIN = 0.5   # Resting acceleration (1g gravity)
    ACCEL_MAX = 3.0   # Fast movement
    VOLUME_MIN = 0.1
    VOLUME_MAX = 1.0
    
    # Character/Texture control (Right IMU acceleration)
    SATURATION_MIN = 0.0
    SATURATION_MAX = 0.8  # Max saturation amount
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_stream = None
        
        # Reference to bars and equalizer widgets (set externally)
        self.bars_widget = None
        self.equalizer_widget = None
        
        # Audio source mode: False = tone, True = music
        self.use_music_mode = False
        
        # MediaPipe pose data (exponentially smoothed)
        self.left_arm_height = 0.0
        self.right_arm_height = 0.0
        self.left_arm_height_smooth = 0.0
        self.right_arm_height_smooth = 0.0
        
        # IMU data
        self.left_imu_accel = 1.0  # Default to 1g
        self.right_imu_accel = 1.0
        
        # Audio generation (for tone mode)
        self.audio_phase = 0.0
        
        # Audio file data (for music mode)
        self.audio_data = None
        self.audio_sample_rate = None
        self.audio_position = 0
        self._audio_file_loaded = False
        
        # EQ state
        self.band_index = build_band_index(self.AUDIO_BLOCK_SIZE, self.AUDIO_SAMPLE_RATE)
        self.smoothed_gains_db = np.zeros(N_BANDS, dtype=np.float32)
        
        # Current values for display
        self.current_volume = 0.5
        self.current_saturation = 0.0
        self.current_band_gains_db = np.zeros(N_BANDS, dtype=np.float32)
    
    def set_audio_source(self, use_music: bool):
        """Set audio source mode: False = tone, True = music."""
        was_running = (self.audio_stream is not None)
        
        # Stop audio if running
        if was_running:
            self.stop_audio()
        
        self.use_music_mode = use_music
        
        # If switching to music mode, load the audio file
        if use_music and not self._audio_file_loaded:
            self._load_audio_file()
            self._audio_file_loaded = True
        
        # Restart audio if it was running
        if was_running:
            self.start_audio()
    
    def _load_audio_file(self):
        """Load the audio file (music.mp3) for music mode."""
        try:
            import librosa
            
            # Try to resolve path relative to project root
            # First try the path as-is (relative to current working directory)
            audio_path = Path(AUDIO_FILE)
            
            # If not found, try relative to this file's location (go up to project root)
            if not audio_path.exists():
                # Get the directory containing this file
                current_file = Path(__file__)
                # Go up: music-motion/imu/methods/model_1.py -> music-motion/ -> .. -> project root
                project_root = current_file.parent.parent.parent.parent
                audio_path = project_root / AUDIO_FILE
            
            if not audio_path.exists():
                print(f"Warning: Audio file not found: {AUDIO_FILE}")
                print(f"  Tried: {Path(AUDIO_FILE).absolute()}")
                print(f"  Tried: {audio_path.absolute()}")
                return
            
            self.audio_data, self.audio_sample_rate = librosa.load(
                str(audio_path),
                sr=self.AUDIO_SAMPLE_RATE,
                mono=True
            )
            print(f"Loaded audio file: {audio_path} ({len(self.audio_data)} samples, {self.audio_sample_rate} Hz)")
        except Exception as e:
            print(f"Error loading audio file: {e}")
            import traceback
            traceback.print_exc()
            self.audio_data = None
    
    def start_audio(self):
        """Start the audio stream."""
        if self.audio_stream is not None:
            return
        
        def audio_callback(outdata, frames, time_info, status):
            try:
                if status:
                    print("Audio status:", status)
                
                # Generate or load audio based on mode
                if self.use_music_mode:
                    # Music mode: read from audio file
                    if self.audio_data is None:
                        outdata.fill(0)
                        return
                    
                    mono = np.zeros(frames, dtype=np.float32)
                    samples_read = 0
                    
                    while samples_read < frames:
                        remaining = frames - samples_read
                        available = len(self.audio_data) - self.audio_position
                        
                        if available > 0:
                            read_count = min(remaining, available)
                            mono[samples_read:samples_read + read_count] = self.audio_data[
                                self.audio_position:self.audio_position + read_count
                            ]
                            self.audio_position += read_count
                            samples_read += read_count
                        
                        # Loop if we've reached the end
                        if self.audio_position >= len(self.audio_data):
                            self.audio_position = 0
                else:
                    # Tone mode: generate sine wave
                    mono, self.audio_phase = generate_sine_wave(self.BASE_FREQ, frames, self.audio_phase)
                
                # Apply timbre control (EQ from arm heights)
                # Left arm → low-freq weight, Right arm → high-freq brightness
                gains_db = self._compute_timbre_eq()
                
                # Smooth EQ gains
                self.smoothed_gains_db = (
                    self.EQ_SMOOTHING_ALPHA * gains_db +
                    (1.0 - self.EQ_SMOOTHING_ALPHA) * self.smoothed_gains_db
                )
                
                # Convert to linear and apply EQ
                gains_linear = gains_db_to_linear(self.smoothed_gains_db)
                bin_gains = gains_linear[self.band_index]
                
                # FFT
                X = np.fft.rfft(mono)
                
                # Apply per-bin gains
                X_filtered = X * bin_gains
                
                # iFFT
                mono = np.fft.irfft(X_filtered, n=len(mono)).astype(np.float32)
                
                # Apply saturation/texture from right IMU
                saturation = self._compute_saturation()
                if saturation > 0.01:
                    mono = self._apply_saturation(mono, saturation)
                
                # Apply volume from left IMU
                volume = self._compute_volume()
                mono *= volume
                
                # Soft limiting
                mono = apply_soft_limiter(mono)
                
                # Stereo output (mono for now, can add stereo width later)
                outdata[:, 0] = mono
                outdata[:, 1] = mono
                
            except Exception as e:
                print(f"Error in Model 1 audio callback: {e}")
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
            print("Model 1 audio stream started successfully")
        except Exception as e:
            print(f"Error starting Model 1 audio stream: {e}")
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
        self.audio_position = 0
    
    def set_widgets(self, bars_widget, equalizer_widget):
        """Set references to the bars and equalizer widgets."""
        self.bars_widget = bars_widget
        self.equalizer_widget = equalizer_widget
    
    def update_pose_data(self, left_arm_height: float, right_arm_height: float):
        """Update MediaPipe pose data with exponential smoothing."""
        self.left_arm_height = left_arm_height
        self.right_arm_height = right_arm_height
        
        # Exponential moving average smoothing
        alpha = 0.1  # Smoothing factor (lower = more smoothing)
        self.left_arm_height_smooth = (
            alpha * left_arm_height +
            (1.0 - alpha) * self.left_arm_height_smooth
        )
        self.right_arm_height_smooth = (
            alpha * right_arm_height +
            (1.0 - alpha) * self.right_arm_height_smooth
        )
        
        # Update bars widget if available
        if self.bars_widget:
            self.bars_widget.update_data(
                self.left_arm_height_smooth,
                self.right_arm_height_smooth,
                self.current_volume,
                self.current_saturation
            )
    
    def update_imu_data(self, left_accel_magnitude: float, right_accel_magnitude: float):
        """Update IMU acceleration data."""
        self.left_imu_accel = left_accel_magnitude
        self.right_imu_accel = right_accel_magnitude
        
        # Update bars widget if available
        if self.bars_widget:
            self.bars_widget.update_data(
                self.left_arm_height_smooth,
                self.right_arm_height_smooth,
                self.current_volume,
                self.current_saturation
            )
    
    def _compute_timbre_eq(self) -> np.ndarray:
        """
        Compute EQ band gains from arm heights.
        
        Left arm height → low-frequency timbre weight
        Right arm height → high-frequency brightness
        """
        # Normalize arm heights to [0, 1]
        left_norm = np.clip(
            (self.left_arm_height_smooth - self.ARM_HEIGHT_MIN) /
            (self.ARM_HEIGHT_MAX - self.ARM_HEIGHT_MIN),
            0.0, 1.0
        )
        right_norm = np.clip(
            (self.right_arm_height_smooth - self.ARM_HEIGHT_MIN) /
            (self.ARM_HEIGHT_MAX - self.ARM_HEIGHT_MIN),
            0.0, 1.0
        )
        
        # Map to EQ gains
        # Left arm: low-freq boost when high, cut when low
        # Right arm: high-freq boost when high, cut when low
        gains_db = np.zeros(N_BANDS, dtype=np.float32)
        mid = (N_BANDS - 1) / 2.0
        
        for i in range(N_BANDS):
            band_pos = (i - mid) / mid  # -1 (low) to +1 (high)
            
            # Low-freq weight from left arm
            if band_pos < 0:  # Low frequencies
                low_gain = self.MAX_GAIN_DB * (left_norm - 0.5) * 2.0  # -MAX to +MAX
                gains_db[i] += low_gain
            
            # High-freq brightness from right arm
            if band_pos > 0:  # High frequencies
                high_gain = self.MAX_GAIN_DB * (right_norm - 0.5) * 2.0  # -MAX to +MAX
                gains_db[i] += high_gain
        
        self.current_band_gains_db = gains_db
        
        # Update equalizer widget if available
        if self.equalizer_widget:
            self.equalizer_widget.update_data(gains_db)
        
        return gains_db
    
    def _compute_volume(self) -> float:
        """Compute volume from left IMU acceleration."""
        # Map acceleration magnitude to volume
        accel_norm = np.clip(
            (self.left_imu_accel - self.ACCEL_MIN) /
            (self.ACCEL_MAX - self.ACCEL_MIN),
            0.0, 1.0
        )
        volume = self.VOLUME_MIN + accel_norm * (self.VOLUME_MAX - self.VOLUME_MIN)
        self.current_volume = volume
        
        # Update bars widget if available
        if self.bars_widget:
            self.bars_widget.update_data(
                self.left_arm_height_smooth,
                self.right_arm_height_smooth,
                self.current_volume,
                self.current_saturation
            )
        
        return volume
    
    def _compute_saturation(self) -> float:
        """Compute saturation amount from right IMU acceleration."""
        # Map acceleration magnitude to saturation
        accel_norm = np.clip(
            (self.right_imu_accel - self.ACCEL_MIN) /
            (self.ACCEL_MAX - self.ACCEL_MIN),
            0.0, 1.0
        )
        saturation = self.SATURATION_MIN + accel_norm * (self.SATURATION_MAX - self.SATURATION_MIN)
        self.current_saturation = saturation
        
        # Update bars widget if available
        if self.bars_widget:
            self.bars_widget.update_data(
                self.left_arm_height_smooth,
                self.right_arm_height_smooth,
                self.current_volume,
                self.current_saturation
            )
        
        return saturation
    
    def _apply_saturation(self, audio: np.ndarray, saturation: float) -> np.ndarray:
        """
        Apply saturation/distortion to audio.
        
        Uses a tanh-based soft saturation.
        """
        # Soft saturation: tanh(x * (1 + saturation))
        drive = 1.0 + saturation * 2.0  # Drive from 1.0 to 2.6
        saturated = np.tanh(audio * drive)
        return saturated.astype(np.float32)
    
    def paintEvent(self, event):
        """Model1Widget no longer draws anything - widgets are separate."""
        # This widget is now just a controller, drawing is done by bars and equalizer widgets
        pass

