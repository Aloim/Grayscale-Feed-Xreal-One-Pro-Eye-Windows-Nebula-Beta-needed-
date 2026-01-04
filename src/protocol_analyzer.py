"""
XREAL Eye Protocol Analyzer

Analyze binary data from discovered ports to understand the protocol format.
"""

import struct
from typing import List, Tuple, Dict, Any

# Raw data captured from glasses
RAW_DATA = {
    52996: bytes.fromhex("273100000020000000000000000068733871440100005e960000000000000000000000"),
    52998: bytes.fromhex("283600000080a8787300000000004034595e44010000bd160000000000000b00"),
    52999: bytes.fromhex("278a000000091a0708011533335f42278a000000091a070802159a992b42"),
}

PORT_NAMES = {
    52996: "Metadata",
    52998: "IMU",
    52999: "Control",
}

def analyze_packet(port: int, data: bytes) -> Dict[str, Any]:
    """Analyze a packet and extract structure"""
    result = {
        "port": port,
        "name": PORT_NAMES.get(port, "Unknown"),
        "length": len(data),
        "raw_hex": data.hex(),
    }

    # Try different header interpretations
    if len(data) >= 2:
        # Big endian 16-bit
        result["header_be16"] = struct.unpack(">H", data[:2])[0]
        # Little endian 16-bit
        result["header_le16"] = struct.unpack("<H", data[:2])[0]

    if len(data) >= 4:
        # Big endian 32-bit
        result["header_be32"] = struct.unpack(">I", data[:4])[0]
        # Little endian 32-bit
        result["header_le32"] = struct.unpack("<I", data[:4])[0]

    # Check for varint at offset 0
    varint_val, varint_len = decode_varint(data)
    if varint_val is not None:
        result["varint_at_0"] = (varint_val, varint_len)

    # Check for length-prefixed format: [len:4][data]
    if len(data) >= 4:
        potential_len = struct.unpack("<I", data[:4])[0]
        if potential_len == len(data) - 4:
            result["length_prefixed_le"] = True
        potential_len = struct.unpack(">I", data[:4])[0]
        if potential_len == len(data) - 4:
            result["length_prefixed_be"] = True

    # Check for pattern [type:1][len:1][data] or [type:1][len:2][data]
    if len(data) >= 2:
        type_byte = data[0]
        len_byte = data[1]
        if len_byte == len(data) - 2:
            result["type_len_format"] = f"type=0x{type_byte:02x}, len={len_byte}"

    # Try to find floats (IMU data is typically floats)
    floats = extract_floats(data)
    if floats:
        result["floats_le"] = floats[:8]  # First 8 floats

    return result

def decode_varint(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Decode a protobuf-style varint"""
    result = 0
    shift = 0
    length = 0

    while offset + length < len(data):
        b = data[offset + length]
        result |= (b & 0x7f) << shift
        length += 1
        if not (b & 0x80):
            return result, length
        shift += 7
        if length > 10:
            break

    return None, 0

def extract_floats(data: bytes) -> List[float]:
    """Extract little-endian floats from data"""
    floats = []
    for i in range(0, len(data) - 3, 4):
        try:
            val = struct.unpack("<f", data[i:i+4])[0]
            # Filter reasonable float values
            if -1e10 < val < 1e10 and val != 0:
                floats.append((i, val))
        except:
            pass
    return floats

def analyze_control_channel(data: bytes):
    """Special analysis for control channel which has repeating pattern"""
    print("\n=== Control Channel Deep Analysis ===")
    print(f"Total length: {len(data)} bytes")
    print(f"Raw: {data.hex()}")

    # Split by 278a pattern
    parts = data.hex().split("278a")
    print(f"\nSplit by '278a' pattern: {len(parts)} parts")
    for i, part in enumerate(parts):
        if part:
            print(f"  Part {i}: {part}")

    # Check if it's two messages concatenated
    if len(data) == 30:
        msg1 = data[:15]
        msg2 = data[15:]
        print(f"\nAs two 15-byte messages:")
        print(f"  Msg1: {msg1.hex()}")
        print(f"  Msg2: {msg2.hex()}")

        # Parse each message
        for i, msg in enumerate([msg1, msg2], 1):
            if len(msg) >= 6:
                header = msg[:2]
                flags = msg[2:6]
                payload = msg[6:]
                print(f"\n  Message {i}:")
                print(f"    Header: {header.hex()} (0x{struct.unpack('>H', header)[0]:04x})")
                print(f"    Flags: {flags.hex()}")
                print(f"    Payload: {payload.hex()}")

                # Try parsing payload bytes
                print(f"    Payload bytes: {' '.join(f'{b:02x}' for b in payload)}")
                # Check for embedded float at end
                if len(payload) >= 4:
                    try:
                        last_float = struct.unpack("<f", payload[-4:])[0]
                        print(f"    Last 4 bytes as float: {last_float}")
                    except:
                        pass

def analyze_imu_data(data: bytes):
    """Special analysis for IMU data"""
    print("\n=== IMU Data Deep Analysis ===")
    print(f"Total length: {len(data)} bytes")
    print(f"Raw: {data.hex()}")

    # Common IMU packet format: [header][timestamp][gyro_xyz][accel_xyz]
    print("\nByte-by-byte analysis:")
    for i in range(0, len(data), 8):
        chunk = data[i:i+8]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        print(f"  {i:3d}-{i+len(chunk)-1:3d}: {hex_str}")

    # Try float extraction at various offsets
    print("\nTrying float extraction:")
    for offset in [0, 4, 8, 12, 16, 20]:
        if offset + 24 <= len(data):
            try:
                vals = struct.unpack("<6f", data[offset:offset+24])
                # Check if values look like IMU data
                reasonable = all(-100 < v < 100 for v in vals)
                marker = " <-- REASONABLE IMU VALUES" if reasonable else ""
                print(f"  Offset {offset}: {[f'{v:.4f}' for v in vals]}{marker}")
            except:
                pass

def analyze_metadata(data: bytes):
    """Special analysis for metadata"""
    print("\n=== Metadata Deep Analysis ===")
    print(f"Total length: {len(data)} bytes")
    print(f"Raw: {data.hex()}")

    print("\nByte-by-byte analysis:")
    for i in range(0, len(data), 8):
        chunk = data[i:i+8]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        print(f"  {i:3d}-{i+len(chunk)-1:3d}: {hex_str}")

    # Check for timestamp-like values
    if len(data) >= 16:
        print("\nPossible 32-bit values:")
        for offset in range(0, len(data) - 3, 4):
            val_le = struct.unpack("<I", data[offset:offset+4])[0]
            val_be = struct.unpack(">I", data[offset:offset+4])[0]
            print(f"  Offset {offset}: LE=0x{val_le:08x} ({val_le}), BE=0x{val_be:08x} ({val_be})")

def main():
    print("=" * 60)
    print("XREAL Eye Protocol Analysis")
    print("=" * 60)

    for port, data in RAW_DATA.items():
        print(f"\n{'='*60}")
        result = analyze_packet(port, data)
        print(f"Port {port} ({result['name']}):")
        print(f"  Length: {result['length']} bytes")
        print(f"  Header BE16: 0x{result.get('header_be16', 0):04x}")
        print(f"  Header LE16: 0x{result.get('header_le16', 0):04x}")
        print(f"  Header BE32: 0x{result.get('header_be32', 0):08x}")
        print(f"  Header LE32: 0x{result.get('header_le32', 0):08x}")

        if result.get('varint_at_0'):
            v, l = result['varint_at_0']
            print(f"  Varint at 0: value={v}, length={l}")

        if result.get('length_prefixed_le'):
            print(f"  Format: Length-prefixed (LE)")
        if result.get('length_prefixed_be'):
            print(f"  Format: Length-prefixed (BE)")
        if result.get('type_len_format'):
            print(f"  Format: {result['type_len_format']}")

        if result.get('floats_le'):
            print(f"  Floats found: {result['floats_le'][:4]}")

    # Deep analysis
    analyze_control_channel(RAW_DATA[52999])
    analyze_imu_data(RAW_DATA[52998])
    analyze_metadata(RAW_DATA[52996])

    # Pattern observation
    print("\n" + "=" * 60)
    print("PATTERN OBSERVATIONS")
    print("=" * 60)
    print("""
1. All packets start with 0x27 or 0x28 (39 or 40 decimal)
   - 0x27 = Control (278a), Metadata (2731)
   - 0x28 = IMU (2836)

2. Second byte appears to be message subtype:
   - 0x8a (138) = Control messages
   - 0x31 (49) = Metadata
   - 0x36 (54) = IMU data

3. Control channel has TWO concatenated messages (278a...278a...)
   - Each 15 bytes, starting with 278a
   - Contains embedded floats at end

4. Bytes 2-5 (0x00000000) = likely sequence number or flags

5. IMU data structure appears to be:
   - Header: 2 bytes
   - Timestamp/sequence: 4 bytes
   - Data payload: variable
""")

if __name__ == "__main__":
    main()
