"""Ensemble + baselines (Phase 2).

EnsembleModel combines member models by configurable weights without
hard-coding future members: any model exposing predict() -> FullPrediction
can be registered in MODEL_REGISTRY (xG/ML/Market/MiroFish later) and
referenced by name. No claim is made that default weights are optimal —
backtesting judges that.

1X2 and expected goals are weight-averaged over all valid members. Score
grids (and hence O/U + BTTS) average over members that provide grids
(Poisson/MonteCarlo); Elo has no grid and is excluded from that average with
renormalized weights. If no member provides a grid, markets stay None.

BaselineModel predicts the constant pre-cutoff league outcome distribution
(most-common-result baseline as honest probabilities, not a single class).
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.services.features.availability import assess_availability
from app.services.features.repository import HistoricalFeatureRepository
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.predictions.elo import EloModel
from app.services.predictions.math_utils import markets_from_grid, normalize_triplet
from app.services.predictions.montecarlo import MonteCarloModel
from app.services.predictions.outputs import FullPrediction
from app.services.predictions.poisson import PoissonModel

MODEL_NAME = "ensemble"
MODEL_VERSION = "ensemble_v1"
BASELINE_NAME = "baseline"
BASELINE_VERSION = "baseline_v1"

MODEL_REGISTRY: Dict[str, type] = {
    "elo": EloModel,
    "poisson": PoissonModel,
    "montecarlo": MonteCarloModel,
    # Future: "xg", "ml", "market", "mirofish" register here without
    # touching the ensemble.
}


class EnsembleModel:
    model_name = MODEL_NAME

    def __init__(self, members: Optional[List] = None,
                 weights: Optional[List[float]] = None):
        self.members = members if members is not None else [EloModel(), PoissonModel()]
        if weights is None:
            weights = [1.0] * len(self.members)
        if len(weights) != len(self.members):
            raise ValueError("weights length must match members length")
        total = sum(weights)
        if total <= 0:
            raise ValueError("weights must sum to something positive")
        self.weights = [w / total for w in weights]
        member_names = "+".join(getattr(m, "model_name", "?") for m in self.members)
        self.model_version = f"{MODEL_VERSION}-{member_names}"

    @classmethod
    def from_names(cls, names: List[str], weights: Optional[List[float]] = None,
                   **kwargs) -> "EnsembleModel":
        """Build from registry names, e.g. ["elo", "poisson"]."""
        members = []
        for name in names:
            if name not in MODEL_REGISTRY:
                raise ValueError(f"unknown model: {name} (registry: {sorted(MODEL_REGISTRY)})")
            members.append(MODEL_REGISTRY[name](**kwargs) if kwargs else MODEL_REGISTRY[name]())
        return cls(members=members, weights=weights)

    def config_dict(self) -> Dict:
        return {
            "members": [getattr(m, "model_version", "?") for m in self.members],
            "weights": list(self.weights),
        }

    def predict(self, db: Session, match_id: int, cutoff: datetime,
                mode: TemporalMode = TemporalMode.STRICT_PREMATCH) -> FullPrediction:
        availability = assess_availability(db, match_id, cutoff, mode)
        member_preds = []
        for member, weight in zip(self.members, self.weights):
            try:
                pred = member.predict(db, match_id, cutoff, mode)
            except Exception:
                continue
            if pred.status != "valid":
                continue
            member_preds.append((pred, weight))
        if not member_preds:
            return FullPrediction(
                model_name=self.model_name, model_version=self.model_version,
                status="insufficient_data",
                home_win_probability=1.0 / 3.0, draw_probability=1.0 / 3.0,
                away_win_probability=1.0 / 3.0, confidence=0.0, xg_used=False,
                feature_availability=availability.as_dict(),
                temporal_mode=mode.value, prediction_cutoff=str(as_naive_utc(cutoff)),
                data_quality=["no member produced a valid prediction"],
            )
        total_w = sum(w for _, w in member_preds)
        home = sum(p.home_win_probability * w for p, w in member_preds) / total_w
        draw = sum(p.draw_probability * w for p, w in member_preds) / total_w
        away = sum(p.away_win_probability * w for p, w in member_preds) / total_w
        home, draw, away = normalize_triplet(home, draw, away)
        exp_home_vals = [p.expected_home_goals for p, _ in member_preds
                         if p.expected_home_goals is not None]
        exp_away_vals = [p.expected_away_goals for p, _ in member_preds
                         if p.expected_away_goals is not None]
        grid_members = [(p, w) for p, w in member_preds if p.score_probabilities]
        grid_w = sum(w for _, w in grid_members)
        markets: Dict = {}
        grid: Dict[str, float] = {}
        if grid_members and grid_w > 0:
            keys = set()
            for p, _ in grid_members:
                keys.update(p.score_probabilities.keys())
            for key in keys:
                grid[key] = sum(p.score_probabilities.get(key, 0.0) * w
                                for p, w in grid_members) / grid_w
            markets = markets_from_grid(grid)
        xg_used = any(p.xg_used for p, _ in member_preds)
        member_names = ", ".join(f"{p.model_name}({p.model_version})" for p, _ in member_preds)
        data_quality = [f"members: {member_names}",
                        f"weights: {[round(w, 3) for w in self.weights]}",
                        "weights are defaults, not claimed optimal"]
        return FullPrediction(
            model_name=self.model_name, model_version=self.model_version, status="valid",
            expected_home_goals=(round(sum(exp_home_vals) / len(exp_home_vals), 4)
                                 if exp_home_vals else None),
            expected_away_goals=(round(sum(exp_away_vals) / len(exp_away_vals), 4)
                                 if exp_away_vals else None),
            expected_total_goals=(round((sum(exp_home_vals) / len(exp_home_vals)
                                        + sum(exp_away_vals) / len(exp_away_vals)), 4)
                                  if exp_home_vals and exp_away_vals else None),
            score_probabilities={k: round(v, 6) for k, v in sorted(grid.items())},
            confidence=abs(home - away),
            xg_used=xg_used, feature_availability=availability.as_dict(),
            temporal_mode=mode.value, prediction_cutoff=str(as_naive_utc(cutoff)),
            data_quality=data_quality,
            home_win_probability=home, draw_probability=draw,
            away_win_probability=away,
            **{k: v for k, v in markets.items()
               if k not in ("home_win_probability", "draw_probability",
                            "away_win_probability")},
        )


class BaselineModel:
    """Most-common-result baseline as pre-cutoff empirical probabilities."""
    model_name = BASELINE_NAME
    model_version = BASELINE_VERSION

    def predict(self, db: Session, match_id: int, cutoff: datetime,
                mode: TemporalMode = TemporalMode.STRICT_PREMATCH) -> FullPrediction:
        match = db.get(Match, match_id)
        availability = assess_availability(db, match_id, cutoff, mode)
        if match is None:
            status, probs, notes = "insufficient_data", (1.0 / 3.0,) * 3, ["match missing"]
        else:
            repo = HistoricalFeatureRepository(db, cutoff, mode)
            history = repo.finished_before(league_id=match.league_id)
            if not history:
                status, probs, notes = "insufficient_data", (1.0 / 3.0,) * 3, \
                    ["no pre-cutoff history"]
            else:
                home = sum(1 for m in history if (m.home_score or 0) > (m.away_score or 0))
                draw = sum(1 for m in history if m.home_score == m.away_score)
                away = len(history) - home - draw
                total = len(history)
                status, probs = "valid", (home / total, draw / total, away / total)
                notes = [f"empirical distribution over {total} pre-cutoff matches"]
        home_p, draw_p, away_p = normalize_triplet(*probs)
        return FullPrediction(
            model_name=self.model_name, model_version=self.model_version, status=status,
            home_win_probability=home_p, draw_probability=draw_p,
            away_win_probability=away_p,
            confidence=abs(home_p - away_p), xg_used=False,
            feature_availability=availability.as_dict(),
            temporal_mode=mode.value, prediction_cutoff=str(as_naive_utc(cutoff)),
            data_quality=notes,
        )
