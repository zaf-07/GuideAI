"""Per-device token ceiling.

The layered rate limits bound request *frequency*. They do not bound spend:
a client within its rate can still burn credits indefinitely. This adds the
missing dimension, a rolling hourly token budget per device.
"""

from __future__ import annotations

import threading
import time
from collections import deque

import config

WINDOW_SECONDS = 3600


class TokenBudget:
    def __init__(self, tokens_per_hour: int | None = None) -> None:
        self._limit = tokens_per_hour if tokens_per_hour is not None else config.DEVICE_TOKENS_PER_HOUR
        self._spend: dict[str, deque[tuple[float, int]]] = {}
        self._lock = threading.Lock()

    def _prune(self, entries: deque[tuple[float, int]], now: float) -> None:
        while entries and now - entries[0][0] > WINDOW_SECONDS:
            entries.popleft()

    def spent(self, device_id: str, now: float | None = None) -> int:
        now = now if now is not None else time.time()
        with self._lock:
            entries = self._spend.get(device_id)
            if not entries:
                return 0
            self._prune(entries, now)
            return sum(count for _, count in entries)

    def allows(self, device_id: str, now: float | None = None) -> bool:
        return self.spent(device_id, now) < self._limit

    def record(self, device_id: str, tokens: int, now: float | None = None) -> None:
        if tokens <= 0:
            return
        now = now if now is not None else time.time()
        with self._lock:
            entries = self._spend.setdefault(device_id, deque())
            self._prune(entries, now)
            entries.append((now, tokens))

    def clear(self) -> None:
        with self._lock:
            self._spend.clear()


budget = TokenBudget()
