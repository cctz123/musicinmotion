"""Method D: Loudness control with acceleration-based volume."""

import time
import numpy as np
import sounddevice as sd
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QTimer
from ...imu.visualization.base import ImuSquareWidget
from ...audio.utils import map_pitch_to_frequency, map_roll_to_pan, compute_equal_power_panning
from ...audio.synthesis import generate_sine_wave
from ...utils.constants import (
    AUDIO_SAMPLE_RATE, AUDIO_BLOCK_SIZE, BASE_FREQ, MAX_FREQ,
    MAX_ROLL_PAN_DEG, AUDIO_AMP, MAX_TILT_DEG,
    AMP_MIN, AMP_MAX, VOLUME_STEP, ACCEL_THRESHOLD_HIGH,
    ACCEL_THRESHOLD_LOW, MEASUREMENT_COOLDOWN
)


class ImuSquareSoundLoudnessWidget(ImuSquareWidget):
    """Widget that displays a blue square with audio including acceleration-based loudness (Method D).
    
    Extends ImuSquareWidget to add acceleration-based amplitude:
    - Visual: Same as Method B (blue square)
    - Audio: Pitch controls frequency, roll controls stereo panning
    - Loudness: Amplitude controlled by Z-axis accelerometer (step-based, 2s cooldown)
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
    
    # Acceleration-based loudness configuration
    AMP_MIN = AMP_MIN
    AMP_MAX = AMP_MAX
    VOLUME_STEP = VOLUME_STEP
    ACCEL_THRESHOLD_HIGH = ACCEL_THRESHOLD_HIGH
    ACCEL_THRESHOLD_LOW = ACCEL_THRESHOLD_LOW
    MEASUREMENT_COOLDOWN = MEASUREMENT_COOLDOWN
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_stream = None
        self.current_roll = 0.0
        self.current_pitch = 0.0
        self.audio_phase = 0.0
        
        # Acceleration-based volume control state
        self.current_amplitude = self.AMP_MIN  # Start at minimum
        self.last_measurement_time = None
        self.current_accel_z = 1.0  # Default to 1g (flat)
        
        # Volume indicator height (reserved at bottom of widget)
        self.VOLUME_INDICATOR_HEIGHT = 50
        
        # Timer to update volume display periodically
        self.volume_update_timer = QTimer(self)
        self.volume_update_timer.timeout.connect(self._update_volume_display)
        self.volume_update_timer.start(50)  # Update every 50ms (~20 Hz)
    
    def update_accel_z(self, accel_z_g: float):
        """Update Z-axis acceleration and adjust volume based on thresholds."""
        self.current_accel_z = accel_z_g
        
        now = time.time()
        
        # Check if enough time has passed since last volume adjustment
        if self.last_measurement_time is not None:
            time_since_last_adjustment = now - self.last_measurement_time
            if time_since_last_adjustment < self.MEASUREMENT_COOLDOWN:
                return
        
        # Check thresholds and adjust volume if needed
        volume_changed = False
        if accel_z_g > self.ACCEL_THRESHOLD_HIGH:
            old_amplitude = self.current_amplitude
            self.current_amplitude = min(
                self.current_amplitude + self.VOLUME_STEP,
                self.AMP_MAX
            )
            if self.current_amplitude != old_amplitude:
                volume_changed = True
        elif accel_z_g < self.ACCEL_THRESHOLD_LOW:
            old_amplitude = self.current_amplitude
            self.current_amplitude = max(
                self.current_amplitude - self.VOLUME_STEP,
                self.AMP_MIN
            )
            if self.current_amplitude != old_amplitude:
                volume_changed = True
        
        if volume_changed:
            self.last_measurement_time = now
    
    def paintEvent(self, event):
        """Paint the blue square and volume indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        widget_width = self.width()
        widget_height = self.height()
        
        # Reserve space at bottom for volume indicator
        square_area_height = widget_height - self.VOLUME_INDICATOR_HEIGHT
        
        # Center of the square drawing area
        cx = widget_width // 2
        cy = square_area_height // 2
        
        # Calculate maximum distance from center (with padding)
        max_dx = widget_width // 2 - self.SQUARE_SIZE // 2 - 5
        max_dy = square_area_height // 2 - self.SQUARE_SIZE // 2 - 5
        
        # Map normalized position to pixel coordinates
        x_offset = (self.square_x - 0.5) * 2 * max_dx
        y_offset = (self.square_y - 0.5) * 2 * max_dy
        
        square_x_pixel = int(cx + x_offset)
        square_y_pixel = int(cy + y_offset)
        
        # Draw blue square (filled, no border)
        painter.setBrush(QColor("#3498db"))
        painter.setPen(Qt.NoPen)
        painter.drawRect(
            square_x_pixel - self.SQUARE_SIZE // 2,
            square_y_pixel - self.SQUARE_SIZE // 2,
            self.SQUARE_SIZE,
            self.SQUARE_SIZE
        )
        
        # Draw volume indicator at the bottom
        self._draw_volume_indicator(painter, widget_width, widget_height)
    
    def _draw_volume_indicator(self, painter, widget_width, widget_height):
        """Draw the volume indicator bar and value."""
        vol_y = widget_height - self.VOLUME_INDICATOR_HEIGHT
        vol_height = self.VOLUME_INDICATOR_HEIGHT
        
        # Calculate volume percentage
        if self.AMP_MAX > self.AMP_MIN:
            vol_percent = ((self.current_amplitude - self.AMP_MIN) / (self.AMP_MAX - self.AMP_MIN)) * 100.0
        else:
            vol_percent = 0.0
        vol_percent = max(0.0, min(100.0, vol_percent))
        
        # Draw background
        painter.fillRect(0, vol_y, widget_width, vol_height, QColor("#f5f5f5"))
        
        # Draw label
        painter.setPen(QColor("#333333"))
        painter.setFont(QFont("Arial", 10))
        label_text = "Volume:"
        label_rect = painter.fontMetrics().boundingRect(label_text)
        painter.drawText(10, vol_y + vol_height // 2 + label_rect.height() // 2 - 2, label_text)
        
        # Draw volume bar
        bar_x = 80
        bar_y = vol_y + 15
        bar_width = widget_width - bar_x - 100
        bar_height = 20
        
        # Bar background
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#ccc"))
        painter.drawRoundedRect(bar_x, bar_y, bar_width, bar_height, 3, 3)
        
        # Bar fill
        fill_width = int((vol_percent / 100.0) * bar_width)
        if fill_width > 0:
            painter.setBrush(QColor("#3498db"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar_x, bar_y, fill_width, bar_height, 3, 3)
        
        # Draw value
        value_text = f"{vol_percent:.1f}%"
        value_rect = painter.fontMetrics().boundingRect(value_text)
        value_x = widget_width - value_rect.width() - 10
        value_y = vol_y + vol_height // 2 + value_rect.height() // 2 - 2
        painter.setPen(QColor("#333333"))
        painter.drawText(value_x, value_y, value_text)
    
    def _update_volume_display(self):
        """Update the volume display (called by timer)."""
        self.update()
    
    def mousePressEvent(self, event):
        """Handle mouse clicks on the volume bar to set volume directly."""
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        
        widget_width = self.width()
        widget_height = self.height()
        vol_y = widget_height - self.VOLUME_INDICATOR_HEIGHT
        
        bar_x = 80
        bar_y = vol_y + 15
        bar_width = widget_width - bar_x - 100
        bar_height = 20
        
        click_x = event.x()
        click_y = event.y()
        
        if (bar_x <= click_x <= bar_x + bar_width and 
            bar_y <= click_y <= bar_y + bar_height):
            relative_x = click_x - bar_x
            vol_percent = (relative_x / bar_width) * 100.0
            vol_percent = max(0.0, min(100.0, vol_percent))
            
            if self.AMP_MAX > self.AMP_MIN:
                new_amplitude = self.AMP_MIN + (vol_percent / 100.0) * (self.AMP_MAX - self.AMP_MIN)
            else:
                new_amplitude = self.AMP_MIN
            
            self.current_amplitude = max(self.AMP_MIN, min(self.AMP_MAX, new_amplitude))
            self.last_measurement_time = None
            self.update()
        
        return super().mousePressEvent(event)
    
    def start_audio(self):
        """Start the audio stream with acceleration-based loudness."""
        if self.audio_stream is not None:
            return
        
        self.current_amplitude = self.AMP_MIN
        self.last_measurement_time = None
        
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
                
                # Acceleration-based loudness
                amp = self.current_amplitude
                
                # Generate sine wave
                mono, self.audio_phase = generate_sine_wave(freq, frames, self.audio_phase)
                mono *= amp
                
                # Equal-power stereo panning
                left_gain, right_gain = compute_equal_power_panning(pan)
                
                outdata[:, 0] = mono * left_gain
                outdata[:, 1] = mono * right_gain
            except Exception as e:
                print(f"Error in Method D audio callback: {e}")
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
        """Stop the audio stream and reset acceleration tracking."""
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        self.audio_phase = 0.0
        self.current_amplitude = self.AMP_MIN
        self.last_measurement_time = None
        self.current_accel_z = 1.0
    
    def set_angles_for_audio(self, roll_deg: float, pitch_deg: float):
        """Update angles for audio generation."""
        self.current_roll = roll_deg
        self.current_pitch = pitch_deg

