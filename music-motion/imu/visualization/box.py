"""Box visualization widget (Method A)."""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor


class ImuBoxWidget(QWidget):
    """Widget that displays a box controlled by IMU data."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.box_x = 0.5  # Normalized position (0.0 to 1.0)
        self.box_y = 0.5  # Normalized position (0.0 to 1.0)
        self.box_size = 80
        self.setMinimumSize(600, 400)
        self.setStyleSheet("background-color: #f5f5f5;")
        
    def set_box_position(self, x: float, y: float):
        """Set box position (normalized 0.0 to 1.0)."""
        # Clamp values to valid range
        self.box_x = max(0.0, min(1.0, x))
        self.box_y = max(0.0, min(1.0, y))
        self.update()  # Trigger repaint
        
    def paintEvent(self, event):
        """Paint the box at the current position."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate box position in widget coordinates
        widget_width = self.width()
        widget_height = self.height()
        
        # Center the box in the widget
        box_x_pixel = int(self.box_x * widget_width)
        box_y_pixel = int(self.box_y * widget_height)
        
        # Draw box
        painter.setBrush(QColor("#3498db"))
        painter.setPen(QColor("#2980b9"))
        painter.drawRect(
            box_x_pixel - self.box_size // 2,
            box_y_pixel - self.box_size // 2,
            self.box_size,
            self.box_size
        )

