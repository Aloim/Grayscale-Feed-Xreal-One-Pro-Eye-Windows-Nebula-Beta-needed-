"""
Find the video activation command in USB capture.

USB packet format:
- Bytes 0-27: USB header
- Bytes 28-31: "ncmh" for NCM packets
- Then NCM + Ethernet + IP + TCP
"""

from scapy.all import rdpcap, Raw
import struct
from collections import defaultdict

CAPTURE_FILE = "../Downloads/Nebula_Windows_20250813/WindowsNebulaAppUSBRecording.pcapng"

def parse_usb_ncm_packet(data):
    """Parse USB packet containing NCM data"""
    # Check for NCM header after USB header
    ncm_offset = data.find(b'ncmh')
    if ncm_offset < 0:
        return None

    # NCM header is 12 bytes
    ncm_header = data[ncm_offset:ncm_offset+12]
    if len(ncm_header) < 12:
        return None

    # Find Ethernet frame (starts with MAC addresses)
    # Look for Ethernet type 0x0800 (IP)
    eth_offset = None
    for i in range(ncm_offset, len(data) - 20):
        if data[i+12:i+14] == b'\x08\x00':  # IP
            if data[i+14] == 0x45:  # IPv4, IHL=5
                eth_offset = i
                break

    if eth_offset is None:
        return None

    eth_frame = data[eth_offset:]

    # Parse IP header (starts at eth + 14)
    ip_start = 14
    if len(eth_frame) < ip_start + 20:
        return None

    ip_header = eth_frame[ip_start:ip_start+20]
    protocol = ip_header[9]
    src_ip = ".".join(str(b) for b in ip_header[12:16])
    dst_ip = ".".join(str(b) for b in ip_header[16:20])

    if protocol != 6:  # Not TCP
        return None

    # Parse TCP header
    tcp_start = ip_start + 20
    if len(eth_frame) < tcp_start + 20:
        return None

    tcp_header = eth_frame[tcp_start:tcp_start+20]
    src_port = struct.unpack(">H", tcp_header[0:2])[0]
    dst_port = struct.unpack(">H", tcp_header[2:4])[0]
    data_offset = ((tcp_header[12] >> 4) & 0x0f) * 4

    # Get TCP payload
    payload_start = tcp_start + data_offset
    if len(eth_frame) <= payload_start:
        return None

    payload = eth_frame[payload_start:]
    if len(payload) == 0:
        return None

    return {
        'src': f"{src_ip}:{src_port}",
        'dst': f"{dst_ip}:{dst_port}",
        'src_port': src_port,
        'dst_port': dst_port,
        'payload': payload
    }

def main():
    print("Loading capture (this takes a while)...")
    packets = rdpcap(CAPTURE_FILE)
    print(f"Loaded {len(packets)} packets")

    # Parse NCM packets from packet 400000 onwards
    tcp_streams = defaultdict(list)
    video_ports = {50356, 50361}
    control_port = 50346

    print("\nParsing NCM packets from index 400000...")

    for i in range(400000, len(packets)):
        pkt = packets[i]
        if Raw not in pkt:
            continue

        data = bytes(pkt[Raw].load)
        result = parse_usb_ncm_packet(data)

        if result:
            key = f"{result['src']} -> {result['dst']}"
            tcp_streams[key].append({
                'idx': i,
                'payload': result['payload'],
                'src_port': result['src_port'],
                'dst_port': result['dst_port']
            })

        if i % 100000 == 0:
            print(f"  Processed {i}...")

    print(f"\nFound {len(tcp_streams)} TCP streams")

    # Show all streams
    print("\n" + "=" * 60)
    print("TCP STREAMS")
    print("=" * 60)
    for key in sorted(tcp_streams.keys()):
        msgs = tcp_streams[key]
        print(f"{key}: {len(msgs)} messages")

    # Find control channel (port 50346)
    print("\n" + "=" * 60)
    print("CONTROL CHANNEL (port 50346)")
    print("=" * 60)

    control_msgs = []
    for key, msgs in tcp_streams.items():
        if msgs and (msgs[0]['src_port'] == 50346 or msgs[0]['dst_port'] == 50346):
            control_msgs.extend([(key, m) for m in msgs])
            print(f"\n{key}: {len(msgs)} messages")
            for m in msgs[:3]:
                payload = m['payload']
                print(f"  [{m['idx']}] {len(payload)}b: {payload[:60].hex()}")

    # Find video channel first packet
    print("\n" + "=" * 60)
    print("VIDEO CHANNEL FIRST PACKETS (port 50356)")
    print("=" * 60)

    video_first_idx = None
    for key, msgs in tcp_streams.items():
        if msgs and (msgs[0]['src_port'] in video_ports or msgs[0]['dst_port'] in video_ports):
            first = msgs[0]
            print(f"\n{key}")
            print(f"  First at packet {first['idx']}")
            print(f"  Payload: {first['payload'][:60].hex()}")
            if video_first_idx is None or first['idx'] < video_first_idx:
                video_first_idx = first['idx']

    if video_first_idx:
        print(f"\n*** Video starts at packet {video_first_idx} ***")

        # Find control messages BEFORE video
        print("\n" + "=" * 60)
        print(f"CONTROL COMMANDS BEFORE VIDEO (packets {video_first_idx-100} to {video_first_idx})")
        print("=" * 60)

        before = [(k,m) for k,m in control_msgs if video_first_idx-100 < m['idx'] < video_first_idx]
        before.sort(key=lambda x: x[1]['idx'])

        for key, m in before:
            payload = m['payload']
            print(f"\n[{m['idx']}] {key}")
            print(f"  Payload ({len(payload)}b): {payload.hex()}")

if __name__ == "__main__":
    main()
