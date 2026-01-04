"""
Maintain heartbeat on control channel while discovering video.
The glasses seem to require active connection management.
"""

import socket
import struct
import time
import threading
from typing import Optional

GLASSES_IP = "169.254.2.1"
CONTROL_PORT = 52999
IMU_PORT = 52998

# Global flag to stop threads
stop_flag = False

def hexdump(data: bytes, limit: int = 64):
    for i in range(0, min(len(data), limit), 16):
        chunk = data[i:i+16]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        print(f"    {i:04x}: {hex_str}")

class ControlChannel:
    """Maintain connection to control channel with heartbeat"""

    def __init__(self):
        self.sock = None
        self.connected = False
        self.last_rx = 0
        self.rx_count = 0

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((GLASSES_IP, CONTROL_PORT))
            self.sock.setblocking(False)
            self.connected = True
            print(f"[CTRL] Connected to {GLASSES_IP}:{CONTROL_PORT}")
            return True
        except Exception as e:
            print(f"[CTRL] Connect failed: {e}")
            return False

    def send(self, data: bytes):
        if self.sock and self.connected:
            try:
                self.sock.sendall(data)
                return True
            except:
                self.connected = False
        return False

    def receive(self) -> Optional[bytes]:
        if self.sock and self.connected:
            try:
                data = self.sock.recv(4096)
                if data:
                    self.rx_count += 1
                    self.last_rx = time.time()
                    return data
            except BlockingIOError:
                pass
            except:
                self.connected = False
        return None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.connected = False


def control_thread(ctrl: ControlChannel):
    """Thread to maintain control channel and send heartbeats"""
    global stop_flag

    # Keepalive message (header 0x2710 was seen in capture)
    keepalive = struct.pack(">H", 0x2710) + struct.pack("<I", 0)

    last_keepalive = 0
    keepalive_interval = 1.0  # Send every second

    print("[CTRL] Starting control thread")

    while not stop_flag and ctrl.connected:
        # Send keepalive periodically
        now = time.time()
        if now - last_keepalive > keepalive_interval:
            ctrl.send(keepalive)
            last_keepalive = now

        # Read any responses
        data = ctrl.receive()
        if data:
            header = struct.unpack(">H", data[:2])[0] if len(data) >= 2 else 0
            print(f"[CTRL] RX: {len(data)} bytes, header 0x{header:04x}")

        time.sleep(0.1)

    print("[CTRL] Thread stopped")


def imu_thread():
    """Thread to monitor IMU port"""
    global stop_flag

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((GLASSES_IP, IMU_PORT))
        sock.settimeout(0.5)
        print(f"[IMU] Connected to port {IMU_PORT}")

        packet_count = 0
        while not stop_flag:
            try:
                data = sock.recv(1024)
                if data:
                    packet_count += 1
                    if packet_count <= 3:
                        header = struct.unpack(">H", data[:2])[0] if len(data) >= 2 else 0
                        print(f"[IMU] Packet {packet_count}: {len(data)} bytes, header 0x{header:04x}")
                    elif packet_count == 4:
                        print(f"[IMU] (streaming, further packets suppressed)")
            except socket.timeout:
                pass
            except Exception as e:
                print(f"[IMU] Error: {e}")
                break

        print(f"[IMU] Received {packet_count} packets total")
        sock.close()
    except Exception as e:
        print(f"[IMU] Failed to connect: {e}")


def test_subscription():
    """Test sending subscription messages while heartbeat is active"""
    global stop_flag

    print("\n" + "="*60)
    print("TESTING SUBSCRIPTIONS WITH ACTIVE HEARTBEAT")
    print("="*60)

    # Start control channel
    ctrl = ControlChannel()
    if not ctrl.connect():
        print("Failed to connect control channel")
        return

    # Read initial data
    time.sleep(0.5)
    for _ in range(5):
        data = ctrl.receive()
        if data:
            print(f"[INIT] Got {len(data)} bytes")
            hexdump(data)

    # Start control thread for heartbeat
    ctrl_t = threading.Thread(target=control_thread, args=(ctrl,))
    ctrl_t.daemon = True
    ctrl_t.start()

    # Start IMU monitoring thread
    imu_t = threading.Thread(target=imu_thread)
    imu_t.daemon = True
    imu_t.start()

    print("\n[MAIN] Heartbeat active, testing subscriptions...")
    time.sleep(1)

    # Now try sending video subscriptions
    subscription_tests = [
        # Based on capture: nr_perception_head_tracking_remote works
        # Header 0x2af8 with service name

        # Try camera subscriptions
        ("nr_perception_rgb_camera", "RGB camera"),
        ("nr_perception_camera", "Camera"),
        ("nr_rgb_camera", "RGB cam short"),
        ("nr_video", "Video"),
        ("nr_camera_preview", "Camera preview"),
    ]

    for service, desc in subscription_tests:
        print(f"\n[SUB] Trying: {desc} ({service})")

        # Build subscription message like in capture
        header = b'\x2a\xf8'
        flags = struct.pack('<I', 0x000000a5)

        # Metadata (simplified)
        meta = struct.pack('<Q', int(time.time() * 1000))  # timestamp
        meta += struct.pack('<I', len(service))  # service name length

        # Protobuf suffix (enable=1)
        suffix = bytes([0x0a, 0x04, 0x08, 0x01, 0x10, 0x01])  # field1={field1=1, field2=1}

        msg = header + flags + meta + service.encode('utf-8') + suffix

        ctrl.send(msg)
        time.sleep(1)

        # Check for response
        data = ctrl.receive()
        if data:
            print(f"[SUB] Response: {len(data)} bytes")
            hexdump(data)

    print("\n[MAIN] Waiting 5 seconds to see if video starts...")
    time.sleep(5)

    # Check if any new ports opened
    print("\n[MAIN] Checking for new open ports...")
    for port in [50051, 50356, 52994, 52995, 52997]:
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(0.5)
            if test_sock.connect_ex((GLASSES_IP, port)) == 0:
                # Try to read data
                try:
                    test_sock.settimeout(1)
                    data = test_sock.recv(1024)
                    if data:
                        print(f"  Port {port}: ACTIVE - {len(data)} bytes")
                    else:
                        print(f"  Port {port}: open but no data")
                except:
                    print(f"  Port {port}: open, timeout on read")
            test_sock.close()
        except:
            pass

    # Stop threads
    stop_flag = True
    time.sleep(0.5)

    ctrl.close()
    print("\n[MAIN] Done")


if __name__ == "__main__":
    test_subscription()
