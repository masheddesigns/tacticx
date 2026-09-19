"""MiroFish provider interface + adapters (Phase 16).

Application code depends only on ``MiroFishProvider``. Concrete adapters:
``DisabledProvider`` (honest unavailability) and ``HttpProvider`` (bounded
timeout/retries against a trusted configured endpoint). Secrets never enter
logs: only error codes plus redacted details leave this module.
"""
from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.services.mirofish import config as config_mod
from app.services.mirofish.errors import (
    CONTRACT_MISMATCH,
    INVALID_RESPONSE,
    PROVIDER_DISABLED,
    PROVIDER_ERROR,
    PROVIDER_NOT_CONFIGURED,
    PROVIDER_RATE_LIMITED,
    PROVIDER_TIMEOUT,
    RESPONSE_TOO_LARGE,
    MiroFishError,
)


class MiroFishProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def run_scenario(self, request_json: str) -> Dict[str, Any]:
        """Execute one scenario. Returns the raw decoded response mapping."""
        ...


class DisabledProvider(MiroFishProvider):
    name = "disabled"

    async def run_scenario(self, request_json: str) -> Dict[str, Any]:
        raise MiroFishError(PROVIDER_NOT_CONFIGURED,
                            "MiroFish is not configured (no external service bound)")


def select_provider() -> MiroFishProvider:
    """Provider selection from trusted configuration only (never user input)."""
    config = config_mod.load_config()
    if not config.enabled or not config.endpoint:
        return DisabledProvider()
    return HttpProvider(config)


class HttpProvider(MiroFishProvider):
    name = "http"

    def __init__(self, config=None):
        self._config = config or config_mod.load_config()

    def _auth_headers(self) -> Dict[str, str]:
        # Secret is read here and used only on the wire; it is never logged.
        # Diagnostics elsewhere report presence only.
        from app.config import get_settings
        api_key = get_settings().MIROFISH_API_KEY.strip()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    async def run_scenario(self, request_json: str) -> Dict[str, Any]:
        import httpx

        config = self._config
        if len(request_json.encode()) > config.response_max_bytes * 4:
            raise MiroFishError(PROVIDER_ERROR, "request exceeds size budget")
        last_error: Optional[MiroFishError] = None
        for attempt in range(max(1, config.retry_attempts + 1)):
            try:
                async with httpx.AsyncClient(
                        timeout=config.timeout_seconds) as client:
                    response = await client.post(
                        config.endpoint, content=request_json,
                        headers=self._auth_headers())
                if response.status_code == 429:
                    last_error = MiroFishError(
                        PROVIDER_RATE_LIMITED,
                        f"provider rate limited (HTTP 429, attempt {attempt + 1})")
                elif 500 <= response.status_code < 600:
                    last_error = MiroFishError(
                        PROVIDER_ERROR,
                        f"provider server error (HTTP {response.status_code})")
                elif 400 <= response.status_code < 500:
                    # Client/contract errors must not be retried.
                    raise MiroFishError(
                        CONTRACT_MISMATCH,
                        f"provider rejected request (HTTP {response.status_code})")
                else:
                    raw = response.content
                    if len(raw) > config.response_max_bytes:
                        raise MiroFishError(
                            RESPONSE_TOO_LARGE,
                            f"response {len(raw)} bytes exceeds "
                            f"{config.response_max_bytes}")
                    try:
                        decoded = json.loads(raw.decode("utf-8"))
                    except Exception:
                        raise MiroFishError(INVALID_RESPONSE, "malformed JSON")
                    if not isinstance(decoded, dict):
                        raise MiroFishError(INVALID_RESPONSE,
                                            "top-level JSON is not an object")
                    return decoded
            except MiroFishError as exc:
                if exc.code in (CONTRACT_MISMATCH, RESPONSE_TOO_LARGE,
                                INVALID_RESPONSE):
                    raise
                last_error = exc
            except (asyncio.TimeoutError, TimeoutError):
                last_error = MiroFishError(
                    PROVIDER_TIMEOUT,
                    f"provider timed out after {config.timeout_seconds}s")
            except Exception as exc:
                last_error = MiroFishError(
                    PROVIDER_ERROR, f"transport failure: {type(exc).__name__}")
            if attempt < config.retry_attempts:
                await asyncio.sleep(config.retry_base_seconds * (2 ** attempt))
        raise last_error or MiroFishError(PROVIDER_ERROR, "unknown provider failure")


def provider_status() -> Dict[str, str]:
    """Machine-readable availability without touching the network."""
    config = config_mod.load_config()
    if not config.enabled:
        return {"status": "unavailable", "reason": PROVIDER_DISABLED}
    if not config.endpoint:
        return {"status": "unavailable", "reason": PROVIDER_NOT_CONFIGURED}
    return {"status": "configured", "reason": "endpoint present"}
