# Witmotion WT901WIFI IMU Device Guide

## Device Overview

The **Witmotion WT901WIFI** is a high-precision 9-axis inertial measurement unit (IMU) that combines:
- 3-axis accelerometer
- 3-axis gyroscope
- 3-axis magnetometer

The device can communicate via USB serial connection or Wi-Fi, making it suitable for a variety of applications including motion tracking, orientation sensing, and navigation systems.

The **Witmotion WT901WIFI** IMU comes with software that only works on Windows.  However, all the commands to read/config the device over USB/Serial ports and/or over WiFi is in the documentation, you technically don't need the software. 

This documentation describes how to get started with the device, and how to use the software we created to configure and demonstrate its capabilities.

Special note: remember that if the device stops working, then as a last resort, you can reset the device via the physical button next to the on/off switch.


## Operating Modes

The WT901WIFI supports three distinct operating modes:

### 1. USB Mode
- **Description**: Direct serial communication over USB cable
- **Connection**: Physical USB connection to computer
- **Protocol**: Serial communication at 9600 baud (hardcoded - device does not accept other baud rates)
- **Use Case**: Initial configuration, direct data streaming, device setup
- **Port Location**: On macOS, appears as `/dev/tty.usbserial-*` (e.g., `/dev/tty.usbserial-110`)
- **Important**: The WT901WIFI device is hardcoded to 9600 baud for USB/Serial communication. All tools (`imu-cli`, `imu_viewer`, `motion-app`) automatically use 9600 baud for USB connections, regardless of what's in `.imuconfig`.

### 2. AP Mode (Access Point)
- **Description**: Device creates its own Wi-Fi network
- **Connection**: Device acts as Wi-Fi access point
- **Use Case**: Direct connection to device without existing network infrastructure
- **Configuration**: Device broadcasts its own SSID that you can connect to

### 3. STA Mode (Station)
- **Description**: Device connects to an existing Wi-Fi network
- **Connection**: Device connects to your Wi-Fi router/network
- **Use Case**: Integration into existing network infrastructure, remote data streaming
- **Configuration**: Requires SSID, password, server IP, and port settings
- **Protocol**: TCP or UDP data transmission


## Getting started with the WT901WIFI on macOS

### 1. Plug the device into the Mac's USB port

The WT901WIFI IMU uses a USB-to-serial chip (typically CH340 or CP2102) that allows it to send traditional serial port commands to a USB connection.

Leave the device in the Off position to start, and plug the  device into the Mac's USB port.  USB-C to USB-C works fine.

macOS will typically recognize the device, and it will show up in `/dev/`: 

   ```bash   
   $ ls /dev/tty.*
    
   /dev/tty.usbserial-110
   /dev/tty.usbserial-10
   ```
   - `tty.*` devices are for incoming connections
   - The number suffix (e.g., `110`, `10`) may vary


### 2. View Serial Data with `screen`

The `screen` command is a built-in macOS Terminal utility that can connect to serial ports and display incoming data in real-time.

```bash
screen /dev/tty.usbserial-110 9600
```
  - First argument: Serial port path (e.g., `/dev/tty.usbserial-110`)
  - Second argument: Baud rate (must be 9600 - device is hardcoded to this rate for USB/Serial)

Once connected with `screen`, **turn on the device** and you should see raw binary data streaming from the device.  There should be some random strings, the word "POWER ON", and some text like this

```
POWER_ON
WORKMODE=2
CONNECTMODE=0
TCP:192.168.4.2,1399
UDP:192.168.4.2,1399
mode : softAP(36:5f:45:60:7d:17)
```
followed by a few commands.

The **WORKMODE and CONNECTMODE** parameters tell you what mode the IMU is currently in:
  - **WORKMODE=0**: USB / UART Only. WiFi is disabled, the IMU works only over serial (USB or TTL).
  - **WORKMODE=2**: WiFi Mode Enabled.  
  - **WORKMODE=1**: Not used.  Older units have a Bluetooth mode.  The WT901WIFI units don’t use this.
    - **CONNECTMODE=0**: AP Mode (SoftAP).  IMU creates its own WiFi network (SSID like WT901-xxxx), and you connect to the IMU.
    - **CONNECTMODE=1**: STA Mode (Station). IMU joins an existing WiFi network (e.g., your home router). The app connects through the router and listens to the port 

For complete details on all available work mode and connect mode values, refer to `documentation/WT901 IMU docs/WT901WIFI protocol.pdf`.

Once the power on is complete, the device should settle into streaming a sequence of rows that all start with WT5500008010, so something like this:
```
WT5500008010...
WT5500008010...
WT5500008010...
```

This is the raw binary data. The WT901WIFI is sending data frames in the WT55 protocol format:

**Frame Structure** (54 bytes total):
   - Bytes 0-3: Header `WT55`
   - Bytes 4-11: Device ID (8 ASCII characters)
   - Bytes 12-19: Timestamp (year, month, day, hour, minute, second, milliseconds)
   - Bytes 20-51: Sensor data (accelerometer, gyroscope, magnetometer, angles, temperature, battery, etc.)
   - Bytes 52-53: Line termination (`\r\n`)

To interpret it, refer to  `documentation/WT901 IMU docs/WT901WIFI protocol.pdf` for complete frame structure and data interpretation.

To disconnect from the serial port:
- Press `Ctrl+A`, then `K`, then `Y` to kill the session
- Or press `Ctrl+A`, then type `:quit` and press Enter


### 3. Connecting to the IMU as an AP server

The IMU by default acts as a WiFi access point -- you can connect to it and read its data using Wifi, which is much faster.  To test this out, 

**Confirm that the IMU is in AP mode**.  There are a few ways to do this:
  - When in AP mode, the IMU should be broadcasting a WiFi SSID, which will look like `WT5500008991`.  The last 4 digits may vary.  By default there does not seem to be a password.  
  - When plugged into the serial port and running `screen`, turn the IMU off and then on.  The first few lines should show the WORKMODE and CONNECTMODE, which should be as so:

```
POWER_ON
WORKMODE=2
CONNECTMODE=0
TCP:192.168.4.2,1399
UDP:192.168.4.2,1399
mode : softAP(36:5f:45:60:7d:17)
```

**Connect to the IMU's WiFi**, and verify that the laptop or computer's IP address is now `192.168.4.2`.

Also see if you can see the device:
  ```bash
  $ ping 192.168.4.1

  PING 192.168.4.1 (192.168.4.1): 56 data bytes
  64 bytes from 192.168.4.1: icmp_seq=0 ttl=128 time=3.924 ms
  64 bytes from 192.168.4.1: icmp_seq=1 ttl=128 time=11.382 ms
  64 bytes from 192.168.4.1: icmp_seq=2 ttl=128 time=6.463 ms
  ```

**View what the IMU is streaming**, using `netcat`, a built-in macOS Terminal utility that is the cloest thing to `screen` for USB.

To read using UDP, use
  ```bash
  nc -u -l 1399 | hexdump -C
  ```

If read using TCP, use
  ```bash
  nc -l 1399 | hexdump -C
  ```
  
You should see something like this:
```bash
$ nc -u -l 1399 | hexdump -C
00000000  57 54 35 35 30 30 30 30  37 39 39 31 00 00 00 00  |WT5500007991....|
00000010  06 19 64 00 0d 00 54 08  d8 01 02 00 de 00 e1 ff  |..d...T.........|
00000020  39 fe b3 fe 09 02 00 34  74 fe 36 9b f2 0d 85 01  |9......4t.6.....|
00000030  1f 00 eb 32 0d 0a 57 54  35 35 30 30 30 30 37 39  |...2..WT55000079|
00000040  39 31 00 00 00 00 06 19  c8 00 4c 00 69 07 f4 01  |91........L.i...|
00000050  a8 00 d8 00 19 00 37 fe  99 fe 0d 02 8a 34 1b ff  |......7......4..|
00000060  0c 9c f1 0d 85 01 1f 00  eb 32 0d 0a 57 54 35 35  |.........2..WT55|
00000070  30 30 30 30 37 39 39 31  00 00 00 00 06 19 2c 01  |00007991......,.|
00000080  07 00 01 08 05 02 cf 00  86 00 03 00 3a fe 93 fe  |............:...|
00000090  0f 02 5d 35 35 ff 9f 9c  ee 0d 85 01 1f 00 eb 32  |..]55..........2|
000000a0  0d 0a 57 54 35 35 30 30  30 30 37 39 39 31 00 00  |..WT5500007991..|
000000b0  00 00 06 19 90 01 07 00  cd 07 da 01 47 00 45 00  |............G.E.|
000000c0  03 00 38 fe 93 fe 11 02  04 36 3c ff e8 9c f2 0d  |..8......6<.....|
000000d0  85 01 1f 00 eb 32 0d 0a  57 54 35 35 30 30 30 30  |.....2..WT550000|
000000e0  37 39 39 31 00 00 00 00  06 19 f4 01 1e 00 f8 07  |7991............|
000000f0  e8 01 71 00 3a 00 00 00  36 fe 90 fe 10 02 56 36  |..q.:...6.....V6|
00000100  4c ff fe 9c f2 0d 85 01  1f 00 eb 32 0d 0a 57 54  |L..........2..WT|
00000110  35 35 30 30 30 30 37 39  39 31 00 00 00 00 06 19  |5500007991......|
00000120  58 02 1e 00 c9 07 cd 01  53 00 3a 00 dd ff 36 fe  |X.......S.:...6.|
00000130  8f fe 10 02 9c 36 76 ff  ef 9c ef 0d 85 01 1f 00  |.....6v.........|
00000140  eb 32 0d 0a 57 54 35 35  30 30 30 30 37 39 39 31  |.2..WT5500007991|
00000150  00 00 00 00 06 19 bc 02  19 00 c5 07 cf 01 33 00  |..............3.|
00000160  26 00 ff ff 36 fe 90 fe  11 02 ab 36 78 ff e1 9c  |&...6......6x...|
00000170  ee 0d 85 01 1f 00 eb 32  0d 0a 57 54 35 35 30 30  |.......2..WT5500|
00000180  30 30 37 39 39 31 00 00  00 00 06 19 20 03 19 00  |007991...... ...|
```


### 4. Connecting the IMU to the local Wi-Fi

The IMU can be put into an STA or Station mode, where it connects to the local Wifi and streams to a target IP Address and port.  This allows you to read the sensor data without disconnecting from your local Wifi.

To put the IMU into STA mode, use the imu-cli.py utility, details are below.  You can then do the following to test this out:

**Confirm that the IMU is in STA mode**. When plugged into the serial port and running `screen`, turn the IMU off and then on.  The IMU will start off in AP mode, so you will see the same as above, but then it will try to connect to the WiFI and show something like this:

```
connected with Fios-GTN8h, channel 1
dhcp client start...
ip:192.168.1.215,mask:255.255.255.0,gw:192.168.1.1
WIFI_CONNECT_OK
SERVER_UDP_CONNECT_OK
```
You can then use `nc` to read the stream.

  ```bash
  nc -u -l 1399 | hexdump -C
  ```



### 4. Using the Physical Reset Button

The WT901WIFI device has a physical reset button that can be used to restore factory settings or change device behavior.

**Location**: The reset button is typically a small button on the device (may require a pin or small tool to press)

**Reset Procedure**:
   - **Short Press**: May trigger a soft reboot or mode change
   - **Long Press** (typically 5+ seconds): Factory reset - restores all settings to defaults
   - **Press While Powering On**: May enter configuration mode

**After Factory Reset**:
   - All Wi-Fi settings are cleared
   - Device returns to USB mode
   - Default baud rate: 9600
   - Device ID may reset

The exact behavior of the reset button may vary by device firmware version. Refer to:
- `documentation/WT901 IMU docs/WT901WIFI Operation Manual.pdf` for detailed reset procedures
- Device may blink LEDs or change LED patterns during reset


## Using the IMU Python Tools

There are two Python applications that help you interact with the IMU device. Both applications use a shared configuration file (`.imuconfig` in the project root) that stores:
- USB serial port path
- Baud rate (stored but ignored - USB/Serial is hardcoded to 9600)
- Wi-Fi STA mode settings (SSID, password, port, protocol)
- Wi-Fi AP mode settings (SSID, IP address, port)

This allows you to configure the device once and reuse settings across different tools.

### imu-cli

A command-line utility for testing, reading, and controlling the IMU device.

**Usage**: `imu-cli <command> [options]`

#### Commands:

**`read`** - Read and display IMU data from the device
- `imu-cli read` - Read using mode from `.imuconfig` (parsed format, default)
- `imu-cli read --usb` - Read over USB/Serial (override config mode)
- `imu-cli read --ap` - Read over Wi-Fi AP mode (override config mode)
- `imu-cli read --sta` - Read over Wi-Fi STA mode (override config mode)
- `imu-cli read --parse` - Explicit parsed format output (default)
- `imu-cli read --raw` - Show raw hex dump in `hexdump -C` format
- Mode flags (`--usb`, `--ap`, `--sta`) and format flags (`--parse`, `--raw`) can be combined
- Examples:
  - `imu-cli read` - Uses mode from `.imuconfig`, parsed output
  - `imu-cli read --ap --raw` - AP mode with raw hex dump
  - `imu-cli read --usb` - USB mode, parsed output
- **USB mode**: Requires USB connection, uses port from `.imuconfig` (baud hardcoded to 9600)
- **AP mode**: Requires device in AP mode, computer connected to device's Wi-Fi, uses IP/port from `.imuconfig` "ap" section (UDP)
- **STA mode**: Requires device in STA mode, listens on port from `.imuconfig` "wifi" section (TCP or UDP server based on `use_tcp` setting)

**`reset`** - Perform device reset operations (requires USB connection)
- `imu-cli reset` - Factory reset (hard reset, default)
  - Sends `FF AA 52 00` command to restore factory defaults
- `imu-cli reset --hard` - Factory reset (same as default)
- `imu-cli reset --soft` - Soft reboot
  - Sends `FF AA 55 00` command to reboot device without resetting settings
- `imu-cli reset --all` - Full reset sequence
  - Performs: standard output mode (`FF AA 60 00`) + factory reset + soft reboot
  - Automatically sets work mode = 2 and connect mode = 0 before reset commands

All reset commands automatically configure the device mode (work mode = 2, connect mode = 0) before executing the reset operation.

**`mode`** - Set or read device mode (requires USB connection)
- `imu-cli mode` - Read current device mode
  - Reads WORKMODE and CONNECTMODE from device output stream
  - Displays current mode: USB, AP (SoftAP), or STA (Station)
- `imu-cli mode --usb` - Set device to USB mode
  - Sends `FF AA 5B 00` (WORKMODE=0, USB/UART only, WiFi disabled)
- `imu-cli mode --ap` - Set device to AP mode (SoftAP)
  - Sends `FF AA 5B 02` (WORKMODE=2, WiFi enabled) + `FF AA 5C 00` (CONNECTMODE=0, AP mode)
  - Device creates its own Wi-Fi network (SSID like WT901-xxxx)
- `imu-cli mode --sta` - Set device to STA mode (Station)
  - Sends `FF AA 5B 02` (WORKMODE=2, WiFi enabled) + `FF AA 5C 01` (CONNECTMODE=1, STA mode)
  - Device connects to an existing Wi-Fi network
- Note: Device may need to be power cycled or rebooted for mode changes to take full effect
- Example: `imu-cli mode --ap`

### imu_viewer

A full-featured GUI application with real-time visualization of IMU data, including:
- Overview statistics panel
- Artificial horizon display
- Compass (heading indicator)
- Time-series plots for angles and acceleration
- Raw device data display
- Support for both USB and Wi-Fi modes

**Usage**: `python imu_viewer/app.py [options]` (run from project root)

#### Options:

- `--port`, `-p <path>` - Serial port path (default: from `.imuconfig`)
  - Example: `--port /dev/tty.usbserial-110`
  - If specified, updates `.imuconfig` with the new port

- `--baud`, `-b <rate>` - Baud rate (ignored - USB/Serial is hardcoded to 9600)
  - Note: USB/Serial communication is hardcoded to 9600 baud. This option is accepted for compatibility but has no effect.

- `--log`, `-l <filename>` - Enable CSV logging to specified file
  - Example: `--log imu_data.csv`
  - Logs all IMU samples with timestamps and all sensor data

- `--list-ports` - List available serial ports and exit
  - Useful for discovering which port the device is connected to

- `--history-seconds <seconds>` - Number of seconds of history to display in plots (default: 20.0)
  - Example: `--history-seconds 30.0`

- `--update-rate <hz>` - Target UI update rate in Hz (default: 30.0)
  - Example: `--update-rate 60.0`

#### Features:

- **Mode Switching**: Toggle between USB and Wi-Fi modes via buttons
- **Wi-Fi Configuration**: Configure Wi-Fi settings through GUI dialog
- **Data Logging**: Start/stop CSV logging via button (creates timestamped files)
- **Real-time Visualization**: Live updates of all sensor data and visualizations

### Data Interpretation

Both tools interpret the raw IMU data as follows:
- **Accelerometer**: ±16g range, converted to g-force units
- **Gyroscope**: ±2000 deg/s range, converted to degrees per second
- **Magnetometer**: Converted to microtesla (µT)
- **Angles**: Roll, pitch, yaw in degrees (yaw normalized to 0-360°)
- **Battery**: Voltage in volts (typically 3.0-4.2V, may show 0.00V if not available)
- **Temperature**: Degrees Celsius
- **RSSI**: Received signal strength indicator in dBm (Wi-Fi mode only)




## Troubleshooting

### Device Not Appearing in `/dev/`
- Check USB cable connection
- Install USB-to-serial drivers if needed
- Try different USB port
- Check System Information → USB to see if device is recognized

### No Data in `screen`
- Verify baud rate is set to 9600 (device is hardcoded to this rate)
- Check that device is powered on
- Try disconnecting and reconnecting USB
- Verify you're using the correct port path

### Garbled Data
- Verify baud rate is set to 9600 (device is hardcoded to this rate for USB/Serial)
- Check USB cable quality
- Try different USB port
- Reset device to factory defaults

### Wi-Fi Connection Issues
- Ensure device is in the correct mode (AP or STA) using `imu-cli mode`
- For AP mode: Verify computer is connected to device's Wi-Fi network (SSID like WT901-xxxx)
- For STA mode: Verify SSID and password are correct in `.imuconfig`
- Check that IP address and port in `.imuconfig` match device settings
- Verify firewall allows incoming connections on the configured port
- Verify you are not running Cloudflare WARP or something similar
- Use `imu-cli mode --ap` or `imu-cli mode --sta` to set device mode

## Additional Resources

- **Protocol Documentation**: `documentation/WT901 IMU docs/WT901WIFI protocol.pdf`
- **Operation Manual**: `documentation/WT901 IMU docs/WT901WIFI Operation Manual.pdf`
- **Product Specifications**: `documentation/WT901 IMU docs/WT901WIFI Product Specifications.pdf`
- **SDK Documentation**: `documentation/WT901 IMU docs/WT901WiFi_SDK and communication protocol.txt`

## Quick Reference Commands

```bash
# List available serial ports
python imu_viewer/app.py --list-ports

# View raw serial data
screen /dev/tty.usbserial-110 9600

# Read and parse IMU data over USB/Serial
imu-cli read --parse

# Read raw hex dump over USB/Serial
imu-cli read --raw

# Read IMU data over Wi-Fi (AP mode, raw output)
imu-cli read --ap --raw

# Read current device mode
imu-cli mode

# Set device to AP mode
imu-cli mode --ap

# Set device to STA mode
imu-cli mode --sta

# Set device to USB mode
imu-cli mode --usb

# Factory reset
imu-cli reset --hard

# Soft reboot
imu-cli reset --soft

# Full reset sequence
imu-cli reset --all

```

