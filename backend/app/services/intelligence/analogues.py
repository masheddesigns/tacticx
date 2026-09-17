"""Historical analogues (Phase 6).

Finds past matches with similar PRE-MATCH characteristics using standardized
Euclidean distance. Similarity inputs are strictly pre-cutoff: Elo ratings,
form, goal rates, rest, xG where mode-eligible. Never the target outcome,
post-match statistics, or the result. The target match is structurally
excluded (it is not finished-before its own cutoff).

Outcome frequencies over analogues are descriptive, gated by a minimum
sample, and never presented as a forecast.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.services.features.repository import HistoricalFeatureRepository
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.intelligence.schemas import (
    AnalogueResult,
    LayerProvenance,
)

MIN_ANALOGUES = 20
MAX_CANDIDATES = 2000
FEATURES = ("elo_diff", "form_ppm_diff", "goal_diff_diff", "rest_diff",
            "total_goals_avg")

_ratings_cache: Dict[str, Dict[int, float]] = {}


def _candidate_vector(db: Session, repo: HistoricalFeatureRepository,
                      match: Match, mode: TemporalMode) -> Optional[List[float]]:
    """Pre-match feature vector for a historical match, evaluated with the
    historical match's own kickoff as cutoff (never the target's cutoff)."""
    from app.services.predictions.elo import EloModel

    if match.home_team_id is None or match.away_team_id is None:
        return None
    if match.kickoff_at is None:
        return None
    hist_cutoff = as_naive_utc(match.kickoff_at)
    if hist_cutoff is None:
        return None
    hist_repo = HistoricalFeatureRepository(db, hist_cutoff, mode)
    league_hist = hist_repo.finished_before(league_id=match.league_id)
    cache_key = f"{id(db)}:{match.league_id}:{hist_cutoff.isoformat()}"
    ratings = _ratings_cache.get(cache_key)
    if ratings is None:
        ratings = EloModel().fit(league_hist)
        _ratings_cache[cache_key] = ratings
    home_r = ratings.get(match.home_team_id, 1500.0)
    away_r = ratings.get(match.away_team_id, 1500.0)
    home_past = [m for m in hist_repo.team_matches_before(match.home_team_id)][-5:]
    away_past = [m for m in hist_repo.team_matches_before(match.away_team_id)][-5:]
    if len(home_past) < 3 or len(away_past) < 3:
        return None

    def ppm(past, team_id):
        pts = 0
        for m in past:
            hs, aws = m.home_score or 0, m.away_score or 0
            if m.home_team_id == team_id:
                pts += 3 if hs > aws else (1 if hs == aws else 0)
            else:
                pts += 3 if aws > hs else (1 if hs == aws else 0)
        return pts / max(1, len(past))

    def gd(past, team_id):
        total = 0
        for m in past:
            hs, aws = m.home_score or 0, m.away_score or 0
            total += (hs - aws) if m.home_team_id == team_id else (aws - hs)
        return total / max(1, len(past))

    def rest(past):
        if not past:
            return 0.0
        last = max(as_naive_utc(m.kickoff_at) for m in past if m.kickoff_at)
        if last is None:
            return 0.0
        return max(0.0, (hist_cutoff - last).total_seconds() / 86400.0)

    total_avg = sum((m.home_score or 0) + (m.away_score or 0) for m in league_hist[-20:]) / \
        max(1, min(20, len(league_hist)))
    return [home_r - away_r, ppm(home_past, match.home_team_id) - ppm(away_past, match.away_team_id),
            gd(home_past, match.home_team_id) - gd(away_past, match.away_team_id),
            rest(home_past) - rest(away_past), total_avg]


def _target_vector(db: Session, match: Match, cutoff: datetime,
                   mode: TemporalMode) -> Optional[List[float]]:
    repo = HistoricalFeatureRepository(db, cutoff, mode)
    pseudo = Match(home_team_id=match.home_team_id, away_team_id=match.away_team_id,
                   league_id=match.league_id, kickoff_at=cutoff)
    return _candidate_vector(db, repo, pseudo, mode)


def find_analogues(db: Session, match_id: int, cutoff: datetime,
                   mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                   top_k: int = 10, min_sample: int = MIN_ANALOGUES) -> AnalogueResult:
    """Standardized-distance analogues over pre-cutoff finished league matches."""
    match = db.get(Match, match_id)
    if match is None:
        raise ValueError(f"unknown match: {match_id}")
    naive_cutoff = as_naive_utc(cutoff)
    if naive_cutoff is None:
        raise ValueError("cutoff is required")
    repo = HistoricalFeatureRepository(db, cutoff, mode)
    pool = [m for m in repo.finished_before(league_id=match.league_id)
            if m.id != match_id][:MAX_CANDIDATES]
    target = _target_vector(db, match, cutoff, mode)
    if target is None:
        return AnalogueResult(
            status="insufficient_sample",
            methodology="standardized Euclidean distance over pre-match features; "
                        "target vector unavailable",
            provenance=_prov(match_id, cutoff, mode))
    vecs: List[Tuple[Match, List[float]]] = []
    for cand in pool:
        vec = _candidate_vector(db, repo, cand, mode)
        if vec is None:
            continue
        vecs.append((cand, vec))
    if len(vecs) < min_sample:
        return AnalogueResult(
            status="insufficient_sample",
            methodology="standardized Euclidean distance over pre-match features "
                        f"(features: {', '.join(FEATURES)}); "
                        f"{len(vecs)} eligible candidates < minimum {min_sample}",
            provenance=_prov(match_id, cutoff, mode))
    # Standardize once over the pool + target (common space), then measure.
    matrix = _standardize([target] + [v for _, v in vecs])
    target_std, pool_std = matrix[0], matrix[1:]
    scored: List[Tuple[float, Match]] = []
    for (cand, _), std in zip(vecs, pool_std):
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(target_std, std)))
        scored.append((dist, cand))
    scored.sort(key=lambda t: t[0])
    top = scored[:max(1, min(top_k, len(scored)))]
    max_dist = top[-1][0] if top[-1][0] > 0 else 1.0
    analogues = []
    for dist, cand in top:
        analogues.append({
            "match_id": cand.id,
            "kickoff_at": str(cand.kickoff_at),
            "home_team_id": cand.home_team_id,
            "away_team_id": cand.away_team_id,
            "actual": ("home" if (cand.home_score or 0) > (cand.away_score or 0)
                       else ("draw" if cand.home_score == cand.away_score else "away")),
            "home_score": cand.home_score, "away_score": cand.away_score,
            "distance": round(dist, 6),
            "similarity": round(max(0.0, 1.0 - dist / (max_dist + dist)), 4),
        })
    counts = {"home": 0, "draw": 0, "away": 0}
    for _, cand in scored:
        if (cand.home_score or 0) > (cand.away_score or 0):
            counts["home"] += 1
        elif cand.home_score == cand.away_score:
            counts["draw"] += 1
        else:
            counts["away"] += 1
    total = sum(counts.values())
    return AnalogueResult(
        status="ok", analogues=analogues,
        outcome_distribution={
            "n": total,
            "home": round(counts["home"] / total, 4),
            "draw": round(counts["draw"] / total, 4),
            "away": round(counts["away"] / total, 4),
            "note": "Descriptive frequency over similar pre-match situations; "
                    "not a forecast and never a guarantee.",
        },
        methodology="standardized Euclidean distance over pre-match features "
                    f"({', '.join(FEATURES)}); candidates are finished matches "
                    "with kickoff strictly before the target cutoff, evaluated "
                    "at their own kickoff; target outcome and post-match data "
                    "never used",
        provenance=_prov(match_id, cutoff, mode))


def _standardize(rows: List[List[float]]) -> List[List[float]]:
    cols = list(zip(*rows))
    out = []
    for col in cols:
        mean = sum(col) / len(col)
        var = sum((v - mean) ** 2 for v in col) / len(col)
        scale = math.sqrt(var) if var > 0 else 1.0
        out.append([(v - mean) / scale for v in col])
    return [list(r) for r in zip(*out)]


def _prov(match_id: int, cutoff: datetime, mode: TemporalMode) -> LayerProvenance:
    return LayerProvenance(source="historical_analogues", cutoff=str(as_naive_utc(cutoff)),
                           temporal_mode=mode.value)
