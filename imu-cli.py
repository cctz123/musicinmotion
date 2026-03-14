#!/usr/bin/env python3
import serial
import time
import struct
import argparse
import socket
from imu_viewer.config_loader import load_config

def format_hexdump(data: bytes, offset: int = 0) -> str:
    """
    Format bytes in hexdump -C style.
    
    Args:
        data: Bytes to format
        offset: Starting offset for the hex dump
        
    Returns:
        Formatted hex dump string
    """
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        current_offset = offset + i
        
        # Format offset (8 hex digits)
        offset_str = f"{current_offset:08x}"
        
        # Format hex bytes (16 bytes, split into two groups of 8)
        # First group: bytes 0-7
        first_group = chunk[:8] if len(chunk) > 0 else b''
        first_hex = ' '.join(f"{b:02x}" for b in first_group)
        if len(first_group) < 8:
            # Pad first group to 23 characters (8 bytes * 3 - 1 space)
            first_hex = first_hex.ljust(23)
        
        # Second group: bytes 8-15
        second_group = chunk[8:16] if len(chunk) > 8 else b''
        second_hex = ' '.join(f"{b:02x}" for b in second_group)
        if len(second_group) < 8:
            # Pad second group to 23 characters
            second_hex = second_hex.ljust(23)
        
        # Combine hex parts with 2 spaces between groups
        hex_str = f"{first_hex}  {second_hex}"
        
        # Format ASCII representation (only actual bytes, not padded)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        
        lines.append(f"{offset_str}  {hex_str}  |{ascii_str}|")
    
    return '\n'.join(lines)

def send_command(ser, command: str):
    """Send an ASCII command to the device over serial."""
    cmd_bytes = (command + '\r\n').encode('ascii')
    ser.write(cmd_bytes)
    ser.flush()
    print(f"Sent command: {command}")

def _parse_frame(line: bytes, raw_output: bool):
    """Parse and display a single IMU frame."""
    HEADER_LEN = 12   # "WT5500007991" length
    
    if raw_output:
        # Raw hex dump style (hexdump -C format)
        print(format_hexdump(line))
        print()  # Empty line between frames
    else:
        # Parsed style
        if len(line) < HEADER_LEN + 2:
            return
        
        # First 12 bytes are ASCII header / device ID
        header = line[:HEADER_LEN].decode(errors="ignore")
        payload = line[HEADER_LEN:-2] if line.endswith(b'\r\n') else line[HEADER_LEN:]
        
        # Parse battery percentage (bytes 46-48 in full line)
        # Battery: 0-255 where 255 = 100% charged
        battery_V = None
        if len(line) >= 48:
            batt_raw = struct.unpack('<H', line[46:48])[0]
            # Old voltage interpretation (commented out):
            # battery_V = batt_raw / 100.0  # Voltage in volts (e.g., 300 = 3.00V, 420 = 4.20V)
            battery_V = (batt_raw / 255.0) * 100.0  # Percentage (0-100%)
        
        print(f"\nHeader: {header}")
        if battery_V is not None:
            print(f"Battery: {battery_V:.1f}%")
        print("Raw payload hex:", payload.hex(" "))
        
        # Interpret payload as sequence of signed 16-bit integers (little-endian)
        if len(payload) % 2 != 0:
            print("Odd payload length, skipping")
            return
        
        values = struct.unpack("<" + "h" * (len(payload) // 2), payload)
        print("Int16 values:", values)

def cmd_read(args):
    """Read and display IMU data from USB, AP, or STA mode."""
    config = load_config()
    
    # Determine mode: command-line override takes precedence, then config
    if args.ap:
        mode = 'ap'
    elif args.sta:
        mode = 'sta'
    elif args.usb:
        mode = 'usb'
    else:
        # Use mode from config, default to 'usb'
        mode = config.get("mode", "usb").lower()
    
    # Determine output format
    raw_output = args.raw if args.raw else (not args.parse)
    
    HEADER_LEN = 12   # "WT5500007991" length
    
    print(f"Reading IMU data in {mode.upper()} mode")
    print(f"Output style: {'raw' if raw_output else 'parsed'}")
    print("Press Ctrl+C to stop\n")
    
    if mode == 'usb':
        # USB Serial mode
        PORT = config["usb"]["port"]
        BAUD = 9600  # Hardcoded for WT901WIFI
        
        try:
            ser = serial.Serial(PORT, BAUD, timeout=1)
            print(f"Opened {PORT} at {BAUD} baud")
            time.sleep(2)
            
            try:
                while True:
                    line = ser.readline()
                    if not line:
                        continue
                    _parse_frame(line, raw_output)
            except KeyboardInterrupt:
                print("\n\nStopped by user")
            finally:
                ser.close()
                print("Serial port closed")
        except serial.SerialException as e:
            print(f"**Error**: No USB device detected or cannot open serial port {PORT}")
            return 1
    
    elif mode == 'ap':
        # Wi-Fi AP mode (UDP)
        if "ap" not in config:
            print("Error: AP mode settings not found in .imuconfig")
            print("Please add an 'ap' section with 'ssid', 'ip', and 'port' fields.")
            return 1
        
        ap_cfg = config["ap"]
        device_ip = ap_cfg.get("ip")
        device_port = ap_cfg.get("port")
        ssid = ap_cfg.get("ssid", "WT901-xxxx")
        
        if not device_ip or not device_port:
            print("Error: AP mode settings incomplete in .imuconfig")
            print("Required fields: 'ip' and 'port'")
            return 1
        
        print(f"Connecting to IMU device at {device_ip}:{device_port} (AP mode, SSID: {ssid})")
        
        sock = None
        try:
            # UDP socket - bind to port to receive data
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            sock.bind(('', device_port))
            
            buffer = b''
            while True:
                try:
                    # UDP: receive datagrams
                    data, addr = sock.recvfrom(4096)
                    buffer += data
                    
                    # Process complete lines (terminated with \r\n)
                    while b'\r\n' in buffer:
                        line_end = buffer.find(b'\r\n')
                        line = buffer[:line_end + 2]
                        buffer = buffer[line_end + 2:]
                        _parse_frame(line, raw_output)
                    
                    # Also check for frames without \r\n (UDP might send raw frames)
                    if len(buffer) >= 54:  # FRAME_LENGTH
                        # Look for WT55 header
                        if buffer[:4] == b'WT55' or (len(buffer) >= 12 and buffer[:12].decode(errors='ignore').startswith('WT55')):
                            # Try to extract a 54-byte frame
                            if len(buffer) >= 54:
                                line = buffer[:54]
                                buffer = buffer[54:]
                                _parse_frame(line, raw_output)
                
                except socket.timeout:
                    continue
                except socket.error as e:
                    print(f"\nSocket error: {e}")
                    break
        
        except socket.error as e:
            print(f"\nError: Could not bind to port {device_port}: {e}")
            print("Please ensure:")
            print(f"  1. The device is in AP mode (SSID: {ssid})")
            print(f"  2. Your computer is connected to the device's Wi-Fi network")
            print(f"  3. The device IP is correct: {device_ip}")
            return 1
        except KeyboardInterrupt:
            print("\n\nStopped by user")
        except Exception as e:
            print(f"\nError: {e}")
            return 1
        finally:
            if sock:
                sock.close()
                print("\nConnection closed")
    
    elif mode == 'sta':
        # Wi-Fi STA mode (TCP or UDP server)
        if "wifi" not in config:
            print("Error: Wi-Fi STA settings not found in .imuconfig")
            print("Please add a 'wifi' section with 'ip', 'port', and 'use_tcp' fields.")
            return 1
        
        wifi_cfg = config["wifi"]
        device_port = wifi_cfg.get("port", 1399)
        use_tcp = wifi_cfg.get("use_tcp", False)
        
        protocol = "TCP" if use_tcp else "UDP"
        print(f"Listening on port {device_port} ({protocol} server mode)")
        print("Waiting for device to connect...")
        
        sock = None
        conn = None
        try:
            if use_tcp:
                # TCP server
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('', device_port))
                sock.listen(1)
                sock.settimeout(1.0)
                print(f"TCP server listening on port {device_port}")
                
                # Wait for connection
                while conn is None:
                    try:
                        conn, addr = sock.accept()
                        print(f"TCP client connected from {addr}")
                        conn.settimeout(1.0)
                    except socket.timeout:
                        continue
                
                # Read from TCP connection
                buffer = b''
                while True:
                    try:
                        data = conn.recv(4096)
                        if not data:
                            print("\nConnection closed by device")
                            break
                        buffer += data
                        
                        # Process complete lines (terminated with \r\n)
                        while b'\r\n' in buffer:
                            line_end = buffer.find(b'\r\n')
                            line = buffer[:line_end + 2]
                            buffer = buffer[line_end + 2:]
                            _parse_frame(line, raw_output)
                    
                    except socket.timeout:
                        continue
                    except socket.error as e:
                        print(f"\nSocket error: {e}")
                        break
            else:
                # UDP server
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(('', device_port))
                sock.settimeout(1.0)
                print(f"UDP server listening on port {device_port}")
                
                buffer = b''
                while True:
                    try:
                        data, addr = sock.recvfrom(4096)
                        buffer += data
                        
                        # Process complete lines (terminated with \r\n)
                        while b'\r\n' in buffer:
                            line_end = buffer.find(b'\r\n')
                            line = buffer[:line_end + 2]
                            buffer = buffer[line_end + 2:]
                            _parse_frame(line, raw_output)
                        
                        # Also check for frames without \r\n
                        if len(buffer) >= 54:
                            if buffer[:4] == b'WT55' or (len(buffer) >= 12 and buffer[:12].decode(errors='ignore').startswith('WT55')):
                                if len(buffer) >= 54:
                                    line = buffer[:54]
                                    buffer = buffer[54:]
                                    _parse_frame(line, raw_output)
                    
                    except socket.timeout:
                        continue
                    except socket.error as e:
                        print(f"\nSocket error: {e}")
                        break
        
        except socket.error as e:
            print(f"\nError: Could not bind to port {device_port}: {e}")
            return 1
        except KeyboardInterrupt:
            print("\n\nStopped by user")
        except Exception as e:
            print(f"\nError: {e}")
            return 1
        finally:
            if conn:
                conn.close()
            if sock:
                sock.close()
                print("\nConnection closed")
    
    else:
        print(f"Error: Unknown mode '{mode}'")
        print("Valid modes: usb, ap, sta")
        return 1
    
    return 0


def cmd_reset(args):
    """Perform reset on the device (hard reset, soft reboot, or all)."""
    config = load_config()
    PORT = config["usb"]["port"]
    # USB/Serial is hardcoded to 9600 baud - device doesn't accept other rates
    BAUD = 9600
    
    reset_type = args.reset_type
    
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        print(f"Opened {PORT} at {BAUD} baud")
        time.sleep(2)
        
        # Flush any existing data
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # First, set work mode = 2 and connect mode = 0 (required before reset commands)
        print("Setting device mode (work mode = 2, connect mode = 0)...")
        work_mode_cmd = bytes([0xFF, 0xAA, 0x5B, 0x02])
        connect_mode_cmd = bytes([0xFF, 0xAA, 0x5C, 0x00])
        
        ser.write(work_mode_cmd)
        ser.flush()
        print(f"Sent work mode command: {work_mode_cmd.hex(' ').upper()}")
        time.sleep(0.2)
        
        ser.write(connect_mode_cmd)
        ser.flush()
        print(f"Sent connect mode command: {connect_mode_cmd.hex(' ').upper()}")
        time.sleep(0.2)
        
        if reset_type == 'all':
            print("\nPerforming full reset sequence (standard output mode + factory reset + soft reboot)...")
            print("WARNING: This will reset all device settings to factory defaults!")
            
            cmds = [
                "FF AA 60 00",  # standard output mode
                "FF AA 52 00",  # factory reset
                "FF AA 55 00"   # soft reboot
            ]
            
            for cmd_hex in cmds:
                cmd_bytes = bytes.fromhex(cmd_hex)
                ser.write(cmd_bytes)
                ser.flush()
                print(f"Sent command: {cmd_hex}")
                time.sleep(0.2)
            
            print("\nFull reset sequence sent successfully!")
            print("Device should now be reset to factory defaults and rebooted.")
            
        elif reset_type == 'soft':
            print("\nPerforming soft reboot...")
            
            # Send soft reboot command: FF AA 55 00
            reboot_cmd = bytes([0xFF, 0xAA, 0x55, 0x00])
            ser.write(reboot_cmd)
            ser.flush()
            print(f"Sent soft reboot command: {reboot_cmd.hex(' ').upper()}")
            
            # Wait for command to be processed
            time.sleep(2)
            
            print("\nSoft reboot command sent successfully!")
            print("Device should now be rebooting.")
            
        else:  # hard (default)
            print("\nPerforming factory reset (hard reset)...")
            print("WARNING: This will reset all device settings to factory defaults!")
            
            # Send factory reset command: FF AA 52 00
            reset_cmd = bytes([0xFF, 0xAA, 0x52, 0x00])
            ser.write(reset_cmd)
            ser.flush()
            print(f"Sent factory reset command: {reset_cmd.hex(' ').upper()}")
            
            # Wait for command to be processed
            time.sleep(2)
            
            print("\nFactory reset command sent successfully!")
            print("Device should now be reset to factory defaults.")
            print("Note: The device may need to be power cycled or restarted.")
        
    except serial.SerialException as e:
        print(f"**Error**: No USB device detected or cannot open serial port {PORT}")
        return 1
    except Exception as e:
        print(f"Error performing reset: {e}")
        return 1
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("\nSerial port closed")
    
    return 0

def cmd_mode(args):
    """Set or read device mode (AP, STA, or USB)."""
    config = load_config()
    PORT = getattr(args, 'port_override', None) or config["usb"]["port"]
    # USB/Serial is hardcoded to 9600 baud - device doesn't accept other rates
    BAUD = 9600
    
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        print(f"Opened {PORT} at {BAUD} baud")
        time.sleep(2)
        
        # Flush any existing data
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        if args.mode is None:
            # Read current mode
            print("Reading current device mode...")
            print("(Reading from device output stream...)")
            
            # The device outputs WORKMODE and CONNECTMODE during startup/power-on
            # We'll read the device output stream to find these values
            workmode = None
            connectmode = None
            
            # Clear any existing data first
            ser.reset_input_buffer()
            
            # Try to trigger device output by sending a harmless query or waiting for natural output
            # Some devices respond to a query, others output status periodically
            # Read for a few seconds to catch device output
            print("Waiting for device output (this may take a few seconds)...")
            start_time = time.time()
            lines_read = 0
            
            while time.time() - start_time < 5.0:
                if ser.in_waiting > 0:
                    line = ser.readline()
                    if line:
                        lines_read += 1
                        line_str = line.decode(errors='ignore')
                        
                        # Look for WORKMODE= pattern in output
                        if 'WORKMODE=' in line_str:
                            try:
                                # Extract WORKMODE value (e.g., "WORKMODE=2")
                                parts = line_str.split('WORKMODE=')
                                if len(parts) > 1:
                                    workmode_str = parts[1].split()[0].strip()
                                    workmode = int(workmode_str)
                                    print(f"Found WORKMODE={workmode}")
                            except (ValueError, IndexError):
                                pass
                        
                        # Look for CONNECTMODE= pattern in output
                        if 'CONNECTMODE=' in line_str:
                            try:
                                # Extract CONNECTMODE value (e.g., "CONNECTMODE=0")
                                parts = line_str.split('CONNECTMODE=')
                                if len(parts) > 1:
                                    connectmode_str = parts[1].split()[0].strip()
                                    connectmode = int(connectmode_str)
                                    print(f"Found CONNECTMODE={connectmode}")
                            except (ValueError, IndexError):
                                pass
                        
                        # If we found both, we can break early
                        if workmode is not None and (workmode != 2 or connectmode is not None):
                            break
                else:
                    time.sleep(0.1)
            
            if lines_read == 0:
                print("Warning: No data received from device. The device may need to be power cycled.")
            
            # Determine mode from WORKMODE and CONNECTMODE
            if workmode is not None:
                if workmode == 0:
                    print("Current mode: USB")
                    print("  WORKMODE=0 (USB/UART Only)")
                elif workmode == 2:
                    if connectmode is not None:
                        if connectmode == 0:
                            print("Current mode: AP (SoftAP)")
                            print("  WORKMODE=2 (WiFi Mode Enabled)")
                            print("  CONNECTMODE=0 (AP Mode)")
                        elif connectmode == 1:
                            print("Current mode: STA (Station)")
                            print("  WORKMODE=2 (WiFi Mode Enabled)")
                            print("  CONNECTMODE=1 (STA Mode)")
                        else:
                            print(f"Current mode: WiFi (WORKMODE=2, CONNECTMODE={connectmode})")
                    else:
                        print("Current mode: WiFi (WORKMODE=2, CONNECTMODE unknown)")
                else:
                    print(f"Current mode: Unknown (WORKMODE={workmode})")
            else:
                print("Could not determine current mode from device output.")
                print("Try power cycling the device or check the connection.")
                return 1
                
        else:
            # Set mode
            mode = args.mode.lower()
            
            if mode == 'usb':
                print("Setting device to USB mode...")
                work_mode_cmd = bytes([0xFF, 0xAA, 0x5B, 0x00])  # WORKMODE=0 (USB only)
                ser.write(work_mode_cmd)
                ser.flush()
                print(f"Sent work mode command: {work_mode_cmd.hex(' ').upper()}")
                time.sleep(0.2)
                print("Device set to USB mode (WiFi disabled)")
                
            elif mode == 'ap':
                print("Setting device to AP mode (SoftAP)...")
                work_mode_cmd = bytes([0xFF, 0xAA, 0x5B, 0x02])  # WORKMODE=2 (WiFi enabled)
                connect_mode_cmd = bytes([0xFF, 0xAA, 0x5C, 0x00])  # CONNECTMODE=0 (AP)
                
                ser.write(work_mode_cmd)
                ser.flush()
                print(f"Sent work mode command: {work_mode_cmd.hex(' ').upper()}")
                time.sleep(0.2)
                
                ser.write(connect_mode_cmd)
                ser.flush()
                print(f"Sent connect mode command: {connect_mode_cmd.hex(' ').upper()}")
                time.sleep(0.2)
                print("Device set to AP mode (SoftAP)")
                
            elif mode == 'sta':
                print("Setting device to STA mode (Station)...")
                
                # Check for Wi-Fi settings in config
                if "wifi" not in config:
                    print("Error: Wi-Fi settings not found in .imuconfig")
                    print("Please add a 'wifi' section with 'ssid', 'password', 'ip', and 'port' fields.")
                    return 1
                
                wifi_cfg = config["wifi"]
                ssid = wifi_cfg.get("ssid")
                password = wifi_cfg.get("password")
                device_ip = wifi_cfg.get("ip")
                
                # Use port2 if --port2 flag is set, otherwise use port
                if args.port2:
                    device_port = wifi_cfg.get("port2")
                    if device_port is None:
                        print("Error: port2 not found in .imuconfig")
                        print("Please add 'port2' to the 'wifi' section in .imuconfig")
                        return 1
                    print("Using port2 from config")
                else:
                    device_port = wifi_cfg.get("port")
                
                use_tcp = wifi_cfg.get("use_tcp", False)  # Default to UDP if not specified
                
                if not ssid or not password or not device_ip or device_port is None:
                    print("Error: Wi-Fi settings incomplete in .imuconfig")
                    if args.port2:
                        print("Required fields: 'ssid', 'password', 'ip', and 'port2'")
                    else:
                        print("Required fields: 'ssid', 'password', 'ip', and 'port'")
                    return 1
                
                protocol = "TCP" if use_tcp else "UDP"
                print(f"Configuring STA mode with:")
                print(f"  SSID: {ssid}")
                print(f"  Password: {'*' * len(password)}")
                print(f"  Destination IP: {device_ip}")
                print(f"  Destination Port: {device_port}")
                print(f"  Protocol: {protocol}")
                print()
                
                # Use combined ASCII command as recommended by docs (same as configure_wifi_sta)
                if use_tcp:
                    command = f'IPWIFI:"{ssid}","{password}";TCP{device_ip},{device_port}'
                else:
                    command = f'IPWIFI:"{ssid}","{password}";UDP{device_ip},{device_port}'
                
                print(f"Sending Wi-Fi configuration command: {command}")
                send_command(ser, command)
                
                # Wait a bit for the command to be processed
                time.sleep(2)
                
                print("\nWi-Fi configuration command sent. Device should now:")
                print(f"  1. Connect to Wi-Fi network: {ssid}")
                if use_tcp:
                    print(f"  2. Connect as TCP client to {device_ip}:{device_port}")
                else:
                    print(f"  2. Connect as UDP client to {device_ip}:{device_port}")
                print("  3. Start streaming data over Wi-Fi")
                print("\nNote: Device may need to be power cycled or rebooted for changes to take full effect.")
                
            else:
                print(f"Error: Invalid mode '{args.mode}'")
                print("Valid modes: --ap, --sta, --usb")
                return 1
            
            # Wait for command to be processed
            time.sleep(1)
            print("\nMode change command sent successfully!")
            print("Note: Device may need to be power cycled or rebooted for changes to take full effect.")
        
    except serial.SerialException as e:
        print(f"**Error**: No USB device detected or cannot open serial port {PORT}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("\nSerial port closed")
    
    return 0

def main():
    parser = argparse.ArgumentParser(
        description='IMU configuration and control utility',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s read                 # Read using mode from .imuconfig (parsed, default)
  %(prog)s read --usb           # Read over USB/Serial (override config mode)
  %(prog)s read --ap             # Read over Wi-Fi AP mode (override config mode)
  %(prog)s read --sta            # Read over Wi-Fi STA mode (override config mode)
  %(prog)s read --parse          # Explicit parsed format output
  %(prog)s read --raw            # Raw hex dump output
  %(prog)s read --ap --raw       # AP mode with raw output
  %(prog)s reset                 # Perform factory reset (hard reset, default)
  %(prog)s reset --hard          # Perform factory reset (same as default)
  %(prog)s reset --soft          # Perform soft reboot
  %(prog)s reset --all           # Perform full reset sequence (standard output + factory reset + soft reboot)
  %(prog)s mode                  # Read current device mode
  %(prog)s mode --usb            # Set device to USB mode
  %(prog)s mode --ap             # Set device to AP mode (SoftAP)
  %(prog)s mode --sta            # Set device to STA mode (Station, uses 'port' from .imuconfig)
  %(prog)s mode --sta --port2    # Set device to STA mode using 'port2' from .imuconfig (for second IMU)

Note: For dual IMU setups, use 'port' for the first IMU and 'port2' for the second IMU in .imuconfig.
The 'read' command currently only reads from 'port' (single IMU). Use --port2 with 'mode --sta' to
configure a second device to use port2.
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute', metavar='COMMAND')
    
    # Read command
    read_parser = subparsers.add_parser('read', help='Read and display IMU data (uses mode from .imuconfig by default)')
    read_mode_group = read_parser.add_mutually_exclusive_group()
    read_mode_group.add_argument('--usb', action='store_true', help='Read over USB/Serial (override config mode)')
    read_mode_group.add_argument('--ap', action='store_true', help='Read over Wi-Fi AP mode (override config mode)')
    read_mode_group.add_argument('--sta', action='store_true', help='Read over Wi-Fi STA mode (override config mode)')
    read_format_group = read_parser.add_mutually_exclusive_group()
    read_format_group.add_argument('--raw', action='store_true', help='Output raw hex dump')
    read_format_group.add_argument('--parse', action='store_true', help='Output parsed format (default)')
    read_parser.set_defaults(func=cmd_read)
    
    # Reset command
    reset_parser = subparsers.add_parser('reset', help='Perform reset on the device (hard reset, soft reboot, or all)')
    reset_group = reset_parser.add_mutually_exclusive_group()
    reset_group.add_argument('--hard', action='store_const', const='hard', dest='reset_type', 
                            help='Perform factory reset (default)')
    reset_group.add_argument('--soft', action='store_const', const='soft', dest='reset_type',
                            help='Perform soft reboot')
    reset_group.add_argument('--all', action='store_const', const='all', dest='reset_type',
                            help='Perform full reset sequence (standard output + factory reset + soft reboot)')
    reset_parser.set_defaults(reset_type='hard', func=cmd_reset)
    
    # Mode command
    mode_parser = subparsers.add_parser('mode', help='Set or read device mode (AP, STA, or USB)')
    mode_group = mode_parser.add_mutually_exclusive_group()
    mode_group.add_argument('--ap', action='store_const', const='ap', dest='mode',
                           help='Set device to AP mode (SoftAP)')
    mode_group.add_argument('--sta', action='store_const', const='sta', dest='mode',
                           help='Set device to STA mode (Station, uses "port" from .imuconfig by default)')
    mode_group.add_argument('--usb', action='store_const', const='usb', dest='mode',
                           help='Set device to USB mode')
    mode_parser.add_argument('--port2', action='store_true',
                           help='Use port2 from .imuconfig instead of port (only for --sta mode, for second IMU)')
    mode_parser.add_argument('--port', dest='port_override', metavar='PATH',
                           help='Serial port path (e.g. /dev/tty.usbserial-10). Overrides .imuconfig for this command.')
    mode_parser.set_defaults(mode=None, func=cmd_mode)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)

if __name__ == '__main__':
    exit(main())

