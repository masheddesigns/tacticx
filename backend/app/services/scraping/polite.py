"""Polite HTTP fetcher (Phase 1.6).

Wraps the existing quota-protected `logged_request` (cache-first,
single-flight, rate limit, backoff, 429 handling, request logging) and adds
scraper-specific politeness on top:

- minimum delay between requests to the same host
- per-host requests-per-minute ceiling (defaults: conservative)
- configurable User-Agent identifying the fetcher
- robots.txt pre-check (refuse cleanly when disallowed)

No CAPTCHA/auth/paywall/anti-bot bypass, ever.
"""
from __future__ import annotations

import time
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.logging_config import get_logger
from app.services.http_client import logged_request
from app.services.scraping.robots import robots_allowed

log = get_logger(__name__)

_last_hit: dict[str, float] = {}
_minute_hits: dict[str, list[float]] = {}


class SourceDisallowed(Exception):
    """robots.txt (or policy) forbids automated access — fail cleanly."""


class PoliteFetcher:
    def __init__(
        self,
        source: str,
        min_delay_seconds: Optional[float] = None,
        max_requests_per_minute: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        cache_ttl_seconds: Optional[int] = None,
        user_agent: Optional[str] = None,
        db_session_factory=None,
        client: Optional[httpx.AsyncClient] = None,
        check_robots: bool = True,
    ):
        s = get_settings()
        self.source = source
        self.min_delay = min_delay_seconds if min_delay_seconds is not None else s.SCRAPER_MIN_DELAY_SECONDS
        self.max_per_minute = max_requests_per_minute if max_requests_per_minute is not None else s.SCRAPER_MAX_REQUESTS_PER_MINUTE
        self.timeout = timeout_seconds if timeout_seconds is not None else s.SCRAPER_TIMEOUT_SECONDS
        self.cache_ttl = cache_ttl_seconds if cache_ttl_seconds is not None else s.SCRAPER_CACHE_TTL_SECONDS
        self.user_agent = user_agent or s.SCRAPER_USER_AGENT
        self.db_session_factory = db_session_factory
        self.client = client
        self.check_robots = check_robots

    @staticmethod
    def _host(url: str) -> str:
        return urlparse(url).hostname or "unknown"

    def _politeness_wait(self, host: str) -> None:
        now = time.time()
        last = _last_hit.get(host, 0.0)
        wait = self.min_delay - (now - last)
        if wait > 0:
            time.sleep(wait)
            now = time.time()
        window = [t for t in _minute_hits.get(host, []) if now - t < 60.0]
        if len(window) >= max(1, self.max_per_minute):
            sleep_for = 60.0 - (now - window[0]) + 0.05
            log.info("scraper rate ceiling host=%s sleeping=%.1fs", host, sleep_for)
            time.sleep(max(0.0, sleep_for))
            now = time.time()
            window = [t for t in window if now - t < 60.0]
        window.append(now)
        _minute_hits[host] = window
        _last_hit[host] = now

    async def fetch_text(self, url: str, *, cache_key: Optional[str] = None) -> str:
        """GET a URL as text. Raises SourceDisallowed / ProviderHTTPError."""
        if self.check_robots and not robots_allowed(url):
            raise SourceDisallowed(f"automated access disallowed by robots.txt: {url}")
        host = self._host(url)
        self._politeness_wait(host)
        headers = {"User-Agent": self.user_agent}
        data = await logged_request(
            self.source, "GET", url, headers=headers,
            cache_key=cache_key or f"scrape:{host}:{url}",
            cache_ttl=self.cache_ttl, response_format="text",
            follow_redirects=True,  # same-protocol redirects are normal, not a bypass
            db_session_factory=self.db_session_factory, client=self.client,
        )
        return str(data or "")

    async def fetch_bytes(self, url: str, *, cache_key: Optional[str] = None) -> bytes:
        return (await self.fetch_text(url, cache_key=cache_key)).encode("utf-8")

    async def head_exists(self, url: str) -> Optional[bool]:
        """HEAD probe for file availability (inventory use).

        Returns True (2xx), False (404), or None (network/other error —
        unknown, never treated as proof of absence). Polite delays and
        robots checks apply; nothing is downloaded.
        """
        from app.services.http_client import ProviderHTTPError

        if self.check_robots and not robots_allowed(url):
            raise SourceDisallowed(f"automated access disallowed by robots.txt: {url}")
        host = self._host(url)
        self._politeness_wait(host)
        headers = {"User-Agent": self.user_agent}
        try:
            if self.client is not None:
                resp = await self.client.head(url, headers=headers,
                                              timeout=self.timeout, follow_redirects=True)
            else:
                async with httpx.AsyncClient(timeout=self.timeout,
                                             follow_redirects=True) as client:
                    resp = await client.head(url, headers=headers)
        except Exception as exc:  # noqa: BLE001 — unknown, not absent
            log.warning("HEAD probe failed url=%s err=%s", url, exc)
            return None
        if resp.status_code == 404:
            return False
        if 200 <= resp.status_code < 300:
            return True
        if resp.status_code == 429:
            raise ProviderHTTPError("HTTP 429 rate limited", 429)
        log.warning("HEAD probe unexpected url=%s status=%s", url, resp.status_code)
        return None


def reset_fetcher_state() -> None:
    """Test helper: clear per-host politeness clocks."""
    _last_hit.clear()
    _minute_hits.clear()
