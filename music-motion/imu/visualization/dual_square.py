"""Dual square visualization widget (Method E)."""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtCore import Qt
from ...utils.constants import MAX_TILT_DEG, SQUARE_SIZE, TARGET_TOLERANCE_DEG, TARGET_CIRCLE_RADIUS
from ...utils.math_utils import map_tilt_to_position


class ImuDualSquareWidget(QWidget):
    """Widget that displays two squares (blue and red) controlled by two IMUs (Method E).
    
    This extends Method B functionality to support dual IMU input:
    - Blue square controlled by first IMU (port from config)
    - Red square controlled by second IMU (port2 from config)
    - Uses same tilt mapping as Method B (±5.0 degrees)
    - Game mode: Target circle appears when roll/pitch are within ±0.3°, turns green when blue square is inside
    """
    
    # Configuration matching ImuSquareWidget
    MAX_TILT_DEG = MAX_TILT_DEG
    SQUARE_SIZE = SQUARE_SIZE
    TARGET_TOLERANCE_DEG = TARGET_TOLERANCE_DEG
    TARGET_CIRCLE_RADIUS = TARGET_CIRCLE_RADIUS
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Blue square (IMU 1) position
        self.blue_square_x = 0.5  # Normalized position (0.0 to 1.0) - center
        self.blue_square_y = 0.5  # Normalized position (0.0 to 1.0) - center
        self.blue_roll_deg = 0.0  # Current roll angle for target detection
        self.blue_pitch_deg = 0.0  # Current pitch angle for target detection
        
        # Red square (IMU 2) position
        self.red_square_x = 0.5  # Normalized position (0.0 to 1.0) - center
        self.red_square_y = 0.5  # Normalized position (0.0 to 1.0) - center
        self.red_roll_deg = 0.0  # Current roll angle for target detection
        self.red_pitch_deg = 0.0  # Current pitch angle for target detection
        
        self.setMinimumSize(400, 400)
        self.setStyleSheet("background-color: white;")
        
    def set_blue_square_position(self, x: float, y: float):
        """Set blue square position (normalized 0.0 to 1.0)."""
        self.blue_square_x = max(0.0, min(1.0, x))
        self.blue_square_y = max(0.0, min(1.0, y))
        self.update()  # Trigger repaint
    
    def set_red_square_position(self, x: float, y: float):
        """Set red square position (normalized 0.0 to 1.0)."""
        self.red_square_x = max(0.0, min(1.0, x))
        self.red_square_y = max(0.0, min(1.0, y))
        self.update()  # Trigger repaint
    
    def set_blue_angles(self, roll_deg: float, pitch_deg: float):
        """Set current angles for blue square (IMU 1) target detection."""
        self.blue_roll_deg = roll_deg
        self.blue_pitch_deg = pitch_deg
        self.update()  # Trigger repaint to update target circle
    
    def set_red_angles(self, roll_deg: float, pitch_deg: float):
        """Set current angles for red square (IMU 2) target detection."""
        self.red_roll_deg = roll_deg
        self.red_pitch_deg = pitch_deg
        self.update()  # Trigger repaint to update target circle
        
    def map_tilt_to_position(self, roll_deg: float, pitch_deg: float) -> tuple:
        """Map roll/pitch in degrees to normalized position (0.0 to 1.0)."""
        return map_tilt_to_position(roll_deg, pitch_deg, self.MAX_TILT_DEG)
        
    def paintEvent(self, event):
        """Paint both blue and red squares at their positions and target circle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate positions in widget coordinates
        widget_width = self.width()
        widget_height = self.height()
        
        # Center of the widget
        cx = widget_width // 2
        cy = widget_height // 2
        
        # Calculate maximum distance from center (with padding)
        max_dx = widget_width // 2 - self.SQUARE_SIZE // 2 - 5
        max_dy = widget_height // 2 - self.SQUARE_SIZE // 2 - 5
        
        # Map normalized positions to pixel coordinates for blue square
        blue_x_offset = (self.blue_square_x - 0.5) * 2 * max_dx
        blue_y_offset = (self.blue_square_y - 0.5) * 2 * max_dy
        blue_x_pixel = int(cx + blue_x_offset)
        blue_y_pixel = int(cy + blue_y_offset)
        
        # Map normalized positions to pixel coordinates for red square
        red_x_offset = (self.red_square_x - 0.5) * 2 * max_dx
        red_y_offset = (self.red_square_y - 0.5) * 2 * max_dy
        red_x_pixel = int(cx + red_x_offset)
        red_y_pixel = int(cy + red_y_offset)
        
        # Calculate distance from each square center to widget center
        blue_distance_from_center = ((blue_x_pixel - cx)**2 + (blue_y_pixel - cy)**2)**0.5
        red_distance_from_center = ((red_x_pixel - cx)**2 + (red_y_pixel - cy)**2)**0.5
        
        # Check if each square's roll and pitch are within target tolerance
        blue_in_target_zone = (abs(self.blue_roll_deg) <= self.TARGET_TOLERANCE_DEG and 
                              abs(self.blue_pitch_deg) <= self.TARGET_TOLERANCE_DEG)
        red_in_target_zone = (abs(self.red_roll_deg) <= self.TARGET_TOLERANCE_DEG and 
                             abs(self.red_pitch_deg) <= self.TARGET_TOLERANCE_DEG)
        
        # Check if each square is inside the target circle
        blue_square_in_circle = blue_distance_from_center <= self.TARGET_CIRCLE_RADIUS
        red_square_in_circle = red_distance_from_center <= self.TARGET_CIRCLE_RADIUS
        
        # Choose circle color based on which squares are in the target zone and circle:
        # - Both in circle → green
        # - Blue only in circle → blue
        # - Red only in circle → red
        # - Neither in circle → gray
        if blue_in_target_zone and blue_square_in_circle and red_in_target_zone and red_square_in_circle:
            circle_color = QColor("#2ecc71")  # Green - both in circle
        elif blue_in_target_zone and blue_square_in_circle:
            circle_color = QColor("#3498db")  # Blue - first IMU in circle
        elif red_in_target_zone and red_square_in_circle:
            circle_color = QColor("#e74c3c")  # Red - second IMU in circle
        else:
            circle_color = QColor("#95a5a6")  # Gray - neither in circle
        
        # Always draw target circle
        painter.setBrush(circle_color)
        painter.setPen(QPen(QColor("#34495e"), 2))  # Dark border
        painter.drawEllipse(
            cx - self.TARGET_CIRCLE_RADIUS,
            cy - self.TARGET_CIRCLE_RADIUS,
            self.TARGET_CIRCLE_RADIUS * 2,
            self.TARGET_CIRCLE_RADIUS * 2
        )
        
        # Draw blue circle (filled, no border) - IMU 1
        painter.setBrush(QColor("#3498db"))  # Blue color
        painter.setPen(Qt.NoPen)  # No border
        painter.drawEllipse(
            blue_x_pixel - self.SQUARE_SIZE // 2,
            blue_y_pixel - self.SQUARE_SIZE // 2,
            self.SQUARE_SIZE,
            self.SQUARE_SIZE
        )
        
        # Draw red circle (filled, no border) - IMU 2
        painter.setBrush(QColor("#e74c3c"))  # Red color
        painter.setPen(Qt.NoPen)  # No border
        painter.drawEllipse(
            red_x_pixel - self.SQUARE_SIZE // 2,
            red_y_pixel - self.SQUARE_SIZE // 2,
            self.SQUARE_SIZE,
            self.SQUARE_SIZE
        )

