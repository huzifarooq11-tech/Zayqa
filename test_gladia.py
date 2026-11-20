
import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv
from gladiaio_sdk import GladiaClient, LiveV2InitRequest


# Load API key from .env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

API_KEY = os.getenv("GLADIA_API_KEY")
API_URL = os.getenv("GLADIA_API_URL", "https://api.gladia.io")

if not API_KEY:
    print("ERROR: GLADIA_API_KEY not found in .env")
    sys.exit(1)


# Configure live transcription
config = {
    "model": "solaria-1",
    "encoding": "wav/pcm",
    "sample_rate": 16000,
    "bit_depth": 16,
    "channels": 1,
    "language_config": {
        "languages": ["ur", "en"]
    }
}

connected = threading.Event()
ended = threading.Event()
errors = []


try:
    print("Connecting to Gladia...")

    client = GladiaClient(
        api_key=API_KEY,
        api_url=API_URL
    )

    session = client.live_v2().start_session(
        LiveV2InitRequest.from_dict(config)
    )

    # Receive transcription messages
    @session.on("message")
    def on_message(message):
        if message.type == "transcript":
            print(
                "TRANSCRIPT:",
                message.data.utterance.text
            )

    # Connection events
    @session.once("connected")
    def on_connected(_):
        connected.set()

    @session.on("error")
    def on_error(error):
        errors.append(error)
        connected.set()
        print("Gladia error:", error)

    @session.once("ended")
    def on_ended(_):
        ended.set()
        connected.set()

    # Handle a connection that opens immediately
    if session.status == "connected":
        connected.set()

    # Wait for connection
    if not connected.wait(timeout=30):
        print("ERROR: Connection timed out.")
        session.stop_recording()
        sys.exit(1)

    if errors or ended.is_set():
        print("ERROR: Gladia session could not connect.")
        sys.exit(1)

    print("SUCCESS: Gladia live session connected!")
    print("Requested model: solaria-1")
    print("Audio format: 16 kHz, 16-bit, mono")
    print("Languages requested: Urdu and English")

    print("\nClosing test session...")

    session.stop_recording()

    if ended.wait(timeout=30):
        print("SUCCESS: Gladia session closed.")
    else:
        print("WARNING: Session closure was not confirmed.")

except Exception as error:
    print("\nCONNECTION FAILED:")
    print(type(error).__name__, error)
    sys.exit(1)
