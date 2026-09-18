"""Candidate feature families + availability gates + missingness (Phase 12).

Families: team (elo_diff, form, gd, rest), xg, shots, player (continuity),
events (registered-only, via continuity coverage), market (pre-cutoff only,
benchmark role). Every feature passes identity/temporal/quality/freshness/
sample-size/definition gates or ships as available=false. Missing values are
never zero-filled, forward-filled, or interpolated: complete-case reporting
vs family availability is explicit, and coverage-poor families report their
eligible/missing counts instead of pretending full coverage.
"""
from __future__ import annotations

from typing import Dict, List, Optional

FAMILIES: Dict[str, Dict] = {
    "team": {"features": ["elo_diff", "form_ppm_diff_5", "gd_diff_5", "rest_diff"],
             "min_rows": 100, "description": "Elo + venue form + rest"},
    "xg": {"features": ["xg_diff_5"], "min_rows": 50,
           "description": "xG differential (estimated timing only; strict-ineligible)"},
    "shots": {"features": ["shots_diff_5"], "min_rows": 50,
              "description": "Shot-volume differential where source coverage exists"},
    "player": {"features": ["continuity_diff"], "min_rows": 50,
               "description": "Starter-continuity differential (estimated timing only)"},
    "events": {"features": ["continuity_diff"], "min_rows": 50,
               "description": "Registered-event coverage proxy (same gate as player)"},
    "market": {"features": [], "min_rows": 0,
               "description": "Benchmark only; never a production input"},
}

FEATURE_TO_FAMILY = {name: family for family, spec in FAMILIES.items()
                     for name in spec["features"]}


def gate_row(row: Dict, family: str) -> bool:
    """Availability gate for one row × family (identity/temporal/quality/
    sample/definition collapsed to the row's recorded availability flag,
    which the dataset builder sets from evidence)."""
    if family not in FAMILIES:
        return False
    if not row.get("availability", {}).get(family, False):
        return False
    return all(row.get("features", {}).get(name) is not None
               for name in FAMILIES[family]["features"])


def missingness_report(rows: List[Dict], family: str) -> Dict:
    """Eligible/missing counts + coverage % + strict/estimated split for one
    family. A 20%-coverage family reports 20%, never 100%."""
    eligible = sum(1 for r in rows if gate_row(r, family))
    missing = len(rows) - eligible
    return {"family": family, "rows": len(rows), "eligible_rows": eligible,
            "missing_rows": missing,
            "coverage_pct": round(100.0 * eligible / len(rows), 2) if rows else 0.0,
            "strict_availability": "unavailable" if family in ("xg", "player", "events")
            else "available",
            "estimated_availability": "available" if eligible else "unavailable"}


def select_features(rows: List[Dict], families: List[str]) -> Dict:
    """Feature matrix for a family set. Rows failing any requested family
    gate are dropped (strict complete-case); dropped counts reported."""
    names = [name for family in families for name in FAMILIES.get(family, {}).get(
        "features", [])]
    kept, dropped = [], 0
    for row in rows:
        if all(gate_row(row, family) for family in families if family != "market"):
            kept.append(row)
        else:
            dropped += 1
    matrix = [[row["features"][name] for name in names] for row in kept]
    return {"feature_names": names, "X": matrix,
            "labels": [row["actual"] for row in kept],
            "match_ids": [row["match_id"] for row in kept],
            "kept": len(kept), "dropped": dropped}
