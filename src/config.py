"""
XREAL Eye Windows Test App - Configuration

Protocol constants and settings based on reverse engineering
and the 6dofXrealWebcam project.
"""

# =============================================================================
# Network Addresses
# =============================================================================

# XREAL glasses IP (via NCM virtual ethernet)
GLASSES_IP_PRIMARY = "169.254.2.1"
GLASSES_IP_SECONDARY = "169.254.1.1"

# Host IP (assigned by Windows)
HOST_IP_PRIMARY = "169.254.2.10"
HOST_IP_SECONDARY = "169.254.1.10"

# =============================================================================
# Service Ports
# =============================================================================

# IMU data stream (VERIFIED WORKING)
PORT_IMU = 52998

# Camera-related ports (need discovery)
PORT_GRPC = 50051          # gRPC streaming server
PORT_CONTROL = 8848        # Control channel
PORT_DISCOVERY = 6001      # UDP discovery ("FIND-SERVER")
PORT_VIDEO_RTP = 5555      # RTP video stream

# =============================================================================
# IMU Protocol Constants (from 6dofXrealWebcam)
# =============================================================================

# Message framing
IMU_HEADER = bytes.fromhex("283600000080")  # 6 bytes
IMU_HEADER_ALT = bytes.fromhex("273600000080")  # Alternate header variant
IMU_FOOTER = bytes.fromhex("000000cff753e3a59b0000db34b6d782de1b43")  # 20 bytes

# Data layout
IMU_HEADER_SIZE = 6
IMU_DATA_SIZE = 24         # 6 floats * 4 bytes
IMU_FOOTER_SIZE = 20

# Data offsets within message (from reference implementation)
DATA_START_OFFSET = 20     # timestamp(8) + invariant(2) + static(10)
DATA_END_OFFSET = -26      # sensor_msg(6) + date_info(20)

# =============================================================================
# Control Channel Protocol
# =============================================================================

class MessageType:
    """Control channel message types"""
    NONE = 0
    CONNECTED = 1
    DISCONNECT = 2
    HEARTBEAT = 3
    ENTER_ROOM = 4
    EXIT_ROOM = 5
    UPDATE_CAMERA_PARAM = 6
    MESSAGE_SYNC = 7

# =============================================================================
# RTP Video Protocol
# =============================================================================

RTP_HEADER_SIZE = 12
DEFAULT_VIDEO_WIDTH = 1280
DEFAULT_VIDEO_HEIGHT = 720
DEFAULT_VIDEO_FPS = 30

# YUV format
YUV_420_MULTIPLIER = 1.5   # YUV 4:2:0 = 1.5 bytes per pixel

# =============================================================================
# Connection Settings
# =============================================================================

CONNECT_TIMEOUT = 5.0      # TCP connection timeout (seconds)
READ_TIMEOUT = 1.0         # Socket read timeout (seconds)
RECONNECT_DELAY = 2.0      # Auto-reconnect delay (seconds)
HEARTBEAT_INTERVAL = 1.0   # Control channel heartbeat (seconds)

# =============================================================================
# USB Device IDs (for potential HID access)
# =============================================================================

XREAL_VENDOR_ID = 0x3318   # 13080
XREAL_PRODUCT_ID = 0x0436  # 1078

# HID command types
HID_TYPE_GET = 0x30
HID_TYPE_SET = 0x31
HID_TYPE_EVT = 0x32

# Known HID command codes
HID_CMD_HEARTBEAT = 0x66
HID_CMD_RGB_ENABLE = 0x68
HID_CMD_RGB_STREAM = 0x69
HID_CMD_NETWORK_ENABLE = 0x6A
