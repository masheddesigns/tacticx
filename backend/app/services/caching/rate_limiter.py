"""Token-bucket rate limiter with Redis backend + in-memory fallback.

Every provider call must pass through `acquire(provider)` first.
"""
from __future__ import annotations

import time

from app.config import get_settings
from app.services.caching import cache as _cache_mod

_buckets: dict[str, tuple[float, float]] = {}  # provider -> (tokens, last_refill)


def _capacity_for(provider: str) -> int:
    settings = get_settings()
    key = f"{provider.upper()}_RATE_LIMIT_PER_MINUTE"
    configured = getattr(settings, key, None)
    if isinstance(configured, (int, float)) and configured > 0:
        return max(1, int(configured))
    return max(1, settings.PROVIDER_MAX_REQUESTS_PER_MINUTE)


def acquire(provider: str) -> bool:
    """Return True if a request slot is available (and consume it)."""
    settings = get_settings()
    capacity = _capacity_for(provider)
    refill_per_sec = capacity / 60.0
    now = time.time()
    tokens, last = _buckets.get(provider, (float(capacity), now))
    tokens = min(float(capacity), tokens + (now - last) * refill_per_sec)
    if tokens >= 1.0:
        _buckets[provider] = (tokens - 1.0, now)
        return True
    _buckets[provider] = (tokens, now)
    return False


def time_until_available(provider: str) -> float:
    capacity = _capacity_for(provider)
    refill_per_sec = capacity / 60.0
    tokens, _ = _buckets.get(provider, (float(capacity), time.time()))
    if tokens >= 1.0:
        return 0.0
    return (1.0 - tokens) / refill_per_sec


def reset_limiter() -> None:
    _buckets.clear()
    try:
        _cache_mod.reset_cache()
    except Exception:
        pass


class RateLimitExceeded(Exception):
    pass
