import asyncio
import time

import pytest

from app.core.rate_limiter import TokenBucket


@pytest.mark.asyncio
async def test_initial_burst_uses_capacity_without_blocking():
    bucket = TokenBucket(rate=1.0, capacity=3.0)
    start = time.monotonic()
    for _ in range(3):
        await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1, f"initial burst should not block, took {elapsed}s"


@pytest.mark.asyncio
async def test_acquire_blocks_until_refill():
    bucket = TokenBucket(rate=10.0, capacity=1.0)
    await bucket.acquire()  # consume the only token
    start = time.monotonic()
    await bucket.acquire()  # must wait ~0.1s
    elapsed = time.monotonic() - start
    assert 0.05 <= elapsed <= 0.5, f"expected ~0.1s wait, got {elapsed}s"


@pytest.mark.asyncio
async def test_concurrent_acquires_serialized():
    """Two concurrent acquires on a 1-capacity, 10/sec bucket are spaced ~0.1s."""
    bucket = TokenBucket(rate=10.0, capacity=1.0)
    await bucket.acquire()  # drain

    start = time.monotonic()
    await asyncio.gather(bucket.acquire(), bucket.acquire())
    elapsed = time.monotonic() - start
    # Two refills needed (we already drained capacity). 2 * 0.1s = 0.2s minimum.
    assert elapsed >= 0.18, f"two acquires should take >=0.18s, got {elapsed}s"
