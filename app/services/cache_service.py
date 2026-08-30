"""Cache abstraction with in-memory and Redis backends."""
from __future__ import annotations

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from typing import Any

from app.config import Config
from app.logging_config import get_logger

logger = get_logger(__name__)


class CacheBackend(ABC):
    """Abstract cache backend."""

    @abstractmethod
    async def get(self, key: str) -> Any | None: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class MemoryCache(CacheBackend):
    """Thread-safe in-memory cache with TTL for development."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if asyncio.get_event_loop().time() > expires_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int) -> None:
        expires_at = asyncio.get_event_loop().time() + ttl
        async with self._lock:
            self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def close(self) -> None:
        async with self._lock:
            self._store.clear()


class RedisCache(CacheBackend):
    """Redis-backed cache for production."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis: Any | None = None

    async def _get_redis(self) -> Any:
        if self._redis is None:
            import redis.asyncio as aioredis

            self._redis = await aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def get(self, key: str) -> Any | None:
        redis = await self._get_redis()
        raw = await redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        redis = await self._get_redis()
        await redis.setex(key, ttl, json.dumps(value, default=str))

    async def delete(self, key: str) -> None:
        redis = await self._get_redis()
        await redis.delete(key)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()


class CacheService:
    """High-level cache service with key namespacing and serialization."""

    def __init__(self, backend: CacheBackend, default_ttl: int) -> None:
        self.backend = backend
        self.default_ttl = default_ttl

    @classmethod
    def from_config(cls, config: Config) -> CacheService:
        if config.redis_url:
            backend: CacheBackend = RedisCache(config.redis_url)
        else:
            backend = MemoryCache()
        return cls(backend=backend, default_ttl=config.cache_ttl_seconds)

    def _make_key(self, namespace: str, *parts: str) -> str:
        raw = ":".join([namespace, *parts])
        # Keep keys reasonably short and safe.
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(self, namespace: str, *parts: str) -> Any | None:
        key = self._make_key(namespace, *parts)
        return await self.backend.get(key)

    async def set(
        self, *, value: Any, namespace: str, parts: tuple[str, ...], ttl: int | None = None
    ) -> None:
        key = self._make_key(namespace, *parts)
        await self.backend.set(key, value, ttl or self.default_ttl)

    async def delete(self, namespace: str, *parts: str) -> None:
        key = self._make_key(namespace, *parts)
        await self.backend.delete(key)

    async def close(self) -> None:
        await self.backend.close()
