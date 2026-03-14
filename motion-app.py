import sys
import os
import cv2
import math
import time
import mediapipe as mp
from pathlib import Path
import numpy as np
import sounddevice as sd
# librosa imported lazily in Proto G: Equalizer to avoid affecting other methods
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QMainWindow,
    QCheckBox,
    QMessageBox,
    QRadioButton,
    QButtonGroup,
    QComboBox,
    QProgressBar,
    QDialog,
    QDialogButtonBox,
    QSizePolicy,
)
from PyQt5.QtGui import QImage, QPixmap, QFont, QFontMetrics, QColor, QPalette, QPainter, QPen, QPolygonF
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint, QPointF
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


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
        palette.setColor(QPalette.Window, QColor("#e8f8f5"))
        self.setPalette(palette)
        # Thicker, more visible border with green color
        self.setStyleSheet(
            "QFrame { border: 3px solid #27ae60; border-radius: 8px; background-color: #e8f8f5; }"
        )
        self.title_label.setStyleSheet("color: #16a085; font-weight: bold;")

    def set_inactive_style(self):
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#ffffff"))
        self.setPalette(palette)
        self.setStyleSheet(
            "QFrame { border: 1px solid #bdc3c7; border-radius: 8px; }"
        )
        self.title_label.setStyleSheet("color: #2c3e50;")


class HandsDemoWidget(QWidget):
    """Hands detection demo integrated into PyQt5 widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cap = None
        self.hands = None
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.mp_styles = mp.solutions.drawing_styles
        self.camera_blackout = False  # Track blackout state
        
        self._init_ui()
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
        # Try AVFoundation (best for macOS). Fall back to default if needed.
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
            # Show black screen
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

    def cleanup(self):
        """Clean up resources when tab is switched."""
        if self.timer:
            self.timer.stop()
        if self.hands:
            self.hands.close()
            self.hands = None
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None

    def resume(self):
        """Resume camera and detection when tab is switched back."""
        if not self.cap or not self.cap.isOpened():
            self._init_camera()
            self._init_hands_detector()
        if self.timer:
            self.timer.start(30)


class YogaPoseDetectorWidget(QWidget):
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
        self.camera_blackout = False  # Track blackout state
        self.pose = None
        self.scroll_area = None  # Reference to scroll area for auto-scrolling
        self.scroll_animation = None  # Animation for smooth scrolling

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

        # Expected preview image paths (optional). Put your PNG/JPG files here.
        base_dir = os.path.dirname(os.path.abspath(__file__))
        poses_dir = os.path.join(base_dir, "pose_images")
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
                border: 1px solid #dfe4ea;
            }
        """
        )
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(16, 16, 16, 16)
        side_layout.setSpacing(16)

        side_title = QLabel("Pose Guide & Status")
        side_title.setFont(QFont("Arial", 16, QFont.Bold))
        side_title.setAlignment(Qt.AlignCenter)
        side_title.setStyleSheet("color: #2c3e50;")

        side_layout.addWidget(side_title)

        # Scrollable area for pose cards
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #ecf0f1;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #bdc3c7;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #95a5a6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Container widget for pose cards
        pose_cards_container = QWidget()
        pose_cards_layout = QVBoxLayout(pose_cards_container)
        pose_cards_layout.setContentsMargins(0, 0, 0, 0)
        pose_cards_layout.setSpacing(12)

        # Pose cards
        self.pose_cards = {}
        for key, name in self.pose_display_names.items():
            card = PoseCard(key, name, self.pose_image_paths.get(key))
            self.pose_cards[key] = card
            pose_cards_layout.addWidget(card)

        # No stretch - let cards fill the full height to show multiple poses
        scroll_area.setWidget(pose_cards_container)
        side_layout.addWidget(scroll_area, 1)  # Give scroll area stretch factor to fill remaining space
        
        # Store reference to scroll area for auto-scrolling
        self.scroll_area = scroll_area
        self.pose_cards_container = pose_cards_container

        # No stretch needed - scroll area already has stretch factor to fill available space

        main_layout.addWidget(video_container, 3)
        main_layout.addWidget(side_panel, 1)

        self._refresh_pose_visuals()

    def _init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_frame)
        self.timer.start(30)

    def _update_frame(self):
        if self.camera_blackout:
            # Show black screen
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
                
                # Detect all poses in order (check tree first, then others)
                landmarks = results.pose_landmarks.landmark
                if self._detect_tree_pose(landmarks):
                    detected_pose = "tree"
                elif self._detect_downward_dog(landmarks):
                    detected_pose = "downward_dog"
                elif self._detect_warrior_i(landmarks):
                    detected_pose = "warrior_i"
                elif self._detect_side_angle(landmarks):
                    detected_pose = "side_angle"
        
        # Update pose state if changed
        if detected_pose != self.current_pose_key:
            self.current_pose_key = detected_pose
            self._refresh_pose_visuals()

        # Convert back to BGR for display (OpenCV format)
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

    def _calculate_angle(self, a, b, c):
        """
        Calculate the angle between three landmark points.
        
        Args:
            a: First point (landmark)
            b: Vertex point (landmark) 
            c: Third point (landmark)
            
        Returns:
            Angle in degrees
        """
        # Calculate vectors from vertex to other points
        vector_ab = [a.x - b.x, a.y - b.y]
        vector_cb = [c.x - b.x, c.y - b.y]
        
        # Calculate dot product
        dot_product = vector_ab[0] * vector_cb[0] + vector_ab[1] * vector_cb[1]
        
        # Calculate magnitudes
        magnitude_ab = math.sqrt(vector_ab[0] ** 2 + vector_ab[1] ** 2)
        magnitude_cb = math.sqrt(vector_cb[0] ** 2 + vector_cb[1] ** 2)
        
        # Calculate cosine of angle
        if magnitude_ab == 0 or magnitude_cb == 0:
            return 0
        
        cos_angle = dot_product / (magnitude_ab * magnitude_cb)
        
        # Clamp to valid range for arccos
        cos_angle = max(-1.0, min(1.0, cos_angle))
        
        # Convert to degrees
        angle = math.degrees(math.acos(cos_angle))
        return angle

    def _detect_tree_pose(self, landmarks):
        """
        Detect if the current pose matches a tree pose.
        
        Tree pose criteria:
        - One foot lifted and placed near the standing leg's inner thigh
        - Standing leg is straight (knee angle > 170 degrees)
        - Body is vertically aligned (shoulders over hips)
        
        Args:
            landmarks: MediaPipe pose landmarks
            
        Returns:
            True if tree pose is detected, False otherwise
        """
        # Extract key body landmarks
        left_ankle = landmarks[self.mp_pose.PoseLandmark.LEFT_ANKLE.value]
        right_ankle = landmarks[self.mp_pose.PoseLandmark.RIGHT_ANKLE.value]
        left_knee = landmarks[self.mp_pose.PoseLandmark.LEFT_KNEE.value]
        right_knee = landmarks[self.mp_pose.PoseLandmark.RIGHT_KNEE.value]
        left_hip = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value]
        right_hip = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value]
        
        # Determine which leg is the standing leg (lower ankle position)
        # In MediaPipe, y increases downward, so higher y = lower position
        if left_ankle.y > right_ankle.y:
            standing_leg = "LEFT"
            lifted_ankle = right_ankle
            standing_knee = left_knee
            standing_hip = left_hip
        else:
            standing_leg = "RIGHT"
            lifted_ankle = left_ankle
            standing_knee = right_knee
            standing_hip = right_hip
        
        # Check 1: Lifted foot horizontal proximity to standing leg knee
        horizontal_distance = abs(lifted_ankle.x - standing_knee.x)
        
        # Check 2: Lifted foot vertical position (should be between hip and knee)
        vertical_position_ok = standing_hip.y < lifted_ankle.y < standing_knee.y
        
        # Check 3: Standing leg straightness (knee angle should be close to 180 degrees)
        if standing_leg == "LEFT":
            knee_angle = self._calculate_angle(left_hip, left_knee, left_ankle)
        else:
            knee_angle = self._calculate_angle(right_hip, right_knee, right_ankle)
        
        # Check 4: Body vertical alignment (shoulders should be over hips)
        left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
        right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
        shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2
        hip_center_x = (left_hip.x + right_hip.x) / 2
        vertical_alignment = abs(shoulder_center_x - hip_center_x)
        
        # All criteria must be met for tree pose
        is_tree_pose = (
            horizontal_distance < 0.1 and
            vertical_position_ok and
            knee_angle > 170 and
            vertical_alignment < 0.05
        )
        
        return is_tree_pose

    def _detect_downward_dog(self, landmarks):
        """
        Detect if the current pose matches a downward dog pose.
        
        Downward dog criteria:
        - Hips are higher than both shoulders and ankles (inverted V shape)
        - Both arms are straight (elbow angles > 160 degrees)
        - Both legs are straight (knee angles > 160 degrees)
        
        Args:
            landmarks: MediaPipe pose landmarks
            
        Returns:
            True if downward dog is detected, False otherwise
        """
        # Extract key body landmarks
        left_wrist = landmarks[self.mp_pose.PoseLandmark.LEFT_WRIST.value]
        right_wrist = landmarks[self.mp_pose.PoseLandmark.RIGHT_WRIST.value]
        left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
        right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
        left_hip = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value]
        right_hip = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value]
        left_knee = landmarks[self.mp_pose.PoseLandmark.LEFT_KNEE.value]
        right_knee = landmarks[self.mp_pose.PoseLandmark.RIGHT_KNEE.value]
        left_ankle = landmarks[self.mp_pose.PoseLandmark.LEFT_ANKLE.value]
        right_ankle = landmarks[self.mp_pose.PoseLandmark.RIGHT_ANKLE.value]
        left_elbow = landmarks[self.mp_pose.PoseLandmark.LEFT_ELBOW.value]
        right_elbow = landmarks[self.mp_pose.PoseLandmark.RIGHT_ELBOW.value]
        
        # Calculate body part centers
        wrist_center_y = (left_wrist.y + right_wrist.y) / 2
        shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2
        hip_center_y = (left_hip.y + right_hip.y) / 2
        ankle_center_y = (left_ankle.y + right_ankle.y) / 2
        
        # Check 1: Hips are higher than shoulders and ankles (inverted V)
        hip_highest = (hip_center_y < shoulder_center_y and hip_center_y < ankle_center_y)
        
        # Check 2: Both arms are straight
        left_arm_angle = self._calculate_angle(left_shoulder, left_elbow, left_wrist)
        right_arm_angle = self._calculate_angle(right_shoulder, right_elbow, right_wrist)
        
        # Check 3: Both legs are straight
        left_leg_angle = self._calculate_angle(left_hip, left_knee, left_ankle)
        right_leg_angle = self._calculate_angle(right_hip, right_knee, right_ankle)
        
        # All criteria must be met
        is_downward_dog = (
            hip_highest and
            left_arm_angle > 160 and
            right_arm_angle > 160 and
            left_leg_angle > 160 and
            right_leg_angle > 160
        )
        
        return is_downward_dog

    def _detect_warrior_i(self, landmarks):
        """
        Detect if the current pose matches a warrior I pose.
        
        Warrior I criteria:
        - Front leg bent at approximately 90 degrees
        - Back leg is straight
        - Front knee is aligned over front ankle
        - Body is upright (shoulders over hips)
        - Arms are raised above shoulders
        
        Args:
            landmarks: MediaPipe pose landmarks
            
        Returns:
            True if warrior I is detected, False otherwise
        """
        # Extract key body landmarks
        left_ankle = landmarks[self.mp_pose.PoseLandmark.LEFT_ANKLE.value]
        right_ankle = landmarks[self.mp_pose.PoseLandmark.RIGHT_ANKLE.value]
        left_knee = landmarks[self.mp_pose.PoseLandmark.LEFT_KNEE.value]
        right_knee = landmarks[self.mp_pose.PoseLandmark.RIGHT_KNEE.value]
        left_hip = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value]
        right_hip = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value]
        left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
        right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
        left_wrist = landmarks[self.mp_pose.PoseLandmark.LEFT_WRIST.value]
        right_wrist = landmarks[self.mp_pose.PoseLandmark.RIGHT_WRIST.value]
        
        # Determine front leg (the one with knee more forward)
        if left_knee.x < right_knee.x:
            front_leg = "LEFT"
            front_knee = left_knee
            front_ankle = left_ankle
            front_hip = left_hip
            back_knee = right_knee
            back_ankle = right_ankle
            back_hip = right_hip
        else:
            front_leg = "RIGHT"
            front_knee = right_knee
            front_ankle = right_ankle
            front_hip = right_hip
            back_knee = left_knee
            back_ankle = left_ankle
            back_hip = left_hip
        
        # Check 1: Front leg bent at approximately 90 degrees
        front_knee_angle = self._calculate_angle(front_hip, front_knee, front_ankle)
        
        # Check 2: Back leg is straight
        back_knee_angle = self._calculate_angle(back_hip, back_knee, back_ankle)
        
        # Check 3: Front knee aligned over front ankle
        knee_ankle_alignment = abs(front_knee.x - front_ankle.x)
        
        # Check 4: Body is upright (shoulders over hips)
        shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2
        hip_center_x = (left_hip.x + right_hip.x) / 2
        vertical_alignment = abs(shoulder_center_x - hip_center_x)
        
        # Check 5: Arms are raised (wrists above shoulders)
        wrists_above_shoulders = (left_wrist.y < left_shoulder.y and
                                 right_wrist.y < right_shoulder.y)
        
        # All criteria must be met
        is_warrior_i = (
            75 < front_knee_angle < 105 and
            back_knee_angle > 170 and
            knee_ankle_alignment < 0.05 and
            vertical_alignment < 0.04 and
            wrists_above_shoulders
        )
        
        return is_warrior_i

    def _detect_side_angle(self, landmarks):
        """
        Detect if the current pose matches a side angle pose.
        
        Side angle criteria:
        - Front leg bent at approximately 90 degrees, knee over ankle
        - Back leg is straight
        - Body is bent sideways (torso angled more than 45 degrees)
        - Lower arm (on front leg side) is down near the ground
        - Body alignment forms a straight line from lower arm through torso to upper arm
        
        Args:
            landmarks: MediaPipe pose landmarks
            
        Returns:
            True if side angle pose is detected, False otherwise
        """
        # Extract key body landmarks
        left_ankle = landmarks[self.mp_pose.PoseLandmark.LEFT_ANKLE.value]
        right_ankle = landmarks[self.mp_pose.PoseLandmark.RIGHT_ANKLE.value]
        left_knee = landmarks[self.mp_pose.PoseLandmark.LEFT_KNEE.value]
        right_knee = landmarks[self.mp_pose.PoseLandmark.RIGHT_KNEE.value]
        left_hip = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value]
        right_hip = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value]
        left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
        right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
        left_wrist = landmarks[self.mp_pose.PoseLandmark.LEFT_WRIST.value]
        right_wrist = landmarks[self.mp_pose.PoseLandmark.RIGHT_WRIST.value]
        
        # Determine front leg by checking which knee is bent
        left_knee_angle = self._calculate_angle(left_hip, left_knee, left_ankle)
        right_knee_angle = self._calculate_angle(right_hip, right_knee, right_ankle)
        
        is_left_bent = 75 < left_knee_angle < 105
        is_right_bent = 75 < right_knee_angle < 105
        
        # Determine front leg (the bent one, or by position if both/none are bent)
        if is_left_bent and not is_right_bent:
            front_leg = "LEFT"
        elif is_right_bent and not is_left_bent:
            front_leg = "RIGHT"
        else:
            # Use position if both or neither are clearly bent
            if left_knee.x < right_knee.x:
                front_leg = "LEFT"
            else:
                front_leg = "RIGHT"
        
        # Set up landmarks based on front leg
        if front_leg == "LEFT":
            front_knee = left_knee
            front_ankle = left_ankle
            front_hip = left_hip
            back_knee = right_knee
            back_ankle = right_ankle
            back_hip = right_hip
            lower_arm_wrist = left_wrist
            upper_arm_wrist = right_wrist
        else:
            front_knee = right_knee
            front_ankle = right_ankle
            front_hip = right_hip
            back_knee = left_knee
            back_ankle = left_ankle
            back_hip = left_hip
            lower_arm_wrist = right_wrist
            upper_arm_wrist = left_wrist
        
        # Check 1: Front leg bent at approximately 90 degrees
        front_knee_angle = self._calculate_angle(front_hip, front_knee, front_ankle)
        front_leg_bent = 75 < front_knee_angle < 105
        
        # Check 2: Front knee aligned over front ankle
        knee_ankle_alignment = abs(front_knee.x - front_ankle.x)
        knee_aligned = knee_ankle_alignment < 0.05
        
        # Check 3: Back leg is straight
        back_knee_angle = self._calculate_angle(back_hip, back_knee, back_ankle)
        back_leg_straight = back_knee_angle > 170
        
        # Check 4: Body is bent sideways (torso angled)
        hip_center = ((left_hip.x + right_hip.x) / 2, (left_hip.y + right_hip.y) / 2)
        shoulder_center = ((left_shoulder.x + right_shoulder.x) / 2,
                          (left_shoulder.y + right_shoulder.y) / 2)
        
        # Calculate body angle from vertical
        dx = shoulder_center[0] - hip_center[0]
        dy = shoulder_center[1] - hip_center[1]
        body_angle = math.degrees(math.atan2(dx, dy)) - 90
        body_bent = abs(body_angle) > 45
        
        # Check 5: Lower arm is down (wrist below knee)
        lower_arm_down = lower_arm_wrist.y > front_knee.y
        
        # Check 6: Body alignment (lower arm, hip, upper arm form a line)
        alignment_angle = self._calculate_angle(
            lower_arm_wrist,
            front_hip,
            upper_arm_wrist
        )
        body_alignment = 160 < alignment_angle < 200
        
        # All criteria must be met
        is_side_angle = (
            front_leg_bent and
            knee_aligned and
            back_leg_straight and
            body_bent and
            lower_arm_down and
            body_alignment
        )
        
        return is_side_angle

    def _smooth_scroll_to_card(self, card):
        """
        Smoothly scroll to the specified pose card with animation.
        
        Args:
            card: The PoseCard widget to scroll to
        """
        if not self.scroll_area or not card or not self.pose_cards_container:
            return
        
        # Stop any existing animation
        if self.scroll_animation:
            self.scroll_animation.stop()
        
        # Get the scrollbar
        scrollbar = self.scroll_area.verticalScrollBar()
        if not scrollbar:
            return
        
        # Get current scroll position
        current_scroll = scrollbar.value()
        
        # Calculate card position relative to container
        card_pos = card.pos()
        card_y = card_pos.y()
        card_height = card.height()
        
        # Get viewport dimensions
        viewport_height = self.scroll_area.viewport().height()
        
        # Calculate target scroll to center the card in viewport
        target_scroll = card_y - (viewport_height - card_height) / 2
        
        # Clamp to valid scroll range
        target_scroll = max(0, min(int(target_scroll), scrollbar.maximum()))
        
        # Only animate if there's a meaningful difference
        if abs(target_scroll - current_scroll) < 5:
            scrollbar.setValue(target_scroll)
            return
        
        # Create smooth animation
        self.scroll_animation = QPropertyAnimation(scrollbar, b"value")
        self.scroll_animation.setDuration(500)  # 500ms animation - smooth but not too slow
        self.scroll_animation.setStartValue(current_scroll)
        self.scroll_animation.setEndValue(target_scroll)
        self.scroll_animation.setEasingCurve(QEasingCurve.OutCubic)  # Smooth easing curve
        self.scroll_animation.start()

    def _refresh_pose_visuals(self):
        # Update status text over the video
        if self.current_pose_key == "none":
            self.video_status_label.setText("No pose detected")
            self.video_status_label.setStyleSheet(
                "color: #e67e22; font-weight: 500; margin-top: 4px;"
            )
        else:
            # Show detected pose name dynamically
            pose_name = self.pose_display_names.get(self.current_pose_key, "Unknown Pose")
            self.video_status_label.setText(f"{pose_name} Detected")
            self.video_status_label.setStyleSheet(
                "color: #27ae60; font-weight: 600; margin-top: 4px;"
            )

        # Update pose cards highlighting
        for key, card in self.pose_cards.items():
            card.set_active(key == self.current_pose_key)
        
        # Smooth scroll to detected pose card with animation
        if self.current_pose_key != "none" and self.current_pose_key in self.pose_cards:
            pose_card = self.pose_cards[self.current_pose_key]
            if self.scroll_area:
                self._smooth_scroll_to_card(pose_card)

    def cleanup(self):
        """Clean up resources when tab is switched."""
        if hasattr(self, 'timer'):
            self.timer.stop()
        if self.pose:
            self.pose.close()
            self.pose = None
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None

    def resume(self):
        """Resume camera and pose detector when tab is switched back."""
        if not self.cap or not self.cap.isOpened():
            self._init_camera()
        if not self.pose:
            self._init_pose_detector()
        if hasattr(self, 'timer'):
            self.timer.start(30)


class ImuStatsWidget(QWidget):
    """Widget displaying IMU statistics using matplotlib (matching imu_viewer style)."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(250)
        self.setMaximumWidth(350)
        
        # Setup matplotlib figure
        self.fig = Figure(figsize=(3.5, 6))
        self.canvas = FigureCanvas(self.fig)
        self.fig.patch.set_facecolor('white')
        
        # Create single axis for stats display
        self.ax_overview = self.fig.add_subplot(111)
        self.ax_overview.axis('off')
        self.ax_overview.set_title('Overview', fontweight='bold', fontsize=11, pad=10)
        
        # Initial waiting message
        self._update_overview_waiting()
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        
        # Draw initial state
        self.canvas.draw()
    
    def _update_overview_waiting(self):
        """Update overview with waiting message."""
        self.ax_overview.clear()
        self.ax_overview.axis('off')
        self.ax_overview.set_title('Overview', fontweight='bold', fontsize=11, pad=10)
        
        text_str = "Waiting for data from device..."
        self.ax_overview.text(0.05, 0.95, text_str, transform=self.ax_overview.transAxes,
                             fontsize=10, verticalalignment='top', fontfamily='monospace',
                             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        self.canvas.draw()
    
    def update_stats(self, sample):
        """Update stats display with IMU sample data."""
        from imu_viewer.models import ImuSample
        if sample and isinstance(sample, ImuSample):
            self._update_overview(sample)
        else:
            self._update_overview_waiting()
    
    def _update_overview(self, sample):
        """Update overview table (same code as imu_viewer)."""
        self.ax_overview.clear()
        self.ax_overview.axis('off')
        self.ax_overview.set_title('Overview', fontweight='bold', fontsize=11, pad=10)
        
        text_str = (
            f"Device ID: {sample.device_id}\n\n"
            f"Angles (deg):\n"
            f"  Roll:  {sample.angles_deg[0]:7.2f}\n"
            f"  Pitch: {sample.angles_deg[1]:7.2f}\n"
            f"  Yaw:   {sample.angles_deg[2]:7.2f}\n\n"
            f"Accelerometer (g):\n"
            f"  X: {sample.accel_g[0]:7.3f}\n"
            f"  Y: {sample.accel_g[1]:7.3f}\n"
            f"  Z: {sample.accel_g[2]:7.3f}\n\n"
            f"Gyroscope (deg/s):\n"
            f"  X: {sample.gyro_dps[0]:7.2f}\n"
            f"  Y: {sample.gyro_dps[1]:7.2f}\n"
            f"  Z: {sample.gyro_dps[2]:7.2f}\n\n"
            f"Temperature: {sample.temp_C:6.2f} °C\n"
            f"Battery:     {sample.battery_V:6.1f}%\n"
            f"RSSI:        {sample.rssi_dBm:6.1f} dBm"
        )
        self.ax_overview.text(0.05, 0.95, text_str, transform=self.ax_overview.transAxes,
                             fontsize=10, verticalalignment='top', fontfamily='monospace',
                             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        self.canvas.draw()


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


class ImuSquareWidget(QWidget):
    """Widget that displays a blue square controlled by IMU tilt (Prototype B).
    
    This replicates the functionality from imu_tkinter.py:
    - White background canvas
    - Blue square that moves based on roll/pitch angles
    - Uses ±5.0 degrees as maximum tilt range
    - Roll controls left/right movement
    - Pitch controls up/down movement (inverted)
    - Game mode: Target circle appears when roll/pitch are within ±1°, turns green when square is inside
    """
    
    # Configuration matching imu_tkinter.py
    MAX_TILT_DEG = 5.0  # Maximum tilt in degrees for full deflection
    SQUARE_SIZE = 40  # Square size in pixels (equivalent to DOT_RADIUS * 2)
    TARGET_TOLERANCE_DEG = 0.3  # Target zone: ±0.3 degree (circle turns green)
    TARGET_CIRCLE_RADIUS = 30  # Radius of target circle in pixels
    
    def get_angles(self):
        """Get current angles from square position (for audio). Override in subclasses."""
        return None, None  # roll, pitch
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.square_x = 0.5  # Normalized position (0.0 to 1.0) - center
        self.square_y = 0.5  # Normalized position (0.0 to 1.0) - center
        self.current_roll_deg = 0.0  # Current roll angle for target detection
        self.current_pitch_deg = 0.0  # Current pitch angle for target detection
        self.setMinimumSize(400, 400)
        self.setStyleSheet("background-color: white;")
        
    def set_square_position(self, x: float, y: float):
        """Set square position (normalized 0.0 to 1.0)."""
        # Clamp values to valid range
        self.square_x = max(0.0, min(1.0, x))
        self.square_y = max(0.0, min(1.0, y))
        self.update()  # Trigger repaint
    
    def set_angles(self, roll_deg: float, pitch_deg: float):
        """Set current angles for target detection."""
        self.current_roll_deg = roll_deg
        self.current_pitch_deg = pitch_deg
        self.update()  # Trigger repaint to update target circle
        
    def map_tilt_to_position(self, roll_deg: float, pitch_deg: float) -> tuple:
        """
        Map roll/pitch in degrees to normalized position (0.0 to 1.0).
        
        This matches the logic from imu_tkinter.py's _map_tilt_to_canvas():
        - Clamp roll and pitch to ±MAX_TILT_DEG
        - Normalize to [-1, 1]
        - Map to position with roll controlling X (left/right)
        - Pitch controlling Y (up/down, inverted)
        
        Args:
            roll_deg: Roll angle in degrees (X-axis tilt, left/right)
            pitch_deg: Pitch angle in degrees (Y-axis tilt, forward/back)
            
        Returns:
            Tuple of (x, y) normalized positions (0.0 to 1.0)
        """
        # Clamp to maximum tilt range
        roll = max(-self.MAX_TILT_DEG, min(self.MAX_TILT_DEG, roll_deg))
        pitch = max(-self.MAX_TILT_DEG, min(self.MAX_TILT_DEG, pitch_deg))
        
        # Normalize to [-1, 1]
        roll_norm = roll / self.MAX_TILT_DEG
        pitch_norm = pitch / self.MAX_TILT_DEG
        
        # Map to normalized position [0.0, 1.0]
        # Roll: positive (tilt right) → move right (increase x)
        x = 0.5 + roll_norm * 0.5
        
        # Pitch: positive (tilt forward) → move up (decrease y, inverted)
        # This matches imu_tkinter.py: "Pitch up (positive) moves dot UP, so subtract"
        y = 0.5 - pitch_norm * 0.5
        
        return x, y
        
    def paintEvent(self, event):
        """Paint the blue square at the current position and target circle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate square position in widget coordinates
        widget_width = self.width()
        widget_height = self.height()
        
        # Center of the widget
        cx = widget_width // 2
        cy = widget_height // 2
        
        # Calculate maximum distance from center (with padding)
        max_dx = widget_width // 2 - self.SQUARE_SIZE // 2 - 5
        max_dy = widget_height // 2 - self.SQUARE_SIZE // 2 - 5
        
        # Map normalized position to pixel coordinates
        # square_x and square_y are in [0.0, 1.0], map to [-max_dx, +max_dx] relative to center
        x_offset = (self.square_x - 0.5) * 2 * max_dx
        y_offset = (self.square_y - 0.5) * 2 * max_dy
        
        square_x_pixel = int(cx + x_offset)
        square_y_pixel = int(cy + y_offset)
        
        # Calculate distance from square center to widget center
        square_center_x = square_x_pixel
        square_center_y = square_y_pixel
        distance_from_center = ((square_center_x - cx)**2 + (square_center_y - cy)**2)**0.5
        
        # Check if roll and pitch are within target tolerance (±0.5 degree)
        in_target_zone = (abs(self.current_roll_deg) <= self.TARGET_TOLERANCE_DEG and 
                         abs(self.current_pitch_deg) <= self.TARGET_TOLERANCE_DEG)
        
        # Check if square is inside the target circle
        square_in_circle = distance_from_center <= self.TARGET_CIRCLE_RADIUS
        
        # Choose circle color: green if in target zone AND square is inside, gray otherwise
        if in_target_zone and square_in_circle:
            circle_color = QColor("#2ecc71")  # Green
        else:
            circle_color = QColor("#95a5a6")  # Gray
        
        # Always draw target circle
        painter.setBrush(circle_color)
        painter.setPen(QPen(QColor("#34495e"), 2))  # Dark border
        painter.drawEllipse(
            cx - self.TARGET_CIRCLE_RADIUS,
            cy - self.TARGET_CIRCLE_RADIUS,
            self.TARGET_CIRCLE_RADIUS * 2,
            self.TARGET_CIRCLE_RADIUS * 2
        )
        
        # Draw blue circle (filled, no border) - same size as square (40px diameter)
        painter.setBrush(QColor("#3498db"))  # Blue color
        painter.setPen(Qt.NoPen)  # No border
        painter.drawEllipse(
            square_x_pixel - self.SQUARE_SIZE // 2,
            square_y_pixel - self.SQUARE_SIZE // 2,
            self.SQUARE_SIZE,
            self.SQUARE_SIZE
        )


class ImuDualSquareWidget(QWidget):
    """Widget that displays two squares (blue and red) controlled by two IMUs (Proto E: Dualing IMUs).
    
    This extends Prototype B functionality to support dual IMU input:
    - Blue square controlled by first IMU (port from config)
    - Red square controlled by second IMU (port2 from config)
    - Uses same tilt mapping as Prototype B (±5.0 degrees)
    - Game mode: Target circle appears when roll/pitch are within ±0.3°, turns green when blue square is inside
    """
    
    # Configuration matching ImuSquareWidget
    MAX_TILT_DEG = 5.0  # Maximum tilt in degrees for full deflection
    SQUARE_SIZE = 40  # Square size in pixels
    TARGET_TOLERANCE_DEG = 0.3  # Target zone: ±0.3 degree (circle turns green)
    TARGET_CIRCLE_RADIUS = 30  # Radius of target circle in pixels
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Blue square (IMU 1) position
        self.blue_square_x = 0.5  # Normalized position (0.0 to 1.0) - center
        self.blue_square_y = 0.5  # Normalized position (0.0 to 1.0) - center
        self.blue_roll_deg = 0.0  # Current roll angle for target detection
        self.blue_pitch_deg = 0.0  # Current pitch angle for target detection
        
        # Red square (IMU 2) position
        self.red_square_x = 0.5  # Normalized position (0.0 to 1.0) - center
        self.red_square_y = 0.5  # Normalized position (0.0 to 1.0) - center
        
        self.setMinimumSize(400, 400)
        self.setStyleSheet("background-color: white;")
        
    def set_blue_square_position(self, x: float, y: float):
        """Set blue square position (normalized 0.0 to 1.0)."""
        self.blue_square_x = max(0.0, min(1.0, x))
        self.blue_square_y = max(0.0, min(1.0, y))
        self.update()  # Trigger repaint
    
    def set_red_square_position(self, x: float, y: float):
        """Set red square position (normalized 0.0 to 1.0)."""
        self.red_square_x = max(0.0, min(1.0, x))
        self.red_square_y = max(0.0, min(1.0, y))
        self.update()  # Trigger repaint
    
    def set_blue_angles(self, roll_deg: float, pitch_deg: float):
        """Set current angles for blue square (IMU 1) target detection."""
        self.blue_roll_deg = roll_deg
        self.blue_pitch_deg = pitch_deg
        self.update()  # Trigger repaint to update target circle
        
    def map_tilt_to_position(self, roll_deg: float, pitch_deg: float) -> tuple:
        """
        Map roll/pitch in degrees to normalized position (0.0 to 1.0).
        
        Same logic as ImuSquareWidget.
        """
        # Clamp to maximum tilt range
        roll = max(-self.MAX_TILT_DEG, min(self.MAX_TILT_DEG, roll_deg))
        pitch = max(-self.MAX_TILT_DEG, min(self.MAX_TILT_DEG, pitch_deg))
        
        # Normalize to [-1, 1]
        roll_norm = roll / self.MAX_TILT_DEG
        pitch_norm = pitch / self.MAX_TILT_DEG
        
        # Map to normalized position [0.0, 1.0]
        x = 0.5 + roll_norm * 0.5
        y = 0.5 - pitch_norm * 0.5
        
        return x, y
        
    def paintEvent(self, event):
        """Paint both blue and red squares at their positions and target circle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate positions in widget coordinates
        widget_width = self.width()
        widget_height = self.height()
        
        # Center of the widget
        cx = widget_width // 2
        cy = widget_height // 2
        
        # Calculate maximum distance from center (with padding)
        max_dx = widget_width // 2 - self.SQUARE_SIZE // 2 - 5
        max_dy = widget_height // 2 - self.SQUARE_SIZE // 2 - 5
        
        # Map normalized positions to pixel coordinates for blue square
        blue_x_offset = (self.blue_square_x - 0.5) * 2 * max_dx
        blue_y_offset = (self.blue_square_y - 0.5) * 2 * max_dy
        blue_x_pixel = int(cx + blue_x_offset)
        blue_y_pixel = int(cy + blue_y_offset)
        
        # Map normalized positions to pixel coordinates for red square
        red_x_offset = (self.red_square_x - 0.5) * 2 * max_dx
        red_y_offset = (self.red_square_y - 0.5) * 2 * max_dy
        red_x_pixel = int(cx + red_x_offset)
        red_y_pixel = int(cy + red_y_offset)
        
        # Calculate distance from blue square center to widget center
        blue_distance_from_center = ((blue_x_pixel - cx)**2 + (blue_y_pixel - cy)**2)**0.5
        
        # Check if blue square's roll and pitch are within target tolerance
        in_target_zone = (abs(self.blue_roll_deg) <= self.TARGET_TOLERANCE_DEG and 
                         abs(self.blue_pitch_deg) <= self.TARGET_TOLERANCE_DEG)
        
        # Check if blue square is inside the target circle
        blue_square_in_circle = blue_distance_from_center <= self.TARGET_CIRCLE_RADIUS
        
        # Choose circle color: green if in target zone AND blue square is inside, gray otherwise
        if in_target_zone and blue_square_in_circle:
            circle_color = QColor("#2ecc71")  # Green
        else:
            circle_color = QColor("#95a5a6")  # Gray
        
        # Always draw target circle
        painter.setBrush(circle_color)
        painter.setPen(QPen(QColor("#34495e"), 2))  # Dark border
        painter.drawEllipse(
            cx - self.TARGET_CIRCLE_RADIUS,
            cy - self.TARGET_CIRCLE_RADIUS,
            self.TARGET_CIRCLE_RADIUS * 2,
            self.TARGET_CIRCLE_RADIUS * 2
        )
        
        # Draw blue circle (filled, no border) - IMU 1
        painter.setBrush(QColor("#3498db"))  # Blue color
        painter.setPen(Qt.NoPen)  # No border
        painter.drawEllipse(
            blue_x_pixel - self.SQUARE_SIZE // 2,
            blue_y_pixel - self.SQUARE_SIZE // 2,
            self.SQUARE_SIZE,
            self.SQUARE_SIZE
        )
        
        # Draw red circle (filled, no border) - IMU 2
        painter.setBrush(QColor("#e74c3c"))  # Red color
        painter.setPen(Qt.NoPen)  # No border
        painter.drawEllipse(
            red_x_pixel - self.SQUARE_SIZE // 2,
            red_y_pixel - self.SQUARE_SIZE // 2,
            self.SQUARE_SIZE,
            self.SQUARE_SIZE
        )


class ImuSquareSoundWidget(ImuSquareWidget):
    """Widget that displays a blue square with audio (Proto C: Pitch + Pan).
    
    Extends ImuSquareWidget to add audio generation:
    - Visual: Same as Prototype B (blue square) plus pitch (freq) dial and pan (L/C/R) indicator
    - Audio: Pitch controls frequency, roll controls stereo panning
    - Uses same tilt mapping as Prototype B for visual
    - Uses extended roll range for audio panning (MAX_ROLL_PAN_DEG = 28.0°)
    """
    
    # Audio configuration (matching imu_tkintersound.py)
    AUDIO_SAMPLE_RATE = 44100
    AUDIO_BLOCK_SIZE = 256
    BASE_FREQ = 220.0   # A3-ish
    MAX_FREQ = 880.0    # A5-ish
    MAX_ROLL_PAN_DEG = 28.0  # Full panning at ±28° roll (more dramatic, easier to hit full L/R)
    AUDIO_AMP = 0.15
    
    # Height reserved at bottom for pitch (freq) dial and pan indicator (dial + pan in one row)
    INDICATOR_HEIGHT = 170
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_stream = None
        self.current_roll = 0.0
        self.current_pitch = 0.0
        self.audio_phase = 0.0
        
    def start_audio(self):
        """Start the audio stream."""
        if self.audio_stream is not None:
            return  # Already started
        
        def audio_callback(outdata, frames, time_info, status):
            try:
                if status:
                    print("Audio status:", status)
                
                # Use current angles (updated by set_angles_for_audio)
                roll_deg = self.current_roll
                pitch_deg = self.current_pitch
                
                # --- Pitch mapping: pitch_deg -> freq in [BASE_FREQ, MAX_FREQ] ---
                pitch_clamped = max(-self.MAX_TILT_DEG, min(self.MAX_TILT_DEG, pitch_deg))
                # Map [-MAX_TILT_DEG, +MAX_TILT_DEG] -> [0, 1]
                norm = (pitch_clamped + self.MAX_TILT_DEG) / (2 * self.MAX_TILT_DEG)
                freq = self.BASE_FREQ + (self.MAX_FREQ - self.BASE_FREQ) * norm
                
                # --- Pan mapping: roll -> pan in [-1, 1] ---
                roll_clamped = max(-self.MAX_ROLL_PAN_DEG, min(self.MAX_ROLL_PAN_DEG, roll_deg))
                pan = roll_clamped / self.MAX_ROLL_PAN_DEG  # -1 = full left, +1 = full right
                
                # --- Oscillator ---
                phase = self.audio_phase
                t = np.arange(frames, dtype=np.float32)
                
                phase_increment = 2.0 * np.pi * freq / self.AUDIO_SAMPLE_RATE
                phases = phase + phase_increment * t
                
                # Keep phase from growing without bound
                self.audio_phase = float((phases[-1] + phase_increment) % (2.0 * np.pi))
                
                mono = np.sin(phases).astype(np.float32)
                
                # Overall amplitude
                mono *= self.AUDIO_AMP
                
                # --- Equal-power stereo panning ---
                left_gain = np.sqrt((1.0 - pan) / 2.0)
                right_gain = np.sqrt((1.0 + pan) / 2.0)
                
                outdata[:, 0] = mono * left_gain   # left channel
                outdata[:, 1] = mono * right_gain  # right channel
            except Exception as e:
                print(f"Error in Proto C: Pitch + Pan audio callback: {e}")
                import traceback
                traceback.print_exc()
                outdata.fill(0)
        
        try:
            self.audio_stream = sd.OutputStream(
                samplerate=self.AUDIO_SAMPLE_RATE,
                channels=2,
                blocksize=self.AUDIO_BLOCK_SIZE,
                callback=audio_callback,
            )
            self.audio_stream.start()
            print(f"Audio stream started successfully")
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            import traceback
            traceback.print_exc()
            self.audio_stream = None
    
    def stop_audio(self):
        """Stop the audio stream."""
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        self.audio_phase = 0.0
    
    def set_angles_for_audio(self, roll_deg: float, pitch_deg: float):
        """Update angles for audio generation (separate from visual position)."""
        self.current_roll = roll_deg
        self.current_pitch = pitch_deg
        self.update()  # Refresh pitch/pan visuals

    def paintEvent(self, event):
        """Paint blue square in top area; pitch (freq) dial and pan (L/C/R) in bottom area."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        widget_width = self.width()
        widget_height = self.height()
        square_area_height = widget_height - self.INDICATOR_HEIGHT
        if square_area_height < 50:
            square_area_height = 50
        cx = widget_width // 2
        cy = square_area_height // 2
        max_dx = widget_width // 2 - self.SQUARE_SIZE // 2 - 5
        max_dy = square_area_height // 2 - self.SQUARE_SIZE // 2 - 5
        x_offset = (self.square_x - 0.5) * 2 * max_dx
        y_offset = (self.square_y - 0.5) * 2 * max_dy
        square_x_pixel = int(cx + x_offset)
        square_y_pixel = int(cy + y_offset)
        distance_from_center = ((square_x_pixel - cx)**2 + (square_y_pixel - cy)**2)**0.5
        in_target_zone = (abs(self.current_roll_deg) <= self.TARGET_TOLERANCE_DEG and
                         abs(self.current_pitch_deg) <= self.TARGET_TOLERANCE_DEG)
        square_in_circle = distance_from_center <= self.TARGET_CIRCLE_RADIUS
        circle_color = QColor("#2ecc71") if (in_target_zone and square_in_circle) else QColor("#95a5a6")
        painter.setBrush(circle_color)
        painter.setPen(QPen(QColor("#34495e"), 2))
        painter.drawEllipse(
            cx - self.TARGET_CIRCLE_RADIUS, cy - self.TARGET_CIRCLE_RADIUS,
            self.TARGET_CIRCLE_RADIUS * 2, self.TARGET_CIRCLE_RADIUS * 2
        )
        painter.setBrush(QColor("#3498db"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            square_x_pixel - self.SQUARE_SIZE // 2, square_y_pixel - self.SQUARE_SIZE // 2,
            self.SQUARE_SIZE, self.SQUARE_SIZE
        )
        # Bottom area: pitch (freq) dial and pan (left-mid-right)
        self._draw_pitch_pan_indicators(painter, widget_width, widget_height)

    def _draw_pitch_pan_indicators(self, painter, widget_width, widget_height):
        """Draw analog-style frequency dial (needle + arc) and left-mid-right pan indicator."""
        bar_area_y = widget_height - self.INDICATOR_HEIGHT
        margin = 12
        # --- Pitch -> frequency (same mapping as audio) ---
        pitch_clamped = max(-self.MAX_TILT_DEG, min(self.MAX_TILT_DEG, self.current_pitch))
        norm = (pitch_clamped + self.MAX_TILT_DEG) / (2 * self.MAX_TILT_DEG)
        freq = self.BASE_FREQ + (self.MAX_FREQ - self.BASE_FREQ) * norm
        # Analog dial: semi-circle arc (Geiger / dB style), needle, tick marks
        dial_size = 144
        dial_cx = margin + dial_size // 2 + 8
        dial_cy = bar_area_y + margin + dial_size // 2 + 4
        dial_rect = QRect(dial_cx - dial_size // 2, dial_cy - dial_size // 2, dial_size, dial_size)
        # Arc: bottom semi-circle (Qt: 0° = 3 o'clock, angles in 1/16 degree)
        # start 180*16 = 9 o'clock, span 180*16 = to 3 o'clock along bottom
        painter.setPen(QPen(QColor("#34495e"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(dial_rect, 180 * 16, 180 * 16)
        # Tick marks at 220, 440, 660, 880 Hz (norm 0, 1/3, 2/3, 1)
        r_outer = dial_size // 2 - 2
        r_tick = r_outer - 6
        painter.setPen(QPen(QColor("#333333"), 1))
        painter.setFont(QFont("Arial", 8))
        for i, (f, label) in enumerate([(220, "220"), (440, "440"), (660, "660"), (880, "880")]):
            t = (f - self.BASE_FREQ) / (self.MAX_FREQ - self.BASE_FREQ)
            angle_deg = 180 - t * 180
            rad = math.radians(angle_deg)
            x_outer = dial_cx + r_outer * math.cos(rad)
            y_outer = dial_cy - r_outer * math.sin(rad)
            x_inner = dial_cx + r_tick * math.cos(rad)
            y_inner = dial_cy - r_tick * math.sin(rad)
            painter.drawLine(int(x_inner), int(y_inner), int(x_outer), int(y_outer))
            # Label below the arc
            lx = dial_cx + (r_outer + 10) * math.cos(rad) - 10
            ly = dial_cy - (r_outer + 10) * math.sin(rad) + 4
            painter.drawText(int(lx), int(ly), label)
        # Needle: from center to edge, angle = 180 - norm*180 (220 Hz = left, 880 Hz = right)
        needle_angle_deg = 180 - norm * 180
        needle_rad = math.radians(needle_angle_deg)
        needle_len = r_outer - 8
        needle_tip_x = dial_cx + needle_len * math.cos(needle_rad)
        needle_tip_y = dial_cy - needle_len * math.sin(needle_rad)
        painter.setPen(QPen(QColor("#c0392b"), 2))
        painter.setBrush(QColor("#c0392b"))
        painter.drawLine(int(dial_cx), int(dial_cy), int(needle_tip_x), int(needle_tip_y))
        painter.setBrush(QColor("#2c3e50"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(dial_cx - 4), int(dial_cy - 4), 8, 8)
        # Title and current value (to the right of dial)
        painter.setPen(QColor("#333333"))
        painter.setFont(QFont("Arial", 11))
        pitch_label_x = dial_cx + dial_size // 2 + 8
        painter.drawText(pitch_label_x, dial_cy - 6, "Pitch")
        painter.drawText(pitch_label_x, dial_cy + 10, f"{int(round(freq))} Hz")
        # --- Pan: left-mid-right, to the right of the dial (same row) ---
        roll_clamped = max(-self.MAX_ROLL_PAN_DEG, min(self.MAX_ROLL_PAN_DEG, self.current_roll))
        pan = roll_clamped / self.MAX_ROLL_PAN_DEG
        pan_area_x = pitch_label_x + 58
        painter.drawText(pan_area_x, dial_cy + 4, "Pan")
        track_x = pan_area_x + 28
        full_track_width = widget_width - track_x - margin - 30
        track_width = int(full_track_width * 0.7)
        track_x_start = track_x + (full_track_width - track_width) // 2
        track_center_y = dial_cy
        track_top = track_center_y - 6
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#ccc"))
        painter.drawRoundedRect(track_x_start, track_top, track_width, 12, 6, 6)
        thumb_x = track_x_start + (pan + 1.0) * 0.5 * track_width
        painter.setBrush(QColor("#3498db"))
        painter.setPen(QPen(QColor("#2980b9"), 1))
        thumb_r = 8
        painter.drawEllipse(int(thumb_x - thumb_r), int(track_center_y - thumb_r), thumb_r * 2, thumb_r * 2)
        painter.setPen(QColor("#333333"))
        painter.drawText(track_x_start - 14, track_center_y + 4, "L")
        painter.drawText(track_x_start + track_width // 2 - 4, track_center_y + 4, "C")
        painter.drawText(track_x_start + track_width - 4, track_center_y + 4, "R")


class ImuSquareSoundLoudnessWidget(ImuSquareSoundWidget):
    """Widget that displays a blue square with audio including acceleration-based loudness (Proto D: Pitch+Pan+Vol).
    
    Extends ImuSquareSoundWidget to add acceleration-based amplitude:
    - Visual: Same as Prototype B (blue square)
    - Audio: Pitch controls frequency, roll controls stereo panning
    - Loudness: Amplitude controlled by Z-axis accelerometer (step-based, 2s cooldown)
    - Uses same tilt mapping as Prototype B for visual
    - Uses extended roll range for audio panning (MAX_ROLL_PAN_DEG = 28.0°)
    - Bottom area: Pan and Volume bars left (stacked), Pitch dial right
    """
    
    # Acceleration-based loudness configuration
    AMP_MIN = 0.02      # Minimum amplitude
    AMP_MAX = 0.25      # Maximum amplitude
    VOLUME_STEP = 0.1   # Volume increment/decrement step (10% of range)
    ACCEL_THRESHOLD_HIGH = 1.2  # Z-acceleration threshold for volume up (g)
    ACCEL_THRESHOLD_LOW = 0.8   # Z-acceleration threshold for volume down (g)
    MEASUREMENT_COOLDOWN = 2.0  # Seconds to wait after last volume adjustment
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Acceleration-based volume control state
        self.current_amplitude = self.AMP_MIN  # Start at minimum
        self.last_measurement_time = None
        self.current_accel_z = 1.0  # Default to 1g (flat)
        
        # Timer to update volume display periodically
        self.volume_update_timer = QTimer(self)
        self.volume_update_timer.timeout.connect(self._update_volume_display)
        self.volume_update_timer.start(50)  # Update every 50ms (~20 Hz)
    
    def update_accel_z(self, accel_z_g: float):
        """Update Z-axis acceleration and adjust volume based on thresholds.
        
        Volume increases by VOLUME_STEP when accel_z > ACCEL_THRESHOLD_HIGH
        Volume decreases by VOLUME_STEP when accel_z < ACCEL_THRESHOLD_LOW
        Volume adjustments are only allowed after MEASUREMENT_COOLDOWN seconds
        have passed since the last volume adjustment.
        
        Args:
            accel_z_g: Z-axis acceleration in g (gravity units)
        """
        # Always update current acceleration (measure continuously)
        self.current_accel_z = accel_z_g
        
        now = time.time()
        
        # Check if enough time has passed since last volume adjustment
        if self.last_measurement_time is not None:
            time_since_last_adjustment = now - self.last_measurement_time
            if time_since_last_adjustment < self.MEASUREMENT_COOLDOWN:
                # Still in cooldown, don't adjust volume yet
                return
        
        # Check thresholds and adjust volume if needed
        volume_changed = False
        if accel_z_g > self.ACCEL_THRESHOLD_HIGH:
            # High acceleration (tilted back/up) → increase volume
            old_amplitude = self.current_amplitude
            self.current_amplitude = min(
                self.current_amplitude + self.VOLUME_STEP,
                self.AMP_MAX
            )
            if self.current_amplitude != old_amplitude:
                volume_changed = True
        elif accel_z_g < self.ACCEL_THRESHOLD_LOW:
            # Low acceleration (tilted forward/down) → decrease volume
            old_amplitude = self.current_amplitude
            self.current_amplitude = max(
                self.current_amplitude - self.VOLUME_STEP,
                self.AMP_MIN
            )
            if self.current_amplitude != old_amplitude:
                volume_changed = True
        
        # Only update cooldown timer if we actually changed the volume
        if volume_changed:
            self.last_measurement_time = now
    
    def paintEvent(self, event):
        """Paint blue square, target circle, and bottom area: Pan + Volume (left), Pitch dial (right)."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        widget_width = self.width()
        widget_height = self.height()
        square_area_height = widget_height - self.INDICATOR_HEIGHT
        if square_area_height < 50:
            square_area_height = 50
        cx = widget_width // 2
        cy = square_area_height // 2
        max_dx = widget_width // 2 - self.SQUARE_SIZE // 2 - 5
        max_dy = square_area_height // 2 - self.SQUARE_SIZE // 2 - 5
        x_offset = (self.square_x - 0.5) * 2 * max_dx
        y_offset = (self.square_y - 0.5) * 2 * max_dy
        square_x_pixel = int(cx + x_offset)
        square_y_pixel = int(cy + y_offset)
        distance_from_center = ((square_x_pixel - cx)**2 + (square_y_pixel - cy)**2)**0.5
        in_target_zone = (abs(self.current_roll_deg) <= self.TARGET_TOLERANCE_DEG and
                         abs(self.current_pitch_deg) <= self.TARGET_TOLERANCE_DEG)
        square_in_circle = distance_from_center <= self.TARGET_CIRCLE_RADIUS
        circle_color = QColor("#2ecc71") if (in_target_zone and square_in_circle) else QColor("#95a5a6")
        painter.setBrush(circle_color)
        painter.setPen(QPen(QColor("#34495e"), 2))
        painter.drawEllipse(
            cx - self.TARGET_CIRCLE_RADIUS, cy - self.TARGET_CIRCLE_RADIUS,
            self.TARGET_CIRCLE_RADIUS * 2, self.TARGET_CIRCLE_RADIUS * 2
        )
        painter.setBrush(QColor("#3498db"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            square_x_pixel - self.SQUARE_SIZE // 2, square_y_pixel - self.SQUARE_SIZE // 2,
            self.SQUARE_SIZE, self.SQUARE_SIZE
        )
        self._draw_pitch_pan_volume_indicators(painter, widget_width, widget_height)
    
    def _draw_pitch_pan_volume_indicators(self, painter, widget_width, widget_height):
        """Draw Pan (top left), Volume (bottom left), Pitch dial (right)."""
        bar_area_y = widget_height - self.INDICATOR_HEIGHT
        margin = 12
        dial_size = 196
        # Pitch dial on the right
        dial_cx = widget_width - margin - dial_size // 2 - 8
        dial_cy = bar_area_y + margin + dial_size // 2 + 4
        # Left area: bars end before dial (26 px gap = 16 + 10 so bars and dial don't crowd)
        left_area_right = dial_cx - dial_size // 2 - 26
        left_area_width = left_area_right - margin - 80
        bar_height = 28
        bar_gap = 15
        # --- Pan bar (top left) ---
        roll_clamped = max(-self.MAX_ROLL_PAN_DEG, min(self.MAX_ROLL_PAN_DEG, self.current_roll))
        pan = roll_clamped / self.MAX_ROLL_PAN_DEG
        pan_y = bar_area_y + margin
        painter.setPen(QColor("#333333"))
        painter.setFont(QFont("Arial", 11))  # match Pitch label
        painter.drawText(margin, pan_y + bar_height // 2 + 4, "Pan")
        track_x = margin + 58
        track_width = left_area_width - 28
        track_x_start = track_x
        track_center_y = pan_y + bar_height // 2
        track_h = 24
        track_top = track_center_y - track_h // 2
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#ccc"))
        painter.drawRoundedRect(track_x_start, track_top, track_width, track_h, 8, 8)
        thumb_x = track_x_start + (pan + 1.0) * 0.5 * track_width
        thumb_r = 14  # 28 px diameter, slightly bigger than track (24 px) for a physical cap
        thumb_rect = (int(thumb_x - thumb_r), int(track_center_y - thumb_r), thumb_r * 2, thumb_r * 2)
        # Bezel look: blue fill + rim (lighter dark for less contrast with highlight)
        painter.setBrush(QColor("#3498db"))  # blue thumb
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(*thumb_rect)
        painter.setPen(QPen(QColor("#2980b9"), 3))  # medium blue rim, less contrast than #1a5276
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(*thumb_rect)
        # Highlight arc (top-left); angles in 1/16th of a degree, 0 = 3 o'clock, positive = CCW
        painter.setPen(QPen(QColor("#7ec8e3"), 3))
        painter.drawArc(*thumb_rect, 1440, 1440)   # 90° to 180°
        painter.setPen(QColor("#333333"))
        painter.drawText(track_x_start - 14, track_center_y + 4, "L")
        painter.drawText(track_x_start + track_width // 2 - 4, track_center_y + 4, "C")
        painter.drawText(track_x_start + track_width + 6, track_center_y + 4, "R")
        # --- Volume bar (bottom left) ---
        if self.AMP_MAX > self.AMP_MIN:
            vol_percent = ((self.current_amplitude - self.AMP_MIN) / (self.AMP_MAX - self.AMP_MIN)) * 100.0
        else:
            vol_percent = 0.0
        vol_percent = max(0.0, min(100.0, vol_percent))
        vol_y = pan_y + bar_height + bar_gap
        painter.drawText(margin, vol_y + bar_height // 2 + 4, "Volume")
        vol_bar_x = margin + 58
        vol_bar_width = left_area_width - 30
        vol_track_h = 24
        vol_track_top = vol_y + (bar_height - vol_track_h) // 2
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#ccc"))
        painter.drawRoundedRect(vol_bar_x, vol_track_top, vol_bar_width, vol_track_h, 8, 8)
        fill_width = int((vol_percent / 100.0) * vol_bar_width)
        if fill_width > 0:
            painter.setBrush(QColor("#3498db"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(vol_bar_x, vol_track_top, fill_width, vol_track_h, 8, 8)
        vol_label = f"{vol_percent:.0f}%"
        fm = QFontMetrics(painter.font())
        vol_label_width = fm.horizontalAdvance(vol_label)
        label_inset = 8
        if fill_width >= vol_label_width + label_inset * 2:
            painter.setPen(QColor("#ffffff"))
            painter.drawText(
                vol_bar_x + label_inset,
                vol_track_top,
                fill_width - label_inset * 2,
                vol_track_h,
                Qt.AlignCenter,
                vol_label,
            )
        # Store for mousePressEvent
        self._vol_bar_bounds = (vol_bar_x, vol_track_top, vol_bar_width, vol_track_h)
        # --- Pitch dial (right): gauge style with segmented arc (green→red), tick marks, black needle ---
        pitch_clamped = max(-self.MAX_TILT_DEG, min(self.MAX_TILT_DEG, self.current_pitch))
        norm = (pitch_clamped + self.MAX_TILT_DEG) / (2 * self.MAX_TILT_DEG)
        freq = self.BASE_FREQ + (self.MAX_FREQ - self.BASE_FREQ) * norm
        r_outer = dial_size // 2 - 2
        r_inner = r_outer - 20
        r_tick = r_inner - 2
        segment_colors = [
            QColor("#2e7d32"),
            QColor("#66bb6a"),
            QColor("#fdd835"),
            QColor("#ff9800"),
            QColor("#e53935"),
        ]
        num_arc_pts = 12
        for i in range(5):
            angle_start_deg = 180 - i * 36
            angle_end_deg = 180 - (i + 1) * 36
            points = []
            for k in range(num_arc_pts + 1):
                t = k / num_arc_pts
                angle_deg = angle_start_deg + t * (angle_end_deg - angle_start_deg)
                rad = math.radians(angle_deg)
                points.append(QPointF(dial_cx + r_outer * math.cos(rad), dial_cy - r_outer * math.sin(rad)))
            for k in range(num_arc_pts, -1, -1):
                t = k / num_arc_pts
                angle_deg = angle_start_deg + t * (angle_end_deg - angle_start_deg)
                rad = math.radians(angle_deg)
                points.append(QPointF(dial_cx + r_inner * math.cos(rad), dial_cy - r_inner * math.sin(rad)))
            poly = QPolygonF(points)
            painter.setPen(Qt.NoPen)
            painter.setBrush(segment_colors[i])
            painter.drawPolygon(poly)
        painter.setPen(QPen(QColor("#333333"), 1))
        for ti in range(11):
            t = ti / 10.0
            angle_deg = 180 - t * 180
            rad = math.radians(angle_deg)
            x_outer = dial_cx + r_tick * math.cos(rad)
            y_outer = dial_cy - r_tick * math.sin(rad)
            x_inner = dial_cx + (r_tick - 6) * math.cos(rad)
            y_inner = dial_cy - (r_tick - 6) * math.sin(rad)
            painter.drawLine(int(x_inner), int(y_inner), int(x_outer), int(y_outer))
        fm = painter.fontMetrics()
        painter.setFont(QFont("Arial", 8))
        for f, label in [(220, "220"), (440, "440"), (660, "660"), (880, "880")]:
            t = (f - self.BASE_FREQ) / (self.MAX_FREQ - self.BASE_FREQ) if (self.MAX_FREQ - self.BASE_FREQ) != 0 else 0
            t = max(0.0, min(1.0, t))
            angle_deg = 180 - t * 180
            rad = math.radians(angle_deg)
            label_r = r_outer + 14
            tx = dial_cx + label_r * math.cos(rad)
            ty = dial_cy - label_r * math.sin(rad)
            lx = int(tx - fm.horizontalAdvance(label) / 2)
            ly = int(ty + fm.ascent() / 2)
            painter.drawText(lx, ly, label)
        needle_angle_deg = 180 - norm * 180
        needle_rad = math.radians(needle_angle_deg)
        needle_len = r_outer - 6
        needle_tip_x = dial_cx + needle_len * math.cos(needle_rad)
        needle_tip_y = dial_cy - needle_len * math.sin(needle_rad)
        base_w = 5
        perp_x = -math.sin(needle_rad) * base_w
        perp_y = -math.cos(needle_rad) * base_w
        needle_poly = QPolygonF([
            QPointF(needle_tip_x, needle_tip_y),
            QPointF(dial_cx + perp_x, dial_cy - perp_y),
            QPointF(dial_cx - perp_x, dial_cy + perp_y),
        ])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1a1a1a"))
        painter.drawPolygon(needle_poly)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#333333"), 1))
        painter.drawEllipse(int(dial_cx - 5), int(dial_cy - 5), 10, 10)
        painter.setPen(QColor("#333333"))
        painter.setFont(QFont("Arial", 11))
        painter.drawText(dial_cx - dial_size // 2 - 60, dial_cy - 6, "Pitch")
        painter.drawText(dial_cx - dial_size // 2 - 60, dial_cy + 10, f"{int(round(freq))} Hz")
    
    def _update_volume_display(self):
        """Update the volume display (called by timer)."""
        self.update()  # Trigger repaint
    
    def mousePressEvent(self, event):
        """Handle mouse clicks on the volume bar to set volume directly."""
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        bounds = getattr(self, "_vol_bar_bounds", None)
        if bounds is None:
            return super().mousePressEvent(event)
        bar_x, bar_y, bar_width, bar_height = bounds
        click_x, click_y = event.x(), event.y()
        if (bar_x <= click_x <= bar_x + bar_width and bar_y <= click_y <= bar_y + bar_height):
            relative_x = click_x - bar_x
            vol_percent = (relative_x / bar_width) * 100.0 if bar_width > 0 else 0.0
            vol_percent = max(0.0, min(100.0, vol_percent))
            if self.AMP_MAX > self.AMP_MIN:
                new_amplitude = self.AMP_MIN + (vol_percent / 100.0) * (self.AMP_MAX - self.AMP_MIN)
            else:
                new_amplitude = self.AMP_MIN
            self.current_amplitude = max(self.AMP_MIN, min(self.AMP_MAX, new_amplitude))
            self.last_measurement_time = None
            self.update()
        return super().mousePressEvent(event)
    
    def start_audio(self):
        """Start the audio stream with acceleration-based loudness."""
        if self.audio_stream is not None:
            return  # Already started
        
        # Reset acceleration tracking state
        self.current_amplitude = self.AMP_MIN  # Start at minimum
        self.last_measurement_time = None
        
        def audio_callback(outdata, frames, time_info, status):
            try:
                if status:
                    print("Audio status:", status)
                
                # Use current angles (updated by set_angles_for_audio)
                roll_deg = self.current_roll
                pitch_deg = self.current_pitch
                
                # --- Pitch mapping: pitch_deg -> freq in [BASE_FREQ, MAX_FREQ] ---
                pitch_clamped = max(-self.MAX_TILT_DEG, min(self.MAX_TILT_DEG, pitch_deg))
                # Map [-MAX_TILT_DEG, +MAX_TILT_DEG] -> [0, 1]
                norm = (pitch_clamped + self.MAX_TILT_DEG) / (2 * self.MAX_TILT_DEG)
                freq = self.BASE_FREQ + (self.MAX_FREQ - self.BASE_FREQ) * norm
                
                # --- Pan mapping: roll -> pan in [-1, 1] ---
                roll_clamped = max(-self.MAX_ROLL_PAN_DEG, min(self.MAX_ROLL_PAN_DEG, roll_deg))
                pan = roll_clamped / self.MAX_ROLL_PAN_DEG  # -1 = full left, +1 = full right
                
                # --- Acceleration-based loudness (updated separately via update_accel_z) ---
                # Use current amplitude (updated by update_accel_z with 2s cooldown)
                amp = self.current_amplitude
                
                # --- Oscillator ---
                phase = self.audio_phase
                t = np.arange(frames, dtype=np.float32)
                
                phase_increment = 2.0 * np.pi * freq / self.AUDIO_SAMPLE_RATE
                phases = phase + phase_increment * t
                
                # Keep phase from growing without bound
                self.audio_phase = float((phases[-1] + phase_increment) % (2.0 * np.pi))
                
                mono = np.sin(phases).astype(np.float32)
                
                # Apply acceleration-based amplitude
                mono *= amp
                
                # --- Equal-power stereo panning ---
                left_gain = np.sqrt((1.0 - pan) / 2.0)
                right_gain = np.sqrt((1.0 + pan) / 2.0)
                
                outdata[:, 0] = mono * left_gain   # left channel
                outdata[:, 1] = mono * right_gain  # right channel
            except Exception as e:
                print(f"Error in Proto D: Pitch+Pan+Vol audio callback: {e}")
                import traceback
                traceback.print_exc()
                outdata.fill(0)
        
        try:
            self.audio_stream = sd.OutputStream(
                samplerate=self.AUDIO_SAMPLE_RATE,
                channels=2,
                blocksize=self.AUDIO_BLOCK_SIZE,
                callback=audio_callback,
            )
            self.audio_stream.start()
            print(f"Audio stream started successfully")
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            import traceback
            traceback.print_exc()
            self.audio_stream = None
    
    def stop_audio(self):
        """Stop the audio stream and reset acceleration tracking."""
        super().stop_audio()
        # Reset acceleration tracking state
        self.current_amplitude = self.AMP_MIN
        self.last_measurement_time = None
        self.current_accel_z = 1.0


class ImuSquareSoundTimbreWidget(ImuSquareWidget):
    """Widget that displays a blue square with audio including timbre control from roll and yaw-based panning (Proto F: Pitch+Timbre).
    
    Extends ImuSquareWidget to add audio with timbre control:
    - Visual: Same as Prototype B (blue square)
    - Audio: Pitch controls frequency, yaw controls stereo panning, roll controls timbre
    - Volume: User-controlled via clickable volume bar (no motion control)
    - Timbre: Roll angle morphs between sine (warm) and sawtooth (bright) waveforms
    - Uses same tilt mapping as Prototype B for visual
    - Uses extended roll range for timbre control (MAX_ROLL_TIMBRE_DEG = 45.0°)
    - Displays three bars: Volume (user-controlled), Pitch (IMU-controlled), Timbre (IMU-controlled)
    """
    
    # Audio configuration (matching ImuSquareSoundWidget)
    AUDIO_SAMPLE_RATE = 44100
    AUDIO_BLOCK_SIZE = 256
    BASE_FREQ = 220.0   # A3-ish
    MAX_FREQ = 880.0    # A5-ish
    AUDIO_AMP = 0.15    # Base amplitude (user can adjust via volume bar)
    
    # Volume control (user-adjustable, no motion control)
    VOLUME_INDICATOR_HEIGHT = 120  # Height for all three bars
    AMP_MIN = 0.0       # Minimum amplitude
    AMP_MAX = 0.5       # Maximum amplitude
    
    MAX_ROLL_TIMBRE_DEG = 45.0  # Full timbre range at ±45° roll
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_stream = None
        self.current_roll = 0.0
        self.current_pitch = 0.0
        self.current_yaw = 180.0  # Initialize to center (180° = center pan)
        self.audio_phase = 0.0
        
        # User-controlled volume (no motion control)
        self.current_amplitude = self.AMP_MIN + (self.AMP_MAX - self.AMP_MIN) * 0.5  # Start at 50%
        
        # Current values for display bars
        self.current_pitch_norm = 0.5  # Normalized pitch (0-1)
        self.current_timbre_norm = 0.5  # Normalized timbre (0-1)
    
    def paintEvent(self, event):
        """Paint the blue square and three control bars (Volume, Pitch, Timbre)."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        widget_width = self.width()
        widget_height = self.height()
        square_area_height = widget_height - self.VOLUME_INDICATOR_HEIGHT
        
        # Center of the square drawing area
        cx = widget_width // 2
        cy = square_area_height // 2
        
        # Calculate maximum distance from center (with padding)
        max_dx = widget_width // 2 - self.SQUARE_SIZE // 2 - 5
        max_dy = square_area_height // 2 - self.SQUARE_SIZE // 2 - 5
        
        # Map normalized position to pixel coordinates
        x_offset = (self.square_x - 0.5) * 2 * max_dx
        y_offset = (self.square_y - 0.5) * 2 * max_dy
        
        square_x_pixel = int(cx + x_offset)
        square_y_pixel = int(cy + y_offset)
        
        # Calculate distance from square center to widget center
        square_center_x = square_x_pixel
        square_center_y = square_y_pixel
        distance_from_center = ((square_center_x - cx)**2 + (square_center_y - cy)**2)**0.5
        
        # Check if roll and pitch are within target tolerance
        in_target_zone = (abs(self.current_roll_deg) <= self.TARGET_TOLERANCE_DEG and 
                         abs(self.current_pitch_deg) <= self.TARGET_TOLERANCE_DEG)
        
        # Check if square is inside the target circle
        square_in_circle = distance_from_center <= self.TARGET_CIRCLE_RADIUS
        
        # Choose circle color: green if in target zone AND square is inside, gray otherwise
        if in_target_zone and square_in_circle:
            circle_color = QColor("#2ecc71")  # Green
        else:
            circle_color = QColor("#95a5a6")  # Gray
        
        # Always draw target circle
        painter.setBrush(circle_color)
        painter.setPen(QPen(QColor("#34495e"), 2))  # Dark border
        painter.drawEllipse(
            cx - self.TARGET_CIRCLE_RADIUS,
            cy - self.TARGET_CIRCLE_RADIUS,
            self.TARGET_CIRCLE_RADIUS * 2,
            self.TARGET_CIRCLE_RADIUS * 2
        )
        
        # Draw blue square (circle)
        painter.setBrush(QColor("#3498db"))  # Blue color
        painter.setPen(QPen(QColor("#2980b9"), 2))
        painter.drawEllipse(
            square_x_pixel - self.SQUARE_SIZE // 2,
            square_y_pixel - self.SQUARE_SIZE // 2,
            self.SQUARE_SIZE,
            self.SQUARE_SIZE
        )
        
        # Draw three control bars at the bottom
        self._draw_control_bars(painter, widget_width, widget_height)
    
    def _draw_control_bars(self, painter, widget_width, widget_height):
        """Draw Volume, Pitch, and Timbre bars."""
        bar_area_y = widget_height - self.VOLUME_INDICATOR_HEIGHT
        bar_height = 20
        bar_spacing = 5
        label_width = 80
        value_width = 60
        bar_x = label_width
        bar_width = widget_width - bar_x - value_width - 20
        
        # Bar 1: Volume (user-controlled)
        vol_y = bar_area_y + 10
        self._draw_single_bar(painter, bar_x, vol_y, bar_width, bar_height,
                             "Volume:", self.current_amplitude, self.AMP_MIN, self.AMP_MAX,
                             widget_width, value_width, "#3498db", True)
        
        # Bar 2: Pitch (IMU-controlled, read-only)
        pitch_y = vol_y + bar_height + bar_spacing
        self._draw_single_bar(painter, bar_x, pitch_y, bar_width, bar_height,
                             "Pitch:", self.current_pitch_norm, 0.0, 1.0,
                             widget_width, value_width, "#27ae60", False)
        
        # Bar 3: Timbre (IMU-controlled, read-only)
        timbre_y = pitch_y + bar_height + bar_spacing
        self._draw_single_bar(painter, bar_x, timbre_y, bar_width, bar_height,
                             "Timbre:", self.current_timbre_norm, 0.0, 1.0,
                             widget_width, value_width, "#e74c3c", False)
    
    def _draw_single_bar(self, painter, bar_x, bar_y, bar_width, bar_height,
                        label, value, min_val, max_val, widget_width, value_width,
                        fill_color, is_clickable):
        """Draw a single control bar with label and value."""
        # Draw background for bar area
        if is_clickable:
            painter.fillRect(0, bar_y - 5, widget_width, bar_height + 10, QColor("#f5f5f5"))
        
        # Draw label
        painter.setPen(QColor("#333333"))
        painter.setFont(QFont("Arial", 10))
        label_rect = painter.fontMetrics().boundingRect(label)
        painter.drawText(10, bar_y + bar_height // 2 + label_rect.height() // 2 - 2, label)
        
        # Calculate fill percentage
        if max_val > min_val:
            percent = ((value - min_val) / (max_val - min_val)) * 100.0
        else:
            percent = 0.0
        percent = max(0.0, min(100.0, percent))
        
        # Draw bar background
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#ccc"))
        painter.drawRoundedRect(bar_x, bar_y, bar_width, bar_height, 3, 3)
        
        # Draw bar fill
        fill_width = int((percent / 100.0) * bar_width)
        if fill_width > 0:
            painter.setBrush(QColor(fill_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar_x, bar_y, fill_width, bar_height, 3, 3)
        
        # Draw value
        if is_clickable:
            # Volume: show percentage
            value_text = f"{percent:.1f}%"
        else:
            # Pitch/Timbre: show percentage
            value_text = f"{percent:.1f}%"
        
        value_rect = painter.fontMetrics().boundingRect(value_text)
        value_x = widget_width - value_width
        value_y = bar_y + bar_height // 2 + value_rect.height() // 2 - 2
        painter.setPen(QColor("#333333"))
        painter.drawText(value_x, value_y, value_text)
    
    def mousePressEvent(self, event):
        """Handle mouse clicks on the volume bar to set volume directly."""
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        
        widget_width = self.width()
        widget_height = self.height()
        bar_area_y = widget_height - self.VOLUME_INDICATOR_HEIGHT
        
        bar_height = 20
        bar_spacing = 5
        label_width = 80
        value_width = 60
        bar_x = label_width
        bar_width = widget_width - bar_x - value_width - 20
        
        # Volume bar coordinates (only clickable bar)
        vol_y = bar_area_y + 10
        
        click_x = event.x()
        click_y = event.y()
        
        # Check if click is within the volume bar area
        if (bar_x <= click_x <= bar_x + bar_width and 
            vol_y <= click_y <= vol_y + bar_height):
            # Calculate volume percentage based on click position
            relative_x = click_x - bar_x
            vol_percent = (relative_x / bar_width) * 100.0
            vol_percent = max(0.0, min(100.0, vol_percent))
            
            # Convert percentage to amplitude
            # Map from [0, 100] to [AMP_MIN, AMP_MAX]
            if self.AMP_MAX > self.AMP_MIN:
                new_amplitude = self.AMP_MIN + (vol_percent / 100.0) * (self.AMP_MAX - self.AMP_MIN)
            else:
                new_amplitude = self.AMP_MIN
            
            # Set the new amplitude
            self.current_amplitude = max(self.AMP_MIN, min(self.AMP_MAX, new_amplitude))
            
            # Trigger repaint to show new volume
            self.update()
        
        return super().mousePressEvent(event)
    
    def _update_display(self):
        """Update the display bars (called periodically)."""
        self.update()  # Trigger repaint
    
    def compute_timbre_from_roll(self, roll_deg: float) -> float:
        """Compute normalized timbre value from roll angle.
        
        Args:
            roll_deg: Roll angle in degrees
            
        Returns:
            Normalized timbre value in [0, 1]
            - 0.0 = full left roll → warm/mellow (sine wave)
            - 0.5 = neutral roll → neutral timbre (50% sine, 50% sawtooth)
            - 1.0 = full right roll → bright/sharp (sawtooth wave)
        """
        roll_clamped = max(-self.MAX_ROLL_TIMBRE_DEG, min(self.MAX_ROLL_TIMBRE_DEG, roll_deg))
        timbre_norm = (roll_clamped + self.MAX_ROLL_TIMBRE_DEG) / (2 * self.MAX_ROLL_TIMBRE_DEG)
        self.current_timbre_norm = timbre_norm  # Store for display
        return timbre_norm
    
    def start_audio(self):
        """Start the audio stream with timbre control."""
        if self.audio_stream is not None:
            return  # Already started
        
        def audio_callback(outdata, frames, time_info, status):
            try:
                if status:
                    print("Audio status:", status)
                
                # Use current angles (updated by set_angles_for_audio)
                roll_deg = self.current_roll
                pitch_deg = self.current_pitch
                yaw_deg = self.current_yaw
                
                # --- Pitch mapping: pitch_deg -> freq in [BASE_FREQ, MAX_FREQ] ---
                pitch_clamped = max(-self.MAX_TILT_DEG, min(self.MAX_TILT_DEG, pitch_deg))
                # Map [-MAX_TILT_DEG, +MAX_TILT_DEG] -> [0, 1]
                norm = (pitch_clamped + self.MAX_TILT_DEG) / (2 * self.MAX_TILT_DEG)
                self.current_pitch_norm = norm  # Store for display
                freq = self.BASE_FREQ + (self.MAX_FREQ - self.BASE_FREQ) * norm
                
                # --- Pan mapping: yaw -> pan in [-1, 1] ---
                # Convert yaw from 0-360° to -1 to +1 for panning
                # 0° = full left, 180° = center, 360° = full right
                yaw_normalized = (yaw_deg - 180.0) / 180.0
                pan = max(-1.0, min(1.0, yaw_normalized))  # -1 = full left, +1 = full right
                
                # --- Timbre mapping: roll -> timbre_norm in [0, 1] ---
                timbre_norm = self.compute_timbre_from_roll(roll_deg)
                
                # --- User-controlled volume (no motion control) ---
                amp = self.current_amplitude
                
                # --- Oscillator with waveform morphing ---
                phase = self.audio_phase
                t = np.arange(frames, dtype=np.float32)
                
                phase_increment = 2.0 * np.pi * freq / self.AUDIO_SAMPLE_RATE
                phases = phase + phase_increment * t
                
                # Keep phase from growing without bound
                self.audio_phase = float((phases[-1] + phase_increment) % (2.0 * np.pi))
                
                # Generate base waveforms
                sine_wave = np.sin(phases).astype(np.float32)
                # Generate sawtooth: 2.0 * (phase / (2π) % 1.0) - 1.0
                sawtooth_wave = (2.0 * (phases / (2.0 * np.pi) % 1.0) - 1.0).astype(np.float32)
                
                # Morph between sine and sawtooth based on timbre
                # timbre_norm = 0 → sine (warm), timbre_norm = 1 → sawtooth (bright)
                mono = (1.0 - timbre_norm) * sine_wave + timbre_norm * sawtooth_wave
                
                # Apply user-controlled amplitude
                mono *= amp
                
                # --- Equal-power stereo panning ---
                left_gain = np.sqrt((1.0 - pan) / 2.0)
                right_gain = np.sqrt((1.0 + pan) / 2.0)
                
                outdata[:, 0] = mono * left_gain   # left channel
                outdata[:, 1] = mono * right_gain  # right channel
            except Exception as e:
                print(f"Error in Proto F: Pitch+Timbre audio callback: {e}")
                import traceback
                traceback.print_exc()
                outdata.fill(0)
        
        try:
            self.audio_stream = sd.OutputStream(
                samplerate=self.AUDIO_SAMPLE_RATE,
                channels=2,
                blocksize=self.AUDIO_BLOCK_SIZE,
                callback=audio_callback,
            )
            self.audio_stream.start()
            print(f"Audio stream started successfully")
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            import traceback
            traceback.print_exc()
            self.audio_stream = None
    
    def stop_audio(self):
        """Stop the audio stream."""
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        self.audio_phase = 0.0
    
    def set_angles_for_audio(self, roll_deg: float, pitch_deg: float, yaw_deg: float):
        """Update angles for audio generation (separate from visual position).
        
        Args:
            roll_deg: Roll angle in degrees (controls timbre)
            pitch_deg: Pitch angle in degrees (controls frequency)
            yaw_deg: Yaw angle in degrees (controls panning, 0-360°)
        """
        self.current_roll = roll_deg
        self.current_pitch = pitch_deg
        self.current_yaw = yaw_deg


class ImuSquareSoundFileWidget(ImuSquareWidget):
    """Widget that displays 7-band EQ visualization with audio file playback (Proto G: Equalizer).
    
    Extends ImuSquareWidget to add audio file playback with IMU control:
    - Visual: 7-band EQ bars (no blue square)
    - Audio: Plays music/music.mp3 on loop
    - Volume: Controlled by pitch angle
    - Timbre: Controlled by roll angle (7-band tilt EQ)
    - Displays: Volume bar + 7 EQ band bars
    """
    
    # Audio configuration
    AUDIO_SAMPLE_RATE = 44100
    AUDIO_BLOCK_SIZE = 2048  # Power of 2 for FFT; 2048 gives ~21.5 Hz bin spacing so 7-band EQ (e.g. 20–60 Hz) is meaningful; 256 was too coarse (~172 Hz)
    AUDIO_FILE = "music/music.mp3"
    
    # Volume control (pitch angle)
    VOLUME_MIN = 0.0      # Minimum volume (muted)
    VOLUME_MAX = 1.0      # Maximum volume
    MAX_PITCH_VOLUME_DEG = 5.0  # Full volume range at ±5° pitch (uses MAX_TILT_DEG)
    
    # Timbre control (roll angle) - 7-band EQ
    MAX_ROLL_TIMBRE_DEG = 10.0  # Full timbre range at ±10° roll (tilt EQ)
    MAX_GAIN_DB = 12.0          # Max gain per band in dB; 12 makes tilt clearly audible on a full mix
    # Asymmetry: lows boost more than highs cut so tilt feels more dramatic
    LOW_BOOST_FACTOR = 1.3      # Multiply gain for low bands (band_pos < 0)
    HIGH_CUT_FACTOR = 0.75      # Multiply gain for high bands (band_pos > 0)
    
    # Smoothing parameters
    EQ_SMOOTHING_ALPHA = 0.15   # Exponential smoothing factor (0-1, lower = smoother)
    
    # Frequency bands (Hz) - 7 bands
    BAND_EDGES = [
        (20, 60),       # Sub bass
        (60, 250),      # Bass
        (250, 500),     # Lower mids
        (500, 2000),    # Mids
        (2000, 4000),   # Upper mids
        (4000, 6000),   # Presence
        (6000, 20000),  # Brilliance
    ]
    N_BANDS = 7
    
    # Control bars height
    USER_VOLUME_INDICATOR_HEIGHT = 50  # Height for Volume bar at bottom
    EQ_BARS_AREA_HEIGHT = 300  # Height for 7 EQ bars in center
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_stream = None
        self.current_roll = 0.0
        self.current_pitch = 0.0
        self.current_yaw = 180.0  # Initialize to center (180° = center pan)
        
        # Audio file data
        self.audio_data = None
        self.audio_sample_rate = None
        self.audio_position = 0  # Current playback position in samples
        
        # Volume is now only controlled by roll angle (IMU), not user-controlled
        
        # Current values for display bars
        self.current_volume_norm = 0.5  # Normalized volume from pitch (0-1)
        self.current_band_gains_db = np.zeros(self.N_BANDS, dtype=np.float32)  # Current EQ band gains in dB
        
        # Smoothed gains for audio processing (exponential smoothing)
        self.smoothed_gains_db = np.zeros(self.N_BANDS, dtype=np.float32)
        
        # Precompute FFT bin to band index mapping
        self.band_index = self._build_band_index()
        
        # Load audio file (lazy - only when Proto G: Equalizer is actually used)
        # Don't load immediately to avoid blocking other methods
        self._audio_file_loaded = False
    
    def _load_audio_file(self):
        """Load the audio file once at initialization."""
        try:
            # Lazy import librosa only when needed
            import librosa
            
            audio_path = Path(self.AUDIO_FILE)
            if not audio_path.exists():
                print(f"Warning: Audio file not found: {self.AUDIO_FILE}")
                return
            
            # Load audio file (mono, resampled to our sample rate if needed)
            self.audio_data, self.audio_sample_rate = librosa.load(
                str(audio_path),
                sr=self.AUDIO_SAMPLE_RATE,
                mono=True
            )
            print(f"Loaded audio file: {self.AUDIO_FILE} ({len(self.audio_data)} samples, {self.audio_sample_rate} Hz)")
        except Exception as e:
            print(f"Error loading audio file: {e}")
            import traceback
            traceback.print_exc()
            self.audio_data = None
    
    def compute_volume_from_pitch(self, pitch_deg: float) -> float:
        """Compute normalized volume value from pitch angle.
        
        Args:
            pitch_deg: Pitch angle in degrees
            
        Returns:
            Normalized volume value in [0, 1]
            - 0.0 = full backward pitch → muted
            - 0.5 = neutral pitch → 50% volume
            - 1.0 = full forward pitch → full volume
        """
        pitch_clamped = max(-self.MAX_PITCH_VOLUME_DEG, min(self.MAX_PITCH_VOLUME_DEG, pitch_deg))
        volume_norm = (pitch_clamped + self.MAX_PITCH_VOLUME_DEG) / (2 * self.MAX_PITCH_VOLUME_DEG)
        self.current_volume_norm = volume_norm  # Store for display
        return volume_norm
    
    def _build_band_index(self) -> np.ndarray:
        """
        Precompute which EQ band each FFT bin belongs to.
        
        Returns:
            band_index: int array of length (AUDIO_BLOCK_SIZE//2 + 1)
                        where band_index[k] is in [0, N_BANDS-1]
        """
        freqs = np.fft.rfftfreq(self.AUDIO_BLOCK_SIZE, d=1.0 / self.AUDIO_SAMPLE_RATE)
        band_index = np.zeros_like(freqs, dtype=np.int32)
        
        for k, f in enumerate(freqs):
            # Default band = 0 (lowest)
            idx = 0
            for band_i, (low, high) in enumerate(self.BAND_EDGES):
                if f >= low and f < high:
                    idx = band_i
                    break
                # If frequency exceeds the last band's upper edge, clamp to last band
                if f >= self.BAND_EDGES[-1][1]:
                    idx = len(self.BAND_EDGES) - 1
                    break
            band_index[k] = idx
        
        return band_index
    
    def compute_band_gains_db(self, roll_deg: float) -> np.ndarray:
        """
        Map IMU roll angle (degrees) to a 7-element array of EQ band gains in dB.
        
        - Tilt EQ: roll right → boost lows / cut highs; roll left → cut lows / boost highs.
        - Nonlinear curve: extremes (full tilt) push harder than small tilts.
        - Asymmetry: low-band moves are larger than high-band (LOW_BOOST_FACTOR / HIGH_CUT_FACTOR).
        """
        roll_clamped = max(-self.MAX_ROLL_TIMBRE_DEG, min(self.MAX_ROLL_TIMBRE_DEG, roll_deg))
        raw_norm = roll_clamped / self.MAX_ROLL_TIMBRE_DEG  # -1..+1
        tilt_norm = np.tanh(raw_norm * 1.2)  # soft clipping at ends
        
        # Nonlinear: full tilt pushes harder (scale gain by 0.5 + 0.5*|tilt| so 100% tilt = full gain)
        tilt_scale = 0.5 + 0.5 * abs(tilt_norm)
        
        mid = (self.N_BANDS - 1) / 2.0
        gains_db = np.zeros(self.N_BANDS, dtype=np.float32)
        for i in range(self.N_BANDS):
            band_pos = (i - mid) / mid
            gain_db = self.MAX_GAIN_DB * (-tilt_norm) * band_pos * tilt_scale
            # Asymmetry: lows boost/cut more than highs
            if band_pos < 0:
                gain_db *= self.LOW_BOOST_FACTOR
            elif band_pos > 0:
                gain_db *= self.HIGH_CUT_FACTOR
            gains_db[i] = gain_db
        
        self.current_band_gains_db = gains_db
        return gains_db
    
    def gains_db_to_linear(self, gains_db: np.ndarray) -> np.ndarray:
        """Convert dB gains to linear multipliers."""
        return np.power(10.0, gains_db / 20.0, dtype=np.float32)
    
    def apply_motion_eq(self, block: np.ndarray, roll_deg: float) -> np.ndarray:
        """
        Apply the motion-controlled multi-band EQ to a 1D numpy audio block (mono).
        
        Uses FFT-based per-bin scaling with:
        - Nonlinear tanh mapping (in compute_band_gains_db)
        - Exponential smoothing of gains over time
        - Soft limiter to prevent clipping
        """
        # Ensure float32
        x = block.astype(np.float32, copy=False)
        
        # Compute raw band gains in dB
        raw_gains_db = self.compute_band_gains_db(roll_deg)
        
        # Smooth gains over time using exponential smoothing
        # smoothed = alpha * new + (1 - alpha) * old
        self.smoothed_gains_db = (
            self.EQ_SMOOTHING_ALPHA * raw_gains_db +
            (1.0 - self.EQ_SMOOTHING_ALPHA) * self.smoothed_gains_db
        )
        
        # Convert smoothed gains to linear
        gains_lin = self.gains_db_to_linear(self.smoothed_gains_db)
        
        # Get per-bin gain via precomputed band index
        bin_gains = gains_lin[self.band_index]
        
        # FFT
        X = np.fft.rfft(x)
        
        # Apply per-bin gains
        X_filtered = X * bin_gains
        
        # iFFT
        y = np.fft.irfft(X_filtered, n=self.AUDIO_BLOCK_SIZE).astype(np.float32)
        
        # Soft limiter: gentle compression above threshold
        threshold = 0.95  # Start limiting at 95% of full scale
        ratio = 0.3       # Compression ratio (gentle)
        
        abs_y = np.abs(y)
        over_threshold = abs_y > threshold
        
        if np.any(over_threshold):
            # Soft knee compression
            excess = abs_y - threshold
            compressed_excess = excess * ratio
            limited_abs = threshold + compressed_excess
            
            # Preserve sign and apply limiting
            y = np.sign(y) * np.minimum(abs_y, limited_abs)
        
        # Final safety: hard clip at ±1.0 if still needed
        y = np.clip(y, -1.0, 1.0)
        
        return y
    
    def start_audio(self):
        """Start the audio stream with file playback."""
        if self.audio_stream is not None:
            return  # Already started
        
        # Load audio file if not already loaded (lazy loading)
        if not self._audio_file_loaded:
            self._load_audio_file()
            self._audio_file_loaded = True
        
        if self.audio_data is None:
            print("Error: Audio file not loaded")
            return
        
        def audio_callback(outdata, frames, time_info, status):
            try:
                if status:
                    print("Audio status:", status)
                
                if self.audio_data is None:
                    outdata.fill(0)
                    return
                
                # Use current angles (updated by set_angles_for_audio)
                roll_deg = self.current_roll
                pitch_deg = self.current_pitch
                yaw_deg = self.current_yaw
                
                # --- Volume mapping: pitch -> volume in [0, 1] ---
                volume_norm = self.compute_volume_from_pitch(pitch_deg)
                
                # --- Pan mapping: yaw -> pan in [-1, 1] ---
                yaw_normalized = (yaw_deg - 180.0) / 180.0
                pan = max(-1.0, min(1.0, yaw_normalized))  # -1 = full left, +1 = full right
                
                # Read audio chunk from file (same as play-music.py)
                chunk = np.zeros(frames, dtype=np.float32)
                samples_read = 0
                
                while samples_read < frames:
                    remaining = frames - samples_read
                    available = len(self.audio_data) - self.audio_position
                    
                    if available > 0:
                        read_count = min(remaining, available)
                        chunk[samples_read:samples_read + read_count] = self.audio_data[
                            self.audio_position:self.audio_position + read_count
                        ]
                        self.audio_position += read_count
                        samples_read += read_count
                    
                    # Loop if we've reached the end
                    if self.audio_position >= len(self.audio_data):
                        self.audio_position = 0
                
                # Apply 7-band EQ (timbre controlled by roll)
                chunk = self.apply_motion_eq(chunk, roll_deg)
                
                # Apply volume (pitch-controlled)
                chunk *= volume_norm
                
                # Convert to stereo with panning (same approach as play-music.py but with panning)
                # DEBUG: Temporarily disable panning to match play-music.py exactly
                # left_gain = np.sqrt((1.0 - pan) / 2.0)
                # right_gain = np.sqrt((1.0 + pan) / 2.0)
                # outdata[:, 0] = chunk * left_gain   # left channel
                # outdata[:, 1] = chunk * right_gain  # right channel
                
                # Simple stereo output (matching play-music.py exactly)
                outdata[:, 0] = chunk
                outdata[:, 1] = chunk
                
            except Exception as e:
                print(f"Error in Proto G: Equalizer audio callback: {e}")
                import traceback
                traceback.print_exc()
                outdata.fill(0)
        
        try:
            self.audio_stream = sd.OutputStream(
                samplerate=self.AUDIO_SAMPLE_RATE,
                channels=2,
                blocksize=self.AUDIO_BLOCK_SIZE,
                callback=audio_callback,
            )
            self.audio_stream.start()
            print(f"Audio stream started successfully")
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            import traceback
            traceback.print_exc()
            self.audio_stream = None
    
    def stop_audio(self):
        """Stop the audio stream."""
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        self.audio_position = 0
    
    def set_angles_for_audio(self, roll_deg: float, pitch_deg: float, yaw_deg: float):
        """Update angles for audio generation.
        
        Args:
            roll_deg: Roll angle in degrees (controls 7-band EQ timbre)
            pitch_deg: Pitch angle in degrees (controls volume)
            yaw_deg: Yaw angle in degrees (controls panning, 0-360°)
        """
        self.current_roll = roll_deg
        self.current_pitch = pitch_deg
        self.current_yaw = yaw_deg
        
        # Compute EQ gains for display (this also updates self.current_band_gains_db)
        self.compute_band_gains_db(roll_deg)
        
        # Compute volume for display
        self.compute_volume_from_pitch(pitch_deg)
    
    def _update_display(self):
        """Update the display bars (called periodically)."""
        self.update()  # Trigger repaint
    
    def paintEvent(self, event):
        """Paint 7-band EQ bars and Volume bar."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        widget_width = self.width()
        widget_height = self.height()
        
        # Draw 7-band EQ bars in center area
        self._draw_eq_bars(painter, widget_width, widget_height)
        
        # Draw Volume bar at the bottom
        self._draw_control_bars(painter, widget_width, widget_height)
    
    def _draw_eq_bars(self, painter, widget_width, widget_height):
        """Draw 7-band EQ bars in the center area."""
        # Calculate available space (excluding volume bar at bottom)
        eq_area_top = 20
        eq_area_bottom = widget_height - self.USER_VOLUME_INDICATOR_HEIGHT - 20
        eq_area_height = eq_area_bottom - eq_area_top
        
        # Bar dimensions
        n_bars = self.N_BANDS
        bar_spacing = 10
        bar_width = (widget_width - (n_bars + 1) * bar_spacing) // n_bars
        bar_max_height = eq_area_height - 60  # Leave room for labels
        
        # Center the bars horizontally
        total_width = n_bars * bar_width + (n_bars - 1) * bar_spacing
        start_x = (widget_width - total_width) // 2
        
        # Band labels
        band_labels = ["Sub", "Bass", "LoMid", "Mid", "UpMid", "Pres", "Brill"]
        
        # Draw each bar
        for i in range(n_bars):
            bar_x = start_x + i * (bar_width + bar_spacing)
            bar_center_y = eq_area_top + eq_area_height // 2
            
            # Calculate bar height from gain (dB to normalized height)
            gain_db = self.current_band_gains_db[i]
            # Normalize: -MAX_GAIN_DB to +MAX_GAIN_DB -> -1 to +1
            normalized = gain_db / self.MAX_GAIN_DB
            normalized = max(-1.0, min(1.0, normalized))
            
            # Bar height as fraction of max height
            bar_height_frac = abs(normalized)
            bar_height = bar_height_frac * bar_max_height // 2
            
            # Draw bar background (gray)
            painter.setBrush(QColor("#ecf0f1"))
            painter.setPen(QPen(QColor("#bdc3c7"), 1))
            painter.drawRect(bar_x, bar_center_y - bar_max_height // 2, bar_width, bar_max_height)
            
            # Draw center line (0 dB reference)
            painter.setPen(QPen(QColor("#7f8c8d"), 1, Qt.DashLine))
            painter.drawLine(bar_x, bar_center_y, bar_x + bar_width, bar_center_y)
            
            # Draw gain bar (green for boost, red for cut)
            if gain_db > 0.1:  # Boost
                fill_color = QColor("#2ecc71")  # Green
                bar_y = bar_center_y - int(bar_height)
                bar_h = int(bar_height)
            elif gain_db < -0.1:  # Cut
                fill_color = QColor("#e74c3c")  # Red
                bar_y = bar_center_y
                bar_h = int(bar_height)
            else:  # Flat (near 0 dB)
                fill_color = QColor("#95a5a6")  # Gray
                bar_y = bar_center_y
                bar_h = 1
            
            painter.setBrush(fill_color)
            painter.setPen(QPen(fill_color.darker(120), 1))
            painter.drawRect(bar_x, bar_y, bar_width, bar_h)
            
            # Draw band label below bar
            painter.setPen(QColor("#2c3e50"))
            painter.setFont(QFont("Arial", 9))
            label_text = band_labels[i]
            label_rect = painter.fontMetrics().boundingRect(label_text)
            label_x = bar_x + (bar_width - label_rect.width()) // 2
            label_y = bar_center_y + bar_max_height // 2 + 15
            painter.drawText(label_x, label_y, label_text)
            
            # Draw gain value (dB) above bar
            gain_text = f"{gain_db:+.1f}dB"
            gain_rect = painter.fontMetrics().boundingRect(gain_text)
            gain_x = bar_x + (bar_width - gain_rect.width()) // 2
            gain_y = bar_center_y - bar_max_height // 2 - 5
            painter.setFont(QFont("Arial", 8))
            painter.drawText(gain_x, gain_y, gain_text)
    
    def _draw_control_bars(self, painter, widget_width, widget_height):
        """Draw Volume bar (pitch-controlled, IMU-only) at the bottom.
        
        Note: This is independent from other methods - Proto G: Equalizer has its own bar drawing.
        Volume is controlled by pitch angle only, not user-clickable.
        """
        bar_area_y = widget_height - self.USER_VOLUME_INDICATOR_HEIGHT
        bar_height = 20
        label_width = 80
        value_width = 60
        bar_x = label_width
        bar_width = widget_width - bar_x - value_width - 20
        
        # Volume bar (pitch-controlled, read-only)
        vol_y = bar_area_y + 10
        self._draw_single_bar(painter, bar_x, vol_y, bar_width, bar_height,
                             "Volume:", self.current_volume_norm, 0.0, 1.0,
                             widget_width, value_width, "#3498db", False)
    
    def _draw_single_bar(self, painter, bar_x, bar_y, bar_width, bar_height,
                        label, value, min_val, max_val, widget_width, value_width,
                        fill_color, is_clickable):
        """Draw a single control bar with label and value."""
        # Draw background for bar area
        if is_clickable:
            painter.fillRect(0, bar_y - 5, widget_width, bar_height + 10, QColor("#f5f5f5"))
        
        # Draw label
        painter.setPen(QColor("#333333"))
        painter.setFont(QFont("Arial", 10))
        label_rect = painter.fontMetrics().boundingRect(label)
        painter.drawText(10, bar_y + bar_height // 2 + label_rect.height() // 2 - 2, label)
        
        # Calculate fill percentage
        if max_val > min_val:
            percent = ((value - min_val) / (max_val - min_val)) * 100.0
        else:
            percent = 0.0
        percent = max(0.0, min(100.0, percent))
        
        # Draw bar background
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#ccc"))
        painter.drawRoundedRect(bar_x, bar_y, bar_width, bar_height, 3, 3)
        
        # Draw bar fill
        fill_width = int((percent / 100.0) * bar_width)
        if fill_width > 0:
            painter.setBrush(QColor(fill_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar_x, bar_y, fill_width, bar_height, 3, 3)
        
        # Draw value
        value_text = f"{percent:.1f}%"
        value_rect = painter.fontMetrics().boundingRect(value_text)
        value_x = widget_width - value_width
        value_y = bar_y + bar_height // 2 + value_rect.height() // 2 - 2
        painter.setPen(QColor("#333333"))
        painter.drawText(value_x, value_y, value_text)
    
    # No mousePressEvent needed - volume is IMU-controlled only


# --- Music in Motion (body/pose → equalizer) tab: arm height bars + 7-band EQ display ---
N_BANDS_BODY = 7
MAX_GAIN_DB_BODY = 12.0  # Match Proto G; ±12 dB makes arm-driven EQ clearly audible on a full mix
# Same band edges and audio config as Proto G (IMU Pipeline Equalizer)
BODY_EQ_BAND_EDGES = [
    (20, 60), (60, 250), (250, 500), (500, 2000),
    (2000, 4000), (4000, 6000), (6000, 20000),
]
BODY_AUDIO_SAMPLE_RATE = 44100
BODY_AUDIO_BLOCK_SIZE = 2048  # Same as Proto G: ~21.5 Hz bin spacing for meaningful 7-band EQ
BODY_AUDIO_FILE = "music/music.mp3"
BODY_EQ_SMOOTHING_ALPHA = 0.15
# Elbow bend → 3-band block shape (TICKET-MMM-EQUALIZER)
THETA_EXT = 165.0   # straight arm (degrees)
THETA_BENT = 70.0   # bent arm (degrees)


class ArmHeightBarsWidget(QWidget):
    """
    Four bars: left/right arm height (half width each) and left/right elbow bend.
    Row 1: Left arm, Right arm. Row 2: Left elbow, Right elbow.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        self.setMinimumWidth(280)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background-color: #f0f0f0;")
        self.left_arm_height = 0.0
        self.right_arm_height = 0.0
        self.left_elbow_bend = 0.0
        self.right_elbow_bend = 0.0

    def update_data(self, left_arm_height, right_arm_height, left_elbow_bend=0.0, right_elbow_bend=0.0):
        self.left_arm_height = left_arm_height
        self.right_arm_height = right_arm_height
        self.left_elbow_bend = left_elbow_bend
        self.right_elbow_bend = right_elbow_bend
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(240, 240, 240))
        label_w = 88
        # Two columns: each bar gets half of (width - labels - margins)
        bar_total_w = w - label_w - 24
        bar_half_w = max(20, bar_total_w // 2 - 8)
        bar_h = 20
        y1, y2 = 16, 16 + bar_h + 14
        col1_x = label_w + 10
        col2_x = label_w + 10 + bar_half_w + 12

        painter.setFont(QFont("Arial", 9, QFont.Bold))
        painter.setPen(QColor(50, 50, 50))
        painter.drawText(6, y1 + bar_h // 2 - 7, label_w - 6, 18, Qt.AlignRight | Qt.AlignVCenter, "L arm:")
        painter.drawText(6, y2 + bar_h // 2 - 7, label_w - 6, 18, Qt.AlignRight | Qt.AlignVCenter, "L elbow:")
        # Right column labels (same row indices)
        painter.drawText(col2_x + bar_half_w + 2, y1 + bar_h // 2 - 7, 50, 18, Qt.AlignLeft | Qt.AlignVCenter, "R arm")
        painter.drawText(col2_x + bar_half_w + 2, y2 + bar_h // 2 - 7, 50, 18, Qt.AlignLeft | Qt.AlignVCenter, "R elbow")

        # Left arm, Right arm (row 1)
        for (x, val), color in [
            ((col1_x, self.left_arm_height), QColor(52, 152, 219)),
            ((col2_x, self.right_arm_height), QColor(52, 152, 219)),
        ]:
            painter.setPen(QPen(QColor(180, 180, 180), 1))
            painter.drawRect(x, y1, bar_half_w, bar_h)
            fill_w = max(0, int(bar_half_w * max(0, min(1, val))))
            if fill_w > 0:
                painter.fillRect(x, y1, fill_w, bar_h, color)
        # Left elbow, Right elbow (row 2)
        for (x, val), color in [
            ((col1_x, self.left_elbow_bend), QColor(155, 89, 182)),
            ((col2_x, self.right_elbow_bend), QColor(155, 89, 182)),
        ]:
            painter.setPen(QPen(QColor(180, 180, 180), 1))
            painter.drawRect(x, y2, bar_half_w, bar_h)
            fill_w = max(0, int(bar_half_w * max(0, min(1, val))))
            if fill_w > 0:
                painter.fillRect(x, y2, fill_w, bar_h, color)
        painter.end()


class BodyEqBarsWidget(QWidget):
    """7-band EQ bar display (pose-driven gains)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background-color: #f0f0f0;")
        self.gains_db = np.zeros(N_BANDS_BODY, dtype=np.float32)

    def update_data(self, gains_db):
        self.gains_db = np.asarray(gains_db, dtype=np.float32).copy()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(240, 240, 240))
        bar_w = max(8, int((w - 40) / (N_BANDS_BODY + 1)) * 4 // 4)
        gap = max(2, (w - N_BANDS_BODY * bar_w) // (N_BANDS_BODY + 1))
        start_x = (w - (N_BANDS_BODY * bar_w + (N_BANDS_BODY - 1) * gap)) // 2
        bar_h = h - 36
        zero_y = h - 28 - bar_h // 2
        for i in range(N_BANDS_BODY):
            x = start_x + i * (bar_w + gap)
            g = self.gains_db[i]
            g_norm = max(-1, min(1, g / MAX_GAIN_DB_BODY))
            fill_h = int(abs(g_norm) * bar_h * 0.5)
            if g_norm >= 0:
                by = zero_y - fill_h
            else:
                by = zero_y
            color = QColor(0, 200, 0) if g_norm >= 0 else QColor(200, 0, 0)
            painter.fillRect(int(x), int(by), bar_w, fill_h, color)
            painter.setPen(QPen(QColor(100, 100, 100), 1))
            painter.drawRect(int(x), zero_y - bar_h // 2, bar_w, bar_h // 2)
            painter.setPen(QColor(50, 50, 50))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(int(x), h - 22, bar_w, 16, Qt.AlignCenter, f"{g:.1f}")
        painter.end()


class BodyMotionEqualizerWidget(QWidget):
    """
    Music in Motion tab: full-body (arm height) controls equalizer.
    Camera + MediaPipe Pose → left/right arm height → 7-band EQ.
    Plays music/music.mp3 (same as Proto G) with pose-driven EQ.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cap = None
        self.pose = None
        self.pose_timer = None
        self.camera_blackout = True
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        # Smoothed arm heights [0, 1]
        self.left_arm_height = 0.5
        self.right_arm_height = 0.5
        self._smooth_alpha = 0.2
        # Smoothed elbow bend [0, 1] for 3-band block shaping (TICKET-MMM-EQUALIZER)
        self.left_elbow_bend = 0.0
        self.right_elbow_bend = 0.0
        # Audio (same file as Proto G)
        self.audio_stream = None
        self.audio_data = None
        self.audio_sample_rate = None
        self.audio_position = 0
        self._audio_file_loaded = False
        self._current_gains_db = np.zeros(N_BANDS_BODY, dtype=np.float32)
        self._smoothed_gains_db = np.zeros(N_BANDS_BODY, dtype=np.float32)
        self._band_index = None  # built on first audio start
        self._init_ui()
        self._init_pose_detector()

    def _init_pose_detector(self):
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def _angle_deg(self, a, b, c):
        """Angle ABC at vertex b in degrees (a, b, c are landmarks with .x, .y)."""
        v1 = (a.x - b.x, a.y - b.y)
        v2 = (c.x - b.x, c.y - b.y)
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        mag1 = math.hypot(*v1)
        mag2 = math.hypot(*v2)
        if mag1 < 1e-6 or mag2 < 1e-6:
            return 180.0
        cos_theta = max(-1.0, min(1.0, dot / (mag1 * mag2)))
        return math.degrees(math.acos(cos_theta))

    def _load_audio_file(self):
        """Load music file (same as Proto G: music/music.mp3)."""
        try:
            import librosa
            audio_path = Path(BODY_AUDIO_FILE)
            if not audio_path.exists():
                print(f"Warning: Audio file not found: {BODY_AUDIO_FILE}")
                return
            self.audio_data, self.audio_sample_rate = librosa.load(
                str(audio_path), sr=BODY_AUDIO_SAMPLE_RATE, mono=True
            )
            print(f"Music in Motion: loaded {BODY_AUDIO_FILE} ({len(self.audio_data)} samples)")
        except Exception as e:
            print(f"Error loading audio for Music in Motion: {e}")
            self.audio_data = None

    def _build_band_index(self):
        """Precompute FFT bin -> band index (same bands as Proto G)."""
        freqs = np.fft.rfftfreq(BODY_AUDIO_BLOCK_SIZE, d=1.0 / BODY_AUDIO_SAMPLE_RATE)
        band_index = np.zeros_like(freqs, dtype=np.int32)
        for k, f in enumerate(freqs):
            idx = 0
            for band_i, (low, high) in enumerate(BODY_EQ_BAND_EDGES):
                if low <= f < high:
                    idx = band_i
                    break
                if f >= BODY_EQ_BAND_EDGES[-1][1]:
                    idx = len(BODY_EQ_BAND_EDGES) - 1
                    break
            band_index[k] = idx
        return band_index

    def _apply_eq_to_block(self, block, gains_db):
        """Apply 7-band EQ to a mono float32 block (arm-height-driven gains)."""
        x = block.astype(np.float32, copy=False)
        self._smoothed_gains_db = (
            BODY_EQ_SMOOTHING_ALPHA * gains_db + (1.0 - BODY_EQ_SMOOTHING_ALPHA) * self._smoothed_gains_db
        )
        gains_lin = np.power(10.0, self._smoothed_gains_db / 20.0).astype(np.float32)
        bin_gains = gains_lin[self._band_index]
        X = np.fft.rfft(x)
        X_filtered = X * bin_gains
        y = np.fft.irfft(X_filtered, n=BODY_AUDIO_BLOCK_SIZE).astype(np.float32)
        y = np.clip(y, -1.0, 1.0)
        return y

    def _start_audio(self):
        """Start playback of music/music.mp3 with pose-driven EQ."""
        if self.audio_stream is not None:
            return
        if not self._audio_file_loaded:
            self._load_audio_file()
            self._audio_file_loaded = True
        if self.audio_data is None:
            return
        if self._band_index is None:
            self._band_index = self._build_band_index()

        def audio_callback(outdata, frames, time_info, status):
            try:
                if status:
                    print("Music in Motion audio status:", status)
                if self.audio_data is None:
                    outdata.fill(0)
                    return
                gains = self._current_gains_db.copy()
                chunk = np.zeros(frames, dtype=np.float32)
                samples_read = 0
                while samples_read < frames:
                    remaining = frames - samples_read
                    available = len(self.audio_data) - self.audio_position
                    if available > 0:
                        read_count = min(remaining, available)
                        chunk[samples_read:samples_read + read_count] = self.audio_data[
                            self.audio_position:self.audio_position + read_count
                        ]
                        self.audio_position += read_count
                        samples_read += read_count
                    if self.audio_position >= len(self.audio_data):
                        self.audio_position = 0
                chunk = self._apply_eq_to_block(chunk, gains)
                outdata[:, 0] = chunk
                outdata[:, 1] = chunk
            except Exception as e:
                print(f"Music in Motion audio callback error: {e}")
                outdata.fill(0)

        try:
            self.audio_stream = sd.OutputStream(
                samplerate=BODY_AUDIO_SAMPLE_RATE,
                channels=2,
                blocksize=BODY_AUDIO_BLOCK_SIZE,
                callback=audio_callback,
            )
            self.audio_stream.start()
        except Exception as e:
            print(f"Music in Motion: error starting audio: {e}")
            self.audio_stream = None

    def _stop_audio(self):
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        self.audio_position = 0

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.start_button = QPushButton("Start")
        self.start_button.setFont(QFont("Arial", 12))
        self.start_button.setStyleSheet("""
            QPushButton { background-color: #3498db; color: white; border: none;
                padding: 10px 25px; border-radius: 5px; font-weight: bold; }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.start_button.clicked.connect(self._toggle_pose)
        top_bar.addWidget(self.start_button)
        layout.addLayout(top_bar)
        content = QHBoxLayout()
        content.setSpacing(20)
        self.arm_bars = ArmHeightBarsWidget()
        self.eq_bars = BodyEqBarsWidget()
        content.addWidget(self.arm_bars)
        content.addWidget(self.eq_bars)
        layout.addLayout(content)
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 360)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setStyleSheet("background-color: black; border-radius: 10px;")
        layout.addWidget(self.video_label, 1)
        self._pose_running = False

    def _toggle_pose(self):
        if self._pose_running:
            self._stop_pose()
        else:
            self._start_pose()

    def _start_pose(self):
        if not self.camera_blackout and (self.cap is None or not self.cap.isOpened()):
            self.cap = cv2.VideoCapture(0)
        if self.pose_timer is None:
            self.pose_timer = QTimer(self)
            self.pose_timer.timeout.connect(self._update_pose)
        self.pose_timer.start(33)
        self._pose_running = True
        self._start_audio()
        self.start_button.setText("Stop")
        self.start_button.setStyleSheet("""
            QPushButton { background-color: #e74c3c; color: white; border: none;
                padding: 10px 25px; border-radius: 5px; font-weight: bold; }
            QPushButton:hover { background-color: #c0392b; }
        """)

    def _stop_pose(self):
        if self.pose_timer:
            self.pose_timer.stop()
        self._stop_audio()
        self._pose_running = False
        self.start_button.setText("Start")
        self.start_button.setStyleSheet("""
            QPushButton { background-color: #3498db; color: white; border: none;
                padding: 10px 25px; border-radius: 5px; font-weight: bold; }
            QPushButton:hover { background-color: #2980b9; }
        """)

    def _update_pose(self):
        if self.camera_blackout:
            black = QPixmap(max(1, self.video_label.width()), max(1, self.video_label.height()))
            black.fill(QColor(0, 0, 0))
            self.video_label.setPixmap(black)
            self.arm_bars.update_data(
                self.left_arm_height, self.right_arm_height,
                self.left_elbow_bend, self.right_elbow_bend
            )
            self._update_eq_from_arms()
            return
        if not self.cap or not self.cap.isOpened():
            return
        ok, frame = self.cap.read()
        if not ok:
            return
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        left_val, right_val = None, None
        if self.pose:
            results = self.pose.process(frame_rgb)
            if results.pose_landmarks:
                self.mp_drawing.draw_landmarks(
                    frame_rgb, results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=self.mp_drawing_styles.get_default_pose_landmarks_style(),
                )
                lm = results.pose_landmarks.landmark
                left_wrist = lm[self.mp_pose.PoseLandmark.LEFT_WRIST.value]
                right_wrist = lm[self.mp_pose.PoseLandmark.RIGHT_WRIST.value]
                left_val = 1.0 - left_wrist.y
                right_val = 1.0 - right_wrist.y
                # Elbow bend for 3-band block shaping (TICKET-MMM-EQUALIZER)
                left_shoulder = lm[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
                left_elbow = lm[self.mp_pose.PoseLandmark.LEFT_ELBOW.value]
                right_shoulder = lm[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
                right_elbow = lm[self.mp_pose.PoseLandmark.RIGHT_ELBOW.value]
                left_angle = self._angle_deg(left_shoulder, left_elbow, left_wrist)
                right_angle = self._angle_deg(right_shoulder, right_elbow, right_wrist)
                # Normalize: straight ~165° -> 0, bent ~70° -> 1
                def _bend_norm(angle):
                    val = (THETA_EXT - angle) / (THETA_EXT - THETA_BENT)
                    return max(0.0, min(1.0, val))
                left_bend = _bend_norm(left_angle) ** 1.5
                right_bend = _bend_norm(right_angle) ** 1.5
                alpha = 0.2
                self.left_elbow_bend = alpha * left_bend + (1 - alpha) * self.left_elbow_bend
                self.right_elbow_bend = alpha * right_bend + (1 - alpha) * self.right_elbow_bend
        if left_val is not None and right_val is not None:
            self.left_arm_height = self._smooth_alpha * left_val + (1 - self._smooth_alpha) * self.left_arm_height
            self.right_arm_height = self._smooth_alpha * right_val + (1 - self._smooth_alpha) * self.right_arm_height
        self.arm_bars.update_data(
            self.left_arm_height, self.right_arm_height,
            self.left_elbow_bend, self.right_elbow_bend
        )
        self._update_eq_from_arms()
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_bgr.shape
        qimg = QImage(frame_bgr.data, w, h, ch * w, QImage.Format_RGB888).rgbSwapped()
        scaled = qimg.scaled(self.video_label.width(), self.video_label.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video_label.setPixmap(QPixmap.fromImage(scaled))

    def _update_eq_from_arms(self):
        """
        Map arm heights + elbow bend to 7-band EQ (TICKET-MMM-EQUALIZER).
        Wrist height -> overall gain of 3-band block; elbow bend -> distribution + strong
        boost to extreme bands. When elbow bars > 50%, lowest (band 0) and highest (band 6)
        are driven to or near peak (MAX_GAIN_DB_BODY).
        """
        left_norm = max(0.0, min(1.0, self.left_arm_height))
        right_norm = max(0.0, min(1.0, self.right_arm_height))
        G_left = MAX_GAIN_DB_BODY * (left_norm - 0.5) * 2.0
        G_right = MAX_GAIN_DB_BODY * (right_norm - 0.5) * 2.0
        shape_left = (self.left_elbow_bend - 0.5) * 2.0
        shape_right = (self.right_elbow_bend - 0.5) * 2.0

        # When elbow > 50%, drive extreme bands to peak (steep: 75% elbow -> near full boost)
        elbow_scale_left = max(0.0, min(1.0, (self.left_elbow_bend - 0.5) * 4.0))
        elbow_scale_right = max(0.0, min(1.0, (self.right_elbow_bend - 0.5) * 4.0))
        elbow_boost_low = elbow_scale_left * MAX_GAIN_DB_BODY   # band 0
        elbow_boost_high = elbow_scale_right * MAX_GAIN_DB_BODY  # band 6

        gains_db = np.zeros(N_BANDS_BODY, dtype=np.float32)

        # Low block (bands 0-2)
        w_center = 1.0
        w_edge = 0.6 + 0.8 * abs(shape_left)
        if shape_left >= 0:
            w0, w1, w2 = w_edge, w_center, 0.6
        else:
            w0, w1, w2 = 0.6, w_center, w_edge
        norm = w0 + w1 + w2
        w0, w1, w2 = w0 / norm, w1 / norm, w2 / norm
        gains_db[0] = G_left * w0 + elbow_boost_low
        gains_db[1] = G_left * w1
        gains_db[2] = G_left * w2

        # Mid band (3)
        gains_db[3] = 0.0

        # High block (bands 4-6)
        w_center = 1.0
        w_edge = 0.6 + 0.8 * abs(shape_right)
        if shape_right >= 0:
            w4, w5, w6 = 0.6, w_center, w_edge
        else:
            w4, w5, w6 = w_edge, w_center, 0.6
        norm = w4 + w5 + w6
        w4, w5, w6 = w4 / norm, w5 / norm, w6 / norm
        gains_db[4] = G_right * w4
        gains_db[5] = G_right * w5
        gains_db[6] = G_right * w6 + elbow_boost_high

        # Clamp so display and audio stay in range
        gains_db[:] = np.clip(gains_db, -MAX_GAIN_DB_BODY, MAX_GAIN_DB_BODY)

        self._current_gains_db = gains_db
        self.eq_bars.update_data(gains_db)

    def set_camera_blackout(self, blackout: bool):
        self.camera_blackout = blackout
        if blackout and self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None
        elif not blackout and (self.cap is None or not self.cap.isOpened()) and self._pose_running:
            self.cap = cv2.VideoCapture(0)

    def cleanup(self):
        self._stop_pose()
        self._stop_audio()
        if self.pose:
            self.pose.close()
            self.pose = None
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None

    def resume(self):
        if not self.camera_blackout and self._pose_running:
            if self.cap is None or not self.cap.isOpened():
                self.cap = cv2.VideoCapture(0)
            if self.pose_timer:
                self.pose_timer.start(33)
        if not self.pose:
            self._init_pose_detector()


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


class MusicInMotionWidget(QWidget):
    """Music in Motion widget with IMU integration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.imu_reader = None
        self.imu_reader2 = None  # Second IMU reader for Proto E: Dualing IMUs
        self.imu_enabled = False
        self.imu_timer = None
        
        # Read default mode from .imuconfig
        from imu_viewer.config_loader import load_config
        config = load_config()
        default_mode = config.get("mode", "usb").lower()
        # Map config mode to internal mode string
        if default_mode == "usb":
            self.imu_mode = "USB"
        elif default_mode == "ap":
            self.imu_mode = "WIFI_AP"
        elif default_mode == "sta":
            self.imu_mode = "WIFI_STA"
        else:
            self.imu_mode = "USB"  # Fallback to USB
        
        self.method = "Prototype A"  # "Prototype A", "Prototype B", or "Proto C: Pitch + Pan"
        # Calibration values for Prototype A
        self.zero_roll = 0.0
        self.zero_pitch = 0.0
        self.calibrated = False
        # Angle limits for position mapping (in degrees)
        self.max_roll_deg = 45.0
        self.max_pitch_deg = 45.0
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Top bar with method selector, mode selection and IMU toggle
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        
        # Method selector dropdown
        self.method_combo = QComboBox()
        self.method_combo.addItem("Prototype A")
        self.method_combo.addItem("Prototype B")
        self.method_combo.addItem("Proto C: Pitch + Pan")
        self.method_combo.addItem("Proto D: Pitch+Pan+Vol")
        self.method_combo.addItem("Proto E: Dualing IMUs")
        self.method_combo.addItem("Proto F: Pitch+Timbre")
        self.method_combo.addItem("Proto G: Equalizer")
        self.method_combo.setFont(QFont("Arial", 11))
        self.method_combo.setCurrentIndex(0)  # Default to Prototype A
        self.method_combo.currentTextChanged.connect(self._on_method_changed)
        top_bar.addWidget(self.method_combo)
        
        # Help button for Prototype A (only visible when Prototype A is selected)
        self.method_a_help_button = QPushButton("?")
        self.method_a_help_button.setFont(QFont("Arial", 12, QFont.Bold))
        self.method_a_help_button.setFixedSize(25, 25)
        self.method_a_help_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
        self.method_a_help_button.setToolTip("Help for Prototype A")
        self.method_a_help_button.clicked.connect(self._show_method_a_help)
        self.method_a_help_button.setVisible(self.method == "Prototype A")
        top_bar.addWidget(self.method_a_help_button)
        
        # Help button for Prototype B (only visible when Prototype B is selected)
        self.method_b_help_button = QPushButton("?")
        self.method_b_help_button.setFont(QFont("Arial", 12, QFont.Bold))
        self.method_b_help_button.setFixedSize(25, 25)
        self.method_b_help_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
        self.method_b_help_button.setToolTip("Help for Prototype B")
        self.method_b_help_button.clicked.connect(self._show_method_b_help)
        self.method_b_help_button.setVisible(self.method == "Prototype B")
        top_bar.addWidget(self.method_b_help_button)
        
        # Add some spacing
        top_bar.addSpacing(15)
        
        # Mode selection radio buttons
        self.mode_button_group = QButtonGroup(self)
        
        self.usb_radio = QRadioButton("USB")
        self.usb_radio.setChecked(self.imu_mode == "USB")
        self.usb_radio.setFont(QFont("Arial", 11))
        self.usb_radio.toggled.connect(self._on_mode_changed)
        self.mode_button_group.addButton(self.usb_radio, 0)
        top_bar.addWidget(self.usb_radio)
        
        self.wifi_ap_radio = QRadioButton("WiFi AP")
        self.wifi_ap_radio.setChecked(self.imu_mode == "WIFI_AP")
        self.wifi_ap_radio.setFont(QFont("Arial", 11))
        self.wifi_ap_radio.toggled.connect(self._on_mode_changed)
        self.mode_button_group.addButton(self.wifi_ap_radio, 1)
        top_bar.addWidget(self.wifi_ap_radio)
        
        self.wifi_sta_radio = QRadioButton("WiFi STA")
        self.wifi_sta_radio.setChecked(self.imu_mode == "WIFI_STA")
        self.wifi_sta_radio.setFont(QFont("Arial", 11))
        self.wifi_sta_radio.toggled.connect(self._on_mode_changed)
        self.mode_button_group.addButton(self.wifi_sta_radio, 2)
        top_bar.addWidget(self.wifi_sta_radio)
        
        # Add some spacing
        top_bar.addSpacing(20)
        
        # Calibrate button (only visible for Prototype A)
        self.calibrate_button = QPushButton("Calibrate")
        self.calibrate_button.setFont(QFont("Arial", 11))
        self.calibrate_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:pressed {
                background-color: #7d3c98;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #7f8c8d;
            }
        """)
        self.calibrate_button.clicked.connect(self._on_calibrate)
        self.calibrate_button.setEnabled(False)  # Disabled until IMU is running
        top_bar.addWidget(self.calibrate_button)
        
        # Add some spacing
        top_bar.addSpacing(15)
        
        self.imu_toggle_button = QPushButton("Start")
        self.imu_toggle_button.setFont(QFont("Arial", 12))
        self.imu_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
        self.imu_toggle_button.clicked.connect(self._toggle_imu)
        top_bar.addWidget(self.imu_toggle_button)
        
        main_layout.addLayout(top_bar)
        
        # Main content area: Stats on left, visualization in center, stats on right (for Proto E: Dualing IMUs)
        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(20)
        
        # Left side: IMU stats (IMU 1)
        self.imu_stats_widget = ImuStatsWidget()
        self.content_layout.addWidget(self.imu_stats_widget)
        
        # Center: IMU visualization area (Prototype A - box widget)
        self.imu_box_widget = ImuBoxWidget()
        self.content_layout.addWidget(self.imu_box_widget, 1)  # Give it stretch factor
        
        # Right side: Prototype B - blue square widget (matching imu_tkinter.py)
        self.imu_square_widget = ImuSquareWidget()
        self.imu_square_widget.hide()  # Hidden by default (Prototype A is active)
        self.content_layout.addWidget(self.imu_square_widget, 1)  # Give it stretch factor
        
        # Right side: Proto C: Pitch + Pan - blue square widget with audio (matching imu_tkintersound.py)
        self.imu_square_sound_widget = ImuSquareSoundWidget()
        self.imu_square_sound_widget.hide()  # Hidden by default (Prototype A is active)
        self.content_layout.addWidget(self.imu_square_sound_widget, 1)  # Give it stretch factor
        
        # Right side: Proto D: Pitch+Pan+Vol - blue square widget with audio + motion-dependent loudness
        self.imu_square_sound_loudness_widget = ImuSquareSoundLoudnessWidget()
        self.imu_square_sound_loudness_widget.hide()  # Hidden by default (Prototype A is active)
        self.content_layout.addWidget(self.imu_square_sound_loudness_widget, 1)  # Give it stretch factor
        
        # Proto E: Dualing IMUs - dual square widget (blue and red)
        self.imu_dual_square_widget = ImuDualSquareWidget()
        self.imu_dual_square_widget.hide()  # Hidden by default (Prototype A is active)
        self.content_layout.addWidget(self.imu_dual_square_widget, 1)  # Give it stretch factor
        
        # Proto F: Pitch+Timbre - square widget with timbre control (roll → timbre, yaw → pan)
        self.imu_square_sound_timbre_widget = ImuSquareSoundTimbreWidget()
        self.imu_square_sound_timbre_widget.hide()  # Hidden by default (Prototype A is active)
        self.content_layout.addWidget(self.imu_square_sound_timbre_widget, 1)  # Give it stretch factor
        
        # Proto G: Equalizer - square widget with audio file playback (roll → volume, pitch → timbre)
        self.imu_square_sound_file_widget = ImuSquareSoundFileWidget()
        self.imu_square_sound_file_widget.hide()  # Hidden by default (Prototype A is active)
        self.content_layout.addWidget(self.imu_square_sound_file_widget, 1)  # Give it stretch factor
        
        # Right side: IMU stats (IMU 2) - only visible for Proto E: Dualing IMUs
        self.imu_stats_widget2 = ImuStatsWidget()
        self.imu_stats_widget2.hide()  # Hidden by default
        self.content_layout.addWidget(self.imu_stats_widget2)
        
        main_layout.addLayout(self.content_layout, 1)  # Give content area stretch
        
    def _on_method_changed(self, method_text):
        """Handle method selector change."""
        # Stop audio if switching away from audio methods
        if self.method == "Proto C: Pitch + Pan" and method_text != "Proto C: Pitch + Pan":
            self.imu_square_sound_widget.stop_audio()
        if self.method == "Proto D: Pitch+Pan+Vol" and method_text != "Proto D: Pitch+Pan+Vol":
            self.imu_square_sound_loudness_widget.stop_audio()
        if self.method == "Proto F: Pitch+Timbre" and method_text != "Proto F: Pitch+Timbre":
            self.imu_square_sound_timbre_widget.stop_audio()
        if self.method == "Proto G: Equalizer" and method_text != "Proto G: Equalizer":
            self.imu_square_sound_file_widget.stop_audio()
        
        self.method = method_text
        
        if method_text == "Prototype A":
            # Show box widget, hide square widgets
            self.imu_box_widget.show()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.hide()
            # Hide second stats widget
            self.imu_stats_widget2.hide()
            # Enable calibrate button if IMU is running
            self.calibrate_button.setEnabled(self.imu_enabled)
            # Show help button for Prototype A, hide Prototype B help button
            self.method_a_help_button.setVisible(True)
            self.method_b_help_button.setVisible(False)
        elif method_text == "Prototype B":
            # Hide help button for other methods, show Prototype B help button
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(True)
            # Hide box widget, show square widget (no audio)
            self.imu_box_widget.hide()
            self.imu_square_widget.show()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.hide()
            # Hide second stats widget
            self.imu_stats_widget2.hide()
            # Disable calibrate button for Prototype B (no calibration needed)
            self.calibrate_button.setEnabled(False)
            # Reset square to center when switching to Prototype B
            self.imu_square_widget.set_square_position(0.5, 0.5)
        elif method_text == "Proto C: Pitch + Pan":
            # Hide help buttons for other methods
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            # Hide box widget, show square sound widget (with audio)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.show()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.hide()
            # Hide second stats widget
            self.imu_stats_widget2.hide()
            # Disable calibrate button for Proto C: Pitch + Pan (no calibration needed)
            self.calibrate_button.setEnabled(False)
            # Reset square to center when switching to Proto C: Pitch + Pan
            self.imu_square_sound_widget.set_square_position(0.5, 0.5)
            # Start audio if IMU is running
            if self.imu_enabled:
                self.imu_square_sound_widget.start_audio()
        elif method_text == "Proto D: Pitch+Pan+Vol":
            # Hide help buttons for other methods
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            # Hide box widget, show square sound loudness widget (with audio + motion loudness)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.show()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.hide()
            # Hide second stats widget
            self.imu_stats_widget2.hide()
            # Disable calibrate button for Proto D: Pitch+Pan+Vol (no calibration needed)
            self.calibrate_button.setEnabled(False)
            # Reset square to center when switching to Proto D: Pitch+Pan+Vol
            self.imu_square_sound_loudness_widget.set_square_position(0.5, 0.5)
            # Start audio if IMU is running
            if self.imu_enabled:
                self.imu_square_sound_loudness_widget.start_audio()
        elif method_text == "Proto E: Dualing IMUs":
            # Hide help buttons for other methods
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            # Hide all other widgets, show dual square widget
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.show()
            # Show second stats widget for Proto E: Dualing IMUs
            self.imu_stats_widget2.show()
            # Disable calibrate button for Proto E: Dualing IMUs (no calibration needed)
            self.calibrate_button.setEnabled(False)
            # Reset squares to center when switching to Proto E: Dualing IMUs
            self.imu_dual_square_widget.set_blue_square_position(0.5, 0.5)
            self.imu_dual_square_widget.set_red_square_position(0.5, 0.5)
            # Stop audio if running
            if self.imu_enabled:
                self.imu_square_sound_widget.stop_audio()
                self.imu_square_sound_loudness_widget.stop_audio()
                self.imu_square_sound_timbre_widget.stop_audio()
                self.imu_square_sound_file_widget.stop_audio()
        elif method_text == "Proto F: Pitch+Timbre":
            # Hide help buttons for other methods
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            # Hide box widget, show square sound timbre widget (with audio + timbre control)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_dual_square_widget.hide()
            self.imu_square_sound_timbre_widget.show()
            self.imu_square_sound_file_widget.hide()
            # Hide second stats widget
            self.imu_stats_widget2.hide()
            # Disable calibrate button for Proto F: Pitch+Timbre (no calibration needed)
            self.calibrate_button.setEnabled(False)
            # Reset square to center when switching to Proto F: Pitch+Timbre
            self.imu_square_sound_timbre_widget.set_square_position(0.5, 0.5)
            # Start audio if IMU is running
            if self.imu_enabled:
                self.imu_square_sound_timbre_widget.start_audio()
        elif method_text == "Proto G: Equalizer":
            # Hide help buttons for other methods
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            # Hide box widget, show square sound file widget (with audio file playback)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.show()
            self.imu_dual_square_widget.hide()
            # Hide second stats widget
            self.imu_stats_widget2.hide()
            # Disable calibrate button for Proto G: Equalizer (no calibration needed)
            self.calibrate_button.setEnabled(False)
            # Reset square to center when switching to Proto G: Equalizer
            self.imu_square_sound_file_widget.set_square_position(0.5, 0.5)
            # Start audio if IMU is running
            if self.imu_enabled:
                print("Proto G: Equalizer selected - starting audio automatically (IMU already running)")
                self.imu_square_sound_file_widget.start_audio()
            else:
                print("Proto G: Equalizer selected - widget visible, audio will start when IMU is enabled")
    
    def _show_method_a_help(self):
        """Show help dialog for Prototype A with IMU orientation instructions."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Prototype A - IMU Orientation Help")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Prototype A - IMU Orientation")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)
        
        # Image
        image_path = os.path.join(os.path.dirname(__file__), "images", "axis.png")
        if os.path.exists(image_path):
            image_label = QLabel()
            pixmap = QPixmap(image_path)
            # Scale image to 50% of original size (200x150 instead of 400x300)
            scaled_pixmap = pixmap.scaled(200, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image_label.setPixmap(scaled_pixmap)
            image_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(image_label)
        else:
            # Fallback if image not found
            image_label = QLabel("(Image: axis.png not found)")
            image_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(image_label)
        
        # Instructions text
        instructions = QLabel("""
<b>Place the IMU on a flat surface</b><br><br>
• Point the x-axis on the IMU forward<br>
• Point the y-axis on the IMU left<br>
• The z-axis is perpendicular to the top of the IMU and should point up<br><br>
<b>Now pretend the screen is the flat surface. After calibrating:</b><br><br>
• Tilt the IMU left and right to move the blue dot right and left<br>
• Tilt the IMU forward (front nose down) to move the blue dot up<br>
• Tilt the IMU back (front nose up) to move the blue dot down
        """)
        instructions.setWordWrap(True)
        instructions.setFont(QFont("Arial", 12))
        layout.addWidget(instructions)
        
        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        dialog.exec_()
    
    def _show_method_b_help(self):
        """Show help dialog for Prototype B with game instructions."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Prototype B - Game Instructions")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Prototype B - Game Instructions")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)
        
        # Image
        image_path = os.path.join(os.path.dirname(__file__), "images", "axis.png")
        if os.path.exists(image_path):
            image_label = QLabel()
            pixmap = QPixmap(image_path)
            # Scale image to 50% of original size (200x150 instead of 400x300)
            scaled_pixmap = pixmap.scaled(200, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image_label.setPixmap(scaled_pixmap)
            image_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(image_label)
        else:
            # Fallback if image not found
            image_label = QLabel("(Image: axis.png not found)")
            image_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(image_label)
        
        # Instructions text
        instructions = QLabel("""
<b>The goal is to steer the blue circle home!</b><br><br>
• Position the IMU so the x-axis faces forward and the y-axis faces left<br>
• Tilt the IMU left and right or forward and backwards to move the blue dot<br>
• When the roll is at +/- 5°, the blue dot will be on the left or right edge<br>
• When the pitch is at +/- 5°, the blue dot will be on the top or bottom edge
        """)
        instructions.setWordWrap(True)
        instructions.setFont(QFont("Arial", 12))
        layout.addWidget(instructions)
        
        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        dialog.exec_()
    
    def _on_calibrate(self):
        """Calibrate zero position from current IMU reading."""
        if not self.imu_reader or not self.imu_enabled:
            return
        
        # Get current sample
        from imu_viewer.models import ImuSample
        sample = self.imu_reader.get_sample(timeout=0.1)
        
        if sample and isinstance(sample, ImuSample):
            # Use device's sensor-fused angles (more stable than raw accelerometer)
            roll_deg, pitch_deg, yaw_deg = sample.angles_deg
            
            # Store as zero reference
            self.zero_roll = roll_deg
            self.zero_pitch = pitch_deg
            self.calibrated = True
            
            # Reset visualization to center
            self.imu_box_widget.set_box_position(0.5, 0.5)
            self.imu_square_widget.set_square_position(0.5, 0.5)
            self.imu_square_sound_widget.set_square_position(0.5, 0.5)
            
            # Show confirmation
            QMessageBox.information(
                self,
                "Calibration Complete",
                f"Calibrated to current position:\n"
                f"Roll: {roll_deg:.1f}°\n"
                f"Pitch: {pitch_deg:.1f}°\n\n"
                f"Box is now centered. Tilt the device to move the box."
            )
        else:
            QMessageBox.warning(
                self,
                "Calibration Failed",
                "Could not read IMU data. Please ensure the device is connected and running."
            )
    
    def _on_mode_changed(self):
        """Handle mode radio button change."""
        if self.usb_radio.isChecked():
            self.imu_mode = "USB"
        elif self.wifi_ap_radio.isChecked():
            self.imu_mode = "WIFI_AP"
        elif self.wifi_sta_radio.isChecked():
            self.imu_mode = "WIFI_STA"
        
        # If IMU is currently running, restart with new mode
        if self.imu_enabled:
            # Stop without re-enabling radio buttons
            if self.imu_timer:
                self.imu_timer.stop()
                self.imu_timer = None
            if self.imu_reader:
                self.imu_reader.stop()
                self.imu_reader = None
            if self.imu_reader2:
                self.imu_reader2.stop()
                self.imu_reader2 = None
            self.imu_box_widget.set_box_position(0.5, 0.5)
            self.imu_square_widget.set_square_position(0.5, 0.5)
            self.imu_dual_square_widget.set_blue_square_position(0.5, 0.5)
            self.imu_dual_square_widget.set_red_square_position(0.5, 0.5)
            self.imu_stats_widget.update_stats(None)
            self.imu_stats_widget2.update_stats(None)
            
            # Restart with new mode (radio buttons stay disabled)
            self._start_imu()
    
    def _toggle_imu(self):
        """Toggle IMU reading on/off."""
        if self.imu_enabled:
            self._stop_imu()
        else:
            self._start_imu()
    
    def _start_imu(self):
        """Start reading IMU data."""
        try:
            # Load config from .imuconfig
            from imu_viewer.config_loader import load_config
            
            config = load_config()
            
            if self.imu_mode == "USB":
                # USB Serial mode
                from imu_viewer.data_sources.serial_reader import SerialImuReader
                
                port = config.get("usb", {}).get("port", "/dev/tty.usbserial-10")
                # USB/Serial is hardcoded to 9600 baud - device doesn't accept other rates
                baud = 9600
                
                # Create and start IMU reader
                self.imu_reader = SerialImuReader(port, baud)
                self.imu_reader.start()
                
            elif self.imu_mode == "WIFI_AP":
                # Wi-Fi AP mode
                from imu_viewer.data_sources.wifi_ap_reader import WifiApImuReader
                
                if "ap" not in config:
                    raise ValueError(
                        "AP mode settings not found in .imuconfig.\n"
                        "Please add an 'ap' section with 'ssid', 'ip', and 'port' fields."
                    )
                
                ap_cfg = config["ap"]
                device_ip = ap_cfg.get("ip")
                device_port = ap_cfg.get("port")
                
                if not device_ip or not device_port:
                    raise ValueError(
                        "AP mode settings incomplete in .imuconfig.\n"
                        "Required fields: 'ip' and 'port'"
                    )
                
                # Create and start Wi-Fi AP reader
                self.imu_reader = WifiApImuReader(device_ip=device_ip, device_port=device_port)
                self.imu_reader.start()
            
            elif self.imu_mode == "WIFI_STA":
                # Wi-Fi STA mode
                from imu_viewer.data_sources.wifi_reader import WifiImuReader
                
                if "wifi" not in config:
                    raise ValueError(
                        "Wi-Fi STA settings not found in .imuconfig.\n"
                        "Please add a 'wifi' section with 'port' and 'use_tcp' fields."
                    )
                
                wifi_cfg = config["wifi"]
                device_port = wifi_cfg.get("port", 1399)
                use_tcp = wifi_cfg.get("use_tcp", False)
                
                if device_port is None:
                    raise ValueError(
                        "Wi-Fi STA settings incomplete in .imuconfig.\n"
                        "Required field: 'port'"
                    )
                
                # Create and start Wi-Fi STA reader (server mode)
                self.imu_reader = WifiImuReader(use_tcp=use_tcp, port=device_port)
                self.imu_reader.start()
            
            # For Proto E: Dualing IMUs, also start second IMU reader on port2
            if self.method == "Proto E: Dualing IMUs":
                wifi_cfg = config.get("wifi", {})
                device_port2 = wifi_cfg.get("port2")
                
                if device_port2 is not None:
                    try:
                        # Create and start second Wi-Fi STA reader on port2
                        self.imu_reader2 = WifiImuReader(use_tcp=use_tcp, port=device_port2)
                        self.imu_reader2.start()
                    except Exception as e2:
                        print(f"Warning: Could not start second IMU reader on port {device_port2}: {e2}")
                        self.imu_reader2 = None
                else:
                    print("Warning: port2 not found in .imuconfig, second IMU will not be available")
                    self.imu_reader2 = None
            
            # Start timer to poll for samples
            self.imu_timer = QTimer(self)
            self.imu_timer.timeout.connect(self._update_imu_data)
            self.imu_timer.start(33)  # ~30 Hz update rate
            
            self.imu_enabled = True
            self.imu_toggle_button.setText("Stop")
            self.imu_toggle_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
                QPushButton:pressed {
                    background-color: #a93226;
                }
            """)
            
            # Disable mode selection while running
            self.usb_radio.setEnabled(False)
            self.wifi_ap_radio.setEnabled(False)
            self.wifi_sta_radio.setEnabled(False)
            
            # Enable calibrate button for Prototype A
            if self.method == "Prototype A":
                self.calibrate_button.setEnabled(True)
            
            # Start audio for Proto C: Pitch + Pan, Proto D: Pitch+Pan+Vol, Proto F: Pitch+Timbre, and Proto G: Equalizer
            if self.method == "Proto C: Pitch + Pan":
                self.imu_square_sound_widget.start_audio()
            elif self.method == "Proto D: Pitch+Pan+Vol":
                self.imu_square_sound_loudness_widget.start_audio()
            elif self.method == "Proto F: Pitch+Timbre":
                self.imu_square_sound_timbre_widget.start_audio()
            elif self.method == "Proto G: Equalizer":
                print("Starting Proto G: Equalizer audio automatically (IMU started)")
                self.imu_square_sound_file_widget.start_audio()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "IMU Error",
                f"Failed to start IMU reading ({self.imu_mode} mode):\n{e}\n\n"
                f"Please check:\n"
                + (f"- Device is connected via USB\n"
                   f"- Serial port is correct in .imuconfig\n"
                   f"- Device is powered on" if self.imu_mode == "USB" else
                   f"- Device is in AP mode\n"
                   f"- Computer is connected to device's Wi-Fi network\n"
                   f"- AP settings (IP, port) are correct in .imuconfig" if self.imu_mode == "WIFI_AP" else
                   f"- Device is in STA mode\n"
                   f"- Device is connected to Wi-Fi network\n"
                   f"- Wi-Fi settings (port, use_tcp) are correct in .imuconfig\n"
                   f"- Device is sending data to this computer's IP on the configured port")
            )
    
    def _stop_imu(self):
        """Stop reading IMU data."""
        # Stop timer first to prevent further updates
        if self.imu_timer:
            self.imu_timer.stop()
            self.imu_timer = None
        
        # Stop IMU readers
        if self.imu_reader:
            self.imu_reader.stop()
            self.imu_reader = None
        
        if self.imu_reader2:
            self.imu_reader2.stop()
            self.imu_reader2 = None
        
        self.imu_enabled = False
        
        # Reset visualization to center immediately
        self.imu_box_widget.set_box_position(0.5, 0.5)
        self.imu_square_widget.set_square_position(0.5, 0.5)
        self.imu_square_sound_widget.set_square_position(0.5, 0.5)
        self.imu_square_sound_loudness_widget.set_square_position(0.5, 0.5)
        self.imu_square_sound_timbre_widget.set_square_position(0.5, 0.5)
        self.imu_dual_square_widget.set_blue_square_position(0.5, 0.5)
        self.imu_dual_square_widget.set_red_square_position(0.5, 0.5)
        self.imu_stats_widget.update_stats(None)
        self.imu_stats_widget2.update_stats(None)
        
        # Stop audio for Proto C: Pitch + Pan, Proto D: Pitch+Pan+Vol, Proto F: Pitch+Timbre, and Proto G: Equalizer
        if self.method == "Proto C: Pitch + Pan":
            self.imu_square_sound_widget.stop_audio()
        if self.method == "Proto D: Pitch+Pan+Vol":
            self.imu_square_sound_loudness_widget.stop_audio()
        if self.method == "Proto F: Pitch+Timbre":
            self.imu_square_sound_timbre_widget.stop_audio()
        if self.method == "Proto G: Equalizer":
            self.imu_square_sound_file_widget.stop_audio()
        
        # Re-enable mode selection
        self.usb_radio.setEnabled(True)
        self.wifi_ap_radio.setEnabled(True)
        self.wifi_sta_radio.setEnabled(True)
        
        # Disable calibrate button
        self.calibrate_button.setEnabled(False)
        
        # Reset calibration state
        self.calibrated = False
        
        # Update button
        self.imu_toggle_button.setText("Start")
        self.imu_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
    
    def _update_imu_data(self):
        """Update box/square position and stats based on IMU data."""
        if not self.imu_reader:
            return
        
        # Get latest sample
        from imu_viewer.models import ImuSample
        sample = self.imu_reader.get_sample(timeout=0.0)
        
        if sample and isinstance(sample, ImuSample):
            # Update stats display
            self.imu_stats_widget.update_stats(sample)
            
            # Get angles from device (sensor-fused angles)
            roll_deg, pitch_deg, yaw_deg = sample.angles_deg
            
            if self.method == "Prototype A":
                # Prototype A: Uses calibrated angles with configurable limits
                if self.calibrated:
                    # Compute relative angles from calibrated zero position
                    roll_rel = roll_deg - self.zero_roll
                    pitch_rel = pitch_deg - self.zero_pitch
                    
                    # Map relative angles to box position
                    # Following standard IMU convention:
                    # - Roll (X-axis rotation, tilt left/right) → horizontal (X) movement
                    # - Pitch (Y-axis rotation, tilt forward/back) → vertical (Y) movement
                    
                    # Roll controls horizontal position (X)
                    # Positive roll (tilt right) → box moves right
                    # Negative roll (tilt left) → box moves left
                    x_pos = 0.5 + (roll_rel / self.max_roll_deg)
                    
                    # Pitch controls vertical position (Y)
                    # Positive pitch (tilt forward) → box moves down (invert Y for screen coordinates)
                    # Negative pitch (tilt back) → box moves up
                    y_pos = 0.5 - (pitch_rel / self.max_pitch_deg)  # Minus to invert screen Y
                    
                    # Clamp to valid range
                    x_pos = max(0.0, min(1.0, x_pos))
                    y_pos = max(0.0, min(1.0, y_pos))
                else:
                    # Not calibrated yet - use old method as fallback
                    # This allows the box to move before calibration
                    ax, ay, az = sample.accel_g
                    x_pos = 0.5 + (ax / 2.0)
                    x_pos = max(0.0, min(1.0, x_pos))
                    y_pos = 0.5 + ((az - 1.0) / 2.0)
                    y_pos = max(0.0, min(1.0, y_pos))
                
                # Update box position
                self.imu_box_widget.set_box_position(x_pos, y_pos)
                
            elif self.method == "Prototype B":
                # Prototype B: Uses direct angle mapping (matching imu_tkinter.py)
                # This method uses ±5.0 degrees as maximum tilt range
                # No calibration needed - directly uses device angles
                # Game mode: Target circle appears when within ±1°, turns green when square is inside
                x_pos, y_pos = self.imu_square_widget.map_tilt_to_position(roll_deg, pitch_deg)
                self.imu_square_widget.set_square_position(x_pos, y_pos)
                # Update angles for target detection
                self.imu_square_widget.set_angles(roll_deg, pitch_deg)
            
            elif self.method == "Proto C: Pitch + Pan":
                # Proto C: Pitch + Pan: Uses direct angle mapping with audio (matching imu_tkintersound.py)
                # Visual: Same as Prototype B (blue square, ±5.0 degrees)
                # Audio: Pitch controls frequency, roll controls stereo panning
                x_pos, y_pos = self.imu_square_sound_widget.map_tilt_to_position(roll_deg, pitch_deg)
                self.imu_square_sound_widget.set_square_position(x_pos, y_pos)
                # Update angles for audio generation (uses extended roll range for panning)
                self.imu_square_sound_widget.set_angles_for_audio(roll_deg, pitch_deg)
            elif self.method == "Proto D: Pitch+Pan+Vol":
                # Proto D: Pitch+Pan+Vol: Uses direct angle mapping with audio + acceleration-based loudness
                # Visual: Same as Prototype B (blue square, ±5.0 degrees)
                # Audio: Pitch controls frequency, roll controls stereo panning
                # Loudness: Amplitude controlled by Z-axis accelerometer (step-based, 2s cooldown)
                x_pos, y_pos = self.imu_square_sound_loudness_widget.map_tilt_to_position(roll_deg, pitch_deg)
                self.imu_square_sound_loudness_widget.set_square_position(x_pos, y_pos)
                # Update angles for audio generation (uses extended roll range for panning)
                self.imu_square_sound_loudness_widget.set_angles_for_audio(roll_deg, pitch_deg)
                # Update Z-axis acceleration for volume control
                az = sample.accel_g[2]  # Z-axis acceleration
                self.imu_square_sound_loudness_widget.update_accel_z(az)
            
            elif self.method == "Proto E: Dualing IMUs":
                # Proto E: Dualing IMUs: Dual IMU support - blue square (IMU 1) and red square (IMU 2)
                # Uses same tilt mapping as Prototype B (±5.0 degrees)
                # Blue square controlled by first IMU (port from config)
                # Red square controlled by second IMU (port2 from config)
                x_pos, y_pos = self.imu_dual_square_widget.map_tilt_to_position(roll_deg, pitch_deg)
                self.imu_dual_square_widget.set_blue_square_position(x_pos, y_pos)
                # Update angles for blue square target detection
                self.imu_dual_square_widget.set_blue_angles(roll_deg, pitch_deg)
                
                # Handle second IMU (red square) if available
                if self.imu_reader2:
                    sample2 = self.imu_reader2.get_sample(timeout=0.0)
                    if sample2 and isinstance(sample2, ImuSample):
                        # Update stats display for second IMU
                        self.imu_stats_widget2.update_stats(sample2)
                        
                        # Get angles from second device
                        roll_deg2, pitch_deg2, yaw_deg2 = sample2.angles_deg
                        
                        # Map to position for red square
                        x_pos2, y_pos2 = self.imu_dual_square_widget.map_tilt_to_position(roll_deg2, pitch_deg2)
                        self.imu_dual_square_widget.set_red_square_position(x_pos2, y_pos2)
                else:
                    # No second IMU - update stats to show waiting
                    self.imu_stats_widget2.update_stats(None)
            
            elif self.method == "Proto F: Pitch+Timbre":
                # Proto F: Pitch+Timbre: Uses direct angle mapping with audio + timbre control + user-controlled volume
                # Visual: Same as Prototype B (blue square, ±5.0 degrees)
                # Audio: Pitch controls frequency, yaw controls stereo panning, roll controls timbre
                # Volume: User-controlled via clickable volume bar (no motion control)
                # Timbre: Roll angle morphs between sine (warm) and sawtooth (bright) waveforms
                x_pos, y_pos = self.imu_square_sound_timbre_widget.map_tilt_to_position(roll_deg, pitch_deg)
                self.imu_square_sound_timbre_widget.set_square_position(x_pos, y_pos)
                # Update angles for target circle display
                self.imu_square_sound_timbre_widget.set_angles(roll_deg, pitch_deg)
                # Update angles for audio generation (yaw for panning, roll for timbre)
                self.imu_square_sound_timbre_widget.set_angles_for_audio(roll_deg, pitch_deg, yaw_deg)
                # Update display to show current pitch and timbre values
                self.imu_square_sound_timbre_widget._update_display()
            
            elif self.method == "Proto G: Equalizer":
                # Proto G: Equalizer: Uses direct angle mapping with audio file playback
                # Visual: Same as Prototype B (blue square, ±5.0 degrees)
                # Audio: Plays music/music.mp3 on loop
                # Volume: Controlled by pitch angle
                # Timbre: Controlled by roll angle (low-pass filter cutoff)
                x_pos, y_pos = self.imu_square_sound_file_widget.map_tilt_to_position(roll_deg, pitch_deg)
                self.imu_square_sound_file_widget.set_square_position(x_pos, y_pos)
                # Update angles for target circle display
                self.imu_square_sound_file_widget.set_angles(roll_deg, pitch_deg)
                # Update angles for audio generation (pitch for volume, roll for timbre, yaw for panning)
                self.imu_square_sound_file_widget.set_angles_for_audio(roll_deg, pitch_deg, yaw_deg)
                # Update display to show current volume and timbre values
                self.imu_square_sound_file_widget._update_display()
    
    def cleanup(self):
        """Clean up resources when tab is switched away."""
        self._stop_imu()
    
    def resume(self):
        """Resume widget when tab is switched to."""
        # Don't auto-start IMU, user must click button
        pass


class MainWindow(QMainWindow):
    """Main window with tabbed interface for multiple apps."""

    def __init__(self):
        super().__init__()
        self.hands_widget = None
        self.yoga_widget = None
        self.music_widget = None
        self.current_active_widget = None
        
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Music & Motion Applications")
        self.setMinimumSize(1200, 700)
        self.resize(1600, 900)

        # Create central widget with layout for checkbox
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Top bar with checkbox
        top_bar = QFrame()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(16, 8, 16, 8)
        top_bar_layout.setAlignment(Qt.AlignRight)
        top_bar.setStyleSheet("background-color: #f8f9fa; border-bottom: 1px solid #dfe4ea;")

        # Camera blackout checkbox
        self.camera_checkbox = QCheckBox("Turn off camera")
        self.camera_checkbox.setFont(QFont("Arial", 12))
        self.camera_checkbox.setStyleSheet("""
            QCheckBox {
                color: #2c3e50;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #bdc3c7;
                border-radius: 3px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #3498db;
                border-color: #3498db;
            }
            QCheckBox::indicator:checked::after {
                content: "";
                position: absolute;
                width: 4px;
                height: 8px;
                border: solid white;
                border-width: 0 2px 2px 0;
                transform: rotate(45deg);
            }
        """)
        self.camera_checkbox.stateChanged.connect(self._on_camera_checkbox_changed)
        
        # Exit button
        self.exit_button = QPushButton("Exit")
        self.exit_button.setFont(QFont("Arial", 12))
        self.exit_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }
        """)
        self.exit_button.clicked.connect(self.close)
        
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.camera_checkbox)
        top_bar_layout.addWidget(self.exit_button)

        central_layout.addWidget(top_bar)

        # Create tab widget
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        # Disable scroll buttons so tabs can expand to fit content
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #ecf0f1;
                color: #2c3e50;
                padding: 16px 40px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 14px;
                font-weight: 500;
                min-width: 200px;
            }
            QTabBar::tab:selected {
                background-color: #3498db;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #bdc3c7;
            }
            QTabBar::tab:selected:hover {
                background-color: #2980b9;
            }
        """)

        # Create and add tabs in order: IMU Pipeline, Hands Demo, Yoga Pose Detector, Music in Motion
        self.music_widget = MusicInMotionWidget()
        self.tabs.addTab(self.music_widget, "IMU Pipeline")
        self.current_active_widget = self.music_widget

        self.hands_widget = HandsDemoWidget()
        self.tabs.addTab(self.hands_widget, "Hands Demo")

        self.yoga_widget = YogaPoseDetectorWidget()
        self.tabs.addTab(self.yoga_widget, "Yoga Pose Detector")

        self.body_motion_widget = BodyMotionEqualizerWidget()
        self.tabs.addTab(self.body_motion_widget, "Music in Motion")

        # Connect tab change signal to manage camera resources
        self.tabs.currentChanged.connect(self._on_tab_changed)

        central_layout.addWidget(self.tabs)
        self.setCentralWidget(central_widget)

    def _on_camera_checkbox_changed(self, state):
        """Handle camera checkbox state change."""
        blackout = state == Qt.Checked
        if self.hands_widget and hasattr(self.hands_widget, 'set_camera_blackout'):
            self.hands_widget.set_camera_blackout(blackout)
        if self.yoga_widget and hasattr(self.yoga_widget, 'set_camera_blackout'):
            self.yoga_widget.set_camera_blackout(blackout)
        if self.body_motion_widget and hasattr(self.body_motion_widget, 'set_camera_blackout'):
            self.body_motion_widget.set_camera_blackout(blackout)

    def _on_tab_changed(self, index: int):
        """Handle tab changes - cleanup previous widget, resume new one."""
        # Cleanup previous active widget
        if self.current_active_widget:
            if hasattr(self.current_active_widget, 'cleanup'):
                self.current_active_widget.cleanup()

        # Determine new active widget
        if index == 0:  # IMU Pipeline
            self.current_active_widget = self.music_widget
        elif index == 1:  # Hands Demo
            self.current_active_widget = self.hands_widget
        elif index == 2:  # Yoga Pose Detector
            self.current_active_widget = self.yoga_widget
        else:  # Music in Motion (body → equalizer)
            self.current_active_widget = self.body_motion_widget

        # Resume new active widget
        if self.current_active_widget and hasattr(self.current_active_widget, 'resume'):
            self.current_active_widget.resume()

    def closeEvent(self, event):
        """Clean up all resources on window close."""
        if self.hands_widget and hasattr(self.hands_widget, 'cleanup'):
            self.hands_widget.cleanup()
        if self.yoga_widget and hasattr(self.yoga_widget, 'cleanup'):
            self.yoga_widget.cleanup()
        if self.body_motion_widget and hasattr(self.body_motion_widget, 'cleanup'):
            self.body_motion_widget.cleanup()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
