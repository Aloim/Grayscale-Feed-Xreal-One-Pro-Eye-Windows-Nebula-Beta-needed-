"""
XREAL Eye Video Activation Tool

Attempts to activate video streaming by sending commands to the control channel.
Based on protocol analysis showing protobuf-encoded messages.
"""

import socket
import struct
import time
from typing import Optional, Tuple

# XREAL glasses network config
GLASSES_IP = "169.254.2.1"
PORT_CONTROL = 52999
PORT_IMU = 52998
PORT_METADATA = 52996

# Known message types (header bytes)
MSG_TYPE_CONTROL = 0x278a
MSG_TYPE_IMU = 0x2836
MSG_TYPE_METADATA = 0x2731

# Potential video activation commands based on firmware analysis
# 0x6A (106) was identified as NRUsbSetNetworkEnable code
VIDEO_ENABLE_CMD = 0x6A

def create_message(msg_type: int, flags: int, payload: bytes) -> bytes:
    """Create a message in XREAL protocol format"""
    header = struct.pack(">H", msg_type)  # Big-endian message type
    flags_bytes = struct.pack("<I", flags)  # Little-endian flags
    return header + flags_bytes + payload

def create_protobuf_field(field_num: int, wire_type: int, value) -> bytes:
    """Create a protobuf field"""
    tag = (field_num << 3) | wire_type

    if wire_type == 0:  # Varint
        return bytes([tag]) + encode_varint(value)
    elif wire_type == 2:  # Length-delimited
        data = value if isinstance(value, bytes) else value.encode()
        return bytes([tag]) + encode_varint(len(data)) + data
    elif wire_type == 5:  # 32-bit (float)
        return bytes([tag]) + struct.pack("<f", value)
    else:
        raise ValueError(f"Unsupported wire type: {wire_type}")

def encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint"""
    result = []
    while value > 127:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)

def create_start_video_cmd_v1() -> bytes:
    """
    Attempt 1: Simple enable command
    Similar to NRUsbSetNetworkEnable with code 0x6A
    """
    # Format: [type:2][flags:4][cmd:1][enable:1]
    msg_type = MSG_TYPE_CONTROL
    flags = 0x00000009  # Same as received messages
    payload = bytes([VIDEO_ENABLE_CMD, 0x01])  # Command 0x6A, enable=1
    return create_message(msg_type, flags, payload)

def create_start_video_cmd_v2() -> bytes:
    """
    Attempt 2: Protobuf-style request
    Field structure matching observed protocol
    """
    # Create protobuf payload
    # Field 1: command type (0x6A = 106 for video enable)
    # Field 2: enable flag (1 = on)
    inner = create_protobuf_field(1, 0, VIDEO_ENABLE_CMD)  # command_type = 106
    inner += create_protobuf_field(2, 0, 1)  # enable = 1

    # Wrap in field 3 (length-delimited) like observed messages
    payload = create_protobuf_field(3, 2, inner)

    return create_message(MSG_TYPE_CONTROL, 0x00000009, payload)

def create_start_video_cmd_v3() -> bytes:
    """
    Attempt 3: Camera config request
    Based on gRPC StartStreaming endpoint
    """
    # Camera config protobuf:
    # Field 1: width (1280)
    # Field 2: height (720)
    # Field 3: fps (30)
    # Field 4: format string ("YUV420")
    camera_config = b""
    camera_config += create_protobuf_field(1, 0, 1280)  # width
    camera_config += create_protobuf_field(2, 0, 720)   # height
    camera_config += create_protobuf_field(3, 0, 30)    # fps
    camera_config += create_protobuf_field(4, 2, b"YUV420")  # format

    # Wrap camera config in field 1 (OpenStreamRequest)
    open_stream = create_protobuf_field(1, 2, camera_config)

    return create_message(MSG_TYPE_CONTROL, 0x00000009, open_stream)

def create_start_video_cmd_v4() -> bytes:
    """
    Attempt 4: Raw command with IP address
    NRUsbSetNetworkEnable might need IP payload
    """
    # Format: [cmd:1][ip_bytes:4]
    ip_bytes = bytes([169, 254, 2, 10])  # Host IP: 169.254.2.10
    payload = bytes([VIDEO_ENABLE_CMD]) + ip_bytes
    return create_message(MSG_TYPE_CONTROL, 0x00000009, payload)

def create_start_video_cmd_v5() -> bytes:
    """
    Attempt 5: Different message type for video
    Maybe video commands use 0x28XX header like IMU
    """
    # Try 0x286a (video type) header
    msg_type = 0x2800 | VIDEO_ENABLE_CMD  # 0x286a
    flags = 0x00000001
    payload = bytes([0x01])  # Enable
    return struct.pack(">H", msg_type) + struct.pack("<I", flags) + payload

def create_ping_cmd() -> bytes:
    """Create a simple ping/keepalive command"""
    return create_message(MSG_TYPE_CONTROL, 0x00000000, b"")

def try_send_command(sock: socket.socket, cmd: bytes, name: str) -> Optional[bytes]:
    """Send a command and wait for response"""
    print(f"\n--- Trying: {name} ---")
    print(f"  Sending: {cmd.hex()}")
    print(f"  Length: {len(cmd)} bytes")

    try:
        sock.sendall(cmd)
        time.sleep(0.1)  # Brief wait

        # Try to receive response
        sock.settimeout(1.0)
        try:
            response = sock.recv(4096)
            print(f"  Response: {response.hex()}")
            print(f"  Response length: {len(response)} bytes")
            return response
        except socket.timeout:
            print("  No response (timeout)")
            return None

    except Exception as e:
        print(f"  Error: {e}")
        return None

def check_video_ports():
    """Check if video ports have opened after commands"""
    video_ports = [50051, 50346, 50356, 50361, 5555, 5556, 5557]
    print("\n--- Checking Video Ports ---")

    for port in video_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((GLASSES_IP, port))
            status = "OPEN" if result == 0 else "closed"
            if result == 0:
                print(f"  Port {port}: {status} ***")
            else:
                print(f"  Port {port}: {status}")
            sock.close()
        except Exception as e:
            print(f"  Port {port}: error ({e})")

def main():
    print("=" * 60)
    print("XREAL Eye Video Activation Tool")
    print("=" * 60)
    print(f"Target: {GLASSES_IP}")
    print(f"Control port: {PORT_CONTROL}")

    # Check initial video port status
    print("\n--- Initial Video Port Status ---")
    check_video_ports()

    # Connect to control channel
    print(f"\nConnecting to control channel {GLASSES_IP}:{PORT_CONTROL}...")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((GLASSES_IP, PORT_CONTROL))
        print("Connected!")

        # Read initial data
        sock.settimeout(1.0)
        try:
            initial = sock.recv(4096)
            print(f"\nInitial data received: {initial.hex()}")
            print(f"Length: {len(initial)} bytes")
        except socket.timeout:
            print("No initial data")
            initial = None

        # Try various video activation commands
        commands = [
            (create_ping_cmd(), "Ping/Keepalive"),
            (create_start_video_cmd_v1(), "Video Enable v1 (0x6A simple)"),
            (create_start_video_cmd_v2(), "Video Enable v2 (Protobuf 0x6A)"),
            (create_start_video_cmd_v4(), "Video Enable v4 (0x6A + IP)"),
            (create_start_video_cmd_v5(), "Video Enable v5 (0x286a header)"),
            (create_start_video_cmd_v3(), "Camera Config (OpenStream)"),
        ]

        for cmd, name in commands:
            response = try_send_command(sock, cmd, name)

            # Check if video ports opened after each command
            if response:
                check_video_ports()

            time.sleep(0.5)

        # Final port check
        print("\n" + "=" * 60)
        print("Final Video Port Status")
        print("=" * 60)
        check_video_ports()

        # Keep connection open and monitor
        print("\n--- Monitoring for data (10 seconds) ---")
        sock.settimeout(1.0)
        start = time.time()
        while time.time() - start < 10:
            try:
                data = sock.recv(4096)
                if data:
                    print(f"[{time.time()-start:.1f}s] Received: {data[:50].hex()}... ({len(data)} bytes)")
            except socket.timeout:
                pass

    except ConnectionRefusedError:
        print(f"Connection refused - control channel not available")
    except socket.timeout:
        print(f"Connection timeout - glasses not reachable")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        try:
            sock.close()
        except:
            pass
        print("\nDisconnected")

if __name__ == "__main__":
    main()
