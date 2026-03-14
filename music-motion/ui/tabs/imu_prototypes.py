"""IMU Prototypes tab - Music in Motion widget with IMU integration."""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QRadioButton, QButtonGroup, QMessageBox, QDialog, QDialogButtonBox, QLabel
)
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtCore import Qt, QTimer
from .base_tab import BaseTabWidget
from ..widgets.imu_stats import ImuStatsWidget
from ...imu.visualization.box import ImuBoxWidget
from ...imu.visualization.base import ImuSquareWidget
from ...imu.visualization.dual_square import ImuDualSquareWidget
from ...imu.methods.method_c import ImuSquareSoundWidget
from ...imu.methods.method_d import ImuSquareSoundLoudnessWidget
from ...imu.methods.method_f import ImuSquareSoundTimbreWidget
from ...imu.methods.method_g import ImuSquareSoundFileWidget
from ...imu.methods.imu_viewer import ImuViewerWidget
from ...imu.methods.lpf_filter_test import LpfFilterTestWidget
from ...imu.methods.imu_latency import ImuLatencyWidget


class MusicInMotionWidget(BaseTabWidget):
    """Music in Motion widget with IMU integration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.imu_reader = None
        self.imu_reader2 = None  # Second IMU reader for Method E
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
        
        self.method = "IMU Viewer"
        # Calibration values for Blue Square #1
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
        self.method_combo.addItem("IMU Viewer")
        self.method_combo.addItem("LPF Filter Test")
        self.method_combo.addItem("IMU Latency")
        self.method_combo.addItem("Blue Square #1")
        self.method_combo.addItem("Method B")
        self.method_combo.addItem("Pitch + Pan")
        self.method_combo.addItem("Method D")
        self.method_combo.addItem("Method E")
        self.method_combo.addItem("Method F")
        self.method_combo.addItem("Method G")
        self.method_combo.setFont(QFont("Arial", 11))
        self.method_combo.setCurrentIndex(0)  # Default to IMU Viewer
        self.method_combo.currentTextChanged.connect(self._on_method_changed)
        top_bar.addWidget(self.method_combo)
        
        # Help button for Blue Square #1
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
        self.method_a_help_button.setToolTip("Help for Blue Square #1")
        self.method_a_help_button.clicked.connect(self._show_method_a_help)
        self.method_a_help_button.setVisible(self.method == "Blue Square #1")
        top_bar.addWidget(self.method_a_help_button)
        
        # Help button for Method B
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
        self.method_b_help_button.setToolTip("Help for Method B")
        self.method_b_help_button.clicked.connect(self._show_method_b_help)
        self.method_b_help_button.setVisible(self.method == "Method B")
        top_bar.addWidget(self.method_b_help_button)
        
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
        
        # Calibrate button (only visible for Blue Square #1)
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
        self.calibrate_button.setEnabled(False)
        top_bar.addWidget(self.calibrate_button)
        
        # LPF button (only visible for LPF Filter Test)
        self.lpf_button = QPushButton("LPF: Off")
        self.lpf_button.setCheckable(True)
        self.lpf_button.setChecked(False)
        self.lpf_button.setFont(QFont("Arial", 11))
        self.lpf_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #27ae60;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:checked:hover {
                background-color: #229954;
            }
        """)
        self.lpf_button.clicked.connect(self._on_lpf_toggle)
        self.lpf_button.hide()  # Hidden by default
        top_bar.addWidget(self.lpf_button)
        
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
        
        # Main content area
        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(20)
        
        # Left side: IMU stats (IMU 1) - hidden for IMU Viewer (default)
        self.imu_stats_widget = ImuStatsWidget()
        self.imu_stats_widget.hide()  # Hidden by default since IMU Viewer is default
        self.content_layout.addWidget(self.imu_stats_widget)
        
        # Center: IMU visualization widgets
        self.imu_box_widget = ImuBoxWidget()
        self.imu_box_widget.hide()  # Hidden by default since IMU Viewer is default
        self.content_layout.addWidget(self.imu_box_widget, 1)
        
        self.imu_square_widget = ImuSquareWidget()
        self.imu_square_widget.hide()
        self.content_layout.addWidget(self.imu_square_widget, 1)
        
        self.imu_square_sound_widget = ImuSquareSoundWidget()
        self.imu_square_sound_widget.hide()
        self.content_layout.addWidget(self.imu_square_sound_widget, 1)
        
        self.imu_square_sound_loudness_widget = ImuSquareSoundLoudnessWidget()
        self.imu_square_sound_loudness_widget.hide()
        self.content_layout.addWidget(self.imu_square_sound_loudness_widget, 1)
        
        self.imu_dual_square_widget = ImuDualSquareWidget()
        self.imu_dual_square_widget.hide()
        self.content_layout.addWidget(self.imu_dual_square_widget, 1)
        
        self.imu_square_sound_timbre_widget = ImuSquareSoundTimbreWidget()
        self.imu_square_sound_timbre_widget.hide()
        self.content_layout.addWidget(self.imu_square_sound_timbre_widget, 1)
        
        self.imu_square_sound_file_widget = ImuSquareSoundFileWidget()
        self.imu_square_sound_file_widget.hide()
        self.content_layout.addWidget(self.imu_square_sound_file_widget, 1)
        
        self.imu_viewer_widget = ImuViewerWidget()
        # IMU Viewer is the default, so show it initially
        self.content_layout.addWidget(self.imu_viewer_widget, 1)
        
        self.lpf_filter_test_widget = LpfFilterTestWidget()
        self.lpf_filter_test_widget.hide()
        self.content_layout.addWidget(self.lpf_filter_test_widget, 1)
        
        self.imu_latency_widget = ImuLatencyWidget()
        self.imu_latency_widget.hide()
        self.content_layout.addWidget(self.imu_latency_widget, 1)
        
        # Right side: IMU stats (IMU 2) - only visible for Method E
        self.imu_stats_widget2 = ImuStatsWidget()
        self.imu_stats_widget2.hide()
        self.content_layout.addWidget(self.imu_stats_widget2)
        
        main_layout.addLayout(self.content_layout, 1)
        
    def _on_method_changed(self, method_text):
        """Handle method selector change."""
        # Stop audio if switching away from audio methods
        if self.method == "Pitch + Pan" and method_text != "Pitch + Pan":
            self.imu_square_sound_widget.stop_audio()
        if self.method == "Method D" and method_text != "Method D":
            self.imu_square_sound_loudness_widget.stop_audio()
        if self.method == "Method F" and method_text != "Method F":
            self.imu_square_sound_timbre_widget.stop_audio()
        if self.method == "Method G" and method_text != "Method G":
            self.imu_square_sound_file_widget.stop_audio()
        
        # Update timer rate based on method (if IMU is running)
        old_method = self.method
        self.method = method_text
        
        if self.imu_enabled and self.imu_timer:
            # All methods use fast polling (200 Hz) for low latency
            self.imu_timer.stop()
            self.imu_timer.start(5)  # 200 Hz for very low latency
        
        if method_text == "Blue Square #1":
            self.imu_box_widget.show()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.hide()
            self.imu_viewer_widget.hide()
            self.lpf_filter_test_widget.hide()
            self.imu_latency_widget.hide()
            self.imu_stats_widget.show()
            self.imu_stats_widget2.hide()
            self.calibrate_button.setVisible(True)
            self.calibrate_button.setEnabled(self.imu_enabled)
            self.lpf_button.setVisible(False)
            self.method_a_help_button.setVisible(True)
            self.method_b_help_button.setVisible(False)
        elif method_text == "Method B":
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(True)
            self.imu_box_widget.hide()
            self.imu_square_widget.show()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.hide()
            self.imu_viewer_widget.hide()
            self.lpf_filter_test_widget.hide()
            self.imu_latency_widget.hide()
            self.imu_stats_widget.show()
            self.imu_stats_widget2.hide()
            self.calibrate_button.setVisible(True)
            self.calibrate_button.setEnabled(False)
            self.lpf_button.setVisible(True)  # Show LPF button for Method B
            self.imu_square_widget.set_square_position(0.5, 0.5)
        elif method_text == "Pitch + Pan":
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.show()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.hide()
            self.imu_viewer_widget.hide()
            self.lpf_filter_test_widget.hide()
            self.imu_latency_widget.hide()
            self.imu_stats_widget.show()
            self.imu_stats_widget2.hide()
            self.calibrate_button.setVisible(True)
            self.calibrate_button.setEnabled(False)
            self.lpf_button.setVisible(False)
            self.imu_square_sound_widget.set_square_position(0.5, 0.5)
            if self.imu_enabled:
                self.imu_square_sound_widget.start_audio()
        elif method_text == "Method D":
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.show()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.hide()
            self.imu_viewer_widget.hide()
            self.lpf_filter_test_widget.hide()
            self.imu_latency_widget.hide()
            self.imu_stats_widget.show()
            self.imu_stats_widget2.hide()
            self.calibrate_button.setVisible(True)
            self.calibrate_button.setEnabled(False)
            self.lpf_button.setVisible(False)
            self.imu_square_sound_loudness_widget.set_square_position(0.5, 0.5)
            if self.imu_enabled:
                self.imu_square_sound_loudness_widget.start_audio()
        elif method_text == "Method E":
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.show()
            self.imu_viewer_widget.hide()
            self.lpf_filter_test_widget.hide()
            self.imu_latency_widget.hide()
            self.imu_stats_widget.show()
            self.imu_stats_widget2.show()
            self.calibrate_button.setVisible(True)
            self.calibrate_button.setEnabled(False)
            self.lpf_button.setVisible(False)
            self.imu_dual_square_widget.set_blue_square_position(0.5, 0.5)
            self.imu_dual_square_widget.set_red_square_position(0.5, 0.5)
            if self.imu_enabled:
                self.imu_square_sound_widget.stop_audio()
                self.imu_square_sound_loudness_widget.stop_audio()
                self.imu_square_sound_timbre_widget.stop_audio()
                self.imu_square_sound_file_widget.stop_audio()
        elif method_text == "Method F":
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_dual_square_widget.hide()
            self.imu_square_sound_timbre_widget.show()
            self.imu_square_sound_file_widget.hide()
            self.imu_viewer_widget.hide()
            self.lpf_filter_test_widget.hide()
            self.imu_latency_widget.hide()
            self.imu_stats_widget.show()
            self.imu_stats_widget2.hide()
            self.calibrate_button.setVisible(True)
            self.calibrate_button.setEnabled(False)
            self.lpf_button.setVisible(False)
            self.imu_square_sound_timbre_widget.set_square_position(0.5, 0.5)
            if self.imu_enabled:
                self.imu_square_sound_timbre_widget.start_audio()
        elif method_text == "Method G":
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.show()
            self.imu_dual_square_widget.hide()
            self.imu_viewer_widget.hide()
            self.lpf_filter_test_widget.hide()
            self.imu_latency_widget.hide()
            self.imu_stats_widget.show()
            self.imu_stats_widget2.hide()
            self.calibrate_button.setVisible(True)
            self.calibrate_button.setEnabled(False)
            self.lpf_button.setVisible(False)
            self.imu_square_sound_file_widget.set_square_position(0.5, 0.5)
            if self.imu_enabled:
                print("Method G selected - starting audio automatically (IMU already running)")
                self.imu_square_sound_file_widget.start_audio()
            else:
                print("Method G selected - widget visible, audio will start when IMU is enabled")
        elif method_text == "IMU Viewer":
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.hide()
            self.imu_viewer_widget.show()
            self.lpf_filter_test_widget.hide()
            self.imu_latency_widget.hide()
            self.imu_stats_widget.hide()  # Hide stats widget - IMU Viewer has its own overview
            self.imu_stats_widget2.hide()
            self.calibrate_button.setVisible(True)
            self.calibrate_button.setEnabled(False)
            self.lpf_button.setVisible(False)
        elif method_text == "LPF Filter Test":
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.hide()
            self.imu_viewer_widget.hide()
            self.lpf_filter_test_widget.show()
            self.imu_latency_widget.hide()
            self.imu_stats_widget.hide()  # Hide stats widget
            self.imu_stats_widget2.hide()
            self.calibrate_button.setVisible(False)  # Hide calibrate button
            self.lpf_button.setVisible(True)  # Show LPF button in top bar
        elif method_text == "IMU Latency":
            self.method_a_help_button.setVisible(False)
            self.method_b_help_button.setVisible(False)
            self.imu_box_widget.hide()
            self.imu_square_widget.hide()
            self.imu_square_sound_widget.hide()
            self.imu_square_sound_loudness_widget.hide()
            self.imu_square_sound_timbre_widget.hide()
            self.imu_square_sound_file_widget.hide()
            self.imu_dual_square_widget.hide()
            self.imu_viewer_widget.hide()
            self.lpf_filter_test_widget.hide()
            self.imu_latency_widget.show()
            self.imu_stats_widget.hide()  # Hide stats widget
            self.imu_stats_widget2.hide()
            self.calibrate_button.setVisible(False)  # Hide calibrate button
            self.lpf_button.setVisible(False)  # Hide LPF button
    
    def _show_method_a_help(self):
        """Show help dialog for Blue Square #1."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Blue Square #1 - IMU Orientation Help")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Blue Square #1 - IMU Orientation")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)
        
        image_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "images", "axis.png")
        if os.path.exists(image_path):
            image_label = QLabel()
            pixmap = QPixmap(image_path)
            scaled_pixmap = pixmap.scaled(200, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image_label.setPixmap(scaled_pixmap)
            image_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(image_label)
        else:
            image_label = QLabel("(Image: axis.png not found)")
            image_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(image_label)
        
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
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        dialog.exec_()
    
    def _show_method_b_help(self):
        """Show help dialog for Method B."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Method B - Game Instructions")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Method B - Game Instructions")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)
        
        image_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "images", "axis.png")
        if os.path.exists(image_path):
            image_label = QLabel()
            pixmap = QPixmap(image_path)
            scaled_pixmap = pixmap.scaled(200, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image_label.setPixmap(scaled_pixmap)
            image_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(image_label)
        else:
            image_label = QLabel("(Image: axis.png not found)")
            image_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(image_label)
        
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
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        dialog.exec_()
    
    def _on_lpf_toggle(self):
        """Handle LPF filter toggle button click."""
        enabled = self.lpf_button.isChecked()
        cutoff = 5.0  # Default
        
        # Apply to appropriate widget based on current method
        if self.method == "LPF Filter Test" and self.lpf_filter_test_widget:
            self.lpf_filter_test_widget.set_lpf_enabled(enabled)
            cutoff = self.lpf_filter_test_widget.lpf_cutoff_hz
        elif self.method == "Method B" and self.imu_square_widget:
            self.imu_square_widget.set_lpf_enabled(enabled)
            cutoff = self.imu_square_widget.lpf_cutoff_hz
        
        # Update button text and style
        if enabled:
            self.lpf_button.setText(f"LPF: On ({cutoff:.1f} Hz)")
            self.lpf_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    padding: 8px 20px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #229954;
                }
            """)
        else:
            self.lpf_button.setText("LPF: Off")
            self.lpf_button.setStyleSheet("""
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
            """)
    
    def _on_calibrate(self):
        """Calibrate zero position from current IMU reading."""
        if not self.imu_reader or not self.imu_enabled:
            return
        
        from imu_viewer.models import ImuSample
        sample = self.imu_reader.get_sample(timeout=0.1)
        
        if sample and isinstance(sample, ImuSample):
            roll_deg, pitch_deg, yaw_deg = sample.angles_deg
            
            self.zero_roll = roll_deg
            self.zero_pitch = pitch_deg
            self.calibrated = True
            
            self.imu_box_widget.set_box_position(0.5, 0.5)
            self.imu_square_widget.set_square_position(0.5, 0.5)
            self.imu_square_sound_widget.set_square_position(0.5, 0.5)
            
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
            self.imu_box_widget.set_box_position(0.5, 0.5)
            self.imu_square_widget.set_square_position(0.5, 0.5)
            self.imu_dual_square_widget.set_blue_square_position(0.5, 0.5)
            self.imu_dual_square_widget.set_red_square_position(0.5, 0.5)
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
            
            # For Method E, also start second IMU reader on port2
            if self.method == "Method E":
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
            # Use fast polling for all methods (200 Hz) for low latency
            self.imu_timer.start(5)  # 200 Hz for very low latency
            
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
            
            if self.method == "Blue Square #1":
                self.calibrate_button.setEnabled(True)
            
            # Start audio for audio methods
            if self.method == "Pitch + Pan":
                self.imu_square_sound_widget.start_audio()
            elif self.method == "Method D":
                self.imu_square_sound_loudness_widget.start_audio()
            elif self.method == "Method F":
                self.imu_square_sound_timbre_widget.start_audio()
            elif self.method == "Method G":
                print("Starting Method G audio automatically (IMU started)")
                self.imu_square_sound_file_widget.start_audio()
            
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
        
        if self.imu_reader:
            self.imu_reader.stop()
            self.imu_reader = None
        
        if self.imu_reader2:
            self.imu_reader2.stop()
            self.imu_reader2 = None
        
        self.imu_enabled = False
        
        self.imu_box_widget.set_box_position(0.5, 0.5)
        self.imu_square_widget.set_square_position(0.5, 0.5)
        self.imu_square_sound_widget.set_square_position(0.5, 0.5)
        self.imu_square_sound_loudness_widget.set_square_position(0.5, 0.5)
        self.imu_square_sound_timbre_widget.set_square_position(0.5, 0.5)
        self.imu_dual_square_widget.set_blue_square_position(0.5, 0.5)
        self.imu_dual_square_widget.set_red_square_position(0.5, 0.5)
        self.imu_stats_widget.update_stats(None)
        self.imu_stats_widget2.update_stats(None)
        
        if self.method == "Pitch + Pan":
            self.imu_square_sound_widget.stop_audio()
        if self.method == "Method D":
            self.imu_square_sound_loudness_widget.stop_audio()
        if self.method == "Method F":
            self.imu_square_sound_timbre_widget.stop_audio()
        if self.method == "Method G":
            self.imu_square_sound_file_widget.stop_audio()
        
        self.usb_radio.setEnabled(True)
        self.wifi_ap_radio.setEnabled(True)
        self.wifi_sta_radio.setEnabled(True)
        
        self.calibrate_button.setEnabled(False)
        self.calibrated = False
        
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
        
        from imu_viewer.models import ImuSample
        sample = self.imu_reader.get_sample(timeout=0.0)
        
        if sample and isinstance(sample, ImuSample):
            # Update stats widget only if not IMU Viewer (which has its own overview)
            if self.method != "IMU Viewer":
                self.imu_stats_widget.update_stats(sample)
            
            roll_deg, pitch_deg, yaw_deg = sample.angles_deg
            
            # Update IMU Viewer widget if that method is selected
            if self.method == "IMU Viewer":
                self.imu_viewer_widget.update_sample(sample)
                return  # Early return - IMU Viewer handles everything
            
            # Update LPF Filter Test widget if that method is selected
            if self.method == "LPF Filter Test":
                self.lpf_filter_test_widget.update_sample(sample)
                return  # Early return - LPF Filter Test handles everything
            
            # Update IMU Latency widget if that method is selected
            if self.method == "IMU Latency":
                self.imu_latency_widget.update_sample(sample)
                return  # Early return - IMU Latency handles everything
            
            if self.method == "Blue Square #1":
                if self.calibrated:
                    roll_rel = roll_deg - self.zero_roll
                    pitch_rel = pitch_deg - self.zero_pitch
                    x_pos = 0.5 + (roll_rel / self.max_roll_deg)
                    y_pos = 0.5 - (pitch_rel / self.max_pitch_deg)
                    x_pos = max(0.0, min(1.0, x_pos))
                    y_pos = max(0.0, min(1.0, y_pos))
                else:
                    ax, ay, az = sample.accel_g
                    x_pos = 0.5 + (ax / 2.0)
                    x_pos = max(0.0, min(1.0, x_pos))
                    y_pos = 0.5 + ((az - 1.0) / 2.0)
                    y_pos = max(0.0, min(1.0, y_pos))
                self.imu_box_widget.set_box_position(x_pos, y_pos)
                
            elif self.method == "Method B":
                # Apply LPF filtering if enabled (handled in set_angles)
                self.imu_square_widget.set_angles(roll_deg, pitch_deg)
                # Use filtered angles for position mapping if LPF is enabled
                if self.imu_square_widget.lpf_enabled:
                    roll_to_use = self.imu_square_widget.roll_filtered
                    pitch_to_use = self.imu_square_widget.pitch_filtered
                else:
                    roll_to_use = roll_deg
                    pitch_to_use = pitch_deg
                x_pos, y_pos = self.imu_square_widget.map_tilt_to_position(roll_to_use, pitch_to_use)
                self.imu_square_widget.set_square_position(x_pos, y_pos)
            
            elif self.method == "Pitch + Pan":
                x_pos, y_pos = self.imu_square_sound_widget.map_tilt_to_position(roll_deg, pitch_deg)
                self.imu_square_sound_widget.set_square_position(x_pos, y_pos)
                self.imu_square_sound_widget.set_angles_for_audio(roll_deg, pitch_deg)
            
            elif self.method == "Method D":
                x_pos, y_pos = self.imu_square_sound_loudness_widget.map_tilt_to_position(roll_deg, pitch_deg)
                self.imu_square_sound_loudness_widget.set_square_position(x_pos, y_pos)
                self.imu_square_sound_loudness_widget.set_angles_for_audio(roll_deg, pitch_deg)
                az = sample.accel_g[2]
                self.imu_square_sound_loudness_widget.update_accel_z(az)
            
            elif self.method == "Method E":
                x_pos, y_pos = self.imu_dual_square_widget.map_tilt_to_position(roll_deg, pitch_deg)
                self.imu_dual_square_widget.set_blue_square_position(x_pos, y_pos)
                self.imu_dual_square_widget.set_blue_angles(roll_deg, pitch_deg)
                
                if self.imu_reader2:
                    sample2 = self.imu_reader2.get_sample(timeout=0.0)
                    if sample2 and isinstance(sample2, ImuSample):
                        self.imu_stats_widget2.update_stats(sample2)
                        roll_deg2, pitch_deg2, yaw_deg2 = sample2.angles_deg
                        x_pos2, y_pos2 = self.imu_dual_square_widget.map_tilt_to_position(roll_deg2, pitch_deg2)
                        self.imu_dual_square_widget.set_red_square_position(x_pos2, y_pos2)
                        self.imu_dual_square_widget.set_red_angles(roll_deg2, pitch_deg2)
                else:
                    self.imu_stats_widget2.update_stats(None)
            
            elif self.method == "Method F":
                x_pos, y_pos = self.imu_square_sound_timbre_widget.map_tilt_to_position(roll_deg, pitch_deg)
                self.imu_square_sound_timbre_widget.set_square_position(x_pos, y_pos)
                self.imu_square_sound_timbre_widget.set_angles(roll_deg, pitch_deg)
                self.imu_square_sound_timbre_widget.set_angles_for_audio(roll_deg, pitch_deg, yaw_deg)
                self.imu_square_sound_timbre_widget._update_display()
            
            elif self.method == "Method G":
                x_pos, y_pos = self.imu_square_sound_file_widget.map_tilt_to_position(roll_deg, pitch_deg)
                self.imu_square_sound_file_widget.set_square_position(x_pos, y_pos)
                self.imu_square_sound_file_widget.set_angles(roll_deg, pitch_deg)
                self.imu_square_sound_file_widget.set_angles_for_audio(roll_deg, pitch_deg, yaw_deg)
                self.imu_square_sound_file_widget._update_display()
    
    def cleanup(self):
        """Clean up resources when tab is switched away."""
        self._stop_imu()
        # Cleanup IMU Latency widget (closes CSV file)
        if self.imu_latency_widget:
            self.imu_latency_widget.cleanup()
    
    def resume(self):
        """Resume widget when tab is switched to."""
        pass

