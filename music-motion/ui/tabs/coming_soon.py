"""Coming Soon tab widget."""

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt


class ComingSoonWidget(QWidget):
    """Simple 'Coming Soon' placeholder widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        
        label = QLabel("Coming Soon")
        label.setAlignment(Qt.AlignCenter)
        font = label.font()
        font.setPointSize(24)
        font.setBold(True)
        label.setFont(font)
        label.setStyleSheet("color: #7f8c8d;")
        
        layout.addWidget(label)
        self.setLayout(layout)
    
    def cleanup(self):
        """Placeholder cleanup method."""
        pass
    
    def resume(self):
        """Placeholder resume method."""
        pass

