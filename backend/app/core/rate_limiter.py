from __future__ import annotations

import time
from dataclasses import dataclass, field

import redis.asyncio as aioredis

from app.config import settings
from app.core.logging import logger


@dataclass
class _InMemoryStore:
    _data: dict[str, list[float]] = field(default_factory=dict)

    def trim(self, key: str, window_start: float) -> None:
        if key in self._data:
            self._data[key] = [t for t in self._data[key] if t > window_start]

    def count(self, key: str) -> int:
        return len(self._data.get(key, []))

    def add(self, key: str, now: float) -> None:
        if key not in self._data:
            self._data[key] = []
        self._data[key].append(now)


class RateLimiter:
    """Redis-backed rate limiter with in-memory fallback.

    Uses a sliding-window counter per key. When Redis is unreachable
    (e.g. dev without the container), degrades gracefully to in-memory.
    This means multi-worker deployments MUST have Redis to enforce
    accurate cross-worker limits.
    """

    def __init__(self, window: int = 60, max_requests: int = 30) -> None:
        self.window = window
        self.max_requests = max_requests
        self._memory = _InMemoryStore()
        self._redis: aioredis.Redis | None = None
        self._redis_ok = False
        self._warned = False

    def _get_redis(self) -> aioredis.Redis | None:
        if self._redis_ok:
            return self._redis
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                    decode_responses=True,
                )
            except Exception:
                return None
        return self._redis

    async def _check_redis_async(self) -> bool:
        r = self._get_redis()
        if r is None:
            return False
        try:
            await r.ping()
            self._redis_ok = True
            return True
        except Exception:
            self._redis_ok = False
            return False

    def _check_redis_sync(self) -> bool:
        r = self._redis
        if r is None:
            return False
        try:
            r.ping()
            self._redis_ok = True
            return True
        except Exception:
            self._redis_ok = False
            return False

    def _warn_fallback(self, key: str) -> None:
        if not self._warned:
            logger.warning("Redis unavailable — rate limiter falling back to in-memory store")
            self._warned = True

    # ── sync path (used by sync endpoints like /auth/login, /chat/ask) ──

    def check(self, key: str) -> None:
        now = time.time()
        window_start = now - self.window

        if self._redis is not None and self._check_redis_sync():
            try:
                pipe = self._redis.pipeline()
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zcard(key)
                pipe.zadd(key, {str(now): now})
                pipe.expire(key, self.window)
                results = pipe.execute()
                count = results[1]  # zcard result
                if count >= self.max_requests:
                    raise RateLimitExceeded()
                return
            except RateLimitExceeded:
                raise
            except Exception:
                self._redis_ok = False

        self._warn_fallback(key)
        self._memory.trim(key, window_start)
        if self._memory.count(key) >= self.max_requests:
            raise RateLimitExceeded()
        self._memory.add(key, now)

    # ── async path (reserved for future async endpoints) ──

    async def check_async(self, key: str) -> None:
        now = time.time()
        window_start = now - self.window

        if await self._check_redis_async():
            try:
                pipe = self._redis.pipeline()
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zcard(key)
                pipe.zadd(key, {str(now): now})
                pipe.expire(key, self.window)
                results = await pipe.execute()
                count = results[1]
                if count >= self.max_requests:
                    raise RateLimitExceeded()
                return
            except RateLimitExceeded:
                raise
            except Exception:
                self._redis_ok = False

        self._warn_fallback(key)
        self._memory.trim(key, window_start)
        if self._memory.count(key) >= self.max_requests:
            raise RateLimitExceeded()
        self._memory.add(key, now)


class RateLimitExceeded(Exception):
    pass
