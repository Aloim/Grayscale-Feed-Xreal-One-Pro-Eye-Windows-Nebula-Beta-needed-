"""
XREAL Eye TCP Stream Analyzer

Connect to open TCP ports and analyze streaming data.
Based on findings that glasses use TCP/IP over NCM.
"""

import socket
import struct
import time
import threading
from typing import Optional, Callable
from collections import defaultdict

# XREAL glasses network config
GLASSES_IP = "169.254.2.1"

# Discovered open ports (from live testing)
LIVE_PORTS = {
    52996: "Metadata",
    52998: "IMU",
    52999: "Control",
}

# Ports from Nebula capture (video active state)
NEBULA_PORTS = {
    50346: "Control (Nebula)",
    50356: "Video (Nebula)",
    50361: "Metadata (Nebula)",
}


def decode_protobuf_packet(data: bytes) -> dict:
    """Decode a simple protobuf packet from control channel"""
    result = {
        'raw': data.hex(),
        'length': len(data),
        'fields': []
    }

    if len(data) < 6:
        return result

    # Parse header: [type:2][flags:4]
    header = struct.unpack(">H", data[:2])[0]
    flags = struct.unpack("<I", data[2:6])[0]

    result['header'] = f"0x{header:04x}"
    result['flags'] = f"0x{flags:08x}"

    # Parse payload starting at offset 6
    payload = data[6:]
    pos = 0

    while pos < len(payload):
        if pos + 1 > len(payload):
            break

        # Parse field tag (varint, but usually single byte)
        tag = payload[pos]
        field_num = tag >> 3
        wire_type = tag & 0x07
        pos += 1

        if wire_type == 0:  # Varint
            value = 0
            shift = 0
            while pos < len(payload):
                b = payload[pos]
                value |= (b & 0x7f) << shift
                pos += 1
                if not (b & 0x80):
                    break
                shift += 7
            result['fields'].append({
                'field': field_num,
                'type': 'varint',
                'value': value
            })

        elif wire_type == 2:  # Length-delimited
            if pos >= len(payload):
                break
            length = payload[pos]
            pos += 1
            value = payload[pos:pos+length]
            pos += length

            # Try to decode nested protobuf
            nested = decode_nested_protobuf(value)
            result['fields'].append({
                'field': field_num,
                'type': 'bytes',
                'length': length,
                'value': nested if nested else value.hex()
            })

        elif wire_type == 5:  # 32-bit (float)
            if pos + 4 > len(payload):
                break
            value = struct.unpack("<f", payload[pos:pos+4])[0]
            pos += 4
            result['fields'].append({
                'field': field_num,
                'type': 'float',
                'value': value
            })

        else:
            # Unknown wire type
            result['fields'].append({
                'field': field_num,
                'type': f'unknown_{wire_type}',
                'value': 'N/A'
            })
            break

    return result


def decode_nested_protobuf(data: bytes) -> Optional[dict]:
    """Decode nested protobuf message"""
    if len(data) < 2:
        return None

    result = {'fields': []}
    pos = 0

    while pos < len(data):
        if pos + 1 > len(data):
            break

        tag = data[pos]
        field_num = tag >> 3
        wire_type = tag & 0x07
        pos += 1

        if wire_type == 0:  # Varint
            value = 0
            shift = 0
            while pos < len(data):
                b = data[pos]
                value |= (b & 0x7f) << shift
                pos += 1
                if not (b & 0x80):
                    break
                shift += 7
            result['fields'].append((field_num, 'varint', value))

        elif wire_type == 5:  # 32-bit float
            if pos + 4 > len(data):
                break
            value = struct.unpack("<f", data[pos:pos+4])[0]
            pos += 4
            result['fields'].append((field_num, 'float', f"{value:.4f}"))

        else:
            break

    return result if result['fields'] else None


def monitor_tcp_stream(host: str, port: int, duration: float = 10.0,
                       on_data: Optional[Callable] = None):
    """Connect to TCP port and monitor stream"""
    print(f"\n--- Monitoring {host}:{port} ---")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        print(f"Connected to {port}")

        # Receive initial data
        sock.settimeout(1.0)
        start = time.time()
        packets = []

        while time.time() - start < duration:
            try:
                data = sock.recv(4096)
                if data:
                    elapsed = time.time() - start
                    packets.append({
                        'time': elapsed,
                        'data': data
                    })

                    if on_data:
                        on_data(elapsed, data)
                    else:
                        # Default: print decoded packet
                        decoded = decode_protobuf_packet(data)
                        print(f"[{elapsed:.2f}s] {len(data)} bytes")
                        print(f"  Header: {decoded.get('header', 'N/A')}, Flags: {decoded.get('flags', 'N/A')}")
                        for field in decoded.get('fields', []):
                            print(f"  Field {field['field']}: {field['type']} = {field['value']}")

            except socket.timeout:
                pass
            except Exception as e:
                print(f"Error: {e}")
                break

        sock.close()
        return packets

    except ConnectionRefusedError:
        print(f"Connection refused on port {port}")
        return []
    except socket.timeout:
        print(f"Connection timeout on port {port}")
        return []
    except Exception as e:
        print(f"Error: {e}")
        return []


def analyze_all_streams():
    """Connect to all open ports and analyze streams simultaneously"""
    print("=" * 60)
    print("XREAL Eye TCP Stream Analysis")
    print("=" * 60)
    print(f"Target: {GLASSES_IP}")

    # Check which ports are open
    print("\n--- Port Status ---")
    open_ports = []
    all_ports = {**LIVE_PORTS, **NEBULA_PORTS}

    for port, name in sorted(all_ports.items()):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((GLASSES_IP, port))
            sock.close()

            status = "OPEN" if result == 0 else "closed"
            marker = " ***" if result == 0 else ""
            print(f"  {port}: {name} - {status}{marker}")

            if result == 0:
                open_ports.append((port, name))
        except:
            print(f"  {port}: {name} - error")

    if not open_ports:
        print("\nNo open ports found!")
        return

    # Monitor each open port
    for port, name in open_ports:
        print(f"\n{'='*60}")
        print(f"Monitoring {name} (port {port})")
        print("="*60)

        packets = monitor_tcp_stream(GLASSES_IP, port, duration=5.0)

        if packets:
            print(f"\nTotal packets: {len(packets)}")
            total_bytes = sum(len(p['data']) for p in packets)
            print(f"Total bytes: {total_bytes}")

            # Analyze patterns
            if len(packets) > 1:
                intervals = [packets[i+1]['time'] - packets[i]['time']
                           for i in range(len(packets)-1)]
                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    rate = 1.0 / avg_interval if avg_interval > 0 else 0
                    print(f"Average rate: {rate:.1f} packets/sec")


def send_video_request():
    """Try to send a video request on the control channel"""
    print("\n" + "=" * 60)
    print("Attempting Video Request via Control Channel")
    print("=" * 60)

    control_port = 52999

    # Build request messages to try
    requests = [
        # Format: [header:2][flags:4][payload]
        # Request 1: OpenStreamRequest-style (protobuf)
        build_open_stream_request(),

        # Request 2: Simple video enable
        bytes.fromhex("278a00000009") + bytes([0x68, 0x01]),  # 0x68 = RGB switch

        # Request 3: Different message type for video
        bytes.fromhex("2800") + struct.pack("<I", 1) + bytes([0x01]),  # Type 0x2800

        # Request 4: Based on IMU header (0x2836) but for video
        bytes.fromhex("2856") + struct.pack("<I", 1) + bytes([0x01]),  # Type 0x2856 (video?)
    ]

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((GLASSES_IP, control_port))
        print(f"Connected to control channel (port {control_port})")

        # Receive any initial data
        sock.settimeout(1.0)
        try:
            initial = sock.recv(4096)
            if initial:
                print(f"Initial data: {initial.hex()} ({len(initial)} bytes)")
        except socket.timeout:
            print("No initial data")

        # Try each request
        for i, request in enumerate(requests):
            print(f"\n--- Request {i+1} ---")
            print(f"Sending: {request.hex()}")

            try:
                sock.sendall(request)
                time.sleep(0.5)

                sock.settimeout(2.0)
                response = sock.recv(4096)
                print(f"Response: {response.hex()} ({len(response)} bytes)")

                # Decode response
                decoded = decode_protobuf_packet(response)
                print(f"  Decoded: {decoded}")

                # Check if video ports opened
                for port in [50356, 5555]:
                    test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    test_sock.settimeout(0.5)
                    result = test_sock.connect_ex((GLASSES_IP, port))
                    test_sock.close()
                    if result == 0:
                        print(f"  *** VIDEO PORT {port} IS NOW OPEN! ***")

            except socket.timeout:
                print("No response (timeout)")
            except Exception as e:
                print(f"Error: {e}")
                break

        sock.close()

    except Exception as e:
        print(f"Connection failed: {e}")


def build_open_stream_request() -> bytes:
    """Build an OpenStreamRequest protobuf message"""
    # Camera config (nested in field 1)
    camera_config = b""
    camera_config += bytes([0x08]) + encode_varint(1280)  # field 1: width
    camera_config += bytes([0x10]) + encode_varint(720)   # field 2: height
    camera_config += bytes([0x18]) + encode_varint(30)    # field 3: fps
    camera_config += bytes([0x22, len(b"YUV420")]) + b"YUV420"  # field 4: format

    # Wrap in field 1 (open_stream)
    open_stream = bytes([0x0a, len(camera_config)]) + camera_config

    # Add header (using observed format)
    header = bytes.fromhex("278a")  # Message type
    flags = struct.pack("<I", 9)     # Flags

    return header + flags + open_stream


def encode_varint(value: int) -> bytes:
    """Encode integer as varint"""
    result = []
    while value > 127:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def main():
    # First, analyze existing streams
    analyze_all_streams()

    # Then try to activate video
    send_video_request()

    # Final port check
    print("\n" + "=" * 60)
    print("Final Port Status")
    print("=" * 60)

    for port in [50051, 50346, 50356, 50361, 5555, 52996, 52998, 52999]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((GLASSES_IP, port))
            sock.close()
            status = "OPEN" if result == 0 else "closed"
            marker = " ***" if result == 0 else ""
            print(f"  {port}: {status}{marker}")
        except:
            print(f"  {port}: error")


if __name__ == "__main__":
    main()
