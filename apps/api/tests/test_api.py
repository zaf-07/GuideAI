import pytest
from fastapi.testclient import TestClient

import llm
import main
import observation_store
import scene
import sign_reader
from conftest import FakeDetector, detection, device_headers, png

client = TestClient(main.app)
FRAMES = {"frames": ["data:image/jpeg;base64,ZmFrZQ=="] * 3}


@pytest.fixture(autouse=True)
def isolated_devices(tmp_path, monkeypatch):
    monkeypatch.setattr(observation_store, "DB_PATH", tmp_path / "devices.sqlite3")
    monkeypatch.delenv("SHARED_SIGHT_TOKEN", raising=False)
    monkeypatch.delenv("SHARED_SIGHT_DEVICE_IDS", raising=False)
    observation_store.init_db()


def use_detector(monkeypatch, detections):
    monkeypatch.setattr(scene.detector, "detect", FakeDetector(detections).detect)
    monkeypatch.setattr(scene.detector, "status", lambda: {"state": "ready", "model": "yolo11n.pt", "error": None})
    monkeypatch.setattr(main._assistant, "detector", scene.detector)


def use_cloud(monkeypatch, answer):
    async def fake_ask(provider, parts, system="", json_mode=False, timeout=10.0):
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(llm, "ask", fake_ask)


def test_health_does_not_expose_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value")
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["vision_providers"] == ["gemini"]
    assert "super-secret-value" not in response.text
    assert "key" not in response.text.lower()


def test_healthz_alias_matches_health():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["configured"] is False


def test_rejects_unsupported_media_type():
    response = client.post(
        "/v1/describe", headers={"X-Session-ID": "invalid-media"},
        files={"image": ("frame.txt", b"not-an-image", "text/plain")},
    )
    assert response.status_code == 415


def test_describe_fails_closed_without_a_model_or_detector():
    response = client.post(
        "/v1/describe", headers={"X-Session-ID": "nothing-configured"},
        files={"image": ("frame.jpg", b"fake-jpeg", "image/jpeg")},
        data={"task": "scene", "previous_scene_key": ""},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Vision service is not configured"


def test_describe_uses_the_detector_alone_when_the_cloud_is_missing(monkeypatch):
    use_detector(monkeypatch, [detection("chair", 0.2, 0.5), detection("book", 0.6, 0.7)])
    monkeypatch.setenv("YOLO_ENABLED", "true")
    response = client.post(
        "/v1/describe", headers={"X-Session-ID": "detector-only"}, files={"image": ("frame.png", png(), "image/png")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "a chair ahead, left" in payload["speech"]
    assert payload["warnings"] == ["Chair ahead, left."]
    assert (payload["urgency"], payload["changed"], payload["should_speak"]) == ("medium", True, True)
    assert payload["objects"][0] == {
        "label": "chair", "confidence": 0.9, "position": "ahead, left", "x": 0.2, "y": 0.2, "width": 0.3, "height": 0.6,
    }


def test_describe_speaks_the_cloud_answer_and_stays_quiet_when_nothing_changed(monkeypatch):
    use_detector(monkeypatch, [detection("chair", 0.2, 0.5)])
    use_cloud(monkeypatch, "A chair is ahead on your left. A window is behind it.")
    first = client.post(
        "/v1/describe", headers={"X-Session-ID": "cloud"}, files={"image": ("frame.png", png(), "image/png")},
    ).json()
    assert first["summary"] == "A chair is ahead on your left."
    assert first["speech"] == "A chair is ahead on your left. A window is behind it."
    assert first["scene_key"] == "chair@ahead-left"
    main._clear_rate_limits_for_tests()
    second = client.post(
        "/v1/describe", headers={"X-Session-ID": "cloud"}, files={"image": ("frame.png", png(), "image/png")},
        data={"previous_scene_key": first["scene_key"]},
    ).json()
    assert (second["changed"], second["should_speak"]) == (False, False)


def test_describe_falls_back_to_the_detector_when_the_cloud_fails(monkeypatch):
    use_detector(monkeypatch, [detection("person", 0.3, 0.7)])
    use_cloud(monkeypatch, TimeoutError())
    payload = client.post(
        "/v1/describe", headers={"X-Session-ID": "cloud-down"}, files={"image": ("frame.png", png(), "image/png")},
    ).json()
    assert "a person ahead" in payload["speech"]


def test_tracking_is_independent_of_the_cloud():
    response = client.post(
        "/v1/track", headers={"X-Session-ID": "tracking"}, files={"image": ("frame.png", png(), "image/png")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["detector"] == "disabled"
    assert payload["objects"] == []
    assert payload["collision_warnings_enabled"] is False


def test_tracking_returns_boxes_and_warnings(monkeypatch):
    use_detector(monkeypatch, [detection("book", 0.6, 0.7), detection("person", 0.1, 0.9)])
    payload = client.post(
        "/v1/track", headers={"X-Session-ID": "tracking-live"}, files={"image": ("frame.png", png(), "image/png")},
    ).json()
    assert payload["detector"] == "yolo11"
    assert [item["label"] for item in payload["objects"]] == ["person", "book"]
    assert payload["warnings"] == ["Person ahead."]


def test_analyze_can_skip_the_cloud(monkeypatch):
    use_detector(monkeypatch, [detection("chair", 0.2, 0.5)])
    use_cloud(monkeypatch, AssertionError("the cloud must not be called"))
    payload = client.post(
        "/v1/vision/analyze", headers={"X-Session-ID": "analyze"},
        files={"image": ("frame.png", png(), "image/png")}, data={"describe": "false"},
    ).json()
    assert payload["warnings"] == ["Chair ahead, left."]
    assert (payload["description"], payload["provider"]) == (None, None)


def test_sign_sequence_requires_three_jpeg_frames():
    response = client.post(
        "/v1/interpret-sign", headers={"X-Session-ID": "two-frames"},
        json={"frames": FRAMES["frames"][:2]},
    )
    assert response.status_code == 422


def test_sign_sequence_rejects_unbounded_transcript():
    response = client.post(
        "/v1/interpret-sign", headers={"X-Session-ID": "long-transcript"},
        json={**FRAMES, "previous_transcript": "x" * 601},
    )
    assert response.status_code == 422


def test_sign_sequence_fails_closed_without_a_model():
    response = client.post(
        "/v1/interpret-sign", headers={"X-Session-ID": "no-model"}, json={**FRAMES, "previous_transcript": "Hello"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Vision service is not configured"


def test_sign_reading_appends_a_known_sign_once(monkeypatch):
    use_cloud(monkeypatch, '{"text": "I love you", "confidence": 0.85}')
    first = client.post("/v1/interpret-sign", headers={"X-Session-ID": "signing"}, json=FRAMES).json()
    assert (first["transcript"], first["segment"], first["should_speak"]) == ("I love you.", "I love you.", True)
    main._clear_rate_limits_for_tests()
    held = client.post(
        "/v1/interpret-sign", headers={"X-Session-ID": "signing"},
        json={**FRAMES, "previous_transcript": "I love you."},
    ).json()
    assert (held["transcript"], held["segment"], held["should_speak"]) == ("I love you.", "", False)


def test_sign_reading_ignores_low_confidence_and_unknown_signs(monkeypatch):
    use_cloud(monkeypatch, '{"text": "hello", "confidence": 0.41}')
    low = client.post("/v1/interpret-sign", headers={"X-Session-ID": "unsure"}, json=FRAMES).json()
    assert (low["segment"], low["should_speak"]) == ("", False)
    assert sign_reader.MIN_CONFIDENCE > 0.41


def test_sign_reading_reports_a_failed_provider(monkeypatch):
    use_cloud(monkeypatch, TimeoutError())
    response = client.post("/v1/interpret-sign", headers={"X-Session-ID": "provider-down"}, json=FRAMES)
    assert response.status_code == 502


def test_assistant_and_family_routes_require_a_device():
    assert client.post("/v1/assistant", data={"text": "hello"}).status_code == 401
    assert client.get("/v1/contacts").status_code == 401
    assert client.post("/v1/contacts", data={"name": "Mom", "phone": "+14155550100"}).status_code == 401
    assert client.get("/v1/places").status_code == 401
    assert client.post("/v1/location", data={"lat": "1", "lon": "1"}).status_code == 401


def test_contacts_belong_to_the_device_that_saved_them():
    alice, bob = device_headers("alice"), device_headers("bob")
    created = client.post("/v1/contacts", headers=alice, data={"name": "Mom", "phone": "+1 415 555 0100"})
    assert created.status_code == 201
    assert created.json() == {"name": "Mom", "phone": "14155550100"}
    assert client.get("/v1/contacts", headers=alice).json() == [{"name": "Mom", "phone": "14155550100"}]
    assert client.get("/v1/contacts", headers=bob).json() == []
    assert client.delete("/v1/contacts/Mom", headers=bob).status_code == 200
    assert len(client.get("/v1/contacts", headers=alice).json()) == 1
    assert client.post("/v1/contacts", headers=alice, data={"name": "Bad", "phone": "1234567"}).status_code == 201
    assert client.post("/v1/contacts", headers=alice, data={"name": "Bad", "phone": "12-34-5"}).status_code == 422


def test_sharing_a_location_waits_for_a_yes():
    async def place_name(lat, lon):
        return "20th Street, Dogpatch"

    main._assistant.place_name = place_name
    alice = device_headers("alice")
    client.post("/v1/contacts", headers=alice, data={"name": "Mom", "phone": "+14155550100"})
    draft = client.post(
        "/v1/assistant", headers=alice, data={"text": "Tell Mom where I am", "lat": "37.7606", "lon": "-122.3866"},
    ).json()
    assert draft["confirm"] == "Send to Mom on WhatsApp?"
    assert draft["open_url"] is None
    main._clear_rate_limits_for_tests()
    stranger = client.post("/v1/assistant", headers=device_headers("bob"), data={"text": "Yes"}).json()
    assert stranger["intent"] == "nothing_pending"
    main._clear_rate_limits_for_tests()
    sent = client.post("/v1/assistant", headers=alice, data={"text": "Yes"}).json()
    assert sent["intent"] == "message_confirm"
    assert sent["open_url"].startswith("https://wa.me/14155550100?text=I%20am%20near%2020th%20Street")


def test_assistant_describes_a_frame_and_rejects_a_broken_one(monkeypatch):
    alice = device_headers("alice")
    broken = client.post(
        "/v1/assistant", headers=alice, data={"text": "What is in front of me?"},
        files={"image": ("frame.jpg", b"fake-jpeg", "image/jpeg")},
    )
    assert broken.status_code == 422
    main._clear_rate_limits_for_tests()
    use_detector(monkeypatch, [detection("chair", 0.2, 0.5)])
    reply = client.post(
        "/v1/assistant", headers=alice, data={"text": "What is in front of me?"},
        files={"image": ("frame.png", png(), "image/png")},
    ).json()
    assert reply["warnings"] == ["Chair ahead, left."]
    assert "a chair ahead, left" in reply["say"]


def test_location_updates_report_no_route_until_one_starts():
    alice = device_headers("alice")
    response = client.post("/v1/location", headers=alice, data={"lat": "37.7606", "lon": "-122.3866"})
    assert response.json() == {"active": False, "say": None}
    assert client.post("/v1/location", headers=alice, data={"lat": "120", "lon": "0"}).status_code == 422


def test_voice_routes_fail_closed_without_a_service():
    assert client.post("/v1/speech", data={"text": "hello"}).status_code == 503
    files = {"audio": ("clip.webm", b"audio", "audio/webm")}
    assert client.post("/v1/speech/transcribe", files=files).status_code == 503


def test_payment_code_image_is_a_png():
    response = client.get("/v1/pay/qr.png", params={"item": "Coffee", "amount": 4.5})
    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")
    assert client.get("/v1/pay/qr.png", params={"item": "Coffee", "amount": 0}).status_code == 422
