#!/usr/bin/env python3
"""Timbre test application - brightness control with low-pass filter."""

import sys
import math
import numpy as np
import sounddevice as sd
import librosa
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QRadioButton, QButtonGroup, QCheckBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class TimbreTestWindow(QMainWindow):
    """Main window for timbre test application."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Timbre Test - Brightness Control")
        self.setMinimumSize(500, 300)
        
        # Audio state
        self.audio_data = None
        self.audio_sample_rate = None
        self.audio_position = 0
        self.is_playing = False
        self.stream = None
        
        # Filter state
        self.brightness = 0.0  # -5 to +5
        self.filter_mode = "linear"  # "none", "linear", or "log"
        self.lpf_cutoff_hz = 500.0  # Default (middle of 200-8000 Hz range)
        self.resonance_q = 0.707  # Default Q (Butterworth, no peak)
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
        
        # High-shelf EQ state
        self.shelf_gain_db = 0.0  # -6 to +6 dB
        self.shelf_frequency_hz = 3500.0  # Fixed at 3.5 kHz
        # High-shelf biquad filter coefficients
        self.shelf_b0 = 0.0
        self.shelf_b1 = 0.0
        self.shelf_b2 = 0.0
        self.shelf_a1 = 0.0
        self.shelf_a2 = 0.0
        # High-shelf biquad filter state
        self.shelf_x1 = 0.0
        self.shelf_x2 = 0.0
        self.shelf_y1 = 0.0
        self.shelf_y2 = 0.0
        
        # Modulation effects state
        # Tremolo (amplitude modulation)
        self.tremolo_enabled = False
        self.tremolo_rate_hz = 5.0  # LFO rate in Hz
        self.tremolo_depth = 0.0  # 0.0 to 1.0 (0% to 100%)
        self.tremolo_phase = 0.0
        
        # Vibrato (pitch modulation)
        self.vibrato_enabled = False
        self.vibrato_rate_hz = 6.0  # LFO rate in Hz
        self.vibrato_depth_cents = 0.0  # Depth in cents (±)
        self.vibrato_phase = 0.0
        
        # Chorus
        self.chorus_enabled = False
        self.chorus_rate_hz = 0.5  # LFO rate in Hz
        self.chorus_depth_ms = 10.0  # Delay depth in milliseconds
        self.chorus_delay_ms = 20.0  # Base delay in milliseconds
        self.chorus_mix = 0.5  # Wet/dry mix (0.0 to 1.0)
        self.chorus_phase = 0.0
        self.chorus_buffer = None
        self.chorus_buffer_size = 0
        self.chorus_write_pos = 0
        
        # Flanger
        self.flanger_enabled = False
        self.flanger_rate_hz = 0.3  # LFO rate in Hz
        self.flanger_depth_ms = 2.0  # Delay depth in milliseconds
        self.flanger_delay_ms = 1.0  # Base delay in milliseconds
        self.flanger_feedback = 0.3  # Feedback amount (0.0 to 0.5)
        self.flanger_mix = 0.5  # Wet/dry mix
        self.flanger_phase = 0.0
        self.flanger_buffer = None
        self.flanger_buffer_size = 0
        self.flanger_write_pos = 0
        
        # Phaser
        self.phaser_enabled = False
        self.phaser_rate_hz = 0.5  # LFO rate in Hz
        self.phaser_depth = 0.8  # Modulation depth (0.0 to 1.0)
        self.phaser_stages = 4  # Number of all-pass filter stages
        self.phaser_phase = 0.0
        self.phaser_min_freq = 200.0  # Minimum all-pass frequency (Hz)
        self.phaser_max_freq = 2000.0  # Maximum all-pass frequency (Hz)
        # All-pass filter states (one per stage)
        self.phaser_ap_x1 = [0.0] * 4
        self.phaser_ap_x2 = [0.0] * 4
        self.phaser_ap_y1 = [0.0] * 4
        self.phaser_ap_y2 = [0.0] * 4
        
        # Load audio file
        self._load_audio_file()
        
        self._init_ui()
    
    def _load_audio_file(self):
        """Load music.mp3 audio file."""
        # Try multiple possible locations
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
        
        # Initialize delay buffers for chorus and flanger
        max_delay_samples = int((50.0 / 1000.0) * self.audio_sample_rate)  # 50ms max delay
        self.chorus_buffer_size = max_delay_samples
        self.chorus_buffer = np.zeros(self.chorus_buffer_size, dtype=np.float32)
        self.flanger_buffer_size = max_delay_samples
        self.flanger_buffer = np.zeros(self.flanger_buffer_size, dtype=np.float32)
        
        # Initialize filter state and coefficients
        self._update_lpf_cutoff()
        self._update_shelf_coefficients()
    
    def _update_lpf_cutoff(self):
        """Update LPF cutoff frequency and biquad coefficients based on brightness value and filter mode."""
        if self.filter_mode == "none":
            # No filter
            self.lpf_cutoff_hz = 0.0
            self.lpf_b0 = 1.0
            self.lpf_b1 = 0.0
            self.lpf_b2 = 0.0
            self.lpf_a1 = 0.0
            self.lpf_a2 = 0.0
        elif self.filter_mode == "linear":
            # Linear mapping: brightness = -5 -> 200 Hz, brightness = +5 -> 8000 Hz
            min_cutoff = 200.0
            max_cutoff = 8000.0
            self.lpf_cutoff_hz = min_cutoff + (self.brightness + 5.0) / 10.0 * (max_cutoff - min_cutoff)
        elif self.filter_mode == "log":
            # Logarithmic mapping
            min_cutoff = 200.0
            max_cutoff = 8000.0
            # Normalize brightness from [-5, +5] to [0, 1]
            dial_normalized = (self.brightness + 5.0) / 10.0
            dial_normalized = max(0.0, min(1.0, dial_normalized))  # Clamp to [0, 1]
            # Logarithmic mapping: cutoff = min * (max/min) ^ dial_normalized
            self.lpf_cutoff_hz = min_cutoff * (max_cutoff / min_cutoff) ** dial_normalized
        
        # Calculate biquad filter coefficients for low-pass filter with resonance
        if self.filter_mode != "none" and self.audio_sample_rate and self.audio_sample_rate > 0:
            self._calculate_biquad_coefficients()
        else:
            # Pass-through coefficients
            self.lpf_b0 = 1.0
            self.lpf_b1 = 0.0
            self.lpf_b2 = 0.0
            self.lpf_a1 = 0.0
            self.lpf_a2 = 0.0
        
        # Reset filter state when cutoff or Q changes
        self.lpf_x1 = 0.0
        self.lpf_x2 = 0.0
        self.lpf_y1 = 0.0
        self.lpf_y2 = 0.0
    
    def _calculate_biquad_coefficients(self):
        """Calculate biquad low-pass filter coefficients with resonance."""
        # Standard biquad low-pass filter design
        # Based on RBJ Audio EQ Cookbook formulas
        
        fc = self.lpf_cutoff_hz
        fs = self.audio_sample_rate
        Q = self.resonance_q
        
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
    
    def _update_shelf_coefficients(self):
        """Calculate high-shelf biquad filter coefficients."""
        # High-shelf filter design based on RBJ Audio EQ Cookbook formulas
        
        if self.audio_sample_rate is None or self.audio_sample_rate <= 0:
            # Pass-through coefficients
            self.shelf_b0 = 1.0
            self.shelf_b1 = 0.0
            self.shelf_b2 = 0.0
            self.shelf_a1 = 0.0
            self.shelf_a2 = 0.0
            return
        
        fc = self.shelf_frequency_hz
        fs = self.audio_sample_rate
        gain_db = self.shelf_gain_db
        
        # Convert gain from dB to linear
        A = 10.0 ** (gain_db / 40.0)  # sqrt of gain for shelf filters
        S = 1.0  # Shelf slope parameter (1.0 = standard shelf)
        
        # Normalized frequency
        w = 2.0 * math.pi * fc / fs
        
        # Pre-warping for bilinear transform
        k = math.tan(w / 2.0)
        
        # Calculate intermediate values
        k2 = k * k
        kS = k * S
        k2S = k2 * S
        
        # High-shelf coefficients
        if gain_db > 0:
            # Boost
            norm = 1.0 / (1.0 + kS + k2)
            self.shelf_b0 = A * (1.0 + kS + k2) * norm
            self.shelf_b1 = A * 2.0 * (k2 - 1.0) * norm
            self.shelf_b2 = A * (1.0 - kS + k2) * norm
            self.shelf_a1 = 2.0 * (k2 - 1.0) * norm
            self.shelf_a2 = (1.0 - kS + k2) * norm
        else:
            # Cut
            norm = 1.0 / (A + kS + A * k2)
            self.shelf_b0 = (1.0 + kS + k2) * norm
            self.shelf_b1 = 2.0 * (k2 - 1.0) * norm
            self.shelf_b2 = (1.0 - kS + k2) * norm
            self.shelf_a1 = 2.0 * (A * k2 - 1.0) * norm
            self.shelf_a2 = (A - kS + A * k2) * norm
        
        # Reset shelf filter state when coefficients change
        self.shelf_x1 = 0.0
        self.shelf_x2 = 0.0
        self.shelf_y1 = 0.0
        self.shelf_y2 = 0.0
    
    def _init_ui(self):
        """Initialize the UI."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title = QLabel("Timbre Test - Brightness Control")
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
        
        # Filter mode radio buttons
        mode_layout = QVBoxLayout()
        mode_layout.setSpacing(10)
        
        mode_label = QLabel("Filter Mode:")
        mode_label.setFont(QFont("Arial", 12, QFont.Bold))
        mode_layout.addWidget(mode_label)
        
        self.mode_button_group = QButtonGroup(self)
        
        radio_layout = QHBoxLayout()
        
        self.none_radio = QRadioButton("None")
        self.none_radio.setFont(QFont("Arial", 11))
        self.none_radio.toggled.connect(self._on_filter_mode_changed)
        self.mode_button_group.addButton(self.none_radio, 0)
        radio_layout.addWidget(self.none_radio)
        
        self.linear_radio = QRadioButton("Linear")
        self.linear_radio.setFont(QFont("Arial", 11))
        self.linear_radio.setChecked(True)  # Default to linear
        self.linear_radio.toggled.connect(self._on_filter_mode_changed)
        self.mode_button_group.addButton(self.linear_radio, 1)
        radio_layout.addWidget(self.linear_radio)
        
        self.log_radio = QRadioButton("Log")
        self.log_radio.setFont(QFont("Arial", 11))
        self.log_radio.toggled.connect(self._on_filter_mode_changed)
        self.mode_button_group.addButton(self.log_radio, 2)
        radio_layout.addWidget(self.log_radio)
        
        radio_layout.addStretch()
        mode_layout.addLayout(radio_layout)
        layout.addLayout(mode_layout)
        
        # Brightness slider
        brightness_layout = QVBoxLayout()
        brightness_layout.setSpacing(10)
        
        brightness_label = QLabel("Brightness:")
        brightness_label.setFont(QFont("Arial", 12, QFont.Bold))
        brightness_layout.addWidget(brightness_label)
        
        slider_layout = QHBoxLayout()
        
        min_label = QLabel("-5")
        min_label.setFont(QFont("Arial", 11))
        slider_layout.addWidget(min_label)
        
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setMinimum(-50)  # -5.0 * 10 for 0.1 precision
        self.brightness_slider.setMaximum(50)   # +5.0 * 10
        self.brightness_slider.setValue(0)      # Default to 0
        self.brightness_slider.setTickPosition(QSlider.TicksBelow)
        self.brightness_slider.setTickInterval(10)  # Tick every 1.0
        self.brightness_slider.valueChanged.connect(self._on_brightness_changed)
        slider_layout.addWidget(self.brightness_slider, 1)
        
        max_label = QLabel("+5")
        max_label.setFont(QFont("Arial", 11))
        slider_layout.addWidget(max_label)
        
        brightness_layout.addLayout(slider_layout)
        
        # Resonance/Q slider
        resonance_layout = QVBoxLayout()
        resonance_layout.setSpacing(10)
        
        resonance_label = QLabel("Resonance (Q):")
        resonance_label.setFont(QFont("Arial", 12, QFont.Bold))
        resonance_layout.addWidget(resonance_label)
        
        q_slider_layout = QHBoxLayout()
        
        q_min_label = QLabel("0.1")
        q_min_label.setFont(QFont("Arial", 11))
        q_slider_layout.addWidget(q_min_label)
        
        self.resonance_slider = QSlider(Qt.Horizontal)
        self.resonance_slider.setMinimum(10)   # 0.1 * 100 for 0.01 precision
        self.resonance_slider.setMaximum(1000) # 10.0 * 100
        self.resonance_slider.setValue(71)     # Default to 0.707 (Butterworth)
        self.resonance_slider.setTickPosition(QSlider.TicksBelow)
        self.resonance_slider.setTickInterval(100)  # Tick every 1.0
        self.resonance_slider.valueChanged.connect(self._on_resonance_changed)
        q_slider_layout.addWidget(self.resonance_slider, 1)
        
        q_max_label = QLabel("10.0")
        q_max_label.setFont(QFont("Arial", 11))
        q_slider_layout.addWidget(q_max_label)
        
        resonance_layout.addLayout(q_slider_layout)
        layout.addLayout(resonance_layout)
        
        # High-shelf EQ slider
        shelf_layout = QVBoxLayout()
        shelf_layout.setSpacing(10)
        
        shelf_label = QLabel("High-Shelf Gain:")
        shelf_label.setFont(QFont("Arial", 12, QFont.Bold))
        shelf_layout.addWidget(shelf_label)
        
        shelf_slider_layout = QHBoxLayout()
        
        shelf_min_label = QLabel("-6 dB")
        shelf_min_label.setFont(QFont("Arial", 11))
        shelf_slider_layout.addWidget(shelf_min_label)
        
        self.shelf_slider = QSlider(Qt.Horizontal)
        self.shelf_slider.setMinimum(-60)  # -6.0 dB * 10 for 0.1 precision
        self.shelf_slider.setMaximum(60)   # +6.0 dB * 10
        self.shelf_slider.setValue(0)       # Default to 0 dB (no shelf)
        self.shelf_slider.setTickPosition(QSlider.TicksBelow)
        self.shelf_slider.setTickInterval(10)  # Tick every 1.0 dB
        self.shelf_slider.valueChanged.connect(self._on_shelf_changed)
        shelf_slider_layout.addWidget(self.shelf_slider, 1)
        
        shelf_max_label = QLabel("+6 dB")
        shelf_max_label.setFont(QFont("Arial", 11))
        shelf_slider_layout.addWidget(shelf_max_label)
        
        shelf_layout.addLayout(shelf_slider_layout)
        layout.addLayout(shelf_layout)
        
        # Brightness value and cutoff frequency display
        self.brightness_display = QLabel("Brightness: 0.0  |  Cutoff: 500.0 Hz  |  Q: 0.707  |  Shelf: 0.0 dB @ 3.5 kHz")
        self.brightness_display.setFont(QFont("Arial", 11))
        self.brightness_display.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        brightness_layout.addWidget(self.brightness_display)
        
        layout.addLayout(brightness_layout)
        
        # Modulation Effects Section
        effects_label = QLabel("Modulation Effects:")
        effects_label.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(effects_label)
        
        # Tremolo controls
        tremolo_layout = QVBoxLayout()
        tremolo_header = QHBoxLayout()
        self.tremolo_checkbox = QCheckBox("Tremolo (Amplitude Modulation)")
        self.tremolo_checkbox.setFont(QFont("Arial", 12, QFont.Bold))
        self.tremolo_checkbox.toggled.connect(self._on_tremolo_toggled)
        tremolo_header.addWidget(self.tremolo_checkbox)
        tremolo_header.addStretch()
        tremolo_layout.addLayout(tremolo_header)
        
        tremolo_controls = QHBoxLayout()
        tremolo_controls.addWidget(QLabel("Rate:"))
        self.tremolo_rate_slider = QSlider(Qt.Horizontal)
        self.tremolo_rate_slider.setMinimum(10)  # 0.1 Hz * 100
        self.tremolo_rate_slider.setMaximum(1000)  # 10.0 Hz * 100
        self.tremolo_rate_slider.setValue(500)  # 5.0 Hz default
        self.tremolo_rate_slider.valueChanged.connect(self._on_tremolo_rate_changed)
        tremolo_controls.addWidget(self.tremolo_rate_slider)
        self.tremolo_rate_label = QLabel("5.0 Hz")
        self.tremolo_rate_label.setMinimumWidth(60)
        tremolo_controls.addWidget(self.tremolo_rate_label)
        
        tremolo_controls.addWidget(QLabel("Depth:"))
        self.tremolo_depth_slider = QSlider(Qt.Horizontal)
        self.tremolo_depth_slider.setMinimum(0)  # 0%
        self.tremolo_depth_slider.setMaximum(1000)  # 100% * 10
        self.tremolo_depth_slider.setValue(0)
        self.tremolo_depth_slider.valueChanged.connect(self._on_tremolo_depth_changed)
        tremolo_controls.addWidget(self.tremolo_depth_slider)
        self.tremolo_depth_label = QLabel("0%")
        self.tremolo_depth_label.setMinimumWidth(50)
        tremolo_controls.addWidget(self.tremolo_depth_label)
        tremolo_layout.addLayout(tremolo_controls)
        layout.addLayout(tremolo_layout)
        
        # Vibrato controls
        vibrato_layout = QVBoxLayout()
        vibrato_header = QHBoxLayout()
        self.vibrato_checkbox = QCheckBox("Vibrato (Pitch Modulation)")
        self.vibrato_checkbox.setFont(QFont("Arial", 12, QFont.Bold))
        self.vibrato_checkbox.toggled.connect(self._on_vibrato_toggled)
        vibrato_header.addWidget(self.vibrato_checkbox)
        vibrato_header.addStretch()
        vibrato_layout.addLayout(vibrato_header)
        
        vibrato_controls = QHBoxLayout()
        vibrato_controls.addWidget(QLabel("Rate:"))
        self.vibrato_rate_slider = QSlider(Qt.Horizontal)
        self.vibrato_rate_slider.setMinimum(40)  # 0.4 Hz * 100
        self.vibrato_rate_slider.setMaximum(800)  # 8.0 Hz * 100
        self.vibrato_rate_slider.setValue(600)  # 6.0 Hz default
        self.vibrato_rate_slider.valueChanged.connect(self._on_vibrato_rate_changed)
        vibrato_controls.addWidget(self.vibrato_rate_slider)
        self.vibrato_rate_label = QLabel("6.0 Hz")
        self.vibrato_rate_label.setMinimumWidth(60)
        vibrato_controls.addWidget(self.vibrato_rate_label)
        
        vibrato_controls.addWidget(QLabel("Depth:"))
        self.vibrato_depth_slider = QSlider(Qt.Horizontal)
        self.vibrato_depth_slider.setMinimum(0)  # 0 cents
        self.vibrato_depth_slider.setMaximum(500)  # 50 cents * 10
        self.vibrato_depth_slider.setValue(0)
        self.vibrato_depth_slider.valueChanged.connect(self._on_vibrato_depth_changed)
        vibrato_controls.addWidget(self.vibrato_depth_slider)
        self.vibrato_depth_label = QLabel("0 cents")
        self.vibrato_depth_label.setMinimumWidth(70)
        vibrato_controls.addWidget(self.vibrato_depth_label)
        vibrato_layout.addLayout(vibrato_controls)
        layout.addLayout(vibrato_layout)
        
        # Chorus controls
        chorus_layout = QVBoxLayout()
        chorus_header = QHBoxLayout()
        self.chorus_checkbox = QCheckBox("Chorus")
        self.chorus_checkbox.setFont(QFont("Arial", 12, QFont.Bold))
        self.chorus_checkbox.toggled.connect(self._on_chorus_toggled)
        chorus_header.addWidget(self.chorus_checkbox)
        chorus_header.addStretch()
        chorus_layout.addLayout(chorus_header)
        
        chorus_controls = QHBoxLayout()
        chorus_controls.addWidget(QLabel("Rate:"))
        self.chorus_rate_slider = QSlider(Qt.Horizontal)
        self.chorus_rate_slider.setMinimum(10)  # 0.1 Hz * 100
        self.chorus_rate_slider.setMaximum(200)  # 2.0 Hz * 100
        self.chorus_rate_slider.setValue(50)  # 0.5 Hz default
        self.chorus_rate_slider.valueChanged.connect(self._on_chorus_rate_changed)
        chorus_controls.addWidget(self.chorus_rate_slider)
        self.chorus_rate_label = QLabel("0.5 Hz")
        self.chorus_rate_label.setMinimumWidth(60)
        chorus_controls.addWidget(self.chorus_rate_label)
        
        chorus_controls.addWidget(QLabel("Depth:"))
        self.chorus_depth_slider = QSlider(Qt.Horizontal)
        self.chorus_depth_slider.setMinimum(0)  # 0 ms * 10
        self.chorus_depth_slider.setMaximum(300)  # 30 ms * 10
        self.chorus_depth_slider.setValue(100)  # 10 ms default
        self.chorus_depth_slider.valueChanged.connect(self._on_chorus_depth_changed)
        chorus_controls.addWidget(self.chorus_depth_slider)
        self.chorus_depth_label = QLabel("10.0 ms")
        self.chorus_depth_label.setMinimumWidth(70)
        chorus_controls.addWidget(self.chorus_depth_label)
        
        chorus_controls.addWidget(QLabel("Mix:"))
        self.chorus_mix_slider = QSlider(Qt.Horizontal)
        self.chorus_mix_slider.setMinimum(0)  # 0% * 10
        self.chorus_mix_slider.setMaximum(1000)  # 100% * 10
        self.chorus_mix_slider.setValue(500)  # 50% default
        self.chorus_mix_slider.valueChanged.connect(self._on_chorus_mix_changed)
        chorus_controls.addWidget(self.chorus_mix_slider)
        self.chorus_mix_label = QLabel("50%")
        self.chorus_mix_label.setMinimumWidth(50)
        chorus_controls.addWidget(self.chorus_mix_label)
        chorus_layout.addLayout(chorus_controls)
        layout.addLayout(chorus_layout)
        
        # Flanger controls
        flanger_layout = QVBoxLayout()
        flanger_header = QHBoxLayout()
        self.flanger_checkbox = QCheckBox("Flanger")
        self.flanger_checkbox.setFont(QFont("Arial", 12, QFont.Bold))
        self.flanger_checkbox.toggled.connect(self._on_flanger_toggled)
        flanger_header.addWidget(self.flanger_checkbox)
        flanger_header.addStretch()
        flanger_layout.addLayout(flanger_header)
        
        flanger_controls = QHBoxLayout()
        flanger_controls.addWidget(QLabel("Rate:"))
        self.flanger_rate_slider = QSlider(Qt.Horizontal)
        self.flanger_rate_slider.setMinimum(10)  # 0.1 Hz * 100
        self.flanger_rate_slider.setMaximum(100)  # 1.0 Hz * 100
        self.flanger_rate_slider.setValue(30)  # 0.3 Hz default
        self.flanger_rate_slider.valueChanged.connect(self._on_flanger_rate_changed)
        flanger_controls.addWidget(self.flanger_rate_slider)
        self.flanger_rate_label = QLabel("0.3 Hz")
        self.flanger_rate_label.setMinimumWidth(60)
        flanger_controls.addWidget(self.flanger_rate_label)
        
        flanger_controls.addWidget(QLabel("Depth:"))
        self.flanger_depth_slider = QSlider(Qt.Horizontal)
        self.flanger_depth_slider.setMinimum(0)  # 0 ms * 10
        self.flanger_depth_slider.setMaximum(100)  # 10 ms * 10
        self.flanger_depth_slider.setValue(20)  # 2 ms default
        self.flanger_depth_slider.valueChanged.connect(self._on_flanger_depth_changed)
        flanger_controls.addWidget(self.flanger_depth_slider)
        self.flanger_depth_label = QLabel("2.0 ms")
        self.flanger_depth_label.setMinimumWidth(70)
        flanger_controls.addWidget(self.flanger_depth_label)
        
        flanger_controls.addWidget(QLabel("Feedback:"))
        self.flanger_feedback_slider = QSlider(Qt.Horizontal)
        self.flanger_feedback_slider.setMinimum(0)  # 0% * 10
        self.flanger_feedback_slider.setMaximum(500)  # 50% * 10
        self.flanger_feedback_slider.setValue(300)  # 30% default
        self.flanger_feedback_slider.valueChanged.connect(self._on_flanger_feedback_changed)
        flanger_controls.addWidget(self.flanger_feedback_slider)
        self.flanger_feedback_label = QLabel("30%")
        self.flanger_feedback_label.setMinimumWidth(50)
        flanger_controls.addWidget(self.flanger_feedback_label)
        flanger_layout.addLayout(flanger_controls)
        layout.addLayout(flanger_layout)
        
        # Phaser controls
        phaser_layout = QVBoxLayout()
        phaser_header = QHBoxLayout()
        self.phaser_checkbox = QCheckBox("Phaser")
        self.phaser_checkbox.setFont(QFont("Arial", 12, QFont.Bold))
        self.phaser_checkbox.toggled.connect(self._on_phaser_toggled)
        phaser_header.addWidget(self.phaser_checkbox)
        phaser_header.addStretch()
        phaser_layout.addLayout(phaser_header)
        
        phaser_controls = QHBoxLayout()
        phaser_controls.addWidget(QLabel("Rate:"))
        self.phaser_rate_slider = QSlider(Qt.Horizontal)
        self.phaser_rate_slider.setMinimum(10)  # 0.1 Hz * 100
        self.phaser_rate_slider.setMaximum(200)  # 2.0 Hz * 100
        self.phaser_rate_slider.setValue(50)  # 0.5 Hz default
        self.phaser_rate_slider.valueChanged.connect(self._on_phaser_rate_changed)
        phaser_controls.addWidget(self.phaser_rate_slider)
        self.phaser_rate_label = QLabel("0.5 Hz")
        self.phaser_rate_label.setMinimumWidth(60)
        phaser_controls.addWidget(self.phaser_rate_label)
        
        phaser_controls.addWidget(QLabel("Depth:"))
        self.phaser_depth_slider = QSlider(Qt.Horizontal)
        self.phaser_depth_slider.setMinimum(0)  # 0% * 10
        self.phaser_depth_slider.setMaximum(1000)  # 100% * 10
        self.phaser_depth_slider.setValue(800)  # 80% default
        self.phaser_depth_slider.valueChanged.connect(self._on_phaser_depth_changed)
        phaser_controls.addWidget(self.phaser_depth_slider)
        self.phaser_depth_label = QLabel("80%")
        self.phaser_depth_label.setMinimumWidth(50)
        phaser_controls.addWidget(self.phaser_depth_label)
        phaser_layout.addLayout(phaser_controls)
        layout.addLayout(phaser_layout)
        
        layout.addStretch()
        
        # Initialize display after UI is created
        self._update_display()
    
    def _on_filter_mode_changed(self):
        """Handle filter mode radio button change."""
        if self.none_radio.isChecked():
            self.filter_mode = "none"
        elif self.linear_radio.isChecked():
            self.filter_mode = "linear"
        elif self.log_radio.isChecked():
            self.filter_mode = "log"
        
        self._update_lpf_cutoff()
        self._update_display()
    
    def _on_resonance_changed(self, value):
        """Handle resonance/Q slider change."""
        self.resonance_q = value / 100.0  # Convert from slider units to actual value
        self._update_lpf_cutoff()
        self._update_display()
    
    def _on_shelf_changed(self, value):
        """Handle high-shelf gain slider change."""
        self.shelf_gain_db = value / 10.0  # Convert from slider units to actual value
        self._update_shelf_coefficients()
        self._update_display()
    
    def _on_brightness_changed(self, value):
        """Handle brightness slider change."""
        self.brightness = value / 10.0  # Convert from slider units to actual value
        self._update_lpf_cutoff()
        self._update_display()
    
    # Tremolo handlers
    def _on_tremolo_toggled(self, checked):
        """Handle tremolo checkbox toggle."""
        self.tremolo_enabled = checked
        if not checked:
            self.tremolo_phase = 0.0
    
    def _on_tremolo_rate_changed(self, value):
        """Handle tremolo rate slider change."""
        self.tremolo_rate_hz = value / 100.0
        self.tremolo_rate_label.setText(f"{self.tremolo_rate_hz:.1f} Hz")
    
    def _on_tremolo_depth_changed(self, value):
        """Handle tremolo depth slider change."""
        self.tremolo_depth = value / 1000.0  # 0.0 to 1.0
        self.tremolo_depth_label.setText(f"{self.tremolo_depth * 100:.0f}%")
    
    # Vibrato handlers
    def _on_vibrato_toggled(self, checked):
        """Handle vibrato checkbox toggle."""
        self.vibrato_enabled = checked
        if not checked:
            self.vibrato_phase = 0.0
    
    def _on_vibrato_rate_changed(self, value):
        """Handle vibrato rate slider change."""
        self.vibrato_rate_hz = value / 100.0
        self.vibrato_rate_label.setText(f"{self.vibrato_rate_hz:.1f} Hz")
    
    def _on_vibrato_depth_changed(self, value):
        """Handle vibrato depth slider change."""
        self.vibrato_depth_cents = value / 10.0  # 0 to 50 cents
        self.vibrato_depth_label.setText(f"{self.vibrato_depth_cents:.0f} cents")
    
    # Chorus handlers
    def _on_chorus_toggled(self, checked):
        """Handle chorus checkbox toggle."""
        self.chorus_enabled = checked
        if not checked:
            self.chorus_phase = 0.0
            self.chorus_buffer.fill(0)
            self.chorus_write_pos = 0
    
    def _on_chorus_rate_changed(self, value):
        """Handle chorus rate slider change."""
        self.chorus_rate_hz = value / 100.0
        self.chorus_rate_label.setText(f"{self.chorus_rate_hz:.2f} Hz")
    
    def _on_chorus_depth_changed(self, value):
        """Handle chorus depth slider change."""
        self.chorus_depth_ms = value / 10.0
        self.chorus_depth_label.setText(f"{self.chorus_depth_ms:.1f} ms")
    
    def _on_chorus_mix_changed(self, value):
        """Handle chorus mix slider change."""
        self.chorus_mix = value / 1000.0
        self.chorus_mix_label.setText(f"{self.chorus_mix * 100:.0f}%")
    
    # Flanger handlers
    def _on_flanger_toggled(self, checked):
        """Handle flanger checkbox toggle."""
        self.flanger_enabled = checked
        if not checked:
            self.flanger_phase = 0.0
            self.flanger_buffer.fill(0)
            self.flanger_write_pos = 0
    
    def _on_flanger_rate_changed(self, value):
        """Handle flanger rate slider change."""
        self.flanger_rate_hz = value / 100.0
        self.flanger_rate_label.setText(f"{self.flanger_rate_hz:.2f} Hz")
    
    def _on_flanger_depth_changed(self, value):
        """Handle flanger depth slider change."""
        self.flanger_depth_ms = value / 10.0
        self.flanger_depth_label.setText(f"{self.flanger_depth_ms:.1f} ms")
    
    def _on_flanger_feedback_changed(self, value):
        """Handle flanger feedback slider change."""
        self.flanger_feedback = value / 1000.0
        self.flanger_feedback_label.setText(f"{self.flanger_feedback * 100:.0f}%")
    
    # Phaser handlers
    def _on_phaser_toggled(self, checked):
        """Handle phaser checkbox toggle."""
        self.phaser_enabled = checked
        if not checked:
            self.phaser_phase = 0.0
            # Reset all-pass filter states
            for i in range(self.phaser_stages):
                self.phaser_ap_x1[i] = 0.0
                self.phaser_ap_x2[i] = 0.0
                self.phaser_ap_y1[i] = 0.0
                self.phaser_ap_y2[i] = 0.0
    
    def _on_phaser_rate_changed(self, value):
        """Handle phaser rate slider change."""
        self.phaser_rate_hz = value / 100.0
        self.phaser_rate_label.setText(f"{self.phaser_rate_hz:.2f} Hz")
    
    def _on_phaser_depth_changed(self, value):
        """Handle phaser depth slider change."""
        self.phaser_depth = value / 1000.0
        self.phaser_depth_label.setText(f"{self.phaser_depth * 100:.0f}%")
    
    def _update_display(self):
        """Update the brightness, cutoff, Q, and shelf display."""
        shelf_text = f"Shelf: {self.shelf_gain_db:+.1f} dB @ {self.shelf_frequency_hz:.0f} Hz"
        if self.filter_mode == "none":
            self.brightness_display.setText(
                f"Brightness: {self.brightness:.1f}  |  Filter: None (no LPF)  |  Q: {self.resonance_q:.2f}  |  {shelf_text}"
            )
        else:
            self.brightness_display.setText(
                f"Brightness: {self.brightness:.1f}  |  Cutoff: {self.lpf_cutoff_hz:.1f} Hz  |  Q: {self.resonance_q:.2f}  |  {shelf_text}"
            )
    
    def _audio_callback(self, outdata, frames, time, status):
        """Audio callback for streaming with real-time filtering and modulation effects."""
        if status:
            print(f"Audio status: {status}")
        
        if not self.is_playing or self.audio_data is None:
            outdata.fill(0)
            return
        
        # Calculate how many samples we need
        samples_needed = frames
        output = np.zeros((samples_needed,), dtype=np.float32)
        
        fs = self.audio_sample_rate
        dt = 1.0 / fs  # Time step per sample
        
        # Read from audio data (with looping)
        for i in range(samples_needed):
            # Update LFO phases for all modulation effects
            if self.tremolo_enabled:
                self.tremolo_phase += 2.0 * math.pi * self.tremolo_rate_hz * dt
                if self.tremolo_phase > 2.0 * math.pi:
                    self.tremolo_phase -= 2.0 * math.pi
            
            if self.vibrato_enabled:
                self.vibrato_phase += 2.0 * math.pi * self.vibrato_rate_hz * dt
                if self.vibrato_phase > 2.0 * math.pi:
                    self.vibrato_phase -= 2.0 * math.pi
            
            if self.chorus_enabled:
                self.chorus_phase += 2.0 * math.pi * self.chorus_rate_hz * dt
                if self.chorus_phase > 2.0 * math.pi:
                    self.chorus_phase -= 2.0 * math.pi
            
            if self.flanger_enabled:
                self.flanger_phase += 2.0 * math.pi * self.flanger_rate_hz * dt
                if self.flanger_phase > 2.0 * math.pi:
                    self.flanger_phase -= 2.0 * math.pi
            
            if self.phaser_enabled:
                self.phaser_phase += 2.0 * math.pi * self.phaser_rate_hz * dt
                if self.phaser_phase > 2.0 * math.pi:
                    self.phaser_phase -= 2.0 * math.pi
            
            # Get base sample position (with vibrato pitch modulation)
            base_pos = self.audio_position
            if self.vibrato_enabled and self.vibrato_depth_cents > 0:
                # Calculate pitch offset in samples
                # cents to ratio: ratio = 2^(cents/1200)
                pitch_ratio = 2.0 ** (self.vibrato_depth_cents * math.sin(self.vibrato_phase) / 1200.0)
                # Adjust read position (fractional)
                vibrato_offset = (pitch_ratio - 1.0) * 0.1  # Small offset to avoid too much movement
                read_pos = base_pos + vibrato_offset
            else:
                read_pos = base_pos
            
            # Handle looping and get sample (with linear interpolation for vibrato)
            if read_pos >= len(self.audio_data):
                read_pos = read_pos % len(self.audio_data)
            if read_pos < 0:
                read_pos = len(self.audio_data) + (read_pos % len(self.audio_data))
            
            # Linear interpolation for fractional positions
            if self.vibrato_enabled and self.vibrato_depth_cents > 0:
                pos_int = int(read_pos)
                pos_frac = read_pos - pos_int
                pos_int_next = (pos_int + 1) % len(self.audio_data)
                sample = self.audio_data[pos_int] * (1.0 - pos_frac) + self.audio_data[pos_int_next] * pos_frac
            else:
                sample = self.audio_data[int(base_pos)]
            
            # Apply biquad low-pass filter if enabled (and not "none" mode)
            if self.filter_mode != "none":
                # Low-pass biquad filter: y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]
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
                
                filtered_sample = lpf_filtered
            else:
                # No LPF - pass through raw sample
                filtered_sample = sample
            
            # Apply high-shelf EQ (always active if gain != 0)
            if abs(self.shelf_gain_db) > 0.01:  # Only apply if gain is significant
                # High-shelf biquad filter
                shelf_filtered = (self.shelf_b0 * filtered_sample + 
                                self.shelf_b1 * self.shelf_x1 + 
                                self.shelf_b2 * self.shelf_x2 - 
                                self.shelf_a1 * self.shelf_y1 - 
                                self.shelf_a2 * self.shelf_y2)
                
                # Update shelf filter state
                self.shelf_x2 = self.shelf_x1
                self.shelf_x1 = filtered_sample
                self.shelf_y2 = self.shelf_y1
                self.shelf_y1 = shelf_filtered
                
                processed_sample = shelf_filtered
            else:
                # No shelf - pass through LPF result
                processed_sample = filtered_sample
            
            # Apply Phaser (before delay-based effects)
            if self.phaser_enabled:
                # Calculate modulated frequency for all-pass filters
                lfo_value = math.sin(self.phaser_phase)
                freq_mod = self.phaser_min_freq + (self.phaser_max_freq - self.phaser_min_freq) * (0.5 + 0.5 * lfo_value * self.phaser_depth)
                
                # Process through cascade of all-pass filters
                phaser_sample = processed_sample
                for stage in range(self.phaser_stages):
                    # Calculate all-pass filter coefficients for this stage
                    w = 2.0 * math.pi * freq_mod / fs
                    k = math.tan(w / 2.0)
                    k2 = k * k
                    norm = 1.0 / (1.0 + k)
                    
                    # All-pass filter coefficients
                    ap_b0 = (1.0 - k) * norm
                    ap_b1 = -1.0
                    ap_a1 = -ap_b0
                    
                    # Apply all-pass filter
                    ap_out = (ap_b0 * phaser_sample + 
                             ap_b1 * self.phaser_ap_x1[stage] - 
                             ap_a1 * self.phaser_ap_y1[stage])
                    
                    # Update all-pass filter state
                    self.phaser_ap_x1[stage] = phaser_sample
                    self.phaser_ap_y1[stage] = ap_out
                    
                    phaser_sample = ap_out
                
                # Mix phaser (50/50 dry/wet)
                processed_sample = processed_sample * 0.5 + phaser_sample * 0.5
            
            # Apply Chorus
            if self.chorus_enabled:
                # Calculate delay time with LFO modulation
                lfo_value = math.sin(self.chorus_phase)
                delay_samples = int((self.chorus_delay_ms + self.chorus_depth_ms * lfo_value) / 1000.0 * fs)
                delay_samples = max(0, min(delay_samples, self.chorus_buffer_size - 1))
                
                # Read from delay buffer
                read_pos = (self.chorus_write_pos - delay_samples) % self.chorus_buffer_size
                delayed_sample = self.chorus_buffer[read_pos]
                
                # Write current sample to buffer
                self.chorus_buffer[self.chorus_write_pos] = processed_sample
                self.chorus_write_pos = (self.chorus_write_pos + 1) % self.chorus_buffer_size
                
                # Mix dry and wet
                processed_sample = processed_sample * (1.0 - self.chorus_mix) + delayed_sample * self.chorus_mix
            
            # Apply Flanger
            if self.flanger_enabled:
                # Calculate delay time with LFO modulation
                lfo_value = math.sin(self.flanger_phase)
                delay_samples = int((self.flanger_delay_ms + self.flanger_depth_ms * lfo_value) / 1000.0 * fs)
                delay_samples = max(1, min(delay_samples, self.flanger_buffer_size - 1))
                
                # Read from delay buffer
                read_pos = (self.flanger_write_pos - delay_samples) % self.flanger_buffer_size
                delayed_sample = self.flanger_buffer[read_pos]
                
                # Write current sample + feedback to buffer
                self.flanger_buffer[self.flanger_write_pos] = processed_sample + delayed_sample * self.flanger_feedback
                self.flanger_write_pos = (self.flanger_write_pos + 1) % self.flanger_buffer_size
                
                # Mix dry and wet (50/50)
                processed_sample = processed_sample * 0.5 + delayed_sample * 0.5
            
            # Apply Tremolo (amplitude modulation) - last in chain
            if self.tremolo_enabled:
                lfo_value = math.sin(self.tremolo_phase)
                tremolo_gain = 1.0 - (self.tremolo_depth * (1.0 + lfo_value) / 2.0)  # 0 to 1.0
                processed_sample = processed_sample * tremolo_gain
            
            output[i] = processed_sample
            
            # Update base audio position
            self.audio_position = (self.audio_position + 1) % len(self.audio_data)
        
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
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            self.audio_position = 0
            # Reset biquad filter states
            self.lpf_x1 = 0.0
            self.lpf_x2 = 0.0
            self.lpf_y1 = 0.0
            self.lpf_y2 = 0.0
            self.shelf_x1 = 0.0
            self.shelf_x2 = 0.0
            self.shelf_y1 = 0.0
            self.shelf_y2 = 0.0
            # Reset modulation effect phases
            self.tremolo_phase = 0.0
            self.vibrato_phase = 0.0
            self.chorus_phase = 0.0
            self.flanger_phase = 0.0
            self.phaser_phase = 0.0
            # Reset delay buffers
            if self.chorus_buffer is not None:
                self.chorus_buffer.fill(0)
            if self.flanger_buffer is not None:
                self.flanger_buffer.fill(0)
            self.chorus_write_pos = 0
            self.flanger_write_pos = 0
            # Reset phaser all-pass states
            for i in range(self.phaser_stages):
                self.phaser_ap_x1[i] = 0.0
                self.phaser_ap_x2[i] = 0.0
                self.phaser_ap_y1[i] = 0.0
                self.phaser_ap_y2[i] = 0.0
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
            # Reset biquad filter states
            self.lpf_x1 = 0.0
            self.lpf_x2 = 0.0
            self.lpf_y1 = 0.0
            self.lpf_y2 = 0.0
            self.shelf_x1 = 0.0
            self.shelf_x2 = 0.0
            self.shelf_y1 = 0.0
            self.shelf_y2 = 0.0
            # Reset modulation effect phases
            self.tremolo_phase = 0.0
            self.vibrato_phase = 0.0
            self.chorus_phase = 0.0
            self.flanger_phase = 0.0
            self.phaser_phase = 0.0
            # Reset delay buffers
            if self.chorus_buffer is not None:
                self.chorus_buffer.fill(0)
            if self.flanger_buffer is not None:
                self.flanger_buffer.fill(0)
            self.chorus_write_pos = 0
            self.flanger_write_pos = 0
            # Reset phaser all-pass states
            for i in range(self.phaser_stages):
                self.phaser_ap_x1[i] = 0.0
                self.phaser_ap_x2[i] = 0.0
                self.phaser_ap_y1[i] = 0.0
                self.phaser_ap_y2[i] = 0.0
            
            try:
                self.stream = sd.OutputStream(
                    samplerate=self.audio_sample_rate,
                    channels=1,
                    dtype=np.float32,
                    callback=self._audio_callback,
                    blocksize=512
                )
                self.stream.start()
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
    
    def closeEvent(self, event):
        """Handle window close - cleanup audio."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
        event.accept()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    window = TimbreTestWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
