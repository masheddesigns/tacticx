"""Cache-first helper: Redis when available, in-memory fallback (tests / local)."""
from __future__ import annotations

from typing import Optional

import json
import time

from app.config import get_settings

_memory: dict[str, tuple[float, str]] = {}


def _redis():
    try:
        import redis  # type: ignore

        client = redis.Redis.from_url(get_settings().REDIS_URL, socket_timeout=2)
        client.ping()
        return client
    except Exception:
        return None


_redis_client = None


def _client():
    global _redis_client
    if _redis_client is None:
        _redis_client = _redis()
    return _redis_client


def cache_get(key: str) -> Optional[str]:
    c = _client()
    if c is not None:
        try:
            val = c.get(key)
            return val.decode() if isinstance(val, bytes) else val
        except Exception:
            pass
    item = _memory.get(key)
    if item is None:
        return None
    expires, val = item
    if expires < time.time():
        _memory.pop(key, None)
        return None
    return val


def cache_set(key: str, value: str, ttl_seconds: int) -> None:
    c = _client()
    if c is not None:
        try:
            c.setex(key, ttl_seconds, value)
            return
        except Exception:
            pass
    _memory[key] = (time.time() + ttl_seconds, value)


def cache_get_json(key: str):
    raw = cache_get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def cache_set_json(key: str, obj, ttl_seconds: int) -> None:
    cache_set(key, json.dumps(obj, default=str), ttl_seconds)


def cache_delete(key: str) -> None:
    c = _client()
    if c is not None:
        try:
            c.delete(key)
        except Exception:
            pass
    _memory.pop(key, None)


def reset_cache() -> None:
    """Test helper: clear memory fallback and drop cached redis client."""
    global _redis_client
    _memory.clear()
    _redis_client = None


def backend_name() -> str:
    """Which cache backend is active: 'redis' or 'memory'.

    The memory fallback is explicit — callers must never silently
    pretend Redis is active when it is not.
    """
    return "redis" if _client() is not None else "memory"


def backend_status() -> dict:
    name = backend_name()
    return {
        "backend": name,
        "redis_url_configured": bool(get_settings().REDIS_URL),
        "fallback_active": name == "memory",
    }
