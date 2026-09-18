"""Candidate models: small, interpretable, deterministic (Phase 12).

Candidates: multinomial logistic regression (numpy SoftmaxRegression reuse),
baseline passthrough (ensemble_v1 / elo_v1 / poisson_v1 stored-or-live
probabilities — never refit). No dozens of models, no new dependencies
(numpy only), no stochastic training. Every candidate records
hyperparameters, data windows, feature version, seed, standardization and
regularization.
"""
from __future__ import annotations

from typing import Dict, List, Optional

CANDIDATES = ("logreg_team", "logreg_team_xg", "logreg_team_player",
              "logreg_all", "baseline_ensemble", "baseline_elo",
              "baseline_poisson")

CANDIDATE_FAMILIES = {
    "logreg_team": ["team"],
    "logreg_team_xg": ["team", "xg"],
    "logreg_team_player": ["team", "player"],
    "logreg_all": ["team", "xg", "shots", "player"],
    "baseline_ensemble": [],
    "baseline_elo": [],
    "baseline_poisson": [],
}


def describe(name: str) -> Dict:
    if name.startswith("logreg_"):
        return {"kind": "multinomial_logistic",
                "families": CANDIDATE_FAMILIES[name],
                "implementation": "numpy SoftmaxRegression (deterministic GD)",
                "hyperparameters": {"l2": 1.0, "learning_rate": 0.5,
                                    "iterations": 2000}}
    if name.startswith("baseline_"):
        return {"kind": "production_baseline",
                "model": name.replace("baseline_", "") + "_v1",
                "implementation": "stored-or-live production probabilities"}
    raise ValueError(f"unknown candidate: {name}")
