"""Audio playback management."""

import sounddevice as sd
import numpy as np
from ..utils.constants import AUDIO_SAMPLE_RATE, AUDIO_BLOCK_SIZE


class AudioStream:
    """Manages an audio output stream."""
    
    def __init__(self, sample_rate: int = AUDIO_SAMPLE_RATE, block_size: int = AUDIO_BLOCK_SIZE, channels: int = 2):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.channels = channels
        self.stream = None
    
    def start(self, callback):
        """Start the audio stream with the given callback."""
        if self.stream is not None:
            return  # Already started
        
        try:
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                blocksize=self.block_size,
                callback=callback,
            )
            self.stream.start()
            print(f"Audio stream started successfully")
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            import traceback
            traceback.print_exc()
            self.stream = None
    
    def stop(self):
        """Stop the audio stream."""
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
    
    def is_active(self) -> bool:
        """Check if the stream is active."""
        return self.stream is not None

