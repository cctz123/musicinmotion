#!/usr/bin/env python3
"""Timbre Control 2 - Simplified version based on timbre-test.py logic."""

import sys
import math
import time
import threading
import numpy as np
import sounddevice as sd
import librosa
import cv2
import mediapipe as mp
from pathlib import Path
from dataclasses import dataclass
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QProgressBar, QCheckBox, QSplitter, QFrame,
    QScrollArea, QLCDNumber, QComboBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QImage, QPixmap, QPalette, QColor, QPainter, QPen
from motion_fusion import MotionFeatureExtractor, MotionState


# -----------------------------------------------------------------------------
# Window and top/bottom layout
# -----------------------------------------------------------------------------
DEFAULT_WINDOW_WIDTH = 1500
DEFAULT_WINDOW_HEIGHT = 900
MIN_WINDOW_WIDTH = 1200
MIN_WINDOW_HEIGHT = 700

TOP_DEFAULT_HEIGHT_RATIO = 0.40   # Top band is 40% of window height by default
TOP_MAX_HEIGHT = 450
TOP_LEFT_MAX_WIDTH = 650          # Play + timeline column (max)
TOP_RIGHT_MIN_WIDTH = 720         # Video column (min)

# -----------------------------------------------------------------------------
# AUDIO_CONTROL: bottom-left (labels, sliders, checkboxes). We add widgets to its layout.
# No width cap; panel shares bottom 50/50 with MOTION_SENSOR.
# -----------------------------------------------------------------------------
BOTTOM_PANEL_MARGINS = 10
BOTTOM_PANEL_VERTICAL_SPACING = 10
# Both bottom panels use a QScrollArea with transparent background and sunken border
SCROLL_AREA_STYLESHEET = "QScrollArea { background-color: transparent; border: 1px solid palette(shadow); border-style: inset; }"
READING_LABEL_FONT = 12   # labels next to LCD readouts
AC_VERTICAL_SPACING = 10
SLIDER_LABEL_FONT = 12   # min_label and max_label (e.g. "0.0", "1.0")
SLIDER_WIDTH = 320
SLIDER_VALUE_FONT = 14   # value display next to each slider
# Modern slider: no ticks, thin track, blue fill left of handle, dark grey right, large round white handle
SLIDER_STYLESHEET = """
QSlider::groove:horizontal {
    height: 6px;
    background: #4a4a4a;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #2196F3;
    border-radius: 3px;
}
QSlider::add-page:horizontal {
    background: #4a4a4a;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 22px;
    height: 22px;
    margin: -8px 0;
    background: white;
    border: none;
    border-radius: 11px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.25);
}
QSlider::handle:horizontal:hover {
    background: #f5f5f5;
}
"""

# Prototype dropdown indices: 0=Manual, 1=Prototype A, 2=Prototype B, 3=Prototype C, 4=Cutoff Only
PROTOTYPE_INDEX_MANUAL = 0
PROTOTYPE_INDEX_PROTOTYPE_A = 1
PROTOTYPE_INDEX_PROTOTYPE_B = 2
PROTOTYPE_INDEX_PROTOTYPE_C = 3
PROTOTYPE_INDEX_CUTOFF_ONLY = 4
# Prototype A: tremolo on/off threshold (below = 0, above = ramp)
TREMOLO_ACTIVATION_THRESHOLD = 0.10
# Prototype B: calm vs intense mode hysteresis
MODE_HYSTERESIS_HIGH = 0.62
MODE_HYSTERESIS_LOW = 0.38
BRIGHTNESS_HEIGHT_EXPONENT = 1.6
JERK_BURST_THRESHOLD = 0.15
JERK_BURST_GAIN = 0.5
TAU_RESONANCE_BURST_DECAY = 0.35  # seconds
RESONANCE_CAP_INTENSE = 0.92
# Prototype C: Two-Hand Instrument
ATTACK_BURST_THRESHOLD = 0.15
ATTACK_BURST_GAIN = 0.5
TAU_ATTACK_BURST_DECAY = 0.30  # seconds
ATTACK_BASE_C = 0.0
MODE_FIXED_C = 0.6
BRIGHTNESS_C_OFFSET = 0.2
BRIGHTNESS_C_SCALE = 0.8
# Pan from lateral position: pan = 0.5 + PAN_LATERAL_K * (offset_R - offset_L)
PAN_LATERAL_K = 0.5

# Live waveform in top-right panel (rolling window of audio output)
WAVEFORM_DISPLAY_POINTS = 800
LIVE_WINDOW_SECONDS = 0.35


class LiveWaveformWidget(QWidget):
    """Draws a live, rolling waveform of the most recent audio output (same as play-music)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = None
        self.setMinimumHeight(160)
        self.setMinimumWidth(200)

    def set_live_samples(self, samples):
        if samples is None or len(samples) == 0:
            self.samples = None
        else:
            self.samples = np.asarray(samples, dtype=np.float32)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Baseline "0" at 25% from bottom; amplitude upward, 50% larger than before
        baseline_y = h * 0.75
        scale_y = (h * 0.75 - 4) * 0.95 * 5 * 1.5
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0))
        if self.samples is None or len(self.samples) < 2:
            painter.end()
            return
        n = len(self.samples)
        step = max(1, n // WAVEFORM_DISPLAY_POINTS)
        n_pts = min(WAVEFORM_DISPLAY_POINTS, (n + step - 1) // step)
        xs, ys = [], []
        for i in range(n_pts):
            start = i * step
            end = min(start + step, n)
            val = np.max(np.abs(self.samples[start:end])) if end > start else 0.0
            x = (i / max(1, n_pts - 1)) * (w - 1) if n_pts > 1 else 0
            y = baseline_y - val * scale_y
            ys.append(max(0, min(h, y)))
            xs.append(x)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        for i in range(len(xs) - 1):
            painter.drawLine(int(xs[i]), int(ys[i]), int(xs[i + 1]), int(ys[i + 1]))
        painter.end()


@dataclass
class TimbreControls:
    """Normalized timbre control vector - decoupled from UI."""
    V_cutoff: float = 0.0      # Low-pass cutoff (0-1, log-mapped to 250-12000 Hz)
    V_resonance: float = 0.0   # Resonance / Q intensity (0-1)
    V_attack: float = 0.0      # Spikiness / transient energy (0-1)
    V_brightness: float = 0.5  # Brightness macro (0-1, default 0.5 = neutral)
    V_tremolo: float = 0.0     # Tremolo depth (0-1)
    V_mode: float = 0.0        # Mode control: calm (0) → intense (1)
    V_volume: float = 0.5      # Volume/loudness (0-1, default 0.5 = normal level)
    V_pan: float = 0.5         # Stereo pan 0-1 (0.5 = center), maps to -1..+1 for equal-power


class TimbreControl3Window(QMainWindow):
    """Main window for timbre control with video and MediaPipe pose detection."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music in Motion")
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        
        # Audio state
        self.audio_data = None
        self.audio_sample_rate = None
        self.audio_position = 0
        self.audio_position_samples = 0  # Track position in samples for progress
        self.is_playing = False
        self.stream = None
        
        # Live waveform ring buffer (filled in audio callback, read in UI)
        self._live_buffer = None
        self._live_index = 0
        self._live_lock = threading.Lock()
        
        # TimbreControls - decoupled from UI (audio code only reads this)
        self.timbre_controls = TimbreControls()  # For UI updates
        
        # Atomic snapshot pattern - audio thread reads from this
        self.ctrl_snapshot = TimbreControls()  # Initial snapshot
        
        # App-level settings (not in TimbreControls - managed by app)
        self.smooth_cutoff = True   # Enable smoothing for cutoff
        self.smooth_resonance = False  # Enable smoothing for resonance (disabled by default)
        # Filter state (derived from TimbreControls, not UI)
        # Smoothed values (for parameter smoothing to avoid zipper noise)
        self.cutoff_hz = 0.0  # Will be calculated from TimbreControls
        self.cutoff_hz_smoothed = 0.0  # Smoothed cutoff value
        self.Q = 0.707  # Will be calculated from TimbreControls (default: Butterworth)
        
        # Low-pass biquad filter coefficients
        self.lpf_b0 = 0.0
        self.lpf_b1 = 0.0
        self.lpf_b2 = 0.0
        self.lpf_a1 = 0.0
        self.lpf_a2 = 0.0
        
        # Low-pass biquad filter state (needs 2 previous samples)
        self.lpf_x1 = 0.0  # x[n-1]
        self.lpf_x2 = 0.0  # x[n-2]
        self.lpf_y1 = 0.0  # y[n-1]
        self.lpf_y2 = 0.0  # y[n-2]
        
        # Tremolo state (LFO for amplitude modulation)
        self.tremolo_phase = 0.0  # Current LFO phase (0 to 2π)
        self.tremolo_rate_hz = 1.0  # LFO rate in Hz
        self.tremolo_depth = 0.0  # Tremolo depth (0.0 to 1.0)
        
        # Volume state (for smoothing)
        self.volume_gain_linear = 0.5  # Current linear gain (smoothed); 0.5 slider ≈ normal
        self.volume_gain_linear_smoothed = 0.5  # Smoothed value
        
        # Progress update timer
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._update_progress)
        self.progress_timer.setInterval(100)  # Update every 100ms
        
        # Video/camera state
        self.cap = None
        self.video_timer = QTimer()
        self.video_timer.timeout.connect(self._update_video_frame)
        self.video_timer.setInterval(33)  # ~30 FPS
        
        # MediaPipe pose solution
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        self.pose = None
        
        # Motion feature extractor
        self.motion_extractor = MotionFeatureExtractor(fps=30.0)
        self.current_motion_state = None  # Store current motion state for future use
        
        # Legacy sensor readings from MediaPipe (kept for backward compatibility)
        self.hand_height_L = 0.0
        self.hand_height_R = 0.0
        self.hands_spread = 0.0
        
        # Two-stage sensor smoothing for hand_height_R (legacy, now handled by motion_extractor)
        self._hand_height_R_history = [0.5, 0.5, 0.5]  # Last 3 frames for median filter
        self._smoothed_hand_height_R = 0.5
        
        # Prototype A smoothed state (updated when Prototype A is selected)
        self._hand_height_L_history = [0.5, 0.5, 0.5]
        self._smoothed_hand_height_L = 0.5
        self._smoothed_hand_spread = 0.5
        self._smoothed_lateral_offset_L = 0.5
        self._smoothed_lateral_offset_R = 0.5
        self._smoothed_activity_global = 0.0
        self._smoothed_shake_energy_R = 0.0
        
        # Prototype B state (reuses _smoothed_hand_spread, _smoothed_activity_global when B active)
        self._mode_state = 'calm'
        self._resonance_burst = 0.0
        self._last_burst_time = time.time()
        self._smoothed_arm_extension_L = 0.5
        
        # Prototype C state (reuses _smoothed_hand_height_L, _smoothed_lateral_offset_L, _smoothed_shake_energy_R when C active)
        self._smoothed_elbow_bend_L = 0.5
        self._smoothed_activity_R = 0.0
        self._attack_burst = 0.0
        self._last_attack_burst_time = time.time()
        
        # Confidence-weighted return-to-neutral (legacy, now handled by motion_extractor)
        self._last_good_hand_height_R = 0.5
        self._last_good_detection_time = time.time()
        self._confidence_threshold = 0.5
        self._grace_period_seconds = 0.2  # 200ms grace period
        self._decay_time_seconds = 1.0  # 1 second to return to neutral
        
        # Load audio file
        self._load_audio_file()
        
        # Initialize UI
        self._init_ui()
        
        # Initialize camera and MediaPipe
        self._init_camera()
        self._init_pose_detector()
        # Motion extractor is initialized in _init_pose_detector after pose detector is created
        
        # Initialize IMU readers (optional, graceful fallback if unavailable)
        self.imu_reader_L = None
        self.imu_reader_R = None
        self._init_imu_readers()
        
        # Note: Filter coefficients will be initialized when audio starts
        # (audio callback will sample TimbreControls at regular intervals)
    
    def _init_camera(self):
        """Initialize camera."""
        self.cap = cv2.VideoCapture(0)
        if self.cap.isOpened():
            self.video_timer.start()
    
    def _init_pose_detector(self):
        """Initialize MediaPipe pose detector (full body only, no face)."""
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        # Initialize motion feature extractor with MediaPipe (now that pose detector exists)
        self.motion_extractor.initialize_mediapipe(self.mp_pose, self.mp_drawing, self.pose)
    
    def _create_imu_reader(self, mode, config, is_left=True):
        """Create an IMU reader based on mode and configuration.
        
        Args:
            mode: IMU mode ("usb", "wifi_ap", "wifi_sta")
            config: Configuration dict from .imuconfig
            is_left: True for left IMU (port), False for right IMU (port2)
        
        Returns:
            IMU reader instance or None if unavailable
        """
        try:
            if mode == "usb":
                from imu_viewer.data_sources.serial_reader import SerialImuReader
                port = config.get("usb", {}).get("port", "/dev/tty.usbserial-10")
                baud = 9600
                reader = SerialImuReader(port, baud)
                reader.start()
                return reader
                
            elif mode == "wifi_ap" or mode == "ap":
                from imu_viewer.data_sources.wifi_ap_reader import WifiApImuReader
                if "ap" not in config:
                    return None
                ap_cfg = config["ap"]
                device_ip = ap_cfg.get("ip")
                device_port = ap_cfg.get("port")
                if not device_ip or not device_port:
                    return None
                reader = WifiApImuReader(device_ip=device_ip, device_port=device_port)
                reader.start()
                return reader
                
            elif mode == "wifi_sta" or mode == "sta":
                from imu_viewer.data_sources.wifi_reader import WifiImuReader
                if "wifi" not in config:
                    return None
                wifi_cfg = config["wifi"]
                use_tcp = wifi_cfg.get("use_tcp", False)
                
                # Left IMU uses port2, right IMU uses port (reversed to match mirrored video)
                if is_left:
                    device_port = wifi_cfg.get("port2")
                else:
                    device_port = wifi_cfg.get("port")
                
                if device_port is None:
                    return None
                
                reader = WifiImuReader(use_tcp=use_tcp, port=device_port)
                reader.start()
                return reader
                
        except Exception as e:
            print(f"Warning: Could not create IMU reader ({'left' if is_left else 'right'}, mode={mode}): {e}")
            return None
        
        return None
    
    def _init_imu_readers(self):
        """Initialize IMU readers (optional, graceful fallback if unavailable)."""
        try:
            from imu_viewer.config_loader import load_config
            config = load_config()
            
            # Auto-detect mode from config (accept "ap" as alias for "wifi_ap")
            mode = config.get("mode", "sta").lower()
            if mode == "ap":
                mode = "wifi_ap"
            if mode not in ["usb", "wifi_ap", "wifi_sta", "sta"]:
                print(f"Warning: Unknown IMU mode '{mode}', defaulting to 'sta'")
                mode = "sta"
            
            # AP mode: only one device; use it for both L and R
            if mode == "wifi_ap":
                self.imu_reader_L = self._create_imu_reader(mode, config, is_left=True)
                self.imu_reader_R = self.imu_reader_L  # same device drives both
                if self.imu_reader_L:
                    print(f"IMU initialized (mode: {mode}, AP single device → used for both L and R)")
                else:
                    print("IMU not available (AP not configured or unavailable)")
            else:
                # Initialize left IMU (uses 'port2', if available)
                # NOTE: Reversed from original - port2 is left, port is right (to match mirrored video)
                self.imu_reader_L = self._create_imu_reader(mode, config, is_left=True)
                if self.imu_reader_L:
                    print(f"Left IMU initialized (mode: {mode}, using port2)")
                else:
                    print("Left IMU not available (port2 not configured or unavailable)")
                # Initialize right IMU (uses 'port')
                self.imu_reader_R = self._create_imu_reader(mode, config, is_left=False)
                if self.imu_reader_R:
                    print(f"Right IMU initialized (mode: {mode}, using port)")
                else:
                    print("Right IMU not available")
                # If only one reader available, use it for both L and R so both indicators move
                if self.imu_reader_L is None and self.imu_reader_R is not None:
                    self.imu_reader_L = self.imu_reader_R
                    print("Single IMU (right): using for both L and R")
                elif self.imu_reader_R is None and self.imu_reader_L is not None:
                    self.imu_reader_R = self.imu_reader_L
                    print("Single IMU (left): using for both L and R")
            # Connect IMU readers to motion extractor
            self.motion_extractor.initialize_imu(self.imu_reader_L, self.imu_reader_R)
            
        except Exception as e:
            print(f"IMU initialization failed (continuing without IMU): {e}")
            # Continue without IMU - motion extractor handles None readers gracefully
            self.motion_extractor.initialize_imu(None, None)
    
    def _load_audio_file(self):
        """Load music.mp3 audio file."""
        script_dir = Path(__file__).parent
        possible_paths = [
            script_dir / "music" / "music.mp3",
            script_dir.parent / "music" / "music.mp3",
            Path("music/music.mp3"),
            Path("../music/music.mp3"),
        ]
        
        audio_path = None
        for path in possible_paths:
            abs_path = path.resolve()
            if abs_path.exists():
                audio_path = abs_path
                break
        
        if audio_path is None:
            raise FileNotFoundError(
                "Could not find music.mp3. Tried:\n" + 
                "\n".join(str(p.resolve()) for p in possible_paths)
            )
        
        print(f"Loading audio from: {audio_path}")
        self.audio_data, self.audio_sample_rate = librosa.load(
            str(audio_path), sr=None, mono=True
        )
        print(f"Loaded audio: {len(self.audio_data)} samples at {self.audio_sample_rate} Hz")
        
        # Calculate total duration
        self.total_duration_samples = len(self.audio_data)
        # Re-allocate live waveform buffer on next play (sample rate may have changed)
        self._live_buffer = None
    
    def _smooth_ar(self, target, prev, dt, tau_up_ms, tau_down_ms):
        """
        Asymmetric one-pole smoothing filter (faster up, slower down).
        
        Args:
            target: Target value
            prev: Previous smoothed value
            dt: Time step (1/sample_rate)
            tau_up_ms: Time constant when going up (faster response)
            tau_down_ms: Time constant when going down (slower response)
        
        Returns:
            Smoothed value
        """
        # Choose tau based on direction
        tau = (tau_up_ms / 1000.0) if target > prev else (tau_down_ms / 1000.0)
        alpha = 1.0 - math.exp(-dt / max(tau, 1e-6))
        return prev + alpha * (target - prev)
    
    def _apply_timbre_controls(self):
        """
        Apply TimbreControls to audio processing.
        This is the ONLY function that converts TimbreControls to DSP parameters.
        Audio code never reads UI sliders directly - only reads from atomic snapshot.
        All parameter changes are smoothed to avoid zipper noise.
        """
        # Read from atomic snapshot (lock-free, coherent)
        ctrl = self.ctrl_snapshot
        
        # === 1. Low-Pass Filter Cutoff (PRIMARY TIMBRE CONTROL) ===
        # Logarithmic mapping as specified in TICKET-P2-TIMBRE-CONTROL.MD
        f_min = 250.0      # Hz (very muffled)
        f_max = 12000.0    # Hz (very bright)
        
        # cutoff_hz = exp(lerp(log(f_min), log(f_max), ctrl["V_cutoff"]))
        target_cutoff_hz = math.exp(
            math.log(f_min) + ctrl.V_cutoff * (math.log(f_max) - math.log(f_min))
        )
        
        # === 3. Brightness Macro (Moves Multiple Parameters) ===
        # Apply brightness macro to cutoff BEFORE smoothing
        brightness = ctrl.V_brightness
        b = (brightness - 0.5) * 2.0   # b in [-1, +1]
        target_cutoff_hz *= 2.0 ** (0.35 * b)  # 0.5 => b=0 => multiplier 1.0
        
        # Apply asymmetric smoothing for cutoff (if enabled by app)
        if self.smooth_cutoff and self.audio_sample_rate and self.audio_sample_rate > 0:
            # Calculate time since last call (approximate: assume called every buffer)
            # For more accuracy, we could track actual time, but this approximation works
            # since we're called regularly at ~11.6ms intervals (512 samples / 44100 Hz)
            if not hasattr(self, '_last_smooth_time'):
                self._last_smooth_time = 0.0
                self._last_buffer_size = 512  # Default blocksize
            
            # Use the buffer size to calculate dt (time step per buffer call)
            # This will be updated in audio callback if needed
            dt = self._last_buffer_size / self.audio_sample_rate
            
            # For cutoff: fast response going up (8ms), slower going down (40ms)
            self.cutoff_hz_smoothed = self._smooth_ar(
                target_cutoff_hz, 
                self.cutoff_hz_smoothed, 
                dt, 
                tau_up_ms=8, 
                tau_down_ms=40
            )
            self.cutoff_hz = self.cutoff_hz_smoothed  # Use smoothed value for filter
        else:
            # No smoothing - use target directly
            self.cutoff_hz = target_cutoff_hz
            if not hasattr(self, 'cutoff_hz_smoothed'):
                self.cutoff_hz_smoothed = target_cutoff_hz
            else:
                self.cutoff_hz_smoothed = target_cutoff_hz  # Keep in sync
        
        # === 2. Resonance (Q) — Dramatic but Stable ===
        Q_min = 0.7
        
        # Mode control affects Q_max (calm vs intense)
        # From ticket: if V_mode > 0.6: Q_max = 10.0, else Q_max = 5.0
        if ctrl.V_mode > 0.6:
            Q_max = 10.0
        else:
            Q_max = 5.0
        
        # Q = lerp(Q_min, Q_max, ctrl["V_resonance"] ** 1.8)
        target_Q = Q_min + (Q_max - Q_min) * (ctrl.V_resonance ** 1.8)
        
        # Attack macro (recommended)
        # Q *= lerp(1.0, 1.5, ctrl["V_attack"])
        target_Q *= 1.0 + 0.5 * ctrl.V_attack
        # Q = clamp(Q, Q_min, Q_max)
        target_Q = max(Q_min, min(Q_max, target_Q))
        
        # Apply brightness macro to Q BEFORE smoothing
        # (brightness variable and b already calculated above for cutoff)
        target_Q *= 2.0 ** (0.10 * b)  # 0.5 => multiplier 1.0
        
        # Apply smoothing for Q (if enabled by app)
        if self.smooth_resonance and self.audio_sample_rate and self.audio_sample_rate > 0:
            if not hasattr(self, 'Q_smoothed'):
                self.Q_smoothed = target_Q
            
            if hasattr(self, '_last_buffer_size'):
                dt = self._last_buffer_size / self.audio_sample_rate
            else:
                dt = 512.0 / self.audio_sample_rate  # Default blocksize
            
            # Use symmetric smoothing for Q (can be made asymmetric later if needed)
            tau_Q = 20.0  # ms (as specified in ticket)
            self.Q_smoothed = self._smooth_ar(
                target_Q,
                self.Q_smoothed,
                dt,
                tau_up_ms=tau_Q,
                tau_down_ms=tau_Q
            )
            self.Q = self.Q_smoothed  # Use smoothed value
        else:
            # No smoothing - use target directly
            self.Q = target_Q
            if not hasattr(self, 'Q_smoothed'):
                self.Q_smoothed = target_Q
            else:
                self.Q_smoothed = target_Q  # Keep in sync
        
        # === Tremolo (Amplitude Modulation) ===
        # From ticket: depth = lerp(0.0, 0.8, V_tremolo * V_motion)
        # Since we don't have V_motion yet, use V_tremolo directly
        # Simplified: depth = lerp(0.0, 0.8, V_tremolo)
        self.tremolo_depth = max(0.0, min(0.8, ctrl.V_tremolo * 0.8))
        
        # From ticket: rate = lerp(1.0, 8.0, V_motion)
        # Simplified: use fixed rate or derive from tremolo value
        # For now, use a fixed moderate rate, or scale with tremolo
        # If tremolo is active, use rate based on mode
        if ctrl.V_tremolo > 0.01:  # If tremolo is active
            if ctrl.V_mode < 0.4:
                # Calm mode: slower rate, max 4.0 Hz
                self.tremolo_rate_hz = 1.0 + (ctrl.V_tremolo * 3.0)  # 1.0 to 4.0 Hz
            else:
                # Intense mode: faster rate
                self.tremolo_rate_hz = 1.0 + (ctrl.V_tremolo * 7.0)  # 1.0 to 8.0 Hz
        else:
            self.tremolo_rate_hz = 1.0  # Default when inactive
        
        # === Volume Control ===
        # V_volume ∈ [0,1] → gain_db = lerp(-30 dB, 0 dB, V_volume ^ curve)
        # Curve chosen so 50% slider = normal level (~-6 dB)
        volume_curve = 0.32  # 0.5^0.32 ≈ 0.8 → -6 dB at 50%
        volume_normalized = max(0.0, min(1.0, ctrl.V_volume))
        volume_curved = volume_normalized ** volume_curve
        
        # Map to gain in dB: -30 dB (silent) to 0 dB (full)
        gain_db_min = -30.0  # Silent
        gain_db_max = 0.0    # Full volume at 100%
        target_gain_db = gain_db_min + volume_curved * (gain_db_max - gain_db_min)
        
        # Convert dB to linear gain
        target_gain_linear = 10.0 ** (target_gain_db / 20.0)
        
        # Apply asymmetric smoothing for volume (fast attack, slow release)
        if self.audio_sample_rate and self.audio_sample_rate > 0:
            if hasattr(self, '_last_buffer_size'):
                dt = self._last_buffer_size / self.audio_sample_rate
            else:
                dt = 512.0 / self.audio_sample_rate  # Default blocksize
            
            # Fast attack (30-60ms), slow release (200-500ms)
            tau_attack_ms = 50.0   # 50ms attack
            tau_release_ms = 300.0  # 300ms release
            
            self.volume_gain_linear_smoothed = self._smooth_ar(
                target_gain_linear,
                self.volume_gain_linear_smoothed,
                dt,
                tau_up_ms=tau_attack_ms,
                tau_down_ms=tau_release_ms
            )
            self.volume_gain_linear = self.volume_gain_linear_smoothed
        else:
            # No smoothing if sample rate not available
            self.volume_gain_linear = target_gain_linear
            if not hasattr(self, 'volume_gain_linear_smoothed'):
                self.volume_gain_linear_smoothed = target_gain_linear
            else:
                self.volume_gain_linear_smoothed = target_gain_linear
        
        # Calculate biquad filter coefficients for low-pass filter with resonance
        if self.audio_sample_rate and self.audio_sample_rate > 0:
            self._calculate_biquad_coefficients()
        else:
            # Pass-through coefficients
            self.lpf_b0 = 1.0
            self.lpf_b1 = 0.0
            self.lpf_b2 = 0.0
            self.lpf_a1 = 0.0
            self.lpf_a2 = 0.0
    
    def _calculate_biquad_coefficients(self):
        """Calculate biquad low-pass filter coefficients with resonance - matching timbre-test.py."""
        # Standard biquad low-pass filter design
        # Based on RBJ Audio EQ Cookbook formulas (same as timbre-test.py)
        # Uses smoothed cutoff value to avoid zipper noise
        
        fc = self.cutoff_hz  # This is the smoothed value
        fs = self.audio_sample_rate
        Q = self.Q  # Q value from TimbreControls (with attack macro applied)
        
        # Normalized frequency
        w = 2.0 * math.pi * fc / fs
        
        # Pre-warping for bilinear transform
        k = math.tan(w / 2.0)
        
        # Calculate intermediate values
        k2 = k * k
        k_over_q = k / Q
        norm = 1.0 / (1.0 + k_over_q + k2)
        
        # Biquad coefficients for low-pass filter
        self.lpf_b0 = k2 * norm
        self.lpf_b1 = 2.0 * self.lpf_b0
        self.lpf_b2 = self.lpf_b0
        self.lpf_a1 = 2.0 * (k2 - 1.0) * norm
        self.lpf_a2 = (1.0 - k_over_q + k2) * norm
    
    def _init_ui(self):
        """Initialize the UI: top band (play + timeline | video), bottom band (AUDIO_CONTROL | MOTION_SENSOR)."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Main vertical splitter: TOP | BOTTOM
        main_splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(main_splitter)
        
        # --- TOP band (max height TOP_MAX_HEIGHT, default 40% of window) ---
        top_widget = QWidget()
        top_widget.setMaximumHeight(TOP_MAX_HEIGHT)
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        
        top_h_splitter = QSplitter(Qt.Horizontal)
        top_layout.addWidget(top_h_splitter)
        
        # Top-left: Video (min width TOP_RIGHT_MIN_WIDTH)
        top_left_widget = QWidget()
        top_left_widget.setMinimumWidth(TOP_RIGHT_MIN_WIDTH)
        top_left_layout = QVBoxLayout(top_left_widget)
        top_left_layout.setContentsMargins(0, 0, 0, 0)
        top_left_layout.setSpacing(10)
        self._init_video_ui(top_left_layout)
        top_h_splitter.addWidget(top_left_widget)
        
        # Top-right: Play button + music timeline (max width TOP_LEFT_MAX_WIDTH)
        top_right_widget = QWidget()
        top_right_widget.setMaximumWidth(TOP_LEFT_MAX_WIDTH)
        top_right_layout = QVBoxLayout(top_right_widget)
        top_right_layout.setContentsMargins(20, 20, 20, 20)
        top_right_layout.setSpacing(10)
        top_right_layout.setAlignment(Qt.AlignTop)
        self._init_play_timeline_ui(top_right_layout)
        top_h_splitter.addWidget(top_right_widget)
        
        # Initial top split: left = video (rest), right = play+timeline (650)
        top_h_splitter.setSizes([DEFAULT_WINDOW_WIDTH - TOP_LEFT_MAX_WIDTH, TOP_LEFT_MAX_WIDTH])
        
        main_splitter.addWidget(top_widget)
        
        # --- BOTTOM band: MOTION_SENSOR (left) | AUDIO_CONTROL (right), 50/50 ---
        bottom_splitter = QSplitter(Qt.Horizontal)
        
        motion_sensor_widget = QWidget()
        motion_sensor_layout = QVBoxLayout(motion_sensor_widget)
        motion_sensor_layout.setContentsMargins(BOTTOM_PANEL_MARGINS, BOTTOM_PANEL_MARGINS, BOTTOM_PANEL_MARGINS, BOTTOM_PANEL_MARGINS)
        motion_sensor_layout.setSpacing(BOTTOM_PANEL_VERTICAL_SPACING)
        motion_sensor_layout.setAlignment(Qt.AlignTop)
        self._init_stats_ui(motion_sensor_layout)
        bottom_splitter.addWidget(motion_sensor_widget)
        
        audio_control_widget = QWidget()
        audio_control_layout = QVBoxLayout(audio_control_widget)
        audio_control_layout.setContentsMargins(BOTTOM_PANEL_MARGINS, BOTTOM_PANEL_MARGINS, BOTTOM_PANEL_MARGINS, BOTTOM_PANEL_MARGINS)
        audio_control_layout.setSpacing(BOTTOM_PANEL_VERTICAL_SPACING)
        audio_control_layout.setAlignment(Qt.AlignTop)
        self._init_controls_ui(audio_control_layout)
        bottom_splitter.addWidget(audio_control_widget)
        
        bottom_splitter.setSizes([DEFAULT_WINDOW_WIDTH // 2, DEFAULT_WINDOW_WIDTH // 2])
        main_splitter.addWidget(bottom_splitter)
        
        # Top 40%, bottom 60%
        top_default_px = int(DEFAULT_WINDOW_HEIGHT * TOP_DEFAULT_HEIGHT_RATIO)
        main_splitter.setSizes([top_default_px, DEFAULT_WINDOW_HEIGHT - top_default_px])
    
    def _init_play_timeline_ui(self, layout):
        """Initialize the top-right UI: prototype dropdown (left), Play button (right), waveform, and music timeline."""
        button_row = QHBoxLayout()
        # Left: prototype dropdown (Manual = sliders only; Cutoff Only = sensor drives cutoff)
        self.prototype_combo = QComboBox()
        self.prototype_combo.setFont(QFont("Arial", 11))
        self.prototype_combo.addItem("Manual Control")
        self.prototype_combo.addItem("Prototype A - Air DJ")
        self.prototype_combo.addItem("Prototype B - Calm vs Intense")
        self.prototype_combo.addItem("Prototype C - Two Hand Instrument")
        self.prototype_combo.addItem("Cutoff Only")
        self.prototype_combo.setCurrentIndex(PROTOTYPE_INDEX_MANUAL)
        self.prototype_combo.currentIndexChanged.connect(self._on_prototype_changed)
        button_row.addWidget(self.prototype_combo)
        button_row.addStretch()
        # Right: Play button
        self.play_button = QPushButton("Play")
        self.play_button.setFont(QFont("Arial", 14, QFont.Bold))
        self.play_button.setFixedSize(100, 40)
        self.play_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
        """)
        self.play_button.clicked.connect(self._on_play_toggle)
        button_row.addWidget(self.play_button)
        layout.addLayout(button_row)
        
        self.waveform_widget = LiveWaveformWidget()
        layout.addWidget(self.waveform_widget)
        
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(5)
        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("0:00")
        self.current_time_label.setFont(QFont("Arial", 11))
        self.current_time_label.setMinimumWidth(50)
        time_layout.addWidget(self.current_time_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        time_layout.addWidget(self.progress_bar, 1)
        self.total_time_label = QLabel("0:00")
        self.total_time_label.setFont(QFont("Arial", 11))
        self.total_time_label.setMinimumWidth(50)
        self.total_time_label.setAlignment(Qt.AlignRight)
        time_layout.addWidget(self.total_time_label)
        progress_layout.addLayout(time_layout)
        layout.addLayout(progress_layout)
        
        if self.audio_data is not None and self.audio_sample_rate is not None:
            total_duration_seconds = len(self.audio_data) / self.audio_sample_rate
            minutes = int(total_duration_seconds // 60)
            seconds = int(total_duration_seconds % 60)
            self.total_time_label.setText(f"{minutes}:{seconds:02d}")
        else:
            self.total_duration_samples = 1
    
    def _init_controls_ui(self, layout):
        """Initialize the AUDIO_CONTROL UI (bottom-right panel): title, scroll area, sliders and checkboxes."""
        audio_control_title = QLabel("Audio Control")
        audio_control_title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(audio_control_title)
        
        audio_control_scroll = QScrollArea()
        audio_control_scroll.setWidgetResizable(True)
        audio_control_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        audio_control_scroll.setStyleSheet(SCROLL_AREA_STYLESHEET)
        
        audio_control_scroll_widget = QWidget()
        audio_control_scroll_widget.setStyleSheet(SLIDER_STYLESHEET)
        scroll_content_layout = QVBoxLayout(audio_control_scroll_widget)
        scroll_content_layout.setContentsMargins(12, 12, 12, 12)
        scroll_content_layout.setSpacing(AC_VERTICAL_SPACING)
        
        # Cutoff + Resonance header row (checkboxes side by side)
        cutoff_resonance_header = QHBoxLayout()
        cutoff_label = QLabel("Cutoff:")
        cutoff_label.setFont(QFont("Arial", 12, QFont.Bold))
        cutoff_resonance_header.addWidget(cutoff_label)
        self.cutoff_smooth_checkbox = QCheckBox("Smooth")
        self.cutoff_smooth_checkbox.setChecked(True)  # Enabled by default
        self.cutoff_smooth_checkbox.setFont(QFont("Arial", 10))
        self.cutoff_smooth_checkbox.toggled.connect(self._on_cutoff_smooth_toggled)
        cutoff_resonance_header.addWidget(self.cutoff_smooth_checkbox)
        cutoff_resonance_header.addSpacing(20)
        resonance_label = QLabel("Resonance:")
        resonance_label.setFont(QFont("Arial", 12, QFont.Bold))
        cutoff_resonance_header.addWidget(resonance_label)
        self.resonance_smooth_checkbox = QCheckBox("Smooth")
        self.resonance_smooth_checkbox.setChecked(False)  # Disabled by default
        self.resonance_smooth_checkbox.setFont(QFont("Arial", 10))
        self.resonance_smooth_checkbox.toggled.connect(self._on_resonance_smooth_toggled)
        cutoff_resonance_header.addWidget(self.resonance_smooth_checkbox)
        cutoff_resonance_header.addStretch()
        
        # Cutoff dial
        cutoff_layout = QVBoxLayout()
        cutoff_layout.setSpacing(10)
        cutoff_layout.addLayout(cutoff_resonance_header)
        
        slider_layout = QHBoxLayout()
        min_label = QLabel("0.0")
        min_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        slider_layout.addWidget(min_label)
        
        self.cutoff_slider = QSlider(Qt.Horizontal)
        self.cutoff_slider.setMinimum(0)
        self.cutoff_slider.setMaximum(100)
        self.cutoff_slider.setValue(50)
        self.cutoff_slider.setTickPosition(QSlider.NoTicks)
        self.cutoff_slider.setMinimumWidth(SLIDER_WIDTH)
        self.cutoff_slider.setMaximumWidth(SLIDER_WIDTH)
        self.cutoff_slider.valueChanged.connect(self._on_cutoff_changed)
        slider_layout.addWidget(self.cutoff_slider)
        
        max_label = QLabel("1.0")
        max_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        slider_layout.addWidget(max_label)
        
        # Initialize TimbreControls with default values
        self.timbre_controls.V_cutoff = 0.5
        self.timbre_controls.V_volume = 0.5
        self.timbre_controls.V_pan = 0.5  # Center
        self._update_atomic_snapshot()
        f_min = 250.0
        f_max = 12000.0
        initial_cutoff = math.exp(math.log(f_min) + 0.5 * (math.log(f_max) - math.log(f_min)))
        self.cutoff_display = QLabel(f"Cutoff: 0.5  |  Frequency: {initial_cutoff:.1f} Hz")
        self.cutoff_display.setFont(QFont("Arial", SLIDER_VALUE_FONT))
        self.cutoff_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        slider_layout.addWidget(self.cutoff_display, 1)
        
        cutoff_layout.addLayout(slider_layout)
        scroll_content_layout.addLayout(cutoff_layout)
        
        # Resonance dial (header already in cutoff_resonance_header above)
        resonance_layout = QVBoxLayout()
        resonance_layout.setSpacing(10)
        
        resonance_slider_layout = QHBoxLayout()
        res_min_label = QLabel("0.0")
        res_min_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        resonance_slider_layout.addWidget(res_min_label)
        
        self.resonance_slider = QSlider(Qt.Horizontal)
        self.resonance_slider.setMinimum(0)
        self.resonance_slider.setMaximum(100)
        self.resonance_slider.setValue(0)
        self.resonance_slider.setTickPosition(QSlider.NoTicks)
        self.resonance_slider.setMinimumWidth(SLIDER_WIDTH)
        self.resonance_slider.setMaximumWidth(SLIDER_WIDTH)
        self.resonance_slider.valueChanged.connect(self._on_resonance_changed)
        resonance_slider_layout.addWidget(self.resonance_slider)
        
        res_max_label = QLabel("1.0")
        res_max_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        resonance_slider_layout.addWidget(res_max_label)
        
        self.resonance_display = QLabel("Resonance: 0.0  |  Q: 0.70")
        self.resonance_display.setFont(QFont("Arial", SLIDER_VALUE_FONT))
        self.resonance_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        resonance_slider_layout.addWidget(self.resonance_display, 1)
        
        resonance_layout.addLayout(resonance_slider_layout)
        scroll_content_layout.addLayout(resonance_layout)
        
        # Attack dial
        attack_layout = QHBoxLayout()
        attack_min_label = QLabel("0.0")
        attack_min_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        attack_layout.addWidget(attack_min_label)
        
        self.attack_slider = QSlider(Qt.Horizontal)
        self.attack_slider.setMinimum(0)
        self.attack_slider.setMaximum(100)
        self.attack_slider.setValue(0)
        self.attack_slider.setTickPosition(QSlider.NoTicks)
        self.attack_slider.setMinimumWidth(SLIDER_WIDTH)
        self.attack_slider.setMaximumWidth(SLIDER_WIDTH)
        self.attack_slider.valueChanged.connect(self._on_attack_changed)
        attack_layout.addWidget(self.attack_slider)
        
        attack_max_label = QLabel("1.0")
        attack_max_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        attack_layout.addWidget(attack_max_label)
        
        self.attack_display = QLabel("Attack: 0.0")
        self.attack_display.setFont(QFont("Arial", SLIDER_VALUE_FONT))
        self.attack_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        attack_layout.addWidget(self.attack_display, 1)
        
        scroll_content_layout.addLayout(attack_layout)
        
        # Brightness dial
        brightness_layout = QHBoxLayout()
        brightness_min_label = QLabel("0.0")
        brightness_min_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        brightness_layout.addWidget(brightness_min_label)
        
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setMinimum(0)
        self.brightness_slider.setMaximum(100)
        self.brightness_slider.setValue(50)
        self.brightness_slider.setTickPosition(QSlider.NoTicks)
        self.brightness_slider.setMinimumWidth(SLIDER_WIDTH)
        self.brightness_slider.setMaximumWidth(SLIDER_WIDTH)
        self.brightness_slider.valueChanged.connect(self._on_brightness_changed)
        brightness_layout.addWidget(self.brightness_slider)
        
        brightness_max_label = QLabel("1.0")
        brightness_max_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        brightness_layout.addWidget(brightness_max_label)
        
        self.brightness_display = QLabel("Brightness: 0.50")
        self.brightness_display.setFont(QFont("Arial", SLIDER_VALUE_FONT))
        self.brightness_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        brightness_layout.addWidget(self.brightness_display, 1)
        
        scroll_content_layout.addLayout(brightness_layout)
        
        # Tremolo dial
        tremolo_layout = QHBoxLayout()
        tremolo_min_label = QLabel("0.0")
        tremolo_min_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        tremolo_layout.addWidget(tremolo_min_label)
        
        self.tremolo_slider = QSlider(Qt.Horizontal)
        self.tremolo_slider.setMinimum(0)
        self.tremolo_slider.setMaximum(100)
        self.tremolo_slider.setValue(0)
        self.tremolo_slider.setTickPosition(QSlider.NoTicks)
        self.tremolo_slider.setMinimumWidth(SLIDER_WIDTH)
        self.tremolo_slider.setMaximumWidth(SLIDER_WIDTH)
        self.tremolo_slider.valueChanged.connect(self._on_tremolo_changed)
        tremolo_layout.addWidget(self.tremolo_slider)
        
        tremolo_max_label = QLabel("1.0")
        tremolo_max_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        tremolo_layout.addWidget(tremolo_max_label)
        
        self.tremolo_display = QLabel("Tremolo: 0.00")
        self.tremolo_display.setFont(QFont("Arial", SLIDER_VALUE_FONT))
        self.tremolo_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        tremolo_layout.addWidget(self.tremolo_display, 1)
        
        scroll_content_layout.addLayout(tremolo_layout)
        
        # Mode dial
        mode_layout = QHBoxLayout()
        mode_min_label = QLabel("0.0 (Calm)")
        mode_min_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        mode_layout.addWidget(mode_min_label)
        
        self.mode_slider = QSlider(Qt.Horizontal)
        self.mode_slider.setMinimum(0)
        self.mode_slider.setMaximum(100)
        self.mode_slider.setValue(0)
        self.mode_slider.setTickPosition(QSlider.NoTicks)
        self.mode_slider.setMinimumWidth(SLIDER_WIDTH)
        self.mode_slider.setMaximumWidth(SLIDER_WIDTH)
        self.mode_slider.valueChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_slider)
        
        mode_max_label = QLabel("1.0 (Intense)")
        mode_max_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        mode_layout.addWidget(mode_max_label)
        
        self.mode_display = QLabel("Mode: 0.00 (Calm)")
        self.mode_display.setFont(QFont("Arial", SLIDER_VALUE_FONT))
        self.mode_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        mode_layout.addWidget(self.mode_display, 1)
        
        scroll_content_layout.addLayout(mode_layout)
        
        # Volume dial
        volume_layout = QHBoxLayout()
        volume_min_label = QLabel("0.0")
        volume_min_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        volume_layout.addWidget(volume_min_label)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(50)
        self.volume_slider.setTickPosition(QSlider.NoTicks)
        self.volume_slider.setMinimumWidth(SLIDER_WIDTH)
        self.volume_slider.setMaximumWidth(SLIDER_WIDTH)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_layout.addWidget(self.volume_slider)
        
        volume_max_label = QLabel("1.0")
        volume_max_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        volume_layout.addWidget(volume_max_label)
        
        self.volume_display = QLabel("Volume: 0.50")
        self.volume_display.setFont(QFont("Arial", SLIDER_VALUE_FONT))
        self.volume_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        volume_layout.addWidget(self.volume_display, 1)
        
        scroll_content_layout.addLayout(volume_layout)
        
        # Pan (stereo balance): 0 = full left, 50 = center, 100 = full right (same as IMU C/D equal-power)
        pan_layout = QHBoxLayout()
        pan_min_label = QLabel("L")
        pan_min_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        pan_layout.addWidget(pan_min_label)
        self.pan_slider = QSlider(Qt.Horizontal)
        self.pan_slider.setMinimum(0)
        self.pan_slider.setMaximum(100)
        self.pan_slider.setValue(50)
        self.pan_slider.setTickPosition(QSlider.NoTicks)
        self.pan_slider.setMinimumWidth(SLIDER_WIDTH)
        self.pan_slider.setMaximumWidth(SLIDER_WIDTH)
        self.pan_slider.valueChanged.connect(self._on_pan_changed)
        pan_layout.addWidget(self.pan_slider)
        pan_max_label = QLabel("R")
        pan_max_label.setFont(QFont("Arial", SLIDER_LABEL_FONT))
        pan_layout.addWidget(pan_max_label)
        self.pan_display = QLabel("Pan: 0.00 (Center)")
        self.pan_display.setFont(QFont("Arial", SLIDER_VALUE_FONT))
        self.pan_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        pan_layout.addWidget(self.pan_display, 1)
        scroll_content_layout.addLayout(pan_layout)
        
        scroll_content_layout.addStretch()
        
        audio_control_scroll.setWidget(audio_control_scroll_widget)
        layout.addWidget(audio_control_scroll, 1)
        
        # Initialize displays
        self._update_cutoff_display()
        self._update_resonance_display()
        self._update_attack_display()
        self._update_brightness_display()
        self._update_tremolo_display()
        self._update_mode_display()
        self._update_volume_display()
        self._update_pan_display()
    
    def _init_video_ui(self, layout):
        """Initialize the video UI (top-left panel)."""
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(320, 240)  # Smaller minimum, will expand to fit
        self.video_label.setScaledContents(False)  # We'll handle scaling manually
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a;
                border: 2px solid #34495e;
                border-radius: 8px;
            }
        """)
        self.video_label.setText("Camera initializing...")
        layout.addWidget(self.video_label, 1)  # Give it stretch factor to fill available space
    
    def _init_stats_ui(self, layout):
        """Initialize the MOTION_SENSOR stats UI (bottom-left panel)."""
        motion_sensor_title = QLabel("Sensor Readings")
        motion_sensor_title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(motion_sensor_title)
        
        motion_sensor_scroll = QScrollArea()
        motion_sensor_scroll.setWidgetResizable(True)
        motion_sensor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        motion_sensor_scroll.setStyleSheet(SCROLL_AREA_STYLESHEET)
        
        motion_sensor_scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        motion_sensor_scroll_widget.setLayout(scroll_layout)
        
        # Helper function to create stat row
        def create_stat_row(label_text, value_attr_name):
            row_layout = QHBoxLayout()
            label = QLabel(f"{label_text}:")
            label.setFont(QFont("Arial", 10))
            row_layout.addWidget(label)
            value_label = QLabel("0.00")
            value_label.setFont(QFont("Arial", 18, QFont.Bold))
            value_label.setStyleSheet("color: #2c3e50;")
            row_layout.addWidget(value_label, 1)
            row_layout.addStretch()
            return value_label, row_layout
        
        # LCD readouts: 3 columns (left 5, right 4, third = activity L/R)
        lcd_three_column = QHBoxLayout()
        lcd_left_column = QVBoxLayout()
        lcd_right_column = QVBoxLayout()
        lcd_third_column = QVBoxLayout()
        lcd_three_column.addLayout(lcd_left_column)
        lcd_three_column.addLayout(lcd_right_column)
        lcd_three_column.addLayout(lcd_third_column)
        
        def _reading_label_display(text):
            """Remove '_', init cap, and turn trailing L/R into (L)/(R)."""
            s = text.replace("_", " ").title()
            s = s.replace(" L", " (L)").replace(" R", " (R)")
            return s
        
        def add_lcd_row(column_layout, lcd_attr, label_text, initial="0.500"):
            lcd = QLCDNumber()
            lcd.setDigitCount(5)
            lcd.setSegmentStyle(QLCDNumber.Flat)
            lcd.setFixedSize(75, 30)
            palette = lcd.palette()
            palette.setColor(palette.WindowText, QColor(0x00, 0x64, 0x00))
            lcd.setPalette(palette)
            lcd.display(initial)
            setattr(self, lcd_attr, lcd)
            row = QHBoxLayout()
            row.addWidget(lcd)
            lbl = QLabel(_reading_label_display(label_text))
            lbl.setFont(QFont("Arial", READING_LABEL_FONT))
            row.addWidget(lbl)
            column_layout.addLayout(row)
        
        add_lcd_row(lcd_left_column, "hand_height_L_lcd", "hand_height_L")
        add_lcd_row(lcd_left_column, "arm_extension_L_lcd", "arm_extension_L")
        add_lcd_row(lcd_left_column, "elbow_bend_L_lcd", "elbow_bend_L")
        add_lcd_row(lcd_left_column, "lateral_offset_L_lcd", "lateral_offset_L")
        add_lcd_row(lcd_left_column, "activity_L_lcd", "activity_L", "0.000")
        add_lcd_row(lcd_left_column, "jerk_L_lcd", "jerk_L", "0.000")
        add_lcd_row(lcd_left_column, "shake_energy_L_lcd", "shake_energy_L", "0.000")
        add_lcd_row(lcd_right_column, "hand_height_R_lcd", "hand_height_R")
        add_lcd_row(lcd_right_column, "arm_extension_R_lcd", "arm_extension_R")
        add_lcd_row(lcd_right_column, "elbow_bend_R_lcd", "elbow_bend_R")
        add_lcd_row(lcd_right_column, "lateral_offset_R_lcd", "lateral_offset_R")
        add_lcd_row(lcd_right_column, "activity_R_lcd", "activity_R", "0.000")
        add_lcd_row(lcd_right_column, "jerk_R_lcd", "jerk_R", "0.000")
        add_lcd_row(lcd_right_column, "shake_energy_R_lcd", "shake_energy_R", "0.000")
        add_lcd_row(lcd_third_column, "hands_spread_lcd", "hand_spread")
        add_lcd_row(lcd_third_column, "mediapipe_confidence_lcd", "mediapipe_confidence", "0.000")
        add_lcd_row(lcd_third_column, "imu_confidence_L_lcd", "imu_confidence_L", "0.000")
        add_lcd_row(lcd_third_column, "imu_confidence_R_lcd", "imu_confidence_R", "0.000")
        add_lcd_row(lcd_third_column, "activity_global_lcd", "activity_global", "0.000")
        
        # Align LCDs to top of each column; stretch below so shorter columns leave blank space
        lcd_left_column.setAlignment(Qt.AlignTop)
        lcd_right_column.setAlignment(Qt.AlignTop)
        lcd_third_column.setAlignment(Qt.AlignTop)
        lcd_left_column.addStretch()
        lcd_right_column.addStretch()
        lcd_third_column.addStretch()
        
        scroll_layout.addLayout(lcd_three_column)
        
        scroll_layout.addStretch()
        
        motion_sensor_scroll.setWidget(motion_sensor_scroll_widget)
        layout.addWidget(motion_sensor_scroll)
    
    def _update_video_frame(self):
        """Update video frame with MediaPipe pose detection (body only, no face)."""
        if not self.cap or not self.cap.isOpened():
            return
        
        ret, frame = self.cap.read()
        if not ret:
            return
        
        # Convert BGR to RGB for MediaPipe processing
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Update motion state using MotionFeatureExtractor
        current_time = time.time()
        self.current_motion_state = self.motion_extractor.update(frame_rgb, current_time)
        
        # Legacy: Update old sensor readings for backward compatibility with existing UI
        # (These are now derived from motion_state, but kept for display compatibility)
        if self.current_motion_state:
            self.hand_height_L = self.current_motion_state.hand_height_L
            self.hand_height_R = self.current_motion_state.hand_height_R
            self.hands_spread = self.current_motion_state.hand_spread
        
        # Process frame with MediaPipe pose detector (for drawing)
        if self.pose:
            results = self.pose.process(frame_rgb)
            
            # Legacy: Calculate sensor readings from pose landmarks (for backward compatibility)
            if results.pose_landmarks:
                self._calculate_sensor_readings(results.pose_landmarks.landmark)
            
            # Draw pose skeleton on frame (excluding face landmarks)
            if results.pose_landmarks:
                # Filter out face landmarks (nose, eyes, ears, mouth)
                # Face landmarks are PoseLandmark enums, not integers
                face_landmarks = {
                    self.mp_pose.PoseLandmark.NOSE,
                    self.mp_pose.PoseLandmark.LEFT_EYE_INNER,
                    self.mp_pose.PoseLandmark.LEFT_EYE,
                    self.mp_pose.PoseLandmark.LEFT_EYE_OUTER,
                    self.mp_pose.PoseLandmark.RIGHT_EYE_INNER,
                    self.mp_pose.PoseLandmark.RIGHT_EYE,
                    self.mp_pose.PoseLandmark.RIGHT_EYE_OUTER,
                    self.mp_pose.PoseLandmark.LEFT_EAR,
                    self.mp_pose.PoseLandmark.RIGHT_EAR,
                    self.mp_pose.PoseLandmark.MOUTH_LEFT,
                    self.mp_pose.PoseLandmark.MOUTH_RIGHT,
                }
                
                # Filter connections to exclude any connections involving face landmarks
                # POSE_CONNECTIONS contains tuples of PoseLandmark enums
                body_only_connections = [
                    conn for conn in self.mp_pose.POSE_CONNECTIONS
                    if conn[0] not in face_landmarks
                    and conn[1] not in face_landmarks
                ]
                
                # Create custom drawing spec that hides face landmarks
                # We'll draw body landmarks normally, but skip face landmarks
                body_landmark_spec = self.mp_drawing.DrawingSpec(
                    color=(0, 255, 0),  # Green for body landmarks
                    thickness=2,
                    circle_radius=2
                )
                
                # Draw pose skeleton with filtered connections (body only)
                # Note: draw_landmarks will still draw all landmarks, but we filter connections
                # To fully hide face landmarks, we'd need to manually draw, but this approach
                # at least removes face connections and keeps the visualization body-focused
                self.mp_drawing.draw_landmarks(
                    frame_rgb,
                    results.pose_landmarks,
                    body_only_connections,
                    landmark_drawing_spec=body_landmark_spec,
                    connection_drawing_spec=self.mp_drawing.DrawingSpec(
                        color=(0, 255, 0),  # Green for connections
                        thickness=2
                    )
                )
        
        # Convert back to BGR for display; mirror horizontally so user sees natural mirror (pose interpretation is swapped separately)
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        frame_bgr = cv2.flip(frame_bgr, 1)  # 1 = horizontal flip (mirror)
        h, w, ch = frame_bgr.shape
        bytes_per_line = ch * w
        q_img = QImage(frame_bgr.data, w, h, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
        
        # Scale to fill label width while maintaining aspect ratio (reduces vertical letterboxing)
        label_width = self.video_label.width()
        label_height = self.video_label.height()
        
        # Calculate scaled size to fill width, maintaining aspect ratio
        aspect_ratio = w / h
        max_height = min(400, label_height)  # Cap at 400px or label height, whichever is smaller
        scaled_width = label_width
        scaled_height = int(label_width / aspect_ratio)
        
        # If scaled height exceeds max height, scale to fit max height instead
        if scaled_height > max_height:
            scaled_height = max_height
            scaled_width = int(max_height * aspect_ratio)
        
        scaled = q_img.scaled(
            scaled_width,
            scaled_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        self.video_label.setPixmap(QPixmap.fromImage(scaled))
        
        # Apply two-stage sensor smoothing and update atomic snapshot
        self._update_sensor_smoothing()
        if self._is_prototype_a():
            self._update_prototype_a_smoothing()
        if self._is_prototype_b():
            self._update_prototype_b_smoothing()
        if self._is_prototype_c():
            self._update_prototype_c_smoothing()
        self._update_atomic_snapshot()
        if self._is_prototype_a():
            self._push_prototype_a_values_to_ui()
        if self._is_prototype_b():
            self._push_prototype_b_values_to_ui()
        if self._is_prototype_c():
            self._push_prototype_c_values_to_ui()
        
        # Update stats display
        self._update_stats_display()
    
    def _calculate_sensor_readings(self, landmarks):
        """Calculate sensor readings from MediaPipe pose landmarks."""
        try:
            # Get key landmarks
            left_wrist = landmarks[self.mp_pose.PoseLandmark.LEFT_WRIST.value]
            right_wrist = landmarks[self.mp_pose.PoseLandmark.RIGHT_WRIST.value]
            left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
            right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
            left_hip = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value]
            right_hip = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value]
            
            # Check visibility of key landmarks (MediaPipe provides visibility scores)
            # Visibility threshold: if below this, consider landmark not visible
            visibility_threshold = 0.5
            
            # Use midpoint of shoulders as head reference
            head_y = (left_shoulder.y + right_shoulder.y) / 2.0
            
            # Average hip position
            hip_y = (left_hip.y + right_hip.y) / 2.0
            
            # Calculate hand heights (normalized 0-1 relative to hips→head)
            # REVERSED: 0 = hand at hip, 1 = hand at head
            # In MediaPipe: y=0 is top, y=1 is bottom
            if abs(hip_y - head_y) > 1e-6:  # Avoid division by zero
                # Check left wrist visibility
                if hasattr(left_wrist, 'visibility') and left_wrist.visibility >= visibility_threshold:
                    # Reversed: (hip_y - wrist_y) / (hip_y - head_y)
                    # When wrist_y = hip_y: (hip_y - hip_y) / (hip_y - head_y) = 0 (at hip)
                    # When wrist_y = head_y: (hip_y - head_y) / (hip_y - head_y) = 1 (at head)
                    self.hand_height_L = max(0.0, min(1.0, (hip_y - left_wrist.y) / (hip_y - head_y)))
                else:
                    # Hand not visible - set to None or keep previous value
                    # We'll display as "--" or keep last known value
                    if not hasattr(self, '_last_hand_height_L'):
                        self.hand_height_L = 0.5  # Default if never seen
                    else:
                        self.hand_height_L = self._last_hand_height_L  # Keep last known value
                self._last_hand_height_L = self.hand_height_L
                
                # Check right wrist visibility
                current_time = time.time()
                if hasattr(right_wrist, 'visibility') and right_wrist.visibility >= visibility_threshold:
                    # Good detection - update value and reset timer
                    raw_hand_height_R = max(0.0, min(1.0, (hip_y - right_wrist.y) / (hip_y - head_y)))
                    self.hand_height_R = raw_hand_height_R
                    self._last_good_hand_height_R = raw_hand_height_R
                    self._last_good_detection_time = current_time
                else:
                    # No detection or low confidence - confidence-weighted return-to-neutral
                    time_since_good = current_time - self._last_good_detection_time
                    
                    if time_since_good < self._grace_period_seconds:
                        # Grace period - use last good value
                        self.hand_height_R = self._last_good_hand_height_R
                    else:
                        # Decay to neutral
                        decay_progress = min(1.0, (time_since_good - self._grace_period_seconds) / self._decay_time_seconds)
                        # Blend: last_good → 0.5 (neutral)
                        self.hand_height_R = self._last_good_hand_height_R + (0.5 - self._last_good_hand_height_R) * decay_progress
            else:
                # Can't calculate if head and hip are at same height
                if not hasattr(self, '_last_hand_height_L'):
                    self.hand_height_L = 0.5
                else:
                    self.hand_height_L = self._last_hand_height_L
                if not hasattr(self, '_last_hand_height_R'):
                    self.hand_height_R = 0.5
                else:
                    self.hand_height_R = self._last_hand_height_R
            
            # Calculate hands_spread (distance between hands / shoulder width)
            # Only calculate if both hands are visible
            left_visible = hasattr(left_wrist, 'visibility') and left_wrist.visibility >= visibility_threshold
            right_visible = hasattr(right_wrist, 'visibility') and right_wrist.visibility >= visibility_threshold
            
            if left_visible and right_visible:
                # Euclidean distance in 2D (x, y)
                hand_distance = math.sqrt(
                    (left_wrist.x - right_wrist.x) ** 2 + 
                    (left_wrist.y - right_wrist.y) ** 2
                )
                shoulder_width = math.sqrt(
                    (left_shoulder.x - right_shoulder.x) ** 2 + 
                    (left_shoulder.y - right_shoulder.y) ** 2
                )
                
                if shoulder_width > 1e-6:  # Avoid division by zero
                    self.hands_spread = hand_distance / shoulder_width
                else:
                    self.hands_spread = 0.0
            else:
                # One or both hands not visible - keep last known value
                if not hasattr(self, '_last_hands_spread'):
                    self.hands_spread = 0.0
                else:
                    self.hands_spread = self._last_hands_spread
            self._last_hands_spread = self.hands_spread
                
        except (IndexError, AttributeError, KeyError) as e:
            # If any landmark is missing, keep previous values
            if not hasattr(self, '_last_hand_height_L'):
                self.hand_height_L = 0.5
            else:
                self.hand_height_L = self._last_hand_height_L
            if not hasattr(self, '_last_hand_height_R'):
                self.hand_height_R = 0.5
            else:
                self.hand_height_R = self._last_hand_height_R
            if not hasattr(self, '_last_hands_spread'):
                self.hands_spread = 0.0
            else:
                self.hands_spread = self._last_hands_spread
    
    def _update_sensor_smoothing(self):
        """Apply two-stage sensor smoothing: median-of-3 + two-speed one-pole."""
        # Stage 1: Median-of-3 to remove single-frame MediaPipe spikes
        self._hand_height_R_history.append(self.hand_height_R)
        self._hand_height_R_history.pop(0)  # Keep only last 3
        median_hand_height_R = sorted(self._hand_height_R_history)[1]  # Middle value
        
        # Stage 2: Two-speed one-pole smoothing
        dt = 0.033  # 33ms per video frame at 30 FPS
        tau_up_ms = 50   # Fast when moving up (50ms)
        tau_down_ms = 200  # Slow when drifting down (200ms)
        
        if median_hand_height_R > self._smoothed_hand_height_R:
            tau = tau_up_ms / 1000.0  # Moving up - fast
        else:
            tau = tau_down_ms / 1000.0  # Moving down - slow
        
        alpha = 1.0 - math.exp(-dt / max(tau, 1e-6))
        self._smoothed_hand_height_R = self._smoothed_hand_height_R + alpha * (median_hand_height_R - self._smoothed_hand_height_R)
    
    def _is_cutoff_sensor_controlled(self):
        """True when prototype is 'Cutoff Only' (sensor drives cutoff)."""
        return self.prototype_combo.currentIndex() == PROTOTYPE_INDEX_CUTOFF_ONLY

    def _is_prototype_a(self):
        """True when prototype dropdown is 'Prototype A' (Air DJ mappings)."""
        return self.prototype_combo.currentIndex() == PROTOTYPE_INDEX_PROTOTYPE_A

    def _is_prototype_b(self):
        """True when prototype dropdown is 'Prototype B' (Calm vs Intense)."""
        return self.prototype_combo.currentIndex() == PROTOTYPE_INDEX_PROTOTYPE_B

    def _is_prototype_c(self):
        """True when prototype dropdown is 'Prototype C' (Two-Hand Instrument)."""
        return self.prototype_combo.currentIndex() == PROTOTYPE_INDEX_PROTOTYPE_C

    def _one_pole_smooth(self, target, prev, dt, tau_sec):
        """One-pole smoother: alpha = 1 - exp(-dt/tau), out = prev + alpha * (target - prev)."""
        alpha = 1.0 - math.exp(-dt / max(tau_sec, 1e-6))
        return prev + alpha * (target - prev)

    def _two_speed_smooth(self, target, prev, dt, tau_up_sec, tau_down_sec):
        """Two-speed one-pole: fast when target > prev, slow when target < prev."""
        tau = tau_up_sec if target > prev else tau_down_sec
        return self._one_pole_smooth(target, prev, dt, tau)

    def _update_prototype_a_smoothing(self):
        """Update all Prototype A smoothed state from current_motion_state. Call when _is_prototype_a()."""
        if not self.current_motion_state:
            return
        dt = 0.033  # ~30 FPS
        s = self.current_motion_state
        # Left hand height: same two-stage as right (median-of-3 + two-speed)
        self._hand_height_L_history.append(s.hand_height_L)
        self._hand_height_L_history.pop(0)
        median_L = sorted(self._hand_height_L_history)[1]
        self._smoothed_hand_height_L = self._two_speed_smooth(
            median_L, self._smoothed_hand_height_L, dt, 0.05, 0.2
        )
        
        # Lateral offsets: one-pole ~80 ms
        tau_lat = 0.08
        self._smoothed_lateral_offset_L = self._one_pole_smooth(
            s.lateral_offset_L, self._smoothed_lateral_offset_L, dt, tau_lat
        )
        self._smoothed_lateral_offset_R = self._one_pole_smooth(
            s.lateral_offset_R, self._smoothed_lateral_offset_R, dt, tau_lat
        )
        
        # Hand spread: one-pole ~80 ms
        self._smoothed_hand_spread = self._one_pole_smooth(
            s.hand_spread, self._smoothed_hand_spread, dt, tau_lat
        )
        
        # Activity global: two-speed 60 ms up / 200 ms down
        self._smoothed_activity_global = self._two_speed_smooth(
            s.activity_global, self._smoothed_activity_global, dt, 0.06, 0.2
        )
        
        # Shake energy R: two-speed 30 ms up / 150 ms down
        self._smoothed_shake_energy_R = self._two_speed_smooth(
            s.shake_energy_R, self._smoothed_shake_energy_R, dt, 0.03, 0.15
        )

    def _update_prototype_b_smoothing(self):
        """Update Prototype B smoothed state and mode/resonance-burst. Call when _is_prototype_b()."""
        if not self.current_motion_state:
            return
        dt = 0.033
        s = self.current_motion_state
        current_time = time.time()
        # Hand spread: one-pole ~80 ms (for mode hysteresis)
        self._smoothed_hand_spread = self._one_pole_smooth(
            s.hand_spread, self._smoothed_hand_spread, dt, 0.08
        )
        # Arm extension L: one-pole ~70 ms
        self._smoothed_arm_extension_L = self._one_pole_smooth(
            s.arm_extension_L, self._smoothed_arm_extension_L, dt, 0.07
        )
        # Activity global: two-speed 60 ms up / 200 ms down
        self._smoothed_activity_global = self._two_speed_smooth(
            s.activity_global, self._smoothed_activity_global, dt, 0.06, 0.2
        )
        # Mode hysteresis
        mode_raw = max(0.0, min(1.0, self._smoothed_hand_spread))
        if self._mode_state == 'calm' and mode_raw > MODE_HYSTERESIS_HIGH:
            self._mode_state = 'intense'
        elif self._mode_state == 'intense' and mode_raw < MODE_HYSTERESIS_LOW:
            self._mode_state = 'calm'
        # Resonance burst: time-based decay then add from jerk
        elapsed = current_time - self._last_burst_time
        self._last_burst_time = current_time
        self._resonance_burst *= math.exp(-elapsed / TAU_RESONANCE_BURST_DECAY)
        jerk_max = max(getattr(s, 'jerk_L', 0.0), getattr(s, 'jerk_R', 0.0))
        if jerk_max > JERK_BURST_THRESHOLD:
            burst_add = JERK_BURST_GAIN * min(1.0, jerk_max - JERK_BURST_THRESHOLD)
            self._resonance_burst = min(1.0, self._resonance_burst + burst_add)

    def _update_prototype_c_smoothing(self):
        """Update Prototype C smoothed state and attack-burst. Call when _is_prototype_c()."""
        if not self.current_motion_state:
            return
        dt = 0.033
        s = self.current_motion_state
        current_time = time.time()
        # Left hand height: two-stage (median-of-3 + two-speed) same as A
        self._hand_height_L_history.append(s.hand_height_L)
        self._hand_height_L_history.pop(0)
        median_L = sorted(self._hand_height_L_history)[1]
        self._smoothed_hand_height_L = self._two_speed_smooth(
            median_L, self._smoothed_hand_height_L, dt, 0.05, 0.2
        )
        # Elbow bend L: one-pole ~70 ms
        self._smoothed_elbow_bend_L = self._one_pole_smooth(
            s.elbow_bend_L, self._smoothed_elbow_bend_L, dt, 0.07
        )
        # Lateral offset L: one-pole ~80 ms
        tau_lat = 0.08
        self._smoothed_lateral_offset_L = self._one_pole_smooth(
            s.lateral_offset_L, self._smoothed_lateral_offset_L, dt, tau_lat
        )
        # Shake energy R: two-speed 30 ms up / 150 ms down
        self._smoothed_shake_energy_R = self._two_speed_smooth(
            s.shake_energy_R, self._smoothed_shake_energy_R, dt, 0.03, 0.15
        )
        # Attack burst: time-based decay then add from jerk_R
        elapsed = current_time - self._last_attack_burst_time
        self._last_attack_burst_time = current_time
        self._attack_burst *= math.exp(-elapsed / TAU_ATTACK_BURST_DECAY)
        jerk_R = getattr(s, 'jerk_R', 0.0)
        if jerk_R > ATTACK_BURST_THRESHOLD:
            burst_add = ATTACK_BURST_GAIN * min(1.0, jerk_R - ATTACK_BURST_THRESHOLD)
            self._attack_burst = min(1.0, self._attack_burst + burst_add)
        # Activity R: two-speed 60 ms up / 200 ms down
        self._smoothed_activity_R = self._two_speed_smooth(
            s.activity_R, self._smoothed_activity_R, dt, 0.06, 0.2
        )

    def _update_atomic_snapshot(self):
        """Create and assign atomic snapshot with all control values."""
        if self._is_prototype_a():
            # Prototype A (Air DJ): six controls from smoothed motion state
            cutoff_value = self._smoothed_hand_height_R
            resonance_value = self._smoothed_hand_height_L
            pan_value = max(0.0, min(1.0, 0.5 + PAN_LATERAL_K * (
                self._smoothed_lateral_offset_R - self._smoothed_lateral_offset_L
            )))
            curved = self._smoothed_activity_global ** 1.0  # linear for higher sensitivity (less movement → louder)
            volume_value = max(0.0, min(1.0, 0.15 + 0.85 * curved))
            # Tremolo: optional spread contribution; then on/off threshold
            raw_tremolo = min(1.0, self._smoothed_shake_energy_R + 0.3 * self._smoothed_hand_spread)
            if raw_tremolo <= TREMOLO_ACTIVATION_THRESHOLD:
                tremolo_value = 0.0
            else:
                tremolo_value = min(1.0, (raw_tremolo - TREMOLO_ACTIVATION_THRESHOLD) / (1.0 - TREMOLO_ACTIVATION_THRESHOLD))
            brightness_value = max(0.0, min(1.0, self._smoothed_hand_spread))
            new_ctrl = TimbreControls(
                V_cutoff=cutoff_value,
                V_resonance=resonance_value,
                V_attack=self.timbre_controls.V_attack,
                V_brightness=brightness_value,
                V_tremolo=tremolo_value,
                V_mode=self.timbre_controls.V_mode,
                V_volume=volume_value,
                V_pan=pan_value,
            )
        elif self._is_prototype_b():
            # Prototype B (Calm vs Intense): mode from hysteresis, cutoff/brightness from R height, attack from L arm, resonance from burst, volume from activity
            mode_value = 1.0 if self._mode_state == 'intense' else 0.0
            height = max(0.0, min(1.0, self._smoothed_hand_height_R))
            cutoff_value = height
            brightness_value = max(0.0, min(1.0, math.pow(height, BRIGHTNESS_HEIGHT_EXPONENT)))
            attack_value = max(0.0, min(1.0, self._smoothed_arm_extension_L))
            base_resonance = 0.0
            resonance_cap = RESONANCE_CAP_INTENSE if self._mode_state == 'intense' else 1.0
            resonance_value = min(resonance_cap, base_resonance + self._resonance_burst)
            curved = self._smoothed_activity_global ** 2.0
            volume_value = max(0.0, min(1.0, 0.25 + 0.55 * curved))
            new_ctrl = TimbreControls(
                V_cutoff=cutoff_value,
                V_resonance=resonance_value,
                V_attack=attack_value,
                V_brightness=brightness_value,
                V_tremolo=self.timbre_controls.V_tremolo,
                V_mode=mode_value,
                V_volume=volume_value,
                V_pan=self.timbre_controls.V_pan,
            )
        elif self._is_prototype_c():
            # Prototype C (Two-Hand Instrument): L = tone (cutoff, resonance, pan), R = rhythm (tremolo, attack, volume); mode fixed, brightness from cutoff
            cutoff_value = max(0.0, min(1.0, self._smoothed_hand_height_L))
            resonance_value = max(0.0, min(1.0, 1.0 - self._smoothed_elbow_bend_L))
            pan_value = max(0.0, min(1.0, self._smoothed_lateral_offset_L))
            raw_tremolo = self._smoothed_shake_energy_R
            if raw_tremolo <= TREMOLO_ACTIVATION_THRESHOLD:
                tremolo_value = 0.0
            else:
                tremolo_value = max(0.0, min(1.0, (raw_tremolo - TREMOLO_ACTIVATION_THRESHOLD) / (1.0 - TREMOLO_ACTIVATION_THRESHOLD)))
            attack_value = max(0.0, min(1.0, ATTACK_BASE_C + self._attack_burst))
            volume_value = max(0.0, min(1.0, 0.35 + 0.55 * self._smoothed_activity_R))
            mode_value = MODE_FIXED_C
            brightness_value = max(0.0, min(1.0, BRIGHTNESS_C_OFFSET + BRIGHTNESS_C_SCALE * cutoff_value))
            new_ctrl = TimbreControls(
                V_cutoff=cutoff_value,
                V_resonance=resonance_value,
                V_attack=attack_value,
                V_brightness=brightness_value,
                V_tremolo=tremolo_value,
                V_mode=mode_value,
                V_volume=volume_value,
                V_pan=pan_value,
            )
        else:
            # Manual or Cutoff Only: cutoff from sensor only when Cutoff Only
            cutoff_value = self._smoothed_hand_height_R if self._is_cutoff_sensor_controlled() else self.timbre_controls.V_cutoff
            new_ctrl = TimbreControls(
                V_cutoff=cutoff_value,
                V_resonance=self.timbre_controls.V_resonance,
                V_attack=self.timbre_controls.V_attack,
                V_brightness=self.timbre_controls.V_brightness,
                V_tremolo=self.timbre_controls.V_tremolo,
                V_mode=self.timbre_controls.V_mode,
                V_volume=self.timbre_controls.V_volume,
                V_pan=self.timbre_controls.V_pan,
            )
        
        # Atomic assignment (lock-free, coherent)
        self.ctrl_snapshot = new_ctrl
    
    def _push_prototype_a_values_to_ui(self):
        """Push the six Prototype A control values to timbre_controls and sliders (with blockSignals)."""
        ctrl = self.ctrl_snapshot
        self.timbre_controls.V_cutoff = ctrl.V_cutoff
        self.timbre_controls.V_resonance = ctrl.V_resonance
        self.timbre_controls.V_pan = ctrl.V_pan
        self.timbre_controls.V_volume = ctrl.V_volume
        self.timbre_controls.V_tremolo = ctrl.V_tremolo
        self.timbre_controls.V_brightness = ctrl.V_brightness
        
        self.cutoff_slider.blockSignals(True)
        self.cutoff_slider.setValue(round(ctrl.V_cutoff * 100))
        self.cutoff_slider.blockSignals(False)
        self.resonance_slider.blockSignals(True)
        self.resonance_slider.setValue(round(ctrl.V_resonance * 100))
        self.resonance_slider.blockSignals(False)
        self.pan_slider.blockSignals(True)
        self.pan_slider.setValue(round(ctrl.V_pan * 100))
        self.pan_slider.blockSignals(False)
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(round(ctrl.V_volume * 100))
        self.volume_slider.blockSignals(False)
        self.tremolo_slider.blockSignals(True)
        self.tremolo_slider.setValue(round(ctrl.V_tremolo * 100))
        self.tremolo_slider.blockSignals(False)
        self.brightness_slider.blockSignals(True)
        self.brightness_slider.setValue(round(ctrl.V_brightness * 100))
        self.brightness_slider.blockSignals(False)
        
        self._update_cutoff_display()
        self._update_resonance_display()
        self._update_pan_display()
        self._update_volume_display()
        self._update_tremolo_display()
        self._update_brightness_display()
    
    def _push_prototype_b_values_to_ui(self):
        """Push the six Prototype B control values to timbre_controls and sliders (with blockSignals)."""
        ctrl = self.ctrl_snapshot
        self.timbre_controls.V_mode = ctrl.V_mode
        self.timbre_controls.V_cutoff = ctrl.V_cutoff
        self.timbre_controls.V_brightness = ctrl.V_brightness
        self.timbre_controls.V_attack = ctrl.V_attack
        self.timbre_controls.V_resonance = ctrl.V_resonance
        self.timbre_controls.V_volume = ctrl.V_volume
        self.mode_slider.blockSignals(True)
        self.mode_slider.setValue(round(ctrl.V_mode * 100))
        self.mode_slider.blockSignals(False)
        self.cutoff_slider.blockSignals(True)
        self.cutoff_slider.setValue(round(ctrl.V_cutoff * 100))
        self.cutoff_slider.blockSignals(False)
        self.brightness_slider.blockSignals(True)
        self.brightness_slider.setValue(round(ctrl.V_brightness * 100))
        self.brightness_slider.blockSignals(False)
        self.attack_slider.blockSignals(True)
        self.attack_slider.setValue(round(ctrl.V_attack * 100))
        self.attack_slider.blockSignals(False)
        self.resonance_slider.blockSignals(True)
        self.resonance_slider.setValue(round(ctrl.V_resonance * 100))
        self.resonance_slider.blockSignals(False)
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(round(ctrl.V_volume * 100))
        self.volume_slider.blockSignals(False)
        self._update_mode_display()
        self._update_cutoff_display()
        self._update_brightness_display()
        self._update_attack_display()
        self._update_resonance_display()
        self._update_volume_display()
    
    def _push_prototype_c_values_to_ui(self):
        """Push the eight Prototype C control values to timbre_controls and sliders (with blockSignals)."""
        ctrl = self.ctrl_snapshot
        self.timbre_controls.V_cutoff = ctrl.V_cutoff
        self.timbre_controls.V_resonance = ctrl.V_resonance
        self.timbre_controls.V_pan = ctrl.V_pan
        self.timbre_controls.V_tremolo = ctrl.V_tremolo
        self.timbre_controls.V_attack = ctrl.V_attack
        self.timbre_controls.V_volume = ctrl.V_volume
        self.timbre_controls.V_mode = ctrl.V_mode
        self.timbre_controls.V_brightness = ctrl.V_brightness
        self.cutoff_slider.blockSignals(True)
        self.cutoff_slider.setValue(round(ctrl.V_cutoff * 100))
        self.cutoff_slider.blockSignals(False)
        self.resonance_slider.blockSignals(True)
        self.resonance_slider.setValue(round(ctrl.V_resonance * 100))
        self.resonance_slider.blockSignals(False)
        self.pan_slider.blockSignals(True)
        self.pan_slider.setValue(round(ctrl.V_pan * 100))
        self.pan_slider.blockSignals(False)
        self.tremolo_slider.blockSignals(True)
        self.tremolo_slider.setValue(round(ctrl.V_tremolo * 100))
        self.tremolo_slider.blockSignals(False)
        self.attack_slider.blockSignals(True)
        self.attack_slider.setValue(round(ctrl.V_attack * 100))
        self.attack_slider.blockSignals(False)
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(round(ctrl.V_volume * 100))
        self.volume_slider.blockSignals(False)
        self.mode_slider.blockSignals(True)
        self.mode_slider.setValue(round(ctrl.V_mode * 100))
        self.mode_slider.blockSignals(False)
        self.brightness_slider.blockSignals(True)
        self.brightness_slider.setValue(round(ctrl.V_brightness * 100))
        self.brightness_slider.blockSignals(False)
        self._update_cutoff_display()
        self._update_resonance_display()
        self._update_pan_display()
        self._update_tremolo_display()
        self._update_attack_display()
        self._update_volume_display()
        self._update_mode_display()
        self._update_brightness_display()
    
    def _update_stats_display(self):
        """Update the stats display values from MotionState."""
        if not self.current_motion_state:
            # Default values if motion state not available
            self.hand_height_L_lcd.display("0.500")
            self.arm_extension_L_lcd.display("0.500")
            self.elbow_bend_L_lcd.display("0.500")
            self.lateral_offset_L_lcd.display("0.500")
            self.hands_spread_lcd.display("0.500")
            self.hand_height_R_lcd.display("0.500")
            self.arm_extension_R_lcd.display("0.500")
            self.elbow_bend_R_lcd.display("0.500")
            self.lateral_offset_R_lcd.display("0.500")
            self.activity_L_lcd.display("0.000")
            self.activity_R_lcd.display("0.000")
            self.activity_global_lcd.display("0.000")
            self.jerk_L_lcd.display("0.000")
            self.jerk_R_lcd.display("0.000")
            self.imu_confidence_L_lcd.display("0.000")
            self.imu_confidence_R_lcd.display("0.000")
            self.shake_energy_L_lcd.display("0.000")
            self.shake_energy_R_lcd.display("0.000")
            self.mediapipe_confidence_lcd.display("0.000")
            return
        
        # Update pose features (5 LCDs + right-hand labels)
        self.hand_height_L_lcd.display(f"{self.current_motion_state.hand_height_L:.3f}")
        self.arm_extension_L_lcd.display(f"{self.current_motion_state.arm_extension_L:.3f}")
        self.elbow_bend_L_lcd.display(f"{self.current_motion_state.elbow_bend_L:.3f}")
        self.lateral_offset_L_lcd.display(f"{self.current_motion_state.lateral_offset_L:.3f}")
        self.hands_spread_lcd.display(f"{self.current_motion_state.hand_spread:.3f}")
        self.hand_height_R_lcd.display(f"{self.current_motion_state.hand_height_R:.3f}")
        self.arm_extension_R_lcd.display(f"{self.current_motion_state.arm_extension_R:.3f}")
        self.elbow_bend_R_lcd.display(f"{self.current_motion_state.elbow_bend_R:.3f}")
        self.lateral_offset_R_lcd.display(f"{self.current_motion_state.lateral_offset_R:.3f}")
        
        # Update dynamics features
        self.activity_L_lcd.display(f"{self.current_motion_state.activity_L:.3f}")
        self.activity_R_lcd.display(f"{self.current_motion_state.activity_R:.3f}")
        self.activity_global_lcd.display(f"{self.current_motion_state.activity_global:.3f}")
        self.jerk_L_lcd.display(f"{self.current_motion_state.jerk_L:.3f}")
        self.jerk_R_lcd.display(f"{self.current_motion_state.jerk_R:.3f}")
        self.imu_confidence_L_lcd.display(f"{self.current_motion_state.imu_confidence_L:.3f}")
        self.imu_confidence_R_lcd.display(f"{self.current_motion_state.imu_confidence_R:.3f}")
        self.shake_energy_L_lcd.display(f"{self.current_motion_state.shake_energy_L:.3f}")
        self.shake_energy_R_lcd.display(f"{self.current_motion_state.shake_energy_R:.3f}")
        
        # Update confidence values
        self.mediapipe_confidence_lcd.display(f"{self.current_motion_state.mediapipe_confidence:.3f}")
    
    def _on_cutoff_changed(self, value):
        """Handle cutoff slider change - update TimbreControls and snapshot (UI layer)."""
        # UI updates TimbreControls (decoupled from audio)
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_cutoff = normalized_value
        
        # Update atomic snapshot only when cutoff is manual (not sensor-driven, not Prototype A/B/C)
        if not self._is_cutoff_sensor_controlled() and not self._is_prototype_a() and not self._is_prototype_b() and not self._is_prototype_c():
            self._update_atomic_snapshot()
        
        self._update_cutoff_display()
    
    def _on_prototype_changed(self, index):
        """Handle prototype dropdown: Cutoff Only disables cutoff slider; Prototype A/B/C drive sliders from sensors."""
        if hasattr(self, 'cutoff_slider'):
            self.cutoff_slider.setEnabled(index != PROTOTYPE_INDEX_CUTOFF_ONLY)
        if self._is_prototype_b():
            self._update_prototype_b_smoothing()
        if self._is_prototype_c():
            self._update_prototype_c_smoothing()
        self._update_atomic_snapshot()
        if self._is_prototype_a() and hasattr(self, 'cutoff_slider'):
            self._push_prototype_a_values_to_ui()
        elif self._is_prototype_b() and hasattr(self, 'cutoff_slider'):
            self._push_prototype_b_values_to_ui()
        elif self._is_prototype_c() and hasattr(self, 'cutoff_slider'):
            self._push_prototype_c_values_to_ui()
        else:
            self._update_cutoff_display()
    
    def _update_cutoff_display(self):
        """Update the cutoff display."""
        if self._is_prototype_a() or self._is_prototype_b() or self._is_prototype_c() or self._is_cutoff_sensor_controlled():
            display_value = self.ctrl_snapshot.V_cutoff
        else:
            display_value = self.timbre_controls.V_cutoff
        f_min = 250.0
        f_max = 12000.0
        display_cutoff = math.exp(
            math.log(f_min) + display_value * (math.log(f_max) - math.log(f_min))
        )
        self.cutoff_display.setText(
            f"Cutoff: {display_value:.2f}  |  Frequency: {display_cutoff:.1f} Hz"
        )
    
    def _on_resonance_changed(self, value):
        """Handle resonance slider change - update TimbreControls and snapshot (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_resonance = normalized_value
        if not self._is_prototype_a() and not self._is_prototype_b() and not self._is_prototype_c():
            self._update_atomic_snapshot()
        self._update_resonance_display()
    
    def _update_resonance_display(self):
        """Update the resonance display."""
        v = (self.ctrl_snapshot.V_resonance if (self._is_prototype_a() or self._is_prototype_b() or self._is_prototype_c())
             else self.timbre_controls.V_resonance)
        Q_min = 0.7
        mode_val = (self.ctrl_snapshot.V_mode if (self._is_prototype_a() or self._is_prototype_b() or self._is_prototype_c())
                    else self.timbre_controls.V_mode)
        if mode_val > 0.6:
            Q_max = 10.0
        else:
            Q_max = 5.0
        Q_base = Q_min + (Q_max - Q_min) * (v ** 1.8)
        attack_val = (self.ctrl_snapshot.V_attack if (self._is_prototype_a() or self._is_prototype_b() or self._is_prototype_c())
                      else self.timbre_controls.V_attack)
        Q_with_attack = Q_base * (1.0 + 0.5 * attack_val)
        Q_final = max(Q_min, min(Q_max, Q_with_attack))
        self.resonance_display.setText(
            f"Resonance: {v:.2f}  |  Q: {Q_final:.2f} (max: {Q_max:.1f})"
        )
    
    def _on_attack_changed(self, value):
        """Handle attack slider change - update TimbreControls only (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_attack = normalized_value
        
        # Update displays (attack affects Q, so update resonance display too)
        self._update_attack_display()
    
    def _on_brightness_changed(self, value):
        """Handle brightness slider change - update TimbreControls and snapshot (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_brightness = normalized_value
        if not self._is_prototype_a() and not self._is_prototype_b() and not self._is_prototype_c():
            self._update_atomic_snapshot()
        self._update_brightness_display()
        self._update_resonance_display()
    
    def _update_attack_display(self):
        """Update the attack display."""
        v = (self.ctrl_snapshot.V_attack if (self._is_prototype_b() or self._is_prototype_c())
             else self.timbre_controls.V_attack)
        self.attack_display.setText(
            f"Attack: {v:.2f}"
        )
    
    def _update_brightness_display(self):
        """Update the brightness display."""
        v = (self.ctrl_snapshot.V_brightness if (self._is_prototype_a() or self._is_prototype_b() or self._is_prototype_c())
             else self.timbre_controls.V_brightness)
        self.brightness_display.setText(
            f"Brightness: {v:.2f}"
        )
    
    def _on_tremolo_changed(self, value):
        """Handle tremolo slider change - update TimbreControls and snapshot (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_tremolo = normalized_value
        if not self._is_prototype_a() and not self._is_prototype_c():
            self._update_atomic_snapshot()
        self._update_tremolo_display()
    
    def _update_tremolo_display(self):
        """Update the tremolo display."""
        v = (self.ctrl_snapshot.V_tremolo if (self._is_prototype_a() or self._is_prototype_c())
             else self.timbre_controls.V_tremolo)
        self.tremolo_display.setText(
            f"Tremolo: {v:.2f}"
        )
    
    def _on_mode_changed(self, value):
        """Handle mode slider change - update TimbreControls and snapshot (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_mode = normalized_value
        
        if not self._is_prototype_b() and not self._is_prototype_c():
            self._update_atomic_snapshot()
        
        self._update_mode_display()
        self._update_resonance_display()
    
    def _update_mode_display(self):
        """Update the mode display."""
        mode_value = (self.ctrl_snapshot.V_mode if (self._is_prototype_b() or self._is_prototype_c())
                      else self.timbre_controls.V_mode)
        if mode_value > 0.6:
            mode_text = "Intense"
        elif mode_value < 0.4:
            mode_text = "Calm"
        else:
            mode_text = "Medium"
        self.mode_display.setText(
            f"Mode: {mode_value:.2f} ({mode_text})"
        )
    
    def _on_volume_changed(self, value):
        """Handle volume slider change - update TimbreControls and snapshot (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_volume = normalized_value
        if not self._is_prototype_a() and not self._is_prototype_b() and not self._is_prototype_c():
            self._update_atomic_snapshot()
        self._update_volume_display()
    
    def _update_volume_display(self):
        """Update the volume display."""
        volume_value = (self.ctrl_snapshot.V_volume if (self._is_prototype_a() or self._is_prototype_b() or self._is_prototype_c())
                        else self.timbre_controls.V_volume)
        volume_curve = 0.32
        volume_curved = volume_value ** volume_curve
        gain_db = -30.0 + volume_curved * (0.0 - (-30.0))
        self.volume_display.setText(
            f"Volume: {volume_value:.2f}  |  Gain: {gain_db:.1f} dB"
        )
    
    def _on_pan_changed(self, value):
        """Handle pan slider change - update TimbreControls and snapshot (UI layer)."""
        normalized_value = value / 100.0  # 0-100 -> 0.0-1.0 (50 -> 0.5 center)
        self.timbre_controls.V_pan = normalized_value
        if not self._is_prototype_a() and not self._is_prototype_c():
            self._update_atomic_snapshot()
        self._update_pan_display()
    
    def _update_pan_display(self):
        """Update the pan display (pan 0-1, display as -1..+1 and L/C/R)."""
        pan_norm = (self.ctrl_snapshot.V_pan if (self._is_prototype_a() or self._is_prototype_c())
                    else self.timbre_controls.V_pan)
        pan_signed = (pan_norm - 0.5) * 2.0  # -1 to +1
        if abs(pan_signed) < 0.05:
            pos = "Center"
        elif pan_signed < 0:
            pos = "L"
        else:
            pos = "R"
        self.pan_display.setText(f"Pan: {pan_signed:+.2f} ({pos})")
    
    def _on_cutoff_smooth_toggled(self, checked):
        """Handle cutoff smoothing checkbox toggle."""
        self.smooth_cutoff = checked
        # Reset smoothed value to current target when toggling
        if not checked:
            f_min = 250.0
            f_max = 12000.0
            target = math.exp(
                math.log(f_min) + self.timbre_controls.V_cutoff * (math.log(f_max) - math.log(f_min))
            )
            self.cutoff_hz_smoothed = target
    
    def _on_resonance_smooth_toggled(self, checked):
        """Handle resonance smoothing checkbox toggle."""
        self.smooth_resonance = checked
        # Reset smoothed value to current target when toggling
        if not checked:
            Q_min = 0.7
            Q_max = 8.0
            target_Q = Q_min + (Q_max - Q_min) * (self.timbre_controls.V_resonance ** 1.8)
            target_Q *= 1.0 + 0.5 * self.timbre_controls.V_attack
            target_Q = max(Q_min, min(Q_max, target_Q))
            self.Q_smoothed = target_Q
    
    def _update_progress(self):
        """Update progress bar and time labels."""
        if self.audio_data is None or self.audio_sample_rate is None:
            return
        
        # Calculate current time
        current_seconds = self.audio_position_samples / self.audio_sample_rate
        minutes = int(current_seconds // 60)
        seconds = int(current_seconds % 60)
        self.current_time_label.setText(f"{minutes}:{seconds:02d}")
        
        # Update progress bar
        if self.total_duration_samples > 0:
            progress = int((self.audio_position_samples / self.total_duration_samples) * 1000)
            self.progress_bar.setValue(progress)
        
        # Update live waveform from ring buffer
        with self._live_lock:
            if self._live_buffer is not None and len(self._live_buffer) > 0:
                b = self._live_buffer
                idx = self._live_index
                part_oldest = b[idx:].copy()
                part_newest = b[:idx].copy()
                self.waveform_widget.set_live_samples(np.concatenate([part_oldest, part_newest]))
    
    def _audio_callback(self, outdata, frames, time, status):
        """
        Audio callback - processes audio with low-pass filter.
        Audio code reads ONLY from TimbreControls, never from UI sliders directly.
        """
        if status:
            print(f"Audio status: {status}")
        
        if not self.is_playing or self.audio_data is None:
            outdata.fill(0)
            return
        
        # Track buffer size for smoothing calculation
        self._last_buffer_size = frames
        
        # Apply TimbreControls to audio (sample the struct)
        # This ensures audio always uses current TimbreControls values
        self._apply_timbre_controls()
        
        samples_needed = frames
        output = np.zeros((samples_needed,), dtype=np.float32)
        
        # Read from audio data (with looping)
        for i in range(samples_needed):
            if self.audio_position >= len(self.audio_data):
                self.audio_position = 0
                self.audio_position_samples = 0  # Reset progress on loop
            
            sample = self.audio_data[int(self.audio_position)]
            
            # Apply Low-Pass Filter (matching timbre-test.py logic)
            lpf_filtered = (self.lpf_b0 * sample + 
                           self.lpf_b1 * self.lpf_x1 + 
                           self.lpf_b2 * self.lpf_x2 - 
                           self.lpf_a1 * self.lpf_y1 - 
                           self.lpf_a2 * self.lpf_y2)
            
            # Update LPF filter state (shift delay line)
            self.lpf_x2 = self.lpf_x1
            self.lpf_x1 = sample
            self.lpf_y2 = self.lpf_y1
            self.lpf_y1 = lpf_filtered
            
            # Apply Tremolo (amplitude modulation)
            if self.tremolo_depth > 0.01:  # Only if tremolo is active
                # Update LFO phase
                dt = 1.0 / self.audio_sample_rate  # Time per sample
                self.tremolo_phase += 2.0 * math.pi * self.tremolo_rate_hz * dt
                if self.tremolo_phase > 2.0 * math.pi:
                    self.tremolo_phase -= 2.0 * math.pi
                
                # Calculate tremolo gain (LFO modulates amplitude)
                lfo_value = math.sin(self.tremolo_phase)
                # tremolo_gain: 1.0 (no effect) to (1.0 - depth) (maximum effect)
                tremolo_gain = 1.0 - (self.tremolo_depth * (1.0 + lfo_value) / 2.0)
                lpf_filtered = lpf_filtered * tremolo_gain
            
            # Apply Volume (after filtering, before output)
            # Volume is already smoothed in _apply_timbre_controls()
            lpf_filtered = lpf_filtered * self.volume_gain_linear
            
            output[i] = lpf_filtered
            
            # Update audio position (increment by 1 for each sample)
            self.audio_position = (self.audio_position + 1) % len(self.audio_data)
            self.audio_position_samples = (self.audio_position_samples + 1)
            if self.audio_position_samples >= self.total_duration_samples:
                self.audio_position_samples = 0  # Reset on loop
        
        # Equal-power stereo panning (same as IMU Pipeline C/D: pan -1=left, +1=right)
        ctrl = self.ctrl_snapshot
        pan = max(-1.0, min(1.0, (ctrl.V_pan - 0.5) * 2.0))
        left_gain = math.sqrt((1.0 - pan) / 2.0)
        right_gain = math.sqrt((1.0 + pan) / 2.0)
        outdata[:, 0] = output * left_gain
        outdata[:, 1] = output * right_gain
        
        # Feed live waveform ring buffer (thread-safe)
        with self._live_lock:
            if self._live_buffer is not None:
                b = self._live_buffer
                for i in range(frames):
                    b[self._live_index] = output[i]
                    self._live_index = (self._live_index + 1) % len(b)
    
    def _on_play_toggle(self):
        """Handle play button toggle."""
        if self.is_playing:
            # Stop playback
            self.is_playing = False
            self.progress_timer.stop()
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            self.audio_position = 0
            self.audio_position_samples = 0
            self._reset_filter_states()
            self._update_progress()  # Reset progress display
            self.play_button.setText("Play")
            self.play_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    border-radius: 6px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #229954;
                }
                QPushButton:pressed {
                    background-color: #1e8449;
                }
            """)
        else:
            # Start playback
            self.is_playing = True
            self.audio_position = 0
            self.audio_position_samples = 0
            self._reset_filter_states()
            # Allocate live waveform ring buffer if needed
            if self._live_buffer is None and self.audio_sample_rate is not None:
                buf_len = int(LIVE_WINDOW_SECONDS * self.audio_sample_rate)
                self._live_buffer = np.zeros(buf_len, dtype=np.float32)
                self._live_index = 0
            
            try:
                self.stream = sd.OutputStream(
                    samplerate=self.audio_sample_rate,
                    channels=2,  # Stereo for pan
                    dtype=np.float32,
                    callback=self._audio_callback,
                    blocksize=512
                )
                self.stream.start()
                self.progress_timer.start()  # Start progress updates
                self.play_button.setText("Stop")
                self.play_button.setStyleSheet("""
                    QPushButton {
                        background-color: #e74c3c;
                        color: white;
                        border: none;
                        padding: 6px 12px;
                        border-radius: 6px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #c0392b;
                    }
                    QPushButton:pressed {
                        background-color: #a93226;
                    }
                """)
            except Exception as e:
                print(f"Error starting audio stream: {e}")
                self.is_playing = False
    
    def _reset_filter_states(self):
        """Reset all filter states."""
        self.lpf_x1 = 0.0
        self.lpf_x2 = 0.0
        self.lpf_y1 = 0.0
        self.lpf_y2 = 0.0
        self.tremolo_phase = 0.0  # Reset tremolo LFO phase
        
        # Reset volume smoothed value to current target
        if self.audio_sample_rate:
            volume_curve = 0.32
            volume_normalized = max(0.0, min(1.0, self.timbre_controls.V_volume))
            volume_curved = volume_normalized ** volume_curve
            gain_db = -30.0 + volume_curved * (0.0 - (-30.0))
            target_gain_linear = 10.0 ** (gain_db / 20.0)
            self.volume_gain_linear_smoothed = target_gain_linear
            self.volume_gain_linear = target_gain_linear
        # Reset smoothed values to current target (for smooth restart)
        if self.audio_sample_rate:
            # Reset cutoff smoothed value (with brightness macro applied)
            f_min = 250.0
            f_max = 12000.0
            target_cutoff = math.exp(
                math.log(f_min) + self.timbre_controls.V_cutoff * (math.log(f_max) - math.log(f_min))
            )
            # Apply brightness macro
            brightness = self.timbre_controls.V_brightness
            b = (brightness - 0.5) * 2.0
            target_cutoff *= 2.0 ** (0.35 * b)
            self.cutoff_hz_smoothed = target_cutoff
            self.cutoff_hz = target_cutoff
            
            # Reset Q smoothed value (with brightness macro applied)
            Q_min = 0.7
            Q_max = 8.0
            target_Q = Q_min + (Q_max - Q_min) * (self.timbre_controls.V_resonance ** 1.8)
            target_Q *= 1.0 + 0.5 * self.timbre_controls.V_attack
            target_Q = max(Q_min, min(Q_max, target_Q))
            # Apply brightness macro
            brightness = self.timbre_controls.V_brightness
            b = (brightness - 0.5) * 2.0
            target_Q *= 2.0 ** (0.10 * b)
            if hasattr(self, 'Q_smoothed'):
                self.Q_smoothed = target_Q
            self.Q = target_Q
        else:
            # Initialize to reasonable defaults if sample rate not available yet
            self.cutoff_hz_smoothed = 1000.0
            self.cutoff_hz = 1000.0
            if hasattr(self, 'Q_smoothed'):
                self.Q_smoothed = 0.707
            self.Q = 0.707
    
    def closeEvent(self, event):
        """Handle window close - cleanup audio, video, MediaPipe, and IMU."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
        if self.progress_timer:
            self.progress_timer.stop()
        if self.video_timer:
            self.video_timer.stop()
        if self.cap is not None:
            self.cap.release()
        if self.pose is not None:
            self.pose.close()
        
        # Stop IMU readers (skip R if same as L, e.g. AP mode single device)
        if self.imu_reader_L:
            try:
                self.imu_reader_L.stop()
            except Exception as e:
                print(f"Error stopping left IMU reader: {e}")
        if self.imu_reader_R and self.imu_reader_R is not self.imu_reader_L:
            try:
                self.imu_reader_R.stop()
            except Exception as e:
                print(f"Error stopping right IMU reader: {e}")
        
        event.accept()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    window = TimbreControl3Window()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

