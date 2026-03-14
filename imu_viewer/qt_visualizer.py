"""PyQt5 widget with embedded matplotlib for IMU visualization."""
import math
from collections import deque
from typing import Optional
import numpy as np
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec

try:
    from .models import ImuSample
except ImportError:
    from models import ImuSample


class DashboardWidget(QWidget):
    """Dashboard widget with 5 visualization panels in a 3-column layout."""
    
    def __init__(self, history_seconds: float = 20.0, update_rate: float = 30.0, parent=None):
        """Initialize dashboard widget."""
        super().__init__(parent)
        self.history_seconds = history_seconds
        self.update_interval = 1.0 / update_rate

        # Current sample
        self.current_sample: Optional[ImuSample] = None

        # LPF filter state
        self.lpf_enabled = False
        self.lpf_cutoff_hz = 5.0  # Default cutoff frequency
        self.sample_rate = update_rate  # Hz
        
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
        self.time_history = deque(maxlen=int(history_seconds * update_rate))
        self.roll_history = deque(maxlen=int(history_seconds * update_rate))
        self.pitch_history = deque(maxlen=int(history_seconds * update_rate))
        self.yaw_history = deque(maxlen=int(history_seconds * update_rate))
        self.accel_mag_history = deque(maxlen=int(history_seconds * update_rate))
        
        # Filtered time-series data
        self.roll_filtered_history = deque(maxlen=int(history_seconds * update_rate))
        self.pitch_filtered_history = deque(maxlen=int(history_seconds * update_rate))
        self.yaw_filtered_history = deque(maxlen=int(history_seconds * update_rate))
        self.accel_mag_filtered_history = deque(maxlen=int(history_seconds * update_rate))

        # Setup matplotlib figure
        self.fig = Figure(figsize=(14, 10))
        self.canvas = FigureCanvas(self.fig)
        self.fig.patch.set_facecolor('white')
        
        # Remove the default title since we have a title in the main window
        # Create 3-row, 3-column grid layout
        # Row 1: Horizon, Compass, Overview (Overview spans rows 1-2)
        # Row 2: Angle Chart (spans cols 0-1), Overview continues
        # Row 3: Acceleration Chart (spans all 3 cols)
        gs = GridSpec(3, 3, figure=self.fig, hspace=0.3, wspace=0.3,
                     height_ratios=[1, 1, 0.8], width_ratios=[1, 1, 1])

        # Row 1, Col 0: Artificial Horizon
        self.ax_horizon = self.fig.add_subplot(gs[0, 0])
        self.ax_horizon.set_xlim(-1.5, 1.5)
        self.ax_horizon.set_ylim(-1.5, 1.5)
        self.ax_horizon.set_aspect('equal')
        self.ax_horizon.set_title('Artificial Horizon (Roll/Pitch)', fontweight='bold', fontsize=11)
        self.ax_horizon.grid(True, alpha=0.3)

        # Row 1, Col 1: Compass
        self.ax_compass = self.fig.add_subplot(gs[0, 1])
        self.ax_compass.set_xlim(-1.2, 1.2)
        self.ax_compass.set_ylim(-1.2, 1.2)
        self.ax_compass.set_aspect('equal')
        self.ax_compass.set_title('Compass (Yaw/Heading)', fontweight='bold', fontsize=11)
        self.ax_compass.grid(True, alpha=0.3)

        # Row 1-2, Col 2: Overview table (spans 2 rows)
        self.ax_overview = self.fig.add_subplot(gs[0:2, 2])
        self.ax_overview.axis('off')
        self.ax_overview.set_title('Overview', fontweight='bold', fontsize=11, pad=10)

        # Row 2, Col 0-1: Angle Chart (spans 2 columns)
        self.ax_timeseries = self.fig.add_subplot(gs[1, 0:2])
        self.ax_timeseries.set_title('Angle History (Roll, Pitch, Yaw)', fontweight='bold', fontsize=11)
        self.ax_timeseries.set_xlabel('Time (s)')
        self.ax_timeseries.set_ylabel('Angle (deg)')
        self.ax_timeseries.grid(True, alpha=0.3)

        # Row 3, Col 0-2: Acceleration Chart (spans all 3 columns)
        self.ax_accel = self.fig.add_subplot(gs[2, :])
        self.ax_accel.set_title('Acceleration Magnitude', fontweight='bold', fontsize=11)
        self.ax_accel.set_xlabel('Time (s)')
        self.ax_accel.set_ylabel('|Accel| (g)')
        self.ax_accel.grid(True, alpha=0.3)

        # Adjust subplot spacing to reduce top margin
        self.fig.subplots_adjust(top=0.99)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

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
        """Update current sample."""
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
            self._update_overview_waiting()
            self.canvas.draw()
            return

        # Update all panels
        self._update_overview(sample)
        self._update_horizon(sample)
        self._update_compass(sample)
        self._update_timeseries()
        self._update_accel_magnitude()

        self.canvas.draw()

    def _update_overview(self, sample: ImuSample):
        """Update overview table."""
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

    def _update_overview_waiting(self):
        """Update overview with waiting message."""
        self.ax_overview.clear()
        self.ax_overview.axis('off')
        self.ax_overview.set_title('Overview', fontweight='bold', fontsize=11, pad=10)
        text_str = "Waiting for data from device..."
        self.ax_overview.text(0.5, 0.5, text_str, transform=self.ax_overview.transAxes,
                             fontsize=12, ha='center', va='center',
                             bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

    def _update_horizon(self, sample: ImuSample):
        """Update artificial horizon."""
        self.ax_horizon.clear()
        self.ax_horizon.set_xlim(-1.5, 1.5)
        self.ax_horizon.set_ylim(-1.5, 1.5)
        self.ax_horizon.set_aspect('equal')
        self.ax_horizon.set_title('Artificial Horizon (Roll/Pitch)', fontweight='bold', fontsize=11)
        self.ax_horizon.grid(True, alpha=0.3)

        roll_rad = math.radians(sample.angles_deg[0])
        pitch_deg = sample.angles_deg[1]

        # Draw horizon line
        horizon_length = 2.0
        x1_local = -horizon_length / 2
        y1_local = pitch_deg / 90.0
        x2_local = horizon_length / 2
        y2_local = pitch_deg / 90.0

        # Rotate by roll
        cos_r = math.cos(roll_rad)
        sin_r = math.sin(roll_rad)
        x1 = x1_local * cos_r - y1_local * sin_r
        y1 = x1_local * sin_r + y1_local * cos_r
        x2 = x2_local * cos_r - y2_local * sin_r
        y2 = x2_local * sin_r + y2_local * cos_r

        # Draw sky and ground
        self.ax_horizon.fill_between([-2, 2], [2, 2], [y1, y2], color='lightblue', alpha=0.5)
        self.ax_horizon.fill_between([-2, 2], [y1, y2], [-2, -2], color='saddlebrown', alpha=0.5)

        # Draw horizon line
        self.ax_horizon.plot([x1, x2], [y1, y2], 'k-', linewidth=3)

        # Draw aircraft symbol
        aircraft_size = 0.3
        nose_y = aircraft_size
        wing_span = aircraft_size * 0.8
        self.ax_horizon.plot([0, 0], [0, nose_y], 'r-', linewidth=2)
        self.ax_horizon.plot([-wing_span/2, wing_span/2], [0, 0], 'r-', linewidth=2)

        # Center crosshair
        self.ax_horizon.plot([-0.1, 0.1], [0, 0], 'k-', linewidth=1)
        self.ax_horizon.plot([0, 0], [-0.1, 0.1], 'k-', linewidth=1)

    def _update_compass(self, sample: ImuSample):
        """Update compass."""
        self.ax_compass.clear()
        self.ax_compass.set_xlim(-1.2, 1.2)
        self.ax_compass.set_ylim(-1.2, 1.2)
        self.ax_compass.set_aspect('equal')
        self.ax_compass.set_title('Compass (Yaw/Heading)', fontweight='bold', fontsize=11)
        self.ax_compass.grid(True, alpha=0.3)

        # Draw compass circle
        from matplotlib.patches import Circle
        circle = Circle((0, 0), 1.0, fill=False, color='black', linewidth=2)
        self.ax_compass.add_patch(circle)

        # Draw cardinal directions
        for angle, label in [(0, 'N'), (90, 'E'), (180, 'S'), (270, 'W')]:
            rad = math.radians(angle)
            x = math.sin(rad) * 1.1
            y = math.cos(rad) * 1.1
            self.ax_compass.text(x, y, label, ha='center', va='center',
                                fontsize=12, fontweight='bold')

        # Draw minor ticks
        for angle in range(0, 360, 30):
            if angle % 90 != 0:
                rad = math.radians(angle)
                x1 = math.sin(rad) * 0.95
                y1 = math.cos(rad) * 0.95
                x2 = math.sin(rad) * 1.05
                y2 = math.cos(rad) * 1.05
                self.ax_compass.plot([x1, x2], [y1, y2], 'k-', linewidth=1)

        # Draw heading arrow
        yaw_rad = math.radians(sample.angles_deg[2])
        arrow_length = 0.8
        arrow_x = math.sin(yaw_rad) * arrow_length
        arrow_y = math.cos(yaw_rad) * arrow_length
        self.ax_compass.arrow(0, 0, arrow_x, arrow_y, head_width=0.15, head_length=0.15,
                             fc='red', ec='red', linewidth=2)

        # Display heading value
        self.ax_compass.text(0, -1.4, f'Heading: {sample.angles_deg[2]:.1f}°',
                           ha='center', fontsize=10, fontweight='bold')

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


class DebugWidget(QWidget):
    """Debug widget showing raw device data."""
    
    def __init__(self, parent=None):
        """Initialize debug widget."""
        super().__init__(parent)
        
        # Main layout using PyQt5
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)  # Space between title and matplotlib canvas
        
        # Title using PyQt5 QLabel
        title_label = QLabel("Raw Device Data")
        title_label.setFont(QFont("Arial", 11, QFont.Bold))
        title_label.setStyleSheet("color: #2c3e50; padding: 0px; border: none;")
        main_layout.addWidget(title_label)
        
        # Setup matplotlib figure - only for the text box
        self.fig = Figure(figsize=(10, 4))  # Small figure, will resize
        self.canvas = FigureCanvas(self.fig)
        self.fig.patch.set_facecolor('white')
        
        # Single axis for debug text - no title (handled by QLabel)
        # Use the full figure area since Qt layout already positions it below the title
        self.ax_debug = self.fig.add_subplot(111)
        self.ax_debug.axis('off')
        # Set fixed axis limits
        self.ax_debug.set_xlim(0, 1)
        self.ax_debug.set_ylim(0, 1)
        
        # Use full figure area - Qt layout already handles positioning below title
        self.fig.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0, hspace=0, wspace=0)
        
        # Add matplotlib canvas to layout
        main_layout.addWidget(self.canvas, 1)  # Stretch factor to fill space
        
        # Update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_display)
        self.update_timer.start(100)  # Update every 100ms
        
        self.current_sample: Optional[ImuSample] = None

    def update_sample(self, sample: ImuSample):
        """Update current sample."""
        self.current_sample = sample

    def _update_display(self):
        """Update debug display."""
        sample = self.current_sample
        
        self.ax_debug.clear()
        self.ax_debug.axis('off')
        # No title here - it's handled by PyQt5 QLabel
        
        # Build debug text
        if sample is None:
            debug_text = "Waiting for data from device...\n\n"
            debug_text += "If no data appears, check:\n"
            debug_text += "- Device is connected and powered\n"
            debug_text += "- Serial port is correct (use --list-ports)\n"
            debug_text += "- Baud rate matches device (default: 9600)"
            bbox_color = 'lightyellow'
        else:
            debug_text = f"Header: {sample.raw_header}\n"
            # Wrap long hex strings to prevent cutoff
            hex_str = sample.raw_payload_hex
            max_hex_line_len = 80  # Characters per line for hex
            if len(hex_str) > max_hex_line_len:
                # Split hex string into multiple lines
                hex_lines = []
                for i in range(0, len(hex_str), max_hex_line_len):
                    hex_lines.append(hex_str[i:i+max_hex_line_len])
                debug_text += "Raw payload hex:\n" + "\n".join(hex_lines) + "\n"
            else:
                debug_text += f"Raw payload hex: {hex_str}\n"
            
            if sample.raw_int16_values:
                int16_str = "Int16 values: " + str(sample.raw_int16_values)
                max_line_len = 100  # Characters per line for int16 values
                if len(int16_str) > max_line_len:
                    chunks = []
                    current = "Int16 values: "
                    for val in sample.raw_int16_values:
                        val_str = str(val)
                        if len(current) + len(val_str) + 2 > max_line_len:
                            chunks.append(current)
                            current = "  " + val_str
                        else:
                            if current != "Int16 values: ":
                                current += ", "
                            current += val_str
                    if current:
                        chunks.append(current)
                    debug_text += "\n".join(chunks)
                else:
                    debug_text += int16_str
            else:
                debug_text += "Int16 values: (no data)"
            bbox_color = 'lightgray'
        
        # Position text at 85% from bottom of matplotlib canvas
        # The matplotlib canvas is already positioned below the QLabel title by Qt layout
        self.ax_debug.text(0.02, 0.85, debug_text, transform=self.ax_debug.transAxes,
                          fontsize=9, verticalalignment='top', horizontalalignment='left',
                          fontfamily='monospace',
                          bbox=dict(boxstyle='square', facecolor=bbox_color, alpha=0.8, pad=0.5))
        
        # Just redraw - layout is handled by Qt
        self.canvas.draw()


# Backward compatibility alias
ImuVisualizerWidget = DashboardWidget
