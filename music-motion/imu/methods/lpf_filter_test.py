"""LPF Filter Test method widget - simplified dashboard with only Angle History and Acceleration Magnitude."""

import math
from collections import deque
from typing import Optional
import numpy as np
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from imu_viewer.models import ImuSample


class LpfFilterTestWidget(QWidget):
    """LPF Filter Test widget showing only Angle History and Acceleration Magnitude."""
    
    def __init__(self, parent=None):
        """Initialize LPF Filter Test widget."""
        super().__init__(parent)
        
        self.history_seconds = 20.0
        self.update_rate = 30.0
        self.update_interval = 1.0 / self.update_rate
        
        # Current sample
        self.current_sample: Optional[ImuSample] = None
        
        # LPF filter state
        self.lpf_enabled = False
        self.lpf_cutoff_hz = 5.0  # Default cutoff frequency
        self.sample_rate = self.update_rate  # Hz
        
        # LPF filter state variables (for first-order IIR filter)
        # y[n] = alpha * x[n] + (1 - alpha) * y[n-1]
        # alpha = 1 - exp(-2*pi*fc/fs)
        self._update_lpf_alpha()
        self.roll_filtered = 0.0
        self.pitch_filtered = 0.0
        self.yaw_filtered = 0.0
        self.accel_mag_filtered = 0.0
        self._filter_initialized = False
        
        # Time-series data (raw)
        self.time_history = deque(maxlen=int(self.history_seconds * self.update_rate))
        self.roll_history = deque(maxlen=int(self.history_seconds * self.update_rate))
        self.pitch_history = deque(maxlen=int(self.history_seconds * self.update_rate))
        self.yaw_history = deque(maxlen=int(self.history_seconds * self.update_rate))
        self.accel_mag_history = deque(maxlen=int(self.history_seconds * self.update_rate))
        
        # Filtered time-series data
        self.roll_filtered_history = deque(maxlen=int(self.history_seconds * self.update_rate))
        self.pitch_filtered_history = deque(maxlen=int(self.history_seconds * self.update_rate))
        self.yaw_filtered_history = deque(maxlen=int(self.history_seconds * self.update_rate))
        self.accel_mag_filtered_history = deque(maxlen=int(self.history_seconds * self.update_rate))
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Setup matplotlib figure
        self.fig = Figure(figsize=(14, 8))
        self.canvas = FigureCanvas(self.fig)
        self.fig.patch.set_facecolor('white')
        
        # Create 2-row layout: Angle History and Acceleration Magnitude
        # Row 1: Angle History
        self.ax_timeseries = self.fig.add_subplot(2, 1, 1)
        self.ax_timeseries.set_title('Angle History (Roll, Pitch, Yaw)', fontweight='bold', fontsize=11)
        self.ax_timeseries.set_xlabel('Time (s)')
        self.ax_timeseries.set_ylabel('Angle (deg)')
        self.ax_timeseries.grid(True, alpha=0.3)
        
        # Row 2: Acceleration Chart
        self.ax_accel = self.fig.add_subplot(2, 1, 2)
        self.ax_accel.set_title('Acceleration Magnitude', fontweight='bold', fontsize=11)
        self.ax_accel.set_xlabel('Time (s)')
        self.ax_accel.set_ylabel('|Accel| (g)')
        self.ax_accel.grid(True, alpha=0.3)
        
        # Adjust subplot spacing
        self.fig.subplots_adjust(hspace=0.3, top=0.95, bottom=0.1)
        
        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        main_layout.addLayout(layout, 1)
        
        # Update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_display)
        self.update_timer.start(int(self.update_interval * 1000))
    
    def _update_lpf_alpha(self):
        """Update LPF filter coefficient based on cutoff frequency."""
        # First-order IIR low-pass filter
        # alpha = 1 - exp(-2*pi*fc/fs)
        # where fc = cutoff frequency, fs = sample rate
        if self.sample_rate > 0:
            self.lpf_alpha = 1.0 - math.exp(-2.0 * math.pi * self.lpf_cutoff_hz / self.sample_rate)
        else:
            self.lpf_alpha = 0.1  # Default
    
    def set_lpf_enabled(self, enabled: bool):
        """Enable or disable LPF filtering."""
        self.lpf_enabled = enabled
        if not enabled:
            # Reset filter state when disabled
            self._filter_initialized = False
    
    def set_lpf_cutoff(self, cutoff_hz: float):
        """Set LPF cutoff frequency in Hz."""
        self.lpf_cutoff_hz = cutoff_hz
        self._update_lpf_alpha()
    
    
    def update_sample(self, sample: ImuSample):
        """Update with new IMU sample."""
        self.current_sample = sample
        
        # Calculate time relative to first sample
        if len(self.time_history) == 0:
            self.t0 = sample.timestamp
            t_rel = 0.0
        else:
            delta = (sample.timestamp - self.t0).total_seconds()
            t_rel = delta
        
        # Update time-series data (raw)
        self.time_history.append(t_rel)
        roll_raw = sample.angles_deg[0]
        pitch_raw = sample.angles_deg[1]
        yaw_raw = sample.angles_deg[2]
        self.roll_history.append(roll_raw)
        self.pitch_history.append(pitch_raw)
        self.yaw_history.append(yaw_raw)
        
        # Calculate acceleration magnitude (raw)
        accel_mag_raw = math.sqrt(
            sample.accel_g[0]**2 +
            sample.accel_g[1]**2 +
            sample.accel_g[2]**2
        )
        self.accel_mag_history.append(accel_mag_raw)
        
        # Apply LPF filter if enabled
        if self.lpf_enabled:
            if not self._filter_initialized:
                # Initialize filter state with first sample
                self.roll_filtered = roll_raw
                self.pitch_filtered = pitch_raw
                self.yaw_filtered = yaw_raw
                self.accel_mag_filtered = accel_mag_raw
                self._filter_initialized = True
            
            # Apply first-order IIR low-pass filter
            # y[n] = alpha * x[n] + (1 - alpha) * y[n-1]
            self.roll_filtered = self.lpf_alpha * roll_raw + (1.0 - self.lpf_alpha) * self.roll_filtered
            self.pitch_filtered = self.lpf_alpha * pitch_raw + (1.0 - self.lpf_alpha) * self.pitch_filtered
            self.yaw_filtered = self.lpf_alpha * yaw_raw + (1.0 - self.lpf_alpha) * self.yaw_filtered
            self.accel_mag_filtered = self.lpf_alpha * accel_mag_raw + (1.0 - self.lpf_alpha) * self.accel_mag_filtered
            
            # Store filtered values
            self.roll_filtered_history.append(self.roll_filtered)
            self.pitch_filtered_history.append(self.pitch_filtered)
            self.yaw_filtered_history.append(self.yaw_filtered)
            self.accel_mag_filtered_history.append(self.accel_mag_filtered)
        else:
            # When filter is disabled, clear filtered history
            if len(self.roll_filtered_history) > 0:
                self.roll_filtered_history.clear()
                self.pitch_filtered_history.clear()
                self.yaw_filtered_history.clear()
                self.accel_mag_filtered_history.clear()
                self._filter_initialized = False
    
    def _update_display(self):
        """Update all displays."""
        sample = self.current_sample
        
        if sample is None:
            self.canvas.draw()
            return
        
        # Update all panels
        self._update_timeseries()
        self._update_accel_magnitude()
        
        self.canvas.draw()
    
    def _update_timeseries(self):
        """Update time-series plot."""
        self.ax_timeseries.clear()
        self.ax_timeseries.set_title('Angle History (Roll, Pitch, Yaw)', fontweight='bold', fontsize=11)
        self.ax_timeseries.set_xlabel('Time (s)')
        self.ax_timeseries.set_ylabel('Angle (deg)')
        self.ax_timeseries.grid(True, alpha=0.3)
        
        if len(self.time_history) > 1:
            time_arr = np.array(self.time_history)
            # Plot raw data
            self.ax_timeseries.plot(time_arr, list(self.roll_history), 'r-', label='Roll', linewidth=1.5, alpha=0.6)
            self.ax_timeseries.plot(time_arr, list(self.pitch_history), 'g-', label='Pitch', linewidth=1.5, alpha=0.6)
            self.ax_timeseries.plot(time_arr, list(self.yaw_history), 'b-', label='Yaw', linewidth=1.5, alpha=0.6)
            
            # Plot filtered data if enabled and has matching length
            if self.lpf_enabled and len(self.roll_filtered_history) > 0:
                # Only plot if filtered history matches time history length
                if len(self.roll_filtered_history) == len(self.time_history):
                    time_arr_filtered = np.array(self.time_history)
                    self.ax_timeseries.plot(time_arr_filtered, list(self.roll_filtered_history), 'r--', label='Roll (filtered)', linewidth=2.0)
                    self.ax_timeseries.plot(time_arr_filtered, list(self.pitch_filtered_history), 'g--', label='Pitch (filtered)', linewidth=2.0)
                    self.ax_timeseries.plot(time_arr_filtered, list(self.yaw_filtered_history), 'b--', label='Yaw (filtered)', linewidth=2.0)
                else:
                    # Use slice of time array to match filtered history length
                    filtered_len = len(self.roll_filtered_history)
                    time_arr_filtered = np.array(list(self.time_history)[-filtered_len:])
                    self.ax_timeseries.plot(time_arr_filtered, list(self.roll_filtered_history), 'r--', label='Roll (filtered)', linewidth=2.0)
                    self.ax_timeseries.plot(time_arr_filtered, list(self.pitch_filtered_history), 'g--', label='Pitch (filtered)', linewidth=2.0)
                    self.ax_timeseries.plot(time_arr_filtered, list(self.yaw_filtered_history), 'b--', label='Yaw (filtered)', linewidth=2.0)
            
            self.ax_timeseries.legend(loc='upper right', fontsize=9)
            if len(time_arr) > 0:
                t_max = max(time_arr)
                t_min = max(0, t_max - self.history_seconds)
                self.ax_timeseries.set_xlim(t_min, t_max)
    
    def _update_accel_magnitude(self):
        """Update acceleration magnitude plot."""
        self.ax_accel.clear()
        title = 'Acceleration Magnitude'
        if self.lpf_enabled:
            title += f' (LPF: {self.lpf_cutoff_hz:.1f} Hz)'
        self.ax_accel.set_title(title, fontweight='bold', fontsize=11)
        self.ax_accel.set_xlabel('Time (s)')
        self.ax_accel.set_ylabel('|Accel| (g)')
        self.ax_accel.grid(True, alpha=0.3)
        
        if len(self.time_history) > 1:
            time_arr = np.array(self.time_history)
            # Plot raw data
            self.ax_accel.plot(time_arr, list(self.accel_mag_history), 'purple', linewidth=1.5, alpha=0.6, label='Raw')
            
            # Plot filtered data if enabled and available
            if self.lpf_enabled and len(self.accel_mag_filtered_history) > 0:
                # Only plot if filtered history matches time history length
                if len(self.accel_mag_filtered_history) == len(self.time_history):
                    time_arr_filtered = np.array(self.time_history)
                    self.ax_accel.plot(time_arr_filtered, list(self.accel_mag_filtered_history), 'purple', linewidth=2.0, linestyle='--', label='Filtered')
                else:
                    # Use slice of time array to match filtered history length
                    filtered_len = len(self.accel_mag_filtered_history)
                    time_arr_filtered = np.array(list(self.time_history)[-filtered_len:])
                    self.ax_accel.plot(time_arr_filtered, list(self.accel_mag_filtered_history), 'purple', linewidth=2.0, linestyle='--', label='Filtered')
            
            if self.lpf_enabled:
                self.ax_accel.legend(loc='upper right', fontsize=9)
            
            if len(time_arr) > 0:
                t_max = max(time_arr)
                t_min = max(0, t_max - self.history_seconds)
                self.ax_accel.set_xlim(t_min, t_max)
