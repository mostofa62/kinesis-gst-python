import os
import gi
import time

# Read environment variables (passed from Docker)
RTSP_URI = os.getenv("RTSP_URI")
STREAM_NAME = os.getenv("STREAM_NAME")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")

# Optional: print them for debug (don’t do this for real creds in prod)
print(f"RTSP_URI={RTSP_URI}")
print(f"STREAM_NAME={STREAM_NAME}")
print(f"AWS_REGION={AWS_REGION}")

gi.require_version('Gst', '1.0')
from gi.repository import Gst

# Initialize GStreamer
Gst.init(None)

# Build pipeline string using the env vars
'''
pipeline_str = (
    f"rtspsrc location={RTSP_URI} protocols=tcp latency=100 short-header=true name=src ! "
    "decodebin ! videoconvert ! "
    "x264enc tune=zerolatency ! h264parse ! "
    f"kvssink stream-name={STREAM_NAME} storage-size=128 "
    f"access-key={AWS_ACCESS_KEY_ID} "
    f"secret-key={AWS_SECRET_ACCESS_KEY} "
    f"aws-region={AWS_REGION}"
)
'''
pipeline_str = (
    f"rtspsrc location={RTSP_URI} protocols=tcp latency=100 short-header=true name=src ! "
    "queue ! rtph265depay ! h265parse ! "
    f"kvssink stream-name={STREAM_NAME} storage-size=128 "
    f"access-key={AWS_ACCESS_KEY_ID} "
    f"secret-key={AWS_SECRET_ACCESS_KEY} "
    f"aws-region={AWS_REGION}"
)


print("Pipeline:", pipeline_str)

# Create and run the pipeline
pipeline = Gst.parse_launch(pipeline_str)
print("Setting pipeline to PLAYING...")
pipeline.set_state(Gst.State.PLAYING)
print("Pipeline set to PLAYING, waiting for messages...")

# Wait until EOS or error, or timeout after 30 seconds
bus = pipeline.get_bus()
start_time = time.time()
timeout = 30  # seconds

while True:
    msg = bus.timed_pop_filtered(
        Gst.SECOND,
        Gst.MessageType.ERROR | Gst.MessageType.EOS
    )
    if msg:
        if msg.type == Gst.MessageType.ERROR:
            err, debug = msg.parse_error()
            print(f"Pipeline error: {err.message}")
            print(f"Debug info: {debug}")
        elif msg.type == Gst.MessageType.EOS:
            print("Pipeline reached EOS")
        break
    if time.time() - start_time > timeout:
        print(f"No EOS or ERROR after {timeout} seconds, exiting loop")
        break

pipeline.set_state(Gst.State.NULL)
print("Done.")
