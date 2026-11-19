import asyncio
import base64
import binascii
import hashlib
import hmac
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import campus_memory
import checkout
import llm
import messaging
import navigation
import observation_store
import payments
import scene
import sign_reader
import speech
import supermemory_gateway
from assistant import Assistant
from family import Family
from gpu_status import gpu_status
from rate_limit import LimitExceeded, LimitRule, TieredSlidingWindowLimiter
from sign_translator import EnglishToSignRequest, EnglishToSignResponse, translate_english_to_asl
from schemas import (
    RecallHit,
    RecallRememberRequest,
    RecallRememberResponse,
    RecallSearchRequest,
    RecallSearchResponse,
    RecallStatusResponse,
    BridgeConversation,
    BridgeMessage,
    BridgeMessageRequest,
    CampusAlert,
    CampusAlertCreateRequest,
    DetectedObject,
    SignSequenceRequest,
    SignTranslation,
    Observation,
    ObservationChanges,
    ObservationCreateRequest,
    SharedSightDashboard,
    TrackingResult,
    VisionResult,
    WhatChangedRequest,
    WhatChangedResponse,
)

MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "1500000"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "4"))
MIN_REQUEST_INTERVAL = float(os.getenv("MIN_REQUEST_INTERVAL", "1.5"))
TRACK_MIN_REQUEST_INTERVAL = float(os.getenv("TRACK_MIN_REQUEST_INTERVAL", "0.7"))
IMAGE_TYPES = {"image/jpeg", "image/webp", "image/png"}
NOT_CONFIGURED = "Vision service is not configured"

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("guideai")
app = FastAPI(title="GuideAI API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS", "http://localhost:8081,http://127.0.0.1:8081,http://localhost:8082,http://127.0.0.1:8082"
    ).split(","),
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:[0-9]+)?$",
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-Session-ID",
        "X-Device-ID",
        "X-Device-Secret",
        "X-Shared-Sight-Key",
        "X-Moderator-Key",
        "Authorization",
    ],
)

_slots = asyncio.Semaphore(MAX_CONCURRENCY)
_general_limits = TieredSlidingWindowLimiter(
    session=LimitRule(20, 60, MIN_REQUEST_INTERVAL, detail="Session rate limit exceeded"),
    peer=LimitRule(60, 60, detail="Source rate limit exceeded"),
    global_budget=LimitRule(240, 60, max_keys=1, detail="Inference capacity limit exceeded"),
)
_track_limits = TieredSlidingWindowLimiter(
    session=LimitRule(16, 10, TRACK_MIN_REQUEST_INTERVAL, detail="Tracking session rate limit exceeded"),
    peer=LimitRule(64, 10, detail="Tracking source rate limit exceeded"),
    global_budget=LimitRule(256, 10, max_keys=1, detail="Tracking capacity limit exceeded"),
)
_bridge_limits = TieredSlidingWindowLimiter(
    device=LimitRule(8, 300, detail="Bridge join limit exceeded"),
    peer=LimitRule(10, 300, detail="Bridge join limit exceeded"),
    global_budget=LimitRule(100, 60, max_keys=1, detail="Bridge join capacity exceeded"),
)
_memory_write_limits = TieredSlidingWindowLimiter(
    session=LimitRule(60, 60, detail="Memory rate limit exceeded"),
    peer=LimitRule(120, 60, detail="Memory source rate limit exceeded"),
    global_budget=LimitRule(600, 60, max_keys=1, detail="Memory capacity limit exceeded"),
)
_assistant_limits = TieredSlidingWindowLimiter(
    session=LimitRule(30, 60, 0.3, detail="Assistant rate limit exceeded"),
    peer=LimitRule(90, 60, detail="Assistant source rate limit exceeded"),
    global_budget=LimitRule(300, 60, max_keys=1, detail="Assistant capacity limit exceeded"),
)
_family_limits = TieredSlidingWindowLimiter(
    session=LimitRule(30, 60, detail="Family rate limit exceeded"),
    peer=LimitRule(60, 60, detail="Family source rate limit exceeded"),
    global_budget=LimitRule(300, 60, max_keys=1, detail="Family capacity limit exceeded"),
)
_orders = payments.Orders()
_navigator = navigation.Navigator()
_assistant = Assistant(Family(), _orders, navigator=_navigator)


def _peer_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _session_id(request: Request) -> str:
    value = request.headers.get("X-Session-ID") or _peer_key(request)
    if len(value) > 100:
        raise HTTPException(422, "X-Session-ID must contain at most 100 characters")
    return value


def _limited_key(peer: str, session_id: str) -> str:
    return peer + ":" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _apply_limits(limiter: TieredSlidingWindowLimiter, *checks: tuple[str, str]) -> None:
    try:
        limiter.check(*checks)
    except LimitExceeded as error:
        raise HTTPException(
            429, error.detail, headers={"Retry-After": str(error.retry_after)},
        ) from error


def _session_limit(limiter: TieredSlidingWindowLimiter, request: Request, session_id: str) -> None:
    peer = _peer_key(request)
    _apply_limits(
        limiter,
        ("session", _limited_key(peer, session_id)),
        ("peer", peer),
        ("global_budget", "global"),
    )


def _rate_limit(request: Request, session_id: str) -> None:
    _session_limit(_general_limits, request, session_id)


def _track_rate_limit(request: Request, session_id: str) -> None:
    _session_limit(_track_limits, request, session_id)


def _memory_rate_limit(request: Request, session_id: str) -> None:
    _session_limit(_memory_write_limits, request, session_id)


def _assistant_rate_limit(request: Request, session_id: str) -> None:
    _session_limit(_assistant_limits, request, session_id)


def _family_rate_limit(request: Request, session_id: str) -> None:
    _session_limit(_family_limits, request, session_id)


def _bridge_join_rate_limit(request: Request, device_id: str) -> None:
    _apply_limits(
        _bridge_limits,
        ("device", device_id),
        ("peer", _peer_key(request)),
        ("global_budget", "global"),
    )


def _clear_rate_limits_for_tests() -> None:
    limiters = (
        _general_limits, _track_limits, _bridge_limits, _memory_write_limits, _assistant_limits, _family_limits,
    )
    for limiter in limiters:
        limiter.clear()


async def _read_image(image: UploadFile) -> bytes:
    if image.content_type not in IMAGE_TYPES:
        raise HTTPException(415, "JPEG, WebP, or PNG required")
    body = await image.read(MAX_IMAGE_BYTES + 1)
    if not body or len(body) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image is empty or too large")
    return body


async def _detect(body: bytes) -> list[dict]:
    try:
        return await asyncio.to_thread(scene.detector.detect, body)
    except scene.SceneError as error:
        raise HTTPException(422, str(error)) from error


def _objects(detections: list[dict], limit: int) -> list[DetectedObject]:
    ranked = sorted(detections, key=lambda item: item["area"], reverse=True)[:limit]
    return [
        DetectedObject(
            label=item["label"][:40], confidence=item["confidence"], position=item["position"],
            x=item["box"][0], y=item["box"][1],
            width=round(item["box"][2] - item["box"][0], 4), height=round(item["box"][3] - item["box"][1], 4),
        )
        for item in ranked
    ]


def _detector_ready() -> bool:
    return scene.detector.status()["state"] == "ready"


def _require_vision() -> None:
    if not llm.configured() and not scene.detector.enabled():
        raise HTTPException(503, NOT_CONFIGURED)


def _first_sentence(text: str, limit: int) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    return sentence[:limit]


def _text_key(text: str) -> str:
    words = sorted({word for word in re.findall(r"[a-z]+", text.lower()) if len(word) > 3})
    return ("text:" + "-".join(words[:8]))[:80]


def _location(lat: float | None, lon: float | None) -> tuple[float, float] | None:
    return (lat, lon) if lat is not None and lon is not None else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.on_event("startup")
async def _start_warm_up() -> None:
    if os.getenv("MODEL_WARMUP", "true").lower() in {"1", "true", "yes"} and scene.detector.enabled():
        threading.Thread(target=scene.detector.warm_up, name="model-warmup", daemon=True).start()


@app.get("/health")
@app.get("/healthz")
def health():
    providers = llm.configured_providers()
    detector = scene.detector.status()
    return {
        "status": "ok",
        "configured": bool(providers),
        "provider": providers[0] if providers else None,
        "model": llm.model(),
        "vision_providers": providers,
        "detector": {"state": detector["state"], "model": detector["model"], "enabled": scene.detector.enabled()},
        "speech": {"voice": speech.provider(), "transcription": speech.transcriber()},
        "messages": {"whatsapp": "direct" if messaging.configured() else "opens_whatsapp"},
        "payments": {"mode": payments.mode()},
        "navigation": {"maps": "openstreetmap"},
        "shared_sight": {
            "enabled": True,
            "device_allowlist_enabled": bool(os.getenv("SHARED_SIGHT_DEVICE_IDS")),
            "shared_auth_configured": bool(os.getenv("SHARED_SIGHT_TOKEN")),
            "minimum_confidence": observation_store.MIN_CONFIDENCE,
            "verified_shared_minimum_confidence": observation_store.VERIFIED_SHARED_MIN_CONFIDENCE,
        },
        "time": _now(),
    }


@app.post("/v1/track", response_model=TrackingResult)
async def track_scene(request: Request, image: UploadFile = File(...)):
    client_id = _session_id(request)
    body = await _read_image(image)
    _track_rate_limit(request, client_id)
    started = time.monotonic()
    async with _slots:
        detections = await _detect(body)
    latency_ms = int((time.monotonic() - started) * 1000)
    observation_store.record_tracking_latency(latency_ms)
    return TrackingResult(
        objects=_objects(detections, 12),
        warnings=scene.hazard_warnings(detections),
        tracking_latency_ms=latency_ms,
        detector="yolo11" if _detector_ready() else "disabled",
    )


@app.post("/v1/vision/analyze")
async def analyze_scene(
    request: Request,
    image: UploadFile = File(...),
    question: str = Form("", max_length=300),
    describe: bool = Form(True),
):
    client_id = _session_id(request)
    body = await _read_image(image)
    _rate_limit(request, client_id)
    started = time.monotonic()
    async with _slots:
        detections = await _detect(body)
        detect_ms = int((time.monotonic() - started) * 1000)
        result = {
            "event": "scene",
            "timestamp": _now(),
            "warnings": scene.hazard_warnings(detections),
            "detections": detections,
            "detector": scene.detector.status()["state"],
            "description": None,
            "provider": None,
            "failed_providers": [],
        }
        if describe:
            answer = await scene.describe(body, image.content_type, question, detections)
            result.update(
                description=answer["text"], provider=answer["provider"], failed_providers=answer["failed_providers"],
            )
    result["latency_ms"] = {"detect": detect_ms, "total": int((time.monotonic() - started) * 1000)}
    return result


@app.post("/v1/describe", response_model=VisionResult)
async def describe(
    request: Request,
    image: UploadFile = File(...),
    task: str = Form("scene"),
    previous_scene_key: str = Form(""),
):
    if task not in {"scene", "sign"}:
        raise HTTPException(422, "task must be 'scene' or 'sign'")
    client_id = _session_id(request)
    body = await _read_image(image)
    previous = previous_scene_key[:80]
    if task == "sign":
        if not llm.configured():
            raise HTTPException(503, NOT_CONFIGURED)
        _rate_limit(request, client_id)
        async with _slots:
            reading = await sign_reader.read_sign([(body, image.content_type)])
        spoken = sign_reader.sentence(reading["text"])
        key = reading["text"].lower() or "none"
        return VisionResult(
            summary=spoken or "No sign recognised", speech=spoken, scene_key=key, urgency="low",
            changed=key != previous, objects=[], task="sign", should_speak=bool(spoken) and key != previous,
        )
    _require_vision()
    _rate_limit(request, client_id)
    started = time.monotonic()
    async with _slots:
        detections = await _detect(body)
        if not llm.configured() and not _detector_ready():
            raise HTTPException(503, NOT_CONFIGURED)
        answer = await scene.describe(body, image.content_type, "", detections)
    warnings = scene.hazard_warnings(detections)
    key = scene.scene_key(detections) if detections or _detector_ready() else _text_key(answer["text"])
    logger.info(
        "describe_complete latency_ms=%d bytes=%d provider=%s objects=%d",
        int((time.monotonic() - started) * 1000), len(body), answer["provider"], len(detections),
    )
    return VisionResult(
        summary=_first_sentence(answer["text"], 100),
        speech=answer["text"][:240],
        scene_key=key,
        urgency="medium" if warnings else "low",
        changed=key != previous,
        objects=_objects(detections, 8),
        task="scene",
        should_speak=bool(warnings) and key != previous,
        warnings=warnings,
    )


@app.post("/v1/interpret-sign", response_model=SignTranslation)
async def interpret_sign(request: Request, sequence: SignSequenceRequest):
    client_id = _session_id(request)
    frames: list[tuple[bytes, str]] = []
    for frame in sequence.frames:
        if not frame.startswith("data:image/jpeg;base64,"):
            raise HTTPException(415, "Each frame must be a JPEG data URL")
        try:
            body = base64.b64decode(frame.split(",", 1)[1], validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(422, "A frame contains invalid base64 data")
        if not body or len(body) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "A sign frame is empty or too large")
        frames.append((body, "image/jpeg"))
    if not llm.configured():
        raise HTTPException(503, NOT_CONFIGURED)
    _rate_limit(request, client_id)
    async with _slots:
        reading = await sign_reader.read_sign(frames)
    if reading["provider"] is None:
        raise HTTPException(502, "Vision provider request failed")
    transcript, segment = sign_reader.extend_transcript(sequence.previous_transcript, reading["text"])
    return SignTranslation(
        transcript=transcript[-600:], segment=segment, confidence=reading["confidence"],
        is_final=bool(segment), should_speak=bool(segment),
    )


@app.post("/v1/translate-to-sign", response_model=EnglishToSignResponse)
async def translate_to_sign_endpoint(request: Request, body: EnglishToSignRequest):
    session_id = _session_id(request)
    _rate_limit(request, session_id)
    return translate_english_to_asl(body.text)


@app.post("/v1/assistant")
async def assistant_respond(
    request: Request,
    text: str = Form(..., min_length=1, max_length=300),
    image: UploadFile | None = File(None),
    lat: float | None = Form(None, ge=-90, le=90),
    lon: float | None = Form(None, ge=-180, le=180),
):
    device_id, session_id = _authorize_sight(request)
    body = await _read_image(image) if image is not None else None
    _assistant_rate_limit(request, session_id)
    started = time.monotonic()
    mime = image.content_type if image is not None else "image/jpeg"
    try:
        async with _slots:
            reply = await _assistant.respond(device_id, text, body, mime, _location(lat, lon))
    except scene.SceneError as error:
        raise HTTPException(422, str(error)) from error
    reply["timestamp"] = _now()
    reply["latency_ms"] = int((time.monotonic() - started) * 1000)
    return reply


@app.post("/v1/location")
async def location_update(
    request: Request,
    lat: float = Form(..., ge=-90, le=90),
    lon: float = Form(..., ge=-180, le=180),
):
    device_id, session_id = _authorize_sight(request)
    _track_rate_limit(request, session_id)
    _assistant.track(device_id, lat, lon)
    return _navigator.update(device_id, lat, lon)


@app.get("/v1/contacts")
async def contacts_list(request: Request):
    device_id, _session = _authorize_sight(request)
    return _assistant.family.contacts(device_id)


@app.post("/v1/contacts", status_code=201)
async def contacts_add(
    request: Request,
    name: str = Form(..., min_length=1, max_length=40),
    phone: str = Form(..., min_length=7, max_length=24),
):
    device_id, session_id = _authorize_sight(request)
    _family_rate_limit(request, session_id)
    try:
        return _assistant.family.add_contact(device_id, name, phone)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.delete("/v1/contacts/{name}")
async def contacts_remove(request: Request, name: str):
    device_id, session_id = _authorize_sight(request)
    _family_rate_limit(request, session_id)
    _assistant.family.remove_contact(device_id, name[:40])
    return {"status": "removed"}


@app.get("/v1/places")
async def places_list(request: Request):
    device_id, _session = _authorize_sight(request)
    return _assistant.family.places(device_id)


@app.post("/v1/places", status_code=201)
async def places_save(
    request: Request,
    name: str = Form("home", max_length=20),
    address: str = Form(..., min_length=3, max_length=200),
    lat: float | None = Form(None, ge=-90, le=90),
    lon: float | None = Form(None, ge=-180, le=180),
):
    device_id, session_id = _authorize_sight(request)
    _family_rate_limit(request, session_id)
    try:
        found = await _assistant.resolve_place(address, _location(lat, lon))
    except Exception as error:
        raise HTTPException(502, "The map service could not be reached") from error
    if found is None:
        raise HTTPException(404, "That address was not found on the map. Try a fuller address with the city.")
    try:
        return _assistant.family.save_place(device_id, name, found["label"], found["lat"], found["lon"])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.delete("/v1/places/{name}")
async def places_remove(request: Request, name: str):
    device_id, session_id = _authorize_sight(request)
    _family_rate_limit(request, session_id)
    _assistant.family.remove_place(device_id, name[:20])
    return {"status": "removed"}


@app.get("/v1/pay/qr.png")
async def pay_qr(request: Request, item: str = "Coffee", amount: float = 4.5):
    if not 0 < amount <= 10000 or not 0 < len(item) <= 60:
        raise HTTPException(422, "Give an item name and a positive amount")
    _rate_limit(request, _session_id(request))
    image = await asyncio.to_thread(checkout.make_qr_png, checkout.payment_code(item, amount))
    return Response(image, media_type="image/png")


@app.post("/v1/speech")
async def speech_out(request: Request, text: str = Form(..., min_length=1, max_length=speech.MAX_TEXT)):
    if not speech.configured():
        raise HTTPException(503, "No voice service is configured")
    _rate_limit(request, _session_id(request))
    try:
        audio = await speech.synthesize(text)
    except speech.SpeechError as error:
        raise HTTPException(502, str(error)) from error
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@app.post("/v1/speech/transcribe")
async def speech_in(request: Request, audio: UploadFile = File(...)):
    if speech.transcriber() is None:
        raise HTTPException(503, "No transcription service is configured")
    body = await audio.read(speech.MAX_AUDIO_BYTES + 1)
    if not body or len(body) > speech.MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio clip is empty or too large")
    _rate_limit(request, _session_id(request))
    mime = (audio.content_type or "application/octet-stream").split(";")[0]
    try:
        return {"text": await speech.transcribe(body, mime)}
    except speech.SpeechError as error:
        raise HTTPException(502, str(error)) from error


@app.get("/v1/memory/alerts", response_model=list[CampusAlert])
async def get_campus_alerts(request: Request, location: str | None = None):
    """Shared, verified campus reports for a room (one store for every phone)."""
    device_id, session_id = _authorize_sight(request)
    # A camera polling for alerts is an active phone on the dashboard.
    observation_store.touch_device(device_id, session_id)
    return [CampusAlert.model_validate(alert) for alert in observation_store.shared_alerts(device_id, location)]


def _authorize_sight(request: Request) -> tuple[str, str]:
    try:
        shared_key = request.headers.get("X-Shared-Sight-Key") or request.headers.get("X-Moderator-Key")
        return observation_store.authorize_device(
            request.headers.get("X-Device-ID"),
            request.headers.get("X-Session-ID"),
            request.headers.get("X-Device-Secret"),
            shared_key,
        )
    except observation_store.ObservationAccessError as error:
        raise HTTPException(401, str(error)) from error


def _is_trusted_shared_mutator(request: Request, device_id: str) -> bool:
    """Check whether caller is enrolled/authorized to mutate shared safety state."""
    token = os.getenv("SHARED_SIGHT_TOKEN", "").strip()
    allowed_devices = {v.strip() for v in os.getenv("SHARED_SIGHT_DEVICE_IDS", "").split(",") if v.strip()}
    if not token and not allowed_devices:
        return False
    if allowed_devices and device_id in allowed_devices:
        return True
    if token:
        supplied = request.headers.get("X-Shared-Sight-Key") or request.headers.get("X-Moderator-Key") or ""
        if supplied and hmac.compare_digest(supplied, token):
            return True
    return False


def _is_moderator(request: Request, device_id: str) -> bool:
    """Check whether caller possesses moderator/administrator privileges."""
    token = os.getenv("SHARED_SIGHT_TOKEN", "").strip()
    moderator_token = os.getenv("SHARED_SIGHT_MODERATOR_TOKEN", token).strip()
    allowed_devices = {v.strip() for v in os.getenv("SHARED_SIGHT_DEVICE_IDS", "").split(",") if v.strip()}
    if allowed_devices and device_id in allowed_devices:
        return True
    mod_key = request.headers.get("X-Moderator-Key", "").strip()
    if moderator_token and mod_key and hmac.compare_digest(mod_key, moderator_token):
        return True
    return False


@app.post("/v1/observations", response_model=Observation)
async def submit_observation(request: Request, body: ObservationCreateRequest):
    device_id, session_id = _authorize_sight(request)
    if body.privacy_scope == "shared":
        if not _is_trusted_shared_mutator(request, device_id):
            raise HTTPException(403, "Shared safety mutations require trusted authorization")
    try:
        result = observation_store.create_observation(
            zone_id=body.zone_id,
            category=body.category,
            label=body.label,
            description=body.description,
            confidence=body.confidence,
            privacy_scope=body.privacy_scope,
            verified=body.verified,
            room_x=body.room_x,
            room_y=body.room_y,
            expires_in_seconds=body.expires_in_seconds,
            origin=body.origin,
            source_device=device_id,
            source_session=session_id,
        )
    except observation_store.DuplicateObservationError as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return Observation.model_validate(result)


@app.get("/v1/observations/changes", response_model=ObservationChanges)
async def get_observation_changes(request: Request, zone_id: str, compared_seconds: int = 3600):
    _authorize_sight(request)
    if not zone_id.strip() or len(zone_id) > 80:
        raise HTTPException(422, "zone_id must contain 1 to 80 characters")
    return ObservationChanges.model_validate(observation_store.changes(zone_id, compared_seconds))


@app.get("/v1/personal/observations", response_model=list[Observation])
async def search_personal_observations(request: Request, query: str = "", limit: int = 50):
    device_id, _ = _authorize_sight(request)
    return [Observation.model_validate(item) for item in observation_store.search_personal(device_id, query, limit)]


@app.delete("/v1/observations/{observation_id}")
async def remove_owned_observation(request: Request, observation_id: int):
    device_id, _ = _authorize_sight(request)
    if not observation_store.delete_owned(observation_id, device_id):
        raise HTTPException(404, "Observation not found or not owned by this device")
    return {"status": "removed", "id": observation_id}


@app.get("/v1/shared-sight/dashboard", response_model=SharedSightDashboard)
async def shared_sight_dashboard(request: Request, zone_id: str, limit: int = 20):
    device_id, session_id = _authorize_sight(request)
    if not zone_id.strip() or len(zone_id) > 80:
        raise HTTPException(422, "zone_id must contain 1 to 80 characters")
    observation_store.touch_device(device_id, session_id)
    return SharedSightDashboard.model_validate({**observation_store.dashboard(zone_id, limit), "gpu": gpu_status()})


@app.post("/v1/memory/observe", response_model=CampusAlert)
async def observe_campus_hazard(request: Request, body: CampusAlertCreateRequest):
    """Record a hazard, obstacle, sign, or room status a person confirmed."""
    device_id, session_id = _authorize_sight(request)
    if not _is_trusted_shared_mutator(request, device_id):
        raise HTTPException(403, "Shared safety mutations require trusted authorization")
    _memory_rate_limit(request, session_id)
    try:
        alert = observation_store.report_alert(
            location=body.location, category=body.category, label=body.label,
            description=body.description, source_device=device_id, source_session=session_id,
        )
    except observation_store.DuplicateObservationError as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return CampusAlert.model_validate(alert)


@app.post("/v1/memory/resolve/{alert_id}")
async def resolve_campus_alert(request: Request, alert_id: int):
    """Mark a campus hazard as cleared or resolved."""
    device_id, _session_id = _authorize_sight(request)
    is_mod = _is_moderator(request, device_id)
    try:
        resolved = observation_store.resolve_shared(alert_id, actor_device=device_id, is_moderator=is_mod)
    except observation_store.ObservationPermissionError as error:
        raise HTTPException(403, str(error)) from error
    if not resolved:
        raise HTTPException(404, "Alert not found")
    return {"status": "resolved", "id": alert_id}


@app.post("/v1/memory/what-changed", response_model=WhatChangedResponse)
async def what_changed(request: Request, body: WhatChangedRequest):
    """Compare current objects against baseline memory for the location."""
    device_id, session_id = _authorize_sight(request)
    _memory_rate_limit(request, session_id)
    is_mod = _is_moderator(request, device_id)
    baseline_exists = campus_memory.has_baseline(body.location)
    if body.update_baseline and baseline_exists and not is_mod:
        raise HTTPException(403, "Only an authorized moderator can replace an established room baseline")
    if not baseline_exists and not _is_trusted_shared_mutator(request, device_id):
        raise HTTPException(403, "Establishing a shared room baseline requires trusted authorization")
    dict_objects = [obj.model_dump() for obj in body.current_objects]
    result = campus_memory.detect_what_changed(
        location=body.location,
        current_objects=dict_objects,
        update_baseline=body.update_baseline if (is_mod or not baseline_exists) else False,
    )
    return WhatChangedResponse.model_validate(result)


@app.get("/v1/recall/status", response_model=RecallStatusResponse)
async def recall_status():
    """Tell the app whether memory sync is available before it offers it."""
    if not supermemory_gateway.configured():
        return RecallStatusResponse(configured=False, reason="SUPERMEMORY_API_KEY is not set on the server")
    return RecallStatusResponse(configured=True)


@app.post("/v1/recall/remember", response_model=RecallRememberResponse)
async def recall_remember(request: Request, body: RecallRememberRequest):
    """Mirror one observation into the caller's own Supermemory namespace.

    The namespace comes from the verified device ID, never from the request
    body, so a client cannot write into another device's memory.
    """
    device_id, session_id = _authorize_sight(request)
    _memory_rate_limit(request, session_id)
    try:
        document = supermemory_gateway.build_document(
            content=body.content,
            kind=body.kind,
            document_id=body.id,
            supporting_context=body.supportingContext,
            metadata=body.metadata,
            date=body.date,
        )
        result = await supermemory_gateway.ingest(device_id, document)
    except supermemory_gateway.SupermemoryError as error:
        raise HTTPException(error.status, str(error)) from error
    return RecallRememberResponse.model_validate(result)


@app.post("/v1/recall/search", response_model=RecallSearchResponse)
async def recall_search(request: Request, body: RecallSearchRequest):
    """Relationship-aware recall from the caller's own namespace."""
    device_id, session_id = _authorize_sight(request)
    _memory_rate_limit(request, session_id)
    try:
        query = supermemory_gateway.build_search(
            query=body.query,
            limit=body.limit,
            kinds=body.kinds,
            threshold=body.threshold,
        )
        results = await supermemory_gateway.search(device_id, query)
    except supermemory_gateway.SupermemoryError as error:
        raise HTTPException(error.status, str(error)) from error
    return RecallSearchResponse(results=[RecallHit.model_validate(hit) for hit in results])


def _bridge_call(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except observation_store.BridgeNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except observation_store.BridgeFullError as error:
        raise HTTPException(409, str(error)) from error
    except observation_store.BridgeAccessError as error:
        raise HTTPException(403, str(error)) from error


def _bridge_code(code: str) -> str:
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(422, "A bridge code is six digits")
    return code


@app.post("/v1/bridge/conversations", response_model=BridgeConversation)
async def create_bridge_conversation(request: Request):
    """Start a Deaf-Blind bridge conversation and get a 6-digit code to share."""
    device_id, _session_id = _authorize_sight(request)
    return BridgeConversation.model_validate(observation_store.create_bridge(device_id))


@app.post("/v1/bridge/conversations/{code}/join", response_model=BridgeConversation)
async def join_bridge_conversation(request: Request, code: str):
    """Join a conversation as its second device (one pair per conversation)."""
    device_id, _session_id = _authorize_sight(request)
    _bridge_join_rate_limit(request, device_id)
    return BridgeConversation.model_validate(
        _bridge_call(observation_store.join_bridge, _bridge_code(code), device_id)
    )


@app.get("/v1/bridge/conversations/{code}", response_model=BridgeConversation)
async def get_bridge_conversation(request: Request, code: str):
    device_id, _session_id = _authorize_sight(request)
    return BridgeConversation.model_validate(
        _bridge_call(observation_store.bridge_status, _bridge_code(code), device_id)
    )


@app.post("/v1/bridge/message", response_model=BridgeMessage)
async def post_bridge_message(request: Request, body: BridgeMessageRequest):
    """Post a Deaf-Blind bridge message (sign translation or spoken reply)."""
    device_id, _session_id = _authorize_sight(request)
    msg = _bridge_call(
        observation_store.add_bridge_message,
        body.session_id, device_id, body.sender_role, body.text, body.client_id,
    )
    return BridgeMessage.model_validate(msg)


@app.get("/v1/bridge/messages", response_model=list[BridgeMessage])
async def get_bridge_messages(
    request: Request, session_id: str, after_id: int | None = None, limit: int = 50,
):
    """The newest messages in time order, or only those after ``after_id`` for live refresh."""
    device_id, _session_id = _authorize_sight(request)
    messages = _bridge_call(
        observation_store.list_bridge_messages, _bridge_code(session_id), device_id, after_id, limit,
    )
    return [BridgeMessage.model_validate(m) for m in messages]

