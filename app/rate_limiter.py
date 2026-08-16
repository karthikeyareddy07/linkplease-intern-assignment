"""Sliding Window Rate Limiter strictly enforcing <= 10 requests per rolling 60 seconds."""
import time
import asyncio
from collections import deque
from typing import Optional


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps = deque()
        self._lock = asyncio.Lock()
        self._pause_until: float = 0.0

    async def acquire(self):
        """
        Block until a rate-limited request token is legally available.
        Ensures that at no point do more than `max_requests` occur in any rolling `window_seconds`.
        """
        while True:
            async with self._lock:
                now = time.time()

                # 1. Respect dynamic 429 Retry-After pauses
                if now < self._pause_until:
                    sleep_duration = self._pause_until - now + 0.1
                else:
                    # 2. Evict timestamps outside the rolling window
                    while self._timestamps and self._timestamps[0] <= now - self.window_seconds:
                        self._timestamps.popleft()

                    # 3. Check if window has capacity
                    if len(self._timestamps) < self.max_requests:
                        self._timestamps.append(now)
                        return

                    # 4. Calculate wait time until oldest request leaves the rolling window
                    oldest_ts = self._timestamps[0]
                    sleep_duration = (oldest_ts + self.window_seconds) - now + 0.1

            # Sleep outside the lock so other tasks can check state
            if sleep_duration > 0:
                await asyncio.sleep(sleep_duration)

    def pause(self, seconds: float):
        """Pause the rate limiter for a specific duration (e.g. from 429 Retry-After)."""
        now = time.time()
        self._pause_until = max(self._pause_until, now + seconds)

    def reset(self):
        """Reset rate limiter state."""
        self._timestamps.clear()
        self._pause_until = 0.0


# Global mutating API rate limiter
api_rate_limiter = RateLimiter(max_requests=10, window_seconds=60.0)
