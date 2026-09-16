"""Provider quota extraction from response headers.

The Odds API sends `x-requests-remaining` / `x-requests-used`;
API-Sports-style APIs may send `x-ratelimit-remaining` variants.
This scans a known list (case-insensitive) and returns the remaining
quota as a float, or None when the provider exposes nothing.

Step 11 rule applies in reverse here too: only persist what the
provider actually reports — never invent quota numbers.
"""
from __future__ import annotations

from typing import Callable, Optional

QUOTA_REMAINING_HEADERS = (
    "x-requests-remaining",       # The Odds API
    "x-ratelimit-remaining",      # generic / api-sports style
    "x-ratelimit-requests-remaining",
    "x-rate-limit-remaining",
)

QuotaExtractor = Callable[[object], Optional[float]]


def extract_quota_remaining(headers: object) -> Optional[float]:
    get = getattr(headers, "get", None)
    if not callable(get):
        return None
    # httpx.Headers.get is case-insensitive; plain dicts may not be.
    try:
        items = list(headers.items())  # type: ignore[union-attr]
    except Exception:
        items = []
    lowered = {str(k).lower(): v for k, v in items} if items else {}
    for name in QUOTA_REMAINING_HEADERS:
        raw = lowered.get(name)
        if raw is None and callable(get):
            try:
                raw = get(name)
            except Exception:
                raw = None
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None
