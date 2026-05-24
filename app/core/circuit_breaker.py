"""
Async circuit breaker for protecting against cascading LLM failures.

States:
    CLOSED   — calls pass through normally.
    OPEN     — calls short-circuit with `CircuitOpenError` for `recovery_seconds`.
    HALF_OPEN — a single trial call is permitted; success closes the circuit,
                failure re-opens it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when the circuit is open and a call is blocked."""


@dataclass
class CircuitBreaker:
    """Single-instance circuit breaker. Not safe across processes."""

    failure_threshold: int = 5
    recovery_seconds: float = 60.0

    _failures: int = 0
    _opened_at: float = 0.0
    _state: State = State.CLOSED
    _lock: asyncio.Lock | None = None

    def _ensure_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def state(self) -> State:
        # Auto-transition OPEN → HALF_OPEN once recovery_seconds has elapsed.
        if self._state is State.OPEN and (time.monotonic() - self._opened_at) >= self.recovery_seconds:
            self._state = State.HALF_OPEN
        return self._state

    async def call(self, fn: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        """Invoke `fn` through the breaker. Raises `CircuitOpenError` if open."""
        lock = self._ensure_lock()
        async with lock:
            current = self.state
            if current is State.OPEN:
                raise CircuitOpenError(
                    f"Circuit open — failed {self._failures} consecutive times."
                )

        try:
            result = await fn(*args, **kwargs)
        except Exception:
            async with lock:
                self._on_failure()
            raise

        async with lock:
            self._on_success()
        return result

    def _on_success(self) -> None:
        if self._state in (State.HALF_OPEN, State.OPEN):
            logger.info("Circuit closed after successful trial call.")
        self._failures = 0
        self._state = State.CLOSED

    def _on_failure(self) -> None:
        self._failures += 1
        if self._state is State.HALF_OPEN or self._failures >= self.failure_threshold:
            self._state = State.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                f"Circuit OPEN (failures={self._failures}, "
                f"recovery_in={self.recovery_seconds}s)"
            )

    def reset(self) -> None:
        """Force-reset to CLOSED state. Intended for tests."""
        self._failures = 0
        self._opened_at = 0.0
        self._state = State.CLOSED
