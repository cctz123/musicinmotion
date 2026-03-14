"""Main application window."""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QTabWidget, QCheckBox, QPushButton
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
from .tabs import (
    MusicInMotionWidget,
    HandsDemoWidget,
    YogaPoseDetectorWidget,
    MusicInMotionTabWidget
)


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

        # Camera blackout checkbox (checked by default to turn camera off)
        self.camera_checkbox = QCheckBox("Turn off camera")
        self.camera_checkbox.setChecked(True)  # Camera off by default
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

        # Create and add tabs in order
        self.music_widget = MusicInMotionWidget()
        self.tabs.addTab(self.music_widget, "IMU Prototypes")
        self.current_active_widget = self.music_widget

        self.hands_widget = HandsDemoWidget()
        self.tabs.addTab(self.hands_widget, "MP Hands Demo")

        self.yoga_widget = YogaPoseDetectorWidget()
        self.tabs.addTab(self.yoga_widget, "Yoga Pose Detector")

        self.music_in_motion_widget = MusicInMotionTabWidget()
        self.tabs.addTab(self.music_in_motion_widget, "Music in Motion")

        # Connect tab change signal
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
        if self.music_in_motion_widget and hasattr(self.music_in_motion_widget, 'set_camera_blackout'):
            self.music_in_motion_widget.set_camera_blackout(blackout)

    def _on_tab_changed(self, index: int):
        """Handle tab changes - cleanup previous widget, resume new one."""
        # Cleanup previous active widget
        if self.current_active_widget:
            if hasattr(self.current_active_widget, 'cleanup'):
                self.current_active_widget.cleanup()

        # Determine new active widget
        if index == 0:  # IMU Prototypes
            self.current_active_widget = self.music_widget
        elif index == 1:  # MP Hands Demo
            self.current_active_widget = self.hands_widget
        elif index == 2:  # Yoga Pose Detector
            self.current_active_widget = self.yoga_widget
        else:  # Music in Motion
            self.current_active_widget = self.music_in_motion_widget

        # Resume new active widget
        if self.current_active_widget and hasattr(self.current_active_widget, 'resume'):
            self.current_active_widget.resume()

    def closeEvent(self, event):
        """Clean up all resources on window close."""
        if self.hands_widget and hasattr(self.hands_widget, 'cleanup'):
            self.hands_widget.cleanup()
        if self.yoga_widget and hasattr(self.yoga_widget, 'cleanup'):
            self.yoga_widget.cleanup()
        event.accept()

