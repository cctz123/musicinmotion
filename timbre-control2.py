#!/usr/bin/env python3
"""Timbre Control 2 - Simplified version based on timbre-test.py logic."""

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
    """Normalized timbre control vector - decoupled from UI."""
    V_cutoff: float = 0.0      # Low-pass cutoff (0-1, log-mapped to 250-12000 Hz)
    V_resonance: float = 0.0   # Resonance / Q intensity (0-1)
    V_attack: float = 0.0      # Spikiness / transient energy (0-1)
    V_brightness: float = 0.5  # Brightness macro (0-1, default 0.5 = neutral)


class TimbreControl2Window(QMainWindow):
    """Main window for simplified timbre control application."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Timbre Control 2 - Simplified")
        self.setMinimumSize(500, 400)
        
        # Audio state
        self.audio_data = None
        self.audio_sample_rate = None
        self.audio_position = 0
        self.audio_position_samples = 0  # Track position in samples for progress
        self.is_playing = False
        self.stream = None
        
        # TimbreControls - decoupled from UI (audio code only reads this)
        self.timbre_controls = TimbreControls()
        
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
        
        # Progress update timer
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._update_progress)
        self.progress_timer.setInterval(100)  # Update every 100ms
        
        # Load audio file
        self._load_audio_file()
        
        # Initialize UI
        self._init_ui()
        
        # Note: Filter coefficients will be initialized when audio starts
        # (audio callback will sample TimbreControls at regular intervals)
    
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
        Audio code never reads UI sliders directly - only reads TimbreControls.
        All parameter changes are smoothed to avoid zipper noise.
        """
        # === 1. Low-Pass Filter Cutoff (PRIMARY TIMBRE CONTROL) ===
        # Logarithmic mapping as specified in TICKET-P2-TIMBRE-CONTROL.MD
        f_min = 250.0      # Hz (very muffled)
        f_max = 12000.0    # Hz (very bright)
        
        # cutoff_hz = exp(lerp(log(f_min), log(f_max), ctrl["V_cutoff"]))
        target_cutoff_hz = math.exp(
            math.log(f_min) + self.timbre_controls.V_cutoff * (math.log(f_max) - math.log(f_min))
        )
        
        # === 3. Brightness Macro (Moves Multiple Parameters) ===
        # Apply brightness macro to cutoff BEFORE smoothing
        brightness = self.timbre_controls.V_brightness
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
        Q_max = 8.0
        
        # Q = lerp(Q_min, Q_max, ctrl["V_resonance"] ** 1.8)
        target_Q = Q_min + (Q_max - Q_min) * (self.timbre_controls.V_resonance ** 1.8)
        
        # Attack macro (recommended)
        # Q *= lerp(1.0, 1.5, ctrl["V_attack"])
        target_Q *= 1.0 + 0.5 * self.timbre_controls.V_attack
        # Q = clamp(Q, Q_min, Q_max)
        target_Q = max(Q_min, min(Q_max, target_Q))
        
        # Apply brightness macro to Q BEFORE smoothing
        # (brightness variable and b already calculated above)
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
        """Initialize the UI."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title = QLabel("Timbre Control 2 - Simplified")
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
        # Initialize TimbreControls with default value
        self.timbre_controls.V_cutoff = 0.5  # Default to 0.5
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
        
        layout.addStretch()
        
        # Initialize displays
        self._update_cutoff_display()
        self._update_resonance_display()
        self._update_attack_display()
        self._update_brightness_display()
    
    def _on_cutoff_changed(self, value):
        """Handle cutoff slider change - update TimbreControls only (UI layer)."""
        # UI updates TimbreControls (decoupled from audio)
        # Audio callback will sample TimbreControls at regular intervals
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_cutoff = normalized_value
        
        # Update display (for UI feedback only)
        self._update_cutoff_display()
    
    def _update_cutoff_display(self):
        """Update the cutoff display."""
        # Calculate what the frequency will be (for display only)
        f_min = 250.0
        f_max = 12000.0
        display_cutoff = math.exp(
            math.log(f_min) + self.timbre_controls.V_cutoff * (math.log(f_max) - math.log(f_min))
        )
        self.cutoff_display.setText(
            f"Cutoff: {self.timbre_controls.V_cutoff:.2f}  |  Frequency: {display_cutoff:.1f} Hz"
        )
    
    def _on_resonance_changed(self, value):
        """Handle resonance slider change - update TimbreControls only (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_resonance = normalized_value
        
        # Update display (for UI feedback only)
        self._update_resonance_display()
    
    def _update_resonance_display(self):
        """Update the resonance display."""
        # Calculate what the Q will be (for display only)
        Q_min = 0.7
        Q_max = 8.0
        Q_base = Q_min + (Q_max - Q_min) * (self.timbre_controls.V_resonance ** 1.8)
        # Apply attack macro for display
        Q_with_attack = Q_base * (1.0 + 0.5 * self.timbre_controls.V_attack)
        Q_final = max(Q_min, min(Q_max, Q_with_attack))
        self.resonance_display.setText(
            f"Resonance: {self.timbre_controls.V_resonance:.2f}  |  Q: {Q_final:.2f}"
        )
    
    def _on_attack_changed(self, value):
        """Handle attack slider change - update TimbreControls only (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_attack = normalized_value
        
        # Update displays (attack affects Q, so update resonance display too)
        self._update_attack_display()
    
    def _on_brightness_changed(self, value):
        """Handle brightness slider change - update TimbreControls only (UI layer)."""
        normalized_value = value / 100.0  # Convert from slider units to actual value (0.0-1.0)
        self.timbre_controls.V_brightness = normalized_value
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
        """Handle window close - cleanup audio."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
        if self.progress_timer:
            self.progress_timer.stop()
        event.accept()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    window = TimbreControl2Window()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

