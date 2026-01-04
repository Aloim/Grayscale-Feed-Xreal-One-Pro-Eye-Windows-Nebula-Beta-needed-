"""
XREAL Eye Camera gRPC Client

Connects to the glasses gRPC server and streams camera frames.
"""

import grpc
import time
import uuid
from typing import Iterator, Optional
import threading

import frames_service_pb2 as pb
import frames_service_pb2_grpc as pb_grpc


def create_open_stream_request(
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    format: str = "YUV420"
) -> pb.StreamRequest:
    """Create an OpenStreamRequest to start camera streaming"""
    return pb.StreamRequest(
        session_id=str(uuid.uuid4()),
        timestamp=int(time.time() * 1000),
        open_stream=pb.OpenStreamRequest(
            camera_config=pb.CameraConfig(
                width=width,
                height=height,
                format=format,
                fps=fps
            ),
            sensor_config=pb.SensorConfig(
                sample_rate=100,
                enabled_sensors=[pb.IMU, pb.ACCELEROMETER, pb.GYROSCOPE]
            )
        )
    )


def request_generator(
    initial_request: pb.StreamRequest
) -> Iterator[pb.StreamRequest]:
    """Generator that yields stream requests"""
    # Send initial open request
    yield initial_request

    # Keep connection alive with periodic heartbeats
    session_id = initial_request.session_id
    while True:
        time.sleep(5)
        yield pb.StreamRequest(
            session_id=session_id,
            timestamp=int(time.time() * 1000)
        )


def test_streaming():
    """Test the gRPC streaming connection"""
    host = "169.254.2.1"
    port = 50051

    print(f"Connecting to gRPC server at {host}:{port}...")

    channel = grpc.insecure_channel(f'{host}:{port}')

    # Wait for channel to be ready
    try:
        grpc.channel_ready_future(channel).result(timeout=5)
        print("Channel ready!")
    except grpc.FutureTimeoutError:
        print("Channel timeout")
        return

    # Create stub
    stub = pb_grpc.FramesStub(channel)

    # Create initial request
    open_request = create_open_stream_request()
    print(f"Session ID: {open_request.session_id}")
    print(f"Requesting: {open_request.open_stream.camera_config}")

    # Start streaming
    print()
    print("Starting bidirectional stream...")

    try:
        # For bidirectional streaming, we need to run the request generator in a thread
        responses = stub.StartStreaming(iter([open_request]), timeout=10)

        print("Stream opened! Waiting for responses...")

        frame_count = 0
        start_time = time.time()

        for response in responses:
            elapsed = time.time() - start_time

            if response.HasField('camera_frame'):
                frame = response.camera_frame
                frame_count += 1
                data_size = len(frame.frame_data) if frame.frame_data else 0
                print(f"[{elapsed:.2f}s] Frame {frame_count}: {frame.width}x{frame.height} {frame.format}, {data_size} bytes")

                # Save first frame for analysis
                if frame_count == 1 and data_size > 0:
                    with open("first_frame.raw", "wb") as f:
                        f.write(frame.frame_data)
                    print(f"  -> Saved to first_frame.raw")

            elif response.HasField('sensor_data'):
                sensor = response.sensor_data
                print(f"[{elapsed:.2f}s] Sensor: type={sensor.sensor_type} values={list(sensor.values)}")

            elif response.HasField('status'):
                status = response.status
                print(f"[{elapsed:.2f}s] Status: {status.status} - {status.message}")
            else:
                print(f"[{elapsed:.2f}s] Unknown response: {response}")

            if frame_count >= 10 or elapsed > 10:
                print(f"\nReceived {frame_count} frames in {elapsed:.2f}s")
                break

    except grpc.RpcError as e:
        print(f"gRPC Error: {e.code().name}: {e.details()}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
    finally:
        channel.close()


if __name__ == "__main__":
    test_streaming()
