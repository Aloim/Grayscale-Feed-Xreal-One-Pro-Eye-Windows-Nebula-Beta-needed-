# XREAL Eye Camera Streaming Tool (Windows)

Stream video from the XREAL One Pro glasses Eye camera accessory on Windows.

## Requirements

### Hardware
- **XREAL One Pro glasses** with **Eye camera accessory** connected
- **USB-C cable** to connect glasses to PC
- **Windows 10/11** PC

### Software
- **Windows Nebula Beta** - Required for Eye camera streaming. Request access on the [XREAL Official Discord](https://discord.gg/QStWHRBajD) or [XREAL Community Discord](https://discord.com/invite/WBHTKMgjjB)
- **Python 3.10+** (3.11 or 3.12 recommended)
- **pip** (Python package manager)
- **Microsoft Visual C++ Redistributable** - Required for OpenCV. Download from [Microsoft](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)

## Installation

### 1. Install Python

Download from [python.org](https://www.python.org/downloads/windows/) if not installed.

Make sure to check **"Add Python to PATH"** during installation.

### 2. Clone/Download this folder

### 3. Install dependencies

Open Command Prompt or PowerShell in this folder and run:

```bash
pip install -r requirements.txt
```

This installs:
- `numpy` - Array processing
- `opencv-python` - Image/video display
- `Pillow` - Image processing
- `netifaces` - Network interface detection
- `colorama` - Colored terminal output
- `pyusb` - USB communication (optional)

## Pre-Launch Setup

**IMPORTANT:** Before running the app, ensure:

1. **Eye accessory is connected** to your XREAL One Pro glasses
2. **Spatial Anchor is activated** in the glasses settings/menu
3. **Glasses are connected** to PC via USB-C cable
4. **Windows detects the NCM network adapter** (check Network Adapters for "USB Ethernet/RNDIS Gadget")

## Usage

### Live Video Viewer (Main App)

Stream live video from the Eye camera:

```bash
cd src
python live_video_viewer.py
```

Press `Q` to quit.

### Full GUI Application

Full GUI with IMU data, service scanner, and camera launcher:

```bash
cd src
python main.py
```

Features:
- Real-time IMU (accelerometer/gyroscope) display
- Service port scanner
- "Launch Camera" button to open video viewer

### Video Decoder (Offline)

Decode previously captured video data:

```bash
cd src
python video_decoder.py
```

### IMU Reader

Stream IMU (accelerometer/gyroscope) data:

```bash
cd src
python imu_reader.py
```

## How It Works

When XREAL glasses connect via USB-C, Windows creates an NCM (Network Control Model) virtual ethernet adapter. The glasses expose services on link-local IP addresses:

| Address | Device |
|---------|--------|
| `169.254.2.1` | Glasses |
| `169.254.2.10` | Host PC (auto-assigned) |

### Available Ports

| Port | Protocol | Service |
|------|----------|---------|
| 52997 | TCP | **Video Stream** (grayscale SLAM cameras) |
| 52998 | TCP | IMU Data |
| 52996 | TCP | Metadata |
| 52999 | TCP | Control |

## Troubleshooting

### "Connection refused" to 169.254.2.1

1. Check Windows Network Adapters for "USB Ethernet/RNDIS Gadget"
2. Run `ipconfig` - verify you have a 169.254.x.x address
3. Try `ping 169.254.2.1` - should succeed if glasses are connected
4. **Make sure Spatial Anchor is activated** in the glasses menu

### No network adapter appears

1. Try a different USB-C cable (some are charge-only)
2. Try a different USB port
3. Check Device Manager for unknown devices
4. Restart the glasses (disconnect and reconnect)

### Video not streaming

1. Ensure **Eye accessory is connected** to glasses
2. Ensure **Spatial Anchor is enabled** in glasses settings
3. Try restarting the glasses while connected to PC

### Python errors

```bash
# Upgrade pip
python -m pip install --upgrade pip

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## File Structure

```
WindowsTestApp/
├── src/                    # Python source code
│   ├── live_video_viewer.py   # Main video streaming app
│   ├── main.py                # Full GUI application
│   ├── video_decoder.py       # Offline video decoder
│   ├── imu_reader.py          # IMU data reader
│   ├── config.py              # Configuration constants
│   └── ...                    # Other utilities
├── output/                 # Generated images/videos
├── data/                   # Raw captured data
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Video Format

The Eye camera streams grayscale video from the SLAM cameras:

- **Resolution:** 512 x 378 per camera (stereo pair)
- **Format:** 4-bit grayscale encoding
- **Protocol:** Custom TCP stream on port 52997

## Credits

- **6dofXrealWebcam** - Protocol reference
- **SamiMitwalli/One-Pro-IMU-Retriever-Demo** - IMU protocol discovery

## License

This tool is for research and educational purposes only.
