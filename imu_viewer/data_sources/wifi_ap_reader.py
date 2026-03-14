"""Wi-Fi AP mode reader for WT901WIFI IMU over UDP."""
import socket
import threading
from typing import Optional

from .base import ImuDataSource
from .serial_reader import SerialImuReader  # For frame decoding
from ..models import ImuSample


class WifiApImuReader(ImuDataSource):
    """Reads WT55 protocol frames from WT901WIFI IMU in AP mode over UDP."""

    FRAME_LENGTH = 54
    HEADER_LEN = 12  # "WT5500007991" length

    def __init__(self, device_ip: str, device_port: int):
        """
        Initialize Wi-Fi AP mode IMU reader.

        Args:
            device_ip: IP address of the device in AP mode (typically 192.168.4.1)
            device_port: Port to bind to for receiving UDP data (typically 1399)
        """
        super().__init__()
        self.device_ip = device_ip
        self.device_port = device_port
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self._decoder = SerialImuReader("", 9600)  # Reuse decoding logic

    def start(self):
        """Start UDP listener and begin reading."""
        try:
            # UDP socket - bind to port to receive data
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(1.0)  # 1 second timeout for reads
            self.sock.bind(('', self.device_port))
            print(f"UDP listener bound to port {self.device_port} for AP mode")
            
            self.running = True
            self.thread = threading.Thread(target=self._udp_read_loop, daemon=True)
            self.thread.start()
        except Exception as e:
            raise RuntimeError(f"Failed to start Wi-Fi AP listener: {e}")

    def stop(self):
        """Stop reading and close sockets."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.sock:
            try:
                self.sock.close()
            except:
                pass

    def _udp_read_loop(self):
        """Read data from UDP socket (AP mode)."""
        buffer = b''
        while self.running:
            try:
                # UDP: receive datagrams
                data, addr = self.sock.recvfrom(4096)
                buffer += data
                
                # Process complete lines (terminated with \r\n)
                while b'\r\n' in buffer:
                    line_end = buffer.find(b'\r\n')
                    line = buffer[:line_end + 2]
                    buffer = buffer[line_end + 2:]
                    
                    sample = self._decode_frame(line)
                    if sample:
                        self._put_sample(sample)
                
                # Also check for frames without \r\n (UDP might send raw frames)
                if len(buffer) >= self.FRAME_LENGTH:
                    # Look for WT55 header
                    if buffer[:4] == b'WT55' or (len(buffer) >= self.HEADER_LEN and buffer[:self.HEADER_LEN].decode(errors='ignore').startswith('WT55')):
                        # Try to extract a 54-byte frame
                        if len(buffer) >= self.FRAME_LENGTH:
                            line = buffer[:self.FRAME_LENGTH]
                            buffer = buffer[self.FRAME_LENGTH:]
                            
                            sample = self._decode_frame(line)
                            if sample:
                                self._put_sample(sample)
                        
            except socket.timeout:
                # Timeout is OK, just continue reading
                continue
            except Exception as e:
                if self.running:
                    print(f"UDP read error (AP mode): {e}")
                break

    def _decode_frame(self, line: bytes) -> Optional[ImuSample]:
        """Decode a WT55 protocol frame (reuses SerialImuReader logic)."""
        return self._decoder._decode_frame(line)

