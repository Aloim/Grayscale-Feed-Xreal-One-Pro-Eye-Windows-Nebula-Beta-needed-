"""
Try subscribing to different camera/video services.

Based on analysis of nr_perception_head_tracking_remote messages.
"""

import socket
import struct
import time

GLASSES_IP = "169.254.2.1"
CONTROL_PORT = 52999

def encode_varint(value):
    result = []
    while value > 127:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)

def create_subscription_message(service_name: str, enable: bool = True) -> bytes:
    """
    Create a subscription message for a service.

    Format:
    - Header: 0x2af8 (2 bytes, big-endian)
    - Flags: 0xa5000000 (4 bytes, little-endian)
    - Metadata: 32 bytes (timestamps, etc - we'll use zeros)
    - Service name: UTF-8 string
    - Suffix: Protobuf with enable flag
    """
    header = b'\x2a\xf8'
    flags = struct.pack('<I', 0x000000a5)

    # Metadata (32 bytes) - use pattern from capture
    # 10 00 00 00 00 00 00 00  - 8 bytes
    # 10 82 79 48 f7 01 00 00  - timestamp? (8 bytes)
    # 22 00 00 00              - length? (4 bytes)
    # 60 b1 5f 40 f7 01 00 00  - timestamp? (8 bytes)
    # 63 00 00 00              - service name length (4 bytes)

    service_bytes = service_name.encode('utf-8')
    service_len = len(service_bytes)

    # Build metadata
    meta = bytes([0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])  # 8 bytes
    meta += struct.pack('<Q', int(time.time() * 1000))  # timestamp
    meta += struct.pack('<I', 0x22)  # ?
    meta += struct.pack('<Q', int(time.time() * 1000))  # timestamp
    meta += struct.pack('<I', service_len)  # service name length

    # Suffix protobuf: field 1 = nested { field 1 = id, field 2 = enable }
    inner = bytes([0x08]) + encode_varint(22348)  # Field 1 = ID
    inner += bytes([0x10]) + encode_varint(1 if enable else 0)  # Field 2 = enable
    suffix = bytes([0x0a, len(inner)]) + inner  # Field 1, length-delimited

    return header + flags + meta + service_bytes + suffix

def try_service(sock, service_name: str):
    """Try subscribing to a service and check response."""
    print(f"\n--- Trying: {service_name} ---")

    msg = create_subscription_message(service_name)
    print(f"Sending {len(msg)} bytes: {msg[:20].hex()}...{msg[-10:].hex()}")

    try:
        sock.sendall(msg)
        time.sleep(0.3)

        # Check for response
        sock.settimeout(1.0)
        try:
            response = sock.recv(4096)
            if response:
                print(f"Response ({len(response)} bytes): {response[:50].hex()}")
                # Check if it's an error or success
                if b'error' in response.lower() or b'fail' in response.lower():
                    print("  -> REJECTED")
                elif len(response) > 10:
                    print("  -> GOT DATA!")
                return response
        except socket.timeout:
            print("  -> No response (timeout)")
            return None

    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    print("=" * 60)
    print("XREAL Camera Service Discovery")
    print("=" * 60)
    print(f"Target: {GLASSES_IP}:{CONTROL_PORT}")

    # Services to try (based on naming patterns)
    services = [
        # Known working
        "nr_perception_head_tracking_remote",

        # Camera variations
        "nr_perception_rgb_camera_remote",
        "nr_perception_camera_remote",
        "nr_rgb_camera_remote",
        "nr_camera_remote",
        "nr_video_remote",
        "nr_perception_video_remote",

        # Stream variations
        "nr_rgb_stream_remote",
        "nr_camera_stream_remote",
        "nr_video_stream_remote",

        # Simple names
        "nr_rgb_camera",
        "nr_camera",
        "nr_video",
        "nr_stream",

        # Eye camera specific
        "nr_eye_camera_remote",
        "nr_perception_eye_camera_remote",

        # Frame/image variations
        "nr_perception_rgb_frame_remote",
        "nr_frame_remote",
        "nr_image_remote",
    ]

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        print(f"\nConnecting to {GLASSES_IP}:{CONTROL_PORT}...")
        sock.connect((GLASSES_IP, CONTROL_PORT))
        print("Connected!")

        # Read any initial data
        sock.settimeout(1.0)
        try:
            initial = sock.recv(4096)
            if initial:
                print(f"Initial data: {initial[:50].hex()}")
        except socket.timeout:
            pass

        # Try each service
        responses = {}
        for service in services:
            resp = try_service(sock, service)
            if resp and len(resp) > 20:
                responses[service] = resp
            time.sleep(0.2)

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        if responses:
            print("Services with responses:")
            for service, resp in responses.items():
                print(f"  {service}: {len(resp)} bytes")
        else:
            print("No services responded with data")

        # Check if any new ports opened
        print("\nChecking for new ports...")
        for port in [50051, 50356, 50357, 50358, 52994, 52995]:
            try:
                test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test.settimeout(0.5)
                result = test.connect_ex((GLASSES_IP, port))
                test.close()
                if result == 0:
                    print(f"  Port {port}: OPEN!")
            except:
                pass

        sock.close()

    except ConnectionRefusedError:
        print("Connection refused - glasses not connected?")
    except socket.timeout:
        print("Connection timeout")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
