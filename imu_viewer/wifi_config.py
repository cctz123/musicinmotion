"""Wi-Fi configuration for WT901WIFI IMU."""
import socket
from typing import Optional, Tuple
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QButtonGroup, QMessageBox
)
from PyQt5.QtCore import Qt

try:
    from .data_sources.serial_reader import SerialImuReader
    from .config_loader import load_config
except ImportError:
    from data_sources.serial_reader import SerialImuReader
    from config_loader import load_config


def get_local_ip() -> str:
    """
    Get the local IP address of this machine.

    Returns:
        IP address string, or '127.0.0.1' if detection fails
    """
    try:
        # Connect to a remote address to determine local IP
        # (doesn't actually send data)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        # Fallback: try hostname
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "127.0.0.1"


class WifiConfigDialog(QDialog):
    """Dialog for configuring Wi-Fi STA mode on WT901WIFI IMU using PyQt5."""

    def __init__(self, parent=None):
        """Initialize the configuration dialog."""
        super().__init__(parent)
        self.setWindowTitle("Wi-Fi STA Mode Configuration")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        self.config_result: Optional[Tuple[str, str, str, bool, int]] = None
        
        self._init_ui()

    def _init_ui(self):
        """Create dialog widgets."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Load defaults from config file
        config = load_config()
        wifi_cfg = config.get("wifi", {})
        default_ssid = wifi_cfg.get("ssid", "kumquat")
        default_password = wifi_cfg.get("password", "5555512121")
        default_ip = get_local_ip()  # Always use current local IP
        default_port = str(wifi_cfg.get("port", 1399))
        default_use_tcp = wifi_cfg.get("use_tcp", False)  # Default to UDP
        
        # SSID
        ssid_layout = QHBoxLayout()
        ssid_label = QLabel("SSID:")
        ssid_label.setMinimumWidth(100)
        self.ssid_edit = QLineEdit()
        self.ssid_edit.setText(default_ssid)
        ssid_layout.addWidget(ssid_label)
        ssid_layout.addWidget(self.ssid_edit)
        layout.addLayout(ssid_layout)

        # Password
        password_layout = QHBoxLayout()
        password_label = QLabel("Password:")
        password_label.setMinimumWidth(100)
        self.password_edit = QLineEdit()
        self.password_edit.setText(default_password)
        self.password_edit.setEchoMode(QLineEdit.Password)
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_edit)
        layout.addLayout(password_layout)

        # IP Address
        ip_layout = QHBoxLayout()
        ip_label = QLabel("Server IP:")
        ip_label.setMinimumWidth(100)
        self.ip_edit = QLineEdit()
        self.ip_edit.setText(default_ip)
        ip_layout.addWidget(ip_label)
        ip_layout.addWidget(self.ip_edit)
        layout.addLayout(ip_layout)

        # Port
        port_layout = QHBoxLayout()
        port_label = QLabel("Port:")
        port_label.setMinimumWidth(100)
        self.port_edit = QLineEdit()
        self.port_edit.setText(default_port)
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_edit)
        layout.addLayout(port_layout)

        # Protocol selection
        protocol_layout = QHBoxLayout()
        protocol_label = QLabel("Protocol:")
        protocol_label.setMinimumWidth(100)
        self.protocol_group = QButtonGroup(self)
        self.tcp_radio = QRadioButton("TCP")
        self.tcp_radio.setChecked(default_use_tcp)
        self.udp_radio = QRadioButton("UDP")
        self.udp_radio.setChecked(not default_use_tcp)
        self.protocol_group.addButton(self.tcp_radio, 0)
        self.protocol_group.addButton(self.udp_radio, 1)
        protocol_layout.addWidget(protocol_label)
        protocol_layout.addWidget(self.tcp_radio)
        protocol_layout.addWidget(self.udp_radio)
        protocol_layout.addStretch()
        layout.addLayout(protocol_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.configure_button = QPushButton("Configure")
        self.configure_button.setDefault(True)
        self.configure_button.clicked.connect(self._on_configure)
        self.configure_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        
        button_layout.addWidget(self.configure_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def _on_configure(self):
        """Handle configure button click."""
        ssid = self.ssid_edit.text().strip()
        password = self.password_edit.text().strip()
        ip = self.ip_edit.text().strip()
        port_str = self.port_edit.text().strip()
        use_tcp = self.tcp_radio.isChecked()

        # Validation
        if not ssid:
            QMessageBox.warning(self, "Error", "SSID cannot be empty")
            return

        if not ip:
            QMessageBox.warning(self, "Error", "IP address cannot be empty")
            return

        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                raise ValueError("Port out of range")
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid port number (1-65535)")
            return

        self.config_result = (ssid, password, ip, use_tcp, port)
        self.accept()

    def get_config(self) -> Optional[Tuple[str, str, str, bool, int]]:
        """
        Get the configuration result.

        Returns:
            Tuple of (ssid, password, ip, use_tcp, port) if configured,
            None if cancelled
        """
        return self.config_result


def configure_wifi_sta(serial_reader: SerialImuReader, ssid: str, password: str,
                      server_ip: str, use_tcp: bool, port: int) -> bool:
    """
    Configure WT901WIFI IMU for Wi-Fi STA mode.

    Args:
        serial_reader: SerialImuReader instance connected to the device
        ssid: Wi-Fi network SSID
        password: Wi-Fi password
        server_ip: Server IP address to connect to
        use_tcp: If True, use TCP; if False, use UDP
        port: Server port number

    Returns:
        True if configuration appears successful, False otherwise
    """
    try:
        # Use combined command as recommended by docs
        if use_tcp:
            command = f'IPWIFI:"{ssid}","{password}";TCP{server_ip},{port}'
        else:
            command = f'IPWIFI:"{ssid}","{password}";UDP{server_ip},{port}'

        print(f"Sending Wi-Fi configuration command: {command}")
        serial_reader.send_command(command)

        # Wait a bit for the command to be processed
        import time
        time.sleep(2)

        print("Wi-Fi configuration command sent. Device should now:")
        print(f"  1. Connect to Wi-Fi network: {ssid}")
        if use_tcp:
            print(f"  2. Connect as TCP client to {server_ip}:{port}")
        else:
            print(f"  2. Connect as UDP client to {server_ip}:{port}")
        print("  3. Start streaming data over Wi-Fi")

        return True

    except Exception as e:
        print(f"Error configuring Wi-Fi: {e}")
        return False
