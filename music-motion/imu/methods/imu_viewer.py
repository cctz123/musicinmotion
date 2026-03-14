"""IMU Viewer method widget - combines dashboard and debug displays."""

import csv
from pathlib import Path
from datetime import datetime
from typing import Optional
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QSplitter
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

# Import from imu_viewer (assumes imu_viewer is in Python path)
from imu_viewer.qt_visualizer import DashboardWidget, DebugWidget
from imu_viewer.models import ImuSample


class ImuViewerWidget(QWidget):
    """IMU Viewer widget combining dashboard and debug displays."""
    
    def __init__(self, parent=None):
        """Initialize IMU Viewer widget."""
        super().__init__(parent)
        
        # CSV logging state
        self.csv_file = None
        self.csv_writer = None
        
        # LPF state
        self.lpf_enabled = False
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Top controls bar - buttons hidden per user request
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)
        
        # LPF Filter toggle button (hidden)
        self.lpf_button = QPushButton("LPF: Off")
        self.lpf_button.setCheckable(True)
        self.lpf_button.setChecked(False)
        self.lpf_button.clicked.connect(self._on_lpf_toggle)
        self.lpf_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 11px;
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
        self.lpf_button.hide()  # Hidden per user request
        controls_layout.addWidget(self.lpf_button)
        
        # Log Data button (hidden)
        self.log_button = QPushButton("Log Data")
        self.log_button.clicked.connect(self._on_log_toggle)
        self.log_button.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        self.log_button.hide()  # Hidden per user request
        controls_layout.addWidget(self.log_button)
        
        controls_layout.addStretch()
        main_layout.addLayout(controls_layout)
        
        # Create splitter for resizable sections
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        
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
            history_seconds=20.0,
            update_rate=30.0
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
        
        # Set initial sizes (dashboard gets more space)
        splitter.setSizes([600, 150])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter, 1)
    
    def _on_lpf_toggle(self):
        """Handle LPF filter toggle button click."""
        enabled = self.lpf_button.isChecked()
        if self.dashboard:
            self.dashboard.set_lpf_enabled(enabled)
            cutoff = self.dashboard.lpf_cutoff_hz
        else:
            cutoff = 5.0
        
        self.lpf_enabled = enabled
        
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
                    font-size: 11px;
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
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #8e44ad;
                }
            """)
    
    def _on_log_toggle(self):
        """Toggle logging on/off via button."""
        if self.csv_file is None:
            self._start_logging()
        else:
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
                    padding: 8px 20px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            
            print(f"Started logging to {filename}")
        except Exception as e:
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
                        padding: 8px 20px;
                        border-radius: 5px;
                        font-weight: bold;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: #e67e22;
                    }
                """)
                
                print(f"Stopped logging. File saved: {filename}")
        except Exception as e:
            print(f"Error stopping logging: {e}")
    
    def update_sample(self, sample: ImuSample):
        """Update with new IMU sample."""
        if self.dashboard:
            self.dashboard.update_sample(sample)
        
        if self.debug_widget:
            self.debug_widget.update_sample(sample)
        
        # Log to CSV if enabled
        if self.csv_writer:
            self.csv_writer.writerow(sample.to_csv_row().split(','))
            if self.csv_file:
                self.csv_file.flush()
    
    def cleanup(self):
        """Clean up resources."""
        if self.csv_file:
            self._stop_logging()
