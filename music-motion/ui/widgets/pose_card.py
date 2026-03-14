"""Pose card widget for yoga pose display."""

import os
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout
from PyQt5.QtGui import QPixmap, QFont, QColor, QPalette
from PyQt5.QtCore import Qt
from ...utils.ui_utils import get_active_pose_style, get_inactive_pose_style, get_active_pose_palette_color


class PoseCard(QFrame):
    """Simple visual card for a pose with a highlight when active."""

    def __init__(self, pose_key: str, display_name: str, image_path: str | None = None, parent=None):
        super().__init__(parent)
        self.pose_key = pose_key
        self.display_name = display_name
        self.image_path = image_path

        self.setFrameShape(QFrame.StyledPanel)
        self.setLineWidth(2)
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.title_label = QLabel(display_name)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFont(QFont("Arial", 14, QFont.Bold))

        self.image_label = QLabel()
        # Make preview area square to match square pose reference images
        self.image_label.setFixedSize(160, 160)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            "background-color: #ecf0f1; border-radius: 6px; color: #7f8c8d;"
        )

        # Load a preview image if provided, otherwise show placeholder text
        if self.image_path and os.path.exists(self.image_path):
            pix = QPixmap(self.image_path)
            if not pix.isNull():
                self.image_label.setPixmap(
                    pix.scaled(
                        self.image_label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
            else:
                self.image_label.setText("Pose\npreview")
        else:
            self.image_label.setText("Pose\npreview")

        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label)

        self.set_inactive_style()

    def set_active(self, is_active: bool):
        if is_active:
            self.set_active_style()
        else:
            self.set_inactive_style()

    def set_active_style(self):
        """Apply active style with colored border highlight."""
        palette = self.palette()
        palette.setColor(QPalette.Window, get_active_pose_palette_color())
        self.setPalette(palette)
        # Thicker, more visible border with green color
        self.setStyleSheet(get_active_pose_style())
        self.title_label.setStyleSheet("color: #16a085; font-weight: bold;")

    def set_inactive_style(self):
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#ffffff"))
        self.setPalette(palette)
        self.setStyleSheet(get_inactive_pose_style())
        self.title_label.setStyleSheet("color: #2c3e50;")

