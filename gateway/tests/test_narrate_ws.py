"""The /v1/narrate protocol, end to end, with Nebius faked.

Exercises the real endpoint: identity, limits, budget, streaming relay and
the SKIP contract. No credits are spent and no network is touched.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

import config
import main
import nebius
from device_identity import derive_device_id
from token_budget import budget

SECRET = "c" * 64
DEVICE = derive_device_id(SECRET)
HEADERS = {"X-Device-ID": DEVICE, "X-Session-ID": "s1", "X-Device-Secret": SECRET}
FRAME = base64.b64encode(b"\xff\xd8\xff\xe0 fake jpeg").decode()


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.delenv("GUIDELENS_DEVICE_IDS", raising=False)
    budget.clear()
    for limiter in (main._narration_limits, main._dialogue_limits):
        limiter.clear()
    yield
    budget.clear()


def fake_stream(deltas, *, input_tokens=700, output_tokens=12):
    async def _stream(*, model, messages, max_tokens, stats):
        stats.input_tokens = input_tokens
        stats.output_tokens = output_tokens
        for delta in deltas:
            stats.ttft_ms = stats.ttft_ms or 1.0
            stats.text += delta
            yield delta

    return _stream


def converse(client, messages, monkeypatch, deltas):
    monkeypatch.setattr(nebius, "stream_completion", fake_stream(deltas))
    with client.websocket_connect("/v1/narrate", headers=HEADERS) as ws:
        for message in messages:
            ws.send_text(json.dumps(message))
        received = []
        while True:
            payload = json.loads(ws.receive_text())
            received.append(payload)
            if payload["type"] == "done" or payload.get("fatal"):
                break
        return received


@pytest.fixture
def client(monkeypatch):
    # The lifespan opens a real httpx client; harmless, but keep it offline.
    async def _noop():
        return None

    monkeypatch.setattr(nebius, "open_client", _noop)
    monkeypatch.setattr(nebius, "close_client", _noop)
    with TestClient(main.app) as test_client:
        yield test_client


def test_health_reports_configuration(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["narration_model"] == config.NARRATION_MODEL


def test_narration_streams_deltas_then_done(client, monkeypatch):
    received = converse(client, [{"type": "narrate", "frame": FRAME}], monkeypatch, ["Pole,", " two meters."])
    assert [m["text"] for m in received if m["type"] == "delta"] == ["Pole,", " two meters."]
    assert received[-1] == {"type": "done", "skipped": False}


def test_a_skip_reply_speaks_nothing(client, monkeypatch):
    received = converse(client, [{"type": "narrate", "frame": FRAME}], monkeypatch, ["SK", "IP"])
    assert not [m for m in received if m["type"] == "delta"]
    assert received[-1] == {"type": "done", "skipped": True}


def test_a_question_is_answered_without_the_skip_contract(client, monkeypatch):
    received = converse(
        client,
        [{"type": "question", "frame": FRAME, "text": "what is to my left?"}],
        monkeypatch,
        ["SKIP"],
    )
    # SKIP is narration-only; a question always gets its answer relayed.
    assert [m["text"] for m in received if m["type"] == "delta"] == ["SKIP"]
    assert received[-1]["skipped"] is False


def test_an_unauthenticated_client_is_closed(client):
    with client.websocket_connect("/v1/narrate", headers={"X-Device-ID": "device-nope"}) as ws:
        payload = json.loads(ws.receive_text())
    assert payload["type"] == "error"
    assert payload["fatal"] is True


def test_another_devices_id_cannot_be_claimed(client):
    headers = dict(HEADERS, **{"X-Device-ID": derive_device_id("d" * 64)})
    with client.websocket_connect("/v1/narrate", headers=headers) as ws:
        payload = json.loads(ws.receive_text())
    assert payload["fatal"] is True


def test_an_oversized_frame_is_refused_without_calling_nebius(client, monkeypatch):
    called = False

    def _explode(**_):
        nonlocal called
        called = True
        raise AssertionError("Nebius must not be called for a rejected frame")

    monkeypatch.setattr(nebius, "stream_completion", _explode)
    huge = base64.b64encode(b"x" * (config.MAX_FRAME_BYTES + 1)).decode()
    with client.websocket_connect("/v1/narrate", headers=HEADERS) as ws:
        ws.send_text(json.dumps({"type": "narrate", "frame": huge}))
        payload = json.loads(ws.receive_text())
    assert payload["type"] == "error"
    assert called is False


def test_malformed_messages_do_not_drop_the_connection(client, monkeypatch):
    monkeypatch.setattr(nebius, "stream_completion", fake_stream(["Door ahead."]))
    with client.websocket_connect("/v1/narrate", headers=HEADERS) as ws:
        ws.send_text("not json")
        assert json.loads(ws.receive_text())["type"] == "error"
        ws.send_text(json.dumps({"type": "narrate"}))
        assert json.loads(ws.receive_text())["type"] == "error"
        ws.send_text(json.dumps({"type": "narrate", "frame": "!!!not base64!!!"}))
        assert json.loads(ws.receive_text())["type"] == "error"
        # The session is still usable afterwards.
        ws.send_text(json.dumps({"type": "narrate", "frame": FRAME}))
        assert json.loads(ws.receive_text())["type"] == "delta"


def test_ping_keeps_the_socket_warm(client):
    with client.websocket_connect("/v1/narrate", headers=HEADERS) as ws:
        ws.send_text(json.dumps({"type": "ping"}))
        assert json.loads(ws.receive_text()) == {"type": "pong"}


def test_the_hourly_budget_stops_a_looping_client(client, monkeypatch):
    budget.record(DEVICE, config.DEVICE_TOKENS_PER_HOUR)
    monkeypatch.setattr(nebius, "stream_completion", fake_stream(["Pole."]))
    with client.websocket_connect("/v1/narrate", headers=HEADERS) as ws:
        ws.send_text(json.dumps({"type": "narrate", "frame": FRAME}))
        payload = json.loads(ws.receive_text())
    assert payload["type"] == "error"
    assert "budget" in payload["message"].lower()


def test_spend_is_recorded_against_the_device(client, monkeypatch):
    converse(client, [{"type": "narrate", "frame": FRAME}], monkeypatch, ["Pole."])
    assert budget.spent(DEVICE) == 712


def test_an_upstream_failure_is_reported_without_closing(client, monkeypatch):
    async def _fail(*, model, messages, max_tokens, stats):
        raise nebius.NebiusError("Nebius unreachable: boom")
        yield  # pragma: no cover

    monkeypatch.setattr(nebius, "stream_completion", _fail)
    with client.websocket_connect("/v1/narrate", headers=HEADERS) as ws:
        ws.send_text(json.dumps({"type": "narrate", "frame": FRAME}))
        payload = json.loads(ws.receive_text())
    assert payload["type"] == "error"
    assert payload["fatal"] is False
