"""Temporal feature engineering (Phase 4).

Every builder consumes ONLY pre-cutoff finished matches (kickoff < cutoff)
and mode-eligible stat rows from HistoricalFeatureRepository. The target
match never appears in its own features — enforced structurally (callers
pass history lists that exclude it) and tested explicitly.

Conventions:
- history lists are oldest-first; rolling windows take the tail (most recent).
- recency weights use configurable half-lives: w = exp(-ln(2) * age / half_life).
- every leaf carries {value, available, source, as_of, quality}; missing data
  yields available=False + reason, never an invented number.
- feature_version "features_v1" is stamped on every snapshot.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.core import Match
from app.services.features.repository import HistoricalFeatureRepository
from app.services.features.temporal import TemporalMode, as_naive_utc, season_label
from app.services.predictions.elo import EloModel

FEATURE_VERSION = "features_v1"


@dataclass
class FeatureConfig:
    form_windows: Tuple[int, ...] = (3, 5, 10)
    form_half_life_days: float = 120.0
    xg_half_life_days: float = 180.0
    min_form_matches: int = 3
    min_xg_matches: int = 5
    min_h2h_matches: int = 3

    @classmethod
    def from_settings(cls) -> "FeatureConfig":
        settings = get_settings()
        return cls(
            form_half_life_days=float(settings.FORM_DECAY_HALF_LIFE_DAYS),
            xg_half_life_days=float(settings.XG_DECAY_HALF_LIFE_DAYS),
            min_form_matches=int(settings.MIN_FORM_MATCHES),
            min_xg_matches=int(settings.MIN_XG_MATCHES),
            min_h2h_matches=int(settings.MIN_H2H_MATCHES),
        )

    def as_dict(self) -> Dict:
        return {
            "form_windows": list(self.form_windows),
            "form_half_life_days": self.form_half_life_days,
            "xg_half_life_days": self.xg_half_life_days,
            "min_form_matches": self.min_form_matches,
            "min_xg_matches": self.min_xg_matches,
            "min_h2h_matches": self.min_h2h_matches,
            "feature_version": FEATURE_VERSION,
        }


def decay_from_half_life(half_life_days: float) -> float:
    """Exponential decay constant from a configured half-life. No magic numbers."""
    if half_life_days <= 0:
        raise ValueError("half-life must be positive")
    return math.log(2.0) / half_life_days


def exp_weights(ages_days: List[float], half_life_days: float) -> List[float]:
    decay = decay_from_half_life(half_life_days)
    return [math.exp(-decay * max(0.0, age)) for age in ages_days]


def _ages_days(matches: List[Match], cutoff: datetime) -> List[float]:
    naive_cutoff = as_naive_utc(cutoff)
    ages = []
    for match in matches:
        kickoff = as_naive_utc(match.kickoff_at)
        if kickoff is None or naive_cutoff is None:
            ages.append(0.0)
        else:
            ages.append(max(0.0, (naive_cutoff - kickoff).total_seconds() / 86400.0))
    return ages


def _outcome_for(team_id: int, match: Match) -> Optional[str]:
    if match.home_score is None or match.away_score is None:
        return None
    home = match.home_team_id == team_id
    scored = match.home_score if home else match.away_score
    conceded = match.away_score if home else match.home_score
    if scored is None or conceded is None:
        return None
    if scored > conceded:
        return "win"
    if scored < conceded:
        return "loss"
    return "draw"


def rolling_form(matches: List[Match], team_id: int, window: int,
                 venue: Optional[str] = None) -> Dict:
    """W/D/L, goals, points over the team's last `window` pre-cutoff matches."""
    pool = [m for m in matches
            if (venue is None
                or (venue == "home" and m.home_team_id == team_id)
                or (venue == "away" and m.away_team_id == team_id))]
    recent = pool[-window:] if window > 0 else pool
    wins = draws = losses = goals_for = goals_against = 0
    counted = 0
    for match in recent:
        outcome = _outcome_for(team_id, match)
        if outcome is None:
            continue
        counted += 1
        home = match.home_team_id == team_id
        scored = match.home_score if home else match.away_score
        conceded = match.away_score if home else match.home_score
        goals_for += scored or 0
        goals_against += conceded or 0
        if outcome == "win":
            wins += 1
        elif outcome == "draw":
            draws += 1
        else:
            losses += 1
    points = 3 * wins + draws
    return {
        "matches": counted,
        "wins": wins, "draws": draws, "losses": losses,
        "goals_for": goals_for, "goals_against": goals_against,
        "goal_difference": goals_for - goals_against,
        "points": points,
        "points_per_match": round(points / counted, 4) if counted else 0.0,
    }


def weighted_form(matches: List[Match], team_id: int, half_life_days: float,
                  cutoff: datetime, venue: Optional[str] = None) -> Dict:
    """Recency-weighted points-per-match and goal difference."""
    pool = [m for m in matches
            if (venue is None
                or (venue == "home" and m.home_team_id == team_id)
                or (venue == "away" and m.away_team_id == team_id))]
    if not pool:
        return {"points_per_match": 0.0, "goal_difference_per_match": 0.0,
                "weight_sum": 0.0, "matches": 0}
    weights = exp_weights(_ages_days(pool, cutoff), half_life_days)
    ppm_num = gd_num = weight_sum = 0.0
    counted = 0
    for match, weight in zip(pool, weights):
        outcome = _outcome_for(team_id, match)
        if outcome is None:
            continue
        counted += 1
        home = match.home_team_id == team_id
        scored = match.home_score if home else match.away_score
        conceded = match.away_score if home else match.home_score
        points = 3.0 if outcome == "win" else (1.0 if outcome == "draw" else 0.0)
        ppm_num += points * weight
        gd_num += ((scored or 0) - (conceded or 0)) * weight
        weight_sum += weight
    if weight_sum <= 0:
        return {"points_per_match": 0.0, "goal_difference_per_match": 0.0,
                "weight_sum": 0.0, "matches": counted}
    return {"points_per_match": round(ppm_num / weight_sum, 4),
            "goal_difference_per_match": round(gd_num / weight_sum, 4),
            "weight_sum": round(weight_sum, 4), "matches": counted}


def rolling_statistic(series: List[Tuple[datetime, float]], window: int,
                      half_life_days: Optional[float] = None,
                      cutoff: Optional[datetime] = None) -> Dict:
    """Mean over the last `window` observations, optional recency weighting.
    Series must be oldest-first (repository guarantees this)."""
    recent = series[-window:] if window > 0 else list(series)
    values = [v for _, v in recent]
    if not values:
        return {"mean": 0.0, "count": 0, "weighted_mean": 0.0}
    mean = sum(values) / len(values)
    weighted_mean = mean
    if half_life_days is not None and cutoff is not None:
        ages = [(as_naive_utc(cutoff) - as_naive_utc(ts)).total_seconds() / 86400.0
                if ts is not None and cutoff is not None else 0.0
                for ts, _ in recent]
        weights = exp_weights(ages, half_life_days)
        total = sum(weights)
        if total > 0:
            weighted_mean = sum(v * w for v, w in zip(values, weights)) / total
    return {"mean": round(mean, 4), "count": len(values),
            "weighted_mean": round(weighted_mean, 4)}


def rest_and_congestion(team_matches: List[Match], cutoff: datetime) -> Dict:
    """Days since previous finished match + recent density. Finished matches
    only — postponed/non-played rows never appear in these lists, so missing
    previous fixtures yield available=False rather than an invented zero."""
    naive_cutoff = as_naive_utc(cutoff)
    if not team_matches or naive_cutoff is None:
        return {"days_since_previous": None, "last_7": 0, "last_14": 0,
                "last_30": 0, "previous_known": False}
    kickoffs = [as_naive_utc(m.kickoff_at) for m in team_matches]
    kickoffs = [k for k in kickoffs if k is not None and k < naive_cutoff]
    if not kickoffs:
        return {"days_since_previous": None, "last_7": 0, "last_14": 0,
                "last_30": 0, "previous_known": False}
    last = max(kickoffs)
    days = (naive_cutoff - last).total_seconds() / 86400.0
    return {
        "days_since_previous": round(days, 2),
        "last_7": sum(1 for k in kickoffs if (naive_cutoff - k).days < 7),
        "last_14": sum(1 for k in kickoffs if (naive_cutoff - k).days < 14),
        "last_30": sum(1 for k in kickoffs if (naive_cutoff - k).days < 30),
        "previous_known": True,
    }


def season_context(team_matches: List[Match], league_matches: List[Match],
                   cutoff: datetime) -> Dict:
    """Season-scoped counts. Seasons use the Aug–Jul label; final-season
    totals are never used — only matches strictly before the cutoff."""
    naive_cutoff = as_naive_utc(cutoff)
    season = season_label(naive_cutoff) if naive_cutoff else "unknown"
    team_season = [m for m in team_matches if season_label(m.kickoff_at) == season]
    league_season = [m for m in league_matches if season_label(m.kickoff_at) == season]
    return {
        "season": season,
        "season_match_number": len(team_season) + 1,
        "team_matches_played": len(team_season),
        "league_matches_played": len(league_season),
    }


def standings_at_cutoff(db, league_id: int, cutoff: datetime) -> Dict[int, Dict]:
    """Reconstruct the CURRENT-SEASON league table from pre-cutoff results.

    Standard 3-1-0 scoring, sorted by points, goal difference, goals scored.
    Only matches from the cutoff's season (Aug–Jul label) count — career
    aggregates across seasons would misrepresent table position. The
    final-season table is never consulted. Teams with no pre-cutoff matches
    this season are absent (not zero-filled).
    """
    repo = HistoricalFeatureRepository(db, cutoff)
    season = season_label(cutoff)
    rows = [m for m in repo.finished_before(league_id=league_id)
            if season_label(m.kickoff_at) == season]
    table: Dict[int, Dict] = {}
    for match in rows:
        if match.home_team_id is None or match.away_team_id is None:
            continue
        for team_id, scored, conceded in (
                (match.home_team_id, match.home_score, match.away_score),
                (match.away_team_id, match.away_score, match.home_score)):
            if scored is None or conceded is None:
                continue
            entry = table.setdefault(team_id, {"played": 0, "won": 0, "drawn": 0,
                                               "lost": 0, "gf": 0, "ga": 0, "points": 0})
            entry["played"] += 1
            entry["gf"] += scored
            entry["ga"] += conceded
            if scored > conceded:
                entry["won"] += 1
                entry["points"] += 3
            elif scored < conceded:
                entry["lost"] += 1
            else:
                entry["drawn"] += 1
                entry["points"] += 1
    ordered = sorted(table.items(),
                     key=lambda kv: (kv[1]["points"], kv[1]["gf"] - kv[1]["ga"], kv[1]["gf"]),
                     reverse=True)
    result = {}
    for position, (team_id, entry) in enumerate(ordered, start=1):
        entry["position"] = position
        entry["goal_difference"] = entry["gf"] - entry["ga"]
        result[team_id] = entry
    return result


def head_to_head(db, home_id: int, away_id: int, cutoff: datetime,
                 minimum: int = 3):
    """Descriptive H2H from pre-cutoff finished meetings. Returns None when
    below minimum sample — small samples must not dominate any model."""
    repo = HistoricalFeatureRepository(db, cutoff, TemporalMode.STRICT_PREMATCH)
    meetings = [m for m in repo.finished_before()
                if {m.home_team_id, m.away_team_id} == {home_id, away_id}]
    if len(meetings) < minimum:
        return None
    home_wins = draws = away_wins = 0
    for m in meetings:
        if m.home_team_id == home_id:
            if (m.home_score or 0) > (m.away_score or 0):
                home_wins += 1
            elif (m.home_score or 0) < (m.away_score or 0):
                away_wins += 1
            else:
                draws += 1
        else:
            if (m.away_score or 0) > (m.home_score or 0):
                home_wins += 1
            elif (m.away_score or 0) < (m.home_score or 0):
                away_wins += 1
            else:
                draws += 1
    return {"matches": len(meetings), "home_wins": home_wins,
            "draws": draws, "away_wins": away_wins}


def opponent_elos(db, team_matches: List[Match], team_id: int, cutoff: datetime,
                  league_id=None) -> Dict:
    """Strength of schedule from historical Elo ratings of opponents faced.

    Ratings come from EloModel.fit over pre-cutoff league history — never
    future ratings. Empty when the team has no pre-cutoff opponents.
    """
    from app.services.predictions.elo import EloModel

    if not team_matches:
        return {"average": None, "weighted": None, "opponents": 0}
    repo = HistoricalFeatureRepository(db, cutoff)
    ratings = EloModel().fit(repo.finished_before(league_id=league_id))
    default = EloModel().config.initial_rating
    recent = team_matches[-10:]
    pairs = []
    for m in recent:
        opp = m.away_team_id if m.home_team_id == team_id else m.home_team_id
        if opp is not None:
            pairs.append((ratings.get(opp, default), m.kickoff_at))
    if not pairs:
        return {"average": None, "weighted": None, "opponents": 0}
    opps = [r for r, _ in pairs]
    naive_cutoff = as_naive_utc(cutoff)
    ages = []
    for _, kickoff in pairs:
        naive_kickoff = as_naive_utc(kickoff)
        if naive_kickoff is None or naive_cutoff is None:
            ages.append(0.0)
        else:
            ages.append(max(0.0, (naive_cutoff - naive_kickoff).total_seconds() / 86400.0))
    weights = exp_weights(ages, FeatureConfig().form_half_life_days)
    total_w = sum(weights) or 1.0
    weighted = sum(r * w for r, w in zip(opps, weights)) / total_w
    return {"average": round(sum(opps) / len(opps), 2),
            "weighted": round(weighted, 2),
            "opponents": len(opps)}


def _env(value, available: bool, source: str, as_of: str, quality: str = "ok") -> Dict:
    """One feature envelope: value + availability + provenance + quality."""
    return {"value": value, "available": bool(available), "source": source,
            "as_of": as_of, "quality": quality if available else "unavailable"}


def build_feature_snapshot(db, match_id: int, cutoff: datetime,
                           mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                           config: Optional[FeatureConfig] = None) -> Dict:
    """Reproducible pre-match feature snapshot (features_v1).

    Every input derives from pre-cutoff finished matches or mode-eligible
    stat rows. The target match never contributes. Missing data yields
    available=False envelopes — never invented numbers.
    """
    from app.db.models.core import Match as MatchModel

    config = config or FeatureConfig.from_settings()
    match = db.get(MatchModel, match_id)
    if match is None:
        raise ValueError(f"unknown match: {match_id}")
    naive_cutoff = as_naive_utc(cutoff)
    if naive_cutoff is None:
        raise ValueError("cutoff is required")
    as_of = naive_cutoff.isoformat()
    repo = HistoricalFeatureRepository(db, cutoff, mode)
    home_id, away_id = match.home_team_id, match.away_team_id
    league_id = match.league_id

    home_hist = repo.team_matches_before(home_id) if home_id is not None else []
    away_hist = repo.team_matches_before(away_id) if away_id is not None else []
    league_hist = repo.finished_before(league_id=league_id)

    # Elo from the same pre-cutoff history the Elo model itself uses.
    from app.services.predictions.elo import EloModel

    elo_model = EloModel()
    ratings = elo_model.fit(league_hist)
    home_elo = ratings.get(home_id, elo_model.config.initial_rating) \
        if home_id is not None else None
    away_elo = ratings.get(away_id, elo_model.config.initial_rating) \
        if away_id is not None else None

    standings = standings_at_cutoff(db, league_id, cutoff) if league_id is not None else {}
    home_table = standings.get(home_id, {}) if home_id is not None else {}
    away_table = standings.get(away_id, {}) if away_id is not None else {}

    def team_block(team_id, hist, opp_hist) -> Dict:
        n = len(hist)
        form_ok = n >= config.min_form_matches
        block: Dict = {"team_id": team_id}
        for window in config.form_windows:
            form = rolling_form(hist, team_id, window)
            block[f"form_last_{window}"] = _env(
                form, form_ok and form["matches"] > 0, "matches:pre-cutoff", as_of,
                "ok" if form_ok else f"only {n} pre-cutoff matches")
            gd = (form["goal_difference"] / form["matches"]) if form["matches"] else 0.0
            block[f"avg_goal_difference_{window}"] = _env(
                round(gd, 4), form_ok and form["matches"] > 0,
                "matches:pre-cutoff", as_of,
                "ok" if form_ok else f"only {n} pre-cutoff matches")
        weighted = weighted_form(hist, team_id, config.form_half_life_days, cutoff)
        block["weighted_goal_difference"] = _env(
            weighted["goal_difference_per_match"], form_ok, "matches:pre-cutoff",
            as_of, "ok" if form_ok else f"only {n} pre-cutoff matches")
        for venue in ("home", "away"):
            venue_hist = [m for m in hist
                          if (venue == "home" and m.home_team_id == team_id)
                          or (venue == "away" and m.away_team_id == team_id)]
            venue_form = rolling_form(hist, team_id, max(config.form_windows), venue=venue)
            block[f"{venue}_form"] = _env(
                venue_form, form_ok, "matches:pre-cutoff:venue", as_of,
                "ok" if form_ok else f"only {n} pre-cutoff matches")
        # xG / shots rolling from eligible stat rows (mode-filtered).
        xg_series = repo.stat_series(team_id, "expected_goals") + \
            repo.stat_series(team_id, "xg")
        xg_series.sort(key=lambda pair: pair[0])
        xg_ok = len(xg_series) >= config.min_xg_matches
        for window in (3, 5, 10):
            rolled = rolling_statistic(
                xg_series, window, config.xg_half_life_days, cutoff)
            block[f"xg_last_{window}"] = _env(
                rolled, xg_ok, "match_statistics:expected_goals", as_of,
                "ok" if xg_ok else f"only {len(xg_series)} xG observations")
        shots_series = repo.stat_series(team_id, "shots_total")
        shots_series.sort(key=lambda pair: pair[0])
        shots = rolling_statistic(shots_series, 5)
        block["shots_per_match_5"] = _env(
            shots, len(shots_series) >= config.min_form_matches,
            "match_statistics:shots_total", as_of,
            "ok" if len(shots_series) >= config.min_form_matches
            else f"only {len(shots_series)} shot observations")
        rest = rest_and_congestion(hist, cutoff)
        block["rest_days"] = _env(
            rest["days_since_previous"], rest["previous_known"],
            "matches:pre-cutoff", as_of,
            "ok" if rest["previous_known"] else "no previous finished match")
        block["congestion"] = _env(
            {"last_7": rest["last_7"], "last_14": rest["last_14"],
             "last_30": rest["last_30"]},
            rest["previous_known"], "matches:pre-cutoff", as_of,
            "ok" if rest["previous_known"] else "no previous finished match")
        ctx = season_context(hist, league_hist, cutoff)
        block["season_context"] = _env(ctx, True, "matches:pre-cutoff", as_of)
        table = home_table if team_id == home_id else away_table
        block["standings"] = _env(
            {"position": table.get("position"), "points": table.get("points"),
             "played": table.get("played")},
            bool(table), "standings:reconstructed:pre-cutoff", as_of,
            "ok" if table else "team absent from reconstructed table")
        sos = opponent_elos(db, hist, team_id, cutoff, league_id)
        block["strength_of_schedule"] = _env(
            sos, sos["opponents"] > 0, "elo_v1:opponents:pre-cutoff", as_of,
            "ok" if sos["opponents"] > 0 else "no pre-cutoff opponents")
        return block

    home_block = team_block(home_id, home_hist, away_hist) if home_id is not None else {}
    away_block = team_block(away_id, away_hist, home_hist) if away_id is not None else {}
    h2h = head_to_head(db, home_id, away_id, cutoff, config.min_h2h_matches) \
        if home_id is not None and away_id is not None else None
    return {
        "match_id": match_id,
        "cutoff": as_of,
        "feature_version": FEATURE_VERSION,
        "temporal_mode": mode.value,
        "home_team": home_block,
        "away_team": away_block,
        "elo": _env(
            {"home_rating": home_elo, "away_rating": away_elo,
             "diff": (round(home_elo - away_elo, 2)
                      if home_elo is not None and away_elo is not None else None)},
            home_elo is not None and away_elo is not None, "elo_v1:pre-cutoff",
            as_of),
        "h2h": _env(
            h2h, h2h is not None, "matches:pre-cutoff:h2h", as_of,
            "ok" if h2h is not None else
            f"fewer than {config.min_h2h_matches} pre-cutoff meetings"),
        "availability": feature_availability_matrix(db, match_id, cutoff, mode, config),
    }


def feature_availability_matrix(db, match_id: int, cutoff: datetime,
                                mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                                config: Optional[FeatureConfig] = None) -> Dict:
    """Per-feature strict/estimated availability for one match.

    Results-derived features share one rule (pre-cutoff finished matches);
    stat-backed features additionally require mode-eligible rows. Closing
    odds and target-match statistics are False in both modes, always.
    """
    from app.db.models.core import Match as MatchModel

    config = config or FeatureConfig.from_settings()
    match = db.get(MatchModel, match_id)
    matrix: Dict[str, Dict[str, bool]] = {}

    def _row(strict: bool, estimated: bool, note: str = "") -> Dict:
        return {"strict": bool(strict), "estimated": bool(estimated), "note": note}

    if match is None or match.home_team_id is None or match.away_team_id is None:
        for name in ("elo", "goals", "form", "home_away", "xg", "shots", "standings",
                     "rest", "events", "lineups", "possession", "closing_odds",
                     "target_stats", "h2h", "strength_of_schedule"):
            matrix[name] = _row(False, False, "match or teams missing")
        return matrix

    for repo_mode, key in ((TemporalMode.STRICT_PREMATCH, "strict"),
                           (TemporalMode.HISTORICAL_ESTIMATED, "estimated")):
        repo = HistoricalFeatureRepository(db, cutoff, repo_mode)
        home_hist = repo.team_matches_before(match.home_team_id)
        away_hist = repo.team_matches_before(match.away_team_id)
        goals_ok = (len(home_hist) >= config.min_form_matches
                    and len(away_hist) >= config.min_form_matches)
        xg_home = len(repo.team_xg_before(match.home_team_id))
        xg_away = len(repo.team_xg_before(match.away_team_id))
        xg_ok = (xg_home >= config.min_xg_matches and xg_away >= config.min_xg_matches)
        shots_ok = bool(repo.stat_series(match.home_team_id, "shots_total")
                        or repo.stat_series(match.away_team_id, "shots_total"))
        if key == "strict":
            matrix["elo"] = _row(goals_ok, False, "")
            matrix["goals"] = _row(goals_ok, False, "")
            matrix["form"] = _row(goals_ok, False, "")
            matrix["home_away"] = _row(goals_ok, False, "")
            matrix["xg"] = _row(xg_ok, False,
                                "" if xg_ok else "insufficient explicitly-timed xG rows")
            matrix["shots"] = _row(shots_ok, False, "")
            matrix["standings"] = _row(goals_ok, False, "")
            matrix["rest"] = _row(True, False, "derived from finished fixtures")
            matrix["events"] = _row(False, False, "not consumed by v1 math")
            matrix["lineups"] = _row(False, False, "not consumed by v1 math")
            matrix["possession"] = _row(False, False, "no legitimate bulk source")
            matrix["closing_odds"] = _row(False, False, "never a prediction input")
            matrix["target_stats"] = _row(False, False, "never used for own match")
            matrix["h2h"] = _row(True, False, "descriptive only")
            matrix["strength_of_schedule"] = _row(goals_ok, False, "")
        else:
            for name in ("elo", "goals", "form", "home_away", "standings",
                         "strength_of_schedule"):
                matrix[name]["estimated"] = matrix[name]["strict"]
            matrix["xg"]["estimated"] = xg_ok
            if not xg_ok:
                matrix["xg"]["note"] = "insufficient parent-anchored xG rows"
            matrix["shots"]["estimated"] = shots_ok
            matrix["rest"]["estimated"] = True
            matrix["h2h"]["estimated"] = True
    return matrix
