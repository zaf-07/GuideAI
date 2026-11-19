"""Device-bound identity, carried forward from the prototype.

Every client generates a 256-bit secret. Its public ID is the first 128 bits
of that secret's SHA-256, so the server can verify the whole secret without
storing anything: no enrollment table, no row to steal, and no way for one
client to claim another's ID. This is the one piece of the prototype's
architecture worth keeping verbatim.

The prototype also carried a SQLite migration path for legacy IDs created
before credentials existed. There is no legacy database any more, so that
path is gone and only derived IDs are accepted.
"""

from __future__ import annotations

import hashlib
import hmac
import os

MAX_ID_LENGTH = 100
MIN_SECRET_LENGTH = 64
MAX_SECRET_LENGTH = 200


class DeviceAuthError(PermissionError):
    """Raised when a caller cannot prove the identity it claims."""


def derive_device_id(device_secret: str) -> str:
    """The only legitimate ID for a secret. Clients derive the same value."""
    digest = hashlib.sha256(device_secret.encode("utf-8")).hexdigest()
    return f"device-{digest[:32]}"


def authorize(device_id: str | None, session_id: str | None, device_secret: str | None) -> tuple[str, str]:
    """Verify a caller and return its (device_id, session_id).

    Raises DeviceAuthError rather than returning a sentinel, so a caller
    cannot forget to check and end up treating an unauthenticated request as
    authenticated.
    """
    if not device_id or not session_id:
        raise DeviceAuthError("X-Device-ID and X-Session-ID headers are required")
    if len(device_id) > MAX_ID_LENGTH or len(session_id) > MAX_ID_LENGTH:
        raise DeviceAuthError("Device and session identifiers are too long")
    if not device_secret or not MIN_SECRET_LENGTH <= len(device_secret) <= MAX_SECRET_LENGTH:
        raise DeviceAuthError("A valid X-Device-Secret header is required")

    allowed = {value.strip() for value in os.getenv("GUIDELENS_DEVICE_IDS", "").split(",") if value.strip()}
    if allowed and device_id not in allowed:
        raise DeviceAuthError("This device is not authorized")

    # compare_digest, not ==, so a wrong ID cannot be found one character at
    # a time by timing the comparison.
    if not hmac.compare_digest(device_id, derive_device_id(device_secret)):
        raise DeviceAuthError("Device ID does not match its secret")
    return device_id, session_id
