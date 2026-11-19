import os

DEEPGRAM_API = "https://api.deepgram.com/v1"
MINIMAX_API = "https://api.minimax.io/v1"
ELEVENLABS_API = "https://api.elevenlabs.io/v1"
MAX_TEXT = 600
MAX_AUDIO_BYTES = 10 * 1024 * 1024

KEYS = {"elevenlabs": "ELEVENLABS_API_KEY", "deepgram": "DEEPGRAM_API_KEY", "minimax": "MINIMAX_API_KEY"}
DEFAULT_ORDER = ["minimax", "deepgram", "elevenlabs"]


class SpeechError(Exception):
    pass


def configured() -> bool:
    return any(os.getenv(key) for key in KEYS.values())


def voices() -> list[str]:
    available = [name for name in DEFAULT_ORDER if os.getenv(KEYS[name])]
    choice = os.getenv("SPEECH_VOICE", "").strip().lower()
    if choice in available:
        available.remove(choice)
        available.insert(0, choice)
    return available


def provider() -> str:
    return next(iter(voices()), "device")


def transcriber() -> str | None:
    if os.getenv("DEEPGRAM_API_KEY"):
        return "deepgram"
    return "elevenlabs" if os.getenv("ELEVENLABS_API_KEY") else None


async def _speak_minimax(text: str) -> bytes:
    import httpx

    payload = {
        "model": os.getenv("MINIMAX_TTS_MODEL", "speech-2.8-turbo"),
        "text": text,
        "stream": False,
        "language_boost": "auto",
        "output_format": "hex",
        "voice_setting": {
            "voice_id": os.getenv("MINIMAX_VOICE_ID", "English_expressive_narrator"),
            "speed": 1, "vol": 1, "pitch": 0,
        },
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=4.0)) as client:
        response = await client.post(
            f"{MINIMAX_API}/t2a_v2",
            headers={"Authorization": f"Bearer {os.environ['MINIMAX_API_KEY']}"},
            json=payload,
        )
        response.raise_for_status()
    result = response.json()
    if result.get("base_resp", {}).get("status_code", 0) != 0:
        raise ValueError("The voice service returned an unsuccessful status")
    audio = bytes.fromhex(result.get("data", {}).get("audio", ""))
    if not audio:
        raise ValueError("The voice service returned no audio")
    return audio


async def _speak_deepgram(text: str) -> bytes:
    import httpx

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
        response = await client.post(
            f"{DEEPGRAM_API}/speak",
            params={"model": os.getenv("DEEPGRAM_VOICE_MODEL", "aura-asteria-en")},
            headers={"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"},
            json={"text": text},
        )
        response.raise_for_status()
    return response.content


async def _speak_elevenlabs(text: str) -> bytes:
    import httpx

    voice = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0)) as client:
        response = await client.post(
            f"{ELEVENLABS_API}/text-to-speech/{voice}",
            params={"output_format": "mp3_44100_64"},
            headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
            json={"text": text, "model_id": os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")},
        )
        response.raise_for_status()
    return response.content


SPEAKERS = {"minimax": _speak_minimax, "deepgram": _speak_deepgram, "elevenlabs": _speak_elevenlabs}


async def synthesize(text: str) -> bytes:
    failure: Exception | None = None
    for name in voices():
        try:
            return await SPEAKERS[name](text[:MAX_TEXT])
        except Exception as error:
            failure = error
    if failure is not None:
        raise SpeechError(f"The voice service failed: {type(failure).__name__}") from failure
    raise SpeechError("No voice service is configured")


async def _hear_deepgram(audio: bytes, mime: str) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0)) as client:
        response = await client.post(
            f"{DEEPGRAM_API}/listen",
            params={"model": os.getenv("DEEPGRAM_STT_MODEL", "nova-3"), "smart_format": "true"},
            headers={
                "Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}",
                "Content-Type": mime or "application/octet-stream",
            },
            content=audio,
        )
        response.raise_for_status()
    channels = response.json().get("results", {}).get("channels", [])
    if channels and channels[0].get("alternatives"):
        return (channels[0]["alternatives"][0].get("transcript") or "").strip()
    return ""


async def _hear_elevenlabs(audio: bytes, mime: str) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=4.0)) as client:
        response = await client.post(
            f"{ELEVENLABS_API}/speech-to-text",
            headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
            data={"model_id": os.getenv("ELEVENLABS_STT_MODEL", "scribe_v1")},
            files={"file": ("speech", audio, mime)},
        )
        response.raise_for_status()
    return (response.json().get("text") or "").strip()


async def transcribe(audio: bytes, mime: str) -> str:
    failure: Exception | None = None
    if os.getenv("DEEPGRAM_API_KEY"):
        try:
            return await _hear_deepgram(audio, mime)
        except Exception as error:
            failure = error
    if os.getenv("ELEVENLABS_API_KEY"):
        try:
            return await _hear_elevenlabs(audio, mime)
        except Exception as error:
            failure = error
    if failure is not None:
        raise SpeechError(f"Transcription failed: {type(failure).__name__}") from failure
    raise SpeechError("No transcription service is configured")
