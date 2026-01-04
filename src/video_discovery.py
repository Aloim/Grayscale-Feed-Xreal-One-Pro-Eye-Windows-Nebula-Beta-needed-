"""
XREAL Eye Video Discovery - Aggressive Mode

Systematically tries every known approach to activate video streaming.
No rate limiting. Full brute force.
"""

import socket
import struct
import time
import threading
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import json

GLASSES_IP = "169.254.2.1"
ALL_PORTS = list(range(52990, 53000))  # 52990-52999

# Video frame signatures
H264_NAL_START = b'\x00\x00\x00\x01'
VIDEO_FRAME_MAGIC = bytes.fromhex('00003628')
VIDEO_FRAME_MAGIC_ALT = bytes.fromhex('36280000')

# Known headers
HEADER_CALIBRATION = 0x271f  # Working
HEADER_SUBSCRIPTION = 0x2af8  # Working
HEADER_KEEPALIVE = 0x2710
HEADER_METADATA = 0x2731
HEADER_IMU = 0x2836
HEADER_CONTROL = 0x278a
HEADER_ERROR = 0xffde

# Suspected video headers
HEADER_VIDEO_V = 0x2856  # 'V' ascii
HEADER_VIDEO_R = 0x2852  # 'R' ascii
HEADER_UNKNOWN_275E = 0x275e  # 30 occurrences in capture
HEADER_UNKNOWN_283E = 0x283e  # 6 occurrences in capture

@dataclass
class DiscoveryResult:
    port: int
    header: int
    payload_type: str
    response_len: int
    response_hex: str
    is_video: bool
    notes: str

class VideoDiscovery:
    def __init__(self):
        self.results: List[DiscoveryResult] = []
        self.video_found = False
        self.video_port = None
        self.video_data = b''
        self.lock = threading.Lock()

    def log(self, msg: str):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def encode_varint(self, value: int) -> bytes:
        result = []
        while value > 127:
            result.append((value & 0x7f) | 0x80)
            value >>= 7
        result.append(value)
        return bytes(result)

    def create_header_message(self, header: int, flags: int = 0, payload: bytes = b'') -> bytes:
        """Create a message with given header"""
        return struct.pack('>H', header) + struct.pack('<I', flags) + payload

    def create_subscription(self, service_name: str, enable: bool = True) -> bytes:
        """Create subscription message (0x2af8 format)"""
        header = b'\x2a\xf8'
        flags = struct.pack('<I', 0x000000a5)

        service_bytes = service_name.encode('utf-8')
        service_len = len(service_bytes)

        # Metadata block
        meta = bytes([0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        meta += struct.pack('<Q', int(time.time() * 1000))
        meta += struct.pack('<I', 0x22)
        meta += struct.pack('<Q', int(time.time() * 1000))
        meta += struct.pack('<I', service_len)

        # Protobuf suffix
        inner = bytes([0x08]) + self.encode_varint(22348)
        inner += bytes([0x10]) + self.encode_varint(1 if enable else 0)
        suffix = bytes([0x0a, len(inner)]) + inner

        return header + flags + meta + service_bytes + suffix

    def check_for_video(self, data: bytes) -> bool:
        """Check if data contains video frames"""
        if H264_NAL_START in data:
            return True
        if VIDEO_FRAME_MAGIC in data or VIDEO_FRAME_MAGIC_ALT in data:
            return True
        # Check for large data that could be video frames
        if len(data) > 1000 and data[:4] not in [b'\xff\xde\x00\x00', b'\x00\x00\xff\xde']:
            return True
        return False

    def probe_port(self, port: int, timeout: float = 2.0) -> Dict[str, Any]:
        """Probe a single port for video data"""
        result = {
            'port': port,
            'connected': False,
            'initial_data': None,
            'initial_len': 0,
            'has_video': False
        }

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((GLASSES_IP, port))
            result['connected'] = True

            # Read any initial data
            sock.settimeout(0.5)
            try:
                data = sock.recv(8192)
                if data:
                    result['initial_data'] = data[:100].hex()
                    result['initial_len'] = len(data)
                    result['has_video'] = self.check_for_video(data)
            except socket.timeout:
                pass

            sock.close()
        except Exception as e:
            result['error'] = str(e)

        return result

    def send_and_receive(self, port: int, data: bytes, timeout: float = 1.0) -> Optional[bytes]:
        """Send data to port and receive response"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((GLASSES_IP, port))

            # Drain any initial data
            sock.settimeout(0.2)
            try:
                sock.recv(4096)
            except:
                pass

            # Send our data
            sock.settimeout(timeout)
            sock.sendall(data)

            # Wait for response
            time.sleep(0.1)
            sock.settimeout(timeout)

            response = b''
            try:
                while True:
                    chunk = sock.recv(8192)
                    if not chunk:
                        break
                    response += chunk
                    if len(response) > 100000:  # 100KB limit
                        break
            except socket.timeout:
                pass

            sock.close()
            return response if response else None

        except Exception as e:
            return None

    def try_header_on_port(self, port: int, header: int, payload: bytes = b'') -> DiscoveryResult:
        """Try a specific header on a port"""
        msg = self.create_header_message(header, 0x00000006, payload)
        response = self.send_and_receive(port, msg)

        is_video = False
        notes = "no response"
        response_hex = ""
        response_len = 0

        if response:
            response_len = len(response)
            response_hex = response[:50].hex()

            # Check response type
            if response[:2] == b'\xff\xde':
                notes = "error response (recognized but rejected)"
            elif self.check_for_video(response):
                is_video = True
                notes = "VIDEO DATA!"
                with self.lock:
                    self.video_found = True
                    self.video_port = port
                    self.video_data = response
            elif response_len > 100:
                notes = f"got {response_len} bytes data"
            else:
                notes = f"short response"

        return DiscoveryResult(
            port=port,
            header=header,
            payload_type="header",
            response_len=response_len,
            response_hex=response_hex,
            is_video=is_video,
            notes=notes
        )

    def try_service_subscription(self, service_name: str) -> DiscoveryResult:
        """Try subscribing to a service"""
        msg = self.create_subscription(service_name)
        response = self.send_and_receive(52999, msg)  # Control port

        is_video = False
        notes = "no response"
        response_hex = ""
        response_len = 0

        if response:
            response_len = len(response)
            response_hex = response[:50].hex()

            if self.check_for_video(response):
                is_video = True
                notes = "VIDEO DATA!"
            elif response_len > 100:
                notes = f"subscription accepted ({response_len} bytes)"
            else:
                notes = "short response"

        return DiscoveryResult(
            port=52999,
            header=0x2af8,
            payload_type=f"service:{service_name}",
            response_len=response_len,
            response_hex=response_hex,
            is_video=is_video,
            notes=notes
        )

    def phase1_port_scan(self):
        """Phase 1: Scan all ports for initial data"""
        self.log("="*60)
        self.log("PHASE 1: Port Scan")
        self.log("="*60)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self.probe_port, p): p for p in ALL_PORTS}

            for future in as_completed(futures):
                port = futures[future]
                result = future.result()

                if result['connected']:
                    status = f"OPEN"
                    if result['initial_len'] > 0:
                        status += f" ({result['initial_len']} bytes)"
                        if result['has_video']:
                            status += " VIDEO!"
                            self.video_found = True
                            self.video_port = port
                    self.log(f"  Port {port}: {status}")

    def phase2_header_bruteforce(self):
        """Phase 2: Try all known and suspected headers"""
        self.log("="*60)
        self.log("PHASE 2: Header Brute Force")
        self.log("="*60)

        # Headers to try
        headers = [
            # Known
            HEADER_CALIBRATION,
            HEADER_SUBSCRIPTION,
            HEADER_KEEPALIVE,
            HEADER_METADATA,
            HEADER_IMU,
            HEADER_CONTROL,
            # Suspected video
            HEADER_VIDEO_V,
            HEADER_VIDEO_R,
            HEADER_UNKNOWN_275E,
            HEADER_UNKNOWN_283E,
            # Try ASCII video-related
            0x2843,  # 'C' for camera
            0x2853,  # 'S' for stream
            0x2846,  # 'F' for frame
            0x2849,  # 'I' for image
            # Try range around known
            0x2857, 0x2858, 0x2859, 0x285a,
            0x2850, 0x2851, 0x2854, 0x2855,
        ]

        # Payloads to try with each header
        payloads = [
            b'',  # Empty
            b'\x01',  # Enable
            b'\x01\x00\x00\x00',  # Enable (32-bit)
            bytes.fromhex('800000191a00'),  # Calibration payload
            struct.pack('<I', 1),  # LE uint32 = 1
            struct.pack('>I', 1),  # BE uint32 = 1
        ]

        for header in headers:
            for payload in payloads:
                result = self.try_header_on_port(52999, header, payload)

                if result.response_len > 0:
                    self.log(f"  0x{header:04x} + {len(payload)}B payload: {result.notes}")
                    self.results.append(result)

                if self.video_found:
                    return

    def phase3_service_subscription(self):
        """Phase 3: Try subscribing to video-related services"""
        self.log("="*60)
        self.log("PHASE 3: Service Subscription Attack")
        self.log("="*60)

        services = [
            # Pattern: nr_perception_[type]_remote
            "nr_perception_rgb_camera_remote",
            "nr_perception_camera_remote",
            "nr_perception_video_remote",
            "nr_perception_video_stream_remote",
            "nr_perception_frame_remote",
            "nr_perception_rgb_frame_remote",
            "nr_perception_image_remote",
            # Pattern: nr_[type]_remote
            "nr_rgb_camera_remote",
            "nr_camera_remote",
            "nr_video_remote",
            "nr_stream_remote",
            "nr_frame_remote",
            # Simple names
            "nr_rgb_camera",
            "nr_camera",
            "nr_video",
            "nr_stream",
            # gRPC style
            "frames.service.Frames",
            "camera.service.Camera",
            "video.service.Video",
            # Eye specific
            "nr_eye_camera_remote",
            "nr_perception_eye_camera_remote",
            "nr_eye_video_remote",
            # Slam camera
            "nr_perception_slam_camera_remote",
            "nr_slam_camera_remote",
        ]

        for service in services:
            result = self.try_service_subscription(service)

            if result.response_len > 0:
                self.log(f"  {service}: {result.notes}")
                self.results.append(result)

            if self.video_found:
                return

    def phase4_listen_all_ports(self):
        """Phase 4: Open connections to all ports and listen for data"""
        self.log("="*60)
        self.log("PHASE 4: Passive Listening (5 seconds)")
        self.log("="*60)

        sockets = {}

        # Connect to all ports
        for port in ALL_PORTS:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                sock.connect((GLASSES_IP, port))
                sock.setblocking(False)
                sockets[port] = sock
                self.log(f"  Connected to {port}")
            except Exception as e:
                pass

        # Listen for 5 seconds
        start = time.time()
        port_data = {p: b'' for p in sockets}

        while time.time() - start < 5:
            for port, sock in sockets.items():
                try:
                    data = sock.recv(8192)
                    if data:
                        port_data[port] += data

                        if self.check_for_video(data):
                            self.log(f"  VIDEO DATA on port {port}!")
                            self.video_found = True
                            self.video_port = port
                            self.video_data = port_data[port]
                except:
                    pass
            time.sleep(0.01)

        # Report
        for port, data in port_data.items():
            if len(data) > 0:
                self.log(f"  Port {port}: received {len(data)} bytes")

        # Cleanup
        for sock in sockets.values():
            sock.close()

    def phase5_gRPC_attack(self):
        """Phase 5: Try gRPC on all ports"""
        self.log("="*60)
        self.log("PHASE 5: gRPC Attack")
        self.log("="*60)

        # HTTP/2 connection preface
        HTTP2_PREFACE = b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'

        # Simple gRPC request frame
        # SETTINGS frame
        SETTINGS = bytes([0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00])

        for port in ALL_PORTS + [50051, 8848]:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                sock.connect((GLASSES_IP, port))

                # Send HTTP/2 preface
                sock.sendall(HTTP2_PREFACE + SETTINGS)

                time.sleep(0.2)

                try:
                    response = sock.recv(4096)
                    if response:
                        self.log(f"  Port {port}: gRPC response {len(response)} bytes: {response[:30].hex()}")

                        # Check for HTTP/2 response
                        if b'HTTP' in response or response[3:4] == b'\x04':
                            self.log(f"    -> HTTP/2 SERVER DETECTED!")
                except socket.timeout:
                    pass

                sock.close()
            except Exception as e:
                pass

    def phase6_sequence_attack(self):
        """Phase 6: Try initialization sequences"""
        self.log("="*60)
        self.log("PHASE 6: Initialization Sequence Attack")
        self.log("="*60)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((GLASSES_IP, 52999))

            # Step 1: Send calibration request (known working)
            self.log("  Step 1: Sending calibration request...")
            cal_msg = bytes.fromhex('271f00000006800000191a00')
            sock.sendall(cal_msg)
            time.sleep(0.5)

            try:
                cal_resp = sock.recv(8192)
                self.log(f"    Calibration response: {len(cal_resp)} bytes")
            except:
                pass

            # Step 2: Subscribe to head tracking (known working)
            self.log("  Step 2: Subscribing to head tracking...")
            head_sub = self.create_subscription("nr_perception_head_tracking_remote")
            sock.sendall(head_sub)
            time.sleep(0.5)

            try:
                head_resp = sock.recv(8192)
                self.log(f"    Head tracking response: {len(head_resp)} bytes")
            except:
                pass

            # Step 3: Try video subscription
            self.log("  Step 3: Trying video subscriptions...")
            video_services = [
                "nr_perception_rgb_camera_remote",
                "nr_rgb_camera_remote",
                "nr_video_remote",
            ]

            for service in video_services:
                video_sub = self.create_subscription(service)
                sock.sendall(video_sub)
                time.sleep(0.3)

                try:
                    video_resp = sock.recv(8192)
                    if video_resp and len(video_resp) > 50:
                        self.log(f"    {service}: {len(video_resp)} bytes")
                        if self.check_for_video(video_resp):
                            self.log(f"    VIDEO DATA!")
                            self.video_found = True
                except:
                    pass

            # Step 4: Try video headers after subscription
            self.log("  Step 4: Trying video headers after init...")
            video_headers = [0x2856, 0x2852, 0x275e]

            for header in video_headers:
                msg = self.create_header_message(header, 0x00000001, b'\x01')
                sock.sendall(msg)
                time.sleep(0.2)

                try:
                    resp = sock.recv(8192)
                    if resp:
                        self.log(f"    0x{header:04x}: {len(resp)} bytes - {resp[:20].hex()}")
                except:
                    pass

            sock.close()

        except Exception as e:
            self.log(f"  Error: {e}")

    def phase7_full_header_scan(self):
        """Phase 7: Scan ALL headers in 0x27XX and 0x28XX range"""
        self.log("="*60)
        self.log("PHASE 7: Full Header Scan (0x2700-0x28FF)")
        self.log("="*60)

        interesting = []

        for header in range(0x2700, 0x2900):
            msg = self.create_header_message(header, 0x00000001, b'\x01')
            response = self.send_and_receive(52999, msg, timeout=0.3)

            if response and len(response) > 6:
                # Skip error responses
                if response[:2] != b'\xff\xde':
                    interesting.append((header, len(response), response[:20].hex()))
                    self.log(f"  0x{header:04x}: {len(response)} bytes - {response[:20].hex()}")

                    if self.check_for_video(response):
                        self.log(f"    VIDEO FOUND!")
                        self.video_found = True
                        self.video_port = 52999
                        self.video_data = response
                        return

            # Progress indicator every 64 headers
            if header % 64 == 0:
                sys.stdout.write(f"\r  Scanning 0x{header:04x}...")
                sys.stdout.flush()

        print()
        self.log(f"  Found {len(interesting)} interesting headers")

    def run(self):
        """Run all discovery phases"""
        self.log("="*60)
        self.log("XREAL EYE VIDEO DISCOVERY - AGGRESSIVE MODE")
        self.log("="*60)
        self.log(f"Target: {GLASSES_IP}")
        self.log(f"Ports: {ALL_PORTS}")
        self.log("")

        # Run phases
        self.phase1_port_scan()
        if self.video_found:
            return self.report_video()

        self.phase2_header_bruteforce()
        if self.video_found:
            return self.report_video()

        self.phase3_service_subscription()
        if self.video_found:
            return self.report_video()

        self.phase4_listen_all_ports()
        if self.video_found:
            return self.report_video()

        self.phase5_gRPC_attack()
        if self.video_found:
            return self.report_video()

        self.phase6_sequence_attack()
        if self.video_found:
            return self.report_video()

        self.phase7_full_header_scan()
        if self.video_found:
            return self.report_video()

        # No video found
        self.log("")
        self.log("="*60)
        self.log("VIDEO NOT FOUND")
        self.log("="*60)
        self.log("")
        self.log("Interesting results:")
        for r in self.results:
            if r.response_len > 100:
                self.log(f"  Port {r.port}, Header 0x{r.header:04x}: {r.notes}")

    def report_video(self):
        """Report video discovery"""
        self.log("")
        self.log("="*60)
        self.log("!!! VIDEO FOUND !!!")
        self.log("="*60)
        self.log(f"Port: {self.video_port}")
        self.log(f"Data size: {len(self.video_data)} bytes")
        self.log(f"First 100 bytes: {self.video_data[:100].hex()}")

        # Save video data
        with open('video_discovery_data.bin', 'wb') as f:
            f.write(self.video_data)
        self.log("Saved to video_discovery_data.bin")


def main():
    discovery = VideoDiscovery()
    discovery.run()

    # Save results
    results_json = [{
        'port': r.port,
        'header': f'0x{r.header:04x}',
        'payload_type': r.payload_type,
        'response_len': r.response_len,
        'is_video': r.is_video,
        'notes': r.notes
    } for r in discovery.results]

    with open('video_discovery_results.json', 'w') as f:
        json.dump(results_json, f, indent=2)
    print("\nResults saved to video_discovery_results.json")


if __name__ == "__main__":
    main()
