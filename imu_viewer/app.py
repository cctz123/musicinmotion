#!/usr/bin/env python3
"""Main entry point for IMU Viewer application."""
import argparse
import sys
from pathlib import Path

# Support both: python -m imu_viewer.app (from project root) and python imu_viewer/app.py
if __package__ is None:
    _dir = Path(__file__).resolve().parent
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

try:
    from .data_sources import SerialImuReader
    from .qt_main_window import ImuViewerMainWindow
    from .config_loader import load_config
except ImportError:
    from data_sources import SerialImuReader
    from qt_main_window import ImuViewerMainWindow
    from config_loader import load_config


def main():
    """Main application entry point."""
    # Load config file for defaults
    config = load_config()
    default_port = config.get("usb", {}).get("port", "/dev/tty.usbserial-10")
    default_mode = config.get("mode", "usb").lower()  # Default to "usb" if not specified

    parser = argparse.ArgumentParser(
        description='WT901WIFI IMU Viewer - Real-time visualization of IMU data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Startup Mode:
  The application uses the "mode" setting from .imuconfig by default ({default_mode}).
  You can override this with command-line flags: --usb, --sta, or --ap.

Examples:
  # Start using mode from .imuconfig (currently: {default_mode})
  python imu_viewer/app.py

  # Override: Start in USB Serial mode
  python imu_viewer/app.py --usb

  # Override: Start in Wi-Fi STA mode (Station)
  python imu_viewer/app.py --sta

  # Override: Start in Wi-Fi AP mode (Access Point)
  python imu_viewer/app.py --ap

  # Enable CSV logging
  python imu_viewer/app.py --log imu_data.csv

  # List available serial ports
  python imu_viewer/app.py --list-ports
        """
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--usb',
        action='store_const',
        const='usb',
        dest='mode',
        help='Start in USB Serial mode (overrides .imuconfig "mode" setting)'
    )
    mode_group.add_argument(
        '--sta',
        action='store_const',
        const='sta',
        dest='mode',
        help='Start in Wi-Fi STA mode (overrides .imuconfig "mode" setting)'
    )
    mode_group.add_argument(
        '--ap',
        action='store_const',
        const='ap',
        dest='mode',
        help='Start in Wi-Fi AP mode (overrides .imuconfig "mode" setting)'
    )

    parser.add_argument(
        '--log', '-l',
        type=str,
        metavar='FILE',
        help='Log samples to CSV file'
    )

    parser.add_argument(
        '--list-ports',
        action='store_true',
        help='List available serial ports and exit'
    )

    parser.add_argument(
        '--history-seconds',
        type=float,
        default=20.0,
        help='Number of seconds of history to display (default: 20.0)'
    )

    parser.add_argument(
        '--update-rate',
        type=float,
        default=30.0,
        help='Target UI update rate in Hz (default: 30.0)'
    )

    args = parser.parse_args()
    
    # Store default port in args for compatibility
    args.port = default_port
    
    # Set mode from command line or use config default
    if args.mode is None:
        args.mode = default_mode

    # List ports if requested
    if args.list_ports:
        ports = SerialImuReader.list_ports()
        if ports:
            print("Available serial ports:")
            for port in ports:
                print(f"  {port}")
        else:
            print("No serial ports found.")
        return 0

    # Enable high DPI scaling BEFORE creating QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("WT901WIFI IMU Viewer")

    # Create and show main window
    window = ImuViewerMainWindow(args)
    window.show()

    # Run application
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
