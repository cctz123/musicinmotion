# IMU Viewer for WT901WIFI

A real-time visualization tool for the WitMotion WT901WIFI IMU device, displaying live sensor data including accelerometer, gyroscope, magnetometer, and orientation angles.

## Features

- **Live Numeric Readouts**: Real-time display of all sensor values
- **Compass Visualization**: Heading indicator using yaw angle
- **Artificial Horizon**: Roll and pitch visualization
- **Time-Series Plots**: Historical data for angles and acceleration
- **CSV Logging**: Optional data logging to CSV files

## Requirements

- Python 3.9 or higher
- macOS (tested on macOS, but should work on Linux/Windows with port adjustments)
- WT901WIFI IMU device connected via USB serial
- Virtual environment (recommended)

## Installation

1. **Create and activate a virtual environment**:

```bash
python -m venv .venv
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows
```

2. **Install dependencies**:

```bash
pip install -r requirements.txt
```

The required packages are:
- `pyserial` - Serial communication
- `matplotlib` - Visualization
- `numpy` - Numerical operations

## Usage

### Basic Usage

Run with default settings (port `/dev/tty.usbserial-10`, baud rate `9600`):

From the project root:
```bash
python imu_viewer/app.py
```

Or from inside the `imu_viewer` directory:
```bash
cd imu_viewer && python app.py
```

### Command Line Options

```bash
python imu_viewer/app.py [OPTIONS]
```

**Options:**
- `--port, -p PORT`: Serial port path (default: `/dev/tty.usbserial-10`)
- `--baud, -b BAUD`: Baud rate (default: `9600`)
- `--log, -l FILE`: Log samples to CSV file
- `--list-ports`: List available serial ports and exit
- `--history-seconds SECONDS`: Number of seconds of history to display (default: `20.0`)
- `--update-rate RATE`: Target UI update rate in Hz (default: `30.0`)

### Examples

**Use custom port and baud rate:**
```bash
python imu_viewer/app.py --port /dev/tty.usbserial-10 --baud 9600
```

**Enable CSV logging:**
```bash
python imu_viewer/app.py --log imu_data.csv
```

**List available serial ports:**
```bash
python imu_viewer/app.py --list-ports
```

**Full example with all options:**
```bash
python imu_viewer/app.py --port /dev/tty.usbserial-10 --baud 9600 --log imu_log.csv --history-seconds 30 --update-rate 50
```

## Finding Your Serial Port

On macOS, USB serial devices typically appear as `/dev/tty.usbserial-*` or `/dev/tty.usbmodem*`. You can:

1. Use the `--list-ports` option to see available ports
2. Check System Information → USB to see connected devices
3. Look in `/dev/` for `tty.usb*` devices

## CSV Log Format

When logging is enabled, the CSV file contains the following columns:

- `timestamp`: ISO format timestamp
- `device_id`: Device identifier
- `ax_g, ay_g, az_g`: Accelerometer values in g
- `gx_dps, gy_dps, gz_dps`: Gyroscope values in degrees per second
- `hx_uT, hy_uT, hz_uT`: Magnetometer values in microtesla
- `roll_deg, pitch_deg, yaw_deg`: Orientation angles in degrees
- `temp_C`: Temperature in Celsius
- `battery_V`: Battery voltage
- `rssi_dBm`: WiFi signal strength in dBm
- `version_raw`: Firmware version

## Display Panels

The application window contains four main panels:

1. **Numeric Readout** (top-left): Current values for all sensors
2. **Artificial Horizon** (top-right): Visual representation of roll and pitch
3. **Compass** (bottom-left): Heading indicator based on yaw angle
4. **Time-Series Plots** (bottom): Historical data for angles and acceleration magnitude

## Troubleshooting

### Serial Port Permission Denied

On macOS/Linux, you may need to add your user to the `dialout` group or use `sudo`. Alternatively, check System Preferences → Security & Privacy for USB device access.

### No Data Appearing

1. Verify the device is powered on and connected
2. Check the serial port path with `--list-ports`
3. Ensure the baud rate matches the device configuration (default: 9600)
4. Verify the device is streaming WT55 protocol frames

### Window Not Updating

- Ensure matplotlib backend supports interactive mode (usually automatic)
- Try reducing `--update-rate` if performance is poor
- Check that samples are being received (watch console output)

## Protocol Details

The application decodes the WT55 protocol frame format from the WT901WIFI device. Each frame is 54 bytes and includes:

- Header: `WT55` (4 bytes)
- Device ID: 8 ASCII characters
- Timestamp: Year, month, day, hour, minute, second, milliseconds
- Sensor data: Accelerometer, gyroscope, magnetometer (16-bit signed integers)
- Orientation: Roll, pitch, yaw angles (16-bit signed integers)
- Status: Temperature, battery, RSSI, firmware version

Raw values are converted to physical units according to the device specifications:
- Accelerometer: ±16g range
- Gyroscope: ±2000 deg/s range
- Angles: ±180 degrees (yaw normalized to 0-360°)
- Temperature: °C (raw / 100)
- Battery: Volts (raw / 100)

## License

This project is provided as-is for use with WT901WIFI IMU devices.

## Support

For issues related to:
- **Device communication**: Check device documentation and serial port settings
- **Protocol decoding**: Verify frame format matches WT55 specification
- **Visualization**: Ensure matplotlib is properly installed and backend is compatible

