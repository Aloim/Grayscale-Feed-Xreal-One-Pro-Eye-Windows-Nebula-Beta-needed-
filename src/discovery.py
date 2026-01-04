"""
XREAL Eye Service Discovery

Port scanning and protocol probing for XREAL glasses services.
"""

import socket
import struct
import time
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from enum import Enum

from config import (
    GLASSES_IP_PRIMARY,
    GLASSES_IP_SECONDARY,
    PORT_IMU,
    PORT_GRPC,
    PORT_CONTROL,
    PORT_DISCOVERY,
    PORT_VIDEO_RTP,
)


class ServiceStatus(Enum):
    """Service availability status"""
    UNKNOWN = "unknown"
    OPEN = "open"
    CLOSED = "closed"
    FILTERED = "filtered"
    ERROR = "error"


@dataclass
class ServiceInfo:
    """Information about a discovered service"""
    port: int
    protocol: str  # 'tcp' or 'udp'
    status: ServiceStatus
    response: Optional[bytes] = None
    latency_ms: float = 0.0
    description: str = ""


@dataclass
class DiscoveryResult:
    """Complete discovery results"""
    host: str
    reachable: bool
    services: Dict[int, ServiceInfo]
    ncm_interface: Optional[str] = None
    scan_time: float = 0.0


class ServiceDiscovery:
    """
    Discover available XREAL glasses services.

    Probes known ports and attempts protocol handshakes
    to determine which services are available.
    """

    # Known service definitions
    SERVICES = {
        PORT_IMU: ('tcp', 'IMU Data Stream'),
        PORT_GRPC: ('tcp', 'gRPC Camera Server'),
        PORT_CONTROL: ('tcp', 'Control Channel'),
        PORT_DISCOVERY: ('udp', 'UDP Discovery'),
        PORT_VIDEO_RTP: ('udp', 'RTP Video Stream'),
    }

    def __init__(
        self,
        host: str = GLASSES_IP_PRIMARY,
        timeout: float = 1.0
    ):
        self.host = host
        self.timeout = timeout

    def discover_all(
        self,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> DiscoveryResult:
        """
        Probe all known service ports.

        Args:
            on_progress: Callback for progress updates

        Returns:
            DiscoveryResult with all findings
        """
        start_time = time.time()
        services = {}

        # Check basic reachability first
        if on_progress:
            on_progress(f"Checking reachability of {self.host}...")

        reachable = self._check_reachability()

        if not reachable:
            if on_progress:
                on_progress(f"Host {self.host} not reachable")
            return DiscoveryResult(
                host=self.host,
                reachable=False,
                services={},
                scan_time=time.time() - start_time
            )

        if on_progress:
            on_progress(f"Host {self.host} is reachable")

        # Probe each service
        for port, (proto, desc) in self.SERVICES.items():
            if on_progress:
                on_progress(f"Probing {desc} ({proto.upper()} {port})...")

            if proto == 'tcp':
                info = self._probe_tcp(port, desc)
            else:
                info = self._probe_udp(port, desc)

            services[port] = info

        # Check for NCM network interface
        ncm = self._find_ncm_interface()

        return DiscoveryResult(
            host=self.host,
            reachable=True,
            services=services,
            ncm_interface=ncm,
            scan_time=time.time() - start_time
        )

    def _check_reachability(self) -> bool:
        """Check if host is reachable via TCP probe"""
        try:
            # Try connecting to any port - connection refused still means host is up
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((self.host, 1))
            sock.close()

            # 0 = connected, 111/10061 = connection refused (host up, port closed)
            return result in [0, 111, 10061, 10060]

        except socket.timeout:
            return False
        except OSError:
            return False

    def _probe_tcp(self, port: int, description: str) -> ServiceInfo:
        """Probe a TCP port"""
        start = time.time()

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)

            result = sock.connect_ex((self.host, port))
            latency = (time.time() - start) * 1000

            if result == 0:
                # Port is open, try to receive any banner/greeting
                sock.settimeout(0.5)
                try:
                    response = sock.recv(1024)
                except socket.timeout:
                    response = None

                sock.close()

                return ServiceInfo(
                    port=port,
                    protocol='tcp',
                    status=ServiceStatus.OPEN,
                    response=response,
                    latency_ms=latency,
                    description=description
                )
            else:
                sock.close()
                return ServiceInfo(
                    port=port,
                    protocol='tcp',
                    status=ServiceStatus.CLOSED,
                    latency_ms=latency,
                    description=description
                )

        except socket.timeout:
            return ServiceInfo(
                port=port,
                protocol='tcp',
                status=ServiceStatus.FILTERED,
                description=description
            )
        except OSError as e:
            return ServiceInfo(
                port=port,
                protocol='tcp',
                status=ServiceStatus.ERROR,
                description=f"{description} (error: {e})"
            )

    def _probe_udp(self, port: int, description: str) -> ServiceInfo:
        """
        Probe a UDP port.

        Note: UDP probing is less reliable since no response
        doesn't necessarily mean the port is closed.
        """
        start = time.time()

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)

            # Send probe packet
            if port == PORT_DISCOVERY:
                # Try the discovery protocol
                probe = b"FIND-SERVER"
            else:
                probe = b"\x00" * 4  # Generic probe

            sock.sendto(probe, (self.host, port))
            latency = (time.time() - start) * 1000

            try:
                response, addr = sock.recvfrom(1024)
                sock.close()

                return ServiceInfo(
                    port=port,
                    protocol='udp',
                    status=ServiceStatus.OPEN,
                    response=response,
                    latency_ms=latency,
                    description=description
                )
            except socket.timeout:
                sock.close()

                # UDP timeout doesn't mean closed
                return ServiceInfo(
                    port=port,
                    protocol='udp',
                    status=ServiceStatus.FILTERED,
                    latency_ms=latency,
                    description=f"{description} (no response)"
                )

        except OSError as e:
            return ServiceInfo(
                port=port,
                protocol='udp',
                status=ServiceStatus.ERROR,
                description=f"{description} (error: {e})"
            )

    def _find_ncm_interface(self) -> Optional[str]:
        """
        Find the NCM network interface for XREAL glasses.

        Returns interface name if found, None otherwise.
        """
        try:
            import netifaces
        except ImportError:
            return None

        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get('addr', '')
                    if ip.startswith('169.254.'):
                        return f"{iface} ({ip})"

        return None

    def probe_grpc(self) -> Optional[bytes]:
        """
        Attempt gRPC handshake with camera server.

        Returns response bytes if successful.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((self.host, PORT_GRPC))

            # HTTP/2 preface
            preface = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
            sock.sendall(preface)

            # Try to receive settings frame
            response = sock.recv(4096)
            sock.close()

            return response

        except Exception:
            return None

    def probe_control_channel(self) -> Optional[bytes]:
        """
        Attempt control channel handshake.

        Returns response bytes if successful.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((self.host, PORT_CONTROL))

            # Send CONNECTED message (type=1)
            # Format: [length:2][type:2]
            message = struct.pack('<HH', 4, 1)  # Length=4, Type=CONNECTED
            sock.sendall(message)

            # Wait for response
            response = sock.recv(1024)
            sock.close()

            return response

        except Exception:
            return None


def format_discovery_result(result: DiscoveryResult) -> str:
    """Format discovery results for display"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"XREAL Service Discovery Results")
    lines.append("=" * 60)
    lines.append(f"Host: {result.host}")
    lines.append(f"Reachable: {'Yes' if result.reachable else 'No'}")

    if result.ncm_interface:
        lines.append(f"NCM Interface: {result.ncm_interface}")

    lines.append(f"Scan Time: {result.scan_time:.2f}s")
    lines.append("")
    lines.append("Services:")
    lines.append("-" * 60)

    for port, info in sorted(result.services.items()):
        status_icon = {
            ServiceStatus.OPEN: "[OPEN]",
            ServiceStatus.CLOSED: "[CLOSED]",
            ServiceStatus.FILTERED: "[FILTERED]",
            ServiceStatus.UNKNOWN: "[?]",
            ServiceStatus.ERROR: "[ERROR]",
        }.get(info.status, "[?]")

        line = f"  {info.protocol.upper():3} {port:5}  {status_icon:10}  {info.description}"

        if info.latency_ms > 0:
            line += f"  ({info.latency_ms:.1f}ms)"

        if info.response:
            # Show first few bytes of response
            preview = info.response[:20].hex()
            line += f"  [{preview}...]"

        lines.append(line)

    lines.append("")
    return "\n".join(lines)


def main():
    """Run discovery from command line"""
    import sys

    host = sys.argv[1] if len(sys.argv) > 1 else GLASSES_IP_PRIMARY

    print(f"Discovering XREAL services on {host}...")
    print()

    discovery = ServiceDiscovery(host=host, timeout=2.0)

    def on_progress(msg):
        print(f"  {msg}")

    result = discovery.discover_all(on_progress=on_progress)

    print()
    print(format_discovery_result(result))

    # Try protocol handshakes for open services
    if result.services.get(PORT_GRPC, ServiceInfo(0, '', ServiceStatus.CLOSED)).status == ServiceStatus.OPEN:
        print("Attempting gRPC handshake...")
        response = discovery.probe_grpc()
        if response:
            print(f"  gRPC response: {response[:50].hex()}...")
        else:
            print("  No gRPC response")

    if result.services.get(PORT_CONTROL, ServiceInfo(0, '', ServiceStatus.CLOSED)).status == ServiceStatus.OPEN:
        print("Attempting control channel handshake...")
        response = discovery.probe_control_channel()
        if response:
            print(f"  Control response: {response.hex()}")
        else:
            print("  No control response")


if __name__ == "__main__":
    main()
