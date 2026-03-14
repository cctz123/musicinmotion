"""Yoga Pose Detector tab."""

import os
import cv2
import mediapipe as mp
from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame,
    QScrollArea, QPushButton
)
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from .base_tab import BaseTabWidget
from ..widgets.pose_card import PoseCard
from ...ml.yoga import (
    detect_tree_pose, detect_downward_dog, detect_warrior_i, detect_side_angle
)


class YogaPoseDetectorWidget(BaseTabWidget):
    """
    Real-time yoga pose detection widget.

    - Large video area showing live camera feed with pose skeleton overlay.
    - Side panel with pose cards showing available poses.
    - Real-time tree pose detection using MediaPipe.
    - Auto-scrolls to detected pose card when pose is found.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cap = None
        self.current_pose_key = "none"
        self.camera_blackout = True  # Camera off by default
        self.pose = None
        self.scroll_area = None
        self.scroll_animation = None

        # MediaPipe pose solution
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles

        self.pose_display_names = {
            "tree": "Tree Pose",
            "downward_dog": "Downward Dog",
            "warrior_i": "Warrior I",
            "side_angle": "Side Angle",
        }

        # Expected preview image paths (optional)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        poses_dir = os.path.join(base_dir, "..", "..", "..", "pose_images")
        self.pose_image_paths = {
            "tree": os.path.join(poses_dir, "tree.png"),
            "downward_dog": os.path.join(poses_dir, "downward_dog.png"),
            "warrior_i": os.path.join(poses_dir, "warrior_i.png"),
            "side_angle": os.path.join(poses_dir, "side_angle.png"),
        }

        self._init_ui()
        self._init_camera()
        self._init_pose_detector()
        self._init_timer()

    def _init_camera(self):
        """Initialize camera."""
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)

    def _init_pose_detector(self):
        """Initialize MediaPipe pose detector."""
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # Left: video area
        video_container = QFrame()
        video_container.setFrameShape(QFrame.NoFrame)
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(12)

        title = QLabel("Real-time Camera Preview")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("color: #2c3e50;")

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(960, 540)
        self.video_label.setStyleSheet(
            "background-color: black; border-radius: 10px;"
        )

        self.video_status_label = QLabel("No pose detected")
        self.video_status_label.setAlignment(Qt.AlignCenter)
        self.video_status_label.setFont(QFont("Arial", 14))
        self.video_status_label.setStyleSheet("color: #7f8c8d; margin-top: 4px;")

        video_layout.addWidget(title)
        video_layout.addWidget(self.video_label, 1)
        video_layout.addWidget(self.video_status_label)

        # Right: side panel with pose cards + controls
        side_panel = QFrame()
        side_panel.setFrameShape(QFrame.StyledPanel)
        side_panel.setStyleSheet(
            """
            QFrame {
                background-color: #f8f9fa;
                border-radius: 10px;
                border: 1px solid #dee2e6;
            }
            """
        )
        side_panel.setFixedWidth(280)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(16, 16, 16, 16)
        side_layout.setSpacing(16)

        side_title = QLabel("Available Poses")
        side_title.setFont(QFont("Arial", 16, QFont.Bold))
        side_title.setStyleSheet("color: #2c3e50; margin-bottom: 8px;")
        side_layout.addWidget(side_title)

        # Scroll area for pose cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        self.pose_cards_container = QWidget()
        self.pose_cards_layout = QVBoxLayout(self.pose_cards_container)
        self.pose_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.pose_cards_layout.setSpacing(12)
        self.pose_cards_layout.addStretch()

        self.pose_cards = {}
        for pose_key, display_name in self.pose_display_names.items():
            image_path = self.pose_image_paths.get(pose_key)
            card = PoseCard(pose_key, display_name, image_path)
            self.pose_cards[pose_key] = card
            self.pose_cards_layout.insertWidget(
                self.pose_cards_layout.count() - 1, card
            )

        self.scroll_area.setWidget(self.pose_cards_container)
        side_layout.addWidget(self.scroll_area)

        main_layout.addWidget(video_container, 2)
        main_layout.addWidget(side_panel, 0)

    def _init_timer(self):
        """Start the video update timer."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_frame)
        self.timer.start(30)

    def _update_frame(self):
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

        # Convert BGR to RGB for MediaPipe processing
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process frame with MediaPipe pose detector
        detected_pose = "none"
        if self.pose:
            results = self.pose.process(frame_rgb)
            
            # Draw pose skeleton on frame
            if results.pose_landmarks:
                self.mp_drawing.draw_landmarks(
                    frame_rgb,
                    results.pose_landmarks,
                    self.mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=self.mp_drawing_styles.get_default_pose_landmarks_style()
                )
                
                # Detect all poses in order
                landmarks = results.pose_landmarks.landmark
                if detect_tree_pose(landmarks, self.mp_pose):
                    detected_pose = "tree"
                elif detect_downward_dog(landmarks, self.mp_pose):
                    detected_pose = "downward_dog"
                elif detect_warrior_i(landmarks, self.mp_pose):
                    detected_pose = "warrior_i"
                elif detect_side_angle(landmarks, self.mp_pose):
                    detected_pose = "side_angle"
        
        # Update pose state if changed
        if detected_pose != self.current_pose_key:
            self.current_pose_key = detected_pose
            self._refresh_pose_visuals()

        # Convert back to BGR for display
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        h, w, ch = frame_bgr.shape
        bytes_per_line = ch * w
        q_img = QImage(frame_bgr.data, w, h, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
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

    def _smooth_scroll_to_card(self, card):
        """Smoothly scroll to the specified pose card with animation."""
        if not self.scroll_area or not card or not self.pose_cards_container:
            return
        
        if self.scroll_animation:
            self.scroll_animation.stop()
        
        scrollbar = self.scroll_area.verticalScrollBar()
        if not scrollbar:
            return
        
        current_scroll = scrollbar.value()
        card_pos = card.pos()
        card_y = card_pos.y()
        card_height = card.height()
        viewport_height = self.scroll_area.viewport().height()
        
        target_scroll = card_y - (viewport_height - card_height) / 2
        target_scroll = max(0, min(int(target_scroll), scrollbar.maximum()))
        
        if abs(target_scroll - current_scroll) < 5:
            scrollbar.setValue(target_scroll)
            return
        
        self.scroll_animation = QPropertyAnimation(scrollbar, b"value")
        self.scroll_animation.setDuration(500)
        self.scroll_animation.setStartValue(current_scroll)
        self.scroll_animation.setEndValue(target_scroll)
        self.scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.scroll_animation.start()

    def _refresh_pose_visuals(self):
        """Update pose visuals based on current detected pose."""
        if self.current_pose_key == "none":
            self.video_status_label.setText("No pose detected")
            self.video_status_label.setStyleSheet(
                "color: #e67e22; font-weight: 500; margin-top: 4px;"
            )
        else:
            pose_name = self.pose_display_names.get(self.current_pose_key, "Unknown Pose")
            self.video_status_label.setText(f"{pose_name} Detected")
            self.video_status_label.setStyleSheet(
                "color: #27ae60; font-weight: 600; margin-top: 4px;"
            )

        # Update pose cards highlighting
        for key, card in self.pose_cards.items():
            card.set_active(key == self.current_pose_key)
        
        # Smooth scroll to detected pose card
        if self.current_pose_key != "none" and self.current_pose_key in self.pose_cards:
            pose_card = self.pose_cards[self.current_pose_key]
            if self.scroll_area:
                self._smooth_scroll_to_card(pose_card)

    def cleanup(self):
        """Clean up resources when tab is switched."""
        if hasattr(self, 'timer') and self.timer:
            self.timer.stop()
        if self.pose:
            self.pose.close()
            self.pose = None
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None

    def resume(self):
        """Resume camera and pose detector when tab is switched back."""
        # Only initialize camera if not blacked out
        if not self.camera_blackout:
            if not self.cap or not self.cap.isOpened():
                self._init_camera()
        if not self.pose:
            self._init_pose_detector()
        if hasattr(self, 'timer') and self.timer:
            self.timer.start(30)

