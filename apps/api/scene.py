import os
import threading
from io import BytesIO
from pathlib import Path

import llm

HAZARD_LABELS = {
    "person", "bicycle", "car", "motorcycle", "bus", "truck", "train",
    "bench", "chair", "couch", "bed", "dining table", "potted plant",
    "fire hydrant", "stop sign", "parking meter", "suitcase", "backpack",
    "dog", "cat", "skateboard", "toilet", "tv", "refrigerator",
}
MIN_HAZARD_AREA = 0.03
MAX_WARNINGS = 3

SYSTEM_PROMPT = (
    "You are GuideAI, speaking to a blind or low-vision person. "
    "Answer in one or two short sentences that sound natural when spoken aloud. "
    "Describe only what is actually visible in the image. "
    "Say where things are with words like ahead, left and right. "
    "Never give distances in metres or feet and never say a path is safe or clear to walk. "
    "Do not identify people or infer sensitive traits. "
    "If asked to read text, read it exactly. If you are not sure, say so plainly."
)
DEFAULT_QUESTION = "Briefly, what is in front of me?"


class SceneError(Exception):
    pass


def zone(center_x: float) -> str:
    if center_x < 0.2:
        return "on the left"
    if center_x < 0.4:
        return "ahead, left"
    if center_x <= 0.6:
        return "ahead"
    if center_x <= 0.8:
        return "ahead, right"
    return "on the right"


def make_detection(label: str, confidence: float, box: list[float]) -> dict:
    x1, y1, x2, y2 = (min(1.0, max(0.0, float(value))) for value in box)
    return {
        "label": label,
        "confidence": round(float(confidence), 3),
        "box": [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)],
        "position": zone((x1 + x2) / 2),
        "area": round(max(0.0, x2 - x1) * max(0.0, y2 - y1), 4),
    }


def hazard_warnings(detections: list[dict]) -> list[str]:
    hazards = [item for item in detections if item["label"] in HAZARD_LABELS and item["area"] >= MIN_HAZARD_AREA]
    hazards.sort(key=lambda item: item["area"], reverse=True)
    warnings: list[str] = []
    for item in hazards:
        text = f"{item['label'].capitalize()} {item['position']}."
        if text not in warnings:
            warnings.append(text)
        if len(warnings) == MAX_WARNINGS:
            break
    return warnings


def plural(label: str) -> str:
    if label == "person":
        return "people"
    return f"{label}es" if label.endswith(("s", "x", "ch", "sh")) else f"{label}s"


def local_description(detections: list[dict]) -> str:
    if not detections:
        return "I do not recognise anything in view right now."
    counts: dict[tuple[str, str], int] = {}
    for item in sorted(detections, key=lambda entry: entry["area"], reverse=True):
        key = (item["label"], item["position"])
        counts[key] = counts.get(key, 0) + 1
    parts = [
        f"{count} {plural(label)} {position}" if count > 1 else f"a {label} {position}"
        for (label, position), count in list(counts.items())[:4]
    ]
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"I can see {listed}. This is from the on-device detector only."


def scene_key(detections: list[dict]) -> str:
    seen = sorted({f"{item['label']}@{item['position']}" for item in detections})
    return ("|".join(seen) or "empty").replace(", ", "-").replace(" ", "-")[:80]


class Detector:
    def __init__(self) -> None:
        self._model = None
        self._error: str | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _weights() -> str:
        configured = os.getenv("YOLO_MODEL")
        if configured:
            return configured
        bundled = Path(__file__).with_name("models") / "yolo11n.pt"
        return str(bundled) if bundled.is_file() else "yolo11n.pt"

    @staticmethod
    def enabled() -> bool:
        return os.getenv("YOLO_ENABLED", "true").lower() not in {"0", "false", "no"}

    def _load(self):
        if self._model is None and self._error is None:
            if not self.enabled():
                self._error = "disabled by YOLO_ENABLED"
                return None
            try:
                from ultralytics import YOLO

                self._model = YOLO(self._weights())
            except Exception as error:
                self._error = f"{type(error).__name__}: {error}"
        return self._model

    def warm_up(self) -> None:
        with self._lock:
            self._load()

    def status(self) -> dict:
        state = "ready" if self._model is not None else ("unavailable" if self._error else "not_loaded")
        return {"state": state, "model": Path(self._weights()).name, "error": self._error}

    def detect(self, image: bytes) -> list[dict]:
        try:
            from PIL import Image

            frame = Image.open(BytesIO(image)).convert("RGB")
        except Exception as error:
            raise SceneError("The image could not be read") from error
        with self._lock:
            model = self._load()
            if model is None:
                return []
            device = os.getenv("YOLO_DEVICE", "").strip()
            results = model.predict(
                frame,
                conf=float(os.getenv("YOLO_MIN_CONFIDENCE", "0.35")),
                device=None if device in {"", "auto"} else device,
                verbose=False,
            )
        detections = []
        for result in results:
            for box in result.boxes:
                detections.append(make_detection(
                    result.names[int(box.cls[0])], float(box.conf[0]), box.xyxyn[0].tolist(),
                ))
        return detections


detector = Detector()


def _user_prompt(question: str, detections: list[dict]) -> str:
    text = question.strip() or DEFAULT_QUESTION
    if detections:
        seen = ", ".join(f"{item['label']} ({item['position']})" for item in detections[:8])
        text += f"\nThe on-device detector found: {seen}. Use this only as a hint."
    return text


def _asker(provider: str):
    async def ask(image: bytes, mime: str, question: str, detections: list[dict]) -> str:
        return await llm.ask(
            provider,
            [llm.image_part(image, mime), {"text": _user_prompt(question, detections)}],
            system=SYSTEM_PROMPT,
        )

    return ask


async def describe(image: bytes, mime: str, question: str, detections: list[dict], providers=None) -> dict:
    if providers is None:
        providers = [(name, _asker(name)) for name in llm.configured_providers()]
    failed: list[str] = []
    for name, ask in providers:
        try:
            text = await ask(image, mime, question, detections)
            return {"text": text, "provider": name, "failed_providers": failed}
        except Exception as error:
            failed.append(f"{name}: {type(error).__name__}")
    return {"text": local_description(detections), "provider": "local", "failed_providers": failed}
