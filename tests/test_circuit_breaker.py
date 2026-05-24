import time

import pytest

from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError, State


async def _ok():
    return "ok"


async def _boom():
    raise RuntimeError("upstream failed")


@pytest.mark.asyncio
async def test_closed_passes_calls_through():
    cb = CircuitBreaker()
    assert await cb.call(_ok) == "ok"
    assert cb.state is State.CLOSED


@pytest.mark.asyncio
async def test_opens_after_threshold_failures():
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=60)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(_boom)
    assert cb.state is State.OPEN


@pytest.mark.asyncio
async def test_open_short_circuits_without_calling_fn():
    cb = CircuitBreaker(failure_threshold=1, recovery_seconds=60)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    assert cb.state is State.OPEN

    called = {"hit": False}

    async def _should_not_run():
        called["hit"] = True
        return "x"

    with pytest.raises(CircuitOpenError):
        await cb.call(_should_not_run)
    assert called["hit"] is False


@pytest.mark.asyncio
async def test_half_open_after_recovery():
    cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.01)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    assert cb.state is State.OPEN

    time.sleep(0.02)
    assert cb.state is State.HALF_OPEN


@pytest.mark.asyncio
async def test_half_open_success_closes_circuit():
    cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.01)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    time.sleep(0.02)
    result = await cb.call(_ok)
    assert result == "ok"
    assert cb.state is State.CLOSED


@pytest.mark.asyncio
async def test_half_open_failure_reopens_circuit():
    cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.01)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    time.sleep(0.02)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    assert cb.state is State.OPEN


@pytest.mark.asyncio
async def test_reset_returns_to_closed():
    cb = CircuitBreaker(failure_threshold=1, recovery_seconds=60)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    cb.reset()
    assert cb.state is State.CLOSED
    assert await cb.call(_ok) == "ok"
