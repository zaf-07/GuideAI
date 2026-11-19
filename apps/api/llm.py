import base64
import os

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

KEYS = {"gemini": "GEMINI_API_KEY", "minimax": "MINIMAX_API_KEY", "groq": "GROQ_API_KEY"}
DEFAULT_ORDER = "gemini,minimax,groq"


def configured_providers() -> list[str]:
    order = [name.strip() for name in os.getenv("VISION_PROVIDERS", DEFAULT_ORDER).split(",")]
    return [name for name in order if name in KEYS and os.getenv(KEYS[name])]


def configured() -> bool:
    return bool(configured_providers())


def model(provider: str | None = None) -> str | None:
    provider = provider or next(iter(configured_providers()), None)
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL") or "gemini-flash-lite-latest"
    if provider == "minimax":
        return os.getenv("MINIMAX_MODEL") or "MiniMax-M3.1-Flash"
    if provider == "groq":
        return os.getenv("GROQ_VISION_MODEL") or "qwen/qwen3.8-27b"
    return None


def image_part(image: bytes, mime: str) -> dict:
    return {"inlineData": {"mimeType": mime, "data": base64.b64encode(image).decode("ascii")}}


async def _gemini(parts: list[dict], system: str, json_mode: bool, timeout: float) -> str:
    import httpx

    config: dict[str, object] = {"temperature": 0.2, "maxOutputTokens": 1024}
    if json_mode:
        config["responseMimeType"] = "application/json"
    payload: dict[str, object] = {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=4.0)) as client:
        response = await client.post(
            GEMINI_URL.format(model=model("gemini")),
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
            json=payload,
        )
        response.raise_for_status()
    reply = response.json()["candidates"][0]["content"]["parts"]
    text = " ".join(part["text"].strip() for part in reply if part.get("text") and not part.get("thought"))
    if not text:
        raise ValueError("The model returned no text")
    return text


def _chat_content(parts: list[dict]) -> list[dict]:
    content: list[dict] = []
    for part in parts:
        if "text" in part:
            content.append({"type": "text", "text": part["text"]})
        elif "inlineData" in part:
            item = part["inlineData"]
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{item['mimeType']};base64,{item['data']}"},
            })
    return content


async def _chat(provider: str, parts: list[dict], system: str, json_mode: bool, timeout: float) -> str:
    import httpx

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": _chat_content(parts)})
    payload: dict[str, object] = {"model": model(provider), "messages": messages, "max_completion_tokens": 1024}
    if provider == "minimax":
        url = os.getenv("MINIMAX_API_URL", MINIMAX_URL)
        payload["reasoning_effort"] = os.getenv("MINIMAX_REASONING_EFFORT", "low")
    else:
        url = os.getenv("GROQ_API_URL", GROQ_URL)
        payload["temperature"] = 0.2
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=4.0)) as client:
        response = await client.post(
            url, headers={"Authorization": f"Bearer {os.environ[KEYS[provider]]}"}, json=payload,
        )
        response.raise_for_status()
    text = (response.json()["choices"][0]["message"].get("content") or "").strip()
    if not text:
        raise ValueError("The model returned no text")
    return text


async def ask(provider: str, parts: list[dict], system: str = "", json_mode: bool = False,
              timeout: float = 10.0) -> str:
    if provider == "gemini":
        return await _gemini(parts, system, json_mode, timeout)
    if provider in ("minimax", "groq"):
        return await _chat(provider, parts, system, json_mode, timeout)
    raise ValueError(f"Unknown provider: {provider}")


async def complete(parts: list[dict], system: str = "", json_mode: bool = False, timeout: float = 10.0) -> str:
    failure: Exception | None = None
    for provider in configured_providers():
        try:
            return await ask(provider, parts, system=system, json_mode=json_mode, timeout=timeout)
        except Exception as error:
            failure = error
    if failure is not None:
        raise failure
    raise RuntimeError("No language model is configured")
