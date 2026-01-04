#!/usr/bin/env python3
"""
XREAL Eye Live Video Viewer
Displays real-time video from the XREAL One Pro glasses camera

Format: 512x378 @ 4-bit grayscale (high nibble)
Port: TCP 52997
Header: 0x2748
"""

import socket
import numpy as np
import cv2
import time
import threading
from collections import deque

GLASSES_IP = "169.254.2.1"
VIDEO_PORT = 52997
PACKET_SIZE = 193862
HEADER_OFFSET = 0x140  # 320 bytes header

WIDTH = 512
HEIGHT = 378
IMAGE_SIZE = WIDTH * HEIGHT  # 193,536 bytes

class XrealEyeViewer:
    def __init__(self):
        self.running = False
        self.frame_queue = deque(maxlen=5)
        self.fps_counter = deque(maxlen=30)
        self.sock = None

    def connect(self):
        """Connect to glasses video stream"""
        print(f"Connecting to {GLASSES_IP}:{VIDEO_PORT}...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect((GLASSES_IP, VIDEO_PORT))
        self.sock.settimeout(1)
        print("Connected!")

    def decode_frame(self, packet):
        """Decode video packet to image"""
        if len(packet) < HEADER_OFFSET + IMAGE_SIZE:
            return None

        # Extract image data (skip header)
        data = packet[HEADER_OFFSET:HEADER_OFFSET + IMAGE_SIZE]

        # Decode: high nibble = pixel value (0-15), scale to 0-255
        pixels = np.frombuffer(data, dtype=np.uint8)
        pixels = ((pixels >> 4) & 0x0F) * 17

        # Reshape to image
        img = pixels.reshape((HEIGHT, WIDTH))

        return img

    def receive_thread(self):
        """Thread to receive video packets"""
        buffer = b''

        while self.running:
            try:
                data = self.sock.recv(65536)
                if not data:
                    continue

                buffer += data

                # Extract complete packets
                while len(buffer) >= PACKET_SIZE:
                    packet = buffer[:PACKET_SIZE]
                    buffer = buffer[PACKET_SIZE:]

                    frame = self.decode_frame(packet)
                    if frame is not None:
                        self.frame_queue.append(frame)
                        self.fps_counter.append(time.time())

            except socket.timeout:
                continue
            except Exception as e:
                print(f"Receive error: {e}")
                break

    def calculate_fps(self):
        """Calculate current FPS"""
        if len(self.fps_counter) < 2:
            return 0
        duration = self.fps_counter[-1] - self.fps_counter[0]
        if duration <= 0:
            return 0
        return len(self.fps_counter) / duration

    def run(self):
        """Main display loop"""
        try:
            self.connect()
        except Exception as e:
            print(f"Connection failed: {e}")
            return

        self.running = True

        # Start receive thread
        recv_thread = threading.Thread(target=self.receive_thread, daemon=True)
        recv_thread.start()

        print("\nXREAL Eye Live Video")
        print("Press 'q' to quit, 's' to save frame")
        print("-" * 40)

        cv2.namedWindow("XREAL Eye Camera", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("XREAL Eye Camera", WIDTH * 2, HEIGHT * 2)

        frame_count = 0
        last_frame = None

        while self.running:
            # Get latest frame
            if self.frame_queue:
                frame = self.frame_queue.pop()
                last_frame = frame
                frame_count += 1
            elif last_frame is not None:
                frame = last_frame
            else:
                time.sleep(0.01)
                continue

            # Convert to BGR for display
            display = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

            # Add FPS overlay
            fps = self.calculate_fps()
            cv2.putText(display, f"FPS: {fps:.1f}", (10, 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(display, f"Frame: {frame_count}", (10, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Show frame
            cv2.imshow("XREAL Eye Camera", display)

            # Handle keyboard
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                filename = f"xreal_frame_{frame_count}.png"
                cv2.imwrite(filename, frame)
                print(f"Saved: {filename}")

        self.running = False
        cv2.destroyAllWindows()

        if self.sock:
            self.sock.close()

        print(f"\nTotal frames: {frame_count}")

def main():
    print("=" * 50)
    print("  XREAL Eye Live Video Viewer")
    print("  Format: 512x378 @ 4-bit grayscale")
    print("=" * 50)

    viewer = XrealEyeViewer()
    viewer.run()

if __name__ == "__main__":
    main()
