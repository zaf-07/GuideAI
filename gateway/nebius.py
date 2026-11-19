"""Nebius client.

Two properties matter more than anything else here, and both are latency:

* One `AsyncClient` with HTTP/2 and a connection pool, opened in the app's
  lifespan and held for the process lifetime. A cold POST costs 150-300ms in
  DNS, TLS and connection setup, every frame, which alone blows the budget.
* `stream=True` always, relaying each delta the instant it arrives. Buffering
  server-side turns 400ms of perceived latency into 1500ms.

The API key never leaves this process; the app authenticates as its device.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

import httpx

import config

_client: httpx.AsyncClient | None = None


class NebiusError(RuntimeError):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


async def open_client() -> None:
    """Called once from the lifespan handler."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=config.NEBIUS_BASE_URL,
            http2=True,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def frame_data_url(jpeg: bytes) -> str:
    """Nebius is OpenAI-compatible, so a frame travels as a data URL part."""
    return f"data:image/jpeg;base64,{base64.b64encode(jpeg).decode('ascii')}"


@dataclass
class StreamStats:
    """What the structured log line needs. You cannot tune what you cannot see."""

    model: str
    ttft_ms: float | None = None
    duration_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    text: str = field(default="")

    @property
    def cost_usd(self) -> float:
        return config.estimate_cost(self.input_tokens, self.output_tokens)


def build_messages(system_prompt: str, jpeg: bytes, question: str | None = None) -> list[dict]:
    content: list[dict] = [{"type": "image_url", "image_url": {"url": frame_data_url(jpeg)}}]
    if question:
        content.append({"type": "text", "text": question})
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


async def stream_completion(
    *,
    model: str,
    messages: list[dict],
    max_tokens: int,
    stats: StreamStats,
) -> AsyncIterator[str]:
    """Yield text deltas as they arrive.

    `stats` is filled in as the stream proceeds, so a caller that aborts
    early still has usable timing and token numbers to log.
    """
    if _client is None:
        raise NebiusError("Nebius client is not open", status=503)
    key = config.api_key()
    if not key:
        raise NebiusError("NEBIUS_API_KEY is not set on this server", status=503)

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
        # Ask for usage on the final chunk so cost is measured, not guessed.
        "stream_options": {"include_usage": True},
    }
    started = time.perf_counter()
    try:
        async with _client.stream(
            "POST",
            "/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {key}"},
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread())[:300].decode("utf-8", "replace")
                # An unknown model must fail loudly rather than silently
                # falling back to something that speaks differently.
                raise NebiusError(f"Nebius error {response.status_code}: {body}", status=502)

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue

                usage = chunk.get("usage")
                if isinstance(usage, dict):
                    stats.input_tokens = int(usage.get("prompt_tokens") or stats.input_tokens)
                    stats.output_tokens = int(usage.get("completion_tokens") or stats.output_tokens)

                for choice in chunk.get("choices") or []:
                    delta = (choice.get("delta") or {}).get("content")
                    if not delta:
                        continue
                    if stats.ttft_ms is None:
                        stats.ttft_ms = (time.perf_counter() - started) * 1000
                    stats.text += delta
                    yield delta
    except httpx.HTTPError as error:
        raise NebiusError(f"Nebius unreachable: {error}") from error
    finally:
        stats.duration_ms = (time.perf_counter() - started) * 1000
