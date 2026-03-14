"""Abstract base class for IMU data sources."""
from abc import ABC, abstractmethod
from typing import Optional
from queue import Queue

from ..models import ImuSample


class ImuDataSource(ABC):
    """Abstract base class for IMU data sources (USB serial, Wi-Fi, etc.)."""

    def __init__(self):
        """Initialize the data source."""
        self.sample_queue: Queue = Queue(maxsize=100)
        self.running = False

    @abstractmethod
    def start(self):
        """Start reading data from the source."""
        pass

    @abstractmethod
    def stop(self):
        """Stop reading data and clean up resources."""
        pass

    def get_sample(self, timeout: float = 0.1) -> Optional[ImuSample]:
        """
        Get the latest sample from the queue.

        Args:
            timeout: Maximum time to wait for a sample

        Returns:
            ImuSample or None if no sample available
        """
        try:
            return self.sample_queue.get(timeout=timeout)
        except:
            return None

    def _put_sample(self, sample: ImuSample):
        """Put a sample into the queue (non-blocking, drops oldest if full)."""
        try:
            self.sample_queue.put_nowait(sample)
        except:
            # Remove oldest and add new
            try:
                self.sample_queue.get_nowait()
                self.sample_queue.put_nowait(sample)
            except:
                pass

