"""IMU Latency measurement method widget."""

import time
import statistics
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from imu_viewer.models import ImuSample


class ImuLatencyWidget(QWidget):
    """IMU Latency measurement widget."""
    
    def __init__(self, parent=None):
        """Initialize IMU Latency widget."""
        super().__init__(parent)
        
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
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Instructions
        instructions = QLabel(
            "1. Hold IMU in one hand\n"
            "2. Press 'Start Measurement' button with other hand\n"
            "3. Immediately jerk/shake the IMU\n"
            "4. Latency will be calculated and logged"
        )
        instructions.setFont(QFont("Arial", 11))
        layout.addWidget(instructions)
        
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
        
        # Update UI
        self.trial_label.setText(f"Trials: {self.trial_count}")
        
        # Update results text
        result_text = f"Trial {self.trial_count}: {latency_ms:.2f} ms"
        result_text += f" (Frozen: {self.frozen_accel:.3f}g, Peak: {peak_accel:.3f}g)"
        self.results_text.append(result_text)
        
        # Calculate and display average (with outlier removal)
        if len(self.trials) > 0:
            avg_latency, valid_count = self._calculate_average_with_outliers_removed()
            if valid_count > 0:
                self.stats_label.setText(f"Average Latency: {avg_latency:.2f} ms (over {valid_count} trials, {len(self.trials) - valid_count} outliers excluded)")
            else:
                self.stats_label.setText(f"Average Latency: N/A (all {len(self.trials)} trials excluded as outliers)")
        
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
    
    def update_sample(self, sample: ImuSample):
        """Update with new IMU sample."""
        self._process_imu_sample(sample)
    
    def _calculate_average_with_outliers_removed(self):
        """Calculate average latency excluding outliers using IQR method."""
        if len(self.trials) < 3:
            # Need at least 3 trials to calculate IQR
            latencies = [t['latency_ms'] for t in self.trials]
            return statistics.mean(latencies), len(latencies)
        
        latencies = [t['latency_ms'] for t in self.trials]
        sorted_latencies = sorted(latencies)
        
        # Calculate Q1 (25th percentile) and Q3 (75th percentile)
        n = len(sorted_latencies)
        q1_idx = int(n * 0.25)
        q3_idx = int(n * 0.75)
        
        q1 = sorted_latencies[q1_idx]
        q3 = sorted_latencies[q3_idx]
        
        # Calculate IQR
        iqr = q3 - q1
        
        # Define outlier bounds (1.5 * IQR rule)
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        # Filter out outliers
        valid_latencies = [lat for lat in latencies if lower_bound <= lat <= upper_bound]
        
        if len(valid_latencies) == 0:
            return 0.0, 0
        
        avg_latency = statistics.mean(valid_latencies)
        return avg_latency, len(valid_latencies)
    
    def cleanup(self):
        """Clean up resources."""
        pass
