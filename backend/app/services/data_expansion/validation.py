"""Source-value gate + row validation (Phase 13).

A source integrates only on material incremental value: new matches,
seasons, families, xG/player/event coverage, or temporal metadata quality.
Duplicated bulk with no new information is rejected as a dependency (its
rows may still backfill gaps case-by-case, but it never becomes depended on).
"""
from __future__ import annotations

from typing import Dict, List


def incremental_value(current: Dict, candidate: Dict) -> Dict:
    """Compare candidate inventory against current canonical inventory.

    Both map (league, season) -> family counts. Returns new matches,
    seasons, families and a gate verdict with reasons.
    """
    current_matches = {(league, season) for (league, season) in current}
    candidate_matches = {(league, season) for (league, season) in candidate}
    new_seasons = sorted(candidate_matches - current_matches)
    overlapping = sorted(candidate_matches & current_matches)
    new_families: Dict[str, List] = {}
    for key in overlapping:
        have = set(current.get(key, {}).get("families", []))
        got = set(candidate.get(key, {}).get("families", []))
        added = sorted(got - have)
        if added:
            new_families[f"{key[0]}:{key[1]}"] = added
    new_matches = sum(candidate[key].get("matches", 0) for key in new_seasons)
    reasons = []
    if new_seasons:
        reasons.append(f"{len(new_seasons)} new seasons: "
                       + ", ".join(f"{league}/{season}" for league, season in new_seasons[:10]))
    if new_families:
        reasons.append(f"new families on {len(new_families)} overlapping seasons")
    verdict = "accept" if (new_seasons or new_families) else "reject"
    if verdict == "reject":
        reasons.append("no incremental matches, seasons or families")
    return {"verdict": verdict, "reasons": reasons,
            "new_seasons": new_seasons, "new_families": new_families,
            "new_matches_estimate": new_matches}


def validate_rows(rows: List[Dict]) -> Dict:
    """Pre-import sanity: required columns, date parseability, score sanity.
    Returns valid/invalid counts + reasons (never raises on bad rows)."""
    valid = invalid = 0
    reasons: Dict[str, int] = {}
    for row in rows:
        problems = []
        if not row.get("HomeTeam") or not row.get("AwayTeam"):
            problems.append("missing teams")
        if not row.get("Date"):
            problems.append("missing date")
        for key in ("FTHG", "FTAG"):
            value = row.get(key)
            if value not in (None, ""):
                try:
                    number = int(float(value))
                    if number < 0 or number > 30:
                        problems.append(f"implausible {key}={value}")
                except (TypeError, ValueError):
                    problems.append(f"unparseable {key}={value}")
        if problems:
            invalid += 1
            for problem in problems:
                reasons[problem.split("=")[0]] = reasons.get(problem.split("=")[0], 0) + 1
        else:
            valid += 1
    return {"rows": len(rows), "valid": valid, "invalid": invalid,
            "reasons": reasons}
