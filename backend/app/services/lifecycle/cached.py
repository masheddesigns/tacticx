"""Lifecycle read cache with explicit staleness (Phase 7).

Every cached response exposes fetched_at / expires_at / is_stale. Stale
data reused while a source is unavailable carries data_status=stale and is
never presented as live. TTLs come from configuration, documented per key.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from app.config import get_settings
from app.services.caching import cache as cache_backend


def cache_key(*parts: str) -> str:
    """Dimensioned key: source, endpoint, league, date range, ..."""
    safe = ["p7"] + ["".join(c if (c.isalnum() or c in "-_.:") else "_"
                             for c in str(p)) for p in parts]
    return ":".join(safe)


def cached_fetch(key: str, ttl_seconds: int, loader: Callable[[], object],
                 force_refresh: bool = False) -> Dict:
    """Return {data, fetched_at, expires_at, is_stale, data_status}.

    - Fresh hit: data_status=live.
    - Stale hit reused after loader failure: data_status=stale.
    - Miss with loader failure: data_status=unavailable, data=None.
    """
    now = time.time()
    if not force_refresh:
        envelope = cache_backend.cache_get_json(key)
        if isinstance(envelope, dict) and "data" in envelope:
            expires_at = envelope.get("expires_at", 0)
            if now < expires_at:
                envelope["is_stale"] = False
                envelope["data_status"] = "live"
                return envelope
            stale_envelope = dict(envelope)
            stale_envelope["is_stale"] = True
            stale_envelope["data_status"] = "stale"
            try:
                fresh = loader()
            except Exception:
                return stale_envelope
            return store(key, ttl_seconds, fresh)
    try:
        return store(key, ttl_seconds, loader())
    except Exception as exc:
        return {"data": None, "fetched_at": None, "expires_at": None,
                "is_stale": False, "data_status": "unavailable",
                "error": str(exc)[:200]}


def store(key: str, ttl_seconds: int, data: object) -> Dict:
    now = time.time()
    envelope = {"data": data, "fetched_at": now,
                "expires_at": now + max(1, ttl_seconds),
                "is_stale": False, "data_status": "live"}
    cache_backend.cache_set_json(key, envelope, max(1, ttl_seconds))
    return envelope


def upcoming_ttl() -> int:
    return get_settings().UPCOMING_FIXTURES_CACHE_TTL_SECONDS


def odds_ttl() -> int:
    return get_settings().CURRENT_ODDS_CACHE_TTL_SECONDS


def source_meta_ttl() -> int:
    return get_settings().SOURCE_META_CACHE_TTL_SECONDS
