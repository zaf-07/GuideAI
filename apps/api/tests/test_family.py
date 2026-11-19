from unittest import mock

import pytest

import family as family_store
import messaging
import speech
from conftest import run
from family import Family


def test_contacts_are_normalised_and_scoped_to_their_owner():
    family = Family(":memory:")
    assert family.add_contact("alice", "Mom", "+1 (415) 555-0100") == {"name": "Mom", "phone": "14155550100"}
    assert family.contacts("alice") == [{"name": "Mom", "phone": "14155550100"}]
    assert family.contacts("bob") == []
    assert family.find_contact("bob", "tell mom where I am") is None
    family.remove_contact("bob", "mom")
    assert len(family.contacts("alice")) == 1
    family.remove_contact("alice", "mom")
    assert family.contacts("alice") == []


def test_contact_names_are_matched_by_sound_but_not_by_accident():
    family = Family(":memory:")
    family.add_contact("s", "Mom", "+14155550100")
    family.add_contact("s", "Zack", "+14155550111")
    assert family.find_contact("s", "tell mom where I am")["name"] == "Mom"
    assert family.find_contact("s", "message Zach that I am late")["name"] == "Zack"
    assert family.find_contact("s", "tell my moment") is None
    assert family.find_contact("s", "what is in front of me") is None


def test_bad_numbers_and_too_many_contacts_are_refused(monkeypatch):
    family = Family(":memory:")
    with pytest.raises(ValueError):
        family.add_contact("s", "Bad", "12")
    with pytest.raises(ValueError):
        family.add_contact("s", " ", "+14155550100")
    monkeypatch.setattr(family_store, "MAX_CONTACTS", 2)
    family.add_contact("s", "One", "+14155550101")
    family.add_contact("s", "Two", "+14155550102")
    with pytest.raises(ValueError):
        family.add_contact("s", "Three", "+14155550103")
    assert family.add_contact("s", "Two", "+14155550199")["phone"] == "14155550199"
    assert family.add_contact("other", "Three", "+14155550103")["name"] == "Three"


def test_places_are_scoped_to_their_owner():
    family = Family(":memory:")
    family.save_place("alice", "Home", "161, Mission Falls Lane", 37.4845, -121.9273)
    assert family.place("alice", "home")["label"] == "161, Mission Falls Lane"
    assert family.place("bob", "home") is None
    assert [place["name"] for place in family.places("alice")] == ["home"]
    family.remove_place("alice", "home")
    assert family.places("alice") == []


def test_contacts_survive_a_restart(tmp_path):
    path = str(tmp_path / "family.sqlite3")
    Family(path).add_contact("s", "Mom", "+14155550100")
    assert Family(path).contacts("s") == [{"name": "Mom", "phone": "14155550100"}]


def test_whatsapp_link_and_configuration(monkeypatch):
    assert not messaging.configured()
    assert messaging.whatsapp_link("14155550100", "I am near home") == "https://wa.me/14155550100?text=I%20am%20near%20home"
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    assert messaging.configured()


def test_voice_falls_back_to_the_device_without_a_service(monkeypatch):
    assert not speech.configured()
    assert speech.provider() == "device"
    assert speech.transcriber() is None
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el")
    assert speech.provider() == "deepgram"
    assert speech.transcriber() == "deepgram"
    monkeypatch.setenv("MINIMAX_API_KEY", "mm")
    assert speech.provider() == "minimax"
    monkeypatch.setenv("SPEECH_VOICE", "elevenlabs")
    assert speech.voices() == ["elevenlabs", "minimax", "deepgram"]


def test_voice_audio_is_decoded_and_the_next_voice_is_tried(monkeypatch):
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"base_resp": {"status_code": 0}, "data": {"audio": "494433"}}
    client = mock.AsyncMock()
    client.__aenter__.return_value.post.return_value = response
    monkeypatch.setenv("MINIMAX_API_KEY", "secret")
    with mock.patch("httpx.AsyncClient", return_value=client):
        assert run(speech.synthesize("Guide me")) == b"ID3"

    async def broken(text):
        raise TimeoutError()

    async def works(text):
        return b"mp3"

    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg")
    monkeypatch.setitem(speech.SPEAKERS, "minimax", broken)
    monkeypatch.setitem(speech.SPEAKERS, "deepgram", works)
    assert run(speech.synthesize("Guide me")) == b"mp3"
    monkeypatch.delenv("MINIMAX_API_KEY")
    monkeypatch.delenv("DEEPGRAM_API_KEY")
    with pytest.raises(speech.SpeechError):
        run(speech.synthesize("Guide me"))
