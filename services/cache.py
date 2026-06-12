"""Redis cache с graceful degradation — если Redis недоступен, всё работает без кеша."""
import json
import logging
import os

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "")
_redis = None


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
        except Exception as e:
            logger.warning("Redis недоступен, кеш отключён: %s", e)
            _redis = None
    return _redis


async def cache_get(key: str):
    r = await _get_redis()
    if not r:
        return None
    try:
        val = await r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


async def cache_set(key: str, value, ttl: int = 180):
    r = await _get_redis()
    if not r:
        return
    try:
        await r.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


async def cache_delete(key: str):
    r = await _get_redis()
    if not r:
        return
    try:
        await r.delete(key)
    except Exception:
        pass


async def cache_invalidate_dashboard():
    """Инвалидирует все ключи дашборда. Вызывать при изменении проектов/задач."""
    r = await _get_redis()
    if not r:
        return
    try:
        keys = await r.keys("dashboard:*")
        if keys:
            await r.delete(*keys)
    except Exception:
        pass
