"""Odds movement math: opening vs current, change, %, direction, velocity."""
from __future__ import annotations

from typing import Optional


def movement(opening: float, current: float, minutes_elapsed: Optional[float] = None) -> dict:
    change = round(current - opening, 4)
    pct = round((change / opening * 100), 2) if opening else 0.0
    direction = "down" if change < 0 else ("up" if change > 0 else "flat")
    out = {
        "opening": opening, "current": current, "absolute_change": change,
        "percentage_change": pct, "direction": direction,
    }
    if minutes_elapsed:
        out["velocity_per_hour"] = round(change / (minutes_elapsed / 60), 4)
    return out
