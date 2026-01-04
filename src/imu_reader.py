"""
XREAL Eye IMU Reader

TCP client for reading IMU data from XREAL One Pro glasses.
Based on 6dofXrealWebcam and SamiMitwalli/One-Pro-IMU-Retriever-Demo.
"""

import socket
import struct
import threading
import time
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Tuple
from enum import Enum

from config import (
    GLASSES_IP_PRIMARY,
    PORT_IMU,
    IMU_HEADER,
    IMU_HEADER_ALT,
    IMU_FOOTER,
    CONNECT_TIMEOUT,
    READ_TIMEOUT,
    RECONNECT_DELAY,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """IMU reader connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ImuData:
    """Parsed IMU sensor data"""
    gyro_x: float      # Gyroscope X (rad/s)
    gyro_y: float      # Gyroscope Y (rad/s)
    gyro_z: float      # Gyroscope Z (rad/s)
    accel_x: float     # Accelerometer X (m/s^2)
    accel_y: float     # Accelerometer Y (m/s^2)
    accel_z: float     # Accelerometer Z (m/s^2)
    timestamp: float   # Local receive timestamp

    def __str__(self):
        return (f"IMU: gyro=({self.gyro_x:.3f}, {self.gyro_y:.3f}, {self.gyro_z:.3f}) "
                f"accel=({self.accel_x:.3f}, {self.accel_y:.3f}, {self.accel_z:.3f})")


class ImuPacketParser:
    """
    Parse binary IMU packets from TCP stream.

    Packet format (from reference implementation):
    [HEADER(6)] [timestamp(8)] [invariant(2)] [static(10)] [IMU_DATA(24)] [sensor_msg(6)] [date_info(20)] [FOOTER(20)]

    Simplified parsing using header/footer detection.
    """

    HEADERS = [IMU_HEADER, IMU_HEADER_ALT]

    def __init__(self):
        self.packets_parsed = 0
        self.bytes_processed = 0

    def find_packet(self, buffer: bytes) -> Optional[Tuple[ImuData, int]]:
        """
        Find and parse next IMU packet in buffer by scanning for valid IMU data.

        Returns:
            (ImuData, bytes_consumed) if packet found, None otherwise
        """
        # Scan buffer for valid IMU data pattern (6 floats with gravity signature)
        for offset in range(0, len(buffer) - 24, 4):
            try:
                values = struct.unpack('<6f', buffer[offset:offset + 24])

                # Check for valid IMU: gyro reasonable, accel ~9.8 m/s^2
                gyro_ok = all(-10 < v < 10 for v in values[:3])
                accel_mag = (values[3]**2 + values[4]**2 + values[5]**2) ** 0.5

                if gyro_ok and 9.0 < accel_mag < 11.0:
                    imu_data = ImuData(
                        gyro_x=values[0],
                        gyro_y=values[1],
                        gyro_z=values[2],
                        accel_x=values[3],
                        accel_y=values[4],
                        accel_z=values[5],
                        timestamp=time.time()
                    )
                    self.packets_parsed += 1
                    # Consume up to end of this IMU data
                    return (imu_data, offset + 24)
            except struct.error:
                continue

        return None

    def _parse_message(self, message: bytes) -> Optional[ImuData]:
        """
        Extract IMU data from complete message.

        The 6 floats (gyro xyz, accel xyz) are at offset 168 from packet start.
        Discovered via packet analysis: offset 168 gives mag ~9.81 (gravity).
        """
        # Need at least 168 + 24 bytes for IMU data
        min_size = 168 + 24
        if len(message) < min_size:
            return self._parse_message_search(message)

        try:
            # IMU data is at offset 168 from packet start (verified via analysis)
            data_start = 168
            imu_bytes = message[data_start:data_start + 24]
            values = struct.unpack('<6f', imu_bytes)

            # Sanity check - gyro reasonable and accel magnitude ~9.8 (gravity)
            gyro_ok = all(-10 < v < 10 for v in values[:3])
            accel_mag = (values[3]**2 + values[4]**2 + values[5]**2) ** 0.5

            if gyro_ok and 9.0 < accel_mag < 11.0:
                return ImuData(
                    gyro_x=values[0],
                    gyro_y=values[1],
                    gyro_z=values[2],
                    accel_x=values[3],
                    accel_y=values[4],
                    accel_z=values[5],
                    timestamp=time.time()
                )
        except struct.error:
            pass

        return self._parse_message_search(message)

    def _parse_message_search(self, message: bytes) -> Optional[ImuData]:
        """
        Search for valid IMU data within message by scanning for reasonable values.
        """
        # Search through message looking for 6 consecutive reasonable floats
        for offset in range(0, len(message) - 24, 4):
            try:
                values = struct.unpack('<6f', message[offset:offset + 24])

                # Check if values look like IMU data:
                # - Gyro: typically small values (-10 to 10 rad/s)
                # - Accel: should have magnitude ~9.8 (gravity)
                gyro_ok = all(-10 < v < 10 for v in values[:3])
                accel_magnitude = (values[3]**2 + values[4]**2 + values[5]**2) ** 0.5
                accel_ok = 9.0 < accel_magnitude < 11.0  # Tighter gravity check

                if gyro_ok and accel_ok:
                    return ImuData(
                        gyro_x=values[0],
                        gyro_y=values[1],
                        gyro_z=values[2],
                        accel_z=values[3],
                        accel_y=values[4],
                        accel_x=values[5],
                        timestamp=time.time()
                    )
            except struct.error:
                continue

        return None


class ImuReader:
    """
    XREAL IMU TCP client.

    Connects to the glasses via TCP and reads IMU sensor data.
    """

    def __init__(
        self,
        host: str = GLASSES_IP_PRIMARY,
        port: int = PORT_IMU,
        on_data: Optional[Callable[[ImuData], None]] = None,
        on_state_change: Optional[Callable[[ConnectionState], None]] = None,
        auto_reconnect: bool = True
    ):
        self.host = host
        self.port = port
        self.on_data = on_data
        self.on_state_change = on_state_change
        self.auto_reconnect = auto_reconnect

        self._socket: Optional[socket.socket] = None
        self._state = ConnectionState.DISCONNECTED
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._parser = ImuPacketParser()

        # Statistics
        self.packets_received = 0
        self.last_packet_time = 0.0
        self._latest_data: Optional[ImuData] = None
        self._data_lock = threading.Lock()

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    def get_latest(self) -> Optional[ImuData]:
        """Get the most recent IMU data (thread-safe)"""
        with self._data_lock:
            return self._latest_data

    def start(self) -> bool:
        """
        Start reading IMU data in background thread.

        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("IMU reader already running")
            return True

        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """Stop reading and close connection"""
        self._running = False
        self._disconnect()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _set_state(self, state: ConnectionState):
        """Update connection state and notify callback"""
        if state != self._state:
            self._state = state
            logger.info(f"IMU connection state: {state.value}")
            if self.on_state_change:
                try:
                    self.on_state_change(state)
                except Exception as e:
                    logger.error(f"State change callback error: {e}")

    def _connect(self) -> bool:
        """Establish TCP connection to glasses"""
        self._set_state(ConnectionState.CONNECTING)

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(CONNECT_TIMEOUT)

            logger.info(f"Connecting to {self.host}:{self.port}...")
            self._socket.connect((self.host, self.port))
            self._socket.settimeout(READ_TIMEOUT)

            self._set_state(ConnectionState.CONNECTED)
            logger.info(f"Connected to XREAL IMU at {self.host}:{self.port}")
            return True

        except socket.timeout:
            logger.error(f"Connection timeout to {self.host}:{self.port}")
            self._set_state(ConnectionState.ERROR)
            return False

        except ConnectionRefusedError:
            logger.error(f"Connection refused - is the device connected?")
            self._set_state(ConnectionState.ERROR)
            return False

        except OSError as e:
            logger.error(f"Connection error: {e}")
            self._set_state(ConnectionState.ERROR)
            return False

    def _disconnect(self):
        """Close TCP connection"""
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._set_state(ConnectionState.DISCONNECTED)

    def _read_loop(self):
        """Main background thread loop"""
        buffer = b''

        while self._running:
            # Connect if needed
            if self._socket is None:
                if not self._connect():
                    if self.auto_reconnect:
                        time.sleep(RECONNECT_DELAY)
                        continue
                    else:
                        break

            # Read data
            try:
                data = self._socket.recv(4096)

                if not data:
                    logger.warning("Connection closed by remote")
                    self._disconnect()
                    buffer = b''
                    continue

                buffer += data

                # Parse packets from buffer
                while True:
                    result = self._parser.find_packet(buffer)
                    if result is None:
                        # Keep buffer but prevent unbounded growth
                        if len(buffer) > 10000:
                            # Keep last portion that might have partial packet
                            buffer = buffer[-1000:]
                        break

                    imu_data, consumed = result
                    buffer = buffer[consumed:]

                    # Update statistics and latest data
                    self.packets_received += 1
                    self.last_packet_time = time.time()

                    with self._data_lock:
                        self._latest_data = imu_data

                    # Notify callback
                    if self.on_data:
                        try:
                            self.on_data(imu_data)
                        except Exception as e:
                            logger.error(f"Data callback error: {e}")

            except socket.timeout:
                # Normal timeout, continue
                continue

            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.warning(f"Connection error: {e}")
                self._disconnect()
                buffer = b''

        # Cleanup on exit
        self._disconnect()


# =============================================================================
# Command-line test
# =============================================================================

def main():
    """Test IMU reader from command line"""
    import sys

    print("=" * 60)
    print("XREAL IMU Reader Test")
    print("=" * 60)
    print(f"Connecting to {GLASSES_IP_PRIMARY}:{PORT_IMU}...")
    print("Press Ctrl+C to stop")
    print()

    # Statistics
    start_time = time.time()
    packet_count = 0

    def on_data(imu: ImuData):
        nonlocal packet_count
        packet_count += 1

        # Clear line and print
        elapsed = time.time() - start_time
        rate = packet_count / elapsed if elapsed > 0 else 0

        sys.stdout.write(f"\r[{packet_count:6d}] {imu} ({rate:.1f} Hz)    ")
        sys.stdout.flush()

    def on_state(state: ConnectionState):
        print(f"\nConnection state: {state.value}")

    reader = ImuReader(
        on_data=on_data,
        on_state_change=on_state,
        auto_reconnect=True
    )

    try:
        reader.start()

        # Keep running until Ctrl+C
        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        reader.stop()

        elapsed = time.time() - start_time
        rate = packet_count / elapsed if elapsed > 0 else 0
        print(f"\nReceived {packet_count} packets in {elapsed:.1f}s ({rate:.1f} Hz)")


if __name__ == "__main__":
    main()
