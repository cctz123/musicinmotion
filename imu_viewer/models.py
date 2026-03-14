"""Data models for IMU samples."""
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple


@dataclass
class ImuSample:
    """Decoded IMU sample from WT901WIFI device."""
    device_id: str
    timestamp: datetime
    accel_g: Tuple[float, float, float]  # ax, ay, az in g
    gyro_dps: Tuple[float, float, float]  # gx, gy, gz in deg/s
    mag_uT: Tuple[float, float, float]  # hx, hy, hz in µT
    angles_deg: Tuple[float, float, float]  # roll, pitch, yaw in deg
    temp_C: float
    battery_V: float
    rssi_dBm: float
    version_raw: int
    raw_header: str = ""  # Raw header string for debugging
    raw_payload_hex: str = ""  # Raw payload hex string for debugging
    raw_int16_values: Tuple = ()  # Raw int16 values for debugging

    def to_csv_row(self) -> str:
        """Convert sample to CSV row format."""
        return (
            f"{self.timestamp.isoformat()},"
            f"{self.device_id},"
            f"{self.accel_g[0]:.4f},{self.accel_g[1]:.4f},{self.accel_g[2]:.4f},"
            f"{self.gyro_dps[0]:.2f},{self.gyro_dps[1]:.2f},{self.gyro_dps[2]:.2f},"
            f"{self.mag_uT[0]:.2f},{self.mag_uT[1]:.2f},{self.mag_uT[2]:.2f},"
            f"{self.angles_deg[0]:.2f},{self.angles_deg[1]:.2f},{self.angles_deg[2]:.2f},"
            f"{self.temp_C:.2f},"
            f"{self.battery_V:.2f},"
            f"{self.rssi_dBm:.1f},"
            f"{self.version_raw}"
        )

    @staticmethod
    def csv_header() -> str:
        """Return CSV header row."""
        return (
            "timestamp,device_id,"
            "ax_g,ay_g,az_g,"
            "gx_dps,gy_dps,gz_dps,"
            "hx_uT,hy_uT,hz_uT,"
            "roll_deg,pitch_deg,yaw_deg,"
            "temp_C,battery_V,rssi_dBm,version_raw"
        )

