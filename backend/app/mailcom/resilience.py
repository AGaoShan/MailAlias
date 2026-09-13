"""容错：重试、熔断、令牌桶限流。"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .errors import MailComError, MailComRateLimitedError

T = TypeVar("T")


class TokenBucket:
    def __init__(self, rate: float, capacity: float | None = None) -> None:
        self.rate = rate
        self.capacity = capacity or rate
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                await asyncio.sleep((tokens - self._tokens) / self.rate)


class CircuitBreaker:
    def __init__(self, fail_threshold: int, cooldown: float) -> None:
        self.fail_threshold = fail_threshold
        self.cooldown = cooldown
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        return not self.allow()

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.monotonic() - self._opened_at >= self.cooldown:
            self._opened_at = None
            self._failures = 0
            return True
        return False

    def retry_after(self) -> float:
        if self._opened_at is None:
            return 0.0
        return max(0.0, self.cooldown - (time.monotonic() - self._opened_at))

    def on_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.fail_threshold:
            self._opened_at = time.monotonic()


class CircuitOpenError(MailComError):
    code = "CIRCUIT_OPEN"
    http_status = 503

    def __init__(self, message: str, retry_after: float = 0.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


async def with_retry(
    factory: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> T:
    """指数退避重试，带抖动。4xx（除 429）不重试。"""
    attempt = 0
    while True:
        try:
            return await factory()
        except MailComError as exc:
            attempt += 1
            if not exc.retryable or attempt >= max_attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1)) * (0.5 + random.random())
            await asyncio.sleep(delay)


class CircuitBreakerRegistry:
    def __init__(self, fail_threshold: int, cooldown: float) -> None:
        self._fail_threshold = fail_threshold
        self._cooldown = cooldown
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, key: str) -> CircuitBreaker:
        breaker = self._breakers.get(key)
        if breaker is None:
            breaker = CircuitBreaker(self._fail_threshold, self._cooldown)
            self._breakers[key] = breaker
        return breaker


class WriteRateLimiter:
    """写操作串行化 + 强制间隔，降低风控概率。"""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}

    def lock(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def wait(self, key: str) -> None:
        last = self._last.get(key)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
        self._last[key] = time.monotonic()


__all__ = [
    "TokenBucket",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitBreakerRegistry",
    "WriteRateLimiter",
    "with_retry",
    "MailComRateLimitedError",
]
