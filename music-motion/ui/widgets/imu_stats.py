"""IMU statistics display widget."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class ImuStatsWidget(QWidget):
    """Widget displaying IMU statistics using matplotlib (matching imu_viewer style)."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(250)
        self.setMaximumWidth(350)
        
        # Setup matplotlib figure
        self.fig = Figure(figsize=(3.5, 6))
        self.canvas = FigureCanvas(self.fig)
        self.fig.patch.set_facecolor('white')
        
        # Create single axis for stats display
        self.ax_overview = self.fig.add_subplot(111)
        self.ax_overview.axis('off')
        self.ax_overview.set_title('Overview', fontweight='bold', fontsize=11, pad=10)
        
        # Initial waiting message
        self._update_overview_waiting()
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        
        # Draw initial state
        self.canvas.draw()
    
    def _update_overview_waiting(self):
        """Update overview with waiting message."""
        self.ax_overview.clear()
        self.ax_overview.axis('off')
        self.ax_overview.set_title('Overview', fontweight='bold', fontsize=11, pad=10)
        
        text_str = "Waiting for data from device..."
        self.ax_overview.text(0.05, 0.95, text_str, transform=self.ax_overview.transAxes,
                             fontsize=10, verticalalignment='top', fontfamily='monospace',
                             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        self.canvas.draw()
    
    def update_stats(self, sample):
        """Update stats display with IMU sample data."""
        from imu_viewer.models import ImuSample
        if sample and isinstance(sample, ImuSample):
            self._update_overview(sample)
        else:
            self._update_overview_waiting()
    
    def _update_overview(self, sample):
        """Update overview table (same code as imu_viewer)."""
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
        self.canvas.draw()

