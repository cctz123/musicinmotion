"""Real-time visualization for IMU data using matplotlib."""
import math
from collections import deque
from typing import Optional
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.gridspec import GridSpec
import numpy as np

try:
    from .models import ImuSample
except ImportError:
    from models import ImuSample


class ImuVisualizer:
    """Real-time IMU data visualization with matplotlib."""

    def __init__(self, history_seconds: float = 20.0, update_rate: float = 30.0):
        """
        Initialize visualizer.

        Args:
            history_seconds: Number of seconds of history to display in time-series
            update_rate: Target update rate in Hz
        """
        self.history_seconds = history_seconds
        self.update_interval = 1.0 / update_rate  # seconds between updates

        # Current sample
        self.current_sample: Optional[ImuSample] = None

        # Time-series data (using deque for efficient append/pop)
        self.time_history = deque(maxlen=int(history_seconds * update_rate))
        self.roll_history = deque(maxlen=int(history_seconds * update_rate))
        self.pitch_history = deque(maxlen=int(history_seconds * update_rate))
        self.yaw_history = deque(maxlen=int(history_seconds * update_rate))
        self.accel_mag_history = deque(maxlen=int(history_seconds * update_rate))

        # Setup figure and axes
        self.fig = plt.figure(figsize=(14, 12))
        self.fig.suptitle('WT901WIFI IMU Viewer', fontsize=16, fontweight='bold')

        # Create grid layout (4 rows to accommodate debug panel)
        # Increased hspace significantly to prevent overlap, and using 3 columns to allow compass positioning
        gs = GridSpec(4, 3, figure=self.fig, hspace=0.4, wspace=0.3, height_ratios=[1, 1, 1, 0.8],
                     width_ratios=[1.2, 1, 1.2])

        # Top-left: Numeric readout panel
        self.ax_text = self.fig.add_subplot(gs[0, 0])
        self.ax_text.axis('off')
        self.text_display = None

        # Top-right: Artificial horizon (roll/pitch) - spans columns 1 and 2
        self.ax_horizon = self.fig.add_subplot(gs[0, 1:])
        self.ax_horizon.set_xlim(-1.5, 1.5)
        self.ax_horizon.set_ylim(-1.5, 1.5)
        self.ax_horizon.set_aspect('equal')
        self.ax_horizon.set_title('Artificial Horizon (Roll/Pitch)', fontweight='bold')
        self.ax_horizon.grid(True, alpha=0.3)

        # Middle-left: Time-series plot
        self.ax_timeseries = self.fig.add_subplot(gs[1, 0])
        self.ax_timeseries.set_title('Angle History', fontweight='bold')
        self.ax_timeseries.set_xlabel('Time (s)')
        self.ax_timeseries.set_ylabel('Angle (deg)')
        self.ax_timeseries.grid(True, alpha=0.3)
        self.ax_timeseries.legend(['Roll', 'Pitch', 'Yaw'], loc='upper right')

        # Middle-center: Compass (moved to center column, higher due to increased hspace)
        self.ax_compass = self.fig.add_subplot(gs[1, 1])
        self.ax_compass.set_xlim(-1.2, 1.2)
        self.ax_compass.set_ylim(-1.2, 1.2)
        self.ax_compass.set_aspect('equal')
        self.ax_compass.set_title('Compass (Yaw/Heading)', fontweight='bold')
        self.ax_compass.grid(True, alpha=0.3)
        
        # Middle-right: Empty space (or could add another plot here later)

        # Third row: Accel magnitude plot
        self.ax_accel = self.fig.add_subplot(gs[2, :])
        self.ax_accel.set_title('Acceleration Magnitude', fontweight='bold')
        self.ax_accel.set_xlabel('Time (s)')
        self.ax_accel.set_ylabel('|Accel| (g)')
        self.ax_accel.grid(True, alpha=0.3)

        # Fourth row: Debug panel showing raw device data
        self.ax_debug = self.fig.add_subplot(gs[3, :])
        self.ax_debug.axis('off')
        self.ax_debug.set_title('Raw Device Data (Debug)', fontweight='bold', pad=10)

        # Animation
        self.anim: Optional[animation.FuncAnimation] = None

    def update_sample(self, sample: ImuSample):
        """Update current sample (called from main thread)."""
        self.current_sample = sample

        # Calculate time relative to first sample
        if len(self.time_history) == 0:
            self.t0 = sample.timestamp
            t_rel = 0.0
        else:
            delta = (sample.timestamp - self.t0).total_seconds()
            t_rel = delta

        # Update time-series data
        self.time_history.append(t_rel)
        self.roll_history.append(sample.angles_deg[0])
        self.pitch_history.append(sample.angles_deg[1])
        self.yaw_history.append(sample.angles_deg[2])

        # Calculate acceleration magnitude
        accel_mag = math.sqrt(
            sample.accel_g[0]**2 +
            sample.accel_g[1]**2 +
            sample.accel_g[2]**2
        )
        self.accel_mag_history.append(accel_mag)

    def _update_display(self, frame):
        """Animation callback to update all displays."""
        sample = self.current_sample
        
        # Show debug panel even if no sample yet
        if sample is None:
            # Update debug panel with waiting message
            self.ax_debug.clear()
            self.ax_debug.axis('off')
            self.ax_debug.set_title('Raw Device Data (Debug)', fontweight='bold', pad=10)
            debug_text = "Waiting for data from device...\n\n"
            debug_text += "If no data appears, check:\n"
            debug_text += "- Device is connected and powered\n"
            debug_text += "- Serial port is correct (use --list-ports)\n"
            debug_text += "- Baud rate matches device (default: 9600)"
            self.ax_debug.text(0.02, 0.95, debug_text, transform=self.ax_debug.transAxes,
                              fontsize=9, verticalalignment='top', fontfamily='monospace',
                              bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
            return

        # Update numeric text panel
        self.ax_text.clear()
        self.ax_text.axis('off')
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
        self.ax_text.text(0.05, 0.95, text_str, transform=self.ax_text.transAxes,
                         fontsize=10, verticalalignment='top', fontfamily='monospace',
                         bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        # Update artificial horizon
        self.ax_horizon.clear()
        self.ax_horizon.set_xlim(-1.5, 1.5)
        self.ax_horizon.set_ylim(-1.5, 1.5)
        self.ax_horizon.set_aspect('equal')
        self.ax_horizon.set_title('Artificial Horizon (Roll/Pitch)', fontweight='bold')
        self.ax_horizon.grid(True, alpha=0.3)

        roll_rad = math.radians(sample.angles_deg[0])
        pitch_deg = sample.angles_deg[1]

        # Draw horizon line (rotated by roll, shifted by pitch)
        horizon_length = 2.0
        # Horizon line endpoints in local frame
        x1_local = -horizon_length / 2
        y1_local = pitch_deg / 90.0  # Normalize pitch to -1 to 1 range
        x2_local = horizon_length / 2
        y2_local = pitch_deg / 90.0

        # Rotate by roll
        cos_r = math.cos(roll_rad)
        sin_r = math.sin(roll_rad)
        x1 = x1_local * cos_r - y1_local * sin_r
        y1 = x1_local * sin_r + y1_local * cos_r
        x2 = x2_local * cos_r - y2_local * sin_r
        y2 = x2_local * sin_r + y2_local * cos_r

        # Draw sky (above horizon) and ground (below)
        self.ax_horizon.fill_between([-2, 2], [2, 2], [y1, y2], color='lightblue', alpha=0.5)
        self.ax_horizon.fill_between([-2, 2], [y1, y2], [-2, -2], color='saddlebrown', alpha=0.5)

        # Draw horizon line
        self.ax_horizon.plot([x1, x2], [y1, y2], 'k-', linewidth=3)

        # Draw aircraft symbol (center, pointing up)
        aircraft_size = 0.3
        nose_y = aircraft_size
        wing_span = aircraft_size * 0.8
        self.ax_horizon.plot([0, 0], [0, nose_y], 'r-', linewidth=2)  # Nose
        self.ax_horizon.plot([-wing_span/2, wing_span/2], [0, 0], 'r-', linewidth=2)  # Wings

        # Draw center crosshair
        self.ax_horizon.plot([-0.1, 0.1], [0, 0], 'k-', linewidth=1)
        self.ax_horizon.plot([0, 0], [-0.1, 0.1], 'k-', linewidth=1)

        # Update compass
        self.ax_compass.clear()
        self.ax_compass.set_xlim(-1.2, 1.2)
        self.ax_compass.set_ylim(-1.2, 1.2)
        self.ax_compass.set_aspect('equal')
        self.ax_compass.set_title('Compass (Yaw/Heading)', fontweight='bold')
        self.ax_compass.grid(True, alpha=0.3)

        # Draw compass circle
        circle = plt.Circle((0, 0), 1.0, fill=False, color='black', linewidth=2)
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
            if angle % 90 != 0:  # Skip cardinals
                rad = math.radians(angle)
                x1 = math.sin(rad) * 0.95
                y1 = math.cos(rad) * 0.95
                x2 = math.sin(rad) * 1.05
                y2 = math.cos(rad) * 1.05
                self.ax_compass.plot([x1, x2], [y1, y2], 'k-', linewidth=1)

        # Draw heading arrow (pointing to current yaw)
        yaw_rad = math.radians(sample.angles_deg[2])
        arrow_length = 0.8
        arrow_x = math.sin(yaw_rad) * arrow_length
        arrow_y = math.cos(yaw_rad) * arrow_length
        self.ax_compass.arrow(0, 0, arrow_x, arrow_y, head_width=0.15, head_length=0.15,
                             fc='red', ec='red', linewidth=2)

        # Display heading value
        self.ax_compass.text(0, -1.4, f'Heading: {sample.angles_deg[2]:.1f}°',
                           ha='center', fontsize=10, fontweight='bold')

        # Update time-series plot
        self.ax_timeseries.clear()
        self.ax_timeseries.set_title('Angle History', fontweight='bold')
        self.ax_timeseries.set_xlabel('Time (s)')
        self.ax_timeseries.set_ylabel('Angle (deg)')
        self.ax_timeseries.grid(True, alpha=0.3)

        if len(self.time_history) > 1:
            time_arr = np.array(self.time_history)
            self.ax_timeseries.plot(time_arr, list(self.roll_history), 'r-', label='Roll', linewidth=1.5)
            self.ax_timeseries.plot(time_arr, list(self.pitch_history), 'g-', label='Pitch', linewidth=1.5)
            self.ax_timeseries.plot(time_arr, list(self.yaw_history), 'b-', label='Yaw', linewidth=1.5)
            self.ax_timeseries.legend(loc='upper right')
            # Auto-scale x-axis to show recent history
            if len(time_arr) > 0:
                t_max = max(time_arr)
                t_min = max(0, t_max - self.history_seconds)
                self.ax_timeseries.set_xlim(t_min, t_max)

        # Update acceleration magnitude plot
        self.ax_accel.clear()
        self.ax_accel.set_title('Acceleration Magnitude', fontweight='bold')
        self.ax_accel.set_xlabel('Time (s)')
        self.ax_accel.set_ylabel('|Accel| (g)')
        self.ax_accel.grid(True, alpha=0.3)

        if len(self.time_history) > 1:
            time_arr = np.array(self.time_history)
            self.ax_accel.plot(time_arr, list(self.accel_mag_history), 'purple', linewidth=1.5)
            # Auto-scale x-axis
            if len(time_arr) > 0:
                t_max = max(time_arr)
                t_min = max(0, t_max - self.history_seconds)
                self.ax_accel.set_xlim(t_min, t_max)

        # Update debug panel with raw device data (testimu2.py format)
        self.ax_debug.clear()
        self.ax_debug.axis('off')
        self.ax_debug.set_title('Raw Device Data (Debug)', fontweight='bold', pad=10)
        
        # Format similar to testimu2.py output
        debug_text = f"Header: {sample.raw_header}\n"
        debug_text += f"Raw payload hex: {sample.raw_payload_hex}\n"
        if sample.raw_int16_values:
            # Format int16 values nicely (wrap long lines)
            int16_str = "Int16 values: " + str(sample.raw_int16_values)
            # Break into multiple lines if too long
            max_line_len = 100
            if len(int16_str) > max_line_len:
                # Split into chunks
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
        
        self.ax_debug.text(0.02, 0.95, debug_text, transform=self.ax_debug.transAxes,
                          fontsize=9, verticalalignment='top', fontfamily='monospace',
                          bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))

    def start_animation(self):
        """Start the matplotlib animation."""
        plt.ion()  # Turn on interactive mode
        plt.show(block=False)
        self.anim = animation.FuncAnimation(
            self.fig, self._update_display,
            interval=int(self.update_interval * 1000),  # milliseconds
            blit=False
        )
        plt.draw()
        plt.pause(0.001)  # Small pause to ensure window is shown

    def close(self):
        """Close the figure."""
        if self.anim:
            self.anim.event_source.stop()
        plt.close(self.fig)

