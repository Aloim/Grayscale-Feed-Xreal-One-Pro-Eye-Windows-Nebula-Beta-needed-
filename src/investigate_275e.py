"""
Investigate header 0x275e which returned 4096 bytes.
Also test 0x273d which responded to HTTP/2 preface.
"""

import socket
import struct
import time

GLASSES_IP = "169.254.2.1"
CONTROL_PORT = 52999

def hexdump(data: bytes, prefix: str = "  "):
    """Pretty print hex dump"""
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"{prefix}{i:04x}: {hex_str:<48} {ascii_str}")

def test_header(header: int, payload: bytes = b'', description: str = ""):
    """Test a specific header with fresh connection"""
    print(f"\n{'='*60}")
    print(f"Testing header 0x{header:04x} {description}")
    print(f"{'='*60}")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((GLASSES_IP, CONTROL_PORT))
        print("Connected")

        # Build message
        msg = struct.pack(">H", header) + struct.pack("<I", 0) + payload
        print(f"Sending: {msg.hex()}")

        sock.sendall(msg)
        time.sleep(0.3)

        # Receive response
        sock.settimeout(2)
        try:
            response = sock.recv(8192)
            print(f"\nResponse: {len(response)} bytes")

            if len(response) >= 2:
                resp_header = struct.unpack(">H", response[:2])[0]
                print(f"Response header: 0x{resp_header:04x}")

            if len(response) >= 6:
                resp_flags = struct.unpack("<I", response[2:6])[0]
                print(f"Response flags: 0x{resp_flags:08x}")

            # Check for ASCII content
            try:
                text = response[6:].decode('utf-8', errors='ignore')
                if text.isprintable() or '\n' in text:
                    print(f"\nASCII content found:")
                    print(text[:500])
            except:
                pass

            # Hex dump first 256 bytes
            print(f"\nHex dump (first 256 bytes):")
            hexdump(response[:256])

            return response

        except socket.timeout:
            print("No response (timeout)")
            return None

    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        try:
            sock.close()
        except:
            pass

def test_variations():
    """Test header variations"""

    # Test 0x275e with different flag values
    print("\n" + "="*60)
    print("TESTING 0x275e VARIATIONS")
    print("="*60)

    # Basic test
    test_header(0x275e, b'', "basic")

    # With payload similar to calibration request
    test_header(0x275e, bytes.fromhex('800000191a00'), "with calibration-style payload")

    # Test 0x273d (responded to HTTP/2)
    print("\n" + "="*60)
    print("TESTING 0x273d")
    print("="*60)

    test_header(0x273d, b'', "basic")
    test_header(0x273d, bytes.fromhex('0001'), "with 0001")

    # Test related headers
    for h in [0x275f, 0x275d, 0x273e, 0x273c]:
        test_header(h, b'', f"neighbor of responsive header")

def scan_ports_for_data():
    """Check what data each port sends"""
    print("\n" + "="*60)
    print("CHECKING ALL OPEN PORTS FOR DATA")
    print("="*60)

    for port in range(52990, 53000):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((GLASSES_IP, port))

            # Wait for data
            try:
                data = sock.recv(1024)
                if data:
                    header = struct.unpack(">H", data[:2])[0] if len(data) >= 2 else 0
                    print(f"Port {port}: {len(data)} bytes, header 0x{header:04x}")
                    if len(data) > 6:
                        hexdump(data[:64], "  ")
                else:
                    print(f"Port {port}: Connected but no data")
            except socket.timeout:
                print(f"Port {port}: Connected, no initial data")

            sock.close()
        except Exception as e:
            print(f"Port {port}: {e}")

def main():
    print("="*60)
    print("INVESTIGATING RESPONSIVE HEADERS")
    print("="*60)

    # First scan ports
    scan_ports_for_data()

    # Then test header variations
    test_variations()

    print("\n" + "="*60)
    print("DONE")
    print("="*60)

if __name__ == "__main__":
    main()
