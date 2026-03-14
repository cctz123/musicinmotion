"""MP Hands Demo tab - Hands detection demo."""

import cv2
import mediapipe as mp
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor
from PyQt5.QtCore import Qt, QTimer
from .base_tab import BaseTabWidget


class HandsDemoWidget(BaseTabWidget):
    """Hands detection demo integrated into PyQt5 widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cap = None  # Camera not initialized until needed
        self.hands = None
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.mp_styles = mp.solutions.drawing_styles
        self.camera_blackout = True  # Camera off by default
        
        self._init_ui()
        # Only initialize camera if not blacked out
        if not self.camera_blackout:
            self._init_camera()
        self._init_hands_detector()
        self._init_timer()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Hands Demo - MediaPipe Hand Detection")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("color: #2c3e50;")

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(960, 540)
        self.video_label.setStyleSheet(
            "background-color: black; border-radius: 10px;"
        )

        status_label = QLabel("Detecting hands in real-time")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setFont(QFont("Arial", 14))
        status_label.setStyleSheet("color: #7f8c8d; margin-top: 4px;")

        layout.addWidget(title)
        layout.addWidget(self.video_label, 1)
        layout.addWidget(status_label)

    def _init_camera(self):
        """Initialize camera with fallback options."""
        if self.cap is not None and self.cap.isOpened():
            return  # Already initialized
        
        self.cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
        if not self.cap.isOpened():
            print("Camera 0 (AVFOUNDATION) failed. Trying default backend...")
            self.cap = cv2.VideoCapture(0)

        if not self.cap.isOpened():
            print("Still can't open camera 0. Trying camera 1...")
            self.cap = cv2.VideoCapture(1, cv2.CAP_AVFOUNDATION)

        if not self.cap.isOpened():
            error_label = QLabel("❌ Could not open any camera (0/1). Check permissions or camera index.")
            error_label.setStyleSheet("color: #e74c3c; font-size: 16px; padding: 20px;")
            self.video_label.setText("Camera Error")
            self.video_label.setStyleSheet("background-color: #ecf0f1; color: #e74c3c; border-radius: 10px;")

    def _init_hands_detector(self):
        """Initialize MediaPipe hands detector."""
        if self.cap and self.cap.isOpened():
            self.hands = self.mp_hands.Hands(
                model_complexity=0,
                max_num_hands=2,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )

    def _init_timer(self):
        """Start the video update timer."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_frame)
        self.timer.start(30)  # ~30 FPS

    def _update_frame(self):
        """Update video frame with hand detection."""
        if self.camera_blackout:
            black_pixmap = QPixmap(self.video_label.width(), self.video_label.height())
            black_pixmap.fill(QColor(0, 0, 0))
            self.video_label.setPixmap(black_pixmap)
            return

        if not self.cap or not self.cap.isOpened():
            return

        ok, frame = self.cap.read()
        if not ok:
            return

        # Convert BGR to RGB for MediaPipe
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process with MediaPipe
        if self.hands:
            results = self.hands.process(image_rgb)
            
            # Draw hand landmarks
            if results.multi_hand_landmarks:
                for hand_lms in results.multi_hand_landmarks:
                    self.mp_draw.draw_landmarks(
                        frame,
                        hand_lms,
                        self.mp_hands.HAND_CONNECTIONS,
                        self.mp_styles.get_default_hand_landmarks_style(),
                        self.mp_styles.get_default_hand_connections_style(),
                    )

        # Convert back to RGB for display
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        # Scale to fit label while maintaining aspect ratio
        scaled = q_img.scaled(
            self.video_label.width(),
            self.video_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.video_label.setPixmap(QPixmap.fromImage(scaled))

    def set_camera_blackout(self, blackout: bool):
        """Set camera blackout state."""
        self.camera_blackout = blackout
        
        if blackout:
            # Stop camera if it's running
            if self.cap and self.cap.isOpened():
                self.cap.release()
                self.cap = None
        else:
            # Initialize camera if not already initialized
            if self.cap is None or not self.cap.isOpened():
                self._init_camera()

    def cleanup(self):
        """Clean up resources when tab is switched."""
        if hasattr(self, 'timer') and self.timer:
            self.timer.stop()
        if self.hands:
            self.hands.close()
            self.hands = None
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None

    def resume(self):
        """Resume camera and detection when tab is switched back."""
        # Only initialize camera if not blacked out
        if not self.camera_blackout:
            if not self.cap or not self.cap.isOpened():
                self._init_camera()
                self._init_hands_detector()
        if hasattr(self, 'timer') and self.timer:
            self.timer.start(30)

