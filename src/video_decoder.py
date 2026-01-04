#!/usr/bin/env python3
"""
XREAL Eye Video Decoder - Proprietary format decoder
Tries multiple approaches to decode the video stream from port 52997
"""

import socket
import struct
import numpy as np
from PIL import Image
import os
import time
from datetime import datetime

GLASSES_IP = "169.254.2.1"
VIDEO_PORT = 52997
PACKET_SIZE = 193862  # Fixed packet size
HEADER_SIZE = 320     # Estimated header size before image data

def capture_frames(num_frames=5, output_dir="decoded_frames"):
    """Capture raw video frames from the glasses"""
    os.makedirs(output_dir, exist_ok=True)

    print(f"Connecting to {GLASSES_IP}:{VIDEO_PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((GLASSES_IP, VIDEO_PORT))
    print("Connected! Capturing frames...")

    frames = []
    buffer = b''

    try:
        while len(frames) < num_frames:
            data = sock.recv(65536)
            if not data:
                break
            buffer += data

            # Extract complete packets
            while len(buffer) >= PACKET_SIZE:
                packet = buffer[:PACKET_SIZE]
                buffer = buffer[PACKET_SIZE:]
                frames.append(packet)
                print(f"Captured frame {len(frames)}/{num_frames}")
    except Exception as e:
        print(f"Capture error: {e}")
    finally:
        sock.close()

    return frames

def analyze_packet_structure(packet):
    """Analyze the structure of a video packet"""
    print("\n=== PACKET STRUCTURE ANALYSIS ===")
    print(f"Total size: {len(packet)} bytes")

    # Header fields (from session summary)
    header = struct.unpack(">H", packet[0:2])[0]
    payload_len = struct.unpack(">I", packet[2:6])[0]
    print(f"Header: 0x{header:04x}")
    print(f"Payload length: {payload_len}")

    # Look for patterns in the data
    print("\nFirst 64 bytes (hex):")
    print(packet[:64].hex())

    # Find where actual image data starts
    print("\nSearching for image data start...")
    for offset in [0x100, 0x140, 0x180, 0x1C0, 0x200]:
        sample = packet[offset:offset+32]
        unique_bytes = len(set(sample))
        print(f"Offset 0x{offset:03x}: {unique_bytes} unique bytes in 32-byte window")
        print(f"  Data: {sample.hex()}")

    return payload_len

def try_decode_raw_grayscale(packet, offset=0x140, width=640, height=480):
    """Try decoding as raw grayscale (1 byte per pixel)"""
    data = packet[offset:]
    needed = width * height

    if len(data) < needed:
        print(f"Not enough data for {width}x{height}: need {needed}, have {len(data)}")
        return None

    pixels = np.frombuffer(data[:needed], dtype=np.uint8)
    img = pixels.reshape((height, width))
    return Image.fromarray(img, mode='L')

def try_decode_high_nibble(packet, offset=0x140, width=640, height=480):
    """Decode using only high nibble as 4-bit grayscale"""
    data = packet[offset:]
    needed = width * height

    if len(data) < needed:
        return None

    pixels = np.frombuffer(data[:needed], dtype=np.uint8)
    # Extract high nibble and scale to 8-bit
    pixels = ((pixels >> 4) & 0x0F) * 17  # Scale 0-15 to 0-255
    img = pixels.reshape((height, width))
    return Image.fromarray(img, mode='L')

def try_decode_low_nibble(packet, offset=0x140, width=640, height=480):
    """Decode using only low nibble as 4-bit grayscale"""
    data = packet[offset:]
    needed = width * height

    if len(data) < needed:
        return None

    pixels = np.frombuffer(data[:needed], dtype=np.uint8)
    # Extract low nibble and scale to 8-bit
    pixels = (pixels & 0x0F) * 17
    img = pixels.reshape((height, width))
    return Image.fromarray(img, mode='L')

def try_decode_packed_nibbles(packet, offset=0x140, width=640, height=480):
    """Decode as packed 4-bit pixels (2 pixels per byte)"""
    data = packet[offset:]
    needed = (width * height) // 2

    if len(data) < needed:
        return None

    raw = np.frombuffer(data[:needed], dtype=np.uint8)
    # Unpack: high nibble first, then low nibble
    high = ((raw >> 4) & 0x0F) * 17
    low = (raw & 0x0F) * 17

    pixels = np.empty(len(raw) * 2, dtype=np.uint8)
    pixels[0::2] = high
    pixels[1::2] = low

    img = pixels.reshape((height, width))
    return Image.fromarray(img, mode='L')

def try_decode_nv12(packet, offset=0x140, width=640, height=480):
    """Decode as NV12 YUV format (Y plane + interleaved UV)"""
    data = packet[offset:]
    y_size = width * height
    uv_size = y_size // 2  # UV is half resolution
    needed = y_size + uv_size

    if len(data) < needed:
        return None

    # Extract Y plane only (grayscale)
    y_plane = np.frombuffer(data[:y_size], dtype=np.uint8)
    img = y_plane.reshape((height, width))
    return Image.fromarray(img, mode='L')

def try_decode_yuyv(packet, offset=0x140, width=640, height=480):
    """Decode as YUYV (YUY2) packed format"""
    data = packet[offset:]
    needed = width * height * 2  # 2 bytes per pixel

    if len(data) < needed:
        return None

    raw = np.frombuffer(data[:needed], dtype=np.uint8)
    # YUYV: Y0 U Y1 V - extract just Y values
    y_values = raw[0::2]  # Every other byte is Y
    img = y_values.reshape((height, width))
    return Image.fromarray(img, mode='L')

def try_decode_bayer(packet, offset=0x140, width=640, height=480):
    """Decode as raw Bayer pattern (single channel)"""
    data = packet[offset:]
    needed = width * height

    if len(data) < needed:
        return None

    pixels = np.frombuffer(data[:needed], dtype=np.uint8)
    img = pixels.reshape((height, width))
    return Image.fromarray(img, mode='L')

def try_decode_rgb565(packet, offset=0x140, width=640, height=480):
    """Decode as RGB565 (16-bit color)"""
    data = packet[offset:]
    needed = width * height * 2

    if len(data) < needed:
        return None

    raw = np.frombuffer(data[:needed], dtype=np.uint16)

    r = ((raw >> 11) & 0x1F) * 8
    g = ((raw >> 5) & 0x3F) * 4
    b = (raw & 0x1F) * 8

    rgb = np.stack([r, g, b], axis=-1).astype(np.uint8)
    img = rgb.reshape((height, width, 3))
    return Image.fromarray(img, mode='RGB')

def try_decode_custom_xreal(packet, offset=0x140, width=640, height=480):
    """
    Custom XREAL format hypothesis:
    Based on pattern 0x12, 0x22, 0x32, 0x42, 0x52...
    - High nibble (0x1, 0x2, 0x3...) = pixel value 0-15
    - Low nibble (0x2) = marker/format indicator
    """
    data = packet[offset:]
    needed = width * height

    if len(data) < needed:
        return None

    pixels = np.frombuffer(data[:needed], dtype=np.uint8)

    # Decode: pixel = high_nibble * 16 + (high_nibble)
    # This spreads 0-15 to 0-255 more smoothly
    high = (pixels >> 4) & 0x0F
    result = high * 17  # 0->0, 1->17, ..., 15->255

    img = result.reshape((height, width))
    return Image.fromarray(img, mode='L')

def find_frame_boundaries(data):
    """Look for patterns that might indicate frame boundaries"""
    print("\n=== SEARCHING FOR FRAME BOUNDARIES ===")

    # Common markers
    markers = [
        (b'\x00\x00\x00\x01', "H.264 NAL"),
        (b'\xFF\xD8', "JPEG SOI"),
        (b'\xFF\xD9', "JPEG EOI"),
        (b'\x00\x00\x01', "MPEG start"),
        (b'\x78\x73\x34\x00', "XS4 marker (seen in capture)"),
        (b'xs4', "xs4 ASCII"),
    ]

    for marker, name in markers:
        positions = []
        pos = 0
        while True:
            idx = data.find(marker, pos)
            if idx == -1:
                break
            positions.append(idx)
            pos = idx + 1
            if len(positions) > 10:
                break

        if positions:
            print(f"{name} found at: {positions[:5]}...")

def analyze_byte_distribution(data, offset=0x140, sample_size=10000):
    """Analyze the distribution of byte values"""
    print("\n=== BYTE DISTRIBUTION ANALYSIS ===")

    sample = data[offset:offset+sample_size]

    # Count occurrences of each byte value
    counts = {}
    for b in sample:
        counts[b] = counts.get(b, 0) + 1

    # Sort by frequency
    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    print("Top 20 most common bytes:")
    for byte_val, count in sorted_counts[:20]:
        high = (byte_val >> 4) & 0x0F
        low = byte_val & 0x0F
        pct = count / len(sample) * 100
        print(f"  0x{byte_val:02x} (hi:{high:x} lo:{low:x}): {count} ({pct:.1f}%)")

    # Analyze high/low nibble patterns
    high_nibbles = [(b >> 4) & 0x0F for b in sample]
    low_nibbles = [b & 0x0F for b in sample]

    print(f"\nHigh nibble distribution: {set(high_nibbles)}")
    print(f"Low nibble distribution: {set(low_nibbles)}")

def calculate_possible_resolutions(data_size):
    """Calculate possible resolutions for the data"""
    print(f"\n=== POSSIBLE RESOLUTIONS FOR {data_size} BYTES ===")

    # Common aspect ratios
    aspects = [
        (4, 3, "4:3"),
        (16, 9, "16:9"),
        (16, 10, "16:10"),
        (3, 2, "3:2"),
        (1, 1, "1:1"),
    ]

    # Different bytes per pixel
    bpp_options = [
        (1, "8-bit grayscale"),
        (0.5, "4-bit packed"),
        (2, "16-bit (RGB565/YUV)"),
        (1.5, "12-bit (NV12)"),
        (3, "24-bit RGB"),
    ]

    for bpp, bpp_name in bpp_options:
        total_pixels = int(data_size / bpp)
        print(f"\n{bpp_name} ({bpp} bytes/pixel) = {total_pixels} pixels:")

        for aw, ah, aname in aspects:
            # width = sqrt(total_pixels * aw / ah)
            import math
            width = int(math.sqrt(total_pixels * aw / ah))
            height = int(total_pixels / width)

            # Round to common sizes
            for w in [width-width%8, width, width+8-width%8]:
                for h in [height-height%8, height, height+8-height%8]:
                    if w > 0 and h > 0 and abs(w*h - total_pixels) < total_pixels * 0.01:
                        print(f"  {aname}: {w}x{h} = {w*h} pixels (diff: {w*h - total_pixels})")

def try_all_decoders(packet, output_dir="decoded_frames"):
    """Try all decoding methods"""
    os.makedirs(output_dir, exist_ok=True)

    # Calculate image data size (packet minus header)
    image_data_size = len(packet) - 0x140  # ~193,542 bytes

    print(f"\nImage data size: {image_data_size} bytes")
    calculate_possible_resolutions(image_data_size)

    # Resolutions to try (based on calculations)
    resolutions = [
        (640, 480),    # VGA
        (640, 360),    # 16:9
        (720, 480),    # NTSC
        (800, 600),    # SVGA
        (504, 384),    # Custom
        (432, 448),    # ~193536 for grayscale
        (440, 440),    # Square
        (1280, 720),   # HD (for packed/compressed)
        (320, 240),    # QVGA
        (384, 504),    # Rotated
        (552, 350),    # Custom ratio
        (456, 424),    # Close to sqrt
        (696, 278),    # 16:9 close
    ]

    decoders = [
        ("raw_grayscale", try_decode_raw_grayscale),
        ("high_nibble", try_decode_high_nibble),
        ("low_nibble", try_decode_low_nibble),
        ("packed_nibbles", try_decode_packed_nibbles),
        ("nv12_y", try_decode_nv12),
        ("yuyv", try_decode_yuyv),
        ("bayer", try_decode_bayer),
        ("rgb565", try_decode_rgb565),
        ("custom_xreal", try_decode_custom_xreal),
    ]

    results = []

    for res in resolutions:
        for decoder_name, decoder_func in decoders:
            try:
                img = decoder_func(packet, offset=0x140, width=res[0], height=res[1])
                if img:
                    filename = f"{output_dir}/{decoder_name}_{res[0]}x{res[1]}.png"
                    img.save(filename)
                    results.append((filename, res, decoder_name))
                    print(f"Saved: {filename}")
            except Exception as e:
                pass  # Skip failed decodes

    return results

def live_decode_test():
    """Capture and decode a live frame"""
    print("=" * 60)
    print("XREAL Eye Video Decoder - Live Test")
    print("=" * 60)

    # Capture frames
    frames = capture_frames(num_frames=3)

    if not frames:
        print("No frames captured!")
        return

    print(f"\nCaptured {len(frames)} frames")

    # Analyze first frame
    packet = frames[0]
    analyze_packet_structure(packet)
    analyze_byte_distribution(packet)
    find_frame_boundaries(packet)

    # Try all decoders
    print("\n" + "=" * 60)
    print("TRYING ALL DECODERS...")
    print("=" * 60)

    results = try_all_decoders(packet)

    print(f"\n\nGenerated {len(results)} test images")
    print("Check the decoded_frames/ directory")

    # Save raw frame for manual analysis
    with open("decoded_frames/raw_frame.bin", "wb") as f:
        f.write(packet)
    print("Saved raw frame to decoded_frames/raw_frame.bin")

if __name__ == "__main__":
    live_decode_test()
