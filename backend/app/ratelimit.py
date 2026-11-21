"""In-process token buckets (same approach as Flowbench): per visitor and site-wide.
Consistent on a single Cloud Run instance; the site-wide bucket is the hard guard."""

from __future__ import annotations

import threading
import time

MAX_BUCKETS = 20_000
IDLE_EVICT_S = 900.0


class RateLimiter:
    def __init__(self, rate_per_min: float, capacity: float):
        self._rate = rate_per_min / 60.0
        self._capacity = capacity
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._buckets) >= MAX_BUCKETS:
                for k in [k for k, (_, ts) in self._buckets.items() if now - ts > IDLE_EVICT_S]:
                    del self._buckets[k]
            tokens, ts = self._buckets.get(key, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - ts) * self._rate)
            ok = tokens >= 1.0
            self._buckets[key] = (tokens - 1.0 if ok else tokens, now)
            return ok

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
