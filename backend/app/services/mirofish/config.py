"""Effective MiroFish configuration (Phase 16).

Secrets come only from environment/configuration. The endpoint URL comes
from trusted configuration — never from user input at runtime (SSRF guard).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True)
class MiroFishConfig:
    enabled: bool = False
    endpoint: str = ""
    timeout_seconds: float = 20.0
    retry_attempts: int = 2
    retry_base_seconds: float = 1.0
    max_scenarios: int = 7
    contract_version: str = "mirofish_contract_v1"
    response_max_bytes: int = 65536
    has_credentials: bool = False


def load_config() -> MiroFishConfig:
    settings = get_settings()
    return MiroFishConfig(
        enabled=bool(settings.MIROFISH_ENABLED),
        endpoint=settings.MIROFISH_ENDPOINT.strip(),
        timeout_seconds=float(settings.MIROFISH_TIMEOUT_SECONDS),
        retry_attempts=max(0, int(settings.MIROFISH_RETRY_ATTEMPTS)),
        retry_base_seconds=float(settings.MIROFISH_RETRY_BASE_SECONDS),
        max_scenarios=max(1, int(settings.MIROFISH_MAX_SCENARIOS)),
        contract_version=settings.MIROFISH_CONTRACT_VERSION.strip()
        or "mirofish_contract_v1",
        response_max_bytes=max(1024, int(settings.MIROFISH_RESPONSE_MAX_BYTES)),
        has_credentials=bool(settings.MIROFISH_API_KEY.strip()),
    )


def diagnose() -> dict:
    """Safe diagnostics: presence only, never secret values."""
    config = load_config()
    return {
        "enabled": config.enabled,
        "endpoint_configured": bool(config.endpoint),
        "credentials": "configured" if config.has_credentials else "missing",
        "contract_version": config.contract_version,
    }
