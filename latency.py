#!/usr/bin/env python3
"""Latency measurement tool for IMU data.

Press the button with one hand while jerking the IMU with the other.
The tool will detect the movement and calculate latency from button press to IMU data change.
"""

import sys
import csv
import time
from pathlib import Path
from datetime import datetime
from collections import deque
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QMessageBox, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from imu_viewer.config_loader import load_config
from imu_viewer.data_sources import SerialImuReader, WifiImuReader, WifiApImuReader
from imu_viewer.models import ImuSample


class LatencyMeasurementWindow(QMainWindow):
    """Window for measuring IMU latency."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IMU Latency Measurement")
        self.setMinimumSize(600, 500)
        
        # IMU data source
        self.data_source = None
        self.data_timer = QTimer(self)
        self.data_timer.timeout.connect(self._poll_imu)
        self.data_timer.start(5)  # Poll at 200 Hz for very low latency
        
        # IMU mode
        config = load_config()
        default_mode = config.get("mode", "usb").lower()
        self.current_mode = "USB" if default_mode == "usb" else "WIFI_AP" if default_mode == "ap" else "USB"
        
        # Measurement state
        self.measurement_active = False
        self.button_press_time = None
        self.frozen_accel = None  # Acceleration frozen at button press
        self.current_accel = 0.0  # Current acceleration (updates continuously)
        self.trials = []
        self.trial_count = 0
        
        # Acceleration spike detection
        self.accel_threshold = 0.5  # g - threshold for detecting movement
        self.movement_detected = False
        self.movement_time = None
        
        # CSV logging
        self.csv_file = None
        self.csv_writer = None
        self._setup_csv()
        
        self._init_ui()
        self._start_imu()
    
    def _setup_csv(self):
        """Setup CSV file for logging."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_path = Path(f"latency_measurements_{timestamp}.csv")
        
        self.csv_file = open(csv_path, 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow([
            'Trial', 'Button_Press_Time', 'Movement_Detected_Time', 
            'Latency_ms', 'Frozen_Accel_g', 'Peak_Accel_g'
        ])
        print(f"Logging to: {csv_path}")
    
    def _init_ui(self):
        """Initialize the UI."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("IMU Latency Measurement")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(title)
        
        # Instructions
        instructions = QLabel(
            "1. Hold IMU in one hand\n"
            "2. Press 'Start Measurement' button with other hand\n"
            "3. Immediately jerk/shake the IMU\n"
            "4. Latency will be calculated and logged"
        )
        instructions.setFont(QFont("Arial", 11))
        layout.addWidget(instructions)
        
        # Mode selection radio buttons
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Connection Mode:")
        mode_label.setFont(QFont("Arial", 11, QFont.Bold))
        mode_layout.addWidget(mode_label)
        
        self.mode_button_group = QButtonGroup(self)
        
        self.usb_radio = QRadioButton("USB")
        self.usb_radio.setChecked(self.current_mode == "USB")
        self.usb_radio.setFont(QFont("Arial", 11))
        self.usb_radio.toggled.connect(self._on_mode_changed)
        self.mode_button_group.addButton(self.usb_radio, 0)
        mode_layout.addWidget(self.usb_radio)
        
        self.ap_radio = QRadioButton("WiFi AP")
        self.ap_radio.setChecked(self.current_mode == "WIFI_AP")
        self.ap_radio.setFont(QFont("Arial", 11))
        self.ap_radio.toggled.connect(self._on_mode_changed)
        self.mode_button_group.addButton(self.ap_radio, 1)
        mode_layout.addWidget(self.ap_radio)
        
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # Status display
        self.status_label = QLabel("Ready - Press button to start measurement")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        layout.addWidget(self.status_label)
        
        # Acceleration display - two numbers
        accel_layout = QVBoxLayout()
        accel_layout.setSpacing(5)
        
        # Frozen acceleration (at button press)
        frozen_layout = QHBoxLayout()
        frozen_label = QLabel("Frozen (at button press):")
        frozen_label.setFont(QFont("Arial", 11, QFont.Bold))
        frozen_layout.addWidget(frozen_label)
        
        self.frozen_accel_display = QLabel("--- g")
        self.frozen_accel_display.setFont(QFont("Arial", 14, QFont.Bold))
        self.frozen_accel_display.setStyleSheet("padding: 8px; background-color: #fff3cd; border: 2px solid #ffc107; border-radius: 5px; min-width: 100px;")
        self.frozen_accel_display.setAlignment(Qt.AlignCenter)
        frozen_layout.addWidget(self.frozen_accel_display)
        frozen_layout.addStretch()
        accel_layout.addLayout(frozen_layout)
        
        # Current acceleration (live)
        current_layout = QHBoxLayout()
        current_label = QLabel("Current (live):")
        current_label.setFont(QFont("Arial", 11, QFont.Bold))
        current_layout.addWidget(current_label)
        
        self.current_accel_display = QLabel("0.000 g")
        self.current_accel_display.setFont(QFont("Arial", 14, QFont.Bold))
        self.current_accel_display.setStyleSheet("padding: 8px; background-color: #ffffff; border: 2px solid #3498db; border-radius: 5px; min-width: 100px;")
        self.current_accel_display.setAlignment(Qt.AlignCenter)
        current_layout.addWidget(self.current_accel_display)
        current_layout.addStretch()
        accel_layout.addLayout(current_layout)
        
        # Difference display
        diff_layout = QHBoxLayout()
        diff_label = QLabel("Difference:")
        diff_label.setFont(QFont("Arial", 11, QFont.Bold))
        diff_layout.addWidget(diff_label)
        
        self.diff_display = QLabel("--- g")
        self.diff_display.setFont(QFont("Arial", 12))
        self.diff_display.setStyleSheet("padding: 5px; color: #7f8c8d;")
        diff_layout.addWidget(self.diff_display)
        diff_layout.addStretch()
        accel_layout.addLayout(diff_layout)
        
        layout.addLayout(accel_layout)
        
        # Trial counter
        self.trial_label = QLabel("Trials: 0")
        self.trial_label.setFont(QFont("Arial", 11, QFont.Bold))
        layout.addWidget(self.trial_label)
        
        # Button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.measure_button = QPushButton("Start Measurement")
        self.measure_button.setFont(QFont("Arial", 14, QFont.Bold))
        self.measure_button.setMinimumSize(200, 60)
        self.measure_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
        """)
        self.measure_button.clicked.connect(self._on_button_press)
        button_layout.addWidget(self.measure_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Results display
        results_label = QLabel("Recent Measurements:")
        results_label.setFont(QFont("Arial", 11, QFont.Bold))
        layout.addWidget(results_label)
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(150)
        self.results_text.setFont(QFont("Courier", 10))
        layout.addWidget(self.results_text)
        
        # Stats
        self.stats_label = QLabel("Average Latency: N/A")
        self.stats_label.setFont(QFont("Arial", 11))
        layout.addWidget(self.stats_label)
        
        layout.addStretch()
    
    def _on_mode_changed(self):
        """Handle mode radio button change."""
        if self.usb_radio.isChecked():
            self.current_mode = "USB"
        elif self.ap_radio.isChecked():
            self.current_mode = "WIFI_AP"
        
        # Restart IMU with new mode
        self._start_imu()
    
    def _start_imu(self):
        """Start IMU data source."""
        # Stop existing data source
        if self.data_source:
            self.data_source.stop()
            self.data_source = None
        
        try:
            config = load_config()
            
            if self.current_mode == "USB":
                port = config.get("usb", {}).get("port", "/dev/tty.usbserial-10")
                self.data_source = SerialImuReader(port, 9600)
                self.data_source.start()
                print(f"Started IMU in USB mode on {port}")
                mode_text = f"USB - {port}"
            elif self.current_mode == "WIFI_AP":
                ap_cfg = config.get("ap", {})
                device_ip = ap_cfg.get("ip")
                device_port = ap_cfg.get("port")
                if not device_ip or not device_port:
                    raise ValueError("AP mode settings incomplete in .imuconfig. Need 'ip' and 'port'.")
                self.data_source = WifiApImuReader(device_ip=device_ip, device_port=device_port)
                self.data_source.start()
                print(f"Started IMU in WiFi AP mode on {device_ip}:{device_port}")
                mode_text = f"WiFi AP - {device_ip}:{device_port}"
            else:
                raise ValueError(f"Unknown mode: {self.current_mode}")
            
            self.status_label.setText(f"IMU connected ({mode_text}) - Ready for measurement")
            self.status_label.setStyleSheet("padding: 10px; background-color: #d5f4e6; border-radius: 5px;")
        except Exception as e:
            QMessageBox.critical(self, "IMU Error", f"Failed to start IMU:\n{e}")
            self.status_label.setText(f"IMU Error: {e}")
            self.status_label.setStyleSheet("padding: 10px; background-color: #fadbd8; border-radius: 5px;")
    
    def _poll_imu(self):
        """Poll IMU for new samples."""
        if not self.data_source:
            return
        
        sample = self.data_source.get_sample(timeout=0.0)
        if sample and isinstance(sample, ImuSample):
            self._process_imu_sample(sample)
    
    def _process_imu_sample(self, sample: ImuSample):
        """Process IMU sample for movement detection."""
        # Calculate acceleration magnitude
        ax, ay, az = sample.accel_g
        accel_mag = (ax**2 + ay**2 + az**2)**0.5
        
        # Update current acceleration (always)
        self.current_accel = accel_mag
        self.current_accel_display.setText(f"{accel_mag:.3f} g")
        
        if self.measurement_active and not self.movement_detected:
            # Calculate difference between frozen and current
            if self.frozen_accel is not None:
                accel_diff = abs(accel_mag - self.frozen_accel)
                self.diff_display.setText(f"{accel_diff:.3f} g (threshold: {self.accel_threshold} g)")
                
                # Check if difference exceeds threshold
                if accel_diff > self.accel_threshold:
                    self.movement_detected = True
                    self.movement_time = time.time()
                    self._complete_measurement(accel_mag)
            else:
                self.diff_display.setText("--- g")
        else:
            # Not measuring - show difference if we have a frozen value
            if self.frozen_accel is not None:
                accel_diff = abs(accel_mag - self.frozen_accel)
                self.diff_display.setText(f"{accel_diff:.3f} g")
            else:
                self.diff_display.setText("--- g")
    
    def _on_button_press(self):
        """Handle button press to start measurement."""
        if self.measurement_active:
            # Cancel current measurement
            self.measurement_active = False
            self.button_press_time = None
            self.frozen_accel = None
            self.movement_detected = False
            self.movement_time = None
            self.frozen_accel_display.setText("--- g")
            self.frozen_accel_display.setStyleSheet("padding: 8px; background-color: #fff3cd; border: 2px solid #ffc107; border-radius: 5px; min-width: 100px;")
            self.measure_button.setText("Start Measurement")
            self.status_label.setText("Measurement cancelled")
            self.status_label.setStyleSheet("padding: 10px; background-color: #fadbd8; border-radius: 5px;")
            return
        
        # Start new measurement
        self.measurement_active = True
        self.button_press_time = time.time()
        self.movement_detected = False
        self.movement_time = None
        
        # Freeze current acceleration at button press
        self.frozen_accel = self.current_accel
        if self.frozen_accel is not None:
            self.frozen_accel_display.setText(f"{self.frozen_accel:.3f} g")
            self.frozen_accel_display.setStyleSheet("padding: 8px; background-color: #fff3cd; border: 2px solid #ffc107; border-radius: 5px; min-width: 100px; font-weight: bold;")
        
        self.measure_button.setText("Cancel Measurement")
        self.measure_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }
        """)
        self.status_label.setText("Measurement active - Jerk the IMU now!")
        self.status_label.setStyleSheet("padding: 10px; background-color: #fef9e7; border-radius: 5px;")
    
    def _complete_measurement(self, peak_accel: float):
        """Complete a measurement and log results."""
        if not self.measurement_active or self.movement_time is None:
            return
        
        # Calculate latency in milliseconds
        latency_ms = (self.movement_time - self.button_press_time) * 1000.0
        
        # Store trial data
        self.trial_count += 1
        trial_data = {
            'trial': self.trial_count,
            'button_time': self.button_press_time,
            'movement_time': self.movement_time,
            'latency_ms': latency_ms,
            'frozen_accel': self.frozen_accel,
            'peak_accel': peak_accel
        }
        self.trials.append(trial_data)
        
        # Log to CSV
        self.csv_writer.writerow([
            self.trial_count,
            f"{self.button_press_time:.6f}",
            f"{self.movement_time:.6f}",
            f"{latency_ms:.2f}",
            f"{self.frozen_accel:.3f}",
            f"{peak_accel:.3f}"
        ])
        self.csv_file.flush()
        
        # Update UI
        self.trial_label.setText(f"Trials: {self.trial_count}")
        
        # Update results text
        result_text = f"Trial {self.trial_count}: {latency_ms:.2f} ms"
        result_text += f" (Frozen: {self.frozen_accel:.3f}g, Peak: {peak_accel:.3f}g)"
        self.results_text.append(result_text)
        
        # Calculate and display average
        if len(self.trials) > 0:
            avg_latency = sum(t['latency_ms'] for t in self.trials) / len(self.trials)
            self.stats_label.setText(f"Average Latency: {avg_latency:.2f} ms (over {len(self.trials)} trials)")
        
        # Reset for next measurement
        self.measurement_active = False
        self.button_press_time = None
        self.frozen_accel = None
        self.movement_detected = False
        self.movement_time = None
        
        # Reset frozen display
        self.frozen_accel_display.setText("--- g")
        self.frozen_accel_display.setStyleSheet("padding: 8px; background-color: #fff3cd; border: 2px solid #ffc107; border-radius: 5px; min-width: 100px;")
        
        self.measure_button.setText("Start Measurement")
        self.measure_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
        """)
        self.status_label.setText(f"Trial {self.trial_count} complete - {latency_ms:.2f} ms. Ready for next measurement.")
        self.status_label.setStyleSheet("padding: 10px; background-color: #d5f4e6; border-radius: 5px;")
    
    def closeEvent(self, event):
        """Handle window close - cleanup."""
        if self.data_source:
            self.data_source.stop()
        if self.csv_file:
            self.csv_file.close()
        event.accept()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    window = LatencyMeasurementWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
