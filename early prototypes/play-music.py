#!/usr/bin/env python3
"""Standalone test utility to play music/music.mp3 with a progress bar and live waveform."""

import sys
import threading
import numpy as np
import sounddevice as sd
import librosa
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QProgressBar,
    QLabel,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPainter, QColor, QPen


WAVEFORM_DISPLAY_POINTS = 800   # points drawn across the widget width
LIVE_WINDOW_SECONDS = 0.35      # rolling window of audio shown (seconds)


class WaveformWidget(QWidget):
    """Widget that draws a live, rolling waveform of the most recent audio output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = None   # 1D array of recent mono samples (oldest to newest)
        self.setMinimumHeight(80)
        self.setMinimumWidth(200)

    def set_live_samples(self, samples):
        """Update with the most recent audio samples (1D array). Left=older, right=newer."""
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
        mid_y = h / 2.0
        scale_y = (h / 2.0 - 4) * 0.95 * 5  # 5x amplitude for visibility
        painter.fillRect(0, 0, w, h, QColor(248, 248, 252))
        if self.samples is None or len(self.samples) < 2:
            painter.end()
            return
        n = len(self.samples)
        # Downsample to display points (max abs per bin for envelope)
        step = max(1, n // WAVEFORM_DISPLAY_POINTS)
        n_pts = min(WAVEFORM_DISPLAY_POINTS, (n + step - 1) // step)
        xs = []
        ys = []
        for i in range(n_pts):
            start = i * step
            end = min(start + step, n)
            if end > start:
                val = np.max(np.abs(self.samples[start:end]))
            else:
                val = 0.0
            x = (i / max(1, n_pts - 1)) * (w - 1) if n_pts > 1 else 0
            y = mid_y - val * scale_y
            ys.append(max(0, min(h, y)))  # clip to widget bounds
            xs.append(x)
        pen = QPen(QColor(80, 120, 180), 1)
        painter.setPen(pen)
        for i in range(len(xs) - 1):
            painter.drawLine(int(xs[i]), int(ys[i]), int(xs[i + 1]), int(ys[i + 1]))
        painter.end()


class MusicPlayer(QWidget):
    def __init__(self):
        super().__init__()
        self.audio_data = None
        self.audio_sample_rate = None
        self.audio_position = 0
        self.audio_stream = None
        self.is_playing = False
        # Ring buffer for live waveform (filled in audio callback, read in UI)
        self._live_buffer = None
        self._live_index = 0
        self._live_lock = threading.Lock()
        
        self.init_ui()
        self.load_audio()
    
    def init_ui(self):
        """Initialize the UI."""
        self.setWindowTitle("Music Player Test - music.mp3")
        self.setGeometry(100, 100, 500, 280)
        
        layout = QVBoxLayout()
        
        # Status label
        self.status_label = QLabel("Status: Not loaded")
        layout.addWidget(self.status_label)
        
        # Waveform display
        self.waveform_widget = WaveformWidget()
        layout.addWidget(self.waveform_widget)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Time label
        self.time_label = QLabel("Time: 0:00 / 0:00")
        layout.addWidget(self.time_label)
        
        # Control buttons
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_play)
        layout.addWidget(self.play_button)
        
        self.setLayout(layout)
        
        # Timer to update progress
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_progress)
        self.update_timer.start(100)  # Update every 100ms
    
    def load_audio(self):
        """Load the audio file."""
        audio_path = Path("music/music.mp3")
        
        if not audio_path.exists():
            self.status_label.setText(f"Error: Audio file not found: {audio_path}")
            self.status_label.setStyleSheet("color: red;")
            return
        
        try:
            self.status_label.setText("Loading audio file...")
            self.status_label.setStyleSheet("color: blue;")
            QApplication.processEvents()  # Update UI
            
            # Load audio file (mono, resampled to 44100 Hz if needed)
            self.audio_data, self.audio_sample_rate = librosa.load(
                str(audio_path),
                sr=44100,
                mono=True
            )
            
            duration_seconds = len(self.audio_data) / self.audio_sample_rate
            self.status_label.setText(
                f"Loaded: {len(self.audio_data)} samples, "
                f"{self.audio_sample_rate} Hz, "
                f"{duration_seconds:.2f} seconds"
            )
            self.status_label.setStyleSheet("color: green;")
            
            # Allocate ring buffer for live waveform (one window at current sample rate)
            buf_len = int(LIVE_WINDOW_SECONDS * self.audio_sample_rate)
            self._live_buffer = np.zeros(buf_len, dtype=np.float32)
            self._live_index = 0
            
            # Set progress bar maximum to duration in seconds (for display)
            self.progress_bar.setMaximum(int(duration_seconds * 100))  # 0.01s precision
            
            print(f"Successfully loaded audio file: {audio_path}")
            print(f"  Samples: {len(self.audio_data)}")
            print(f"  Sample rate: {self.audio_sample_rate} Hz")
            print(f"  Duration: {duration_seconds:.2f} seconds")
            
        except Exception as e:
            self.status_label.setText(f"Error loading audio: {e}")
            self.status_label.setStyleSheet("color: red;")
            print(f"Error loading audio file: {e}")
            import traceback
            traceback.print_exc()
            self.audio_data = None
    
    def toggle_play(self):
        """Toggle play/pause."""
        if self.audio_data is None:
            return
        
        if self.is_playing:
            self.stop_audio()
        else:
            self.start_audio()
    
    def start_audio(self):
        """Start the audio stream."""
        if self.audio_stream is not None:
            return  # Already started
        
        if self.audio_data is None:
            print("Error: Audio data not loaded")
            return
        
        def audio_callback(outdata, frames, time_info, status):
            try:
                if status:
                    print(f"Audio status: {status}")
                
                if self.audio_data is None:
                    outdata.fill(0)
                    return
                
                # Read audio chunk from file
                chunk = np.zeros(frames, dtype=np.float32)
                samples_read = 0
                
                while samples_read < frames:
                    remaining = frames - samples_read
                    available = len(self.audio_data) - self.audio_position
                    
                    if available > 0:
                        read_count = min(remaining, available)
                        chunk[samples_read:samples_read + read_count] = self.audio_data[
                            self.audio_position:self.audio_position + read_count
                        ]
                        self.audio_position += read_count
                        samples_read += read_count
                    
                    # Loop if we've reached the end
                    if self.audio_position >= len(self.audio_data):
                        self.audio_position = 0
                        # Stop when we loop (for testing, don't loop)
                        self.stop_audio()
                        return
                
                # Convert to stereo (mono to both channels)
                outdata[:, 0] = chunk
                outdata[:, 1] = chunk
                
                # Feed live waveform ring buffer (thread-safe)
                with self._live_lock:
                    if self._live_buffer is not None:
                        b = self._live_buffer
                        for i in range(frames):
                            b[self._live_index] = chunk[i]
                            self._live_index = (self._live_index + 1) % len(b)
                
            except Exception as e:
                print(f"Error in audio callback: {e}")
                import traceback
                traceback.print_exc()
                outdata.fill(0)
        
        try:
            self.audio_stream = sd.OutputStream(
                samplerate=self.audio_sample_rate,
                channels=2,
                blocksize=256,
                callback=audio_callback,
            )
            self.audio_stream.start()
            self.is_playing = True
            self.play_button.setText("Stop")
            print("Audio stream started successfully")
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            import traceback
            traceback.print_exc()
            self.audio_stream = None
            self.is_playing = False
    
    def stop_audio(self):
        """Stop the audio stream."""
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        self.is_playing = False
        self.play_button.setText("Play")
    
    def update_progress(self):
        """Update the progress bar and time label."""
        if self.audio_data is None or self.audio_sample_rate is None:
            return
        
        # Calculate current position in seconds
        current_seconds = self.audio_position / self.audio_sample_rate
        total_seconds = len(self.audio_data) / self.audio_sample_rate
        
        # Update progress bar (0-100 based on 0.01s precision)
        progress_value = int(current_seconds * 100)
        self.progress_bar.setValue(min(progress_value, int(total_seconds * 100)))
        
        # Update live waveform from ring buffer (oldest to newest order for left-to-right display)
        with self._live_lock:
            if self._live_buffer is not None and len(self._live_buffer) > 0:
                b = self._live_buffer
                idx = self._live_index
                # Copy in chronological order: oldest first (left), newest last (right)
                part_oldest = b[idx:].copy()   # from current write pos to end = oldest in buffer
                part_newest = b[:idx].copy()   # from start to write pos = newest
                self.waveform_widget.set_live_samples(np.concatenate([part_oldest, part_newest]))
        
        # Update time label
        current_min = int(current_seconds // 60)
        current_sec = int(current_seconds % 60)
        total_min = int(total_seconds // 60)
        total_sec = int(total_seconds % 60)
        self.time_label.setText(
            f"Time: {current_min}:{current_sec:02d} / {total_min}:{total_sec:02d}"
        )
    
    def closeEvent(self, event):
        """Handle window close event."""
        self.stop_audio()
        event.accept()


def main():
    app = QApplication(sys.argv)
    player = MusicPlayer()
    player.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()




