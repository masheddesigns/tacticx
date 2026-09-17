"""Temporal modes for prediction (Phase 2).

STRICT_PREMATCH: only data demonstrably safe for pre-match prediction —
finished matches before cutoff, plus feature records with explicit timing
at or before cutoff. Unknown-timing records are EXCLUDED (counts reported).

HISTORICAL_ESTIMATED: additionally allows records whose parent match kicked
off before the cutoff (post-match facts of past matches). Predictions made
in this mode carry temporal uncertainty and are labeled as such.

Backtesting defaults to STRICT_PREMATCH. Modes are never mixed silently.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional


class TemporalMode(str, enum.Enum):
    STRICT_PREMATCH = "strict_prematch"
    HISTORICAL_ESTIMATED = "historical_estimated"


def as_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes, Postgres aware ones. Compare naive UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def season_label(kickoff: Optional[datetime]) -> str:
    """August–July season label, e.g. 2024-09-21 -> '2024'."""
    naive = as_naive_utc(kickoff)
    if naive is None:
        return "unknown"
    return str(naive.year if naive.month >= 8 else naive.year - 1)
