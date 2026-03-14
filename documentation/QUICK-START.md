# Music Motion

A project for creating music through body motion, combining MediaPipe pose detection and IMU sensors with real-time audio processing.

## Getting Started

### Activate Virtual Environment

```bash
source .venv/bin/activate
```

### Initialize the IMU(s)

(1) Plug in the IMU into the Mac's USB port.  On the Macbook Air, plug it into the one closer to the Magsafe power socket.

(2) From terminal, verify that the Mac sees the IMU:

```bash
ls /dev/tty.*
```

You should see either  

```
 /dev/tty.usbserial-110 or  
 /dev/tty.usbserial-10
```

The rest of this assumes the IMU is plugged into `usbserial-110`

(3) Use `Screen` command to read what is coming off the IMU

```bash
screen /dev/tty.usbserial-110 9600
```

And then turn on the IMU. You should see characters start to appear. To quit screen, type `Ctrl + A` then `D` (or `Ctrl + A` then `:` then `exit`).

(4) Get the IMU(s) ready by putting them on `sta` mode so they begin to send data to the Mac.

First, get the IP address of the Mac, and update `.imuconfig` with the IP address.

```
  "wifi": {
    "ssid": "kumquat",
    "password": "5555512121",
    "port": 1399,
    "port2": 1398,
    "ip": "192.168.0.173",  <<- update this IP
    "use_tcp": false
```

Next, use the `imu-cli.py` tool to put the two IMUs in STA mode with the proper IP address.

```
python imu-cli.py mode --sta

# for the 2nd IMU:
python imu-cli.py mode --sta -- port 2
```

You should see this output:

```
Opened /dev/tty.usbserial-110 at 9600 baud
Setting device to STA mode (Station)...
Configuring STA mode with:
  SSID: kumquat
  Password: **********
  Destination IP: 192.168.0.173
  Destination Port: 1399
  Protocol: UDP

Sending Wi-Fi configuration command: IPWIFI:"kumquat","5555512121";UDP192.168.0.173,1399
Sent command: IPWIFI:"kumquat","5555512121";UDP192.168.0.173,1399

Wi-Fi configuration command sent. Device should now:
  1. Connect to Wi-Fi network: kumquat
  2. Connect as UDP client to 192.168.0.173:1399
  3. Start streaming data over Wi-Fi

Note: Device may need to be power cycled or rebooted for changes to take full effect.

Mode change command sent successfully!
```

(5) If you are unable to get on a WiFi network that allows the IMU to see the mac, then fall back on AP mode with the IMU service as the hot spot.  Note this will limit you to using a single IMU.

Note when you use the IMU as a hot spot, DO NOT TURN IT OFF, as that will shut down the hotspot and break the WiFi connection.  If you need to reset the IMU, remember to reconnect to its hotspot once it resets.

First, you may need to reset the IMU.  Use a pin tip to hold the reset button down for 10 seconds.  Use screen to confirm that it is in AP mode.

Second, update .imu config to set the mode = ap.  You may also set these fields, but it's not that important, as the apps do not need the SSID, and the IMUs all use the same ip and port when in AP mode.

```
  "ap": {
    "ssid": "WT5500008026",
    "ip": "192.168.4.1",
    "port": 1399
  }
```

Next, use the `imu-cli.py` tool to put the single IMU in STA mode.

```
python imu-cli.py mode --ap

```

Finally, from the Mac, connect to the IMU as a hot spot.  The SSID will look something like `WT5500008026`.  Then use imu-cli to see if you can read the IMU.

```
python imu-cli.py read --ap
```

To perform a hard reset of the IMU so it goes back into the factory state, there is a button inside a hole next to the power button.  Use a pen tip to hold down that button for 6-10 seconds.

**Detailed information** in [IMU.md](IMU.md)

## Next Steps

Go to [MUSIC-MOTION](MUSIC-MOTION.md) for information on the app.

---

For reference only, here are the key apps.

## Key Applications

### 1. IMU Command Line Tool

**Description:** IMU configuration and control utility. Read data over USB or Wi-Fi (AP/STA), set device mode (USB, AP, STA), and perform resets.

```bash
python imu-cli.py

usage: imu-cli.py [-h] COMMAND ...

IMU configuration and control utility

positional arguments:
  COMMAND     Command to execute
    read      Read and display IMU data (uses mode from .imuconfig by default)
    reset     Perform reset on the device (hard reset, soft reboot, or all)
    mode      Set or read device mode (AP, STA, or USB)

options:
  -h, --help  show this help message and exit

Examples:
  imu-cli.py read                 # Read using mode from .imuconfig (parsed, default)
  imu-cli.py read --usb           # Read over USB/Serial (override config mode)
  imu-cli.py read --ap             # Read over Wi-Fi AP mode (override config mode)
  imu-cli.py read --sta            # Read over Wi-Fi STA mode (override config mode)
  imu-cli.py read --parse          # Explicit parsed format output
  imu-cli.py read --raw            # Raw hex dump output
  imu-cli.py read --ap --raw       # AP mode with raw output
  imu-cli.py reset                 # Perform factory reset (hard reset, default)
  imu-cli.py reset --hard          # Perform factory reset (same as default)
  imu-cli.py reset --soft          # Perform soft reboot
  imu-cli.py reset --all           # Perform full reset sequence (standard output + factory reset + soft reboot)
  imu-cli.py mode                  # Read current device mode
  imu-cli.py mode --usb            # Set device to USB mode
  imu-cli.py mode --ap             # Set device to AP mode (SoftAP)
  imu-cli.py mode --sta            # Set device to STA mode (Station)
```

---

### 2. IMU Viewer

**Description:** Standalone IMU data visualization tool. Also used to log data from latency tests.

```bash
python -m imu_viewer.app
```

---

### 3. Music in Motion (mmotion)

**Description:** Final design: fused multimodal sensor pipeline that maps motion sensors to audio controls, with 3 mapping styles.

```bash
python mmotion.py
```

**Mapping Styles** include:

- `Air DJ`
- `Calm/Intense`
- `Two Handed Instrument`

---

### 4. Motion App (Legacy)

**Description:** Original monolithic application with all features in one file.

```bash
python motion-app.py
```

**Tabs:**

- **IMU Pipeline** — IMU-based visualization and sound: method selector (Prototype A through G for pitch/pan, dual IMUs, equalizer, etc.), USB or Wi‑Fi mode, real-time IMU → audio.
- **Hands Demo** — Live MediaPipe hand detection on the camera feed.
- **Yoga Pose Detector** — Live camera with pose skeleton overlay and pose cards (e.g. Tree, Downward Dog, Warrior I); real-time yoga pose detection and auto-scroll to the detected pose.
- **Music in Motion** — Camera + MediaPipe pose: left/right arm height drives a 7-band equalizer; plays music with pose-driven EQ.

---

### 5. Timbre Control 1

**Description:** First attempt at timbre control.

```bash
python timbre-control1.py
```

---

### 6. Timbre Control 2 (Simplified)

**Description:** Simplified timbre control with manual sliders for cutoff, resonance, attack, and brightness.

```bash
python timbre-control2.py
```

---

### 7. Timbre Control 3 (Latest - with Video & Sensor Control)

**Description:** Timbre control with MediaPipe pose detection. Connects hand height to audio filter cutoff using atomic snapshot pattern for thread-safe sensor-to-music pipeline.

```bash
python fusionpipe.py
```

**Features:**

- Split-screen: Timbre controls (left) + Video with pose detection (right)
- "Sensor Control" toggle to connect hand height to cutoff frequency
- Two-stage sensor smoothing (median + two-speed one-pole)
- Confidence-weighted return-to-neutral when hands leave frame

---

### 8. IMU Latency

**Description:** Measures latency between button press and IMU data detection.

```bash
python latency.py
```

---

