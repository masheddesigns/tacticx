"""Poisson goal model (Phase 2, versions poisson_v1 / poisson_v1-xg).

Methodology (documented, reviewable):
- Team attack/defense strengths split by venue, estimated from pre-cutoff
  finished matches only, with exponential recency weights
  w = exp(-decay * age_days).
- attack_home(T) = weighted home goals scored / league weighted home average
  (defense analogously; away uses away averages).
- lambda_home = attack_home(H) * defense_away(A) * league_avg_home (away mirrored).
- Lambdas clipped to [0.05, 6.0] as a numerical guard (documented).
- Scorelines from independent Poissons (documented simplification), grid
  0..max_grid_goals renormalized; 1X2/O-U/BTTS aggregated from the grid.
- xG blend (XG_ENHANCED): venue-pooled xG attack/defense per team blended
  with weight xg_weight. Requires minimum_xg_matches per team AND a
  computable league xG average; otherwise pure-goals fallback with
  xg_used=false. Missing xG is NEVER replaced with goals/shots/estimates.
- Sufficiency: each team needs >= minimum_team_matches total and >=
  minimum_venue_matches per venue role, else status=insufficient_data
  (no fabrication, counts reported).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.services.features.availability import assess_availability
from app.services.features.repository import HistoricalFeatureRepository
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.predictions.math_utils import markets_from_grid, score_grid
from app.services.predictions.outputs import FullPrediction

MODEL_NAME = "poisson"
MODEL_VERSION = "poisson_v1"

GRID_MAX = 10  # 0..10 each side: truncation mass beyond is negligible,
# so analytic and Monte Carlo markets converge tightly.


@dataclass
class PoissonConfig:
    minimum_team_matches: int = 5
    minimum_venue_matches: int = 2
    recency_decay: float = 0.01
    xg_weight: float = 0.0
    minimum_xg_matches: int = 3
    max_grid_goals: int = GRID_MAX

    def as_dict(self) -> Dict:
        return {
            "minimum_team_matches": self.minimum_team_matches,
            "minimum_venue_matches": self.minimum_venue_matches,
            "recency_decay": self.recency_decay,
            "xg_weight": self.xg_weight,
            "minimum_xg_matches": self.minimum_xg_matches,
            "max_grid_goals": self.max_grid_goals,
        }

    def version_string(self) -> str:
        if self.xg_weight > 0:
            return f"{MODEL_VERSION}-xg"
        if (self.minimum_team_matches, self.minimum_venue_matches,
                self.recency_decay) != (5, 2, 0.01):
            return f"{MODEL_VERSION}-custom"
        return MODEL_VERSION


BASELINE_CONFIG = PoissonConfig()


def xg_enhanced_config(xg_weight: float = 0.5) -> PoissonConfig:
    return PoissonConfig(xg_weight=xg_weight)


class PoissonModel:
    model_name = MODEL_NAME

    def __init__(self, config: Optional[PoissonConfig] = None):
        self.config = config or PoissonConfig()
        self.model_version = self.config.version_string()

    # -- estimation -------------------------------------------------
    def _weights(self, matches: List[Match], cutoff: datetime) -> List[float]:
        naive_cutoff = as_naive_utc(cutoff)
        weights = []
        for match in matches:
            kickoff = as_naive_utc(match.kickoff_at)
            age_days = 0.0
            if kickoff is not None and naive_cutoff is not None:
                age_days = max(0.0, (naive_cutoff - kickoff).total_seconds() / 86400.0)
            weights.append(math.exp(-self.config.recency_decay * age_days))
        return weights

    def _venue_rates(self, matches: List[Match], team_id: int, venue: str,
                     cutoff: datetime) -> Tuple[float, float, float]:
        """Weighted (scored, conceded, weight_sum) for a team in a venue role."""
        scored = conceded = weight = 0.0
        weights = self._weights(matches, cutoff)
        for match, w in zip(matches, weights):
            if venue == "home" and match.home_team_id == team_id:
                scored += (match.home_score or 0) * w
                conceded += (match.away_score or 0) * w
                weight += w
            elif venue == "away" and match.away_team_id == team_id:
                scored += (match.away_score or 0) * w
                conceded += (match.home_score or 0) * w
                weight += w
        if weight <= 0:
            return 0.0, 0.0, 0.0
        return scored / weight, conceded / weight, weight

    def _league_averages(self, matches: List[Match], cutoff: datetime) -> Tuple[float, float]:
        weights = self._weights(matches, cutoff)
        total_w = sum(weights)
        if total_w <= 0:
            return 0.0, 0.0
        home = sum((m.home_score or 0) * w for m, w in zip(matches, weights)) / total_w
        away = sum((m.away_score or 0) * w for m, w in zip(matches, weights)) / total_w
        return home, away

    def estimate_lambdas(self, db: Session, match_id: int, cutoff: datetime,
                         mode: TemporalMode = TemporalMode.STRICT_PREMATCH):
        """Returns (lambda_home, lambda_away, diagnostics dict).

        Raises _InsufficientData with a reason when history is too thin.
        """
        match = db.get(Match, match_id)
        if match is None or match.home_team_id is None or match.away_team_id is None:
            raise _InsufficientData("match or teams missing")
        repo = HistoricalFeatureRepository(db, cutoff, mode)
        history = repo.finished_before(league_id=match.league_id)
        home_hist = [m for m in history if m.home_team_id == match.home_team_id
                     or m.away_team_id == match.home_team_id]
        away_hist = [m for m in history if m.home_team_id == match.away_team_id
                     or m.away_team_id == match.away_team_id]
        if len(home_hist) < self.config.minimum_team_matches:
            raise _InsufficientData(
                f"home team history {len(home_hist)} < {self.config.minimum_team_matches}")
        if len(away_hist) < self.config.minimum_team_matches:
            raise _InsufficientData(
                f"away team history {len(away_hist)} < {self.config.minimum_team_matches}")
        home_home = [m for m in home_hist if m.home_team_id == match.home_team_id]
        home_away = [m for m in home_hist if m.away_team_id == match.home_team_id]
        away_home = [m for m in away_hist if m.home_team_id == match.away_team_id]
        away_away = [m for m in away_hist if m.away_team_id == match.away_team_id]
        counts = {"home_home": len(home_home), "home_away": len(home_away),
                  "away_home": len(away_home), "away_away": len(away_away)}
        if min(counts.values()) < self.config.minimum_venue_matches:
            raise _InsufficientData(f"venue split too thin: {counts}")
        avg_home, avg_away = self._league_averages(history, cutoff)
        if avg_home <= 0 or avg_away <= 0:
            raise _InsufficientData("league averages unavailable (no pre-cutoff goals)")
        atk_h, def_h, _ = self._venue_rates(home_home, match.home_team_id, "home", cutoff)
        atk_a, def_a, _ = self._venue_rates(away_away, match.away_team_id, "away", cutoff)
        attack_home = atk_h / avg_home
        defense_away = def_a / avg_away
        attack_away = atk_a / avg_away
        defense_home = def_h / avg_home
        lam_home = attack_home * defense_away * avg_home
        lam_away = attack_away * defense_home * avg_away
        xg_used = False
        if self.config.xg_weight > 0:
            blended = self._blend_xg(repo, match, avg_home, avg_away,
                                     attack_home, defense_away, attack_away, defense_home)
            if blended is not None:
                (attack_home, defense_away, attack_away, defense_home) = blended
                lam_home = attack_home * defense_away * avg_home
                lam_away = attack_away * defense_home * avg_away
                xg_used = True
        lam_home = min(6.0, max(0.05, lam_home))
        lam_away = min(6.0, max(0.05, lam_away))
        diag = {
            "n_history": len(history),
            "venue_counts": counts,
            "league_avg_home": round(avg_home, 4),
            "league_avg_away": round(avg_away, 4),
            "xg_used": xg_used,
        }
        return lam_home, lam_away, diag

    def _blend_xg(self, repo: HistoricalFeatureRepository, match: Match,
                  avg_home: float, avg_away: float,
                  attack_home: float, defense_away: float,
                  attack_away: float, defense_home: float):
        """Blend venue-pooled xG strengths. Returns None when xG insufficient."""
        home_xg = repo.team_xg_before(match.home_team_id)
        away_xg = repo.team_xg_before(match.away_team_id)
        if len(home_xg) < self.config.minimum_xg_matches:
            return None
        if len(away_xg) < self.config.minimum_xg_matches:
            return None
        # League xG average from all pre-cutoff xG observations is not tracked
        # per league here; use the pooled mean of both teams' histories as the
        # normalizer would bias — instead require a league-wide estimate from
        # finished matches' xG rows. Fall back to None when unavailable.
        league_xg = self._league_xg_average(repo, match.league_id)
        if league_xg is None or league_xg <= 0:
            return None
        w = self.config.xg_weight
        home_for = sum(home_xg) / len(home_xg)
        home_against = self._xg_against(repo, match.home_team_id)
        away_for = sum(away_xg) / len(away_xg)
        away_against = self._xg_against(repo, match.away_team_id)
        if home_against is None or away_against is None:
            return None
        blend = lambda goal, xg: (1.0 - w) * goal + w * (xg / league_xg)
        return (blend(attack_home, home_for), blend(defense_away, away_against),
                blend(attack_away, away_for), blend(defense_home, home_against))

    def _xg_against(self, repo: HistoricalFeatureRepository, team_id: int):
        """Mean xG conceded (opponents' xG in this team's pre-cutoff matches)."""

        values = []
        for m in repo.team_matches_before(team_id):
            side = "away" if m.home_team_id == team_id else "home"
            for r in repo.match_stats(m.id):
                if r.team == side and r.stat_name in ("expected_goals", "xg"):
                    try:
                        values.append(float(str(r.stat_value).rstrip("%")))
                    except (TypeError, ValueError):
                        continue
        if not values:
            return None
        return sum(values) / len(values)

    def _league_xg_average(self, repo: HistoricalFeatureRepository, league_id):

        values = []
        for m in repo.finished_before(league_id=league_id):
            for r in repo.match_stats(m.id):
                if r.stat_name in ("expected_goals", "xg"):
                    try:
                        values.append(float(str(r.stat_value).rstrip("%")))
                    except (TypeError, ValueError):
                        continue
        if not values:
            return None
        return sum(values) / len(values)

    # -- prediction ---------------------------------------------------
    def predict(self, db: Session, match_id: int, cutoff: datetime,
                mode: TemporalMode = TemporalMode.STRICT_PREMATCH) -> FullPrediction:
        availability = assess_availability(
            db, match_id, cutoff, mode,
            minimum_team_matches=self.config.minimum_team_matches,
            minimum_xg_matches=self.config.minimum_xg_matches)
        try:
            lam_home, lam_away, diag = self.estimate_lambdas(db, match_id, cutoff, mode)
        except _InsufficientData as exc:
            return FullPrediction(
                model_name=self.model_name, model_version=self.model_version,
                status="insufficient_data",
                home_win_probability=1.0 / 3.0, draw_probability=1.0 / 3.0,
                away_win_probability=1.0 / 3.0, confidence=0.0, xg_used=False,
                feature_availability=availability.as_dict(),
                temporal_mode=mode.value, prediction_cutoff=str(as_naive_utc(cutoff)),
                data_quality=[str(exc), "uniform probabilities are a placeholder, not an estimate"],
            )
        grid = score_grid(lam_home, lam_away, self.config.max_grid_goals)
        markets = markets_from_grid(grid)
        return FullPrediction(
            model_name=self.model_name, model_version=self.model_version, status="valid",
            expected_home_goals=round(lam_home, 4), expected_away_goals=round(lam_away, 4),
            expected_total_goals=round(lam_home + lam_away, 4),
            score_probabilities={k: round(v, 6) for k, v in sorted(grid.items())},
            confidence=abs(markets["home_win_probability"] - markets["away_win_probability"]),
            xg_used=diag["xg_used"], feature_availability=availability.as_dict(),
            temporal_mode=mode.value, prediction_cutoff=str(as_naive_utc(cutoff)),
            data_quality=[f"{diag['n_history']} pre-cutoff matches",
                          f"venue splits {diag['venue_counts']}",
                          f"league avgs H={diag['league_avg_home']} A={diag['league_avg_away']}",
                          f"xg_used={diag['xg_used']}"],
            **markets,
        )


class _InsufficientData(Exception):
    pass
