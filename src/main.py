"""
XREAL Eye Windows Test Application

Main entry point with Tkinter GUI for viewing IMU data
and discovering camera services.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import sys
import subprocess
import os
from typing import Optional

from config import (
    GLASSES_IP_PRIMARY,
    GLASSES_IP_SECONDARY,
    PORT_IMU,
    PORT_GRPC,
    PORT_CONTROL,
    PORT_DISCOVERY,
    PORT_VIDEO_RTP,
)
from imu_reader import ImuReader, ImuData, ConnectionState


class XrealTestApp:
    """Main application window"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("XREAL Eye Test Application")
        self.root.geometry("900x700")
        self.root.configure(bg='#1e1e1e')

        # State
        self.imu_reader: Optional[ImuReader] = None
        self._update_rate = 30  # UI updates per second
        self._last_imu: Optional[ImuData] = None  # Keep last valid reading
        self._camera_active = False
        self._camera_thread = None

        # Setup UI
        self._setup_styles()
        self._setup_ui()

        # Start UI update loop
        self._schedule_update()

    def _setup_styles(self):
        """Configure ttk styles for dark theme"""
        style = ttk.Style()
        style.theme_use('clam')

        # Dark theme colors
        bg_dark = '#1e1e1e'
        bg_medium = '#2d2d2d'
        bg_light = '#3d3d3d'
        fg_normal = '#ffffff'
        fg_dim = '#888888'
        accent = '#007acc'
        success = '#4ec9b0'
        error = '#f14c4c'

        style.configure('TFrame', background=bg_dark)
        style.configure('TLabel', background=bg_dark, foreground=fg_normal, font=('Segoe UI', 10))
        style.configure('TLabelframe', background=bg_dark, foreground=fg_normal)
        style.configure('TLabelframe.Label', background=bg_dark, foreground=fg_normal, font=('Segoe UI', 11, 'bold'))
        style.configure('TButton', font=('Segoe UI', 10))

        style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'), foreground=accent)
        style.configure('Value.TLabel', font=('Consolas', 12), foreground=success)
        style.configure('Status.TLabel', font=('Segoe UI', 10))
        style.configure('Connected.TLabel', foreground=success)
        style.configure('Disconnected.TLabel', foreground=error)
        style.configure('Dim.TLabel', foreground=fg_dim)

    def _setup_ui(self):
        """Create all UI components"""
        # Main container
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left panel - IMU data
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self._setup_imu_panel(left_frame)
        self._setup_stats_panel(left_frame)

        # Right panel - Status and controls
        right_frame = ttk.Frame(main_frame, width=350)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        right_frame.pack_propagate(False)

        self._setup_connection_panel(right_frame)
        self._setup_discovery_panel(right_frame)
        self._setup_controls(right_frame)
        self._setup_log_panel(right_frame)

    def _setup_imu_panel(self, parent):
        """IMU data display panel"""
        frame = ttk.LabelFrame(parent, text="IMU Sensor Data", padding=15)
        frame.pack(fill=tk.X, pady=(0, 10))

        # Gyroscope section
        gyro_frame = ttk.Frame(frame)
        gyro_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(gyro_frame, text="Gyroscope (rad/s)", style='Header.TLabel').pack(anchor=tk.W)

        self.gyro_labels = {}
        for axis in ['X', 'Y', 'Z']:
            row = ttk.Frame(gyro_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"  {axis}:", width=6).pack(side=tk.LEFT)
            label = ttk.Label(row, text="0.0000", style='Value.TLabel', width=12)
            label.pack(side=tk.LEFT)
            self.gyro_labels[axis] = label

        # Accelerometer section
        accel_frame = ttk.Frame(frame)
        accel_frame.pack(fill=tk.X)

        ttk.Label(accel_frame, text="Accelerometer (m/s^2)", style='Header.TLabel').pack(anchor=tk.W)

        self.accel_labels = {}
        for axis in ['X', 'Y', 'Z']:
            row = ttk.Frame(accel_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"  {axis}:", width=6).pack(side=tk.LEFT)
            label = ttk.Label(row, text="0.0000", style='Value.TLabel', width=12)
            label.pack(side=tk.LEFT)
            self.accel_labels[axis] = label

    def _setup_stats_panel(self, parent):
        """Statistics panel"""
        frame = ttk.LabelFrame(parent, text="Statistics", padding=10)
        frame.pack(fill=tk.X, pady=(0, 10))

        self.stats_labels = {}
        for name in ['Packets', 'Rate', 'Uptime']:
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{name}:", width=10).pack(side=tk.LEFT)
            label = ttk.Label(row, text="-", style='Dim.TLabel')
            label.pack(side=tk.LEFT)
            self.stats_labels[name] = label

    def _setup_connection_panel(self, parent):
        """Connection status panel"""
        frame = ttk.LabelFrame(parent, text="Connection Status", padding=10)
        frame.pack(fill=tk.X, pady=(0, 10))

        # IMU connection
        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="IMU Stream:", width=15).pack(side=tk.LEFT)
        self.imu_status_label = ttk.Label(row, text="Disconnected", style='Disconnected.TLabel')
        self.imu_status_label.pack(side=tk.LEFT)

        # Target IP
        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Target IP:", width=15).pack(side=tk.LEFT)
        self.ip_var = tk.StringVar(value=GLASSES_IP_PRIMARY)
        ip_entry = ttk.Entry(row, textvariable=self.ip_var, width=15)
        ip_entry.pack(side=tk.LEFT)

    def _setup_discovery_panel(self, parent):
        """Service discovery panel"""
        frame = ttk.LabelFrame(parent, text="Service Discovery", padding=10)
        frame.pack(fill=tk.X, pady=(0, 10))

        self.service_labels = {}
        services = [
            ('IMU (52998)', PORT_IMU, 'tcp'),
            ('gRPC (50051)', PORT_GRPC, 'tcp'),
            ('Control (8848)', PORT_CONTROL, 'tcp'),
            ('Discovery (6001)', PORT_DISCOVERY, 'udp'),
            ('Video RTP (5555)', PORT_VIDEO_RTP, 'udp'),
        ]

        for name, port, proto in services:
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=f"{name}:", width=18).pack(side=tk.LEFT)
            label = ttk.Label(row, text="Unknown", style='Dim.TLabel')
            label.pack(side=tk.LEFT)
            self.service_labels[port] = label

    def _setup_controls(self, parent):
        """Control buttons"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=10)

        ttk.Button(frame, text="Connect IMU", command=self._connect_imu).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text="Disconnect", command=self._disconnect).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text="Launch Camera", command=self._launch_camera).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text="Scan Services", command=self._scan_services).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text="Clear Log", command=self._clear_log).pack(fill=tk.X, pady=2)

    def _setup_log_panel(self, parent):
        """Log output panel"""
        frame = ttk.LabelFrame(parent, text="Log", padding=5)
        frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(frame, height=12, bg='#1e1e1e', fg='#cccccc',
                                font=('Consolas', 9), wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(self.log_text, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _log(self, message: str):
        """Add message to log"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def _clear_log(self):
        """Clear log output"""
        self.log_text.delete(1.0, tk.END)

    def _connect_imu(self):
        """Start IMU connection"""
        if self.imu_reader and self.imu_reader.is_connected:
            self._log("Already connected")
            return

        host = self.ip_var.get().strip()
        self._log(f"Connecting to {host}:{PORT_IMU}...")

        self.imu_reader = ImuReader(
            host=host,
            port=PORT_IMU,
            on_state_change=self._on_imu_state_change,
            auto_reconnect=True
        )
        self.imu_reader.start()

    def _disconnect(self):
        """Stop IMU connection"""
        if self.imu_reader:
            self.imu_reader.stop()
            self.imu_reader = None
            self._log("Disconnected")

    def _launch_camera(self):
        """Launch the camera viewer in a separate window"""
        if self._camera_active:
            self._log("Camera viewer already running")
            return

        # Get path to live_video_viewer.py
        script_dir = os.path.dirname(os.path.abspath(__file__))
        viewer_path = os.path.join(script_dir, "live_video_viewer.py")

        if not os.path.exists(viewer_path):
            self._log(f"Error: Camera viewer not found at {viewer_path}")
            return

        self._log("Launching camera viewer...")
        try:
            # Launch as subprocess (non-blocking)
            self._camera_thread = subprocess.Popen(
                [sys.executable, viewer_path],
                cwd=script_dir
            )
            self._camera_active = True
            self._log("Camera viewer launched (press Q in camera window to close)")
        except Exception as e:
            self._log(f"Failed to launch camera: {e}")

    def _on_imu_state_change(self, state: ConnectionState):
        """Handle IMU connection state change"""
        # Update UI in main thread
        self.root.after(0, lambda: self._update_imu_status(state))

    def _update_imu_status(self, state: ConnectionState):
        """Update IMU status label"""
        if state == ConnectionState.CONNECTED:
            self.imu_status_label.configure(text="Connected", style='Connected.TLabel')
            self._log("IMU connected!")
        elif state == ConnectionState.CONNECTING:
            self.imu_status_label.configure(text="Connecting...", style='Dim.TLabel')
        elif state == ConnectionState.ERROR:
            self.imu_status_label.configure(text="Error", style='Disconnected.TLabel')
            self._log("Connection error - check if glasses are connected")
        else:
            self.imu_status_label.configure(text="Disconnected", style='Disconnected.TLabel')

    def _scan_services(self):
        """Scan for available services"""
        import socket

        host = self.ip_var.get().strip()
        self._log(f"Scanning services on {host}...")

        def scan():
            results = {}

            # TCP ports
            for port in [PORT_IMU, PORT_GRPC, PORT_CONTROL]:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1.0)
                    result = sock.connect_ex((host, port))
                    sock.close()
                    results[port] = "Open" if result == 0 else "Closed"
                except Exception as e:
                    results[port] = f"Error: {e}"

            # UDP ports (less reliable detection)
            for port in [PORT_DISCOVERY, PORT_VIDEO_RTP]:
                results[port] = "UDP (unknown)"

            # Update UI
            self.root.after(0, lambda: self._update_service_results(results))

        threading.Thread(target=scan, daemon=True).start()

    def _update_service_results(self, results: dict):
        """Update service discovery results"""
        for port, status in results.items():
            if port in self.service_labels:
                label = self.service_labels[port]
                if "Open" in status:
                    label.configure(text=status, style='Connected.TLabel')
                    self._log(f"Port {port}: {status}")
                else:
                    label.configure(text=status, style='Dim.TLabel')

        self._log("Service scan complete")

    def _schedule_update(self):
        """Schedule periodic UI update"""
        self._update_ui()
        self.root.after(int(1000 / self._update_rate), self._schedule_update)

    def _update_ui(self):
        """Update UI with latest data"""
        if self.imu_reader:
            imu = self.imu_reader.get_latest()

            # Store last valid reading
            if imu:
                self._last_imu = imu

            # Display last valid reading (keeps values on screen)
            if self._last_imu:
                # Update gyro labels
                self.gyro_labels['X'].configure(text=f"{self._last_imu.gyro_x:+.4f}")
                self.gyro_labels['Y'].configure(text=f"{self._last_imu.gyro_y:+.4f}")
                self.gyro_labels['Z'].configure(text=f"{self._last_imu.gyro_z:+.4f}")

                # Update accel labels
                self.accel_labels['X'].configure(text=f"{self._last_imu.accel_x:+.4f}")
                self.accel_labels['Y'].configure(text=f"{self._last_imu.accel_y:+.4f}")
                self.accel_labels['Z'].configure(text=f"{self._last_imu.accel_z:+.4f}")

            # Update statistics
            packets = self.imu_reader.packets_received
            self.stats_labels['Packets'].configure(text=f"{packets:,}")

            if self.imu_reader.last_packet_time > 0:
                elapsed = time.time() - self.imu_reader.last_packet_time
                if elapsed < 1.0 and packets > 0:
                    # Calculate recent rate
                    rate = packets / (time.time() - self.imu_reader.last_packet_time + packets * 0.01)
                    self.stats_labels['Rate'].configure(text=f"{min(rate, 1000):.0f} Hz")
                else:
                    self.stats_labels['Rate'].configure(text="0 Hz")

    def run(self):
        """Start the application"""
        self._log("XREAL Eye Test Application started")
        self._log(f"Default target: {GLASSES_IP_PRIMARY}")
        self._log("Click 'Connect IMU' to start streaming")

        try:
            self.root.mainloop()
        finally:
            if self.imu_reader:
                self.imu_reader.stop()
            # Terminate camera viewer if running
            if self._camera_thread and self._camera_thread.poll() is None:
                self._camera_thread.terminate()


def main():
    """Entry point"""
    print("Starting XREAL Eye Test Application...")
    app = XrealTestApp()
    app.run()


if __name__ == "__main__":
    main()
