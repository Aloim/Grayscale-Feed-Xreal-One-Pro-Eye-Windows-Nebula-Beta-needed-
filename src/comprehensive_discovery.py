"""
XREAL Eye Comprehensive Video Discovery Tool

Systematically explores:
1. All ports in 50000-53000 range
2. Unknown header types (0x275e, 0x283e, 0x2753, etc.)
3. Camera/video service name variations
4. Different request formats

Run with glasses connected via USB.
"""

import socket
import struct
import time
import json
from datetime import datetime
from typing import Optional, Dict, List, Any

# Try to import gRPC support
try:
    import grpc
    import frames_service_pb2
    import frames_service_pb2_grpc
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    print("Note: gRPC modules not found. Install with: pip install grpcio")

GLASSES_IP = "169.254.2.1"
GRPC_PORT = 50051  # Standard gRPC port
RESULTS_FILE = "discovery_results.json"

# Known headers from capture analysis
KNOWN_HEADERS = {
    0x2710: "Keepalive/status",
    0x271f: "Get calibration (working!)",
    0x2731: "Metadata stream",
    0x2836: "IMU data",
    0x2af8: "Service subscription",
}

# Unknown headers to explore
UNKNOWN_HEADERS = [
    0x275e,  # 30 occurrences in capture
    0x283e,  # 6 occurrences in capture
    0x2753,  # Possible camera request
    0x2720,  # Pattern: 0x27XX
    0x2721,
    0x2722,
    0x2723,
    0x2724,
    0x2725,
    0x2730,
    0x2732,
    0x2733,
    0x2734,
    0x2735,
    0x2740,
    0x2750,
    0x2760,
    0x2770,
    0x2780,
    0x2790,
    0x27a0,
    0x27b0,
    0x27c0,
    0x27d0,
    0x27e0,
    0x27f0,
    # 0x28XX range for data types
    0x2830,
    0x2831,
    0x2832,
    0x2833,
    0x2834,
    0x2835,
    0x2837,
    0x2838,
    0x2839,
    0x283a,
    0x283b,
    0x283c,
    0x283d,
    0x283f,
    0x2840,
    0x2850,
    0x2860,
    0x2870,
    # Video specific guesses
    0x2856,  # 'V' = 0x56 for video?
    0x2843,  # 'C' = 0x43 for camera?
]

# Camera/video service names to try
CAMERA_SERVICES = [
    # Known working
    "nr_perception_head_tracking_remote",

    # RGB Camera variations
    "nr_perception_rgb_camera_remote",
    "nr_perception_camera_remote",
    "nr_perception_rgb_remote",
    "nr_rgb_camera_remote",
    "nr_camera_remote",
    "nr_rgb_remote",

    # Video variations
    "nr_video_remote",
    "nr_perception_video_remote",
    "nr_video_stream_remote",
    "nr_perception_video_stream_remote",

    # Stream variations
    "nr_rgb_stream_remote",
    "nr_camera_stream_remote",
    "nr_stream_remote",
    "nr_perception_stream_remote",

    # Frame variations
    "nr_frame_remote",
    "nr_rgb_frame_remote",
    "nr_perception_rgb_frame_remote",
    "nr_perception_frame_remote",
    "nr_image_remote",

    # Eye camera specific
    "nr_eye_camera_remote",
    "nr_perception_eye_camera_remote",
    "nr_eye_remote",

    # SLAM camera
    "nr_slam_camera_remote",
    "nr_perception_slam_camera_remote",
    "nr_slam_remote",

    # Without _remote suffix
    "nr_perception_rgb_camera",
    "nr_perception_camera",
    "nr_perception_video",
    "nr_rgb_camera",
    "nr_camera",
    "nr_video",

    # Display/render related (might trigger camera)
    "nr_display_remote",
    "nr_perception_display_remote",
    "nr_render_remote",

    # Capture variations
    "nr_capture_remote",
    "nr_perception_capture_remote",
    "nr_rgb_capture_remote",

    # Preview
    "nr_preview_remote",
    "nr_camera_preview_remote",
    "nr_perception_preview_remote",
]

def encode_varint(value: int) -> bytes:
    result = []
    while value > 127:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)

def scan_ports(start: int = 50000, end: int = 53100) -> Dict[int, str]:
    """Scan for open TCP ports on glasses"""
    print(f"\n{'='*60}")
    print("PORT SCAN")
    print(f"{'='*60}")
    print(f"Scanning {GLASSES_IP} ports {start}-{end}...")

    open_ports = {}
    for port in range(start, end):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.15)
            result = sock.connect_ex((GLASSES_IP, port))
            if result == 0:
                # Try to read initial data
                try:
                    sock.settimeout(0.3)
                    data = sock.recv(256)
                    header = data[:4].hex() if data else "empty"
                except:
                    header = "no-data"
                open_ports[port] = header
                print(f"  Port {port}: OPEN (header: {header})")
            sock.close()
        except:
            pass

        # Progress indicator every 500 ports
        if (port - start) % 500 == 0 and port > start:
            print(f"  ... scanned {port - start} ports ...")

    print(f"\nFound {len(open_ports)} open ports")
    return open_ports

def create_header_request(header: int, payload: bytes = b'') -> bytes:
    """Create a request with given header"""
    return struct.pack(">H", header) + struct.pack("<I", 0) + payload

def create_subscription(service_name: str, enable: bool = True) -> bytes:
    """Create a subscription message"""
    header = b'\x2a\xf8'
    flags = struct.pack('<I', 0x000000a5)

    service_bytes = service_name.encode('utf-8')
    service_len = len(service_bytes)

    # Metadata (32 bytes)
    meta = bytes([0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    meta += struct.pack('<Q', int(time.time() * 1000))
    meta += struct.pack('<I', 0x22)
    meta += struct.pack('<Q', int(time.time() * 1000))
    meta += struct.pack('<I', service_len)

    # Protobuf suffix
    inner = bytes([0x08]) + encode_varint(22348)
    inner += bytes([0x10]) + encode_varint(1 if enable else 0)
    suffix = bytes([0x0a, len(inner)]) + inner

    return header + flags + meta + service_bytes + suffix

def test_headers(sock: socket.socket) -> Dict[int, Any]:
    """Test unknown headers and record responses"""
    print(f"\n{'='*60}")
    print("HEADER TESTING")
    print(f"{'='*60}")

    results = {}

    for header in UNKNOWN_HEADERS:
        print(f"\nTesting header 0x{header:04x}...")

        # Try with empty payload
        msg = create_header_request(header)

        try:
            sock.sendall(msg)
            time.sleep(0.2)

            sock.settimeout(0.5)
            try:
                response = sock.recv(4096)
                if response:
                    results[header] = {
                        "status": "response",
                        "length": len(response),
                        "hex": response[:100].hex(),
                        "header": response[:2].hex() if len(response) >= 2 else None
                    }
                    print(f"  -> Response: {len(response)} bytes, header: {response[:2].hex()}")
                else:
                    results[header] = {"status": "empty"}
                    print(f"  -> Empty response")
            except socket.timeout:
                results[header] = {"status": "timeout"}
                print(f"  -> Timeout (no response)")

        except Exception as e:
            results[header] = {"status": "error", "error": str(e)}
            print(f"  -> Error: {e}")

    # Summary
    responsive = [h for h, r in results.items() if r.get("status") == "response"]
    print(f"\nHeaders with responses: {[f'0x{h:04x}' for h in responsive]}")

    return results

def test_services(sock: socket.socket) -> Dict[str, Any]:
    """Test camera service names"""
    print(f"\n{'='*60}")
    print("SERVICE TESTING")
    print(f"{'='*60}")

    results = {}

    for service in CAMERA_SERVICES:
        print(f"\nTrying service: {service}")

        msg = create_subscription(service)

        try:
            sock.sendall(msg)
            time.sleep(0.3)

            sock.settimeout(0.8)
            try:
                response = sock.recv(4096)
                if response and len(response) > 10:
                    results[service] = {
                        "status": "response",
                        "length": len(response),
                        "hex": response[:100].hex()
                    }
                    print(f"  -> Response: {len(response)} bytes")
                    print(f"     Data: {response[:50].hex()}")
                elif response:
                    results[service] = {"status": "minimal", "length": len(response)}
                    print(f"  -> Minimal response: {len(response)} bytes")
                else:
                    results[service] = {"status": "empty"}
            except socket.timeout:
                results[service] = {"status": "timeout"}
                print(f"  -> Timeout")

        except Exception as e:
            results[service] = {"status": "error", "error": str(e)}
            print(f"  -> Error: {e}")

    # Summary
    responsive = [s for s, r in results.items() if r.get("status") == "response"]
    print(f"\nServices with responses: {responsive}")

    return results

def test_calibration_request(sock: socket.socket) -> Optional[bytes]:
    """Test the known-working calibration request"""
    print(f"\n{'='*60}")
    print("CALIBRATION REQUEST (verification)")
    print(f"{'='*60}")

    # Known working request
    request = bytes.fromhex('271f00000006800000191a00')

    try:
        sock.sendall(request)
        time.sleep(0.3)

        sock.settimeout(2.0)
        response = sock.recv(8192)

        if response:
            print(f"Response: {len(response)} bytes")
            # Look for JSON
            try:
                # Find JSON in response
                json_start = response.find(b'{')
                if json_start >= 0:
                    json_data = response[json_start:]
                    json_end = json_data.rfind(b'}') + 1
                    if json_end > 0:
                        calibration = json.loads(json_data[:json_end])
                        print("Calibration data found!")
                        if 'RGB_camera' in calibration:
                            cam = calibration['RGB_camera']
                            print(f"  RGB Camera: {cam.get('width', '?')}x{cam.get('height', '?')}")
                        return response
            except:
                print(f"Raw response: {response[:200].hex()}")

        return response

    except Exception as e:
        print(f"Error: {e}")
        return None

def check_for_new_connections():
    """After tests, check if any new ports opened"""
    print(f"\n{'='*60}")
    print("POST-TEST PORT CHECK")
    print(f"{'='*60}")

    video_ports = [
        5555, 5556, 5557,  # Common video ports
        50051,  # gRPC
        50346, 50356, 50361,  # Nebula protocol
        52994, 52995,  # Discovered empty ports
        8000, 8080, 8554,  # HTTP/RTSP
        554,  # RTSP
    ]

    open_now = []
    for port in video_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.3)
            if sock.connect_ex((GLASSES_IP, port)) == 0:
                open_now.append(port)
                print(f"  Port {port}: OPEN")
            sock.close()
        except:
            pass

    return open_now


def test_grpc_streaming() -> Dict[str, Any]:
    """Test gRPC StartStreaming endpoint"""
    print(f"\n{'='*60}")
    print("gRPC STREAMING TEST")
    print(f"{'='*60}")

    if not GRPC_AVAILABLE:
        print("gRPC not available - skipping")
        return {"status": "skipped", "reason": "grpc not installed"}

    results = {}

    # Try multiple ports for gRPC
    # Based on USB capture: 52998 (IMU), 52996 (metadata), 52999 (control)
    # Based on firmware analysis: 50051 (standard gRPC)
    # Nebula ports: 50346 (control), 50356 (video)
    grpc_ports = [50051, 52999, 50346, 50356, 52998, 52996]

    for port in grpc_ports:
        print(f"\nTrying gRPC on port {port}...")

        try:
            target = f"{GLASSES_IP}:{port}"
            channel = grpc.insecure_channel(
                target,
                options=[
                    ('grpc.enable_http_proxy', 0),
                    ('grpc.initial_reconnect_backoff_ms', 100),
                    ('grpc.max_reconnect_backoff_ms', 500),
                ]
            )

            # Check connectivity
            try:
                grpc.channel_ready_future(channel).result(timeout=2)
                print(f"  Channel ready on port {port}!")

                # Create stub
                stub = frames_service_pb2_grpc.FramesStub(channel)

                # Create camera config
                camera_config = frames_service_pb2.CameraConfig(
                    width=1280,
                    height=720,
                    format="YUV420",
                    fps=30
                )

                # Create open stream request
                open_request = frames_service_pb2.OpenStreamRequest(
                    camera_config=camera_config
                )

                # Create stream request
                stream_request = frames_service_pb2.StreamRequest(
                    session_id="discovery_test",
                    timestamp=int(time.time() * 1000),
                    open_stream=open_request
                )

                print(f"  Sending OpenStreamRequest...")

                # Try to start streaming (bi-directional)
                def request_generator():
                    yield stream_request
                    # Keep connection alive
                    time.sleep(2)

                try:
                    responses = stub.StartStreaming(
                        request_generator(),
                        timeout=5
                    )

                    frame_count = 0
                    for response in responses:
                        print(f"  Got response type: {response.WhichOneof('response')}")
                        if response.HasField('camera_frame'):
                            frame = response.camera_frame
                            print(f"    Frame {frame.frame_id}: {frame.width}x{frame.height}")
                            frame_count += 1
                        elif response.HasField('status'):
                            print(f"    Status: {response.status.status} - {response.status.message}")
                        elif response.HasField('sensor_data'):
                            print(f"    Sensor data received")

                        if frame_count >= 5:
                            break

                    results[port] = {
                        "status": "success",
                        "frames_received": frame_count
                    }
                    print(f"  SUCCESS! Received {frame_count} frames")

                except grpc.RpcError as e:
                    print(f"  RPC Error: {e.code()} - {e.details()}")
                    results[port] = {
                        "status": "rpc_error",
                        "code": str(e.code()),
                        "details": e.details()
                    }

            except grpc.FutureTimeoutError:
                print(f"  Channel not ready (timeout)")
                results[port] = {"status": "timeout"}

            channel.close()

        except Exception as e:
            print(f"  Error: {e}")
            results[port] = {"status": "error", "error": str(e)}

    return results


def test_raw_grpc_http2(port: int = 50051) -> Dict[str, Any]:
    """Test raw HTTP/2 connection (gRPC uses HTTP/2)"""
    print(f"\n{'='*60}")
    print(f"RAW HTTP/2 TEST (port {port})")
    print(f"{'='*60}")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((GLASSES_IP, port))

        # HTTP/2 connection preface
        preface = b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
        sock.sendall(preface)

        # Wait for response
        time.sleep(0.5)
        sock.settimeout(2)

        try:
            response = sock.recv(4096)
            print(f"  Response: {len(response)} bytes")
            print(f"  Hex: {response[:100].hex()}")

            # Check for HTTP/2 SETTINGS frame (type 0x04)
            if len(response) >= 9:
                frame_len = (response[0] << 16) | (response[1] << 8) | response[2]
                frame_type = response[3]
                frame_flags = response[4]
                print(f"  Frame: len={frame_len}, type={frame_type}, flags={frame_flags}")

                if frame_type == 0x04:
                    print(f"  -> HTTP/2 SETTINGS frame detected!")
                    return {"status": "http2_detected", "port": port}

            return {"status": "response", "data": response[:100].hex()}

        except socket.timeout:
            print(f"  No response")
            return {"status": "timeout"}

    except Exception as e:
        print(f"  Error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        try:
            sock.close()
        except:
            pass

def main():
    print("=" * 60)
    print("XREAL Eye Comprehensive Video Discovery")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)
    print(f"Target: {GLASSES_IP}")

    all_results = {
        "timestamp": datetime.now().isoformat(),
        "target": GLASSES_IP,
    }

    # Step 1: Port scan
    try:
        open_ports = scan_ports(52990, 53010)  # Narrow range first
        all_results["ports_narrow"] = open_ports

        # Also scan common video ports
        video_scan = scan_ports(50340, 50370)
        all_results["ports_video"] = video_scan
    except Exception as e:
        print(f"Port scan error: {e}")
        all_results["port_scan_error"] = str(e)

    # Step 2: Connect to control channel
    try:
        print(f"\nConnecting to control channel {GLASSES_IP}:52999...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((GLASSES_IP, 52999))
        print("Connected!")

        # Read initial data
        sock.settimeout(1.0)
        try:
            initial = sock.recv(4096)
            if initial:
                print(f"Initial data: {initial[:50].hex()}")
                all_results["initial_data"] = initial.hex()
        except socket.timeout:
            print("No initial data")

        # Step 3: Verify calibration works
        cal_response = test_calibration_request(sock)
        if cal_response:
            all_results["calibration_working"] = True

        # Step 4: Test unknown headers
        header_results = test_headers(sock)
        all_results["headers"] = {f"0x{k:04x}": v for k, v in header_results.items()}

        # Step 5: Test service names
        service_results = test_services(sock)
        all_results["services"] = service_results

        sock.close()

        # Step 6: Test gRPC streaming
        grpc_results = test_grpc_streaming()
        all_results["grpc"] = grpc_results

        # Step 7: Test raw HTTP/2 on various ports
        for port in [50051, 52999]:
            http2_result = test_raw_grpc_http2(port)
            all_results[f"http2_port_{port}"] = http2_result

        # Step 8: Final port check
        new_ports = check_for_new_connections()
        all_results["post_test_ports"] = new_ports

    except ConnectionRefusedError:
        print("Control channel refused - glasses not connected?")
        all_results["error"] = "connection_refused"
    except socket.timeout:
        print("Connection timeout")
        all_results["error"] = "timeout"
    except Exception as e:
        print(f"Error: {e}")
        all_results["error"] = str(e)

    # Save results
    print(f"\n{'='*60}")
    print("SAVING RESULTS")
    print(f"{'='*60}")

    with open(RESULTS_FILE, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"Results saved to {RESULTS_FILE}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    if "headers" in all_results:
        responsive_headers = [h for h, r in all_results["headers"].items()
                            if r.get("status") == "response"]
        print(f"Headers with responses: {responsive_headers}")

    if "services" in all_results:
        responsive_services = [s for s, r in all_results["services"].items()
                             if r.get("status") == "response"]
        print(f"Services with responses: {responsive_services}")

    if "grpc" in all_results:
        working_grpc = [str(p) for p, r in all_results["grpc"].items()
                       if r.get("status") == "success"]
        if working_grpc:
            print(f"gRPC working ports: {working_grpc}")
        else:
            print("gRPC: No working ports found")

    print(f"\nComplete! Check {RESULTS_FILE} for full results.")
    print("\nTo visualize results:")
    print("  python -c \"import json; print(json.dumps(json.load(open('discovery_results.json')), indent=2))\"")

if __name__ == "__main__":
    main()
