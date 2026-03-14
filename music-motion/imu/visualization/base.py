"""Base IMU visualization widget."""

import math
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtCore import Qt
from ...utils.constants import MAX_TILT_DEG, SQUARE_SIZE, TARGET_TOLERANCE_DEG, TARGET_CIRCLE_RADIUS
from ...utils.math_utils import map_tilt_to_position


class ImuSquareWidget(QWidget):
    """Base widget that displays a blue square controlled by IMU tilt.
    
    This replicates the functionality from imu_tkinter.py:
    - White background canvas
    - Blue square that moves based on roll/pitch angles
    - Uses ±5.0 degrees as maximum tilt range
    - Roll controls left/right movement
    - Pitch controls up/down movement (inverted)
    - Game mode: Target circle appears when roll/pitch are within ±1°, turns green when square is inside
    """
    
    # Configuration matching imu_tkinter.py
    MAX_TILT_DEG = MAX_TILT_DEG
    SQUARE_SIZE = SQUARE_SIZE
    TARGET_TOLERANCE_DEG = TARGET_TOLERANCE_DEG
    TARGET_CIRCLE_RADIUS = TARGET_CIRCLE_RADIUS
    
    def get_angles(self):
        """Get current angles from square position (for audio). Override in subclasses."""
        return None, None  # roll, pitch
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.square_x = 0.5  # Normalized position (0.0 to 1.0) - center
        self.square_y = 0.5  # Normalized position (0.0 to 1.0) - center
        self.current_roll_deg = 0.0  # Current roll angle for target detection
        self.current_pitch_deg = 0.0  # Current pitch angle for target detection
        
        # LPF filter state
        self.lpf_enabled = False
        self.lpf_cutoff_hz = 5.0  # Default cutoff frequency
        self.sample_rate = 200.0  # Hz (5ms polling = 200 Hz)
        self._update_lpf_alpha()
        self.roll_filtered = 0.0
        self.pitch_filtered = 0.0
        self._filter_initialized = False
        
        self.setMinimumSize(400, 400)
        self.setStyleSheet("background-color: white;")
        
    def set_square_position(self, x: float, y: float):
        """Set square position (normalized 0.0 to 1.0)."""
        # Clamp values to valid range
        self.square_x = max(0.0, min(1.0, x))
        self.square_y = max(0.0, min(1.0, y))
        self.update()  # Trigger repaint
    
    def set_angles(self, roll_deg: float, pitch_deg: float):
        """Set current angles for target detection."""
        # Apply LPF filter if enabled
        if self.lpf_enabled:
            if not self._filter_initialized:
                # Initialize filter state with first sample
                self.roll_filtered = roll_deg
                self.pitch_filtered = pitch_deg
                self._filter_initialized = True
            else:
                # Apply first-order IIR low-pass filter
                # y[n] = alpha * x[n] + (1 - alpha) * y[n-1]
                self.roll_filtered = self.lpf_alpha * roll_deg + (1.0 - self.lpf_alpha) * self.roll_filtered
                self.pitch_filtered = self.lpf_alpha * pitch_deg + (1.0 - self.lpf_alpha) * self.pitch_filtered
            
            # Use filtered angles for display and target detection
            self.current_roll_deg = self.roll_filtered
            self.current_pitch_deg = self.pitch_filtered
        else:
            # Use raw angles
            self.current_roll_deg = roll_deg
            self.current_pitch_deg = pitch_deg
            if self._filter_initialized:
                # Reset filter state when disabled
                self._filter_initialized = False
        
        self.update()  # Trigger repaint to update target circle
    
    def _update_lpf_alpha(self):
        """Update LPF filter coefficient based on cutoff frequency."""
        # First-order IIR low-pass filter
        # alpha = 1 - exp(-2*pi*fc/fs)
        # where fc = cutoff frequency, fs = sample rate
        if self.sample_rate > 0:
            self.lpf_alpha = 1.0 - math.exp(-2.0 * math.pi * self.lpf_cutoff_hz / self.sample_rate)
        else:
            self.lpf_alpha = 0.1  # Default
    
    def set_lpf_enabled(self, enabled: bool):
        """Enable or disable LPF filtering."""
        self.lpf_enabled = enabled
        if not enabled:
            # Reset filter state when disabled
            self._filter_initialized = False
    
    def set_lpf_cutoff(self, cutoff_hz: float):
        """Set LPF cutoff frequency in Hz."""
        self.lpf_cutoff_hz = cutoff_hz
        self._update_lpf_alpha()
        
    def map_tilt_to_position(self, roll_deg: float, pitch_deg: float) -> tuple:
        """Map roll/pitch in degrees to normalized position (0.0 to 1.0)."""
        return map_tilt_to_position(roll_deg, pitch_deg, self.MAX_TILT_DEG)
        
    def paintEvent(self, event):
        """Paint the blue square at the current position and target circle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate square position in widget coordinates
        widget_width = self.width()
        widget_height = self.height()
        
        # Center of the widget
        cx = widget_width // 2
        cy = widget_height // 2
        
        # Calculate maximum distance from center (with padding)
        max_dx = widget_width // 2 - self.SQUARE_SIZE // 2 - 5
        max_dy = widget_height // 2 - self.SQUARE_SIZE // 2 - 5
        
        # Map normalized position to pixel coordinates
        square_x_pixel = cx + (self.square_x - 0.5) * 2 * max_dx
        square_y_pixel = cy + (self.square_y - 0.5) * 2 * max_dy
        
        # Draw target circle if angles are within ±1°
        roll_abs = abs(self.current_roll_deg)
        pitch_abs = abs(self.current_pitch_deg)
        
        if roll_abs <= 1.0 and pitch_abs <= 1.0:
            # Check if square is inside target circle
            square_dist_from_center = (
                (square_x_pixel - cx) ** 2 + (square_y_pixel - cy) ** 2
            ) ** 0.5
            
            target_radius_pixel = self.TARGET_CIRCLE_RADIUS
            
            if square_dist_from_center <= target_radius_pixel:
                # Green: square is inside target
                painter.setPen(QColor("#27ae60"))
                painter.setBrush(QColor("#2ecc71"))
            else:
                # Yellow: target visible but square not inside
                painter.setPen(QColor("#f39c12"))
                painter.setBrush(QColor("#f1c40f"))
            
            painter.drawEllipse(
                cx - target_radius_pixel,
                cy - target_radius_pixel,
                target_radius_pixel * 2,
                target_radius_pixel * 2
            )
        
        # Draw blue square
        painter.setBrush(QColor("#3498db"))
        painter.setPen(QColor("#2980b9"))
        painter.drawRect(
            int(square_x_pixel - self.SQUARE_SIZE // 2),
            int(square_y_pixel - self.SQUARE_SIZE // 2),
            self.SQUARE_SIZE,
            self.SQUARE_SIZE
        )

