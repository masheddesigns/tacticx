"""MiroFish failure taxonomy (Phase 16).

Machine-readable error codes only. No secrets, no raw headers, no payload
echoes — callers log the code plus a redacted detail string.
"""
from __future__ import annotations

PROVIDER_NOT_CONFIGURED = "provider_not_configured"
PROVIDER_DISABLED = "provider_disabled"
PROVIDER_TIMEOUT = "provider_timeout"
PROVIDER_ERROR = "provider_error"
PROVIDER_RATE_LIMITED = "provider_rate_limited"
INVALID_RESPONSE = "invalid_response"
CONTRACT_MISMATCH = "contract_mismatch"
RESPONSE_TOO_LARGE = "response_too_large"


class MiroFishError(Exception):
    """Classified provider failure carrying a machine-readable code."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail)
        self.code = code
        # Never store secrets: detail is caller-redacted before construction.
        self.detail = detail[:500]
