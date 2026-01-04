"""
Extract video activation commands from Nebula USB capture.

Focus: Find TCP payloads on control channel (port 50346/52999)
that trigger video streaming (port 50356).
"""

from scapy.all import rdpcap, TCP, IP, Raw
from collections import defaultdict
import struct

CAPTURE_FILE = "../Downloads/Nebula_Windows_20250813/WindowsNebulaAppUSBRecording.pcapng"

# Ports we care about
CONTROL_PORTS = {50346, 52999}
VIDEO_PORTS = {50356, 50361}
IMU_PORT = 52998

def main():
    print("Loading capture file (this may take a minute)...")
    try:
        packets = rdpcap(CAPTURE_FILE)
    except Exception as e:
        print(f"Error loading capture: {e}")
        print("Make sure scapy is installed: pip install scapy")
        return

    print(f"Loaded {len(packets)} packets")

    # Find TCP streams
    tcp_streams = defaultdict(list)

    for i, pkt in enumerate(packets):
        if TCP in pkt and Raw in pkt:
            if IP in pkt:
                src = f"{pkt[IP].src}:{pkt[TCP].sport}"
                dst = f"{pkt[IP].dst}:{pkt[TCP].dport}"
                stream_key = f"{src} -> {dst}"
                data = bytes(pkt[Raw].load)
                tcp_streams[stream_key].append({
                    'idx': i,
                    'data': data,
                    'sport': pkt[TCP].sport,
                    'dport': pkt[TCP].dport
                })

    print(f"\nFound {len(tcp_streams)} TCP streams")

    # Find control channel traffic
    print("\n" + "=" * 60)
    print("CONTROL CHANNEL TRAFFIC")
    print("=" * 60)

    for stream_key, msgs in tcp_streams.items():
        if not msgs:
            continue
        sport = msgs[0]['sport']
        dport = msgs[0]['dport']

        if sport in CONTROL_PORTS or dport in CONTROL_PORTS:
            print(f"\n{stream_key} ({len(msgs)} messages)")

            # Show first 5 messages
            for msg in msgs[:5]:
                data = msg['data']
                print(f"  [{msg['idx']}] {len(data)} bytes: {data[:50].hex()}...")

                # Try to decode header
                if len(data) >= 6:
                    header = struct.unpack(">H", data[:2])[0]
                    flags = struct.unpack("<I", data[2:6])[0]
                    print(f"        Header: 0x{header:04x}, Flags: 0x{flags:08x}")

    # Find first video data
    print("\n" + "=" * 60)
    print("FIRST VIDEO TRAFFIC")
    print("=" * 60)

    video_start_idx = None
    for stream_key, msgs in tcp_streams.items():
        if not msgs:
            continue
        sport = msgs[0]['sport']
        dport = msgs[0]['dport']

        if sport in VIDEO_PORTS or dport in VIDEO_PORTS:
            first_msg = msgs[0]
            if video_start_idx is None or first_msg['idx'] < video_start_idx:
                video_start_idx = first_msg['idx']
            print(f"\n{stream_key}")
            print(f"  First video at packet {first_msg['idx']}")
            print(f"  First 50 bytes: {first_msg['data'][:50].hex()}")

    if video_start_idx:
        print(f"\n*** Video starts at packet index {video_start_idx} ***")
        print("Look for control commands BEFORE this packet to find activation sequence")

        # Find control messages just before video
        print("\n" + "=" * 60)
        print(f"CONTROL MESSAGES BEFORE VIDEO (packets {video_start_idx-50} to {video_start_idx})")
        print("=" * 60)

        for stream_key, msgs in tcp_streams.items():
            sport = msgs[0]['sport'] if msgs else 0
            dport = msgs[0]['dport'] if msgs else 0

            if sport in CONTROL_PORTS or dport in CONTROL_PORTS:
                for msg in msgs:
                    if video_start_idx - 50 < msg['idx'] < video_start_idx:
                        data = msg['data']
                        print(f"\n[{msg['idx']}] {stream_key}")
                        print(f"  Full data: {data.hex()}")

if __name__ == "__main__":
    main()
