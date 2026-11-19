import asyncio
import hashlib
import os
from io import BytesIO

import pytest
from PIL import Image

os.environ["YOLO_ENABLED"] = "false"
os.environ["FAMILY_DB"] = ":memory:"

import main  # noqa: E402
import scene  # noqa: E402
from assistant import Assistant  # noqa: E402
from family import Family  # noqa: E402
from navigation import Navigator  # noqa: E402
from payments import Orders  # noqa: E402

CLOUD_KEYS = [
    "GEMINI_API_KEY", "MINIMAX_API_KEY", "GROQ_API_KEY", "VISION_PROVIDERS", "STRIPE_SECRET_KEY",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY", "SPEECH_VOICE",
]


def run(coroutine):
    return asyncio.run(coroutine)


def detection(label, x1, x2, confidence=0.9, y1=0.2, y2=0.8):
    return scene.make_detection(label, confidence, [x1, y1, x2, y2])


def png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color=(40, 60, 80)).save(buffer, format="PNG")
    return buffer.getvalue()


def device_headers(device: str, session: str = "session") -> dict[str, str]:
    secret = hashlib.sha256(f"secret:{device}".encode()).hexdigest()
    device_id = f"device-{hashlib.sha256(secret.encode()).hexdigest()[:32]}"
    return {"X-Device-ID": device_id, "X-Session-ID": session, "X-Device-Secret": secret}


class FakeDetector:
    def __init__(self, detections=()):
        self.detections = list(detections)

    def detect(self, image):
        return self.detections


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("YOLO_ENABLED", "false")
    monkeypatch.setattr(scene.detector, "_model", None)
    monkeypatch.setattr(scene.detector, "_error", None)
    orders, navigator = Orders(), Navigator()
    monkeypatch.setattr(main, "_orders", orders)
    monkeypatch.setattr(main, "_navigator", navigator)
    monkeypatch.setattr(main, "_assistant", Assistant(Family(":memory:"), orders, navigator=navigator))
    main._clear_rate_limits_for_tests()
    yield
    main._clear_rate_limits_for_tests()
