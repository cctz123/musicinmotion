#!/usr/bin/env python3
"""Timbre Control 2 - Simplified version based on timbre-test.py logic."""

import sys
import math
import time
import numpy as np
import sounddevice as sd
import librosa
import cv2
import mediapipe as mp
from pathlib import Path
from dataclasses import dataclass
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QProgressBar, QCheckBox, QSplitter
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QImage, QPixmap
from motion_fusion import MotionFeatureExtractor, MotionState


@dataclass
class TimbreControls:
    """Normalized timbre control vector - decoupled from UI."""
    V_cutoff: float = 0.0      # Low-pass cutoff (0-1, log-mapped to 250-12000 Hz)
    V_resonance: float = 0.0   # Resonance / Q intensity (0-1)
    V_attack: float = 0.0      # Spikiness / transient energy (0-1)
    V_brightness: float = 0.5  # Brightness macro (0-1, default 0.5 = neutral)
    V_tremolo: float = 0.0     # Tremolo depth (0-1)
    V_mode: float = 0.0        # Mode control: calm (0) → intense (1)
    V_volume: float = 0.2      # Volume/loudness (0-1, default 0.2 = musically quiet but audible)


class TimbreControl3Window(QMainWindow):
    """Main window for timbre control with video and MediaPipe pose detection."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Timbre Control 3 - With Video")
        self.setMinimumSize(1000, 600)  # 2x width for split screen
        self.resize(1280, 900)  # Start at 1280x900
        
        # Audio state
        self.audio_data = None
        self.audio_sample_rate = None
        self.audio_position = 0
        self.audio_position_samples = 0  # Track position in samples for progress
        self.is_playing = False
        self.stream = None
        
        # TimbreControls - decoupled from UI (audio code only reads this)
        self.timbre_controls = TimbreControls()  # For UI updates
        
        # Atomic snapshot pattern - audio thread reads from this
        self.ctrl_snapshot = TimbreControls()  # Initial snapshot
        
        # App-level settings (not in TimbreControls - managed by app)
        self.smooth_cutoff = True   # Enable smoothing for cutoff
        self.smooth_resonance = False  # Enable smoothing for resonance (disabled by default)
        self.sensor_control_enabled = False  # Sensor control toggle
        
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
        self.volume_gain_linear = 0.2  # Current linear gain (smoothed)
        self.volume_gain_linear_smoothed = 0.2  # Smoothed value
        
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
                self.imu_reader_R = self.imu_reader_L
                if self.imu_reader_L:
                    print(f"IMU initialized (mode: {mode}, AP single device → used for both L and R)")
                else:
                    print("IMU not available (AP not configured or unavailable)")
            else:
                # Initialize left IMU (uses 'port2', if available)
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
                # If only one reader available, use it for both L and R
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
        # From ticket: V_volume ∈ [0,1] → gain_db = lerp(-30 dB, 0 dB, V_volume ^ curve)
        # Use nonlinear curve (power ≈ 1.5-2.0) for perceptual linearity
        volume_curve = 1.8  # Power curve for perceptual linearity
        volume_normalized = max(0.0, min(1.0, ctrl.V_volume))
        volume_curved = volume_normalized ** volume_curve
        
        # Map to gain in dB: -30 dB (silent) to -3 dB (full, with ~3 dB headroom)
        gain_db_min = -30.0  # Silent
        gain_db_max = -3.0   # Full volume with 3 dB headroom
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
        """Initialize the UI with split screen layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main horizontal splitter
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left side: Controls
        left_widget = QWidget()
        left_widget.setMaximumWidth(640)  # Cap at 640px width
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(15)
        
        self._init_controls_ui(left_layout)
        
        splitter.addWidget(left_widget)
        
        # Right side: Video with MediaPipe (split into video and stats)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(10)
        
        # Vertical splitter for right side
        right_splitter = QSplitter(Qt.Vertical)
        right_layout.addWidget(right_splitter)
        
        # Top: Video section
        video_widget = QWidget()
        video_widget.setMaximumHeight(450)  # Cap at 450px total
        video_layout = QVBoxLayout(video_widget)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(10)
        self._init_video_ui(video_layout)
        right_splitter.addWidget(video_widget)
        
        # Bottom: Stats section
        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)
        stats_layout.setContentsMargins(10, 10, 10, 10)
        stats_layout.setSpacing(10)
        self._init_stats_ui(stats_layout)
        right_splitter.addWidget(stats_widget)
        
        # Set splitter proportions (60% video, 40% stats)
        right_splitter.setSizes([600, 300])
        
        splitter.addWidget(right_widget)
        
        # Set splitter proportions (50/50)
        splitter.setSizes([500, 500])
    
    def _init_controls_ui(self, layout):
        """Initialize the controls UI (left side)."""
        # Title
        title = QLabel("Timbre Control 3")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(title)
        
        # Play button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.play_button = QPushButton("Play")
        self.play_button.setFont(QFont("Arial", 14, QFont.Bold))
        self.play_button.setMinimumSize(150, 60)
        self.play_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 8px;
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
        button_layout.addWidget(self.play_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Progress bar
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(5)
        
        # Time labels and progress bar
        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("0:00")
        self.current_time_label.setFont(QFont("Arial", 11))
        self.current_time_label.setMinimumWidth(50)
        time_layout.addWidget(self.current_time_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(1000)  # Use 1000 for smooth updates
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
        
        # Calculate total duration
        if self.audio_data is not None and self.audio_sample_rate is not None:
            total_duration_seconds = len(self.audio_data) / self.audio_sample_rate
            minutes = int(total_duration_seconds // 60)
            seconds = int(total_duration_seconds % 60)
            self.total_time_label.setText(f"{minutes}:{seconds:02d}")
        else:
            self.total_duration_samples = 1  # Avoid division by zero
        
        # Cutoff dial
        cutoff_layout = QVBoxLayout()
        cutoff_layout.setSpacing(10)
        
        cutoff_header = QHBoxLayout()
        cutoff_label = QLabel("Cutoff:")
        cutoff_label.setFont(QFont("Arial", 12, QFont.Bold))
        cutoff_header.addWidget(cutoff_label)
        
        # Smoothing checkbox for cutoff
        self.cutoff_smooth_checkbox = QCheckBox("Smooth")
        self.cutoff_smooth_checkbox.setChecked(True)  # Enabled by default
        self.cutoff_smooth_checkbox.setFont(QFont("Arial", 10))
        self.cutoff_smooth_checkbox.toggled.connect(self._on_cutoff_smooth_toggled)
        cutoff_header.addWidget(self.cutoff_smooth_checkbox)
        
        # Sensor control checkbox
        self.sensor_control_checkbox = QCheckBox("Sensor Control")
        self.sensor_control_checkbox.setChecked(False)  # Disabled by default
        self.sensor_control_checkbox.setFont(QFont("Arial", 10))
        self.sensor_control_checkbox.toggled.connect(self._on_sensor_control_toggled)
        cutoff_header.addWidget(self.sensor_control_checkbox)
        
        cutoff_header.addStretch()
        cutoff_layout.addLayout(cutoff_header)
        
        slider_layout = QHBoxLayout()
        
        min_label = QLabel("0.0")
        min_label.setFont(QFont("Arial", 11))
        slider_layout.addWidget(min_label)
        
        self.cutoff_slider = QSlider(Qt.Horizontal)
        self.cutoff_slider.setMinimum(0)   # 0.0 * 100 for 0.01 precision
        self.cutoff_slider.setMaximum(100) # 1.0 * 100
        self.cutoff_slider.setValue(50)    # Default to 0.5 (middle)
        self.cutoff_slider.setTickPosition(QSlider.TicksBelow)
        self.cutoff_slider.setTickInterval(10)  # Tick every 0.1
        self.cutoff_slider.valueChanged.connect(self._on_cutoff_changed)
        slider_layout.addWidget(self.cutoff_slider, 1)
        
        max_label = QLabel("1.0")
        max_label.setFont(QFont("Arial", 11))
        slider_layout.addWidget(max_label)
        
        cutoff_layout.addLayout(slider_layout)
        
        # Cutoff value and frequency display
        # Initialize TimbreControls with default values
        self.timbre_controls.V_cutoff = 0.5  # Default to 0.5
        self.timbre_controls.V_volume = 0.2  # Default to 0.2 (musically quiet but audible)
        # Initialize atomic snapshot
        self._update_atomic_snapshot()
        # Calculate initial cutoff for display (using ticket formula)
        f_min = 250.0
        f_max = 12000.0
        initial_cutoff = math.exp(math.log(f_min) + 0.5 * (math.log(f_max) - math.log(f_min)))
        self.cutoff_display = QLabel(f"Cutoff: 0.5  |  Frequency: {initial_cutoff:.1f} Hz")
        self.cutoff_display.setFont(QFont("Arial", 11))
        self.cutoff_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        cutoff_layout.addWidget(self.cutoff_display)
        
        layout.addLayout(cutoff_layout)
        
        # Resonance dial
        resonance_layout = QVBoxLayout()
        resonance_layout.setSpacing(10)
        
        resonance_header = QHBoxLayout()
        resonance_label = QLabel("Resonance:")
        resonance_label.setFont(QFont("Arial", 12, QFont.Bold))
        resonance_header.addWidget(resonance_label)
        
        # Smoothing checkbox for resonance
        self.resonance_smooth_checkbox = QCheckBox("Smooth")
        self.resonance_smooth_checkbox.setChecked(False)  # Disabled by default
        self.resonance_smooth_checkbox.setFont(QFont("Arial", 10))
        self.resonance_smooth_checkbox.toggled.connect(self._on_resonance_smooth_toggled)
        resonance_header.addWidget(self.resonance_smooth_checkbox)
        resonance_header.addStretch()
        resonance_layout.addLayout(resonance_header)
        
        resonance_slider_layout = QHBoxLayout()
        
        res_min_label = QLabel("0.0")
        res_min_label.setFont(QFont("Arial", 11))
        resonance_slider_layout.addWidget(res_min_label)
        
        self.resonance_slider = QSlider(Qt.Horizontal)
        self.resonance_slider.setMinimum(0)   # 0.0 * 100
        self.resonance_slider.setMaximum(100) # 1.0 * 100
        self.resonance_slider.setValue(0)     # Default to 0.0
        self.resonance_slider.setTickPosition(QSlider.TicksBelow)
        self.resonance_slider.setTickInterval(10)  # Tick every 0.1
        self.resonance_slider.valueChanged.connect(self._on_resonance_changed)
        resonance_slider_layout.addWidget(self.resonance_slider, 1)
        
        res_max_label = QLabel("1.0")
        res_max_label.setFont(QFont("Arial", 11))
        resonance_slider_layout.addWidget(res_max_label)
        
        resonance_layout.addLayout(resonance_slider_layout)
        
        # Resonance value and Q display
        self.resonance_display = QLabel("Resonance: 0.0  |  Q: 0.70")
        self.resonance_display.setFont(QFont("Arial", 11))
        self.resonance_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        resonance_layout.addWidget(self.resonance_display)
        
        layout.addLayout(resonance_layout)
        
        # Attack dial
        attack_layout = QVBoxLayout()
        attack_layout.setSpacing(10)
        
        attack_label = QLabel("Attack:")
        attack_label.setFont(QFont("Arial", 12, QFont.Bold))
        attack_layout.addWidget(attack_label)
        
        attack_slider_layout = QHBoxLayout()
        
        attack_min_label = QLabel("0.0")
        attack_min_label.setFont(QFont("Arial", 11))
        attack_slider_layout.addWidget(attack_min_label)
        
        self.attack_slider = QSlider(Qt.Horizontal)
        self.attack_slider.setMinimum(0)   # 0.0 * 100
        self.attack_slider.setMaximum(100) # 1.0 * 100
        self.attack_slider.setValue(0)     # Default to 0.0
        self.attack_slider.setTickPosition(QSlider.TicksBelow)
        self.attack_slider.setTickInterval(10)  # Tick every 0.1
        self.attack_slider.valueChanged.connect(self._on_attack_changed)
        attack_slider_layout.addWidget(self.attack_slider, 1)
        
        attack_max_label = QLabel("1.0")
        attack_max_label.setFont(QFont("Arial", 11))
        attack_slider_layout.addWidget(attack_max_label)
        
        attack_layout.addLayout(attack_slider_layout)
        
        # Attack value display
        self.attack_display = QLabel("Attack: 0.0")
        self.attack_display.setFont(QFont("Arial", 11))
        self.attack_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        attack_layout.addWidget(self.attack_display)
        
        layout.addLayout(attack_layout)
        
        # Brightness dial
        brightness_layout = QVBoxLayout()
        brightness_layout.setSpacing(10)
        
        brightness_label = QLabel("Brightness:")
        brightness_label.setFont(QFont("Arial", 12, QFont.Bold))
        brightness_layout.addWidget(brightness_label)
        
        brightness_slider_layout = QHBoxLayout()
        
        brightness_min_label = QLabel("0.0")
        brightness_min_label.setFont(QFont("Arial", 11))
        brightness_slider_layout.addWidget(brightness_min_label)
        
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setMinimum(0)   # 0.0 * 100
        self.brightness_slider.setMaximum(100) # 1.0 * 100
        self.brightness_slider.setValue(50)     # Default to 0.5 (50% = neutral)
        self.brightness_slider.setTickPosition(QSlider.TicksBelow)
        self.brightness_slider.setTickInterval(10)  # Tick every 0.1
        self.brightness_slider.valueChanged.connect(self._on_brightness_changed)
        brightness_slider_layout.addWidget(self.brightness_slider, 1)
        
        brightness_max_label = QLabel("1.0")
        brightness_max_label.setFont(QFont("Arial", 11))
        brightness_slider_layout.addWidget(brightness_max_label)
        
        brightness_layout.addLayout(brightness_slider_layout)
        
        # Brightness value display
        self.brightness_display = QLabel("Brightness: 0.50")
        self.brightness_display.setFont(QFont("Arial", 11))
        self.brightness_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        brightness_layout.addWidget(self.brightness_display)
        
        layout.addLayout(brightness_layout)
        
        # Tremolo dial
        tremolo_layout = QVBoxLayout()
        tremolo_layout.setSpacing(10)
        
        tremolo_label = QLabel("Tremolo:")
        tremolo_label.setFont(QFont("Arial", 12, QFont.Bold))
        tremolo_layout.addWidget(tremolo_label)
        
        tremolo_slider_layout = QHBoxLayout()
        
        tremolo_min_label = QLabel("0.0")
        tremolo_min_label.setFont(QFont("Arial", 11))
        tremolo_slider_layout.addWidget(tremolo_min_label)
        
        self.tremolo_slider = QSlider(Qt.Horizontal)
        self.tremolo_slider.setMinimum(0)   # 0.0 * 100
        self.tremolo_slider.setMaximum(100) # 1.0 * 100
        self.tremolo_slider.setValue(0)     # Default to 0.0
        self.tremolo_slider.setTickPosition(QSlider.TicksBelow)
        self.tremolo_slider.setTickInterval(10)  # Tick every 0.1
        self.tremolo_slider.valueChanged.connect(self._on_tremolo_changed)
        tremolo_slider_layout.addWidget(self.tremolo_slider, 1)
        
        tremolo_max_label = QLabel("1.0")
        tremolo_max_label.setFont(QFont("Arial", 11))
        tremolo_slider_layout.addWidget(tremolo_max_label)
        
        tremolo_layout.addLayout(tremolo_slider_layout)
        
        # Tremolo value display
        self.tremolo_display = QLabel("Tremolo: 0.00")
        self.tremolo_display.setFont(QFont("Arial", 11))
        self.tremolo_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        tremolo_layout.addWidget(self.tremolo_display)
        
        layout.addLayout(tremolo_layout)
        
        # Mode dial
        mode_layout = QVBoxLayout()
        mode_layout.setSpacing(10)
        
        mode_label = QLabel("Mode:")
        mode_label.setFont(QFont("Arial", 12, QFont.Bold))
        mode_layout.addWidget(mode_label)
        
        mode_slider_layout = QHBoxLayout()
        
        mode_min_label = QLabel("0.0 (Calm)")
        mode_min_label.setFont(QFont("Arial", 11))
        mode_slider_layout.addWidget(mode_min_label)
        
        self.mode_slider = QSlider(Qt.Horizontal)
        self.mode_slider.setMinimum(0)   # 0.0 * 100
        self.mode_slider.setMaximum(100) # 1.0 * 100
        self.mode_slider.setValue(0)     # Default to 0.0 (calm)
        self.mode_slider.setTickPosition(QSlider.TicksBelow)
        self.mode_slider.setTickInterval(10)  # Tick every 0.1
        self.mode_slider.valueChanged.connect(self._on_mode_changed)
        mode_slider_layout.addWidget(self.mode_slider, 1)
        
        mode_max_label = QLabel("1.0 (Intense)")
        mode_max_label.setFont(QFont("Arial", 11))
        mode_slider_layout.addWidget(mode_max_label)
        
        mode_layout.addLayout(mode_slider_layout)
        
        # Mode value display
        self.mode_display = QLabel("Mode: 0.00 (Calm)")
        self.mode_display.setFont(QFont("Arial", 11))
        self.mode_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        mode_layout.addWidget(self.mode_display)
        
        layout.addLayout(mode_layout)
        
        # Volume dial
        volume_layout = QVBoxLayout()
        volume_layout.setSpacing(10)
        
        volume_label = QLabel("Volume:")
        volume_label.setFont(QFont("Arial", 12, QFont.Bold))
        volume_layout.addWidget(volume_label)
        
        volume_slider_layout = QHBoxLayout()
        
        volume_min_label = QLabel("0.0")
        volume_min_label.setFont(QFont("Arial", 11))
        volume_slider_layout.addWidget(volume_min_label)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setMinimum(0)   # 0.0 * 100
        self.volume_slider.setMaximum(100) # 1.0 * 100
        self.volume_slider.setValue(20)     # Default to 0.2 (musically quiet but audible)
        self.volume_slider.setTickPosition(QSlider.TicksBelow)
        self.volume_slider.setTickInterval(10)  # Tick every 0.1
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_slider_layout.addWidget(self.volume_slider, 1)
        
        volume_max_label = QLabel("1.0")
        volume_max_label.setFont(QFont("Arial", 11))
        volume_slider_layout.addWidget(volume_max_label)
        
        volume_layout.addLayout(volume_slider_layout)
        
        # Volume value display
        self.volume_display = QLabel("Volume: 0.20")
        self.volume_display.setFont(QFont("Arial", 11))
        self.volume_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        volume_layout.addWidget(self.volume_display)
        
        layout.addLayout(volume_layout)
        
        layout.addStretch()
        
        # Initialize displays
        self._update_cutoff_display()
        self._update_resonance_display()
        self._update_attack_display()
        self._update_brightness_display()
        self._update_tremolo_display()
        self._update_mode_display()
        self._update_volume_display()
    
    def _init_video_ui(self, layout):
        """Initialize the video UI (right side)."""
        # Title
        video_title = QLabel("MediaPipe Pose Detection")
        video_title.setFont(QFont("Arial", 18, QFont.Bold))
        video_title.setMaximumHeight(30)  # Limit title height
        layout.addWidget(video_title)
        
        # Video display label
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(320, 240)  # Smaller minimum, will expand to fit
        self.video_label.setMaximumHeight(400)  # Cap height at 400px (450px widget - ~50px for title/spacing)
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
        """Initialize the stats UI (bottom section of right side)."""
        # Title
        stats_title = QLabel("Sensor Reading")
        stats_title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(stats_title)
        
        # Create a scrollable area for all stats
        from PyQt5.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_widget.setLayout(scroll_layout)
        
        # Helper function to create stat row
        def create_stat_row(label_text, value_attr_name):
            row_layout = QHBoxLayout()
            label = QLabel(f"{label_text}:")
            label.setFont(QFont("Arial", 10))
            row_layout.addWidget(label)
            value_label = QLabel("0.00")
            value_label.setFont(QFont("Arial", 24, QFont.Bold))
            value_label.setStyleSheet("color: #2c3e50;")
            row_layout.addWidget(value_label, 1)
            row_layout.addStretch()
            return value_label, row_layout
        
        # Create two-column layout
        two_column_layout = QHBoxLayout()
        left_column = QVBoxLayout()
        right_column = QVBoxLayout()
        two_column_layout.addLayout(left_column)
        two_column_layout.addLayout(right_column)
        
        # Pose features section (spans both columns)
        pose_section = QLabel("Pose Features (MediaPipe)")
        pose_section.setFont(QFont("Arial", 14, QFont.Bold))
        pose_section.setStyleSheet("color: #3498db; margin-top: 10px;")
        scroll_layout.addWidget(pose_section)
        
        # Add pose features in two columns - hand-specific stats first, left in left column, right in right column
        # Left column: Left hand stats
        self.hand_height_L_value, row = create_stat_row("hand_height_L", "hand_height_L")
        left_column.addLayout(row)
        self.arm_extension_L_value, row = create_stat_row("arm_extension_L", "arm_extension_L")
        left_column.addLayout(row)
        self.elbow_bend_L_value, row = create_stat_row("elbow_bend_L", "elbow_bend_L")
        left_column.addLayout(row)
        self.lateral_offset_L_value, row = create_stat_row("lateral_offset_L", "lateral_offset_L")
        left_column.addLayout(row)
        
        # Right column: Right hand stats
        self.hand_height_R_value, row = create_stat_row("hand_height_R", "hand_height_R")
        right_column.addLayout(row)
        self.arm_extension_R_value, row = create_stat_row("arm_extension_R", "arm_extension_R")
        right_column.addLayout(row)
        self.elbow_bend_R_value, row = create_stat_row("elbow_bend_R", "elbow_bend_R")
        right_column.addLayout(row)
        self.lateral_offset_R_value, row = create_stat_row("lateral_offset_R", "lateral_offset_R")
        right_column.addLayout(row)
        
        # Other pose stats (hand_spread spans both columns or goes in left)
        self.hands_spread_value, row = create_stat_row("hand_spread", "hand_spread")
        left_column.addLayout(row)
        
        # Add the two-column layout to scroll layout
        scroll_layout.addLayout(two_column_layout)
        
        # Dynamics features section
        dynamics_section = QLabel("Dynamics Features (IMU)")
        dynamics_section.setFont(QFont("Arial", 14, QFont.Bold))
        dynamics_section.setStyleSheet("color: #e74c3c; margin-top: 10px;")
        scroll_layout.addWidget(dynamics_section)
        
        # Create another two-column layout for dynamics
        dynamics_two_column = QHBoxLayout()
        dynamics_left = QVBoxLayout()
        dynamics_right = QVBoxLayout()
        dynamics_two_column.addLayout(dynamics_left)
        dynamics_two_column.addLayout(dynamics_right)
        
        # Hand-specific stats first: left in left column, right in right column
        self.activity_L_value, row = create_stat_row("activity_L", "activity_L")
        dynamics_left.addLayout(row)
        self.activity_R_value, row = create_stat_row("activity_R", "activity_R")
        dynamics_right.addLayout(row)
        
        self.jerk_L_value, row = create_stat_row("jerk_L", "jerk_L")
        dynamics_left.addLayout(row)
        self.jerk_R_value, row = create_stat_row("jerk_R", "jerk_R")
        dynamics_right.addLayout(row)
        
        self.shake_energy_L_value, row = create_stat_row("shake_energy_L", "shake_energy_L")
        dynamics_left.addLayout(row)
        self.shake_energy_R_value, row = create_stat_row("shake_energy_R", "shake_energy_R")
        dynamics_right.addLayout(row)
        
        # Other dynamics stats (activity_global spans both columns or goes in left)
        self.activity_global_value, row = create_stat_row("activity_global", "activity_global")
        dynamics_left.addLayout(row)
        
        scroll_layout.addLayout(dynamics_two_column)
        
        # Confidence section
        confidence_section = QLabel("Confidence")
        confidence_section.setFont(QFont("Arial", 14, QFont.Bold))
        confidence_section.setStyleSheet("color: #27ae60; margin-top: 10px;")
        scroll_layout.addWidget(confidence_section)
        
        # Confidence in two columns
        confidence_two_column = QHBoxLayout()
        conf_left = QVBoxLayout()
        conf_right = QVBoxLayout()
        confidence_two_column.addLayout(conf_left)
        confidence_two_column.addLayout(conf_right)
        
        self.mediapipe_confidence_value, row = create_stat_row("mediapipe_confidence", "mediapipe_confidence")
        conf_left.addLayout(row)
        self.imu_confidence_L_value, row = create_stat_row("imu_confidence_L", "imu_confidence_L")
        conf_right.addLayout(row)
        
        self.imu_confidence_R_value, row = create_stat_row("imu_confidence_R", "imu_confidence_R")
        conf_left.addLayout(row)
        
        scroll_layout.addLayout(confidence_two_column)
        
        left_column.addStretch()
        right_column.addStretch()
        dynamics_left.addStretch()
        dynamics_right.addStretch()
        conf_left.addStretch()
        conf_right.addStretch()
        scroll_layout.addStretch()
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
    
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
        
        # Convert back to BGR for display
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
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
        self._update_atomic_snapshot()
        
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
    
    def _update_atomic_snapshot(self):
        """Create and assign atomic snapshot with all control values."""
        # Build new snapshot with all values
        # If sensor control is enabled, use sensor value; otherwise use UI value
        cutoff_value = self._smoothed_hand_height_R if self.sensor_control_enabled else self.timbre_controls.V_cutoff
        
        new_ctrl = TimbreControls(
            V_cutoff=cutoff_value,
            V_resonance=self.timbre_controls.V_resonance,
            V_attack=self.timbre_controls.V_attack,
            V_brightness=self.timbre_controls.V_brightness,
            V_tremolo=self.timbre_controls.V_tremolo,
            V_mode=self.timbre_controls.V_mode,
            V_volume=self.timbre_controls.V_volume,
        )
        
        # Atomic assignment (lock-free, coherent)
        self.ctrl_snapshot = new_ctrl
    
    def _update_stats_display(self):
        """Update the stats display values from MotionState."""
        if not self.current_motion_state:
            # Default values if motion state not available
            self.hand_height_L_value.setText("0.50")
            self.hand_height_R_value.setText("0.50")
            self.arm_extension_L_value.setText("0.50")
            self.arm_extension_R_value.setText("0.50")
            self.elbow_bend_L_value.setText("0.50")
            self.elbow_bend_R_value.setText("0.50")
            self.hands_spread_value.setText("0.50")
            self.lateral_offset_L_value.setText("0.50")
            self.lateral_offset_R_value.setText("0.50")
            self.activity_L_value.setText("0.00")
            self.activity_R_value.setText("0.00")
            self.activity_global_value.setText("0.00")
            self.jerk_L_value.setText("0.00")
            self.jerk_R_value.setText("0.00")
            self.shake_energy_L_value.setText("0.00")
            self.shake_energy_R_value.setText("0.00")
            self.mediapipe_confidence_value.setText("0.00")
            self.imu_confidence_L_value.setText("0.00")
            self.imu_confidence_R_value.setText("0.00")
            return
        
        # Update pose features
        self.hand_height_L_value.setText(f"{self.current_motion_state.hand_height_L:.2f}")
        self.hand_height_R_value.setText(f"{self.current_motion_state.hand_height_R:.2f}")
        self.arm_extension_L_value.setText(f"{self.current_motion_state.arm_extension_L:.2f}")
        self.arm_extension_R_value.setText(f"{self.current_motion_state.arm_extension_R:.2f}")
        self.elbow_bend_L_value.setText(f"{self.current_motion_state.elbow_bend_L:.2f}")
        self.elbow_bend_R_value.setText(f"{self.current_motion_state.elbow_bend_R:.2f}")
        self.hands_spread_value.setText(f"{self.current_motion_state.hand_spread:.2f}")
        self.lateral_offset_L_value.setText(f"{self.current_motion_state.lateral_offset_L:.2f}")
        self.lateral_offset_R_value.setText(f"{self.current_motion_state.lateral_offset_R:.2f}")
        
        # Update dynamics features
        self.activity_L_value.setText(f"{self.current_motion_state.activity_L:.2f}")
        self.activity_R_value.setText(f"{self.current_motion_state.activity_R:.2f}")
        self.activity_global_value.setText(f"{self.current_motion_state.activity_global:.2f}")
        self.jerk_L_value.setText(f"{self.current_motion_state.jerk_L:.2f}")
        self.jerk_R_value.setText(f"{self.current_motion_state.jerk_R:.2f}")
        self.shake_energy_L_value.setText(f"{self.current_motion_state.shake_energy_L:.2f}")
        self.shake_energy_R_value.setText(f"{self.current_motion_state.shake_energy_R:.2f}")
        
        # Update confidence values
        self.mediapipe_confidence_value.setText(f"{self.current_motion_state.mediapipe_confidence:.2f}")
        self.imu_confidence_L_value.setText(f"{self.current_motion_state.imu_confidence_L:.2f}")
        self.imu_confidence_R_value.setText(f"{self.current_motion_state.imu_confidence_R:.2f}")
    
    def _on_cutoff_changed(self, value):
        """Handle cutoff slider change - update TimbreControls and snapshot (UI layer)."""
        # UI updates TimbreControls (decoupled from audio)
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_cutoff = normalized_value
        
        # Update atomic snapshot (only if sensor control is disabled)
        if not self.sensor_control_enabled:
            self._update_atomic_snapshot()
        
        # Update display (for UI feedback only)
        self._update_cutoff_display()
    
    def _on_sensor_control_toggled(self, checked):
        """Handle sensor control checkbox toggle."""
        self.sensor_control_enabled = checked
        
        # Enable/disable cutoff slider based on sensor control
        self.cutoff_slider.setEnabled(not checked)
        
        # Update snapshot immediately
        self._update_atomic_snapshot()
        
        # Update display
        self._update_cutoff_display()
    
    def _update_cutoff_display(self):
        """Update the cutoff display."""
        # Show current value (from snapshot if sensor control enabled, else from UI)
        if self.sensor_control_enabled:
            display_value = self.ctrl_snapshot.V_cutoff
            source = "Sensor"
        else:
            display_value = self.timbre_controls.V_cutoff
            source = "Manual"
        
        # Calculate what the frequency will be (for display only)
        f_min = 250.0
        f_max = 12000.0
        display_cutoff = math.exp(
            math.log(f_min) + display_value * (math.log(f_max) - math.log(f_min))
        )
        self.cutoff_display.setText(
            f"Cutoff: {display_value:.2f} ({source})  |  Frequency: {display_cutoff:.1f} Hz"
        )
    
    def _on_resonance_changed(self, value):
        """Handle resonance slider change - update TimbreControls and snapshot (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_resonance = normalized_value
        
        # Update atomic snapshot
        self._update_atomic_snapshot()
        
        # Update display (for UI feedback only)
        self._update_resonance_display()
    
    def _update_resonance_display(self):
        """Update the resonance display."""
        # Calculate what the Q will be (for display only)
        Q_min = 0.7
        # Mode affects Q_max
        if self.timbre_controls.V_mode > 0.6:
            Q_max = 10.0
        else:
            Q_max = 5.0
        Q_base = Q_min + (Q_max - Q_min) * (self.timbre_controls.V_resonance ** 1.8)
        # Apply attack macro for display
        Q_with_attack = Q_base * (1.0 + 0.5 * self.timbre_controls.V_attack)
        Q_final = max(Q_min, min(Q_max, Q_with_attack))
        self.resonance_display.setText(
            f"Resonance: {self.timbre_controls.V_resonance:.2f}  |  Q: {Q_final:.2f} (max: {Q_max:.1f})"
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
        
        # Update atomic snapshot
        self._update_atomic_snapshot()
        
        self._update_brightness_display()
        self._update_resonance_display()
    
    def _update_attack_display(self):
        """Update the attack display."""
        self.attack_display.setText(
            f"Attack: {self.timbre_controls.V_attack:.2f}"
        )
    
    def _update_brightness_display(self):
        """Update the brightness display."""
        self.brightness_display.setText(
            f"Brightness: {self.timbre_controls.V_brightness:.2f}"
        )
    
    def _on_tremolo_changed(self, value):
        """Handle tremolo slider change - update TimbreControls and snapshot (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_tremolo = normalized_value
        
        # Update atomic snapshot
        self._update_atomic_snapshot()
        
        self._update_tremolo_display()
    
    def _update_tremolo_display(self):
        """Update the tremolo display."""
        self.tremolo_display.setText(
            f"Tremolo: {self.timbre_controls.V_tremolo:.2f}"
        )
    
    def _on_mode_changed(self, value):
        """Handle mode slider change - update TimbreControls and snapshot (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_mode = normalized_value
        
        # Update atomic snapshot
        self._update_atomic_snapshot()
        
        # Mode affects Q, so update resonance display too
        self._update_mode_display()
        self._update_resonance_display()
    
    def _update_mode_display(self):
        """Update the mode display."""
        mode_value = self.timbre_controls.V_mode
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
        
        # Update atomic snapshot
        self._update_atomic_snapshot()
        
        self._update_volume_display()
    
    def _update_volume_display(self):
        """Update the volume display."""
        volume_value = self.timbre_controls.V_volume
        # Calculate gain in dB for display
        volume_curve = 1.8
        volume_curved = volume_value ** volume_curve
        gain_db = -30.0 + volume_curved * (-3.0 - (-30.0))
        self.volume_display.setText(
            f"Volume: {volume_value:.2f}  |  Gain: {gain_db:.1f} dB"
        )
    
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
        
        # Convert to stereo if needed (sounddevice expects 2D array)
        if len(output.shape) == 1:
            outdata[:, 0] = output
            if outdata.shape[1] > 1:
                outdata[:, 1] = output
    
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
                    padding: 15px 30px;
                    border-radius: 8px;
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
            
            try:
                self.stream = sd.OutputStream(
                    samplerate=self.audio_sample_rate,
                    channels=1,  # Mono
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
                        padding: 15px 30px;
                        border-radius: 8px;
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
            volume_curve = 1.8
            volume_normalized = max(0.0, min(1.0, self.timbre_controls.V_volume))
            volume_curved = volume_normalized ** volume_curve
            gain_db = -30.0 + volume_curved * (-3.0 - (-30.0))
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
        
        # Stop IMU readers
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

