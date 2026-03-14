"""Serial reader and protocol decoder for WT901WIFI IMU."""
import struct
import threading
from datetime import datetime
from typing import Optional
import serial
import serial.tools.list_ports

from .base import ImuDataSource
from ..models import ImuSample


class SerialImuReader(ImuDataSource):
    """Reads and decodes WT55 protocol frames from WT901WIFI IMU over USB serial."""

    FRAME_LENGTH = 54
    HEADER = b"WT55"

    def __init__(self, port: str, baud: int = 9600):
        """
        Initialize serial IMU reader.

        Args:
            port: Serial port path (e.g., '/dev/tty.usbserial-10')
            baud: Baud rate (ignored - USB/Serial is hardcoded to 9600)
        """
        super().__init__()
        self.port = port
        # USB/Serial is hardcoded to 9600 baud - device doesn't accept other rates
        self.baud = 9600
        self.ser: Optional[serial.Serial] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """Open serial port and start reading thread."""
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            print(f"Opened {self.port} at {self.baud} baud")
            # Give device time to initialize (matching imu_config.py behavior)
            import time
            time.sleep(2)
            print(f"Serial port ready, starting read loop...")
        except serial.SerialException as e:
            raise RuntimeError(f"Failed to open serial port {self.port}: {e}")

        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop reading and close serial port."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send_command(self, command: str):
        """
        Send an ASCII command to the device over serial.

        Args:
            command: ASCII command string (will be terminated with \\r\\n)
        """
        if self.ser and self.ser.is_open:
            cmd_bytes = (command + '\r\n').encode('ascii')
            self.ser.write(cmd_bytes)
            self.ser.flush()

    def _read_loop(self):
        """Background thread that reads serial data."""
        frames_found = 0
        
        while self.running:
            try:
                # Use readline() like imu_config.py - this blocks until a complete line is received
                line = self.ser.readline()
                if not line:
                    continue
                
                # Validate minimum frame length (matching imu_config.py approach)
                HEADER_LEN = 12  # "WT5500007991" length
                if len(line) < HEADER_LEN + 2:
                    # Too short to be a valid frame, skip it
                    continue
                
                # Decode the frame (will validate exact length internally)
                sample = self._decode_frame(line)
                if sample:
                    frames_found += 1
                    if frames_found == 1:
                        print(f"First frame decoded successfully! Device ID: {sample.device_id}")
                    self._put_sample(sample)

            except serial.SerialException as e:
                print(f"Serial error: {e}")
                break
            except Exception as e:
                print(f"Error in read loop: {e}")
                import traceback
                traceback.print_exc()
                continue

    def _decode_frame(self, line: bytes) -> Optional[ImuSample]:
        """
        Decode a WT55 protocol frame.

        Frame structure (54 bytes):
        - Bytes 0-3: Header "WT55"
        - Bytes 4-11: Device ID (8 ASCII chars)
        - Bytes 12-19: Time fields (year, month, day, hour, minute, second, ms_low, ms_high)
        - Bytes 20-51: Data fields (16-bit little-endian signed/unsigned)
        - Bytes 52-53: CR LF (0x0D 0x0A)
        """
        # Validate minimum length (matching imu_config.py approach)
        if len(line) < self.FRAME_LENGTH:
            return None

        # Validate header
        if line[0:4] != self.HEADER:
            return None

        # Use only the first FRAME_LENGTH bytes if line is longer (matching imu_config.py)
        if len(line) > self.FRAME_LENGTH:
            line = line[:self.FRAME_LENGTH]
        
        # Note: We don't strictly validate line ending like imu_config.py doesn't
        # It just assumes the last 2 bytes are CR LF and strips them

        try:
            # Extract raw frame data for debugging (similar to testimu2.py format)
            HEADER_LEN = 12  # "WT5500007991" length
            if len(line) >= HEADER_LEN + 2:
                raw_header = line[:HEADER_LEN].decode('ascii', errors='ignore')
                raw_payload = line[HEADER_LEN:-2]  # strip off CR LF
                raw_payload_hex = raw_payload.hex(" ")
                
                # Interpret payload as sequence of signed 16-bit integers (little-endian)
                if len(raw_payload) % 2 == 0:
                    raw_int16_values = struct.unpack("<" + "h" * (len(raw_payload) // 2), raw_payload)
                else:
                    raw_int16_values = ()
            else:
                raw_header = ""
                raw_payload_hex = ""
                raw_int16_values = ()

            # Device ID (bytes 4-12, 8 ASCII chars)
            device_id = line[4:12].decode('ascii', errors='ignore').strip()

            # Time fields (bytes 12-20)
            year = 2000 + line[12]
            month = line[13]
            day = line[14]
            hour = line[15]
            minute = line[16]
            second = line[17]
            ms_low = line[18]
            ms_high = line[19]
            milliseconds = (ms_high << 8) | ms_low

            # Validate time fields - device may send invalid time (e.g., month=0)
            # Use current time as fallback if device time is invalid
            try:
                # Clamp values to valid ranges
                month = max(1, min(12, month)) if month > 0 else 1
                day = max(1, min(31, day)) if day > 0 else 1
                hour = max(0, min(23, hour))
                minute = max(0, min(59, minute))
                second = max(0, min(59, second))
                milliseconds = max(0, min(999, milliseconds))
                
                timestamp = datetime(year, month, day, hour, minute, second, milliseconds * 1000)
            except (ValueError, OverflowError):
                # If timestamp is still invalid, use current time
                timestamp = datetime.now()

            # Data fields (bytes 20-51, little-endian)
            # Accel X, Y, Z (signed int16)
            ax_raw = struct.unpack('<h', line[20:22])[0]
            ay_raw = struct.unpack('<h', line[22:24])[0]
            az_raw = struct.unpack('<h', line[24:26])[0]

            # Gyro X, Y, Z (signed int16)
            gx_raw = struct.unpack('<h', line[26:28])[0]
            gy_raw = struct.unpack('<h', line[28:30])[0]
            gz_raw = struct.unpack('<h', line[30:32])[0]

            # Mag X, Y, Z (signed int16)
            hx_raw = struct.unpack('<h', line[32:34])[0]
            hy_raw = struct.unpack('<h', line[34:36])[0]
            hz_raw = struct.unpack('<h', line[36:38])[0]

            # Angles: Roll, Pitch, Yaw (signed int16)
            roll_raw = struct.unpack('<h', line[38:40])[0]
            pitch_raw = struct.unpack('<h', line[40:42])[0]
            yaw_raw = struct.unpack('<h', line[42:44])[0]

            # Temperature (signed int16)
            temp_raw = struct.unpack('<h', line[44:46])[0]

            # Battery (unsigned int16)
            batt_raw = struct.unpack('<H', line[46:48])[0]

            # RSSI (signed int16)
            rssi_raw = struct.unpack('<h', line[48:50])[0]

            # Version (unsigned int16)
            version_raw = struct.unpack('<H', line[50:52])[0]

            # Convert to physical units
            # Accelerometer: ±16g range
            ax_g = ax_raw / 32768.0 * 16.0
            ay_g = ay_raw / 32768.0 * 16.0
            az_g = az_raw / 32768.0 * 16.0

            # Gyroscope: ±2000 deg/s range
            gx_dps = gx_raw / 32768.0 * 2000.0
            gy_dps = gy_raw / 32768.0 * 2000.0
            gz_dps = gz_raw / 32768.0 * 2000.0

            # Magnetometer: µT
            hx_uT = hx_raw * 100.0 / 1024.0
            hy_uT = hy_raw * 100.0 / 1024.0
            hz_uT = hz_raw * 100.0 / 1024.0

            # Angles: ±180 degrees
            roll_deg = roll_raw / 32768.0 * 180.0
            pitch_deg = pitch_raw / 32768.0 * 180.0
            yaw_deg = yaw_raw / 32768.0 * 180.0
            # Normalize yaw to 0-360
            if yaw_deg < 0:
                yaw_deg += 360.0

            # Temperature: °C
            temp_C = temp_raw / 100.0

            # Battery: Percentage (0-255 where 255 = 100% charged)
            # Old voltage interpretation (commented out):
            # battery_V = batt_raw / 100.0  # Voltage in volts (e.g., 300 = 3.00V, 420 = 4.20V)
            battery_V = (batt_raw / 255.0) * 100.0  # Percentage (0-100%)

            # RSSI: dBm (raw value is already in dBm)
            rssi_dBm = float(rssi_raw)

            return ImuSample(
                device_id=device_id,
                timestamp=timestamp,
                accel_g=(ax_g, ay_g, az_g),
                gyro_dps=(gx_dps, gy_dps, gz_dps),
                mag_uT=(hx_uT, hy_uT, hz_uT),
                angles_deg=(roll_deg, pitch_deg, yaw_deg),
                temp_C=temp_C,
                battery_V=battery_V,
                rssi_dBm=rssi_dBm,
                version_raw=version_raw,
                raw_header=raw_header,
                raw_payload_hex=raw_payload_hex,
                raw_int16_values=raw_int16_values
            )

        except (struct.error, ValueError, IndexError) as e:
            # Malformed frame, skip it
            return None

    @staticmethod
    def list_ports():
        """List available serial ports."""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

