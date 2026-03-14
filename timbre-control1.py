#!/usr/bin/env python3
"""Timbre Control - Decoupled audio mapping engine with TimbreControls vector."""

import sys
import math
import numpy as np
import sounddevice as sd
import librosa
from pathlib import Path
from dataclasses import dataclass
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QProgressBar, QCheckBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont


@dataclass
class TimbreControls:
    """Normalized timbre control vector (all values 0-1)."""
    V_brightness: float = 0.0      # overall timbral brightness macro
    V_cutoff: float = 0.0           # low-pass cutoff (log-mapped)
    V_resonance: float = 0.0         # resonance / Q intensity
    V_presence: float = 0.0          # high-shelf gain (presence)
    V_motion: float = 0.0            # overall motion energy (macro driver)
    V_attack: float = 0.0            # spikiness / transient energy
    V_stereo: float = 0.5           # stereo intent (0=left, 1=right)
    V_chorus_mix: float = 0.0        # chorus amount
    V_phaser_depth: float = 0.0     # phaser intensity
    V_mode: float = 0.0              # calm (0) → intense (1)
    
    # Enable/disable flags for each control (all start disabled)
    enable_brightness: bool = False
    enable_cutoff: bool = False
    enable_resonance: bool = False
    enable_presence: bool = False
    enable_motion: bool = False
    enable_attack: bool = False
    enable_stereo: bool = False
    enable_chorus: bool = False
    enable_phaser: bool = False
    enable_mode: bool = False


class AudioState:
    """Holds all DSP parameters and smoothed values."""
    
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        
        # Smoothed DSP parameters
        # Start with pass-through (very high cutoff = no filtering)
        self.cutoff_hz = sample_rate  # Start at Nyquist = pass-through
        self.Q = 0.707
        self.presence_gain_db = 0.0
        self.pan = 0.0  # -1.0 (left) to +1.0 (right)
        self.stereo_width = 1.0
        
        # Chorus parameters
        self.chorus_mix = 0.0
        self.chorus_depth_ms = 4.0
        self.chorus_rate_hz = 0.2
        self.chorus_delay_ms = 20.0
        
        # Phaser parameters
        self.phaser_depth = 0.0
        self.phaser_rate_hz = 0.1
        
        # Filter coefficients (updated by apply_timbre_controls)
        # Initialize to pass-through to avoid static
        self.lpf_b0 = 1.0
        self.lpf_b1 = 0.0
        self.lpf_b2 = 0.0
        self.lpf_a1 = 0.0
        self.lpf_a2 = 0.0
        
        self.shelf_b0 = 1.0
        self.shelf_b1 = 0.0
        self.shelf_b2 = 0.0
        self.shelf_a1 = 0.0
        self.shelf_a2 = 0.0
        
        # Filter states
        self.lpf_x1 = 0.0
        self.lpf_x2 = 0.0
        self.lpf_y1 = 0.0
        self.lpf_y2 = 0.0
        
        self.shelf_x1 = 0.0
        self.shelf_x2 = 0.0
        self.shelf_y1 = 0.0
        self.shelf_y2 = 0.0
        
        # Chorus delay buffer
        max_delay_samples = int((50.0 / 1000.0) * sample_rate)
        self.chorus_buffer_size = max_delay_samples
        self.chorus_buffer = np.zeros(self.chorus_buffer_size, dtype=np.float32)
        self.chorus_write_pos = 0
        self.chorus_phase = 0.0
        
        # Phaser all-pass filters (4 stages)
        self.phaser_stages = 4
        self.phaser_ap_x1 = [0.0] * 4
        self.phaser_ap_x2 = [0.0] * 4
        self.phaser_ap_y1 = [0.0] * 4
        self.phaser_ap_y2 = [0.0] * 4
        self.phaser_phase = 0.0
        self.phaser_min_freq = 200.0
        self.phaser_max_freq = 2000.0


def smooth(target, current, tau_ms, sample_rate):
    """One-pole smoothing filter to avoid zipper noise.
    
    Args:
        target: Target value
        current: Current smoothed value
        tau_ms: Time constant in milliseconds
        sample_rate: Audio sample rate
    
    Returns:
        Smoothed value
    """
    if tau_ms <= 0:
        return target
    alpha = 1.0 - math.exp(-1.0 / (tau_ms / 1000.0 * sample_rate))
    return current + alpha * (target - current)


def lerp(a, b, t):
    """Linear interpolation."""
    return a + (b - a) * t


def clamp01(x):
    """Clamp value to [0, 1]."""
    return max(0.0, min(1.0, x))


def apply_timbre_controls(ctrl: TimbreControls, audio_state: AudioState):
    """
    Maps normalized timbre controls to DSP parameters
    and applies them to the audio engine.
    
    This is the ONLY function that converts TimbreControls to DSP parameters.
    All parameter changes are smoothed to avoid zipper noise.
    """
    fs = audio_state.sample_rate
    
    # === 1. Low-Pass Filter Cutoff (PRIMARY TIMBRE CONTROL) ===
    f_min = 200.0      # Hz (very muffled) - match timbre-test.py
    f_max = 8000.0     # Hz (very bright) - match timbre-test.py
    
    # Cutoff should work independently - just like brightness in timbre-test.py
    if ctrl.enable_cutoff:
        # Logarithmic mapping: cutoff directly controlled by V_cutoff slider
        cutoff_hz = math.exp(
            lerp(math.log(f_min), math.log(f_max), clamp01(ctrl.V_cutoff))
        )
        # Debug: print when cutoff changes significantly
        if not hasattr(audio_state, '_last_cutoff_debug'):
            audio_state._last_cutoff_debug = 0.0
        if abs(cutoff_hz - audio_state._last_cutoff_debug) > 50.0:  # Only print on significant change
            print(f"[DEBUG] Cutoff (V_cutoff): {cutoff_hz:.1f} Hz (value={ctrl.V_cutoff:.2f})")
            audio_state._last_cutoff_debug = cutoff_hz
    else:
        # Cutoff disabled - don't set a value yet, let brightness or default handle it
        cutoff_hz = None  # Will be set by brightness or default to pass-through
    
    # === 2. Resonance (Q) — Dramatic but Stable ===
    Q_min = 0.7
    Q_max = 8.0
    
    if ctrl.enable_resonance:
        Q = lerp(Q_min, Q_max, clamp01(ctrl.V_resonance) ** 1.8)
    else:
        Q = 0.707  # Safe default: Butterworth
    
    # Attack macro (recommended)
    if ctrl.enable_attack:
        Q *= lerp(1.0, 1.5, clamp01(ctrl.V_attack))
        Q = max(Q_min, min(Q_max, Q))
    
    # === 3. Brightness Macro (Moves Multiple Parameters) ===
    # Make brightness more dramatic - directly control cutoff like timbre-test.py
    if ctrl.enable_brightness:
        brightness = clamp01(ctrl.V_brightness)
        # Brightness directly sets cutoff (like timbre-test.py) - this makes it very obvious
        brightness_cutoff = math.exp(
            lerp(math.log(f_min), math.log(f_max), brightness)
        )
        # If cutoff is also enabled, blend them (brightness acts as multiplier)
        if cutoff_hz is not None:
            # Both enabled: brightness multiplies the cutoff
            cutoff_hz = cutoff_hz * lerp(0.5, 1.5, brightness)
            if not hasattr(audio_state, '_last_brightness_debug') or abs(brightness - audio_state._last_brightness_debug) > 0.1:
                print(f"[DEBUG] Brightness: value={brightness:.2f}, cutoff={cutoff_hz:.1f} Hz (blended with V_cutoff)")
                audio_state._last_brightness_debug = brightness
        else:
            # Cutoff disabled, brightness directly controls it (like timbre-test.py)
            cutoff_hz = brightness_cutoff
            if not hasattr(audio_state, '_last_brightness_debug') or abs(brightness - audio_state._last_brightness_debug) > 0.1:
                print(f"[DEBUG] Brightness: value={brightness:.2f}, cutoff={cutoff_hz:.1f} Hz (direct control, like timbre-test.py)")
                audio_state._last_brightness_debug = brightness
        Q *= lerp(1.0, 1.2, brightness)
    elif cutoff_hz is None:
        # Neither cutoff nor brightness enabled - use pass-through (very high cutoff)
        cutoff_hz = fs  # Set to sample rate (Nyquist) = pass-through
    
    # === 4. Mode Control (Calm vs Intense) ===
    if ctrl.enable_mode:
        mode = clamp01(ctrl.V_mode)
        if mode > 0.6:
            Q_max_mode = 10.0
        else:
            Q_max_mode = 5.0
        # Clamp Q to mode-dependent max
        Q = min(Q, Q_max_mode)
    else:
        Q_max_mode = 8.0  # Default max
    
    # === 5. Motion Macro Driver (gates all modulation) ===
    if ctrl.enable_motion:
        mod_intensity = clamp01(ctrl.V_motion)
        if ctrl.enable_mode:
            mode = clamp01(ctrl.V_mode)
            if mode > 0.6:
                mod_intensity *= 1.2
            else:
                mod_intensity *= 0.8
    else:
        mod_intensity = 0.0  # Disable all modulation if motion is off
    
    # === 6. Presence / High-Shelf Filter ===
    shelf_freq = 3500.0  # Hz
    if ctrl.enable_presence:
        presence_gain_db = lerp(-3.0, +9.0, clamp01(ctrl.V_presence))
        # Safety coupling: reduce presence if cutoff is very low
        if cutoff_hz < 2000:
            presence_gain_db *= 0.4
    else:
        presence_gain_db = 0.0  # No presence boost/cut
    
    # === 7. Chorus (Obvious, Musical, Forgiving) ===
    if ctrl.enable_chorus:
        chorus_mix = lerp(0.0, 0.7, clamp01(ctrl.V_chorus_mix) * mod_intensity)
        chorus_depth_ms = lerp(4.0, 18.0, mod_intensity)
        chorus_rate_hz = lerp(0.2, 1.2, mod_intensity)
    else:
        chorus_mix = 0.0
        chorus_depth_ms = 4.0
        chorus_rate_hz = 0.2
    
    # === 8. Phaser (Gesture / Accent Effect) ===
    if ctrl.enable_phaser:
        phaser_depth = lerp(
            0.0, 0.9, clamp01(ctrl.V_phaser_depth) * clamp01(ctrl.V_attack) if ctrl.enable_attack else 0.0
        )
        phaser_rate_hz = lerp(0.1, 0.8, mod_intensity)
        # Phaser should be inactive during calm motion
        if mod_intensity < 0.1:
            phaser_depth = 0.0
    else:
        phaser_depth = 0.0
        phaser_rate_hz = 0.1
    
    # === 9. Stereo / Pan ===
    if ctrl.enable_stereo:
        pan = lerp(-1.0, +1.0, clamp01(ctrl.V_stereo))
        # Optional stereo width macro
        stereo_width = lerp(0.8, 1.3, mod_intensity)
    else:
        pan = 0.0  # Center
        stereo_width = 1.0  # Normal width
    
    # === Apply Smoothing (MANDATORY) ===
    tau_cutoff = 30.0  # ms
    tau_Q = 20.0       # ms
    tau_presence = 40.0  # ms
    tau_pan = 25.0     # ms
    tau_chorus = 30.0  # ms
    tau_phaser = 25.0  # ms
    
    audio_state.cutoff_hz = smooth(cutoff_hz, audio_state.cutoff_hz, tau_cutoff, fs)
    audio_state.Q = smooth(Q, audio_state.Q, tau_Q, fs)
    audio_state.presence_gain_db = smooth(presence_gain_db, audio_state.presence_gain_db, tau_presence, fs)
    audio_state.pan = smooth(pan, audio_state.pan, tau_pan, fs)
    audio_state.chorus_mix = smooth(chorus_mix, audio_state.chorus_mix, tau_chorus, fs)
    audio_state.chorus_depth_ms = smooth(chorus_depth_ms, audio_state.chorus_depth_ms, tau_chorus, fs)
    audio_state.chorus_rate_hz = smooth(chorus_rate_hz, audio_state.chorus_rate_hz, tau_chorus, fs)
    audio_state.phaser_depth = smooth(phaser_depth, audio_state.phaser_depth, tau_phaser, fs)
    audio_state.phaser_rate_hz = smooth(phaser_rate_hz, audio_state.phaser_rate_hz, tau_phaser, fs)
    audio_state.stereo_width = smooth(stereo_width, audio_state.stereo_width, tau_chorus, fs)
    
    # === Update Filter Coefficients ===
    # Low-pass filter coefficients
    # IMPORTANT: Check if cutoff is in valid range for filter
    # Only apply filter if cutoff is below Nyquist (pass-through if >= Nyquist)
    nyquist = fs / 2.0
    if audio_state.cutoff_hz > 0 and audio_state.cutoff_hz < nyquist:
        fc = audio_state.cutoff_hz
        Q_val = audio_state.Q
        
        w = 2.0 * math.pi * fc / fs
        k = math.tan(w / 2.0)
        k2 = k * k
        k_over_q = k / Q_val
        norm = 1.0 / (1.0 + k_over_q + k2)
        
        audio_state.lpf_b0 = k2 * norm
        audio_state.lpf_b1 = 2.0 * audio_state.lpf_b0
        audio_state.lpf_b2 = audio_state.lpf_b0
        audio_state.lpf_a1 = 2.0 * (k2 - 1.0) * norm
        audio_state.lpf_a2 = (1.0 - k_over_q + k2) * norm
        
        # Debug: print filter coefficients when they change significantly
        if not hasattr(audio_state, '_last_fc_debug'):
            audio_state._last_fc_debug = 0.0
            audio_state._debug_counter = 0
        
        audio_state._debug_counter += 1
        
        # Print when cutoff changes significantly or every 1000 calls
        if abs(fc - audio_state._last_fc_debug) > 100.0 or audio_state._debug_counter % 1000 == 0:
            print(f"[DEBUG] Filter ACTIVE: cutoff={fc:.1f} Hz, Q={Q_val:.2f}, b0={audio_state.lpf_b0:.4f}, a1={audio_state.lpf_a1:.4f}, nyquist={nyquist:.1f} Hz")
            audio_state._last_fc_debug = fc
    else:
        # Pass-through - cutoff is out of valid range
        audio_state.lpf_b0 = 1.0
        audio_state.lpf_b1 = 0.0
        audio_state.lpf_b2 = 0.0
        audio_state.lpf_a1 = 0.0
        audio_state.lpf_a2 = 0.0
        # Only print pass-through warning once or when it changes
        if not hasattr(audio_state, '_pass_through_warned') or not audio_state._pass_through_warned:
            print(f"[DEBUG] Filter PASS-THROUGH: cutoff={audio_state.cutoff_hz:.1f} Hz is OUT OF RANGE (must be 0 < cutoff < {nyquist:.1f} Hz)")
            audio_state._pass_through_warned = True
    
    # High-shelf filter coefficients
    if abs(audio_state.presence_gain_db) > 0.01:
        fc = shelf_freq
        gain_db = audio_state.presence_gain_db
        A = 10.0 ** (gain_db / 40.0)  # sqrt of gain for shelf filters
        S = 1.0  # Shelf slope parameter
        
        w = 2.0 * math.pi * fc / fs
        k = math.tan(w / 2.0)
        k2 = k * k
        kS = k * S
        k2S = k2 * S
        
        if gain_db > 0:
            # Boost
            norm = 1.0 / (1.0 + kS + k2)
            audio_state.shelf_b0 = A * (1.0 + kS + k2) * norm
            audio_state.shelf_b1 = A * 2.0 * (k2 - 1.0) * norm
            audio_state.shelf_b2 = A * (1.0 - kS + k2) * norm
            audio_state.shelf_a1 = 2.0 * (k2 - 1.0) * norm
            audio_state.shelf_a2 = (1.0 - kS + k2) * norm
        else:
            # Cut
            norm = 1.0 / (A + kS + A * k2)
            audio_state.shelf_b0 = (1.0 + kS + k2) * norm
            audio_state.shelf_b1 = 2.0 * (k2 - 1.0) * norm
            audio_state.shelf_b2 = (1.0 - kS + k2) * norm
            audio_state.shelf_a1 = 2.0 * (A * k2 - 1.0) * norm
            audio_state.shelf_a2 = (A - kS + A * k2) * norm
    else:
        # Pass-through
        audio_state.shelf_b0 = 1.0
        audio_state.shelf_b1 = 0.0
        audio_state.shelf_b2 = 0.0
        audio_state.shelf_a1 = 0.0
        audio_state.shelf_a2 = 0.0


class TimbreControlWindow(QMainWindow):
    """Main window for timbre control application."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Timbre Control - Vector Mapping Engine")
        self.setMinimumSize(600, 800)
        
        # Audio state
        self.audio_data = None
        self.audio_sample_rate = None
        self.audio_position = 0
        self.audio_position_samples = 0  # Track position in samples for progress
        self.is_playing = False
        self.stream = None
        
        # Timbre controls (decoupled from UI)
        self.timbre_controls = TimbreControls()
        
        # Audio state (holds DSP parameters)
        self.audio_state = None
        
        # Progress update timer
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._update_progress)
        self.progress_timer.setInterval(100)  # Update every 100ms
        
        # Load audio file
        self._load_audio_file()
        
        # Initialize audio state
        self.audio_state = AudioState(self.audio_sample_rate)
        
        # Initialize UI
        self._init_ui()
        
        # Initial DSP update (this will set initial filter coefficients)
        apply_timbre_controls(self.timbre_controls, self.audio_state)
        
        # Initialize brightness cutoff display
        if hasattr(self, 'brightness_cutoff_label'):
            cutoff = self.audio_state.cutoff_hz
            self.brightness_cutoff_label.setText(f"Cutoff: {cutoff:.1f} Hz")
            print(f"[DEBUG] Initial state: cutoff={cutoff:.1f} Hz, Q={self.audio_state.Q:.2f}")
    
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
    
    def _init_ui(self):
        """Initialize the UI with 10 sliders."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title = QLabel("Timbre Control Vector → Audio Mapping")
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
            self.total_duration_samples = len(self.audio_data)
        else:
            self.total_duration_samples = 1  # Avoid division by zero
        
        # Select All checkbox
        select_all_layout = QHBoxLayout()
        self.select_all_checkbox = QCheckBox("Select All")
        self.select_all_checkbox.setFont(QFont("Arial", 12, QFont.Bold))
        self.select_all_checkbox.setChecked(False)  # Start unchecked
        self.select_all_checkbox.stateChanged.connect(self._on_select_all_changed)
        select_all_layout.addWidget(self.select_all_checkbox)
        select_all_layout.addStretch()
        layout.addLayout(select_all_layout)
        
        # Create sliders for each control
        self.sliders = {}
        self.labels = {}
        self.checkboxes = {}  # Store checkboxes for select all functionality
        
        controls = [
            ("V_brightness", "Brightness (Macro)", "enable_brightness"),
            ("V_cutoff", "Cutoff", "enable_cutoff"),
            ("V_resonance", "Resonance", "enable_resonance"),
            ("V_presence", "Presence", "enable_presence"),
            ("V_motion", "Motion (Macro)", "enable_motion"),
            ("V_attack", "Attack", "enable_attack"),
            ("V_stereo", "Stereo", "enable_stereo"),
            ("V_chorus_mix", "Chorus Mix", "enable_chorus"),
            ("V_phaser_depth", "Phaser Depth", "enable_phaser"),
            ("V_mode", "Mode (Calm→Intense)", "enable_mode"),
        ]
        
        for var_name, display_name, enable_flag in controls:
            control_layout = QVBoxLayout()
            control_layout.setSpacing(5)
            
            # Label with current value and checkbox
            label_layout = QHBoxLayout()
            
            # Checkbox to enable/disable this control
            checkbox = QCheckBox()
            checkbox.setChecked(False)  # Disabled by default
            checkbox.setToolTip(f"Enable/disable {display_name}")
            checkbox.stateChanged.connect(
                lambda state, flag=enable_flag: self._on_checkbox_changed(flag, state)
            )
            label_layout.addWidget(checkbox)
            
            # Store checkbox for select all functionality
            self.checkboxes[var_name] = checkbox
            
            name_label = QLabel(f"{display_name}:")
            name_label.setFont(QFont("Arial", 11, QFont.Bold))
            label_layout.addWidget(name_label)
            
            value_label = QLabel("0.0")
            value_label.setFont(QFont("Arial", 11))
            value_label.setMinimumWidth(50)
            value_label.setAlignment(Qt.AlignRight)
            label_layout.addWidget(value_label)
            label_layout.addStretch()
            
            control_layout.addLayout(label_layout)
            
            # Special: Add cutoff frequency display for brightness
            if var_name == "V_brightness":
                self.brightness_cutoff_label = QLabel("Cutoff: -- Hz")
                self.brightness_cutoff_label.setFont(QFont("Arial", 10))
                self.brightness_cutoff_label.setStyleSheet("color: #7f8c8d; padding: 2px;")
                control_layout.addWidget(self.brightness_cutoff_label)
            
            # Slider (0-1 in 0.1 increments = 11 steps: 0, 0.1, 0.2, ..., 1.0)
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)   # 0.0 * 10
            slider.setMaximum(10)  # 1.0 * 10
            slider.setValue(0)
            slider.setTickPosition(QSlider.TicksBelow)
            slider.setTickInterval(1)  # Every 0.1
            
            # Special default for V_stereo (0.5)
            if var_name == "V_stereo":
                slider.setValue(5)  # 0.5 * 10
                self.timbre_controls.V_stereo = 0.5
                value_label.setText("0.5")
            
            slider.valueChanged.connect(
                lambda value, vn=var_name, vl=value_label: self._on_slider_changed(vn, value, vl)
            )
            control_layout.addWidget(slider)
            
            layout.addLayout(control_layout)
            
            self.sliders[var_name] = slider
            self.labels[var_name] = value_label
        
        layout.addStretch()
    
    def _on_slider_changed(self, var_name, value, value_label):
        """Handle slider change - update TimbreControls and apply to DSP."""
        # Convert slider value (0-10) to normalized (0.0-1.0)
        normalized_value = value / 10.0
        value_label.setText(f"{normalized_value:.1f}")
        
        # Update TimbreControls (decoupled from UI)
        setattr(self.timbre_controls, var_name, normalized_value)
        
        # Apply to DSP (this is the ONLY place we call apply_timbre_controls)
        apply_timbre_controls(self.timbre_controls, self.audio_state)
        
        # Update brightness cutoff display if this is the brightness slider
        if var_name == "V_brightness":
            cutoff = self.audio_state.cutoff_hz
            self.brightness_cutoff_label.setText(f"Cutoff: {cutoff:.1f} Hz")
            print(f"[DEBUG] Brightness changed: V_brightness={normalized_value:.2f}, Final cutoff={cutoff:.1f} Hz, Q={self.audio_state.Q:.2f}")
    
    def _on_checkbox_changed(self, enable_flag, state):
        """Handle checkbox change - enable/disable a control."""
        # state: 0 = unchecked, 2 = checked
        enabled = (state == 2)
        setattr(self.timbre_controls, enable_flag, enabled)
        
        # Update select all checkbox state (check if all are checked/unchecked)
        self._update_select_all_state()
        
        # Reapply timbre controls with new enable state
        apply_timbre_controls(self.timbre_controls, self.audio_state)
        
        # Update brightness cutoff display if brightness or cutoff checkbox changed
        if enable_flag == "enable_brightness" or enable_flag == "enable_cutoff":
            if hasattr(self, 'brightness_cutoff_label'):
                cutoff = self.audio_state.cutoff_hz
                self.brightness_cutoff_label.setText(f"Cutoff: {cutoff:.1f} Hz")
                print(f"[DEBUG] Checkbox changed: {enable_flag}={enabled}, Final smoothed cutoff={cutoff:.1f} Hz, Q={self.audio_state.Q:.2f}")
    
    def _on_select_all_changed(self, state):
        """Handle select all checkbox change."""
        # state: 0 = unchecked, 2 = checked
        all_enabled = (state == 2)
        
        # Update all individual checkboxes without triggering their callbacks
        for var_name, checkbox in self.checkboxes.items():
            checkbox.blockSignals(True)  # Block signals to avoid recursion
            checkbox.setChecked(all_enabled)
            checkbox.blockSignals(False)
        
        # Update all enable flags in TimbreControls
        self.timbre_controls.enable_brightness = all_enabled
        self.timbre_controls.enable_cutoff = all_enabled
        self.timbre_controls.enable_resonance = all_enabled
        self.timbre_controls.enable_presence = all_enabled
        self.timbre_controls.enable_motion = all_enabled
        self.timbre_controls.enable_attack = all_enabled
        self.timbre_controls.enable_stereo = all_enabled
        self.timbre_controls.enable_chorus = all_enabled
        self.timbre_controls.enable_phaser = all_enabled
        self.timbre_controls.enable_mode = all_enabled
        
        # Reapply timbre controls
        apply_timbre_controls(self.timbre_controls, self.audio_state)
    
    def _update_select_all_state(self):
        """Update select all checkbox based on individual checkbox states."""
        # Check if all checkboxes are checked
        all_checked = all(checkbox.isChecked() for checkbox in self.checkboxes.values())
        
        # Update select all checkbox without triggering its callback
        self.select_all_checkbox.blockSignals(True)
        self.select_all_checkbox.setChecked(all_checked)
        self.select_all_checkbox.blockSignals(False)
    
    def _audio_callback(self, outdata, frames, time, status):
        """Audio callback - processes audio using current TimbreControls."""
        if status:
            print(f"Audio status: {status}")
        
        if not self.is_playing or self.audio_data is None:
            outdata.fill(0)
            return
        
        samples_needed = frames
        fs = self.audio_sample_rate
        dt = 1.0 / fs
        
        # Continuously apply timbre controls (for smoothing)
        # This is called every audio buffer to allow smooth parameter transitions
        apply_timbre_controls(self.timbre_controls, self.audio_state)
        
        for i in range(samples_needed):
            # Update LFO phases
            if self.audio_state.chorus_mix > 0.01:
                self.audio_state.chorus_phase += 2.0 * math.pi * self.audio_state.chorus_rate_hz * dt
                if self.audio_state.chorus_phase > 2.0 * math.pi:
                    self.audio_state.chorus_phase -= 2.0 * math.pi
            
            if self.audio_state.phaser_depth > 0.01:
                self.audio_state.phaser_phase += 2.0 * math.pi * self.audio_state.phaser_rate_hz * dt
                if self.audio_state.phaser_phase > 2.0 * math.pi:
                    self.audio_state.phaser_phase -= 2.0 * math.pi
            
            # Read sample (with looping)
            if self.audio_position >= len(self.audio_data):
                self.audio_position = 0
                self.audio_position_samples = 0  # Reset progress on loop
            
            # Use integer index
            sample = self.audio_data[int(self.audio_position)]
            
            # Apply Low-Pass Filter
            # Check if filter is actually active (not pass-through)
            is_pass_through = (abs(self.audio_state.lpf_b0 - 1.0) < 0.001 and 
                              abs(self.audio_state.lpf_b1) < 0.001 and 
                              abs(self.audio_state.lpf_a1) < 0.001)
            
            lpf_filtered = (self.audio_state.lpf_b0 * sample + 
                           self.audio_state.lpf_b1 * self.audio_state.lpf_x1 + 
                           self.audio_state.lpf_b2 * self.audio_state.lpf_x2 - 
                           self.audio_state.lpf_a1 * self.audio_state.lpf_y1 - 
                           self.audio_state.lpf_a2 * self.audio_state.lpf_y2)
            
            # Debug: occasionally check if filter is working
            if i == 0:
                if not hasattr(self, '_audio_debug_counter'):
                    self._audio_debug_counter = 0
                self._audio_debug_counter += 1
                if self._audio_debug_counter % 1000 == 0:
                    is_pass_through = (abs(self.audio_state.lpf_b0 - 1.0) < 0.001 and 
                                      abs(self.audio_state.lpf_b1) < 0.001 and 
                                      abs(self.audio_state.lpf_a1) < 0.001)
                    print(f"[DEBUG] Audio callback: cutoff={self.audio_state.cutoff_hz:.1f} Hz, pass_through={is_pass_through}, b0={self.audio_state.lpf_b0:.4f}, sample_before={sample:.4f}, sample_after={lpf_filtered:.4f}")
            
            # Update LPF state
            self.audio_state.lpf_x2 = self.audio_state.lpf_x1
            self.audio_state.lpf_x1 = sample
            self.audio_state.lpf_y2 = self.audio_state.lpf_y1
            self.audio_state.lpf_y1 = lpf_filtered
            
            processed = lpf_filtered
            
            # Apply High-Shelf EQ
            if abs(self.audio_state.presence_gain_db) > 0.01:
                shelf_filtered = (self.audio_state.shelf_b0 * processed + 
                                self.audio_state.shelf_b1 * self.audio_state.shelf_x1 + 
                                self.audio_state.shelf_b2 * self.audio_state.shelf_x2 - 
                                self.audio_state.shelf_a1 * self.audio_state.shelf_y1 - 
                                self.audio_state.shelf_a2 * self.audio_state.shelf_y2)
                
                self.audio_state.shelf_x2 = self.audio_state.shelf_x1
                self.audio_state.shelf_x1 = processed
                self.audio_state.shelf_y2 = self.audio_state.shelf_y1
                self.audio_state.shelf_y1 = shelf_filtered
                
                processed = shelf_filtered
            
            # Apply Phaser
            if self.audio_state.phaser_depth > 0.01:
                lfo_value = math.sin(self.audio_state.phaser_phase)
                freq_mod = (self.audio_state.phaser_min_freq + 
                           (self.audio_state.phaser_max_freq - self.audio_state.phaser_min_freq) * 
                           (0.5 + 0.5 * lfo_value * self.audio_state.phaser_depth))
                
                phaser_sample = processed
                for stage in range(self.audio_state.phaser_stages):
                    w = 2.0 * math.pi * freq_mod / fs
                    k = math.tan(w / 2.0)
                    norm = 1.0 / (1.0 + k)
                    
                    ap_b0 = (1.0 - k) * norm
                    ap_b1 = -1.0
                    ap_a1 = -ap_b0
                    
                    ap_out = (ap_b0 * phaser_sample + 
                             ap_b1 * self.audio_state.phaser_ap_x1[stage] - 
                             ap_a1 * self.audio_state.phaser_ap_y1[stage])
                    
                    self.audio_state.phaser_ap_x1[stage] = phaser_sample
                    self.audio_state.phaser_ap_y1[stage] = ap_out
                    
                    phaser_sample = ap_out
                
                processed = processed * 0.5 + phaser_sample * 0.5
            
            # Apply Chorus
            if self.audio_state.chorus_mix > 0.01:
                lfo_value = math.sin(self.audio_state.chorus_phase)
                delay_samples = int((self.audio_state.chorus_delay_ms + 
                                    self.audio_state.chorus_depth_ms * lfo_value) / 1000.0 * fs)
                delay_samples = max(0, min(delay_samples, self.audio_state.chorus_buffer_size - 1))
                
                read_pos = (self.audio_state.chorus_write_pos - delay_samples) % self.audio_state.chorus_buffer_size
                delayed_sample = self.audio_state.chorus_buffer[read_pos]
                
                self.audio_state.chorus_buffer[self.audio_state.chorus_write_pos] = processed
                self.audio_state.chorus_write_pos = (self.audio_state.chorus_write_pos + 1) % self.audio_state.chorus_buffer_size
                
                processed = processed * (1.0 - self.audio_state.chorus_mix) + delayed_sample * self.audio_state.chorus_mix
            
            # Apply Stereo Pan
            if outdata.shape[1] >= 2:
                # Pan: -1.0 (left) to +1.0 (right)
                # Equal-power panning
                pan = self.audio_state.pan
                pan = max(-1.0, min(1.0, pan))  # Clamp to [-1, 1]
                
                # Convert pan to left/right gains using equal-power law
                left_gain = math.sqrt((1.0 - pan) / 2.0)
                right_gain = math.sqrt((1.0 + pan) / 2.0)
                
                # Apply stereo width
                center = (left_gain + right_gain) / 2.0
                sides = (right_gain - left_gain) / 2.0
                left_gain = center - sides * self.audio_state.stereo_width
                right_gain = center + sides * self.audio_state.stereo_width
                
                # Clamp gains to prevent clipping
                left_gain = max(0.0, min(1.0, left_gain))
                right_gain = max(0.0, min(1.0, right_gain))
                
                outdata[i, 0] = processed * left_gain
                outdata[i, 1] = processed * right_gain
            else:
                # Mono output
                outdata[i, 0] = processed
            
            # Update audio position (increment by 1 for each sample, like timbre-test.py)
            self.audio_position = (self.audio_position + 1) % len(self.audio_data)
            self.audio_position_samples = (self.audio_position_samples + 1)
            if self.audio_position_samples >= self.total_duration_samples:
                self.audio_position_samples = 0  # Reset on loop
    
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
                    channels=2,  # Stereo for panning
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
        if self.audio_state:
            self.audio_state.lpf_x1 = 0.0
            self.audio_state.lpf_x2 = 0.0
            self.audio_state.lpf_y1 = 0.0
            self.audio_state.lpf_y2 = 0.0
            
            self.audio_state.shelf_x1 = 0.0
            self.audio_state.shelf_x2 = 0.0
            self.audio_state.shelf_y1 = 0.0
            self.audio_state.shelf_y2 = 0.0
            
            if self.audio_state.chorus_buffer is not None:
                self.audio_state.chorus_buffer.fill(0)
            self.audio_state.chorus_write_pos = 0
            self.audio_state.chorus_phase = 0.0
            
            for i in range(self.audio_state.phaser_stages):
                self.audio_state.phaser_ap_x1[i] = 0.0
                self.audio_state.phaser_ap_x2[i] = 0.0
                self.audio_state.phaser_ap_y1[i] = 0.0
                self.audio_state.phaser_ap_y2[i] = 0.0
            self.audio_state.phaser_phase = 0.0
    
    def closeEvent(self, event):
        """Handle window close - cleanup audio."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
        event.accept()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    window = TimbreControlWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

