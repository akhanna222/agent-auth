"""Redis connection pool — with in-memory fallback for development."""
from __future__ import annotations

import time
from typing import Any


class InMemoryCache:
    """Simple in-memory cache that mimics Redis interface for dev use."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}

    def _check_expiry(self, key: str) -> bool:
        if key in self._expiry and time.time() > self._expiry[key]:
            del self._store[key]
            del self._expiry[key]
            return True
        return False

    async def get(self, key: str) -> Any | None:
        self._check_expiry(key)
        return self._store.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self._store[key] = value
        if ex:
            self._expiry[key] = time.time() + ex

    async def setex(self, key: str, ttl: int, value: Any) -> None:
        self._store[key] = value
        self._expiry[key] = time.time() + ttl

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._expiry.pop(key, None)

    async def exists(self, key: str) -> bool:
        self._check_expiry(key)
        return key in self._store

    async def incr(self, key: str) -> int:
        self._check_expiry(key)
        val = self._store.get(key, 0)
        val = int(val) + 1
        self._store[key] = val
        return val

    async def expire(self, key: str, ttl: int) -> None:
        self._expiry[key] = time.time() + ttl

    async def ping(self) -> bool:
        return True


# Global cache instance
cache = InMemoryCache()
