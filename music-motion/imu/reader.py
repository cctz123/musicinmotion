"""IMU reader wrapper/manager."""

# This module wraps the imu_viewer package to provide a unified interface
# for IMU data reading across different modes (USB, WIFI_AP, WIFI_STA)

# TODO: Extract IMU reader initialization and management from motion-app.py
# This should handle:
# - Mode selection (USB, WIFI_AP, WIFI_STA)
# - Reader initialization
# - Data stream management
# - Error handling

# Example usage (to be implemented):
# from music_motion.imu.reader import ImuReader
# reader = ImuReader(mode='usb')
# reader.start()
# sample = reader.read_sample()

