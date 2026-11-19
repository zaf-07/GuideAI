"""Device identity: one client must never be able to act as another."""

from __future__ import annotations

import hashlib

import pytest

from device_identity import DeviceAuthError, authorize, derive_device_id

SECRET = "a" * 64
DEVICE = derive_device_id(SECRET)
SESSION = "session-1"


def test_id_is_the_first_128_bits_of_the_secret_hash():
    expected = hashlib.sha256(SECRET.encode()).hexdigest()[:32]
    assert DEVICE == f"device-{expected}"


def test_a_matching_secret_authorizes():
    assert authorize(DEVICE, SESSION, SECRET) == (DEVICE, SESSION)


def test_another_devices_id_cannot_be_claimed():
    other = derive_device_id("b" * 64)
    with pytest.raises(DeviceAuthError):
        authorize(other, SESSION, SECRET)


def test_a_made_up_id_is_rejected():
    with pytest.raises(DeviceAuthError):
        authorize("device-whatever", SESSION, SECRET)


@pytest.mark.parametrize(
    "device_id, session_id, secret",
    [
        (None, SESSION, SECRET),
        (DEVICE, None, SECRET),
        (DEVICE, SESSION, None),
        (DEVICE, SESSION, "tooshort"),
        (DEVICE, SESSION, "a" * 500),
        ("x" * 200, SESSION, SECRET),
        (DEVICE, "x" * 200, SECRET),
    ],
)
def test_malformed_credentials_are_rejected(device_id, session_id, secret):
    with pytest.raises(DeviceAuthError):
        authorize(device_id, session_id, secret)


def test_an_allowlist_excludes_everyone_else(monkeypatch):
    monkeypatch.setenv("GUIDELENS_DEVICE_IDS", "device-somebodyelse")
    with pytest.raises(DeviceAuthError):
        authorize(DEVICE, SESSION, SECRET)


def test_an_empty_allowlist_allows_any_valid_device(monkeypatch):
    monkeypatch.setenv("GUIDELENS_DEVICE_IDS", "")
    assert authorize(DEVICE, SESSION, SECRET) == (DEVICE, SESSION)
