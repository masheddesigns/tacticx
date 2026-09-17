"""Odds timelines and movement (Phase 3).

Per (bookmaker, market, selection): chronological distinct observations,
opening vs current vs closing, movement steps, velocity, and line features.
Built on the existing movement() helper; extended with versioning and
defensive timestamp handling (zero intervals, duplicates, out-of-order rows).

Version: movement_v1. Units: percentage_points_per_hour for velocity.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.config import get_settings
from app.services.features.temporal import as_naive_utc
from app.utils.odds_math import movement as _movement

MOVEMENT_V1 = "movement_v1"


def dedupe_observations(points: List[tuple]) -> List[tuple]:
    """Sort by timestamp; collapse consecutive equal prices (within flat
    tolerance); count duplicate timestamps. Returns distinct observations."""
    flat = get_settings().ODDS_MOVEMENT_FLAT_TOLERANCE
    ordered = sorted(points, key=lambda p: (p[0] is None, p[0]))
    out: List[tuple] = []
    duplicate_timestamps = 0
    seen_times = set()
    for timestamp, price in ordered:
        if timestamp in seen_times:
            duplicate_timestamps += 1
        else:
            seen_times.add(timestamp)
        if out and abs(price - out[-1][1]) <= flat:
            continue
        out.append((timestamp, price))
    return out


def _hours_between(first, second) -> Optional[float]:
    first_naive = as_naive_utc(first)
    second_naive = as_naive_utc(second)
    if first_naive is None or second_naive is None:
        return None
    return (second_naive - first_naive).total_seconds() / 3600.0


def velocity(change_pct_points: float, hours: Optional[float],
             min_interval_seconds: Optional[float] = None) -> Optional[float]:
    """Percentage points per hour. None on zero/unknown intervals — never
    a division error, never an invented number. Intervals below the
    configured minimum (bulk import batches stamp milliseconds apart) also
    yield None: annualizing them would manufacture absurd velocities while
    the movement itself stays recorded."""
    if min_interval_seconds is None:
        min_interval_seconds = get_settings().ODDS_MIN_VELOCITY_INTERVAL_SECONDS
    if hours is None or hours <= 0:
        return None
    if hours * 3600.0 < min_interval_seconds:
        return None
    return round(change_pct_points / hours, 4)


def timeline(points: List[tuple], closing_price=None,
             closing_timestamp=None) -> Dict:
    """Full timeline dict for one selection's observation series."""
    distinct = dedupe_observations(points)
    if not distinct:
        return {"observations": 0, "calculation_version": MOVEMENT_V1}
    opening_ts, opening = distinct[0]
    current_ts, current = distinct[-1]
    moves = []
    for (prev_ts, prev_price), (next_ts, next_price) in zip(distinct[:-1], distinct[1:]):
        step = _movement(prev_price, next_price, None)
        hours = _hours_between(prev_ts, next_ts)
        pct_points = round((next_price - prev_price) / prev_price * 100.0, 4) \
            if prev_price else 0.0
        step["from_timestamp"] = str(prev_ts)
        step["to_timestamp"] = str(next_ts)
        step["velocity_per_hour"] = velocity(pct_points, hours)
        moves.append(step)
    overall = _movement(opening, current, None)
    anchor_ts = closing_timestamp or current_ts
    elapsed = _hours_between(opening_ts, anchor_ts)
    overall_pct = round((current - opening) / opening * 100.0, 4) if opening else 0.0
    prices = [p for _, p in distinct]
    return {
        "observations": len(distinct),
        "opening_price": opening,
        "opening_timestamp": str(opening_ts),
        "first_observed_price": opening,
        "current_price": current,
        "current_timestamp": str(current_ts),
        "closing_price": closing_price,
        "closing_timestamp": str(closing_timestamp) if closing_timestamp else None,
        "absolute_movement": overall["absolute_change"],
        "percentage_movement": overall["percentage_change"],
        "direction": overall["direction"],
        "max_price": max(prices),
        "min_price": min(prices),
        "number_of_movements": len(moves),
        "time_to_close_hours": round(elapsed, 4) if elapsed is not None else None,
        "movement_velocity_per_hour": velocity(overall_pct, elapsed),
        "movements": moves,
        "calculation_version": MOVEMENT_V1,
    }


def opening_status(has_source_opening: bool, has_any: bool) -> str:
    """source_verified | first_observed | unknown.

    Never label the first DB row a true bookmaker opening unless the source
    explicitly identifies it as such (none of our current sources do).
    """
    if has_source_opening:
        return "source_verified"
    if has_any:
        return "first_observed"
    return "unknown"
