import llm
import scene
import sign_reader
from conftest import detection, run


def test_zone_names_follow_horizontal_position():
    assert scene.zone(0.1) == "on the left"
    assert scene.zone(0.3) == "ahead, left"
    assert scene.zone(0.5) == "ahead"
    assert scene.zone(0.7) == "ahead, right"
    assert scene.zone(0.95) == "on the right"


def test_warning_names_position_and_never_distance():
    warnings = scene.hazard_warnings([detection("chair", 0.2, 0.5)])
    assert warnings == ["Chair ahead, left."]
    assert not any(char.isdigit() for char in warnings[0])


def test_small_or_harmless_objects_do_not_warn():
    tiny_chair = detection("chair", 0.50, 0.55, y1=0.5, y2=0.55)
    assert scene.hazard_warnings([tiny_chair, detection("book", 0.2, 0.8)]) == []


def test_warnings_are_largest_first_and_capped():
    found = [
        detection("chair", 0.45, 0.55), detection("person", 0.0, 0.9), detection("car", 0.6, 1.0),
        detection("bench", 0.0, 0.3), detection("dog", 0.3, 0.6),
    ]
    warnings = scene.hazard_warnings(found)
    assert len(warnings) == scene.MAX_WARNINGS
    assert warnings[0].startswith("Person")


def test_local_description():
    assert "do not recognise" in scene.local_description([])
    text = scene.local_description([
        detection("person", 0.7, 0.9), detection("person", 0.65, 0.85), detection("chair", 0.2, 0.5),
    ])
    assert "2 people ahead, right" in text
    assert scene.plural("bus") == "buses" and scene.plural("chair") == "chairs"
    assert "a chair ahead, left" in text


def test_scene_key_is_stable_and_ignores_order():
    first = scene.scene_key([detection("chair", 0.2, 0.5), detection("person", 0.7, 0.9)])
    second = scene.scene_key([detection("person", 0.7, 0.9), detection("chair", 0.2, 0.5)])
    assert first == second == "chair@ahead-left|person@ahead-right"
    assert scene.scene_key([]) == "empty"


def test_first_working_provider_wins():
    async def good(*args):
        return "A chair is ahead."

    async def never(*args):
        raise AssertionError("should not be called")

    result = run(scene.describe(b"", "image/jpeg", "", [], providers=[("gemini", good), ("groq", never)]))
    assert (result["provider"], result["text"], result["failed_providers"]) == ("gemini", "A chair is ahead.", [])


def test_falls_back_to_next_provider():
    async def broken(*args):
        raise TimeoutError()

    async def good(*args):
        return "A door is ahead."

    result = run(scene.describe(b"", "image/jpeg", "", [], providers=[("gemini", broken), ("groq", good)]))
    assert result["provider"] == "groq"
    assert result["failed_providers"] == ["gemini: TimeoutError"]


def test_falls_back_to_local_detector_when_cloud_is_down():
    async def broken(*args):
        raise ConnectionError()

    seen = [detection("chair", 0.2, 0.5)]
    result = run(scene.describe(b"", "image/jpeg", "", seen, providers=[("gemini", broken), ("groq", broken)]))
    assert result["provider"] == "local"
    assert "a chair ahead, left" in result["text"]
    assert len(result["failed_providers"]) == 2


def test_disabled_detector_returns_nothing_and_bad_images_are_rejected():
    import pytest

    from conftest import png

    assert scene.detector.detect(png()) == []
    assert scene.detector.status()["state"] == "unavailable"
    with pytest.raises(scene.SceneError):
        scene.detector.detect(b"not an image")


def test_provider_order_and_models(monkeypatch):
    assert llm.configured_providers() == []
    assert llm.model() is None
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert llm.configured_providers() == ["gemini", "groq"]
    assert llm.model() == "gemini-flash-lite-latest"
    monkeypatch.setenv("VISION_PROVIDERS", "groq,gemini")
    assert llm.configured_providers() == ["groq", "gemini"]


def test_complete_tries_each_provider_in_turn(monkeypatch):
    calls = []

    async def fake_ask(provider, parts, system="", json_mode=False, timeout=10.0):
        calls.append(provider)
        if provider == "gemini":
            raise TimeoutError()
        return "ok"

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setattr(llm, "ask", fake_ask)
    assert run(llm.complete([{"text": "hi"}])) == "ok"
    assert calls == ["gemini", "groq"]


def test_only_known_confident_signs_pass():
    assert sign_reader.parse_reading('{"text": "Thank You", "confidence": 0.9}')["text"] == "thank you"
    assert sign_reader.parse_reading('{"text": "i love you", "confidence": 0.8}')["text"] == "I love you"
    assert sign_reader.parse_reading('{"text": "banana", "confidence": 0.95}')["text"] == ""
    assert sign_reader.parse_reading('{"text": "hello", "confidence": 0.4}')["text"] == ""
    assert sign_reader.parse_reading("not json") == {"text": "", "confidence": 0.0}


def test_transcript_grows_once_per_sign():
    assert sign_reader.extend_transcript("", "hello") == ("Hello.", "Hello.")
    assert sign_reader.extend_transcript("Hello.", "thank you") == ("Hello. Thank you.", "Thank you.")
    assert sign_reader.extend_transcript("Hello. Thank you.", "thank you") == ("Hello. Thank you.", "")
    assert sign_reader.extend_transcript("Hello.", "") == ("Hello.", "")


def test_sign_reading_survives_a_failed_provider():
    reading = run(sign_reader.read_sign([(b"frame", "image/jpeg")]))
    assert (reading["text"], reading["provider"], reading["experimental"]) == ("", None, True)
