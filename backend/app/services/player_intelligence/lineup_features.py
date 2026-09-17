"""Historical lineup + formation features (Phase 9).

Timing rule: lineup rows carry effective_at=NULL in this dataset, so strict
mode reports them unavailable (honest) and estimated mode marks them
estimated (parent-anchored). The target lineup is never historical
information. Formation claims are descriptive (frequency/entropy/stability),
never causal ("formation X causes wins" is not generated).
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.features.temporal import TemporalMode
from app.services.player_intelligence.repository import PlayerEventRepository


def _env(value, available: bool, source: str, as_of: str, quality: str,
         method: str) -> Dict:
    return {"value": value, "available": available, "source": source,
            "as_of": as_of, "quality": quality, "aggregation": method}


def lineup_features(db: Session, team_id: int, cutoff: datetime,
                    mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                    target_match_id=None) -> Dict:
    """Continuity + formation features over eligible historical lineups."""
    from app.services.features.temporal import as_naive_utc

    repo = PlayerEventRepository(db, cutoff, mode, target_match_id)
    lineups = repo.team_lineups_before(team_id)
    as_of = str(as_naive_utc(cutoff))
    quality = "estimated" if mode == TemporalMode.HISTORICAL_ESTIMATED else "strict"
    matches: Dict[int, List] = {}
    for match, lineup, _ in lineups:
        matches.setdefault(match.id, []).append(lineup)
    ordered_ids = sorted(matches)
    if not ordered_ids:
        return {"mode": mode.value, "as_of": as_of,
                "status": "unavailable",
                "reason": "no eligible historical lineups under this mode "
                          "(strict requires explicit effective_at; dataset rows "
                          "carry none)",
                "matches_considered": 0}
    starters_per_match = []
    formations = []
    for mid in ordered_ids:
        starters = {str(r.player_provider_id) for r in matches[mid] if r.is_starting}
        starters_per_match.append(starters)
        forms = {r.formation for r in matches[mid] if r.formation}
        formations.append(sorted(forms)[0] if forms else "")
    # Starting XI continuity: overlap of consecutive starter sets.
    overlaps = []
    for prev, current in zip(starters_per_match, starters_per_match[1:]):
        union = prev | current
        overlaps.append(len(prev & current) / len(union) if union else None)
    overlaps = [o for o in overlaps if o is not None]
    known_forms = [f for f in formations if f]
    freq = Counter(known_forms)
    total = sum(freq.values())
    entropy = (-sum((c / total) * math.log(c / total) for c in freq.values())
               if total else None)
    recent = known_forms[-5:]
    stability = (recent.count(freq.most_common(1)[0][0]) / len(recent)
                 if recent and freq else None)
    return {
        "mode": mode.value, "as_of": as_of, "status": "ok",
        "matches_considered": len(ordered_ids),
        "starting_xi_continuity": _env(
            round(sum(overlaps) / len(overlaps), 4) if overlaps else None,
            bool(overlaps), "lineups", as_of, quality,
            "mean Jaccard overlap of consecutive starter sets"),
        "starter_minutes_continuity": _env(
            None, False, "lineups", as_of, quality,
            "minutes unavailable in lineup schema"),
        "formation_frequency": _env(
            dict(freq) if freq else None, bool(freq), "lineups", as_of,
            quality, "counts over eligible historical matches"),
        "formation_entropy": _env(
            round(entropy, 4) if entropy is not None else None,
            entropy is not None, "lineups", as_of, quality,
            "Shannon entropy of formation distribution (descriptive)"),
        "formation_stability": _env(
            round(stability, 4) if stability is not None else None,
            stability is not None, "lineups", as_of, quality,
            "share of last <=5 matches using the modal formation"),
        "most_frequent_formation": _env(
            freq.most_common(1)[0][0] if freq else None, bool(freq),
            "lineups", as_of, quality, "mode of formation distribution"),
    }
