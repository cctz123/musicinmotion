"""Settings dialog for editing .imuconfig file."""
import json
from pathlib import Path
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QMessageBox, QTabWidget, QWidget,
    QFormLayout, QCheckBox, QSpinBox
)
from PyQt5.QtCore import Qt

try:
    from .config_loader import CONFIG_FILE, load_config, save_config
except ImportError:
    from config_loader import CONFIG_FILE, load_config, save_config


class SettingsDialog(QDialog):
    """Dialog for editing .imuconfig file."""

    def __init__(self, parent=None):
        """Initialize the settings dialog."""
        super().__init__(parent)
        self.setWindowTitle("IMU Configuration Settings")
        self.setModal(True)
        self.setMinimumSize(600, 500)
        
        self.config_changed = False
        
        self._init_ui()
        self._load_config()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        
        # Create tab widget
        tabs = QTabWidget()
        
        # USB/Serial tab
        usb_tab = QWidget()
        usb_layout = QFormLayout(usb_tab)
        
        self.usb_port_edit = QLineEdit()
        usb_layout.addRow("Port:", self.usb_port_edit)
        
        self.usb_baud_edit = QSpinBox()
        self.usb_baud_edit.setRange(9600, 230400)
        self.usb_baud_edit.setSingleStep(9600)
        usb_layout.addRow("Baud Rate:", self.usb_baud_edit)
        
        usb_note = QLabel("Note: USB/Serial is hardcoded to 9600 baud for WT901WIFI")
        usb_note.setWordWrap(True)
        usb_note.setStyleSheet("color: #7f8c8d; font-style: italic;")
        usb_layout.addRow("", usb_note)
        
        tabs.addTab(usb_tab, "USB/Serial")
        
        # Wi-Fi STA tab
        wifi_tab = QWidget()
        wifi_layout = QFormLayout(wifi_tab)
        
        self.wifi_ssid_edit = QLineEdit()
        wifi_layout.addRow("SSID:", self.wifi_ssid_edit)
        
        self.wifi_password_edit = QLineEdit()
        self.wifi_password_edit.setEchoMode(QLineEdit.Password)
        wifi_layout.addRow("Password:", self.wifi_password_edit)
        
        self.wifi_port_edit = QSpinBox()
        self.wifi_port_edit.setRange(1, 65535)
        wifi_layout.addRow("Port:", self.wifi_port_edit)
        
        self.wifi_tcp_checkbox = QCheckBox("Use TCP (unchecked for UDP)")
        self.wifi_tcp_checkbox.setChecked(False)  # Default to UDP
        wifi_layout.addRow("Protocol:", self.wifi_tcp_checkbox)
        
        tabs.addTab(wifi_tab, "Wi-Fi STA")
        
        # Wi-Fi AP tab
        ap_tab = QWidget()
        ap_layout = QFormLayout(ap_tab)
        
        self.ap_ssid_edit = QLineEdit()
        ap_layout.addRow("SSID:", self.ap_ssid_edit)
        
        self.ap_ip_edit = QLineEdit()
        ap_layout.addRow("Device IP:", self.ap_ip_edit)
        
        self.ap_port_edit = QSpinBox()
        self.ap_port_edit.setRange(1, 65535)
        ap_layout.addRow("Port:", self.ap_port_edit)
        
        tabs.addTab(ap_tab, "Wi-Fi AP")
        
        layout.addWidget(tabs)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
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
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def _load_config(self):
        """Load configuration from file."""
        try:
            config = load_config()
            
            # USB/Serial
            usb_cfg = config.get("usb", {})
            self.usb_port_edit.setText(usb_cfg.get("port", "/dev/tty.usbserial-10"))
            self.usb_baud_edit.setValue(usb_cfg.get("baud", 9600))
            
            # Wi-Fi STA
            wifi_cfg = config.get("wifi", {})
            self.wifi_ssid_edit.setText(wifi_cfg.get("ssid", ""))
            self.wifi_password_edit.setText(wifi_cfg.get("password", ""))
            self.wifi_port_edit.setValue(wifi_cfg.get("port", 1399))
            self.wifi_tcp_checkbox.setChecked(wifi_cfg.get("use_tcp", False))  # Default to UDP
            
            # Wi-Fi AP
            ap_cfg = config.get("ap", {})
            self.ap_ssid_edit.setText(ap_cfg.get("ssid", "WT901-xxxx"))
            self.ap_ip_edit.setText(ap_cfg.get("ip", "192.168.4.1"))
            self.ap_port_edit.setValue(ap_cfg.get("port", 1399))
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load configuration:\n{e}")

    def _on_save(self):
        """Save configuration to file. Preserves all existing keys; only updates fields edited in this dialog."""
        try:
            # Load full current config so we preserve mode, _note, port2, ip, and any other fields
            config = load_config()

            # Validate before merging
            usb_port = self.usb_port_edit.text().strip()
            ap_ip = self.ap_ip_edit.text().strip()
            if not usb_port:
                QMessageBox.warning(self, "Validation Error", "USB port cannot be empty")
                return
            if not ap_ip:
                QMessageBox.warning(self, "Validation Error", "AP device IP cannot be empty")
                return

            # Update only the sections and keys this dialog edits; keep the rest intact
            config.setdefault("usb", {})
            config["usb"]["port"] = usb_port
            config["usb"]["baud"] = self.usb_baud_edit.value()

            config.setdefault("wifi", {})
            config["wifi"]["ssid"] = self.wifi_ssid_edit.text().strip()
            config["wifi"]["password"] = self.wifi_password_edit.text().strip()
            config["wifi"]["port"] = self.wifi_port_edit.value()
            config["wifi"]["use_tcp"] = self.wifi_tcp_checkbox.isChecked()

            config.setdefault("ap", {})
            config["ap"]["ssid"] = self.ap_ssid_edit.text().strip()
            config["ap"]["ip"] = ap_ip
            config["ap"]["port"] = self.ap_port_edit.value()

            save_config(config)
            self.config_changed = True
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration:\n{e}")

