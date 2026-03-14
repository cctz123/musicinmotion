"""Method G: Audio file playback with 7-band EQ."""

import numpy as np
import sounddevice as sd
from pathlib import Path
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtCore import Qt
from ...imu.visualization.base import ImuSquareWidget
from ...audio.utils import map_pitch_to_volume
from ...audio.effects import (
    build_band_index, compute_band_gains_db, gains_db_to_linear,
    apply_motion_eq, apply_soft_limiter
)
from ...utils.constants import (
    AUDIO_SAMPLE_RATE, AUDIO_BLOCK_SIZE, AUDIO_FILE,
    MAX_PITCH_VOLUME_DEG, MAX_ROLL_TIMBRE_DEG_METHOD_G,
    MAX_GAIN_DB, EQ_SMOOTHING_ALPHA, N_BANDS, BAND_EDGES,
    USER_VOLUME_INDICATOR_HEIGHT
)


class ImuSquareSoundFileWidget(ImuSquareWidget):
    """Widget that displays 7-band EQ visualization with audio file playback (Method G).
    
    Extends ImuSquareWidget to add audio file playback with IMU control:
    - Visual: 7-band EQ bars (no blue square)
    - Audio: Plays music/music.mp3 on loop
    - Volume: Controlled by pitch angle
    - Timbre: Controlled by roll angle (7-band tilt EQ)
    - Displays: Volume bar + 7 EQ band bars
    """
    
    # Audio configuration
    AUDIO_SAMPLE_RATE = AUDIO_SAMPLE_RATE
    AUDIO_BLOCK_SIZE = AUDIO_BLOCK_SIZE
    AUDIO_FILE = AUDIO_FILE
    
    # Volume control (pitch angle)
    VOLUME_MIN = 0.0
    VOLUME_MAX = 1.0
    MAX_PITCH_VOLUME_DEG = MAX_PITCH_VOLUME_DEG
    
    # Timbre control (roll angle) - 7-band EQ
    MAX_ROLL_TIMBRE_DEG = MAX_ROLL_TIMBRE_DEG_METHOD_G
    MAX_GAIN_DB = MAX_GAIN_DB
    EQ_SMOOTHING_ALPHA = EQ_SMOOTHING_ALPHA
    BAND_EDGES = BAND_EDGES
    N_BANDS = N_BANDS
    
    # Control bars height
    USER_VOLUME_INDICATOR_HEIGHT = USER_VOLUME_INDICATOR_HEIGHT
    EQ_BARS_AREA_HEIGHT = 300
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_stream = None
        self.current_roll = 0.0
        self.current_pitch = 0.0
        self.current_yaw = 180.0
        
        # Audio file data
        self.audio_data = None
        self.audio_sample_rate = None
        self.audio_position = 0
        
        # Current values for display bars
        self.current_volume_norm = 0.5
        self.current_band_gains_db = np.zeros(self.N_BANDS, dtype=np.float32)
        
        # Smoothed gains for audio processing
        self.smoothed_gains_db = np.zeros(self.N_BANDS, dtype=np.float32)
        
        # Precompute FFT bin to band index mapping
        self.band_index = build_band_index(self.AUDIO_BLOCK_SIZE, self.AUDIO_SAMPLE_RATE)
        
        # Lazy loading
        self._audio_file_loaded = False
    
    def _load_audio_file(self):
        """Load the audio file once at initialization."""
        try:
            import librosa
            
            audio_path = Path(self.AUDIO_FILE)
            if not audio_path.exists():
                print(f"Warning: Audio file not found: {self.AUDIO_FILE}")
                return
            
            self.audio_data, self.audio_sample_rate = librosa.load(
                str(audio_path),
                sr=self.AUDIO_SAMPLE_RATE,
                mono=True
            )
            print(f"Loaded audio file: {self.AUDIO_FILE} ({len(self.audio_data)} samples, {self.audio_sample_rate} Hz)")
        except Exception as e:
            print(f"Error loading audio file: {e}")
            import traceback
            traceback.print_exc()
            self.audio_data = None
    
    def compute_volume_from_pitch(self, pitch_deg: float) -> float:
        """Compute normalized volume value from pitch angle."""
        volume_norm = map_pitch_to_volume(pitch_deg, self.MAX_PITCH_VOLUME_DEG)
        self.current_volume_norm = volume_norm
        return volume_norm
    
    def compute_band_gains_db(self, roll_deg: float) -> np.ndarray:
        """Map IMU roll angle to EQ band gains in dB."""
        gains_db = compute_band_gains_db(roll_deg, self.MAX_ROLL_TIMBRE_DEG)
        self.current_band_gains_db = gains_db
        return gains_db
    
    def apply_motion_eq(self, block: np.ndarray, roll_deg: float) -> np.ndarray:
        """Apply the motion-controlled multi-band EQ to audio block."""
        processed, self.smoothed_gains_db = apply_motion_eq(
            block, roll_deg, self.band_index, self.smoothed_gains_db,
            self.MAX_ROLL_TIMBRE_DEG, self.EQ_SMOOTHING_ALPHA, self.AUDIO_BLOCK_SIZE
        )
        return processed
    
    def start_audio(self):
        """Start the audio stream with file playback."""
        if self.audio_stream is not None:
            return
        
        # Load audio file if not already loaded
        if not self._audio_file_loaded:
            self._load_audio_file()
            self._audio_file_loaded = True
        
        if self.audio_data is None:
            print("Error: Audio file not loaded")
            return
        
        def audio_callback(outdata, frames, time_info, status):
            try:
                if status:
                    print("Audio status:", status)
                
                if self.audio_data is None:
                    outdata.fill(0)
                    return
                
                roll_deg = self.current_roll
                pitch_deg = self.current_pitch
                yaw_deg = self.current_yaw
                
                # Volume mapping
                volume_norm = self.compute_volume_from_pitch(pitch_deg)
                
                # Pan mapping
                yaw_normalized = (yaw_deg - 180.0) / 180.0
                pan = max(-1.0, min(1.0, yaw_normalized))
                
                # Read audio chunk from file
                chunk = np.zeros(frames, dtype=np.float32)
                samples_read = 0
                
                while samples_read < frames:
                    remaining = frames - samples_read
                    available = len(self.audio_data) - self.audio_position
                    
                    if available > 0:
                        read_count = min(remaining, available)
                        chunk[samples_read:samples_read + read_count] = self.audio_data[
                            self.audio_position:self.audio_position + read_count
                        ]
                        self.audio_position += read_count
                        samples_read += read_count
                    
                    # Loop if we've reached the end
                    if self.audio_position >= len(self.audio_data):
                        self.audio_position = 0
                
                # Apply 7-band EQ (timbre controlled by roll)
                chunk = self.apply_motion_eq(chunk, roll_deg)
                
                # Apply volume (pitch-controlled)
                chunk *= volume_norm
                
                # Simple stereo output
                outdata[:, 0] = chunk
                outdata[:, 1] = chunk
                
            except Exception as e:
                print(f"Error in Method G audio callback: {e}")
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
        self.audio_position = 0
    
    def set_angles_for_audio(self, roll_deg: float, pitch_deg: float, yaw_deg: float):
        """Update angles for audio generation."""
        self.current_roll = roll_deg
        self.current_pitch = pitch_deg
        self.current_yaw = yaw_deg
        
        # Compute EQ gains for display
        self.compute_band_gains_db(roll_deg)
        
        # Compute volume for display
        self.compute_volume_from_pitch(pitch_deg)
    
    def _update_display(self):
        """Update the display bars."""
        self.update()
    
    def paintEvent(self, event):
        """Paint 7-band EQ bars and Volume bar."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        widget_width = self.width()
        widget_height = self.height()
        
        # Draw 7-band EQ bars in center area
        self._draw_eq_bars(painter, widget_width, widget_height)
        
        # Draw Volume bar at the bottom
        self._draw_control_bars(painter, widget_width, widget_height)
    
    def _draw_eq_bars(self, painter, widget_width, widget_height):
        """Draw 7-band EQ bars in the center area."""
        eq_area_top = 20
        eq_area_bottom = widget_height - self.USER_VOLUME_INDICATOR_HEIGHT - 20
        eq_area_height = eq_area_bottom - eq_area_top
        
        n_bars = self.N_BANDS
        bar_spacing = 10
        bar_width = (widget_width - (n_bars + 1) * bar_spacing) // n_bars
        bar_max_height = eq_area_height - 60
        
        total_width = n_bars * bar_width + (n_bars - 1) * bar_spacing
        start_x = (widget_width - total_width) // 2
        
        band_labels = ["Sub", "Bass", "LoMid", "Mid", "UpMid", "Pres", "Brill"]
        
        for i in range(n_bars):
            bar_x = start_x + i * (bar_width + bar_spacing)
            bar_center_y = eq_area_top + eq_area_height // 2
            
            gain_db = self.current_band_gains_db[i]
            normalized = gain_db / self.MAX_GAIN_DB
            normalized = max(-1.0, min(1.0, normalized))
            
            bar_height_frac = abs(normalized)
            bar_height = bar_height_frac * bar_max_height // 2
            
            # Draw bar background
            painter.setBrush(QColor("#ecf0f1"))
            painter.setPen(QPen(QColor("#bdc3c7"), 1))
            painter.drawRect(bar_x, bar_center_y - bar_max_height // 2, bar_width, bar_max_height)
            
            # Draw center line
            painter.setPen(QPen(QColor("#7f8c8d"), 1, Qt.DashLine))
            painter.drawLine(bar_x, bar_center_y, bar_x + bar_width, bar_center_y)
            
            # Draw gain bar
            if gain_db > 0.1:
                fill_color = QColor("#2ecc71")
                bar_y = bar_center_y - int(bar_height)
                bar_h = int(bar_height)
            elif gain_db < -0.1:
                fill_color = QColor("#e74c3c")
                bar_y = bar_center_y
                bar_h = int(bar_height)
            else:
                fill_color = QColor("#95a5a6")
                bar_y = bar_center_y
                bar_h = 1
            
            painter.setBrush(fill_color)
            painter.setPen(QPen(fill_color.darker(120), 1))
            painter.drawRect(bar_x, bar_y, bar_width, bar_h)
            
            # Draw band label
            painter.setPen(QColor("#2c3e50"))
            painter.setFont(QFont("Arial", 9))
            label_text = band_labels[i]
            label_rect = painter.fontMetrics().boundingRect(label_text)
            label_x = bar_x + (bar_width - label_rect.width()) // 2
            label_y = bar_center_y + bar_max_height // 2 + 15
            painter.drawText(label_x, label_y, label_text)
            
            # Draw gain value
            gain_text = f"{gain_db:+.1f}dB"
            gain_rect = painter.fontMetrics().boundingRect(gain_text)
            gain_x = bar_x + (bar_width - gain_rect.width()) // 2
            gain_y = bar_center_y - bar_max_height // 2 - 5
            painter.setFont(QFont("Arial", 8))
            painter.drawText(gain_x, gain_y, gain_text)
    
    def _draw_control_bars(self, painter, widget_width, widget_height):
        """Draw Volume bar at the bottom."""
        bar_area_y = widget_height - self.USER_VOLUME_INDICATOR_HEIGHT
        bar_height = 20
        label_width = 80
        value_width = 60
        bar_x = label_width
        bar_width = widget_width - bar_x - value_width - 20
        
        vol_y = bar_area_y + 10
        self._draw_single_bar(painter, bar_x, vol_y, bar_width, bar_height,
                             "Volume:", self.current_volume_norm, 0.0, 1.0,
                             widget_width, value_width, "#3498db", False)
    
    def _draw_single_bar(self, painter, bar_x, bar_y, bar_width, bar_height,
                        label, value, min_val, max_val, widget_width, value_width,
                        fill_color, is_clickable):
        """Draw a single control bar with label and value."""
        if is_clickable:
            painter.fillRect(0, bar_y - 5, widget_width, bar_height + 10, QColor("#f5f5f5"))
        
        painter.setPen(QColor("#333333"))
        painter.setFont(QFont("Arial", 10))
        label_rect = painter.fontMetrics().boundingRect(label)
        painter.drawText(10, bar_y + bar_height // 2 + label_rect.height() // 2 - 2, label)
        
        if max_val > min_val:
            percent = ((value - min_val) / (max_val - min_val)) * 100.0
        else:
            percent = 0.0
        percent = max(0.0, min(100.0, percent))
        
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#ccc"))
        painter.drawRoundedRect(bar_x, bar_y, bar_width, bar_height, 3, 3)
        
        fill_width = int((percent / 100.0) * bar_width)
        if fill_width > 0:
            painter.setBrush(QColor(fill_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar_x, bar_y, fill_width, bar_height, 3, 3)
        
        value_text = f"{percent:.1f}%"
        value_rect = painter.fontMetrics().boundingRect(value_text)
        value_x = widget_width - value_width
        value_y = bar_y + bar_height // 2 + value_rect.height() // 2 - 2
        painter.setPen(QColor("#333333"))
        painter.drawText(value_x, value_y, value_text)

