"""Wi-Fi reader for WT901WIFI IMU over TCP/UDP."""
import struct
import socket
import threading
from datetime import datetime
from typing import Optional

from .base import ImuDataSource
from .serial_reader import SerialImuReader  # For frame decoding
from ..models import ImuSample


class WifiImuReader(ImuDataSource):
    """Reads WT55 protocol frames from WT901WIFI IMU over Wi-Fi (TCP or UDP)."""

    FRAME_LENGTH = 54
    HEADER = b"WT55"

    def __init__(self, use_tcp: bool = True, port: int = 1399):
        """
        Initialize Wi-Fi IMU reader.

        Args:
            use_tcp: If True, use TCP; if False, use UDP
            port: Port to listen on (default 1399)
        """
        super().__init__()
        self.use_tcp = use_tcp
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.conn: Optional[socket.socket] = None  # For TCP connection
        self.thread: Optional[threading.Thread] = None
        self.server_thread: Optional[threading.Thread] = None
        self._decoder = SerialImuReader("", 9600)  # Reuse decoding logic

    def start(self):
        """Start TCP/UDP server and begin reading."""
        try:
            if self.use_tcp:
                # TCP server
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.sock.bind(('', self.port))
                self.sock.listen(1)
                self.sock.settimeout(1.0)  # Allow periodic checking of self.running
                print(f"TCP server listening on port {self.port}")
                
                self.running = True
                self.server_thread = threading.Thread(target=self._tcp_server_loop, daemon=True)
                self.server_thread.start()
            else:
                # UDP server
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.bind(('', self.port))
                self.sock.settimeout(1.0)
                print(f"UDP server listening on port {self.port}")
                
                self.running = True
                self.thread = threading.Thread(target=self._udp_read_loop, daemon=True)
                self.thread.start()
        except Exception as e:
            raise RuntimeError(f"Failed to start Wi-Fi server: {e}")

    def stop(self):
        """Stop reading and close sockets."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.server_thread:
            self.server_thread.join(timeout=2.0)
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
        if self.sock:
            try:
                self.sock.close()
            except:
                pass

    def _tcp_server_loop(self):
        """TCP server loop - accepts connections and starts reading."""
        while self.running:
            try:
                if self.conn is None:
                    # Wait for connection
                    try:
                        conn, addr = self.sock.accept()
                        print(f"TCP client connected from {addr}")
                        self.conn = conn
                        # Start reading from this connection
                        self.thread = threading.Thread(target=self._tcp_read_loop, daemon=True)
                        self.thread.start()
                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self.running:
                            print(f"Error accepting TCP connection: {e}")
                        break
                else:
                    # Connection exists, just wait
                    import time
                    time.sleep(0.1)
            except Exception as e:
                if self.running:
                    print(f"TCP server error: {e}")
                break

    def _tcp_read_loop(self):
        """Read data from TCP connection."""
        buffer = b''
        while self.running and self.conn:
            try:
                data = self.conn.recv(4096)
                if not data:
                    # Connection closed
                    print("TCP connection closed by client")
                    self.conn.close()
                    self.conn = None
                    break
                
                buffer += data
                # Process complete frames (terminated with \r\n)
                while b'\r\n' in buffer:
                    line_end = buffer.find(b'\r\n')
                    line = buffer[:line_end + 2]
                    buffer = buffer[line_end + 2:]
                    
                    sample = self._decode_frame(line)
                    if sample:
                        self._put_sample(sample)
                        
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"TCP read error: {e}")
                break

    def _udp_read_loop(self):
        """Read data from UDP socket."""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                # UDP packets should contain complete frames
                # Try to find frame boundaries
                if len(data) >= self.FRAME_LENGTH:
                    # Look for WT55 header
                    idx = 0
                    while idx < len(data):
                        header_pos = data.find(self.HEADER, idx)
                        if header_pos == -1:
                            break
                        # Extract potential frame
                        if header_pos + self.FRAME_LENGTH <= len(data):
                            frame = data[header_pos:header_pos + self.FRAME_LENGTH]
                            sample = self._decode_frame(frame)
                            if sample:
                                self._put_sample(sample)
                            idx = header_pos + self.FRAME_LENGTH
                        else:
                            break
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"UDP read error: {e}")
                break

    def _decode_frame(self, line: bytes) -> Optional[ImuSample]:
        """Decode a WT55 protocol frame (reuses SerialImuReader logic)."""
        return self._decoder._decode_frame(line)

