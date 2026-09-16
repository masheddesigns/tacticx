"""robots.txt compliance (Phase 1.6).

A source that disallows automated access must fail cleanly — never bypassed.
Results are cached; check failures are treated as "not allowed" (fail closed).
"""
from __future__ import annotations

import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from app.logging_config import get_logger
from app.services.caching import cache as cache_mod

log = get_logger(__name__)

_CACHE_TTL = 86400
_cache: dict[str, tuple[float, bool]] = {}


def robots_allowed(url: str, user_agent: str = "*") -> bool:
    """True when fetching `url` is permitted by the host's robots.txt.

    A missing robots.txt (HTTP 404) means no stated restriction (allowed).
    Any fetch/parse error resolves to disallowed (fail closed) — a source
    that cannot be checked must fail cleanly, never be bypassed.
    """
    try:
        host = urlparse(url).hostname or ""
        if not host:
            return False
        cache_key = f"robots:{host}:{user_agent}"
        now = time.time()
        hit = _cache.get(cache_key)
        if hit and hit[0] > now:
            return hit[1]
        cached = cache_mod.cache_get(cache_key)
        if cached in ("1", "0"):
            result = cached == "1"
            _cache[cache_key] = (now + _CACHE_TTL, result)
            return result

        rp = RobotFileParser()
        rp.set_url(f"https://{host}/robots.txt")
        try:
            rp.read()
        except Exception as exc:  # noqa: BLE001 — fail closed
            log.warning("robots fetch failed host=%s err=%s", host, exc)
            return False
        result = bool(rp.can_fetch(user_agent, url))
        _cache[cache_key] = (now + _CACHE_TTL, result)
        try:
            cache_mod.cache_set(cache_key, "1" if result else "0", _CACHE_TTL)
        except Exception:  # noqa: BLE001 — cache is best-effort
            pass
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("robots check failed url=%s err=%s", url, exc)
        return False


def reset_robots_cache() -> None:
    _cache.clear()
