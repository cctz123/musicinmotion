"""UI utility functions and helpers."""

from PyQt5.QtGui import QColor, QPalette, QFont
from PyQt5.QtCore import Qt


def get_active_pose_style() -> str:
    """Get the active pose card style."""
    return "QFrame { border: 3px solid #27ae60; border-radius: 8px; background-color: #e8f8f5; }"


def get_inactive_pose_style() -> str:
    """Get the inactive pose card style."""
    return "QFrame { border: 2px solid #bdc3c7; border-radius: 8px; background-color: #ffffff; }"


def get_active_pose_palette_color() -> QColor:
    """Get the active pose card background color."""
    return QColor("#e8f8f5")


def create_standard_font(size: int = 12, bold: bool = False) -> QFont:
    """Create a standard font."""
    font = QFont("Arial", size)
    if bold:
        font.setBold(True)
    return font

