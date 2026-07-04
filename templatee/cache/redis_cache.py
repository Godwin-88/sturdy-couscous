"""
Redis-backed market data cache with in-memory L1 fallback.

Cache hierarchy
───────────────
L1  in-process TTLCache   30 s    per-uvicorn-worker, zero-latency
L2  Redis                 5 min   shared across all workers, sub-ms
L3  Redis (long-TTL)      1 hr    historical / yfinance / OpenBB data

If Redis is unreachable the cache silently degrades to L1-only; the
application keeps working, just without cross-worker sharing.

Environment variables
─────────────────────
REDIS_URL          redis://localhost:6379/0   full Redis connection string
CACHE_TTL_L1       30                         L1 TTL in seconds
CACHE_TTL_L2       300                        Redis short TTL in seconds
CACHE_TTL_L3       3600                       Redis long TTL in seconds
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import redis.asyncio as aioredis
import structlog
from cachetools import TTLCache

logger = structlog.get_logger(__name__)

# ── Configuration from environment ───────────────────────────────────────────
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
L1_TTL: int = int(os.getenv("CACHE_TTL_L1", "30"))
L2_TTL: int = int(os.getenv("CACHE_TTL_L2", "300"))
L3_TTL: int = int(os.getenv("CACHE_TTL_L3", "3600"))

_NAMESPACE = "mktdata"


def _rk(key: str) -> str:
    """Prefix a key with the global namespace."""
    return f"{_NAMESPACE}:{key}"


class RedisMarketDataCache:
    """
    Async two-level market data cache.

    Public API (all async)
    ──────────────────────
    get(key)                → Any | None
    set(key, value, ttl?)
    delete(key)
    clear_pattern(pattern?)  → int (keys deleted)
    ping()                   → bool
    stats()                  → dict
    close()
    """

    def __init__(
        self,
        redis_url: str = REDIS_URL,
        l1_ttl: int = L1_TTL,
        l2_ttl: int = L2_TTL,
        l1_maxsize: int = 512,
    ) -> None:
        self._redis_url = redis_url
        self._l2_ttl = l2_ttl

        # L1: per-process in-memory cache
        self._l1: TTLCache = TTLCache(maxsize=l1_maxsize, ttl=l1_ttl)

        # L2: Redis (lazily initialised)
        self._redis: Optional[aioredis.Redis] = None
        self._redis_ok: bool = False

        # Metrics
        self._hits_l1 = 0
        self._hits_l2 = 0
        self._misses = 0
        self._errors = 0

    # ── Internal: Redis connection ────────────────────────────────────────────

    async def _get_redis(self) -> Optional[aioredis.Redis]:
        """Return a live Redis client, or None if unavailable."""
        if self._redis is not None and self._redis_ok:
            return self._redis

        try:
            self._redis = aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await self._redis.ping()
            self._redis_ok = True
            logger.info("Redis connected", url=self._redis_url)
        except Exception as exc:
            logger.warning(
                "Redis unavailable — in-memory L1 cache only",
                error=str(exc),
            )
            self._redis = None
            self._redis_ok = False

        return self._redis if self._redis_ok else None

    # ── Public interface ──────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Return True when Redis is reachable."""
        try:
            r = await self._get_redis()
            if r:
                await r.ping()
                return True
        except Exception:
            self._redis_ok = False
            self._redis = None
        return False

    async def get(self, key: str) -> Optional[Any]:
        """Return the cached value or None. Checks L1 then Redis L2."""
        # L1 hit — fastest path
        if key in self._l1:
            self._hits_l1 += 1
            logger.debug("Cache L1 hit", key=key)
            return self._l1[key]

        # L2 Redis hit
        r = await self._get_redis()
        if r:
            try:
                raw = await r.get(_rk(key))
                if raw is not None:
                    value = json.loads(raw)
                    self._l1[key] = value          # promote to L1
                    self._hits_l2 += 1
                    logger.debug("Cache L2 hit", key=key)
                    return value
            except Exception as exc:
                self._errors += 1
                logger.warning("Redis GET error", key=key, error=str(exc))

        self._misses += 1
        logger.debug("Cache miss", key=key)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """Store value in L1 and Redis L2."""
        effective_ttl = ttl if ttl is not None else self._l2_ttl

        # L1 always written
        self._l1[key] = value

        # L2 Redis
        r = await self._get_redis()
        if r:
            try:
                await r.setex(
                    _rk(key),
                    effective_ttl,
                    json.dumps(value, default=str),
                )
                logger.debug("Cache set", key=key, ttl=effective_ttl)
            except Exception as exc:
                self._errors += 1
                logger.warning("Redis SET error", key=key, error=str(exc))

    async def delete(self, key: str) -> None:
        """Remove a key from L1 and Redis."""
        self._l1.pop(key, None)
        r = await self._get_redis()
        if r:
            try:
                await r.delete(_rk(key))
            except Exception as exc:
                self._errors += 1
                logger.warning("Redis DEL error", key=key, error=str(exc))

    async def clear_pattern(self, pattern: str = "*") -> int:
        """Delete all Redis keys matching *pattern* and flush L1."""
        self._l1.clear()
        r = await self._get_redis()
        if r:
            try:
                keys = await r.keys(_rk(pattern))
                if keys:
                    deleted: int = await r.delete(*keys)
                    logger.info("Cache cleared", pattern=pattern, deleted=deleted)
                    return deleted
            except Exception as exc:
                self._errors += 1
                logger.warning("Redis CLEAR error", pattern=pattern, error=str(exc))
        return 0

    def stats(self) -> dict:
        """Return cache hit / miss / error counters."""
        total = self._hits_l1 + self._hits_l2 + self._misses
        return {
            "l1_hits": self._hits_l1,
            "l2_hits": self._hits_l2,
            "misses": self._misses,
            "errors": self._errors,
            "hit_rate": round(
                (self._hits_l1 + self._hits_l2) / total, 3
            ) if total else 0.0,
            "l1_size": len(self._l1),
            "l1_maxsize": self._l1.maxsize,
            "redis_connected": self._redis_ok,
            "redis_url": self._redis_url,
        }

    async def close(self) -> None:
        """Close the Redis connection pool."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
            self._redis_ok = False
            logger.info("Redis connection closed")


# ── Module-level singleton ────────────────────────────────────────────────────

_instance: Optional[RedisMarketDataCache] = None


def get_cache() -> RedisMarketDataCache:
    """Return the application-wide cache singleton."""
    global _instance
    if _instance is None:
        _instance = RedisMarketDataCache()
    return _instance


async def close_cache() -> None:
    """Gracefully close the singleton cache (call on app shutdown)."""
    global _instance
    if _instance is not None:
        await _instance.close()
        _instance = None
