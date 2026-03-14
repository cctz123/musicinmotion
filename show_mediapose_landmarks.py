#!/usr/bin/env python3
"""Simple PyQt5 app that displays documentation/images/mediapose-landmarks.png."""

import os
import sys

from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt


def find_image():
    """Return path to mediapose-landmarks.png (relative to project root or script)."""
    root = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(root, "documentation", "images", "mediapose-landmarks.png")
    if os.path.isfile(path):
        return path
    if os.path.isfile("documentation/images/mediapose-landmarks.png"):
        return "documentation/images/mediapose-landmarks.png"
    return None


class LandmarksWindow(QMainWindow):
    def __init__(self, image_path: str):
        super().__init__()
        self.setWindowTitle("MediaPipe Pose Landmarks")
        label = QLabel(self)
        label.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            label.setText(f"Could not load image:\n{image_path}")
        else:
            label.setPixmap(pixmap)
        self.setCentralWidget(label)
        self.resize(pixmap.width() if not pixmap.isNull() else 400, pixmap.height() if not pixmap.isNull() else 300)


def main():
    app = QApplication(sys.argv)
    path = find_image()
    if not path:
        print("Image not found: documentation/images/mediapose-landmarks.png", file=sys.stderr)
        sys.exit(1)
    win = LandmarksWindow(path)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
