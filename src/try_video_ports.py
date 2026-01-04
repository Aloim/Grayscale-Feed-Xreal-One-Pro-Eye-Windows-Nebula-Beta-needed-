"""
Focus on ports 52995 and 52997 which behave differently.
They don't respond to calibration - might be video ports.
"""

import socket
import struct
import time

GLASSES_IP = "169.254.2.1"

def hexdump(data: bytes, limit: int = 128):
    for i in range(0, min(len(data), limit), 16):
        chunk = data[i:i+16]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"  {i:04x}: {hex_str:<48} {ascii_str}")

def test_port(port: int, request: bytes, desc: str, wait_time: float = 0.5):
    """Test a single request on a port"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((GLASSES_IP, port))

        print(f"  {desc}: ", end="", flush=True)
        sock.sendall(request)
        time.sleep(wait_time)

        sock.settimeout(3)
        try:
            response = sock.recv(8192)
            if response:
                if len(response) > 20:
                    print(f"GOT {len(response)} bytes!")
                    hexdump(response)
                    return response
                else:
                    print(f"{len(response)} bytes: {response.hex()}")
            else:
                print("empty")
        except socket.timeout:
            print("timeout")

        sock.close()
    except Exception as e:
        print(f"error: {e}")

    return None

def main():
    print("="*60)
    print("TESTING VIDEO CANDIDATE PORTS")
    print("="*60)

    # Test headers from the protobuf analysis
    # CameraFrame uses field numbers 1-6
    # StreamRequest uses field 10 for open_stream

    requests = [
        # Simple headers we haven't fully tested
        (struct.pack(">H", 0x2843) + b'\x00\x00\x00\x00', "0x2843 empty"),
        (struct.pack(">H", 0x2843) + b'\x00\x00\x00\x01\x01', "0x2843 enable"),
        (struct.pack(">H", 0x2846) + b'\x00\x00\x00\x00', "0x2846 empty"),
        (struct.pack(">H", 0x2846) + b'\x00\x00\x00\x01\x01', "0x2846 enable"),

        # Try IMU header pattern but for video
        (struct.pack(">H", 0x2856) + struct.pack("<I", 0x80) + b'', "0x2856 flags=0x80"),

        # Match calibration response format
        (struct.pack(">H", 0x271f) + b'\x00\x00\x00\x06\x80\x00\x00\x19\x1a\x00', "calibration"),

        # Start command variations
        (b'\x00\x01', "raw 00 01"),
        (b'\x01\x00', "raw 01 00"),
        (b'\x01\x00\x00\x00', "raw 01 000000"),

        # Protobuf-style start
        (b'\x0a\x02\x08\x01', "proto: field1={field1=1}"),
        (b'\x52\x02\x08\x01', "proto: field10={field1=1}"),  # open_stream is field 10
    ]

    for port in [52995, 52997]:
        print(f"\n{'='*60}")
        print(f"PORT {port}")
        print(f"{'='*60}")

        for req, desc in requests:
            result = test_port(port, req, desc)
            if result and len(result) > 50:
                print(f"\n*** FOUND VIDEO DATA ON PORT {port}! ***\n")
            time.sleep(0.5)  # Rate limit

    # Also keep-alive on known working port and check for changes
    print(f"\n{'='*60}")
    print("MONITORING PORT 52998 (IMU) FOR FORMAT CLUES")
    print(f"{'='*60}")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((GLASSES_IP, 52998))

        print("Reading IMU data stream for 3 seconds...")
        end_time = time.time() + 3
        packets = []
        while time.time() < end_time:
            try:
                data = sock.recv(1024)
                if data:
                    packets.append(data)
            except:
                break

        print(f"Received {len(packets)} packets")
        if packets:
            print("First packet:")
            hexdump(packets[0])

            # Look for patterns
            sizes = [len(p) for p in packets]
            print(f"Packet sizes: min={min(sizes)}, max={max(sizes)}, avg={sum(sizes)//len(sizes)}")

        sock.close()
    except Exception as e:
        print(f"Error: {e}")

    print("\n" + "="*60)
    print("DONE")
    print("="*60)

if __name__ == "__main__":
    main()
