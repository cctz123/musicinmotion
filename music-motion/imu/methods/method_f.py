"""Method F: Timbre control with waveform morphing."""

import numpy as np
import sounddevice as sd
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtCore import Qt
from ...imu.visualization.base import ImuSquareWidget
from ...audio.utils import map_pitch_to_frequency, map_yaw_to_pan, compute_equal_power_panning
from ...audio.synthesis import generate_sine_wave, generate_sawtooth_wave, morph_waveforms
from ...audio.utils import map_roll_to_timbre
from ...utils.constants import (
    AUDIO_SAMPLE_RATE, AUDIO_BLOCK_SIZE, BASE_FREQ, MAX_FREQ,
    AUDIO_AMP, MAX_TILT_DEG, MAX_ROLL_TIMBRE_DEG,
    AMP_MIN, AMP_MAX, VOLUME_INDICATOR_HEIGHT
)


class ImuSquareSoundTimbreWidget(ImuSquareWidget):
    """Widget that displays a blue square with audio including timbre control from roll and yaw-based panning (Method F).
    
    Extends ImuSquareWidget to add audio with timbre control:
    - Visual: Same as Method B (blue square)
    - Audio: Pitch controls frequency, yaw controls stereo panning, roll controls timbre
    - Volume: User-controlled via clickable volume bar (no motion control)
    - Timbre: Roll angle morphs between sine (warm) and sawtooth (bright) waveforms
    - Uses same tilt mapping as Method B for visual
    - Uses extended roll range for timbre control (MAX_ROLL_TIMBRE_DEG = 45.0°)
    - Displays three bars: Volume (user-controlled), Pitch (IMU-controlled), Timbre (IMU-controlled)
    """
    
    # Audio configuration
    AUDIO_SAMPLE_RATE = AUDIO_SAMPLE_RATE
    AUDIO_BLOCK_SIZE = AUDIO_BLOCK_SIZE
    BASE_FREQ = BASE_FREQ
    MAX_FREQ = MAX_FREQ
    AUDIO_AMP = AUDIO_AMP
    MAX_TILT_DEG = MAX_TILT_DEG
    
    # Volume control (user-adjustable, no motion control)
    VOLUME_INDICATOR_HEIGHT = VOLUME_INDICATOR_HEIGHT
    AMP_MIN = AMP_MIN
    AMP_MAX = AMP_MAX
    
    MAX_ROLL_TIMBRE_DEG = MAX_ROLL_TIMBRE_DEG
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_stream = None
        self.current_roll = 0.0
        self.current_pitch = 0.0
        self.current_yaw = 180.0  # Initialize to center (180° = center pan)
        self.audio_phase = 0.0
        
        # User-controlled volume (no motion control)
        self.current_amplitude = self.AMP_MIN + (self.AMP_MAX - self.AMP_MIN) * 0.5  # Start at 50%
        
        # Current values for display bars
        self.current_pitch_norm = 0.5  # Normalized pitch (0-1)
        self.current_timbre_norm = 0.5  # Normalized timbre (0-1)
    
    def paintEvent(self, event):
        """Paint the blue square and three control bars (Volume, Pitch, Timbre)."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        widget_width = self.width()
        widget_height = self.height()
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
        
        # Calculate distance from square center to widget center
        square_center_x = square_x_pixel
        square_center_y = square_y_pixel
        distance_from_center = ((square_center_x - cx)**2 + (square_center_y - cy)**2)**0.5
        
        # Check if roll and pitch are within target tolerance
        in_target_zone = (abs(self.current_roll_deg) <= self.TARGET_TOLERANCE_DEG and 
                         abs(self.current_pitch_deg) <= self.TARGET_TOLERANCE_DEG)
        
        # Check if square is inside the target circle
        square_in_circle = distance_from_center <= self.TARGET_CIRCLE_RADIUS
        
        # Choose circle color: green if in target zone AND square is inside, gray otherwise
        if in_target_zone and square_in_circle:
            circle_color = QColor("#2ecc71")  # Green
        else:
            circle_color = QColor("#95a5a6")  # Gray
        
        # Always draw target circle
        painter.setBrush(circle_color)
        painter.setPen(QPen(QColor("#34495e"), 2))  # Dark border
        painter.drawEllipse(
            cx - self.TARGET_CIRCLE_RADIUS,
            cy - self.TARGET_CIRCLE_RADIUS,
            self.TARGET_CIRCLE_RADIUS * 2,
            self.TARGET_CIRCLE_RADIUS * 2
        )
        
        # Draw blue square (circle)
        painter.setBrush(QColor("#3498db"))  # Blue color
        painter.setPen(QPen(QColor("#2980b9"), 2))
        painter.drawEllipse(
            square_x_pixel - self.SQUARE_SIZE // 2,
            square_y_pixel - self.SQUARE_SIZE // 2,
            self.SQUARE_SIZE,
            self.SQUARE_SIZE
        )
        
        # Draw three control bars at the bottom
        self._draw_control_bars(painter, widget_width, widget_height)
    
    def _draw_control_bars(self, painter, widget_width, widget_height):
        """Draw Volume, Pitch, and Timbre bars."""
        bar_area_y = widget_height - self.VOLUME_INDICATOR_HEIGHT
        bar_height = 20
        bar_spacing = 5
        label_width = 80
        value_width = 60
        bar_x = label_width
        bar_width = widget_width - bar_x - value_width - 20
        
        # Bar 1: Volume (user-controlled)
        vol_y = bar_area_y + 10
        self._draw_single_bar(painter, bar_x, vol_y, bar_width, bar_height,
                             "Volume:", self.current_amplitude, self.AMP_MIN, self.AMP_MAX,
                             widget_width, value_width, "#3498db", True)
        
        # Bar 2: Pitch (IMU-controlled, read-only)
        pitch_y = vol_y + bar_height + bar_spacing
        self._draw_single_bar(painter, bar_x, pitch_y, bar_width, bar_height,
                             "Pitch:", self.current_pitch_norm, 0.0, 1.0,
                             widget_width, value_width, "#27ae60", False)
        
        # Bar 3: Timbre (IMU-controlled, read-only)
        timbre_y = pitch_y + bar_height + bar_spacing
        self._draw_single_bar(painter, bar_x, timbre_y, bar_width, bar_height,
                             "Timbre:", self.current_timbre_norm, 0.0, 1.0,
                             widget_width, value_width, "#e74c3c", False)
    
    def _draw_single_bar(self, painter, bar_x, bar_y, bar_width, bar_height,
                        label, value, min_val, max_val, widget_width, value_width,
                        fill_color, is_clickable):
        """Draw a single control bar with label and value."""
        # Draw background for bar area
        if is_clickable:
            painter.fillRect(0, bar_y - 5, widget_width, bar_height + 10, QColor("#f5f5f5"))
        
        # Draw label
        painter.setPen(QColor("#333333"))
        painter.setFont(QFont("Arial", 10))
        label_rect = painter.fontMetrics().boundingRect(label)
        painter.drawText(10, bar_y + bar_height // 2 + label_rect.height() // 2 - 2, label)
        
        # Calculate fill percentage
        if max_val > min_val:
            percent = ((value - min_val) / (max_val - min_val)) * 100.0
        else:
            percent = 0.0
        percent = max(0.0, min(100.0, percent))
        
        # Draw bar background
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#ccc"))
        painter.drawRoundedRect(bar_x, bar_y, bar_width, bar_height, 3, 3)
        
        # Draw bar fill
        fill_width = int((percent / 100.0) * bar_width)
        if fill_width > 0:
            painter.setBrush(QColor(fill_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar_x, bar_y, fill_width, bar_height, 3, 3)
        
        # Draw value
        value_text = f"{percent:.1f}%"
        value_rect = painter.fontMetrics().boundingRect(value_text)
        value_x = widget_width - value_width
        value_y = bar_y + bar_height // 2 + value_rect.height() // 2 - 2
        painter.setPen(QColor("#333333"))
        painter.drawText(value_x, value_y, value_text)
    
    def mousePressEvent(self, event):
        """Handle mouse clicks on the volume bar to set volume directly."""
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        
        widget_width = self.width()
        widget_height = self.height()
        bar_area_y = widget_height - self.VOLUME_INDICATOR_HEIGHT
        
        bar_height = 20
        bar_spacing = 5
        label_width = 80
        value_width = 60
        bar_x = label_width
        bar_width = widget_width - bar_x - value_width - 20
        
        # Volume bar coordinates (only clickable bar)
        vol_y = bar_area_y + 10
        
        click_x = event.x()
        click_y = event.y()
        
        # Check if click is within the volume bar area
        if (bar_x <= click_x <= bar_x + bar_width and 
            vol_y <= click_y <= vol_y + bar_height):
            # Calculate volume percentage based on click position
            relative_x = click_x - bar_x
            vol_percent = (relative_x / bar_width) * 100.0
            vol_percent = max(0.0, min(100.0, vol_percent))
            
            # Convert percentage to amplitude
            if self.AMP_MAX > self.AMP_MIN:
                new_amplitude = self.AMP_MIN + (vol_percent / 100.0) * (self.AMP_MAX - self.AMP_MIN)
            else:
                new_amplitude = self.AMP_MIN
            
            # Set the new amplitude
            self.current_amplitude = max(self.AMP_MIN, min(self.AMP_MAX, new_amplitude))
            
            # Trigger repaint to show new volume
            self.update()
        
        return super().mousePressEvent(event)
    
    def _update_display(self):
        """Update the display bars (called periodically)."""
        self.update()
    
    def compute_timbre_from_roll(self, roll_deg: float) -> float:
        """Compute normalized timbre value from roll angle."""
        timbre_norm = map_roll_to_timbre(roll_deg, self.MAX_ROLL_TIMBRE_DEG)
        self.current_timbre_norm = timbre_norm  # Store for display
        return timbre_norm
    
    def start_audio(self):
        """Start the audio stream with timbre control."""
        if self.audio_stream is not None:
            return
        
        def audio_callback(outdata, frames, time_info, status):
            try:
                if status:
                    print("Audio status:", status)
                
                roll_deg = self.current_roll
                pitch_deg = self.current_pitch
                yaw_deg = self.current_yaw
                
                # Pitch mapping
                pitch_clamped = max(-self.MAX_TILT_DEG, min(self.MAX_TILT_DEG, pitch_deg))
                norm = (pitch_clamped + self.MAX_TILT_DEG) / (2 * self.MAX_TILT_DEG)
                self.current_pitch_norm = norm
                freq = map_pitch_to_frequency(pitch_deg, self.MAX_TILT_DEG)
                
                # Pan mapping
                pan = map_yaw_to_pan(yaw_deg)
                
                # Timbre mapping
                timbre_norm = self.compute_timbre_from_roll(roll_deg)
                self.current_timbre_norm = timbre_norm
                
                # User-controlled volume
                amp = self.current_amplitude
                
                # Generate waveforms
                sine_wave, self.audio_phase = generate_sine_wave(freq, frames, self.audio_phase)
                sawtooth_wave, _ = generate_sawtooth_wave(freq, frames, self.audio_phase)
                
                # Morph between sine and sawtooth
                mono = morph_waveforms(sine_wave, sawtooth_wave, timbre_norm)
                mono *= amp
                
                # Equal-power stereo panning
                left_gain, right_gain = compute_equal_power_panning(pan)
                
                outdata[:, 0] = mono * left_gain
                outdata[:, 1] = mono * right_gain
            except Exception as e:
                print(f"Error in Method F audio callback: {e}")
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
    
    def set_angles_for_audio(self, roll_deg: float, pitch_deg: float, yaw_deg: float):
        """Update angles for audio generation."""
        self.current_roll = roll_deg
        self.current_pitch = pitch_deg
        self.current_yaw = yaw_deg

