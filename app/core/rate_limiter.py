"""
Async token-bucket rate limiter for outbound HTTP calls.

Used to throttle mutating GitHub API calls below GitHub's secondary
rate limit (~1 req/sec for writes on a single token).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """
    Refills at `rate` tokens/sec, capped at `capacity`. Each `acquire()` consumes
    one token, blocking until one is available.
    """

    rate: float = 1.0
    capacity: float = 1.0

    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: asyncio.Lock | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._tokens = self.capacity
        self._last_refill = time.monotonic()

    def _ensure_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last_refill = now

    async def acquire(self) -> None:
        """Block until a token is available, then consume one."""
        lock = self._ensure_lock()
        while True:
            async with lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                deficit = 1.0 - self._tokens
                wait_s = deficit / self.rate
            await asyncio.sleep(wait_s)
