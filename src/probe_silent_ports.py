"""
Probe the silent ports (52990-52995, 52997) to find video stream.
These accept connections but don't send initial data.
"""

import socket
import struct
import time

GLASSES_IP = "169.254.2.1"

def hexdump(data: bytes, prefix: str = "  "):
    for i in range(0, min(len(data), 128), 16):
        chunk = data[i:i+16]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"{prefix}{i:04x}: {hex_str:<48} {ascii_str}")

def probe_port(port: int, request: bytes, description: str):
    """Send a request to a port and check response"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((GLASSES_IP, port))

        print(f"  Sending: {request.hex()}")
        sock.sendall(request)

        time.sleep(0.3)
        sock.settimeout(2)

        try:
            response = sock.recv(4096)
            if response:
                header = struct.unpack(">H", response[:2])[0] if len(response) >= 2 else 0
                print(f"  Response: {len(response)} bytes, header 0x{header:04x}")
                hexdump(response[:64])
                return response
            else:
                print(f"  Empty response")
        except socket.timeout:
            print(f"  No response")

        sock.close()
    except Exception as e:
        print(f"  Error: {e}")

    return None

def main():
    # Known headers that work
    calibration_request = bytes.fromhex('271f00000006800000191a00')

    # Different request types to try
    requests = [
        # Calibration request (known working)
        (bytes.fromhex('271f00000006800000191a00'), "calibration request 0x271f"),

        # Video/camera related guesses
        (bytes.fromhex('285600000000'), "0x2856 (V for video?)"),
        (bytes.fromhex('284300000000'), "0x2843 (C for camera?)"),
        (bytes.fromhex('285200000000'), "0x2852 (R for RGB?)"),
        (bytes.fromhex('284600000000'), "0x2846 (F for frame?)"),

        # Stream request variations
        (bytes.fromhex('2753000000000100'), "0x2753 with enable flag"),
        (bytes.fromhex('275400000000'), "0x2754"),
        (bytes.fromhex('275500000000'), "0x2755"),
        (bytes.fromhex('275600000000'), "0x2756"),
        (bytes.fromhex('275700000000'), "0x2757"),

        # Request with camera config (width=1280, height=720)
        (bytes.fromhex('2753000000000805001006d002'), "0x2753 with protobuf config"),

        # Simple start commands
        (bytes.fromhex('2af800000000'), "0x2af8 subscription header"),
        (bytes.fromhex('271000000000'), "0x2710 keepalive"),

        # Binary patterns that might mean "start"
        (bytes.fromhex('0001000000000001'), "simple enable"),
        (bytes.fromhex('010000000001'), "start stream"),
    ]

    # Test each silent port
    for port in [52990, 52991, 52992, 52993, 52994, 52995, 52997]:
        print(f"\n{'='*60}")
        print(f"PORT {port}")
        print(f"{'='*60}")

        for request, desc in requests[:5]:  # Test first 5 request types
            print(f"\n{desc}:")
            result = probe_port(port, request, desc)
            if result and len(result) > 10:
                print(f"  *** GOT SUBSTANTIAL RESPONSE! ***")
                break  # Found something interesting
            time.sleep(0.2)

    # Also try control port with more requests
    print(f"\n{'='*60}")
    print(f"PORT 52999 (control) - additional tests")
    print(f"{'='*60}")

    for request, desc in requests:
        print(f"\n{desc}:")
        result = probe_port(52999, request, desc)
        if result and len(result) > 100:
            print(f"  *** LARGE RESPONSE! ***")
        time.sleep(0.3)

if __name__ == "__main__":
    main()
