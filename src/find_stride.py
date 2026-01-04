#!/usr/bin/env python3
"""
Find correct stride/line width for XREAL Eye video
The diagonal lines indicate wrong row width
"""

import socket
import numpy as np
from PIL import Image
import os

GLASSES_IP = "169.254.2.1"
VIDEO_PORT = 52997

def capture_frame():
    """Capture one frame"""
    print(f"Connecting to {GLASSES_IP}:{VIDEO_PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((GLASSES_IP, VIDEO_PORT))

    data = b''
    while len(data) < 193862:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
    sock.close()

    print(f"Captured {len(data)} bytes")
    return data

def decode_with_stride(data, offset, stride, height):
    """Decode image with given stride (line width in bytes)"""
    # Skip header, use high nibble as pixel value
    pixels = np.frombuffer(data[offset:], dtype=np.uint8)

    # Extract high nibble and scale
    pixels = ((pixels >> 4) & 0x0F) * 17

    # Calculate how many complete lines we can get
    total_bytes = len(pixels)
    max_lines = total_bytes // stride

    if max_lines < height:
        height = max_lines

    if height < 10:
        return None

    # Reshape with stride
    img_data = pixels[:stride * height].reshape((height, stride))

    return Image.fromarray(img_data, mode='L')

def find_correct_stride():
    """Try many strides to find the correct one"""
    # Capture frame
    frame = capture_frame()

    os.makedirs("stride_test", exist_ok=True)

    # Image data starts at offset 0x140 (320 bytes)
    offset = 0x140
    data_size = len(frame) - offset  # ~193542 bytes

    print(f"\nData size after header: {data_size} bytes")
    print("\nTrying different strides...")

    # Common video widths to try
    widths = [
        # Standard widths
        320, 352, 384, 400, 416, 432, 448, 480, 504, 512,
        528, 544, 560, 576, 592, 608, 624, 640, 656, 672,
        688, 704, 720, 736, 752, 768, 784, 800, 816, 832,
        848, 864, 880, 896, 912, 928, 944, 960, 976, 992,
        1008, 1024, 1040, 1056, 1072, 1088, 1104, 1120, 1136,
        1152, 1168, 1184, 1200, 1216, 1232, 1248, 1264, 1280,
        # Try packed (2 pixels per byte)
        640, 720, 768, 800, 960, 1024, 1280,
        # Common camera widths
        640, 720, 800, 848, 960, 1024, 1280, 1440, 1920,
        # XREAL Eye specific guesses
        504, 508, 512, 520, 524, 528, 532, 536, 540,
        # USB camera common
        160, 176, 320, 352, 640, 704, 1280,
    ]

    # Remove duplicates and sort
    widths = sorted(set(widths))

    saved = []
    for stride in widths:
        # Calculate height for this stride
        height = data_size // stride

        if height < 100 or height > 1200:
            continue

        img = decode_with_stride(frame, offset, stride, height)
        if img:
            filename = f"stride_test/stride_{stride}x{height}.png"
            img.save(filename)
            saved.append((stride, height, filename))
            print(f"  Saved: {filename}")

    print(f"\nGenerated {len(saved)} test images")
    print("Check stride_test/ folder for recognizable image")

    # Also try treating 0xFF as line delimiters
    print("\n\nLooking for 0xFF line delimiters...")
    data = frame[offset:]
    ff_positions = [i for i, b in enumerate(data[:50000]) if b == 0xFF]

    if len(ff_positions) > 10:
        # Calculate distances between 0xFF markers
        distances = [ff_positions[i+1] - ff_positions[i] for i in range(min(50, len(ff_positions)-1))]
        from collections import Counter
        common_distances = Counter(distances).most_common(10)
        print(f"Most common distances between 0xFF: {common_distances}")

        # Try the most common distance as stride
        for dist, count in common_distances[:3]:
            if 100 < dist < 2000:
                height = data_size // dist
                img = decode_with_stride(frame, offset, dist, height)
                if img:
                    filename = f"stride_test/ff_stride_{dist}x{height}.png"
                    img.save(filename)
                    print(f"  Saved: {filename}")

    # Also check for repeating patterns
    print("\n\nSearching for line patterns...")
    sample = frame[offset:offset+10000]

    # Look for repeating sequences
    for test_stride in range(400, 700):
        line1 = sample[:test_stride]
        line2 = sample[test_stride:test_stride*2]

        # Check if lines start/end similarly (common in video)
        if line1[:4] == line2[:4] or line1[-4:] == line2[-4:]:
            print(f"Possible stride {test_stride}: lines have similar boundaries")

if __name__ == "__main__":
    find_correct_stride()
