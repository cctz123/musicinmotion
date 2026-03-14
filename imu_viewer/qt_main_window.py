"""PyQt5 main window for IMU Viewer."""
import sys
import csv
import time
from dataclasses import replace
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for older Python versions
    from backports.zoneinfo import ZoneInfo
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QStatusBar, QMessageBox, QDialog, QFrame, QSplitter
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QIcon

try:
    from .data_sources import SerialImuReader, WifiImuReader, WifiApImuReader, ImuDataSource
    from .data_sources.serial_reader import SerialImuReader as SerialReader
    from .models import ImuSample
    from .qt_visualizer import DashboardWidget, DebugWidget
    from .wifi_config import get_local_ip
    from .config_loader import load_config
    from .settings_dialog import SettingsDialog
except ImportError:
    from data_sources import SerialImuReader, WifiImuReader, WifiApImuReader, ImuDataSource
    from data_sources.serial_reader import SerialImuReader as SerialReader
    from models import ImuSample
    from qt_visualizer import DashboardWidget, DebugWidget
    from wifi_config import get_local_ip
    from config_loader import load_config
    from settings_dialog import SettingsDialog


class DataSourceSignals(QObject):
    """Signals for data source events."""
    sample_received = pyqtSignal(object)  # Emits ImuSample
    error_occurred = pyqtSignal(str)  # Emits error message


class ImuViewerMainWindow(QMainWindow):
    """Main window for IMU Viewer application."""

    def __init__(self, args):
        """Initialize the main window."""
        super().__init__()
        self.args = args
        self.current_mode = "USB"  # "USB", "WIFI", or "WIFI_AP"
        self.data_source: Optional[ImuDataSource] = None
        self.serial_reader: Optional[SerialReader] = None
        self.csv_file = None
        self.csv_writer = None
        self.signals = DataSourceSignals()
        # Calibration (like Prototype A in motion-app): zero pose for relative angles
        self.calibrated = False
        self.zero_roll: Optional[float] = None
        self.zero_pitch: Optional[float] = None
        self.zero_yaw: Optional[float] = None
        self.latest_sample: Optional[ImuSample] = None

        # Load Wi-Fi config from file
        config = load_config()
        wifi_cfg = config.get("wifi", {})
        
        # Initialize Wi-Fi config tuple from file
        # server_ip is always determined dynamically from current local IP
        self.wifi_config: Optional[Tuple[str, str, str, bool, int]] = (
            wifi_cfg.get("ssid", "kumquat"),
            wifi_cfg.get("password", "5555512121"),
            get_local_ip(),  # Always use current local IP
            wifi_cfg.get("use_tcp", False),  # Default to UDP
            wifi_cfg.get("port", 1399)
        )
        
        # Connect signals
        self.signals.sample_received.connect(self._on_sample_received)
        self.signals.error_occurred.connect(self._on_error)
        
        self._init_ui()
        self._setup_csv_logging()
        
        # Timer for polling data source
        self.data_timer = QTimer(self)
        self.data_timer.timeout.connect(self._poll_data_source)
        self.data_timer.start(33)  # ~30 Hz
        
        # Start in requested mode (from command line or .imuconfig)
        startup_mode = getattr(self.args, 'mode', 'usb')
        # Set current_mode and update button colors to match before connecting
        if startup_mode == 'ap':
            self.current_mode = "WIFI_AP"
        elif startup_mode == 'sta':
            self.current_mode = "WIFI"
        else:
            self.current_mode = "USB"
        self._update_mode_buttons()
        # Then start the connection for the chosen mode
        if startup_mode == 'ap':
            self._switch_to_wifi_ap_mode()
        elif startup_mode == 'sta':
            self._switch_to_wifi_sta_mode()
        else:
            self._try_startup_connection()

    def _init_ui(self):
        """Initialize the UI."""
        self.setWindowTitle("WT901WIFI IMU Viewer")
        self.setMinimumSize(1400, 900)
        
        # Set grey background for main window
        self.setStyleSheet("QMainWindow { background-color: #f5f5f5; }")
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # Top strip: Title and mode buttons (no box, just grey background)
        top_bar = QWidget()
        top_bar.setStyleSheet("background-color: transparent;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)
        
        title_label = QLabel("WT901WIFI IMU Viewer")
        title_label.setFont(QFont("Arial", 18, QFont.Bold))
        title_label.setStyleSheet("color: #2c3e50;")
        top_layout.addWidget(title_label)
        
        top_layout.addStretch()
        
        # Mode buttons
        self.usb_button = QPushButton("USB Serial")
        self.usb_button.setCheckable(True)
        self.usb_button.setChecked(True)
        self.usb_button.clicked.connect(self._on_usb_mode)
        # Initial USB button style (will be updated by _update_mode_buttons)
        self.usb_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:checked {
                background-color: #27ae60;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:checked:hover {
                background-color: #229954;
            }
        """)
        
        self.wifi_sta_button = QPushButton("WiFi STA")
        self.wifi_sta_button.setCheckable(True)
        self.wifi_sta_button.clicked.connect(self._on_wifi_sta_mode)
        self.wifi_sta_button.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:checked {
                background-color: #27ae60;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
            QPushButton:checked:hover {
                background-color: #229954;
            }
        """)
        
        self.wifi_ap_button = QPushButton("Wi-Fi AP")
        self.wifi_ap_button.setCheckable(True)
        self.wifi_ap_button.clicked.connect(self._on_wifi_ap_mode)
        self.wifi_ap_button.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:checked {
                background-color: #27ae60;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
            QPushButton:checked:hover {
                background-color: #229954;
            }
        """)
        
        # LPF Filter toggle button
        self.lpf_button = QPushButton("LPF: Off")
        self.lpf_button.setCheckable(True)
        self.lpf_button.setChecked(False)
        self.lpf_button.clicked.connect(self._on_lpf_toggle)
        self.lpf_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
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

        # Calibrate button (set current pose as zero for relative angle display)
        self.calibrate_button = QPushButton("Calibrate")
        self.calibrate_button.setToolTip("Set current orientation as zero (dashboard shows relative angles)")
        self.calibrate_button.clicked.connect(self._on_calibrate)
        self.calibrate_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:pressed {
                background-color: #7d3c98;
            }
        """)
        
        # Log Data button
        self.log_button = QPushButton("Log Data")
        self.log_button.clicked.connect(self._on_log_toggle)
        self.log_button.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        
        # Settings button (with gear icon)
        self.settings_button = QPushButton("⚙")
        self.settings_button.setToolTip("Settings")
        self.settings_button.clicked.connect(self._on_settings)
        self.settings_button.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #2c3e50;
            }
        """)
        
        # Exit button
        self.exit_button = QPushButton("Exit")
        self.exit_button.clicked.connect(self.close)
        self.exit_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        
        top_layout.addWidget(self.usb_button)
        top_layout.addWidget(self.wifi_sta_button)
        top_layout.addWidget(self.wifi_ap_button)
        top_layout.addWidget(self.lpf_button)
        top_layout.addWidget(self.calibrate_button)
        top_layout.addWidget(self.log_button)
        top_layout.addWidget(self.settings_button)
        top_layout.addWidget(self.exit_button)
        
        main_layout.addWidget(top_bar)
        
        # Create splitter for resizable sections
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)  # Prevent sections from being collapsed completely
        
        # Middle section: Dashboard in white box
        dashboard_frame = QFrame()
        dashboard_frame.setFrameShape(QFrame.StyledPanel)
        dashboard_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
        """)
        dashboard_layout = QVBoxLayout(dashboard_frame)
        dashboard_layout.setContentsMargins(10, 10, 10, 10)
        
        self.dashboard = DashboardWidget(
            history_seconds=self.args.history_seconds,
            update_rate=self.args.update_rate
        )
        dashboard_layout.addWidget(self.dashboard)
        
        splitter.addWidget(dashboard_frame)
        
        # Bottom section: Debug panel in white box
        debug_frame = QFrame()
        debug_frame.setFrameShape(QFrame.StyledPanel)
        debug_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
        """)
        debug_layout = QVBoxLayout(debug_frame)
        debug_layout.setContentsMargins(10, 10, 10, 10)
        
        self.debug_widget = DebugWidget()
        debug_layout.addWidget(self.debug_widget)
        
        splitter.addWidget(debug_frame)
        
        # Set initial sizes (dashboard gets more space initially)
        # Debug section starts at 3/4 of its previous height (200 * 0.75 = 150)
        splitter.setSizes([600, 150])  # Dashboard: 600, Debug: 150 (3/4 of previous 200)
        splitter.setStretchFactor(0, 1)  # Dashboard can grow
        splitter.setStretchFactor(1, 1)  # Debug can grow too
        
        main_layout.addWidget(splitter, 1)  # Give splitter stretch factor
        
        # Status bar
        self.statusBar().showMessage("Ready - USB Serial Mode")

    def _setup_csv_logging(self):
        """Setup CSV logging if requested via command line."""
        if self.args.log:
            csv_path = Path(self.args.log)
            self.csv_file = open(csv_path, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(ImuSample.csv_header().split(','))
    
    def _on_log_toggle(self):
        """Toggle logging on/off via button."""
        if self.csv_file is None:
            # Start logging
            self._start_logging()
        else:
            # Stop logging
            self._stop_logging()
    
    def _start_logging(self):
        """Start logging to a new file with Eastern Time datetime in filename."""
        try:
            # Get Eastern Time
            eastern = ZoneInfo('US/Eastern')
            now_et = datetime.now(eastern)
            
            # Create filename with Eastern Time datetime
            filename = f"imu_data_{now_et.strftime('%Y%m%d_%H%M%S')}_ET.csv"
            csv_path = Path(filename)
            
            # Open file and write header
            self.csv_file = open(csv_path, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(ImuSample.csv_header().split(','))
            
            # Update button
            self.log_button.setText("Stop Logging")
            self.log_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            
            self.statusBar().showMessage(f"Logging to {filename}")
            print(f"Started logging to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start logging:\n{e}")
            print(f"Error starting logging: {e}")
    
    def _stop_logging(self):
        """Stop logging and close the file."""
        try:
            if self.csv_file:
                filename = self.csv_file.name
                self.csv_file.close()
                self.csv_file = None
                self.csv_writer = None
                
                # Update button
                self.log_button.setText("Log Data")
                self.log_button.setStyleSheet("""
                    QPushButton {
                        background-color: #f39c12;
                        color: white;
                        border: none;
                        padding: 10px 25px;
                        border-radius: 5px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #e67e22;
                    }
                """)
                
                self.statusBar().showMessage(f"Stopped logging. File saved: {filename}")
                print(f"Stopped logging. File saved: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to stop logging:\n{e}")
            print(f"Error stopping logging: {e}")

    def _on_usb_mode(self):
        """Handle USB mode button click."""
        if self.current_mode == "USB":
            return
        self._switch_to_usb_mode()

    def _on_wifi_sta_mode(self):
        """Handle WiFi STA mode button click."""
        if self.current_mode == "WIFI":
            return
        
        self._switch_to_wifi_sta_mode()
    
    def _on_wifi_ap_mode(self):
        """Handle Wi-Fi AP mode button click."""
        if self.current_mode == "WIFI_AP":
            return
        
        self._switch_to_wifi_ap_mode()
    
    def _on_lpf_toggle(self):
        """Handle LPF filter toggle button click."""
        enabled = self.lpf_button.isChecked()
        if self.dashboard:
            self.dashboard.set_lpf_enabled(enabled)
            cutoff = self.dashboard.lpf_cutoff_hz
        else:
            cutoff = 5.0  # Default if dashboard not available
        
        # Update button text and style
        if enabled:
            self.lpf_button.setText(f"LPF: On ({cutoff:.1f} Hz)")
            self.lpf_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
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
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #8e44ad;
                }
            """)
    
    def _on_settings(self):
        """Handle Settings button click - open settings dialog."""
        dialog = SettingsDialog(self)
        result = dialog.exec_()
        
        if result == QDialog.Accepted and dialog.config_changed:
            # Reload config and restart app
            QMessageBox.information(
                self, "Settings Saved",
                "Configuration saved. The application will restart with new settings."
            )
            # Restart the application
            self._restart_app()
    
    def _restart_app(self):
        """Restart the application with new config."""
        # Stop current data source
        if self.data_source:
            self.data_source.stop()
            self.data_source = None
        
        # Reload config
        config = load_config()
        self.args.port = config["usb"]["port"]
        
        # Update Wi-Fi config
        wifi_cfg = config.get("wifi", {})
        self.wifi_config = (
            wifi_cfg.get("ssid", "kumquat"),
            wifi_cfg.get("password", "5555512121"),
            get_local_ip(),
            wifi_cfg.get("use_tcp", False),  # Default to UDP
            wifi_cfg.get("port", 1399)
        )
        
        # Try to reconnect
        self._try_startup_connection()

    def _update_mode_buttons(self):
        """Update mode button styles based on current mode."""
        # Reset all buttons
        self.usb_button.setChecked(False)
        self.wifi_sta_button.setChecked(False)
        self.wifi_ap_button.setChecked(False)
        
        # Grey out inactive buttons and highlight active one
        if self.current_mode == "USB":
            self.usb_button.setChecked(True)
            # Restore normal USB button style
            self.usb_button.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:checked {
                    background-color: #27ae60;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:checked:hover {
                    background-color: #229954;
                }
            """)
            # Grey out WiFi buttons
            self.wifi_sta_button.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #7f8c8d;
                }
            """)
            self.wifi_ap_button.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #7f8c8d;
                }
            """)
        elif self.current_mode == "WIFI":
            self.wifi_sta_button.setChecked(True)
            # Grey out USB button
            self.usb_button.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #7f8c8d;
                }
            """)
            # Restore normal WiFi STA button style
            self.wifi_sta_button.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: white;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:checked {
                    background-color: #27ae60;
                }
                QPushButton:hover {
                    background-color: #7f8c8d;
                }
                QPushButton:checked:hover {
                    background-color: #229954;
                }
            """)
            # Grey out AP button
            self.wifi_ap_button.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #7f8c8d;
                }
            """)
        elif self.current_mode == "WIFI_AP":
            self.wifi_ap_button.setChecked(True)
            # Grey out USB button
            self.usb_button.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #7f8c8d;
                }
            """)
            # Grey out STA button
            self.wifi_sta_button.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #7f8c8d;
                }
            """)
            # Restore normal WiFi AP button style
            self.wifi_ap_button.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: white;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:checked {
                    background-color: #27ae60;
                }
                QPushButton:hover {
                    background-color: #7f8c8d;
                }
                QPushButton:checked:hover {
                    background-color: #229954;
                }
            """)
    
    def _try_startup_connection(self):
        """Try to connect via USB first, then Wi-Fi if USB is unavailable."""
        # Try USB first
        try:
            # USB/Serial is hardcoded to 9600 baud - device doesn't accept other rates
            self.data_source = SerialImuReader(self.args.port, 9600)
            self.data_source.start()
            self.current_mode = "USB"
            # Update button styles
            self._update_mode_buttons()
            self.statusBar().showMessage(f"USB Serial Mode - Port: {self.args.port}, Baud: 9600")
            print("Started in USB Serial mode")
            return
        except Exception as e:
            print(f"USB connection failed: {e}")
            print("Checking Wi-Fi port for data...")
        
        # USB failed, try Wi-Fi
        if self.wifi_config is None:
            print("No Wi-Fi configuration available")
            self.statusBar().showMessage("USB unavailable - No Wi-Fi config")
            return
        
        # Try Wi-Fi mode
        ssid, password, server_ip, use_tcp, port = self.wifi_config
        try:
            self.data_source = WifiImuReader(use_tcp=use_tcp, port=port)
            self.data_source.start()
            
            # Give it a moment to see if data comes through
            time.sleep(2)
            
            # Check if we got any samples
            sample = self.data_source.get_sample(timeout=0.1)
            if sample:
                # Data is coming through Wi-Fi, switch to Wi-Fi mode
                self.current_mode = "WIFI"
                self._update_mode_buttons()
                protocol = "TCP" if use_tcp else "UDP"
                self.statusBar().showMessage(f"WiFi STA Mode - {protocol} on port {port} - Auto-detected")
                print(f"Auto-switched to WiFi STA mode ({protocol} on port {port}) - data detected")
            else:
                # No data yet, but keep trying Wi-Fi
                self.current_mode = "WIFI"
                self._update_mode_buttons()
                protocol = "TCP" if use_tcp else "UDP"
                self.statusBar().showMessage(f"WiFi STA Mode - {protocol} on port {port} - Waiting for connection...")
                print(f"Started in WiFi STA mode ({protocol} on port {port}) - waiting for data")
        except Exception as e:
            print(f"Wi-Fi connection also failed: {e}")
            self.statusBar().showMessage("USB unavailable - Wi-Fi connection failed")
            # Keep data_source as None, user can manually switch modes
    
    def _switch_to_usb_mode(self):
        """Switch to USB serial mode."""
        # Stop current data source
        if self.data_source:
            self.data_source.stop()
            self.data_source = None

        # Start USB serial reader
        try:
            # USB/Serial is hardcoded to 9600 baud - device doesn't accept other rates
            self.data_source = SerialImuReader(self.args.port, 9600)
            self.data_source.start()
            self.current_mode = "USB"
            # Update button styles
            self._update_mode_buttons()
            self.statusBar().showMessage(f"USB Serial Mode - Port: {self.args.port}, Baud: 9600")
            print("Switched to USB Serial mode")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to switch to USB mode:\n{e}")
            print(f"Error switching to USB mode: {e}")

    def _switch_to_wifi_sta_mode(self):
        """Switch to WiFi STA mode using stored configuration."""
        # Load from config file
        config = load_config()
        wifi_cfg = config.get("wifi", {})
        self.wifi_config = (
            wifi_cfg.get("ssid", "kumquat"),
            wifi_cfg.get("password", "5555512121"),
            get_local_ip(),  # Always use current local IP
            wifi_cfg.get("use_tcp", False),  # Default to UDP
            wifi_cfg.get("port", 1399)
        )

        ssid, password, server_ip, use_tcp, port = self.wifi_config

        # Stop current data source
        if self.data_source:
            self.data_source.stop()
            self.data_source = None

        # Start Wi-Fi reader
        try:
            self.data_source = WifiImuReader(use_tcp=use_tcp, port=port)
            self.data_source.start()
            self.current_mode = "WIFI"
            self._update_mode_buttons()
            protocol = "TCP" if use_tcp else "UDP"
            self.statusBar().showMessage(f"WiFi STA Mode - {protocol} on port {port} - Waiting for connection...")
            print(f"Switched to WiFi STA mode ({protocol} on port {port})")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start WiFi STA mode:\n{e}")
            print(f"Error switching to WiFi STA mode: {e}")
            # Try to fall back to USB
            self._switch_to_usb_mode()
    
    def _switch_to_wifi_ap_mode(self):
        """Switch to Wi-Fi AP mode using settings from .imuconfig."""
        # Load AP config from file
        config = load_config()
        
        if "ap" not in config:
            error_msg = (
                "AP mode settings not found in .imuconfig.\n"
                "Please add an 'ap' section with 'ssid', 'ip', and 'port' fields."
            )
            if hasattr(self, 'wifi_ap_button'):
                QMessageBox.warning(self, "Configuration Error", error_msg)
                self.wifi_ap_button.setChecked(False)
            else:
                # Called from startup, show error and fall back to USB
                print(f"Error: {error_msg}")
                QMessageBox.warning(self, "Configuration Error", error_msg)
                self._try_startup_connection()
            return
        
        ap_cfg = config["ap"]
        device_ip = ap_cfg.get("ip")
        device_port = ap_cfg.get("port")
        ssid = ap_cfg.get("ssid", "WT901-xxxx")
        
        if not device_ip or not device_port:
            error_msg = (
                "AP mode settings incomplete in .imuconfig.\n"
                "Required fields: 'ip' and 'port'"
            )
            if hasattr(self, 'wifi_ap_button'):
                QMessageBox.warning(self, "Configuration Error", error_msg)
                self.wifi_ap_button.setChecked(False)
            else:
                # Called from startup, show error and fall back to USB
                print(f"Error: {error_msg}")
                QMessageBox.warning(self, "Configuration Error", error_msg)
                self._try_startup_connection()
            return
        
        # Stop current data source
        if self.data_source:
            self.data_source.stop()
            self.data_source = None
        
        # Start Wi-Fi AP reader
        try:
            self.data_source = WifiApImuReader(device_ip=device_ip, device_port=device_port)
            self.data_source.start()
            self.current_mode = "WIFI_AP"
            if hasattr(self, 'wifi_ap_button'):
                self._update_mode_buttons()
            self.statusBar().showMessage(f"Wi-Fi AP Mode - {device_ip}:{device_port} (SSID: {ssid}) - Waiting for data...")
            print(f"Switched to Wi-Fi AP mode - {device_ip}:{device_port} (SSID: {ssid})")
        except Exception as e:
            error_msg = f"Failed to start Wi-Fi AP mode:\n{e}"
            QMessageBox.critical(self, "Error", error_msg)
            print(f"Error switching to Wi-Fi AP mode: {e}")
            if hasattr(self, 'wifi_ap_button'):
                self.wifi_ap_button.setChecked(False)
            # Try to fall back to USB
            self._try_startup_connection()


    def _poll_data_source(self):
        """Poll the data source for new samples."""
        if self.data_source:
            sample = self.data_source.get_sample(timeout=0.0)
            if sample:
                self.signals.sample_received.emit(sample)

    def _on_calibrate(self):
        """Set current orientation as zero (like Prototype A in motion-app). Dashboard will show relative angles."""
        if self.latest_sample is None:
            self.statusBar().showMessage("No data yet — move the device and try again", 3000)
            return
        roll, pitch, yaw = self.latest_sample.angles_deg
        self.zero_roll = roll
        self.zero_pitch = pitch
        self.zero_yaw = yaw
        self.calibrated = True
        self.statusBar().showMessage(
            f"Calibrated: roll={roll:.1f}° pitch={pitch:.1f}° yaw={yaw:.1f}° (display shows relative angles)", 5000
        )

    def _on_sample_received(self, sample: ImuSample):
        """Handle received sample."""
        self.latest_sample = sample
        display_sample = sample
        if self.calibrated and self.zero_roll is not None and self.zero_pitch is not None and self.zero_yaw is not None:
            roll, pitch, yaw = sample.angles_deg
            rel_roll = roll - self.zero_roll
            rel_pitch = pitch - self.zero_pitch
            rel_yaw = (yaw - self.zero_yaw + 360.0) % 360.0
            display_sample = replace(sample, angles_deg=(rel_roll, rel_pitch, rel_yaw))
        if self.dashboard:
            self.dashboard.update_sample(display_sample)
        if self.debug_widget:
            self.debug_widget.update_sample(display_sample)
        if self.csv_writer:
            self.csv_writer.writerow(sample.to_csv_row().split(','))
            if self.csv_file:
                self.csv_file.flush()

    def _on_error(self, error_msg: str):
        """Handle error from data source."""
        self.statusBar().showMessage(f"Error: {error_msg}", 5000)
        print(f"Error: {error_msg}")

    def closeEvent(self, event):
        """Handle window close event."""
        # Cleanup
        if self.data_source:
            self.data_source.stop()
        if self.serial_reader:
            self.serial_reader.stop()
        # Stop logging if active
        if self.csv_file:
            self._stop_logging()
        event.accept()
