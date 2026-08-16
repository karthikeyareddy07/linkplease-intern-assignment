import time
import asyncio
import pytest
from app.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_up_to_max():
    # Test rate limiter with 3 requests in 1 second window
    limiter = RateLimiter(max_requests=3, window_seconds=1.0)

    start = time.time()
    for _ in range(3):
        await limiter.acquire()
    duration = time.time() - start

    # First 3 should acquire almost instantly
    assert duration < 0.1


@pytest.mark.asyncio
async def test_rate_limiter_blocks_on_excess():
    limiter = RateLimiter(max_requests=2, window_seconds=0.5)

    start = time.time()
    await limiter.acquire()
    await limiter.acquire()

    # 3rd acquire must wait until first request is >= 0.5s old
    await limiter.acquire()
    duration = time.time() - start

    assert duration >= 0.45


@pytest.mark.asyncio
async def test_rate_limiter_pause():
    limiter = RateLimiter(max_requests=5, window_seconds=1.0)
    limiter.pause(0.3)

    start = time.time()
    await limiter.acquire()
    duration = time.time() - start

    assert duration >= 0.28
