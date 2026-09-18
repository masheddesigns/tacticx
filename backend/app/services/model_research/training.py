"""Training with train-only preprocessing + validation-only calibration (Phase 12).

Standardization (mean/scale) is fit on the training window and frozen for
validation/test. Calibration temperature is fit on validation outcomes only
— never test labels. Hyperparameters are fixed per candidate spec (no
test-set tuning); the calibration module keeps calibrated variants as
separate versions.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np


def standardize_fit(X: np.ndarray):
    mean = X.mean(axis=0)
    scale = X.std(axis=0)
    scale[scale == 0.0] = 1.0
    return mean, scale


def standardize_apply(X: np.ndarray, mean: np.ndarray, scale: np.ndarray):
    return (X - mean) / scale


def train_logreg(X_train: np.ndarray, y_train: np.ndarray,
                 l2: float = 1.0, learning_rate: float = 0.5,
                 iterations: int = 2000, seed: int = 7) -> Dict:
    """Deterministic multinomial logistic regression (fixed order, zeros
    init, full-batch GD — same numerics as production SoftmaxRegression)."""
    from app.services.predictions.advanced import SoftmaxRegression

    _ = seed  # deterministic by construction; seed recorded for provenance
    model = SoftmaxRegression(l2=l2, learning_rate=learning_rate,
                              iterations=iterations)
    model.fit(np.asarray(X_train, dtype=float), np.asarray(y_train, dtype=int))
    return {"model": model, "coef": model.coef_.tolist(),
            "mean": model.mean_.tolist(), "scale": model.scale_.tolist(),
            "hyperparameters": {"l2": l2, "learning_rate": learning_rate,
                                "iterations": iterations, "seed": seed}}


def predict_logreg(trained: Dict, X) -> np.ndarray:
    return trained["model"].predict_proba(np.asarray(X, dtype=float))


def fit_temperature(probs_list, actual_list) -> float:
    """Thin wrapper: validation-only temperature (production implementation)."""
    from app.services.predictions.advanced import fit_temperature as _fit

    return _fit(probs_list, actual_list)


def apply_temperature(probs_list, temperature: float):
    from app.services.predictions.advanced import apply_temperature as _apply

    return [_apply(list(row), temperature) for row in probs_list]
