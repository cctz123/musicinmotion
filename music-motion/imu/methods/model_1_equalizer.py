"""Model 1 Equalizer Widget - Displays 7-band EQ visualization."""

import numpy as np
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtCore import Qt
from ...utils.constants import N_BANDS, MAX_GAIN_DB


class Model1EqualizerWidget(QWidget):
    """Widget displaying the 7-band equalizer for Model 1."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(200)  # Fixed height as requested
        self.setMinimumWidth(300)  # Minimum width for EQ bars
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background-color: #f0f0f0;")
        
        # Data (will be updated from Model1Widget)
        self.current_band_gains_db = np.zeros(N_BANDS, dtype=np.float32)
    
    def update_data(self, current_band_gains_db):
        """Update the EQ band gains to display."""
        self.current_band_gains_db = current_band_gains_db.copy()
        self.update()  # Trigger repaint
    
    def paintEvent(self, event):
        """Draw the 7-band EQ bars."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        # Background
        painter.fillRect(0, 0, width, height, QColor(240, 240, 240))
        
        # Draw EQ bars
        bar_width = int((width // (N_BANDS + 2)) * 0.8)  # 20% off instead of 50%
        bar_spacing = bar_width // 2  # Half spacing
        start_x = (width - (N_BANDS * bar_width + (N_BANDS - 1) * bar_spacing)) // 2
        
        bar_height = height - 50  # Reserve 50px for labels
        
        for i in range(N_BANDS):
            x = start_x + i * (bar_width + bar_spacing)
            gain_db = self.current_band_gains_db[i]
            
            # Normalize gain to bar height
            gain_norm = np.clip(gain_db / MAX_GAIN_DB, -1.0, 1.0)
            bar_fill_height = int(abs(gain_norm) * bar_height * 0.5)
            bar_y = int(height - 50 - bar_fill_height if gain_norm > 0 else height - 50)
            
            # Color: green for boost, red for cut
            color = QColor(0, 200, 0) if gain_norm > 0 else QColor(200, 0, 0)
            painter.fillRect(int(x), bar_y, int(bar_width), bar_fill_height, color)
            
            # Draw bar outline
            painter.setPen(QPen(QColor(100, 100, 100), 1))
            bar_outline_y = int(height - 50 - bar_height * 0.5)
            bar_outline_height = int(bar_height * 0.5)
            painter.drawRect(int(x), bar_outline_y, int(bar_width), bar_outline_height)
            
            # Label
            painter.setFont(QFont("Arial", 9))
            painter.setPen(QColor(50, 50, 50))
            label_y = height - 30
            painter.drawText(x, label_y, bar_width, 20, Qt.AlignCenter, f"{gain_db:.1f}dB")

