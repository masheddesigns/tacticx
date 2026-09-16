"""Resilient provider HTTP layer: rate limit gate, cache-first, retries with
exponential backoff, HTTP 429 respect, and per-request quota logging."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.logging_config import get_logger, redact_secrets
from app.services.caching import cache as cache_mod
from app.services.caching.rate_limiter import RateLimitExceeded, acquire
from app.services.quota import QuotaExtractor, extract_quota_remaining

log = get_logger(__name__)

# 4xx (other than 429) means the request itself is bad — retrying burns quota.
def _retryable(status: Optional[int]) -> bool:
    return status is None or status == 429 or status >= 500

_inflight: dict[str, asyncio.Task] = {}


class ProviderHTTPError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


async def logged_request(
    provider: str,
    method: str,
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    cache_key: Optional[str] = None,
    cache_ttl: int = 300,
    request_cost: Optional[float] = None,
    db_session_factory=None,
    client: Optional[httpx.AsyncClient] = None,
    quota_extractor: Optional[QuotaExtractor] = None,
    response_format: str = "json",
    follow_redirects: bool = False,
) -> Any:
    """GET/POST JSON with quota protection. Returns parsed JSON.

    - cache-first when cache_key is set
    - single-flight dedup for concurrent identical calls
    - rate limiter gate, exponential-backoff retries, honors Retry-After on 429
    - writes a ProviderRequestLog row when db_session_factory is provided,
      including provider-reported quota remaining when headers carry it
    - response_format="text" returns raw text (CSV/HTML scrapers)
    - follow_redirects follows HTTP redirects (polite fetcher only)
    - secrets are redacted from logs and stored error messages
    """
    settings = get_settings()
    quota_fn: QuotaExtractor = quota_extractor or extract_quota_remaining
    if cache_key:
        cached = cache_mod.cache_get_json(cache_key)
        if cached is not None:
            log.info("cache_hit provider=%s key=%s", provider, cache_key)
            return cached

    if cache_key and cache_key in _inflight:
        return await _inflight[cache_key]

    async def _do() -> Any:
        attempts = max(1, settings.PROVIDER_RETRY_ATTEMPTS)
        delay = settings.PROVIDER_RETRY_BASE_SECONDS
        last_exc: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            if not acquire(provider):
                raise RateLimitExceeded(f"rate limit exceeded for provider={provider}")
            start = time.monotonic()
            status: Optional[int] = None
            error = ""
            success = False
            try:
                own_client = client is None
                if own_client:
                    cm = httpx.AsyncClient(timeout=settings.PROVIDER_TIMEOUT_SECONDS,
                                           follow_redirects=follow_redirects)
                else:
                    cm = client
                try:
                    resp = await cm.request(method, url, headers=headers, params=params)
                finally:
                    if own_client:
                        await cm.aclose()
                status = resp.status_code
                elapsed_ms = (time.monotonic() - start) * 1000
                quota = quota_fn(resp.headers)
                if status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else delay
                    error = "HTTP 429 rate limited"
                    _write_log(db_session_factory, provider, url, status, elapsed_ms, False, error, request_cost, quota)
                    if attempt == attempts:
                        raise ProviderHTTPError(error, 429)
                    log.warning("429 provider=%s attempt=%d waiting=%.1fs", provider, attempt, wait)
                    await asyncio.sleep(wait)
                    delay *= 2
                    continue
                resp.raise_for_status()
                success = True
                data = resp.text if response_format == "text" else resp.json()
                _write_log(db_session_factory, provider, url, status, elapsed_ms, True, "", request_cost, quota)
                if cache_key:
                    cache_mod.cache_set_json(cache_key, data, cache_ttl)
                return data
            except RateLimitExceeded:
                raise
            except ProviderHTTPError:
                raise
            except Exception as exc:  # noqa: BLE001 — retried, then logged
                last_exc = exc
                status = getattr(getattr(exc, "response", None), "status_code", status)
                error = redact_secrets(str(exc)[:500])
                elapsed_ms = (time.monotonic() - start) * 1000
                _write_log(db_session_factory, provider, url, status, elapsed_ms, False, error, request_cost, None)
                if attempt == attempts or not _retryable(status):
                    raise ProviderHTTPError(f"{provider} request failed: {error}", status) from exc
                log.warning("provider=%s attempt=%d failed err=%s retry_in=%.1fs",
                            provider, attempt, error, delay)
                await asyncio.sleep(delay)
                delay *= 2
        raise ProviderHTTPError(f"{provider} request failed: {last_exc}", None)

    if cache_key:
        task = asyncio.ensure_future(_do())
        _inflight[cache_key] = task
        try:
            return await task
        finally:
            _inflight.pop(cache_key, None)
    return await _do()


def _write_log(factory, provider, endpoint, status, elapsed_ms, success, error, cost,
               quota_remaining=None) -> None:
    if factory is None:
        return
    try:
        from app.db.models.logs import ProviderRequestLog

        # Accept a Session, a sessionmaker, or a zero-arg factory returning either.
        s = factory
        while callable(s) and not hasattr(s, "add"):
            s = s()
        try:
            s.add(ProviderRequestLog(
                provider=provider, endpoint=endpoint[:256], status_code=status,
                response_time_ms=elapsed_ms, success=success, error=error or "",
                request_cost=cost, quota_remaining=quota_remaining,
            ))
            s.commit()
        finally:
            s.close()
    except Exception as exc:  # noqa: BLE001 — logging must never break ingestion
        log.warning("request-log write failed: %s", exc)
