"""Music in Motion tab - Body-as-instrument control."""

import os
import cv2
import numpy as np
import mediapipe as mp
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QRadioButton, QButtonGroup, QMessageBox, QLabel, QSizePolicy
)
from PyQt5.QtGui import QFont, QImage, QPixmap, QColor
from PyQt5.QtCore import Qt, QTimer
from .base_tab import BaseTabWidget
from ..widgets.imu_stats import ImuStatsWidget
from ...imu.methods import Model1Widget, Model1BarsWidget, Model1EqualizerWidget


class MusicInMotionTabWidget(BaseTabWidget):
    """Music in Motion tab with body-as-instrument control."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.imu_reader = None
        self.imu_reader2 = None  # Second IMU reader for dual IMU support
        self.imu_enabled = False
        self.imu_timer = None
        self.pose_timer = None
        
        # MediaPipe pose solution
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        self.pose = None
        self.cap = None
        self.camera_blackout = True  # Camera off by default
        self.cap = None  # Camera not initialized until needed
        
        # Read default mode from .imuconfig
        from imu_viewer.config_loader import load_config
        config = load_config()
        default_mode = config.get("mode", "usb").lower()
        if default_mode == "usb":
            self.imu_mode = "USB"
        elif default_mode == "ap":
            self.imu_mode = "WIFI_AP"
        elif default_mode == "sta":
            self.imu_mode = "WIFI_STA"
        else:
            self.imu_mode = "USB"
        
        self.model = "Model 1"
        self._init_ui()
        # Only initialize camera if not blacked out
        if not self.camera_blackout:
            self._init_camera()
        self._init_pose_detector()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Top bar with model selector, mode selection and IMU toggle
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        
        # Model selector dropdown
        self.model_combo = QComboBox()
        self.model_combo.addItem("Model 1")
        self.model_combo.setFont(QFont("Arial", 11))
        self.model_combo.setCurrentIndex(0)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        top_bar.addWidget(self.model_combo)
        
        top_bar.addSpacing(15)
        
        # Audio source selector dropdown (only for Model 1)
        self.audio_source_combo = QComboBox()
        self.audio_source_combo.addItem("Play a tone")
        self.audio_source_combo.addItem("Play Music")
        self.audio_source_combo.setFont(QFont("Arial", 11))
        self.audio_source_combo.setCurrentIndex(0)
        self.audio_source_combo.setMinimumWidth(120)  # Ensure it has a visible width
        self.audio_source_combo.currentTextChanged.connect(self._on_audio_source_changed)
        top_bar.addWidget(self.audio_source_combo)
        
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
        
        top_bar.addSpacing(20)
        
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
        
        # Main content area - Dashboard container for Model 1
        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(20)
        
        # Left side: IMU stats (IMU 1)
        self.imu_stats_widget = ImuStatsWidget()
        self.content_layout.addWidget(self.imu_stats_widget)
        
        # Dashboard container for Model 1 (fixed height 220px)
        self.dashboard_widget = QWidget()
        self.dashboard_widget.setFixedHeight(220)  # Fixed height as requested
        self.dashboard_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.dashboard_widget.setStyleSheet("background-color: #e8e8e8;")
        
        dashboard_layout = QHBoxLayout(self.dashboard_widget)
        dashboard_layout.setContentsMargins(10, 10, 10, 10)
        dashboard_layout.setSpacing(20)
        
        # Create bars and equalizer widgets
        self.model_1_bars_widget = Model1BarsWidget()
        self.model_1_equalizer_widget = Model1EqualizerWidget()
        
        # Add bars and equalizer to dashboard (side by side)
        dashboard_layout.addWidget(self.model_1_bars_widget, 0)  # Bars on left, flexible width
        dashboard_layout.addWidget(self.model_1_equalizer_widget, 1)  # Equalizer on right, flexible width
        
        # Center: Model widgets (controller only, not displayed)
        self.model_1_widget = Model1Widget()
        # Connect bars and equalizer widgets to Model1Widget
        self.model_1_widget.set_widgets(self.model_1_bars_widget, self.model_1_equalizer_widget)
        # Model1Widget is just a controller, doesn't need to be in layout
        self.model_1_widget.hide()
        
        # Add dashboard to content layout
        self.content_layout.addWidget(self.dashboard_widget, 0)
        
        # Set initial visibility - Model 1 is default, so show the dropdown
        # _on_model_changed will handle visibility when switching models
        if self.model == "Model 1":
            # Hide IMU stats widget for Model 1 (bars are shown in dashboard instead)
            self.imu_stats_widget.hide()
            self.dashboard_widget.show()
            self.audio_source_combo.setVisible(True)
            self.audio_source_combo.setEnabled(True)
            # Initialize Model1Widget with default audio source (tone mode)
            self.model_1_widget.set_audio_source(False)  # False = tone mode
        else:
            self.dashboard_widget.hide()
            self.audio_source_combo.setVisible(False)
        
        # Right side: IMU stats (IMU 2) - for dual IMU support
        self.imu_stats_widget2 = ImuStatsWidget()
        self.imu_stats_widget2.hide()  # Hidden by default
        self.content_layout.addWidget(self.imu_stats_widget2)
        
        main_layout.addLayout(self.content_layout, 0)  # Don't stretch, let video expand
        
        # Video preview area (for MediaPipe visualization) - expands to fill space
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 360)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setStyleSheet("background-color: black; border-radius: 10px;")
        main_layout.addWidget(self.video_label, 1)  # Stretch to fill remaining space

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

    def _on_model_changed(self, model_text):
        """Handle model selector change."""
        self.model = model_text
        
        if model_text == "Model 1":
            # Model1Widget is always hidden (just a controller)
            # Hide IMU stats widgets for Model 1 (bars are shown in dashboard instead)
            self.imu_stats_widget.hide()
            self.imu_stats_widget2.hide()
            # Show dashboard
            self.dashboard_widget.show()
            # Show audio source dropdown
            self.audio_source_combo.setVisible(True)
            self.audio_source_combo.setEnabled(True)
            # Stop audio if switching away
            # (Model 1 will start its own audio when IMU is enabled)
        else:
            # Hide dashboard
            self.dashboard_widget.hide()
            # Show IMU stats widgets for other models
            self.imu_stats_widget.show()
            self.imu_stats_widget2.hide()
            # Hide audio source dropdown
            self.audio_source_combo.setVisible(False)
    
    def _on_audio_source_changed(self, audio_source_text):
        """Handle audio source selector change."""
        if self.model == "Model 1":
            # Update Model 1 widget with new audio source
            is_music_mode = (audio_source_text == "Play Music")
            self.model_1_widget.set_audio_source(is_music_mode)
            
            # If audio is currently running, restart it with new source
            if self.imu_enabled:
                self.model_1_widget.stop_audio()
                self.model_1_widget.start_audio()

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
            if self.imu_timer:
                self.imu_timer.stop()
                self.imu_timer = None
            if self.imu_reader:
                self.imu_reader.stop()
                self.imu_reader = None
            if self.imu_reader2:
                self.imu_reader2.stop()
                self.imu_reader2 = None
            self.imu_stats_widget.update_stats(None)
            self.imu_stats_widget2.update_stats(None)
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
            from imu_viewer.config_loader import load_config
            config = load_config()
            
            if self.imu_mode == "USB":
                from imu_viewer.data_sources.serial_reader import SerialImuReader
                port = config.get("usb", {}).get("port", "/dev/tty.usbserial-10")
                baud = 9600
                self.imu_reader = SerialImuReader(port, baud)
                self.imu_reader.start()
                
            elif self.imu_mode == "WIFI_AP":
                from imu_viewer.data_sources.wifi_ap_reader import WifiApImuReader
                if "ap" not in config:
                    raise ValueError("AP mode settings not found in .imuconfig.")
                ap_cfg = config["ap"]
                device_ip = ap_cfg.get("ip")
                device_port = ap_cfg.get("port")
                if not device_ip or not device_port:
                    raise ValueError("AP mode settings incomplete in .imuconfig.")
                self.imu_reader = WifiApImuReader(device_ip=device_ip, device_port=device_port)
                self.imu_reader.start()
            
            elif self.imu_mode == "WIFI_STA":
                from imu_viewer.data_sources.wifi_reader import WifiImuReader
                if "wifi" not in config:
                    raise ValueError("Wi-Fi STA settings not found in .imuconfig.")
                wifi_cfg = config["wifi"]
                device_port = wifi_cfg.get("port", 1399)
                use_tcp = wifi_cfg.get("use_tcp", False)
                if device_port is None:
                    raise ValueError("Wi-Fi STA settings incomplete in .imuconfig.")
                self.imu_reader = WifiImuReader(use_tcp=use_tcp, port=device_port)
                self.imu_reader.start()
            
            # For Model 1, also start second IMU reader on port2
            if self.model == "Model 1":
                wifi_cfg = config.get("wifi", {})
                device_port2 = wifi_cfg.get("port2")
                if device_port2 is not None:
                    try:
                        use_tcp = wifi_cfg.get("use_tcp", False)
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
            
            # Start pose detection timer
            self.pose_timer = QTimer(self)
            self.pose_timer.timeout.connect(self._update_pose_data)
            self.pose_timer.start(33)  # ~30 FPS
            
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
            
            self.usb_radio.setEnabled(False)
            self.wifi_ap_radio.setEnabled(False)
            self.wifi_sta_radio.setEnabled(False)
            
            # Start audio for Model 1
            if self.model == "Model 1":
                self.model_1_widget.start_audio()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "IMU Error",
                f"Failed to start IMU reading ({self.imu_mode} mode):\n{e}\n\n"
                f"Please check your .imuconfig settings and device connection."
            )

    def _stop_imu(self):
        """Stop reading IMU data."""
        if self.imu_timer:
            self.imu_timer.stop()
            self.imu_timer = None
        
        if self.pose_timer:
            self.pose_timer.stop()
            self.pose_timer = None
        
        if self.imu_reader:
            self.imu_reader.stop()
            self.imu_reader = None
        
        if self.imu_reader2:
            self.imu_reader2.stop()
            self.imu_reader2 = None
        
        self.imu_enabled = False
        
        self.imu_stats_widget.update_stats(None)
        self.imu_stats_widget2.update_stats(None)
        
        # Stop audio
        if self.model == "Model 1":
            self.model_1_widget.stop_audio()
        
        self.usb_radio.setEnabled(True)
        self.wifi_ap_radio.setEnabled(True)
        self.wifi_sta_radio.setEnabled(True)
        
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
        """Update IMU data and pass to model widgets."""
        if not self.imu_reader:
            return
        
        from imu_viewer.models import ImuSample
        sample = self.imu_reader.get_sample(timeout=0.0)
        
        if sample and isinstance(sample, ImuSample):
            self.imu_stats_widget.update_stats(sample)
            
            # Get acceleration magnitude for left IMU
            ax, ay, az = sample.accel_g
            accel_magnitude = np.sqrt(ax**2 + ay**2 + az**2)
            
            # Get second IMU data if available
            accel_magnitude2 = 0.0
            if self.imu_reader2:
                sample2 = self.imu_reader2.get_sample(timeout=0.0)
                if sample2 and isinstance(sample2, ImuSample):
                    self.imu_stats_widget2.update_stats(sample2)
                    ax2, ay2, az2 = sample2.accel_g
                    accel_magnitude2 = np.sqrt(ax2**2 + ay2**2 + az2**2)
                else:
                    self.imu_stats_widget2.update_stats(None)
            else:
                self.imu_stats_widget2.update_stats(None)
            
            # Update Model 1 with IMU data
            if self.model == "Model 1":
                self.model_1_widget.update_imu_data(accel_magnitude, accel_magnitude2)

    def _update_pose_data(self):
        """Update MediaPipe pose data and pass to model widgets."""
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
        left_arm_height = None
        right_arm_height = None
        
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
                
                # Extract wrist positions
                landmarks = results.pose_landmarks.landmark
                
                # Left arm: use left wrist y position directly
                # MediaPipe y: 0 = top of frame, 1 = bottom of frame
                # Invert so lower y (higher on screen) = higher value
                left_wrist = landmarks[self.mp_pose.PoseLandmark.LEFT_WRIST.value]
                left_arm_height = 1.0 - left_wrist.y  # Inverted: arm raised (low y) = high value
                
                # Right arm: use right wrist y position directly
                right_wrist = landmarks[self.mp_pose.PoseLandmark.RIGHT_WRIST.value]
                right_arm_height = 1.0 - right_wrist.y  # Inverted: arm raised (low y) = high value
        
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
        
        # Update Model 1 with pose data
        if self.model == "Model 1" and left_arm_height is not None and right_arm_height is not None:
            self.model_1_widget.update_pose_data(left_arm_height, right_arm_height)

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
        """Clean up resources when tab is switched away."""
        self._stop_imu()
        if self.pose:
            self.pose.close()
            self.pose = None
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None

    def resume(self):
        """Resume widget when tab is switched to."""
        # Only initialize camera if not blacked out
        if not self.camera_blackout:
            if not self.cap or not self.cap.isOpened():
                self._init_camera()
        if not self.pose:
            self._init_pose_detector()

