"""Backtest metrics (Phase 2). Implemented with numpy only.

Probability quality is the point: accuracy alone is never reported without
log loss, Brier score and calibration. All metrics handle edge cases
(probabilities clipped away from 0/1 for log loss) deterministically.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

_EPS = 1e-12


def _clip(probs: np.ndarray) -> np.ndarray:
    return np.clip(probs, _EPS, 1.0 - _EPS)


def accuracy(predicted: List[str], actual: List[str]) -> float:
    if not actual:
        return 0.0
    return sum(1 for p, a in zip(predicted, actual) if p == a) / len(actual)


def argmax_labels(prob_matrix: List[List[float]]) -> List[int]:
    """Predicted class indices (ties resolve to the lowest index)."""
    out = []
    for row in prob_matrix:
        best, best_idx = None, 0
        for i, value in enumerate(row):
            if best is None or value > best:
                best, best_idx = value, i
        out.append(best_idx)
    return out


def accuracy_from_probs(prob_matrix: List[List[float]], actual_indices: List[int],
                        labels: Optional[List[str]] = None) -> float:
    """Accuracy of argmax predictions against integer class labels."""
    if not actual_indices:
        return 0.0
    predicted = argmax_labels(prob_matrix)
    return sum(1 for p, a in zip(predicted, actual_indices) if p == a) / len(actual_indices)


def multiclass_log_loss(prob_matrix: np.ndarray, actual_indices: List[int]) -> float:
    """Mean negative log-likelihood of the true class."""
    if not actual_indices:
        return 0.0
    probs = _clip(np.asarray(prob_matrix, dtype=float))
    chosen = probs[np.arange(len(actual_indices)), np.asarray(actual_indices)]
    return float(-np.mean(np.log(chosen)))


def multiclass_brier(prob_matrix: np.ndarray, actual_indices: List[int]) -> float:
    """Mean squared error over the full probability vector."""
    if not actual_indices:
        return 0.0
    probs = np.asarray(prob_matrix, dtype=float)
    n = len(actual_indices)
    one_hot = np.zeros_like(probs)
    one_hot[np.arange(n), np.asarray(actual_indices)] = 1.0
    return float(np.mean(np.sum((probs - one_hot) ** 2, axis=1)))


def binary_log_loss(probs: List[float], actual: List[int]) -> float:
    if not actual:
        return 0.0
    clipped = _clip(np.asarray(probs, dtype=float))
    true = np.asarray(actual, dtype=float)
    return float(-np.mean(true * np.log(clipped) + (1.0 - true) * np.log(1.0 - clipped)))


def binary_brier(probs: List[float], actual: List[int]) -> float:
    if not actual:
        return 0.0
    return float(np.mean((np.asarray(probs, dtype=float) - np.asarray(actual, dtype=float)) ** 2))


def mae(predicted: List[float], actual: List[float]) -> float:
    if not actual:
        return 0.0
    return float(np.mean(np.abs(np.asarray(predicted) - np.asarray(actual))))


def rmse(predicted: List[float], actual: List[float]) -> float:
    if not actual:
        return 0.0
    return float(np.sqrt(np.mean((np.asarray(predicted) - np.asarray(actual)) ** 2)))


def reliability_curve(probabilities: List[float], outcomes: List[int],
                      n_bins: int = 10) -> Dict:
    """Calibration bins: mean predicted vs empirical frequency per bin."""
    probs = np.asarray(probabilities, dtype=float)
    outs = np.asarray(outcomes, dtype=int)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins = []
    for low, high in zip(edges[:-1], edges[1:]):
        if high == 1.0:
            mask = (probs >= low) & (probs <= high)
        else:
            mask = (probs >= low) & (probs < high)
        count = int(mask.sum())
        bins.append({
            "bin_low": round(float(low), 3),
            "bin_high": round(float(high), 3),
            "count": count,
            "mean_predicted": round(float(probs[mask].mean()), 4) if count else None,
            "empirical_rate": round(float(outs[mask].mean()), 4) if count else None,
        })
    return {"n_bins": n_bins, "bins": bins}


def expected_calibration_error(probabilities: List[float], outcomes: List[int],
                               n_bins: int = 10) -> Optional[float]:
    """Weighted mean |predicted - empirical| over non-empty bins."""
    curve = reliability_curve(probabilities, outcomes, n_bins)
    total = sum(b["count"] for b in curve["bins"])
    if not total:
        return None
    err = 0.0
    for b in curve["bins"]:
        if b["count"] and b["mean_predicted"] is not None and b["empirical_rate"] is not None:
            err += (b["count"] / total) * abs(b["mean_predicted"] - b["empirical_rate"])
    return round(err, 4)
