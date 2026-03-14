"""Model 1 Bars Widget - Displays arm heights, volume, and saturation bars."""

import numpy as np
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtCore import Qt


class Model1BarsWidget(QWidget):
    """Widget displaying the 4 horizontal bars for Model 1."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(200)  # Fixed height as requested
        self.setMinimumWidth(500)  # Minimum width for bars
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background-color: #f0f0f0;")
        
        # Data (will be updated from Model1Widget)
        self.left_arm_height_smooth = 0.0
        self.right_arm_height_smooth = 0.0
        self.current_volume = 0.5
        self.current_saturation = 0.0
        
        # Constants
        self.ARM_HEIGHT_MIN = -0.3
        self.ARM_HEIGHT_MAX = 0.5
        self.SATURATION_MAX = 0.8
    
    def update_data(self, left_arm_height_smooth, right_arm_height_smooth, 
                   current_volume, current_saturation):
        """Update the data to display."""
        self.left_arm_height_smooth = left_arm_height_smooth
        self.right_arm_height_smooth = right_arm_height_smooth
        self.current_volume = current_volume
        self.current_saturation = current_saturation
        self.update()  # Trigger repaint
    
    def paintEvent(self, event):
        """Draw the 4 horizontal bars."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        # Background
        painter.fillRect(0, 0, width, height, QColor(240, 240, 240))
        
        # Label area on the left
        label_area_width = 120
        label_padding = 10
        
        # Bar configuration
        bar_start_x = label_area_width + label_padding  # Bars start after label area
        bar_area_y = 20
        bar_width = width - bar_start_x - 20  # Use remaining width minus right padding
        bar_height = 20
        bar_spacing = 35  # Space between bars
        
        # Calculate bar positions
        left_bar_y = bar_area_y
        right_bar_y = left_bar_y + bar_spacing
        volume_bar_y = right_bar_y + bar_spacing
        sat_bar_y = volume_bar_y + bar_spacing
        
        # Draw "Arm Heights:" label - vertically centered between Left and Right bars
        arm_heights_label_y = left_bar_y + (right_bar_y - left_bar_y) / 2 + bar_height / 2
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.setPen(QColor(50, 50, 50))
        painter.drawText(
            label_padding, 
            int(arm_heights_label_y - 10), 
            label_area_width - label_padding, 
            20, 
            Qt.AlignRight | Qt.AlignVCenter, 
            "Arm Heights:"
        )
        
        # Left arm bar
        left_norm = np.clip(
            (self.left_arm_height_smooth - self.ARM_HEIGHT_MIN) /
            (self.ARM_HEIGHT_MAX - self.ARM_HEIGHT_MIN),
            0.0, 1.0
        )
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawRect(bar_start_x, left_bar_y, bar_width, bar_height)
        painter.fillRect(bar_start_x, left_bar_y, int(left_norm * bar_width), bar_height, QColor(100, 150, 255))
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QColor(50, 50, 50))
        painter.drawText(bar_start_x, left_bar_y, bar_width, bar_height, Qt.AlignCenter, f"Left: {left_norm*100:.0f}%")
        
        # Right arm bar
        right_norm = np.clip(
            (self.right_arm_height_smooth - self.ARM_HEIGHT_MIN) /
            (self.ARM_HEIGHT_MAX - self.ARM_HEIGHT_MIN),
            0.0, 1.0
        )
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawRect(bar_start_x, right_bar_y, bar_width, bar_height)
        painter.fillRect(bar_start_x, right_bar_y, int(right_norm * bar_width), bar_height, QColor(255, 150, 100))
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QColor(50, 50, 50))
        painter.drawText(bar_start_x, right_bar_y, bar_width, bar_height, Qt.AlignCenter, f"Right: {right_norm*100:.0f}%")
        
        # Draw "Volume" label - to the left of the volume bar, vertically centered
        painter.setFont(QFont("Arial", 10))
        painter.setPen(QColor(50, 50, 50))
        painter.drawText(
            label_padding,
            volume_bar_y,
            label_area_width - label_padding,
            bar_height,
            Qt.AlignRight | Qt.AlignVCenter,
            "Volume"
        )
        
        # Draw volume bar
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawRect(bar_start_x, volume_bar_y, bar_width, bar_height)
        
        volume_fill_width = int(self.current_volume * bar_width)
        painter.fillRect(bar_start_x, volume_bar_y, volume_fill_width, bar_height, QColor(0, 150, 255))
        
        # Draw "Saturation" label - to the left of the saturation bar, vertically centered
        painter.setFont(QFont("Arial", 10))
        painter.setPen(QColor(50, 50, 50))
        painter.drawText(
            label_padding,
            sat_bar_y,
            label_area_width - label_padding,
            bar_height,
            Qt.AlignRight | Qt.AlignVCenter,
            "Saturation"
        )
        
        # Draw saturation bar
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawRect(bar_start_x, sat_bar_y, bar_width, bar_height)
        
        sat_fill_width = int((self.current_saturation / self.SATURATION_MAX) * bar_width)
        painter.fillRect(bar_start_x, sat_bar_y, sat_fill_width, bar_height, QColor(255, 150, 0))

