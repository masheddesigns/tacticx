"""Monte Carlo simulator (Phase 2, version montecarlo_v1).

Samples scorelines from a goal-distribution provider (default: PoissonModel
lambdas) and derives 1X2 / O-U / BTTS / score frequencies empirically.
Reproducible whenever random_seed is provided. With large n_simulations the
empirical frequencies converge to the analytic Poisson markets (tested).
"""
from __future__ import annotations

import random
from collections import Counter
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.services.features.availability import assess_availability
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.predictions.math_utils import markets_from_grid
from app.services.predictions.outputs import FullPrediction
from app.services.predictions.poisson import PoissonModel, _InsufficientData

MODEL_NAME = "montecarlo"
MODEL_VERSION = "montecarlo_v1"


class MonteCarloModel:
    model_name = MODEL_NAME
    model_version = MODEL_VERSION

    def __init__(self, base_model: Optional[PoissonModel] = None,
                 n_simulations: int = 10000, random_seed: Optional[int] = None):
        self.base_model = base_model or PoissonModel()
        self.n_simulations = n_simulations
        self.random_seed = random_seed
        if (n_simulations, random_seed) != (10000, None):
            self.model_version = f"{MODEL_VERSION}-custom"

    def config_dict(self) -> Dict:
        return {
            "base_model": self.base_model.model_version,
            "base_config": self.base_model.config.as_dict(),
            "n_simulations": self.n_simulations,
            "random_seed": self.random_seed,
        }

    def predict(self, db: Session, match_id: int, cutoff: datetime,
                mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                seed: Optional[int] = None) -> FullPrediction:
        availability = assess_availability(
            db, match_id, cutoff, mode,
            minimum_team_matches=self.base_model.config.minimum_team_matches,
            minimum_xg_matches=self.base_model.config.minimum_xg_matches)
        try:
            lam_home, lam_away, diag = self.base_model.estimate_lambdas(
                db, match_id, cutoff, mode)
        except _InsufficientData as exc:
            return FullPrediction(
                model_name=self.model_name, model_version=self.model_version,
                status="insufficient_data",
                home_win_probability=1.0 / 3.0, draw_probability=1.0 / 3.0,
                away_win_probability=1.0 / 3.0, confidence=0.0, xg_used=False,
                feature_availability=availability.as_dict(),
                temporal_mode=mode.value, prediction_cutoff=str(as_naive_utc(cutoff)),
                random_seed=seed if seed is not None else self.random_seed,
                data_quality=[str(exc), "uniform probabilities are a placeholder, not an estimate"],
            )
        active_seed = seed if seed is not None else self.random_seed
        rng = random.Random(active_seed)
        cap = getattr(getattr(self.base_model, "config", None), "max_grid_goals", 10) or 10
        counts: Counter = Counter()
        for _ in range(max(1, self.n_simulations)):
            home = self._poisson_sample(rng, lam_home)
            away = self._poisson_sample(rng, lam_away)
            # Same truncated support as the analytic grid so Monte Carlo
            # converges to it (renormalized identically).
            counts[(min(home, cap), min(away, cap))] += 1
        total = sum(counts.values())
        grid = {f"{home}-{away}": count / total for (home, away), count in counts.items()}
        markets = markets_from_grid(grid)
        return FullPrediction(
            model_name=self.model_name, model_version=self.model_version, status="valid",
            expected_home_goals=round(lam_home, 4), expected_away_goals=round(lam_away, 4),
            expected_total_goals=round(lam_home + lam_away, 4),
            score_probabilities={k: round(v, 6) for k, v in sorted(grid.items())},
            confidence=abs(markets["home_win_probability"] - markets["away_win_probability"]),
            xg_used=diag["xg_used"], feature_availability=availability.as_dict(),
            temporal_mode=mode.value, prediction_cutoff=str(as_naive_utc(cutoff)),
            random_seed=active_seed,
            data_quality=[f"{self.n_simulations} simulations, seed={active_seed}",
                          f"base lambdas H={lam_home:.3f} A={lam_away:.3f}",
                          f"xg_used={diag['xg_used']}"],
            **markets,
        )

    @staticmethod
    def _poisson_sample(rng: random.Random, lam: float) -> int:
        """Knuth's algorithm; exact for our lambda range."""
        import math

        if lam <= 0:
            return 0
        limit = 1.0
        count = 0
        bound = math.exp(-lam)
        while True:
            count += 1
            limit *= rng.random()
            if limit <= bound:
                return count - 1
