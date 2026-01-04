"""
Parse USB NCM capture to extract TCP payloads.

USB NCM structure:
- USB bulk packets contain NCM Transfer Headers (NTH16)
- NTH16 contains pointers to NCM Datagram Pointers (NDP16)
- NDP16 contains pointers to Ethernet frames
- Ethernet frames contain IP/TCP data
"""

from scapy.all import rdpcap, Raw
import struct

CAPTURE_FILE = "../Downloads/Nebula_Windows_20250813/WindowsNebulaAppUSBRecording.pcapng"

# NCM signatures
NTH16_SIGNATURE = b"NCMH"  # 0x484d434e
NDP16_SIGNATURE = b"NCM0"  # 0x304d434e

def parse_nth16(data):
    """Parse NCM Transfer Header (NTH16)"""
    if len(data) < 12:
        return None
    if data[:4] != NTH16_SIGNATURE:
        return None

    header_len = struct.unpack("<H", data[4:6])[0]
    seq = struct.unpack("<H", data[6:8])[0]
    block_len = struct.unpack("<H", data[8:10])[0]
    ndp_index = struct.unpack("<H", data[10:12])[0]

    return {
        'header_len': header_len,
        'sequence': seq,
        'block_len': block_len,
        'ndp_index': ndp_index
    }

def parse_ndp16(data, offset):
    """Parse NCM Datagram Pointer (NDP16)"""
    if offset + 8 > len(data):
        return None

    ndp = data[offset:]
    if ndp[:4] != NDP16_SIGNATURE:
        return None

    length = struct.unpack("<H", ndp[4:6])[0]
    # Next pointer at offset 6

    # Datagram entries start at offset 8
    entries = []
    pos = 8
    while pos + 4 <= len(ndp) and pos < length:
        dg_index = struct.unpack("<H", ndp[pos:pos+2])[0]
        dg_len = struct.unpack("<H", ndp[pos+2:pos+4])[0]
        if dg_index == 0 and dg_len == 0:
            break
        entries.append((dg_index, dg_len))
        pos += 4

    return entries

def extract_ethernet_frame(data, offset, length):
    """Extract Ethernet frame from NCM datagram"""
    if offset + length > len(data):
        return None
    return data[offset:offset+length]

def parse_ip_header(eth_frame):
    """Parse IP header from Ethernet frame"""
    if len(eth_frame) < 34:  # 14 eth + 20 ip minimum
        return None

    # Check Ethernet type (IP = 0x0800)
    eth_type = struct.unpack(">H", eth_frame[12:14])[0]
    if eth_type != 0x0800:
        return None

    ip_start = 14
    ip_header = eth_frame[ip_start:ip_start+20]

    version_ihl = ip_header[0]
    ihl = (version_ihl & 0x0f) * 4
    protocol = ip_header[9]
    src_ip = ".".join(str(b) for b in ip_header[12:16])
    dst_ip = ".".join(str(b) for b in ip_header[16:20])

    return {
        'ihl': ihl,
        'protocol': protocol,
        'src': src_ip,
        'dst': dst_ip,
        'payload_offset': ip_start + ihl
    }

def parse_tcp_header(eth_frame, ip_offset):
    """Parse TCP header"""
    if len(eth_frame) < ip_offset + 20:
        return None

    tcp = eth_frame[ip_offset:]
    src_port = struct.unpack(">H", tcp[0:2])[0]
    dst_port = struct.unpack(">H", tcp[2:4])[0]
    data_offset = ((tcp[12] >> 4) & 0x0f) * 4

    return {
        'src_port': src_port,
        'dst_port': dst_port,
        'data_offset': data_offset,
        'payload_offset': ip_offset + data_offset
    }

def main():
    print("Loading capture file...")
    packets = rdpcap(CAPTURE_FILE)
    print(f"Loaded {len(packets)} packets")

    # Look for NCM data
    ncm_packets = []
    tcp_streams = {}

    print("\nSearching for NCM packets...")

    for i, pkt in enumerate(packets):
        if Raw in pkt:
            data = bytes(pkt[Raw].load)

            # Look for NCM header
            if data[:4] == NTH16_SIGNATURE:
                nth = parse_nth16(data)
                if nth and nth['ndp_index'] > 0:
                    entries = parse_ndp16(data, nth['ndp_index'])
                    if entries:
                        for dg_idx, dg_len in entries:
                            eth_frame = extract_ethernet_frame(data, dg_idx, dg_len)
                            if eth_frame:
                                ip = parse_ip_header(eth_frame)
                                if ip and ip['protocol'] == 6:  # TCP
                                    tcp = parse_tcp_header(eth_frame, ip['payload_offset'])
                                    if tcp:
                                        payload = eth_frame[tcp['payload_offset']:]
                                        if len(payload) > 0:
                                            key = f"{ip['src']}:{tcp['src_port']} -> {ip['dst']}:{tcp['dst_port']}"
                                            if key not in tcp_streams:
                                                tcp_streams[key] = []
                                            tcp_streams[key].append({
                                                'pkt': i,
                                                'data': payload
                                            })

        if i > 0 and i % 100000 == 0:
            print(f"  Processed {i} packets, found {len(tcp_streams)} TCP streams...")

    print(f"\nFound {len(tcp_streams)} TCP streams")

    # Show streams
    for key, msgs in sorted(tcp_streams.items(), key=lambda x: len(x[1]), reverse=True)[:20]:
        print(f"\n{key}: {len(msgs)} messages")
        if msgs:
            first = msgs[0]['data'][:50]
            print(f"  First: {first.hex()}")

    # Look for control channels
    print("\n" + "=" * 60)
    print("Control Channel Messages (ports 50346, 52999)")
    print("=" * 60)

    for key, msgs in tcp_streams.items():
        if "50346" in key or "52999" in key:
            print(f"\n{key}: {len(msgs)} messages")
            for msg in msgs[:10]:
                data = msg['data']
                print(f"  [{msg['pkt']}] {data.hex()[:100]}...")

if __name__ == "__main__":
    main()
