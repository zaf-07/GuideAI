"""Prompts.

NARRATION_SYSTEM_PROMPT is byte-identical on every call so Nebius' prompt
caching can hit. Do not reformat it, and do not interpolate anything into it.

Its last three lines are load-bearing safety, not style: the model is barred
from ever reporting an absence of obstacles, because absence of detection is
not detection of absence, and a blind user stepping forward on "path is
clear" is the failure this whole app exists to avoid.
"""

NARRATION_SYSTEM_PROMPT = """You describe camera frames for a blind user who is walking.
Reply in at most 12 words, as fragments, most important first.
Name only: obstacles in the path, doorways, stairs, people,
signage text, and changes in floor surface.
Give direction as a clock position and distance in meters when visible.
Never say the path is clear, safe, empty, or free of obstacles.
Never mention image quality, lighting, or that you are an AI.
If the frame shows nothing worth reporting, reply exactly: SKIP"""

DIALOGUE_SYSTEM_PROMPT = """You answer a blind user's spoken question about the camera frame.
Answer in at most 30 words, plainly, most important first.
Give direction as a clock position and distance in meters when visible.
Answer only what was asked.
Never say the path is clear, safe, empty, or free of obstacles.
Never mention image quality, lighting, or that you are an AI."""

# Spoken nothing. Most corridor frames should return this, and that is
# correct: constant chatter is the top complaint about assistive vision apps.
SKIP_TOKEN = "SKIP"


class SkipGate:
    """Withholds narration deltas only while the reply could still be SKIP.

    SKIP arrives as ordinary streamed text, so it cannot be recognised until
    enough of it has arrived. Buffering the whole reply to check would cost
    the streaming latency the design exists to protect, so this holds deltas
    only while the text so far is still a prefix of SKIP, then releases
    everything at once and passes the rest straight through.

    In practice that is a delay of one or two tokens on a speaking frame, and
    silence on a skipped one.
    """

    def __init__(self, token: str = SKIP_TOKEN) -> None:
        self._token = token
        self._buffer = ""
        self._released = False

    def feed(self, delta: str) -> str:
        """Return the text that is safe to send now; may be empty."""
        if self._released:
            return delta
        self._buffer += delta
        stripped = self._buffer.lstrip()
        if not stripped:
            return ""
        if len(stripped) <= len(self._token) and self._token.startswith(stripped):
            return ""
        self._released = True
        out, self._buffer = self._buffer, ""
        return out

    @property
    def is_skip(self) -> bool:
        """True only for a reply that is exactly SKIP and nothing else."""
        return not self._released and self._buffer.strip() == self._token

    def flush(self) -> str:
        """Anything still held at the end of a non-SKIP reply."""
        if self._released or self.is_skip:
            return ""
        out, self._buffer = self._buffer, ""
        self._released = True
        return out
