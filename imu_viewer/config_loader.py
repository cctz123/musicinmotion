"""Configuration file loader for IMU Viewer."""
import json
import os
import socket
from pathlib import Path
from typing import Dict, Any, Optional


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


# Config file is in project root, not in imu_viewer directory
# Go up from imu_viewer/ to project root
CONFIG_FILE = Path(__file__).parent.parent / ".imuconfig"


def load_config() -> Dict[str, Any]:
    """
    Load configuration from .config file.
    
    Returns:
        Dictionary with configuration values
    """
    if not CONFIG_FILE.exists():
        # Create default config if it doesn't exist
        default_config = get_default_config()
        save_config(default_config)
        return default_config
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        # Remove server_ip from wifi config if it exists (always use current local IP)
        if "wifi" in config and "server_ip" in config["wifi"]:
            del config["wifi"]["server_ip"]
            # Save cleaned config
            save_config(config)
        
        # Validate and fill in missing keys with defaults
        default_config = get_default_config()
        for key, value in default_config.items():
            if key not in config:
                config[key] = value
            elif isinstance(value, dict) and isinstance(config[key], dict):
                # For nested dicts (usb, wifi, ap), merge missing keys
                for subkey, subvalue in value.items():
                    if subkey not in config[key]:
                        config[key][subkey] = subvalue
        
        return config
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading config file: {e}. Using defaults.")
        return get_default_config()


def save_config(config: Dict[str, Any]) -> None:
    """
    Save configuration to .config file.
    
    Args:
        config: Configuration dictionary to save
    """
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except IOError as e:
        print(f"Error saving config file: {e}")


def get_default_config() -> Dict[str, Any]:
    """
    Get default configuration values.
    
    Note: server_ip is not stored in config - it's always determined dynamically.
    
    Returns:
        Dictionary with default configuration
    """
    return {
        "mode": "usb",  # Default startup mode: "usb", "sta", or "ap"
        "usb": {
            "port": "/dev/tty.usbserial-10",
            "baud": 9600
        },
        "wifi": {
            "ssid": "kumquat",
            "password": "5555512121",
            "port": 1399,
            "use_tcp": False  # Default to UDP
        },
        "ap": {
            "ssid": "WT901-xxxx",
            "ip": "192.168.4.1",
            "port": 1399
        }
    }


def update_wifi_config(ssid: str, password: str, server_ip: str, port: int, use_tcp: bool) -> None:
    """
    Update Wi-Fi configuration in config file.
    Preserves existing wifi keys (e.g. port2, ip) and only updates ssid, password, port, use_tcp.
    
    Note: server_ip is accepted for compatibility but not stored in config.
    The server IP is always determined dynamically from the current local IP.
    
    Args:
        ssid: Wi-Fi network SSID
        password: Wi-Fi password
        server_ip: Server IP address (not stored, kept for API compatibility)
        port: Server port
        use_tcp: Whether to use TCP (True) or UDP (False)
    """
    config = load_config()
    config.setdefault("wifi", {})
    config["wifi"]["ssid"] = ssid
    config["wifi"]["password"] = password
    config["wifi"]["port"] = port
    config["wifi"]["use_tcp"] = use_tcp
    save_config(config)


def update_usb_config(port: str, baud: int) -> None:
    """
    Update USB configuration in config file.
    Preserves any other usb keys; only updates port and baud.
    
    Args:
        port: Serial port path
        baud: Baud rate
    """
    config = load_config()
    config.setdefault("usb", {})
    config["usb"]["port"] = port
    config["usb"]["baud"] = baud
    save_config(config)


def update_ap_config(ssid: str, ip: str, port: int) -> None:
    """
    Update AP (Access Point) mode configuration in config file.
    Preserves any other ap keys; only updates ssid, ip, and port.
    
    Args:
        ssid: AP SSID (device-generated, typically "WT901-xxxx")
        ip: Device IP address when in AP mode (typically "192.168.4.1")
        port: Port number (typically 1399)
    """
    config = load_config()
    config.setdefault("ap", {})
    config["ap"]["ssid"] = ssid
    config["ap"]["ip"] = ip
    config["ap"]["port"] = port
    save_config(config)

