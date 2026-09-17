"""Elo model (Phase 2, version elo_v1).

Ratings evolve chronologically from finished pre-cutoff matches only — a
prediction at time T never sees matches at or after T (enforced by the
feature repository, tested explicitly).

Methodology (documented, reviewable):
- expected_home = logistic(home_rating - away_rating + home_advantage)
- draw probability = pre-cutoff league empirical draw rate (fallback 0.25
  when no history exists), applied as:
  P(H) = E*(1-d), P(D) = d, P(A) = (1-E)*(1-d). Sums to 1 by construction.
- Ratings update with actual scores (1/0.5/0), no margin-of-victory multiplier.
- Home advantage is configurable globally, with optional per-league overrides
  (used only when configured; no silent league fitting).

Elo never reports insufficient_data: unrated teams start at the prior
(initial_rating), which is weakest early and converges with history.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.services.features.availability import assess_availability
from app.services.features.repository import HistoricalFeatureRepository
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.predictions.math_utils import logistic_expected, normalize_triplet
from app.services.predictions.outputs import FullPrediction

MODEL_NAME = "elo"
MODEL_VERSION = "elo_v1"


@dataclass
class EloConfig:
    initial_rating: float = 1500.0
    k_factor: float = 20.0
    home_advantage: float = 60.0  # Elo points added to the home side
    home_advantage_by_league: Dict[str, float] = field(default_factory=dict)
    draw_fallback: float = 0.25

    def as_dict(self) -> Dict:
        return {
            "initial_rating": self.initial_rating,
            "k_factor": self.k_factor,
            "home_advantage": self.home_advantage,
            "home_advantage_by_league": dict(self.home_advantage_by_league),
            "draw_fallback": self.draw_fallback,
        }

    def version_string(self) -> str:
        """Any parameter change must surface as a new version string."""
        base = MODEL_VERSION
        if (self.initial_rating, self.k_factor, self.home_advantage) != (1500.0, 20.0, 60.0):
            return f"{base}-custom"
        if self.home_advantage_by_league:
            return f"{base}-leagues"
        return base


def _result(home_score: int, away_score: int) -> float:
    if home_score > away_score:
        return 1.0
    if home_score < away_score:
        return 0.0
    return 0.5


class EloModel:
    model_name = MODEL_NAME

    def __init__(self, config: Optional[EloConfig] = None):
        self.config = config or EloConfig()
        self.model_version = self.config.version_string()

    def _home_edge(self, league_code: Optional[str] = None) -> float:
        if league_code and league_code in self.config.home_advantage_by_league:
            return self.config.home_advantage_by_league[league_code]
        return self.config.home_advantage

    def fit(self, history: List[Match], league_code: Optional[str] = None) -> Dict[int, float]:
        """Chronological rating evolution. History must already be pre-cutoff
        ordered oldest-first (the repository guarantees this)."""
        ratings: Dict[int, float] = {}
        edge = self._home_edge(league_code)
        for match in history:
            if match.home_team_id is None or match.away_team_id is None:
                continue
            if match.home_score is None or match.away_score is None:
                continue
            home = ratings.setdefault(match.home_team_id, self.config.initial_rating)
            away = ratings.setdefault(match.away_team_id, self.config.initial_rating)
            expected = logistic_expected(home - away + edge)
            actual = _result(match.home_score, match.away_score)
            ratings[match.home_team_id] = home + self.config.k_factor * (actual - expected)
            ratings[match.away_team_id] = away + self.config.k_factor * ((1.0 - actual) - (1.0 - expected))
        return ratings

    def predict(self, db: Session, match_id: int, cutoff: datetime,
                mode: TemporalMode = TemporalMode.STRICT_PREMATCH) -> FullPrediction:
        from app.db.models.core import League

        match = db.get(Match, match_id)
        if match is None or match.home_team_id is None or match.away_team_id is None:
            return self._insufficient(match_id, cutoff, mode, "match or teams missing")
        league_code = None
        if match.league_id is not None:
            league = db.get(League, match.league_id)
            league_code = league.code if league else None
        repo = HistoricalFeatureRepository(db, cutoff, mode)
        history = repo.finished_before(league_id=match.league_id)
        ratings = self.fit(history, league_code)
        home_rating = ratings.get(match.home_team_id, self.config.initial_rating)
        away_rating = ratings.get(match.away_team_id, self.config.initial_rating)
        expected = logistic_expected(home_rating - away_rating + self._home_edge(league_code))
        draw_rate, draw_n = repo.league_draw_rate(match.league_id) if match.league_id else (self.config.draw_fallback, 0)
        if draw_n == 0:
            draw_rate = self.config.draw_fallback
        home_p, draw_p, away_p = normalize_triplet(
            expected * (1.0 - draw_rate), draw_rate, (1.0 - expected) * (1.0 - draw_rate))
        availability = assess_availability(db, match_id, cutoff, mode)
        notes = [f"elo ratings from {len(history)} pre-cutoff matches",
                 f"draw prior {draw_rate:.3f} from {draw_n} matches"]
        if len(history) == 0:
            notes.append("no history: pure priors (both teams at initial rating)")
        return FullPrediction(
            model_name=self.model_name, model_version=self.model_version, status="valid",
            home_win_probability=home_p, draw_probability=draw_p, away_win_probability=away_p,
            confidence=abs(home_p - away_p),
            xg_used=False, feature_availability=availability.as_dict(),
            temporal_mode=mode.value, prediction_cutoff=str(as_naive_utc(cutoff)),
            data_quality=notes,
        )

    def _insufficient(self, match_id: int, cutoff: datetime,
                      mode: TemporalMode, reason: str) -> FullPrediction:
        return FullPrediction(
            model_name=self.model_name, model_version=self.model_version,
            status="insufficient_data",
            home_win_probability=1.0 / 3.0, draw_probability=1.0 / 3.0,
            away_win_probability=1.0 / 3.0, confidence=0.0, xg_used=False,
            feature_availability={}, temporal_mode=mode.value,
            prediction_cutoff=str(as_naive_utc(cutoff)),
            data_quality=[reason, "uniform probabilities are a placeholder, not an estimate"],
        )

    def ratings_at(self, db: Session, cutoff: datetime,
                   league_id: Optional[int] = None,
                   mode: TemporalMode = TemporalMode.STRICT_PREMATCH) -> Tuple[Dict[int, float], int]:
        """Ratings plus history size (useful for tests and debugging)."""
        repo = HistoricalFeatureRepository(db, cutoff, mode)
        history = repo.finished_before(league_id=league_id)
        return self.fit(history), len(history)
