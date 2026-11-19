"""Gateway configuration.

Model IDs live here, never in code. Hosted catalogs churn, and a silent
fallback to some other model would change what a blind user hears without
anyone noticing. An unknown model fails loudly instead.
"""

from __future__ import annotations

import os

NEBIUS_BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.studio.nebius.com/v1").rstrip("/")

# Narration is chosen on latency, not quality: it must beat a walking pace.
NARRATION_MODEL = os.getenv("NEBIUS_NARRATION_MODEL", "nvidia/Nemotron-3-Nano-Omni")

# Dialogue runs only on explicit user request, where 1-2s is acceptable.
DIALOGUE_MODEL = os.getenv("NEBIUS_DIALOGUE_MODEL", "Qwen/Qwen3-VL-32B-Instruct")

NARRATION_MAX_TOKENS = int(os.getenv("NEBIUS_NARRATION_MAX_TOKENS", "48"))
DIALOGUE_MAX_TOKENS = int(os.getenv("NEBIUS_DIALOGUE_MAX_TOKENS", "160"))

# A frame arrives as ~20KB of JPEG. The ceiling is generous enough for a
# higher-resolution dialogue frame and small enough that a malformed or
# hostile client cannot push arbitrary payloads through to a paid API.
MAX_FRAME_BYTES = int(os.getenv("GUIDELENS_MAX_FRAME_BYTES", str(512 * 1024)))

# Per-device ceiling so one looping client cannot drain the credits.
DEVICE_TOKENS_PER_HOUR = int(os.getenv("GUIDELENS_DEVICE_TOKENS_PER_HOUR", "250000"))

# Published prices per 1M tokens, used only for the cost line in the logs.
INPUT_COST_PER_MTOK = float(os.getenv("NEBIUS_INPUT_COST_PER_MTOK", "0.06"))
OUTPUT_COST_PER_MTOK = float(os.getenv("NEBIUS_OUTPUT_COST_PER_MTOK", "0.24"))


def api_key() -> str:
    return os.getenv("NEBIUS_API_KEY", "").strip()


def configured() -> bool:
    return bool(api_key())


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_COST_PER_MTOK + output_tokens * OUTPUT_COST_PER_MTOK) / 1_000_000
