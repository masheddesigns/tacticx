"""Evidence-based data warnings (Phase 15).

Each warning fires only on a measurable condition. Warnings describe data
limitations, never betting advice. Output stays concise: irrelevant warnings
are omitted, not emitted as noise.
"""
from __future__ import annotations

from typing import Dict, List

XG_UNAVAILABLE = "XG_UNAVAILABLE"
PLAYER_DATA_UNAVAILABLE = "PLAYER_DATA_UNAVAILABLE"
TEMPORAL_QUALITY_UNKNOWN = "TEMPORAL_QUALITY_UNKNOWN"
MARKET_THIN = "MARKET_THIN"
HISTORICAL_DATA_SPARSE = "HISTORICAL_DATA_SPARSE"
MODEL_DISAGREEMENT_HIGH = "MODEL_DISAGREEMENT_HIGH"
NO_MARKET = "NO_MARKET"
CLOSING_ONLY = "CLOSING_ONLY"


def generate_warnings(composed_dump: Dict) -> List[Dict]:
    """Inspect a composed prediction dump; return fired warnings only."""
    warnings = []
    avail = (composed_dump.get("core_prediction") or {}).get(
        "feature_availability", {}) or {}
    data_quality = composed_dump.get("data_quality", {}) or {}
    market = composed_dump.get("market", {}) or {}
    disagreement = composed_dump.get("model_disagreement", {}) or {}

    if not avail.get("xg"):
        warnings.append({"code": XG_UNAVAILABLE, "severity": "info",
                         "detail": "xG history below minimum; goals-only pathway"})
    if data_quality.get("missing_feature_count", 0) > 0 and \
            not avail.get("shots", True):
        warnings.append({"code": PLAYER_DATA_UNAVAILABLE, "severity": "info",
                         "detail": "secondary features incomplete"})
    if not data_quality.get("strict_mode", True) or \
            data_quality.get("estimated_fields"):
        warnings.append({"code": TEMPORAL_QUALITY_UNKNOWN, "severity": "warning",
                         "detail": "estimated-mode fields present; not strict"})
    books = market.get("bookmakers", []) or []
    if market.get("status") == "ok" and len(books) < 3:
        warnings.append({"code": MARKET_THIN, "severity": "warning",
                         "detail": f"consensus from {len(books)} bookmakers (<3)"})
    if market.get("status") not in ("ok", "partial"):
        warnings.append({"code": NO_MARKET, "severity": "info",
                         "detail": "no pre-cutoff market coverage"})
    if (market.get("consensus") or {}).get("closing_snapshots_excluded"):
        warnings.append({"code": CLOSING_ONLY, "severity": "info",
                         "detail": "closing snapshots excluded from consensus"})
    hist_n = (avail.get("home_history", 0) or 0) + (avail.get("away_history", 0) or 0)
    if 0 < hist_n < 20:
        warnings.append({"code": HISTORICAL_DATA_SPARSE, "severity": "warning",
                         "detail": f"only {hist_n} pre-cutoff team-matches"})
    ranges = [v.get("range") for v in (disagreement.get("per_outcome") or {}).values()
              if isinstance(v, dict) and v.get("range") is not None]
    if ranges and max(ranges) > 0.15:
        warnings.append({"code": MODEL_DISAGREEMENT_HIGH, "severity": "warning",
                         "detail": f"member spread up to {max(ranges):.3f} on an outcome"})
    return warnings
