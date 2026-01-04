"""
Try video headers 0x2856 and 0x2852 with different payloads.
These returned error 0xffde meaning they're recognized but need correct payload.
"""

import socket
import struct
import time

GLASSES_IP = "169.254.2.1"
CONTROL_PORT = 52999

def encode_varint(value: int) -> bytes:
    result = []
    while value > 127:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)

def hexdump(data: bytes, prefix: str = "  "):
    for i in range(0, min(len(data), 256), 16):
        chunk = data[i:i+16]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"{prefix}{i:04x}: {hex_str:<48} {ascii_str}")

def try_request(header: int, payload: bytes, desc: str) -> bytes:
    """Send request with fresh connection"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((GLASSES_IP, CONTROL_PORT))

        msg = struct.pack(">H", header) + struct.pack("<I", len(payload)) + payload
        print(f"\n{desc}:")
        print(f"  Header: 0x{header:04x}, Payload len: {len(payload)}")
        print(f"  Full msg: {msg.hex()}")

        sock.sendall(msg)
        time.sleep(0.3)

        sock.settimeout(2)
        try:
            response = sock.recv(8192)
            if response:
                resp_header = struct.unpack(">H", response[:2])[0] if len(response) >= 2 else 0
                print(f"  Response: {len(response)} bytes, header 0x{resp_header:04x}")

                if resp_header == 0xffde:
                    print(f"  -> ERROR response")
                elif len(response) > 20:
                    print(f"  -> SUCCESS! Got data")
                    hexdump(response[:128])

                return response
            else:
                print(f"  Empty response (might be accepted)")
        except socket.timeout:
            print(f"  No response")

        sock.close()
    except Exception as e:
        print(f"  Error: {e}")

    return None

def main():
    print("="*60)
    print("TESTING VIDEO HEADERS WITH PAYLOADS")
    print("="*60)

    # Payloads to try
    # Based on calibration request pattern: 800000191a00

    # Test 0x2856 (V for video?)
    print("\n" + "="*60)
    print("HEADER 0x2856 (Video?)")
    print("="*60)

    payloads_2856 = [
        (b'', "empty"),
        (b'\x01', "enable=1"),
        (b'\x00\x01', "00 01"),
        (b'\x01\x00', "01 00"),
        (bytes.fromhex('800000191a00'), "calibration-style"),
        (bytes.fromhex('0801'), "protobuf field1=1"),
        (bytes.fromhex('08011001'), "protobuf field1=1,field2=1"),
        (bytes.fromhex('0805001006d002'), "protobuf 1280x720"),
        # Camera config: width=1280(0x500), height=720(0x2d0), fps=30(0x1e)
        (bytes.fromhex('0880100610d0051a0359555620011e'), "camera config proto"),
        # Simple structs
        (struct.pack("<HH", 1280, 720), "1280x720 LE"),
        (struct.pack(">HH", 1280, 720), "1280x720 BE"),
        (struct.pack("<HHBB", 1280, 720, 30, 1), "1280x720 30fps enable"),
    ]

    for payload, desc in payloads_2856:
        try_request(0x2856, payload, desc)
        time.sleep(0.2)

    # Test 0x2852 (R for RGB?)
    print("\n" + "="*60)
    print("HEADER 0x2852 (RGB?)")
    print("="*60)

    for payload, desc in payloads_2856[:8]:  # Reuse payloads
        try_request(0x2852, payload, desc)
        time.sleep(0.2)

    # Also try 0x2853 (S for stream?)
    print("\n" + "="*60)
    print("HEADER 0x2853 (Stream?)")
    print("="*60)

    for payload, desc in payloads_2856[:5]:
        try_request(0x2853, payload, desc)
        time.sleep(0.2)

    # Try with different flag values
    print("\n" + "="*60)
    print("TESTING FLAG VALUES")
    print("="*60)

    # The calibration uses flags 0x00000006
    # Let's try 0x2856 with different flags
    for flags in [0x00000001, 0x00000006, 0x00000080, 0x000000a5]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((GLASSES_IP, CONTROL_PORT))

            payload = b'\x01'
            msg = struct.pack(">H", 0x2856) + struct.pack("<I", flags) + payload
            print(f"\n0x2856 with flags 0x{flags:08x}:")
            print(f"  Sending: {msg.hex()}")

            sock.sendall(msg)
            time.sleep(0.3)

            sock.settimeout(2)
            try:
                response = sock.recv(4096)
                if response:
                    resp_header = struct.unpack(">H", response[:2])[0] if len(response) >= 2 else 0
                    print(f"  Response: {len(response)} bytes, header 0x{resp_header:04x}")
                    if resp_header != 0xffde and len(response) > 12:
                        hexdump(response[:64])
            except socket.timeout:
                print(f"  No response")

            sock.close()
        except Exception as e:
            print(f"  Error: {e}")

    print("\n" + "="*60)
    print("DONE")
    print("="*60)

if __name__ == "__main__":
    main()
