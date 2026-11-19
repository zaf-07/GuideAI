"""GuideLens gateway.

One WebSocket endpoint. The client opens it when the vision surface loads and
keeps it warm for the session, because per-frame HTTP would spend 150-300ms on
connection setup every time.

What this service is **not**: it is never in the safety loop. Obstacle
detection, distance and collision warning all run on the device. If this
gateway disappears mid-walk the user must notice no change in safety
behaviour. Everything here produces descriptions, never warnings.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import config
import nebius
import prompts
from device_identity import DeviceAuthError, authorize
from rate_limit import LimitExceeded, LimitRule, TieredSlidingWindowLimiter
from token_budget import budget

logger = logging.getLogger("guidelens.gateway")

# Narration is motion-gated on the client, so a well-behaved session sends far
# fewer frames than this. The ceiling exists for the misbehaving one.
_narration_limits = TieredSlidingWindowLimiter(
    session=LimitRule(40, 60, detail="Narration session rate limit exceeded"),
    peer=LimitRule(120, 60, detail="Narration source rate limit exceeded"),
    global_budget=LimitRule(600, 60, max_keys=1, detail="Narration capacity limit exceeded"),
)
_dialogue_limits = TieredSlidingWindowLimiter(
    session=LimitRule(12, 60, detail="Question rate limit exceeded"),
    peer=LimitRule(30, 60, detail="Question source rate limit exceeded"),
    global_budget=LimitRule(120, 60, max_keys=1, detail="Question capacity limit exceeded"),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await nebius.open_client()
    try:
        yield
    finally:
        await nebius.close_client()


app = FastAPI(title="GuideLens Gateway", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in __import__("os").getenv("CORS_ORIGINS", "").split(",") if origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/healthz")
def health() -> dict:
    return {
        "status": "ok",
        "narration_configured": config.configured(),
        "narration_model": config.NARRATION_MODEL,
        "dialogue_model": config.DIALOGUE_MODEL,
    }


def _peer_key(websocket: WebSocket) -> str:
    forwarded = websocket.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = websocket.client
    return client.host if client else "unknown"


async def _send(websocket: WebSocket, payload: dict) -> None:
    await websocket.send_text(json.dumps(payload))


def _log(kind: str, device_id: str, stats: nebius.StreamStats, spoken: bool) -> None:
    """One line per request. TTFT, duration, tokens, model, estimated cost."""
    logger.info(
        json.dumps(
            {
                "event": kind,
                "device": device_id[:16],
                "model": stats.model,
                "ttft_ms": round(stats.ttft_ms) if stats.ttft_ms is not None else None,
                "duration_ms": round(stats.duration_ms),
                "input_tokens": stats.input_tokens,
                "output_tokens": stats.output_tokens,
                "cost_usd": round(stats.cost_usd, 8),
                "spoken": spoken,
            }
        )
    )


@app.websocket("/v1/narrate")
async def narrate(websocket: WebSocket) -> None:
    """Frames in, spoken fragments out.

    Protocol, all JSON text frames:
      client -> {"type": "narrate",  "frame": "<base64 jpeg>"}
                {"type": "question", "frame": "<base64 jpeg>", "text": "..."}
      server -> {"type": "delta", "text": "..."}        streamed fragment
                {"type": "done",  "skipped": bool}      end of one reply
                {"type": "error", "message": "...", "fatal": bool}

    Deltas are relayed the instant they arrive so the client can speak by
    sentence instead of waiting for completion.
    """
    await websocket.accept()
    try:
        device_id, session_id = authorize(
            websocket.headers.get("X-Device-ID"),
            websocket.headers.get("X-Session-ID"),
            websocket.headers.get("X-Device-Secret"),
        )
    except DeviceAuthError as error:
        await _send(websocket, {"type": "error", "message": str(error), "fatal": True})
        await websocket.close(code=4401)
        return

    peer = _peer_key(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except ValueError:
                await _send(websocket, {"type": "error", "message": "Malformed message", "fatal": False})
                continue

            kind = message.get("type")
            if kind == "ping":
                await _send(websocket, {"type": "pong"})
                continue
            if kind not in ("narrate", "question"):
                await _send(websocket, {"type": "error", "message": "Unknown message type", "fatal": False})
                continue

            frame = message.get("frame")
            if not isinstance(frame, str) or not frame:
                await _send(websocket, {"type": "error", "message": "A frame is required", "fatal": False})
                continue
            try:
                import base64

                jpeg = base64.b64decode(frame, validate=True)
            except Exception:
                await _send(websocket, {"type": "error", "message": "Frame is not valid base64", "fatal": False})
                continue
            if len(jpeg) > config.MAX_FRAME_BYTES:
                await _send(websocket, {"type": "error", "message": "Frame is too large", "fatal": False})
                continue

            limiter = _narration_limits if kind == "narrate" else _dialogue_limits
            try:
                # One call, so a rejection in any tier leaves no partial
                # charge in the others.
                limiter.check(
                    ("session", f"{peer}|{session_id}"),
                    ("peer", peer),
                    ("global_budget", "global"),
                )
            except LimitExceeded as error:
                await _send(websocket, {"type": "error", "message": str(error), "fatal": False})
                continue

            # Frequency limits do not bound spend; this does.
            if not budget.allows(device_id):
                await _send(
                    websocket,
                    {"type": "error", "message": "Hourly narration budget reached for this device", "fatal": False},
                )
                continue

            question = message.get("text") if kind == "question" else None
            model = config.NARRATION_MODEL if kind == "narrate" else config.DIALOGUE_MODEL
            stats = nebius.StreamStats(model=model)
            messages = nebius.build_messages(
                prompts.NARRATION_SYSTEM_PROMPT if kind == "narrate" else prompts.DIALOGUE_SYSTEM_PROMPT,
                jpeg,
                question if isinstance(question, str) and question.strip() else None,
            )

            # Only narration can answer SKIP; a question always gets an answer.
            gate = prompts.SkipGate() if kind == "narrate" else None
            try:
                async for delta in nebius.stream_completion(
                    model=model,
                    messages=messages,
                    max_tokens=config.NARRATION_MAX_TOKENS if kind == "narrate" else config.DIALOGUE_MAX_TOKENS,
                    stats=stats,
                ):
                    text = gate.feed(delta) if gate else delta
                    if text:
                        await _send(websocket, {"type": "delta", "text": text})
            except nebius.NebiusError as error:
                budget.record(device_id, stats.input_tokens + stats.output_tokens)
                _log(kind, device_id, stats, spoken=False)
                await _send(websocket, {"type": "error", "message": str(error), "fatal": False})
                continue

            budget.record(device_id, stats.input_tokens + stats.output_tokens)
            skipped = bool(gate and gate.is_skip)
            if gate and not skipped:
                remainder = gate.flush()
                if remainder:
                    await _send(websocket, {"type": "delta", "text": remainder})
            # A skipped frame produces silence, which is the correct output
            # for most frames: constant chatter is what users switch off.
            await _send(websocket, {"type": "done", "skipped": skipped})
            _log(kind, device_id, stats, spoken=not skipped)
    except WebSocketDisconnect:
        return
