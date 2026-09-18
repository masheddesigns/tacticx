"""Research datasets: versioned, immutable, chronological (Phase 12).

One chronological pass per league builds team states (Elo, form, venue goal
rates, rest, xG means from bulk-fetched rows, lineup starter sets) and emits
one row per finished match: features per family with availability flags,
label, kickoff. Current/upcoming production data never enters: only
FINISHED matches with scores, and every feature uses strictly earlier
matches. Dataset version = hash of (params + league + seasons + families +
mode), stored with the rows.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Lineup, Match, MatchEvent, MatchStatistic
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.predictions.math_utils import logistic_expected

INDEX = {"home": 0, "draw": 1, "away": 2}
K_FACTOR = 20.0
INITIAL_RATING = 1500.0
HOME_EDGE = 60.0


def dataset_version(params: Dict) -> str:
    digest = hashlib.sha256(json.dumps(params, sort_keys=True,
                                       default=str).encode()).hexdigest()
    return f"research_ds_{digest[:12]}"


def _result(home_score: int, away_score: int) -> float:
    if home_score > away_score:
        return 1.0
    if home_score < away_score:
        return 0.0
    return 0.5


class LeaguePass:
    """Single chronological pass accumulating team states."""

    def __init__(self):
        self.elo: Dict[int, float] = {}
        self.matches: Dict[int, list] = {}  # team_id -> [match,...] oldest first
        self.xg: Dict[int, list] = {}  # team_id -> [xg values] oldest first
        self.starters: Dict[int, list] = {}  # team_id -> [starter-id sets]

    def rating(self, team_id: int) -> float:
        return self.elo.get(team_id, INITIAL_RATING)

    def update(self, match: Match) -> None:
        home, away = match.home_team_id, match.away_team_id
        if home is None or away is None:
            return
        hr, ar = self.rating(home), self.rating(away)
        expected = logistic_expected(hr - ar + HOME_EDGE)
        actual = _result(match.home_score or 0, match.away_score or 0)
        self.elo[home] = hr + K_FACTOR * (actual - expected)
        self.elo[away] = ar + K_FACTOR * ((1.0 - actual) - (1.0 - expected))
        self.matches.setdefault(home, []).append(match)
        self.matches.setdefault(away, []).append(match)


def build_dataset(db: Session, league_code: str, seasons: Optional[List[str]] = None,
                  families: Optional[List[str]] = None,
                  mode: TemporalMode = TemporalMode.STRICT_PREMATCH) -> Dict:
    """Chronological rows for one league. Seasons filter by kickoff-derived
    season label (never manufactured)."""
    from app.services.backtesting.runner import _season_label

    league = db.query(League).filter_by(code=league_code).first()
    if league is None:
        raise ValueError(f"unknown league: {league_code}")
    families = families or ["team"]
    matches = db.query(Match).filter(
        Match.league_id == league.id, Match.status == "FINISHED",
        Match.home_score.is_not(None), Match.away_score.is_not(None),
        Match.kickoff_at.is_not(None),
        Match.home_team_id.is_not(None), Match.away_team_id.is_not(None),
    ).order_by(Match.kickoff_at.asc(), Match.id.asc()).all()
    if seasons:
        matches = [m for m in matches if _season_label(m.kickoff_at) in seasons]
    # Bulk prefetch (indexed, no N+1).
    match_ids = [m.id for m in matches]
    xg_rows = db.query(MatchStatistic).filter(
        MatchStatistic.match_id.in_(match_ids),
        MatchStatistic.stat_name.in_(("expected_goals", "xg"))).all() if match_ids else []
    xg_by_match: Dict[int, Dict[str, list]] = {}
    for row in xg_rows:
        try:
            value = float(str(row.stat_value).rstrip("%"))
        except (TypeError, ValueError):
            continue
        xg_by_match.setdefault(row.match_id, {}).setdefault(row.team, []).append(value)
    lineup_rows = db.query(Lineup).filter(
        Lineup.match_id.in_(match_ids)).all() if match_ids else []
    starters_by_match: Dict[int, Dict[str, set]] = {}
    for row in lineup_rows:
        if row.is_starting and row.player_provider_id:
            side = row.team or ""
            match = next((m for m in matches if m.id == row.match_id), None)
            if match is None:
                continue
            starters_by_match.setdefault(row.match_id, {}).setdefault(side, set()).add(
                row.player_provider_id)
    stat_rows = db.query(MatchStatistic).filter(
        MatchStatistic.match_id.in_(match_ids),
        MatchStatistic.stat_name.in_(("shots_total", "shots_on_target"))).all() \
        if match_ids else []
    shots_by_match: Dict[int, Dict[str, float]] = {}
    for row in stat_rows:
        try:
            value = float(str(row.stat_value).rstrip("%"))
        except (TypeError, ValueError):
            continue
        shots_by_match.setdefault(row.match_id, {}).setdefault(row.team, 0.0)
        shots_by_match[row.match_id][row.team] += value
    league_histories: Dict[int, list] = {}
    for match in matches:
        league_histories.setdefault(match.league_id, []).append(match)

    league_pass = LeaguePass()
    rows = []
    for match in matches:
        home, away = match.home_team_id, match.away_team_id
        features: Dict[str, Optional[float]] = {}
        availability: Dict[str, bool] = {}
        # Team family (always computed; gates below decide eligibility).
        elo_diff = league_pass.rating(home) - league_pass.rating(away)
        home_hist = league_pass.matches.get(home, [])
        away_hist = league_pass.matches.get(away, [])
        features["elo_diff"] = round(elo_diff, 3)
        ppm_h = _ppm(home_hist[-5:], home)
        ppm_a = _ppm(away_hist[-5:], away)
        features["form_ppm_diff_5"] = None if ppm_h is None or ppm_a is None \
            else round(ppm_h - ppm_a, 4)
        gd_h = _gd(home_hist[-5:], home)
        gd_a = _gd(away_hist[-5:], away)
        features["gd_diff_5"] = None if gd_h is None or gd_a is None \
            else round(gd_h - gd_a, 4)
        features["rest_diff"] = _rest_diff(home_hist, away_hist, match.kickoff_at)
        availability["team"] = (len(home_hist) >= 5 and len(away_hist) >= 5
                                and features["form_ppm_diff_5"] is not None)
        # xG family (estimated-only in practice: effective_at unknown).
        xg_ok, xg_val = _xg_diff(league_pass, home, away)
        features["xg_diff_5"] = xg_val
        availability["xg"] = xg_ok
        # Shots family (where available).
        shots_ok, shots_val = _shots_diff(shots_by_match, home_hist, away_hist, home,
                                          away)
        features["shots_diff_5"] = shots_val
        availability["shots"] = shots_ok
        # Player family: starter continuity differential (last-XI overlap).
        cont_ok, cont_val = _continuity_diff(league_pass, starters_by_match, home,
                                             away)
        features["continuity_diff"] = cont_val
        availability["player"] = cont_ok
        # Event family: goal-rate differential from registered events.
        # (Computed in the same pass would need event prefetch; measured via
        # snapshots in the runner. Marked here with coverage from lineups.)
        availability["events"] = cont_ok
        actual = INDEX["home" if (match.home_score or 0) > (match.away_score or 0)
                       else ("draw" if match.home_score == match.away_score else "away")]
        # Update state AFTER emitting (strictly earlier matches only).
        _ingest(league_pass, xg_by_match, starters_by_match, match)
        rows.append({"match_id": match.id, "kickoff": str(match.kickoff_at),
                     "features": features, "availability": availability,
                     "actual": actual,
                     "home_goals": match.home_score, "away_goals": match.away_score})
    params = {"league": league_code, "seasons": seasons or "all",
              "families": sorted(families), "mode": mode.value,
              "n_matches": len(rows)}
    return {"dataset_version": dataset_version(params), "params": params,
            "rows": rows}


def _ppm(past: list, team_id: int):
    if len(past) < 3:
        return None
    pts = 0
    for m in past:
        hs, aws = m.home_score or 0, m.away_score or 0
        if m.home_team_id == team_id:
            pts += 3 if hs > aws else (1 if hs == aws else 0)
        else:
            pts += 3 if aws > hs else (1 if hs == aws else 0)
    return pts / len(past)


def _gd(past: list, team_id: int):
    if len(past) < 3:
        return None
    total = 0
    for m in past:
        hs, aws = m.home_score or 0, m.away_score or 0
        total += (hs - aws) if m.home_team_id == team_id else (aws - hs)
    return total / len(past)


def _rest_diff(home_hist: list, away_hist: list, kickoff) -> Optional[float]:
    from app.services.features.temporal import as_naive_utc

    def last(hist):
        kicks = [as_naive_utc(m.kickoff_at) for m in hist if m.kickoff_at]
        return max(kicks) if kicks else None

    lh, la = last(home_hist), last(away_hist)
    naive = as_naive_utc(kickoff)
    if lh is None or la is None or naive is None:
        return None
    return round((naive - lh).total_seconds() / 86400.0
                 - (naive - la).total_seconds() / 86400.0, 2)


def _xg_diff(league_pass: LeaguePass, home: int, away: int):
    home_xg = league_pass.xg.get(home, [])[-5:]
    away_xg = league_pass.xg.get(away, [])[-5:]
    if len(home_xg) < 3 or len(away_xg) < 3:
        return False, None
    return True, round(sum(home_xg) / len(home_xg) - sum(away_xg) / len(away_xg), 4)


def _shots_diff(shots_by_match: Dict, home_hist: list, away_hist: list,
                home: int, away: int):
    home_vals, away_vals = [], []
    for m in home_hist[-5:]:
        side = "home" if m.home_team_id == home else "away"
        value = (shots_by_match.get(m.id) or {}).get(side)
        if value is not None:
            home_vals.append(value)
    for m in away_hist[-5:]:
        side = "home" if m.home_team_id == away else "away"
        value = (shots_by_match.get(m.id) or {}).get(side)
        if value is not None:
            away_vals.append(value)
    if len(home_vals) < 3 or len(away_vals) < 3:
        return False, None
    return True, round(sum(home_vals) / len(home_vals) - sum(away_vals) / len(away_vals), 3)


def _continuity_diff(league_pass: LeaguePass, starters_by_match: Dict,
                     home: int, away: int):
    home_sets = league_pass.starters.get(home, [])
    away_sets = league_pass.starters.get(away, [])
    if not home_sets or not away_sets:
        return False, None

    def overlap(sets):
        if len(sets) < 2:
            return None
        prev, current = sets[-2], sets[-1]
        union = prev | current
        return len(prev & current) / len(union) if union else None

    home_o, away_o = overlap(home_sets), overlap(away_sets)
    if home_o is None or away_o is None:
        return False, None
    return True, round(home_o - away_o, 4)


def _ingest(league_pass: LeaguePass, xg_by_match: Dict,
            starters_by_match: Dict, match: Match) -> None:
    league_pass.update(match)
    home, away = match.home_team_id, match.away_team_id
    for team_id, side in ((home, "home"), (away, "away")):
        values = (xg_by_match.get(match.id) or {}).get(side, [])
        if values:
            league_pass.xg.setdefault(team_id, []).append(sum(values) / len(values))
        starters = (starters_by_match.get(match.id) or {}).get(side, set())
        if starters:
            league_pass.starters.setdefault(team_id, []).append(set(starters))
