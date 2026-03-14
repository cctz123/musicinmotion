# Project Organization

This document describes the current layout and how to run the main applications.

## Current Layout

```
musicmotion/
├── motion-app.py              # Main PyQt5 app: IMU prototypes, vision tabs, music-in-motion
├── imu-cli.py                 # CLI for IMU config and testing
├── motion_fusion.py           # Sensor fusion (MediaPipe + IMU → MotionState); used by fusionpipe
├── timbre-control1.py         # Timbre control (10 sliders)
├── timbre-control2.py         # Timbre control simplified (4 sliders)
├── fusionpipe.py              # Timbre control with video + MediaPipe + IMU fusion
├── timbre-test.py             # Timbre/brightness experiments (filters, modulation)
├── latency.py                 # Latency measurement utility
│
├── imu_viewer/                # Standalone IMU Viewer (PyQt5); config, data sources, UI
├── music-motion/              # Refactored package (python -m music-motion); modular UI/IMU/audio
│
├── early prototypes/          # Legacy/experimental scripts (Tkinter, play-music, qr-code-prototype, etc.)
├── documentation/             # Docs (IMU, pipelines, install, quick-start, etc.)
├── posterboard/               # Static posterboard + docs viewer (HTML)
├── music/                     # Audio assets (e.g. music.mp3)
├── tickets/                   # Project tickets and specs
│
├── .imuconfig                 # IMU connection config (port, wifi, etc.)
├── requirements.txt
├── requirements-lock.txt
└── README.md
```

**Early prototypes:** The `early prototypes/` folder holds older or experimental scripts (e.g. Tkinter-based visualizers, play-music, qr-code-prototype, yoga/hands demos). They are not part of the main app flow; the main applications are listed above.

## Main Applications

| What | How to run |
|------|------------|
| **Motion app** (IMU + vision + music-in-motion) | `python motion-app.py` |
| **IMU Viewer** (standalone IMU diagnostics) | `python -m imu_viewer.app` or from inside `imu_viewer/`: `python app.py` |
| **IMU CLI** (config, read, test) | `python imu-cli.py read` (see `python imu-cli.py -h`) |
| **Music Motion package** (refactored UI) | From project root: `python -m music-motion` |
| **Timbre control (with video/fusion)** | `python fusionpipe.py` |
| **Timbre control (simplified)** | `python timbre-control2.py` |
| **Timbre test** (filters/effects experiments) | `python timbre-test.py` |

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
  imu-cli.py reset --all           # Full reset sequence (standard output + factory reset + soft reboot)
  imu-cli.py mode                  # Read current device mode
  imu-cli.py mode --usb            # Set device to USB mode
  imu-cli.py mode --ap             # Set device to AP mode (SoftAP)
  imu-cli.py mode --sta            # Set device to STA mode (Station)
```

### 2. Music Motion Package

**Description:** Full-featured application with multiple tabs for yoga pose detection, hands demo, IMU prototypes, and music-in-motion experiments.

```bash
python -m music-motion
```

Or:

```bash
python music-motion/main.py
```

**Tabs include:**

- Yoga Pose Detector (MediaPipe)
- Hands Demo (MediaPipe)
- IMU Prototypes (various IMU visualization methods)
- Music in Motion

### 3. Fusionpipe (Timbre + Video & Sensor Control)

**Description:** Timbre control with MediaPipe pose detection. Connects hand height to audio filter cutoff using atomic snapshot pattern for thread-safe sensor-to-music pipeline.

```bash
python fusionpipe.py
```

**Features:**

- Split-screen: Timbre controls (left) + Video with pose detection (right)
- "Sensor Control" toggle to connect hand height to cutoff frequency
- Two-stage sensor smoothing (median + two-speed one-pole)
- Confidence-weighted return-to-neutral when hands leave frame

### 4. Timbre Control 2 (Simplified)

**Description:** Simplified timbre control with manual sliders for cutoff, resonance, attack, and brightness.

```bash
python timbre-control2.py
```

### 5. Timbre Test

**Description:** Experimental timbre control with modulation effects (vibrato, tremolo, chorus, flanger, phaser).

```bash
python timbre-test.py
```

### 6. Motion App (Legacy)

**Description:** Original monolithic application with all features in one file.

```bash
python motion-app.py
```

### 7. IMU Latency Tool

**Description:** Measures latency between button press and IMU data detection.

```bash
python latency.py
```

### 8. IMU Viewer

**Description:** Standalone IMU data visualization tool. Also used to log data from latency tests.

```bash
python imu_viewer/app.py
```

## Key Dependencies

- **motion-app.py** — Uses IMU readers (from config), PyQt5, MediaPipe, sounddevice, librosa; no dependency on `motion_fusion.py`.
- **fusionpipe.py** — Uses `motion_fusion` (MotionFeatureExtractor, MotionState) for camera + IMU fusion into timbre controls.
- **imu_viewer** — Self-contained; its own config loader and data sources in `imu_viewer/`.

Configuration (ports, WiFi, etc.) is in `.imuconfig` at the project root. See [IMU Viewer](IMU-VIEWER.md) and [Installation](INSTALL.md) for setup.
