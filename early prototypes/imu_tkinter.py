import socket
import threading
import struct
import time
import tkinter as tk
import json
import serial
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Tuple


# ==========================
# Configuration
# ==========================

# Config file path (in project root)
CONFIG_FILE = Path(__file__).parent / ".imuconfig"


def load_config():
    """Load configuration from .imuconfig file."""
    if not CONFIG_FILE.exists():
        print(f"Warning: {CONFIG_FILE} not found, using defaults")
        return {
            "mode": "usb",
            "usb": {"port": "/dev/tty.usbserial-10", "baud": 9600},
            "wifi": {"port": 1399, "use_tcp": False},
            "ap": {"ip": "192.168.4.1", "port": 1399}
        }
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        # Set defaults if missing
        if "mode" not in config:
            config["mode"] = "usb"
        return config
    except Exception as e:
        print(f"Error loading config: {e}, using defaults")
        return {
            "mode": "usb",
            "usb": {"port": "/dev/tty.usbserial-10", "baud": 9600},
            "wifi": {"port": 1399, "use_tcp": False},
            "ap": {"ip": "192.168.4.1", "port": 1399}
        }

# UI configuration
WINDOW_WIDTH = 400
WINDOW_HEIGHT = 400
DOT_RADIUS = 20
FPS = 60  # target frames per second

# How many degrees of tilt correspond to full deflection of the dot
MAX_TILT_DEG = 5.0


# ==========================
# IMU Data Structures
# ==========================

@dataclass
class IMUAngles:
    roll: float = 0.0   # X-axis tilt (left/right)
    pitch: float = 0.0  # Y-axis tilt (forward/back)
    yaw: float = 0.0    # Z-axis heading


@dataclass
class SharedIMUState:
    """Angles shared between UDP thread and Tkinter thread."""
    angles: IMUAngles = field(default_factory=IMUAngles)
    lock: threading.Lock = field(default_factory=threading.Lock)


# ==========================
# Data Receiver Threads
# ==========================

class IMUSerialReceiver(threading.Thread):
    """
    Background thread that reads from USB serial port and parses 54-byte WT55 frames.
    """
    
    FRAME_LEN = 54
    
    def __init__(self, port: str, baud: int, shared_state: SharedIMUState):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.shared_state = shared_state
        self.ser = None
        self.running = False
    
    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            print(f"[IMUSerialReceiver] Opened {self.port} at {self.baud} baud")
            time.sleep(2)  # Give device time to initialize
        except Exception as e:
            print(f"[IMUSerialReceiver] Failed to open serial port: {e}")
            return
        
        self.running = True
        
        while self.running:
            try:
                line = self.ser.readline()
                if not line:
                    continue
                
                # Parse frame (same format as UDP)
                if len(line) >= self.FRAME_LEN:
                    # Use first FRAME_LEN bytes
                    frame = line[:self.FRAME_LEN]
                    angles = self._parse_wt_frame(frame)
                    if angles is not None:
                        with self.shared_state.lock:
                            self.shared_state.angles = angles
            except serial.SerialException as e:
                print(f"[IMUSerialReceiver] Serial error: {e}")
                break
            except Exception as e:
                print(f"[IMUSerialReceiver] Error: {e}")
                continue
        
        if self.ser and self.ser.is_open:
            self.ser.close()
        print("[IMUSerialReceiver] Stopped")
    
    def stop(self):
        self.running = False
    
    @staticmethod
    def _parse_wt_frame(frame: bytes) -> Optional[IMUAngles]:
        """Parse a 54-byte WT55 frame into IMUAngles."""
        if len(frame) < IMUSerialReceiver.FRAME_LEN:
            return None
        
        # Validate header
        if frame[0:4] != b"WT55":
            return None
        
        try:
            # Angles are at same offsets as UDP frames
            roll_raw = int.from_bytes(frame[32:34], byteorder="little", signed=True)
            pitch_raw = int.from_bytes(frame[34:36], byteorder="little", signed=True)
            yaw_raw = int.from_bytes(frame[36:38], byteorder="little", signed=True)
        except Exception as e:
            return None
        
        factor = 180.0 / 32768.0
        roll_deg = roll_raw * factor
        pitch_deg = pitch_raw * factor
        yaw_deg = yaw_raw * factor
        
        return IMUAngles(roll=roll_deg, pitch=pitch_deg, yaw=yaw_deg)


class IMUUDPReceiver(threading.Thread):
    """
    Background thread that listens to WT901WIFI over UDP (WiFi AP mode)
    and parses 54-byte "WT..." records into roll/pitch/yaw angles.

    Each record looks like:
      - 0-1:   'W','T'  (0x57, 0x54)
      - 2-11:  ASCII serial like '5500007991'
      - 12-15: zeros / flags
      - 16-51: packed 16-bit fields
      - 52-53: 0x0D 0x0A terminator

    From your capture, angles appear at:
      - roll_raw  = int16 at offset 32
      - pitch_raw = int16 at offset 34
      - yaw_raw   = int16 at offset 36
    Angle degrees = raw / 32768.0 * 180.0
    """

    FRAME_LEN = 54

    def __init__(self, ip: str, port: int, shared_state: SharedIMUState):
        super().__init__(daemon=True)
        self.ip = ip
        self.port = port
        self.shared_state = shared_state
        self.sock = None
        self.buffer = bytearray()
        self.running = False

    def run(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.ip, self.port))
        self.sock.settimeout(0.5)

        self.running = True
        print(f"[IMUUDPReceiver] Listening on {self.ip}:{self.port}")

        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break  # socket closed

            # Append to rolling buffer and parse what we can
            self.buffer.extend(data)
            self._parse_buffer()

        if self.sock:
            self.sock.close()
        print("[IMUUDPReceiver] Stopped")

    def stop(self):
        self.running = False

    def _parse_buffer(self):
        """
        Look for 54-byte records starting with 'WT' (0x57,0x54)
        and ending with 0x0D,0x0A. Parse all full records we can.
        """
        while True:
            # Need at least one full frame
            if len(self.buffer) < self.FRAME_LEN:
                return

            # Find header 'W','T'
            try:
                start = self.buffer.index(0x57)  # 'W'
            except ValueError:
                # No 'W' at all, clear buffer
                self.buffer.clear()
                return

            # Ensure next byte is 'T'; if not, skip this 'W'
            if start + 1 >= len(self.buffer) or self.buffer[start + 1] != 0x54:
                # Drop this byte and search again next time
                del self.buffer[:start + 1]
                continue

            # If not enough bytes for a full frame from 'WT', wait for more
            if start + self.FRAME_LEN > len(self.buffer):
                # Keep only the tail starting at 'WT'
                if start > 0:
                    del self.buffer[:start]
                return

            frame = self.buffer[start:start + self.FRAME_LEN]

            # Check for 0x0D 0x0A terminator at end
            if frame[-2] != 0x0D or frame[-1] != 0x0A:
                # Not a valid frame, drop this 'W' and continue
                del self.buffer[:start + 1]
                continue

            # At this point we have a full 54-byte WT frame
            del self.buffer[:start + self.FRAME_LEN]

            angles = self._parse_wt_wifi_frame(frame)
            if angles is not None:
                with self.shared_state.lock:
                    self.shared_state.angles = angles

    @staticmethod
    def _parse_wt_wifi_frame(frame: bytes) -> Optional[IMUAngles]:
        """
        Parse a 54-byte WT WiFi frame into IMUAngles.

        From reverse-engineering your sample:
          roll_raw  = int16 at offset 32
          pitch_raw = int16 at offset 34
          yaw_raw   = int16 at offset 36
        """
        if len(frame) != IMUUDPReceiver.FRAME_LEN:
            return None

        try:
            # int16 little-endian from given offsets
            roll_raw = int.from_bytes(frame[32:34], byteorder="little", signed=True)
            pitch_raw = int.from_bytes(frame[34:36], byteorder="little", signed=True)
            yaw_raw = int.from_bytes(frame[36:38], byteorder="little", signed=True)
        except Exception as e:
            print(f"[IMUUDPReceiver] Parse error: {e}")
            return None

        factor = 180.0 / 32768.0
        roll_deg = roll_raw * factor
        pitch_deg = pitch_raw * factor
        yaw_deg = yaw_raw * factor

        return IMUAngles(roll=roll_deg, pitch=pitch_deg, yaw=yaw_deg)


# ==========================
# Tkinter Visualizer
# ==========================

class IMUVisualizerApp:
    def __init__(self, root: tk.Tk, shared_state: SharedIMUState):
        self.root = root
        self.shared_state = shared_state

        self.root.title("WT901WIFI IMU Visualizer (Tilt -> Dot)")

        self.canvas = tk.Canvas(
            self.root,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            bg="white"
        )
        self.canvas.pack()

        # Center of the canvas
        self.cx = WINDOW_WIDTH // 2
        self.cy = WINDOW_HEIGHT // 2

        # Create the dot in the center
        self.dot = self.canvas.create_oval(
            self.cx - DOT_RADIUS, self.cy - DOT_RADIUS,
            self.cx + DOT_RADIUS, self.cy + DOT_RADIUS,
            fill="black"
        )

        # Text to show current angles
        self.text = self.canvas.create_text(
            10, 10,
            anchor="nw",
            text="Roll: 0.0 | Pitch: 0.0 | Yaw: 0.0",
            font=("Helvetica", 12)
        )

        # Start the update loop
        self.frame_interval_ms = int(1000 / FPS)
        self._schedule_next_frame()

    def _schedule_next_frame(self):
        self.root.after(self.frame_interval_ms, self._update_frame)

    def _update_frame(self):
        # Read the latest angles
        with self.shared_state.lock:
            angles = IMUAngles(
                roll=self.shared_state.angles.roll,
                pitch=self.shared_state.angles.pitch,
                yaw=self.shared_state.angles.yaw
            )

        # Map tilt to dot position
        x, y = self._map_tilt_to_canvas(angles.roll, angles.pitch)

        # Move the dot (set absolute coords)
        self.canvas.coords(
            self.dot,
            x - DOT_RADIUS, y - DOT_RADIUS,
            x + DOT_RADIUS, y + DOT_RADIUS
        )

        # Update text
        self.canvas.itemconfigure(
            self.text,
            text=f"Roll: {angles.roll:6.2f}°  Pitch: {angles.pitch:6.2f}°  Yaw: {angles.yaw:6.2f}°"
        )

        # Schedule next frame
        self._schedule_next_frame()

    def _map_tilt_to_canvas(self, roll_deg: float, pitch_deg: float) -> Tuple[float, float]:
        """
        Map roll/pitch in degrees to X/Y on the canvas.
        - roll moves the dot left/right
        - pitch moves the dot up/down
        We clamp at ±MAX_TILT_DEG.
        """
        # Clamp
        roll = max(-MAX_TILT_DEG, min(MAX_TILT_DEG, roll_deg))
        pitch = max(-MAX_TILT_DEG, min(MAX_TILT_DEG, pitch_deg))

        # Normalize to [-1, 1]
        roll_norm = roll / MAX_TILT_DEG
        pitch_norm = pitch / MAX_TILT_DEG

        # How far from center can we go?
        max_dx = WINDOW_WIDTH // 2 - DOT_RADIUS - 5
        max_dy = WINDOW_HEIGHT // 2 - DOT_RADIUS - 5

        x = self.cx + roll_norm * max_dx
        # Pitch up (positive) moves dot UP, so subtract
        y = self.cy - pitch_norm * max_dy

        return x, y


# ==========================
# Main
# ==========================

def main():
    # Load configuration
    config = load_config()
    mode = config.get("mode", "usb").lower()
    
    shared_state = SharedIMUState()
    receiver = None
    
    # Start appropriate receiver based on mode
    if mode == "usb":
        usb_cfg = config.get("usb", {})
        port = usb_cfg.get("port", "/dev/tty.usbserial-10")
        baud = usb_cfg.get("baud", 9600)
        print(f"Starting in USB mode: {port} @ {baud} baud")
        receiver = IMUSerialReceiver(port, baud, shared_state)
    elif mode == "sta":
        wifi_cfg = config.get("wifi", {})
        port = wifi_cfg.get("port", 1399)
        print(f"Starting in WiFi STA mode: UDP port {port}")
        receiver = IMUUDPReceiver("0.0.0.0", port, shared_state)
    elif mode == "ap":
        ap_cfg = config.get("ap", {})
        port = ap_cfg.get("port", 1399)
        print(f"Starting in WiFi AP mode: UDP port {port}")
        receiver = IMUUDPReceiver("0.0.0.0", port, shared_state)
    else:
        print(f"Unknown mode '{mode}', defaulting to USB")
        usb_cfg = config.get("usb", {})
        port = usb_cfg.get("port", "/dev/tty.usbserial-10")
        baud = usb_cfg.get("baud", 9600)
        receiver = IMUSerialReceiver(port, baud, shared_state)
    
    if receiver:
        receiver.start()
    
    # Start Tkinter app
    root = tk.Tk()
    app = IMUVisualizerApp(root, shared_state)

    def on_close():
        if receiver:
            receiver.stop()
        # Give the thread a moment to exit
        time.sleep(0.1)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
