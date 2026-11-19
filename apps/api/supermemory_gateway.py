"""Supermemory gateway.

GuideAI never ships the Supermemory API key to the phone. A Bearer key has
write access to every memory in the account, and anything inside an app bundle
can be extracted from it, so the key lives here and the client authenticates
as its own device. The namespace is derived from the device ID the API has
already verified, which is what stops one device reading another's memories.

API surface used (Supermemory v5; v3/v4 are deprecated and shut down on
2026-12-31):
    POST {base}/ns/{namespace}/document   ingest
    POST {base}/ns/{namespace}/search     recall
"""

from __future__ import annotations

import os
import re
from typing import Any, Iterable

import httpx

DEFAULT_BASE_URL = "https://api.supermemory.ai"

# Supermemory's documented namespace rule: ^[a-zA-Z0-9_:-]+$, max 100 chars.
_NAMESPACE_SAFE = re.compile(r"[^a-zA-Z0-9_:-]+")
_NAMESPACE_MAX = 100

# Documented ceilings, enforced here so a bad request fails locally and cheaply.
SUPPORTING_CONTEXT_MAX = 1500
DOCUMENT_ID_MAX = 255
SEARCH_LIMIT_MAX = 100

# Content is capped well below any model limit: GuideAI writes short
# observations, and an unbounded body would be a cheap way to burn credits.
CONTENT_MAX = 4000


class SupermemoryError(RuntimeError):
    """Raised when the upstream call fails or the gateway is misconfigured."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def api_key() -> str:
    return os.getenv("SUPERMEMORY_API_KEY", "").strip()


def base_url() -> str:
    return os.getenv("SUPERMEMORY_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL


def configured() -> bool:
    return bool(api_key())


def namespace_for(device_id: str) -> str:
    """Derive a stable, isolated Supermemory namespace from a verified device.

    The prefix keeps GuideAI's namespaces distinguishable if the same
    Supermemory account is ever shared with another project.
    """
    cleaned = _NAMESPACE_SAFE.sub("_", (device_id or "").strip())
    if not cleaned:
        raise SupermemoryError("A device ID is required to scope memory", status=400)
    return f"guideai_{cleaned}"[:_NAMESPACE_MAX]


def _headers() -> dict[str, str]:
    key = api_key()
    if not key:
        raise SupermemoryError("Supermemory is not configured on this server", status=503)
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def build_document(
    *,
    content: str,
    kind: str | None = None,
    document_id: str | None = None,
    supporting_context: str | None = None,
    metadata: dict[str, Any] | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """Build an ingest body, clamped to the documented field limits."""
    text = (content or "").strip()
    if not text:
        raise SupermemoryError("Nothing to remember", status=400)

    body: dict[str, Any] = {"content": text[:CONTENT_MAX], "taskType": "memory"}
    if document_id:
        body["id"] = document_id[:DOCUMENT_ID_MAX]
    if supporting_context:
        body["supportingContext"] = supporting_context[:SUPPORTING_CONTEXT_MAX]
    if date:
        body["date"] = date

    meta = {k: v for k, v in (metadata or {}).items() if isinstance(v, (str, int, float, bool))}
    if kind:
        meta["kind"] = kind
    if meta:
        body["metadata"] = meta
    return body


def build_search(
    *,
    query: str,
    limit: int = 8,
    kinds: Iterable[str] | None = None,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Build a search body.

    `include.related` is always on: the graph context is the entire reason
    GuideAI uses Supermemory rather than a plain vector store.
    """
    text = (query or "").strip()
    if not text:
        raise SupermemoryError("A query is required", status=400)

    body: dict[str, Any] = {
        "query": text,
        "limit": max(1, min(int(limit or 8), SEARCH_LIMIT_MAX)),
        "searchMode": "hybrid",
        "include": {"documents": False, "related": True, "forgotten": False},
    }
    if threshold is not None:
        body["threshold"] = max(0.0, min(float(threshold), 1.0))

    kind_list = [k for k in (kinds or []) if k]
    if kind_list:
        # Metadata keys are literal in Supermemory's filter language.
        leaves = [{"field": "kind", "operator": "eq", "value": k} for k in kind_list]
        body["filter"] = leaves[0] if len(leaves) == 1 else {"operator": "or", "operands": leaves}
    return body


def normalize_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Supermemory's response into the shape the app expects.

    In hybrid mode a result carries either `memory` or `chunk`, so branch on
    field presence rather than assuming one. Related memories arrive grouped
    as parents/children/siblings; those group names are the relation.
    """
    out: list[dict[str, Any]] = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        text = item.get("memory") or item.get("chunk") or ""
        if not text:
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        system = item.get("system") if isinstance(item.get("system"), dict) else {}

        related: list[dict[str, Any]] = []
        included = item.get("included") if isinstance(item.get("included"), dict) else {}
        groups = included.get("related") if isinstance(included.get("related"), dict) else {}
        for group, relation in (
            ("parents", "refers_to"),
            ("children", "refers_to"),
            ("siblings", "co_occurred"),
        ):
            for rel in groups.get(group) or []:
                if not isinstance(rel, dict):
                    continue
                rel_text = rel.get("memory") or rel.get("content") or rel.get("chunk") or ""
                if not rel_text:
                    continue
                related.append({"id": str(rel.get("id") or ""), "text": rel_text, "relation": relation})

        out.append(
            {
                "id": str(item.get("id") or ""),
                "text": text,
                "similarity": float(item.get("similarity") or 0.0),
                "kind": metadata.get("kind"),
                "metadata": metadata,
                "updatedAt": system.get("updatedAt"),
                "related": related,
            }
        )
    return out


async def _post(path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    url = f"{base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=body, headers=_headers())
    except httpx.HTTPError as error:
        raise SupermemoryError(f"Memory service unreachable: {error}") from error

    if response.status_code >= 400:
        # Upstream text is echoed back trimmed; it never contains the API key.
        detail = response.text[:300]
        raise SupermemoryError(f"Memory service error {response.status_code}: {detail}", status=502)
    try:
        return response.json()
    except ValueError as error:
        raise SupermemoryError("Memory service returned invalid JSON") from error


async def ingest(device_id: str, document: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
    namespace = namespace_for(device_id)
    data = await _post(f"/ns/{namespace}/document", document, timeout)
    return {"id": str(data.get("id") or ""), "status": str(data.get("status") or "unknown")}


async def search(device_id: str, body: dict[str, Any], timeout: float = 15.0) -> list[dict[str, Any]]:
    namespace = namespace_for(device_id)
    data = await _post(f"/ns/{namespace}/search", body, timeout)
    return normalize_results(data)
