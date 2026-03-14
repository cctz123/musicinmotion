"""Base tab widget with common functionality."""

from PyQt5.QtWidgets import QWidget


class BaseTabWidget(QWidget):
    """Base class for all tab widgets with common functionality."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def cleanup(self):
        """Clean up resources when tab is hidden/switched.
        
        Override in subclasses to release cameras, audio streams, etc.
        """
        pass
    
    def resume(self):
        """Resume activity when tab becomes active.
        
        Override in subclasses to restart cameras, audio streams, etc.
        """
        pass
    
    def set_camera_blackout(self, blackout: bool):
        """Set camera blackout state.
        
        Args:
            blackout: If True, turn off camera. If False, turn on camera.
        """
        pass

