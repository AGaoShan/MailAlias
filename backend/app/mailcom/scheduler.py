"""取件调度：双层信号量 + 单账号串行 + single-flight 去重 + 令牌桶限流。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .resilience import TokenBucket

T = TypeVar("T")


class PickupScheduler:
    def __init__(
        self,
        global_limit: int,
        per_account_limit: int,
        *,
        global_qps: float = 5.0,
        account_qps: float = 1.0,
    ) -> None:
        self._global = asyncio.Semaphore(global_limit)
        self._per_account_limit = per_account_limit
        self._per_account: dict[int, asyncio.Semaphore] = {}
        self._account_locks: dict[int, asyncio.Lock] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._global_bucket = TokenBucket(global_qps)
        self._account_buckets: dict[int, TokenBucket] = {}
        self._registry_lock = asyncio.Lock()

    def _account_semaphore(self, account_id: int) -> asyncio.Semaphore:
        semaphore = self._per_account.get(account_id)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self._per_account_limit)
            self._per_account[account_id] = semaphore
        return semaphore

    def _account_bucket(self, account_id: int) -> TokenBucket:
        bucket = self._account_buckets.get(account_id)
        if bucket is None:
            bucket = TokenBucket(1.0)
            self._account_buckets[account_id] = bucket
        return bucket

    def set_account_rate(self, account_id: int, qps: float) -> None:
        self._account_buckets[account_id] = TokenBucket(qps)

    async def run(
        self,
        account_id: int,
        key: str,
        coro_factory: Callable[[], Awaitable[T]],
        *,
        account_qps: float = 1.0,
    ) -> T:
        async with self._registry_lock:
            existing = self._inflight.get(key)
            if existing is not None:
                return await asyncio.shield(existing)
            future: asyncio.Future[T] = asyncio.get_running_loop().create_future()
            self._inflight[key] = future

        try:
            await self._global_bucket.acquire()
            account_bucket = self._account_buckets.get(account_id)
            if account_bucket is None:
                account_bucket = TokenBucket(account_qps)
                self._account_buckets[account_id] = account_bucket
            await account_bucket.acquire()

            async with self._global:
                async with self._account_semaphore(account_id):
                    async with self._account_locks.setdefault(account_id, asyncio.Lock()):
                        result = await coro_factory()
            future.set_result(result)
            return result
        except Exception as exc:  # noqa: BLE001
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            self._inflight.pop(key, None)


class PickupCache:
    def __init__(self, ttl: float) -> None:
        self.ttl = ttl
        self._store: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> object | None:
        import time

        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def get_typed(self, key: str, expected: type[T]) -> T | None:
        value = self.get(key)
        if isinstance(value, expected):
            return value
        return None

    def set(self, key: str, value: object) -> None:
        import time

        self._store[key] = (time.monotonic() + self.ttl, value)

    def invalidate_prefix(self, prefix: str) -> None:
        for key in [key for key in self._store if key.startswith(prefix)]:
            self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
