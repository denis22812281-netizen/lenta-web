"""Cache с двумя уровнями: Redis (если REDIS_URL задан) + in-memory fallback.

In-memory fallback работает всегда — без Redis данные живут в RAM процесса.
Redis включается автоматически при наличии REDIS_URL (Railway addon).
"""
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "")
_redis = None

# In-memory fallback: key → (value_json, expires_at)
_mem: dict[str, tuple[str, float]] = {}


def _mem_get(key: str):
    entry = _mem.get(key)
    if entry is None:
        return None
    val_json, expires_at = entry
    if time.monotonic() > expires_at:
        _mem.pop(key, None)
        return None
    return json.loads(val_json)


def _mem_set(key: str, value, ttl: int) -> None:
    _mem[key] = (json.dumps(value, default=str), time.monotonic() + ttl)


def _mem_delete(key: str) -> None:
    _mem.pop(key, None)


def _mem_delete_prefix(prefix: str) -> None:
    for k in [k for k in list(_mem) if k.startswith(prefix)]:
        _mem.pop(k, None)


async def _get_redis():
    global _redis
    if not _REDIS_URL:
        return None
    if _redis is None:
        try:
            import redis.asyncio as aioredis
            _redis = aioredis.from_url(
                _REDIS_URL, decode_responses=True,
                socket_connect_timeout=2, socket_timeout=2,
            )
            await _redis.ping()
            logger.info("Redis cache подключён: %s", _REDIS_URL[:30])
        except Exception as e:
            logger.warning("Redis недоступен, используется in-memory cache: %s", e)
            _redis = None
    return _redis


async def cache_get(key: str):
    r = await _get_redis()
    if r:
        try:
            val = await r.get(key)
            return json.loads(val) if val else None
        except Exception:
            pass
    return _mem_get(key)


async def cache_set(key: str, value, ttl: int = 180):
    r = await _get_redis()
    if r:
        try:
            await r.setex(key, ttl, json.dumps(value, default=str))
            return
        except Exception:
            pass
    _mem_set(key, value, ttl)


async def cache_delete(key: str):
    r = await _get_redis()
    if r:
        try:
            await r.delete(key)
        except Exception:
            pass
    _mem_delete(key)


async def cache_invalidate_dashboard():
    """Инвалидирует все ключи дашборда. Вызывать при изменении проектов/задач."""
    _mem_delete_prefix("dashboard:")
    r = await _get_redis()
    if r:
        try:
            keys = await r.keys("dashboard:*")
            if keys:
                await r.delete(*keys)
        except Exception:
            pass
