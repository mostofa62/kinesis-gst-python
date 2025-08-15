import os
import gi
import time
import threading
import socket
from urllib.parse import urlparse
import cv2  # Make sure you have opencv-python installed
import datetime
gi.require_version('Gst', '1.0')
from gi.repository import Gst

def log(msg):
    print(f"[{datetime.datetime.now().isoformat()}] {msg}")

def prRed(s): print("\033[91m {}\033[00m".format(s))
def prGreen(s): print("\033[92m {}\033[00m".format(s))
def prYellow(s): print("\033[93m {}\033[00m".format(s))
def prLightPurple(s): print("\033[94m {}\033[00m".format(s))
def prPurple(s): print("\033[95m {}\033[00m".format(s))
def prCyan(s): print("\033[96m {}\033[00m".format(s))
def prLightGray(s): print("\033[97m {}\033[00m".format(s))
def prBlack(s): print("\033[90m {}\033[00m".format(s))  # Corrected from 98 to 90 (standard ANSI)

# Read environment variables (passed from Docker)
RTSP_URI = os.getenv("RTSP_URI")
STREAM_NAME = os.getenv("STREAM_NAME")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
LOG_CONFIG_PATH = "/opt/kvs_log_configuration"

## util functions
def is_stream_accessible(url, timeout=5):
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or 554  # Default RTSP port

        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as e:
        log(f"⚠️ Unable to reach host {host}:{port} - {e}")
        return False

def is_stream_working(url, timeout=10):
    if not is_stream_accessible(url):
        return False
    cap = None
    try:
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            log(f"⚠️ Unable to open stream: {url}")
            return False

        start_time = time.time()
        while time.time() - start_time < timeout:
            ret, frame = cap.read()
            if ret:
                cap.release()
                return True
            time.sleep(1)

        cap.release()
        return False
    except Exception as e:
        log(f"❌ Exception while checking stream {url}: {e}")
        return False
    finally:
        if cap is not None:
            cap.release()
    
## end util functions

pipeline_thread = None
pipeline_thread_lock = threading.Lock()

pipeline_heartbeat = 0
heartbeat_lock = threading.Lock()

# Add a stop event for the pipeline thread
pipeline_stop_event = threading.Event()

def run_pipeline():
    Gst.init(None)

    # pipeline_str = (
    #     f"rtspsrc location={RTSP_URI} protocols=tcp latency=500 short-header=true name=src ! "
    #     "queue ! rtph265depay ! h265parse config-interval=1 ! "
    #     f'kvssink stream-name={STREAM_NAME} storage-size=128 '
    #     f'access-key={AWS_ACCESS_KEY_ID} '
    #     f'secret-key={AWS_SECRET_ACCESS_KEY} '
    #     f'aws-region={AWS_REGION} '
    #     f'log-config="{LOG_CONFIG_PATH}"'
    # )

    pipeline_str = (
        f"rtspsrc location={RTSP_URI} protocols=tcp latency=200 short-header=true ! "
        "queue max-size-buffers=2 ! rtph265depay ! h265parse ! avdec_h265 ! videoconvert ! "
        "videoscale ! video/x-raw,width=720,height=450 ! videorate ! video/x-raw,framerate=15/1 ! "
        "x264enc tune=zerolatency bitrate=1024 speed-preset=ultrafast byte-stream=true key-int-max=30 ! "
        "video/x-h264,profile=baseline ! "
        f'kvssink stream-name={STREAM_NAME} storage-size=128 '
        f'access-key={AWS_ACCESS_KEY_ID} '
        f'secret-key={AWS_SECRET_ACCESS_KEY} '
        f'aws-region={AWS_REGION} '
        f'log-config="{LOG_CONFIG_PATH}"'
    )



    prYellow("Pipeline: " + pipeline_str)

    pipeline = Gst.parse_launch(pipeline_str)
    log("🔄Setting pipeline to PLAYING...")

    # Start pipeline (non-blocking)
    ret = pipeline.set_state(Gst.State.PLAYING)

    if ret == Gst.StateChangeReturn.FAILURE:
        log("❌ Failed to start pipeline.")
        pipeline.set_state(Gst.State.NULL)
        return

    if ret == Gst.StateChangeReturn.ASYNC:
        # Wait up to 5 seconds for state change
        log("⏳ Pipeline starting asynchronously...")
        state_change = pipeline.get_state(5 * Gst.SECOND)
        log(f"🔁 State change after async start: {state_change}")

    elif ret == Gst.StateChangeReturn.SUCCESS:
        log("✅ Pipeline started immediately.")

    log("▶️ Pipeline set to PLAYING, waiting for messages...")

    bus = pipeline.get_bus()
    global pipeline_heartbeat

    while not pipeline_stop_event.is_set():
        # Update heartbeat
        with heartbeat_lock:
            pipeline_heartbeat = time.time()

        msg = bus.timed_pop_filtered(
        Gst.CLOCK_TIME_NONE,
        Gst.MessageType.ERROR | Gst.MessageType.EOS | Gst.MessageType.STATE_CHANGED | Gst.MessageType.ELEMENT
    )

        if msg:
            t = msg.type

            # Only show state changes once per change
            if t == Gst.MessageType.STATE_CHANGED:
                old_state, new_state, pending_state = msg.parse_state_changed()
                if msg.src == pipeline:
                    print(f"🔁[STATE] Pipeline changed from {old_state.value_nick} to {new_state.value_nick}", flush=True)

            # Show errors clearly
            elif t == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                print(f"❌[ERROR] {err} — {debug}", flush=True)

            # Show upload events from kvssink
            elif t == Gst.MessageType.ELEMENT:
                s = msg.get_structure()
                if s and s.has_name("kvssink-upload"):
                    upload_handle = s.get_value("upload_handle")
                    start_ts = s.get_value("start_timecode")
                    print(f"⏫[UPLOAD] Chunk uploaded: handle={upload_handle}, start_ts={start_ts}", flush=True)
                    sys.stdout.flush()

            elif t == Gst.MessageType.EOS:
                print("❎[EOS] End of stream reached", flush=True)
                break


    log("❎ Stop event set or pipeline ended, stopping pipeline...")
    pipeline.set_state(Gst.State.NULL)
    log("❎ Pipeline stopped.")

def start_pipeline_thread():
    global pipeline_thread, pipeline_stop_event
    with pipeline_thread_lock:
        if pipeline_thread and pipeline_thread.is_alive():
            log("🏃‍➡️ Pipeline thread already running")
            return
        # Clear any previous stop event before starting
        pipeline_stop_event.clear()
        pipeline_thread = threading.Thread(target=run_pipeline, daemon=True)
        pipeline_thread.start()
        log("🔛 Pipeline thread started")

def stop_pipeline_thread():
    global pipeline_thread, pipeline_stop_event
    with pipeline_thread_lock:
        if pipeline_thread and pipeline_thread.is_alive():
            log("❎ Stopping pipeline thread...")
            pipeline_stop_event.set()  # Signal the thread to stop
            pipeline_thread.join(timeout=10)  # Wait for graceful stop
            if pipeline_thread.is_alive():
                log("⚠️ Pipeline thread did not stop in time")
            else:
                log("❎ Pipeline thread stopped")
        else:
            log("🙂‍↔️ Pipeline thread not running")




def monitor_pipeline():
    global pipeline_heartbeat
    while True:
        with pipeline_thread_lock:
            running = pipeline_thread and pipeline_thread.is_alive()

        now = time.time()

        stream_ok = is_stream_working(RTSP_URI)

        if running:
            with heartbeat_lock:
                last_beat = pipeline_heartbeat

            if now - last_beat > 30:  # no heartbeat for 30 seconds = stuck
                log("⚠️ Pipeline thread heartbeat timed out, restarting pipeline...")
                stop_pipeline_thread()
                if stream_ok:
                    start_pipeline_thread()
            else:
                log("👍 Pipeline running and healthy (heartbeat OK)")

        else:
            log("⚠️ Pipeline not running — checking RTSP stream...")
            if stream_ok:
                log("👍 Stream is live — starting pipeline")
                start_pipeline_thread()
            else:
                log("⚠️ Stream not available — pipeline is not running")
        # Additionally, if pipeline running but stream lost, stop pipeline:
        if running and not stream_ok:
            log("⚠️ Stream lost while pipeline running — stopping pipeline")
            stop_pipeline_thread()

        #time.sleep(15)
        time.sleep(5)

if __name__ == "__main__":
    monitor_thread = threading.Thread(target=monitor_pipeline, daemon=True)
    monitor_thread.start()

    # Keep main thread alive
    while True:
        time.sleep(1)
