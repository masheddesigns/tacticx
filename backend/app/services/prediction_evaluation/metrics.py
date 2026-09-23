"""Phase 27 per-snapshot metric computation.

Reuses the Phase 2 primitive definitions in backtesting/metrics.py
(accuracy, log loss with 1e-12 clipping, full-vector Brier, MAE/RMSE).
No new scoring methodologies.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from app.services.backtesting import metrics as met

from .contracts import result_from_goals, result_index

_EPS = 1e-12


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def score_snapshot(prediction: Dict[str, Any],
                   home_goals: int, away_goals: int) -> Dict[str, Any]:
    """Score one validated prediction payload against a verified outcome."""
    actual = result_from_goals(home_goals, away_goals)
    actual_idx = result_index(actual)
    metrics: Dict[str, Any] = {
        "actual_result": actual,
        "actual_home_goals": home_goals,
        "actual_away_goals": away_goals,
    }

    probs = [_num(prediction.get("home_win_probability")),
             _num(prediction.get("draw_probability")),
             _num(prediction.get("away_win_probability"))]
    if all(p is not None for p in probs):
        total = sum(probs)
        norm = [p / total for p in probs] if total > 0 else list(probs)
        picked = norm[actual_idx]
        metrics["p_home"] = round(norm[0], 6)
        metrics["p_draw"] = round(norm[1], 6)
        metrics["p_away"] = round(norm[2], 6)
        metrics["predicted_result"] = ("home", "draw", "away")[
            met.argmax_labels([norm])[0]]
        metrics["accuracy_1x2"] = (
            1 if metrics["predicted_result"] == actual else 0)
        metrics["log_loss_1x2"] = round(
            -math.log(max(picked, _EPS)), 6)
        metrics["brier_1x2"] = round(
            sum((p - (1.0 if i == actual_idx else 0.0)) ** 2
                for i, p in enumerate(norm)), 6)

    exp_home = _num(prediction.get("expected_home_goals"))
    exp_away = _num(prediction.get("expected_away_goals"))
    if exp_home is not None and exp_away is not None:
        metrics["home_goal_error"] = round(abs(exp_home - home_goals), 4)
        metrics["away_goal_error"] = round(abs(exp_away - away_goals), 4)
        metrics["home_goal_se"] = round((exp_home - home_goals) ** 2, 4)
        metrics["away_goal_se"] = round((exp_away - away_goals) ** 2, 4)
        metrics["goal_mae"] = round(
            (metrics["home_goal_error"] + metrics["away_goal_error"]) / 2.0, 4)
    exp_total = _num(prediction.get("expected_total_goals"))
    if exp_total is not None:
        metrics["total_goal_error"] = round(
            abs(exp_total - (home_goals + away_goals)), 4)
        metrics["total_goal_se"] = round(
            (exp_total - (home_goals + away_goals)) ** 2, 4)

    total_goals = home_goals + away_goals
    btts_actual = 1 if (home_goals > 0 and away_goals > 0) else 0
    for line in ("1_5", "2_5", "3_5"):
        over_p = _num(prediction.get(f"over_{line}_probability"))
        if over_p is None:
            continue
        over_actual = 1 if total_goals > float(line.replace("_", ".")) else 0
        metrics[f"ou_{line}_predicted_over"] = 1 if over_p >= 0.5 else 0
        metrics[f"ou_{line}_accuracy"] = (
            1 if metrics[f"ou_{line}_predicted_over"] == over_actual else 0)
        metrics[f"ou_{line}_log_loss"] = round(
            met.binary_log_loss([over_p], [over_actual]), 6)
        metrics[f"ou_{line}_brier"] = round(
            met.binary_brier([over_p], [over_actual]), 6)
    btts_p = _num(prediction.get("btts_yes_probability"))
    if btts_p is not None:
        metrics["btts_predicted_yes"] = 1 if btts_p >= 0.5 else 0
        metrics["btts_accuracy"] = (
            1 if metrics["btts_predicted_yes"] == btts_actual else 0)
        metrics["btts_log_loss"] = round(
            met.binary_log_loss([btts_p], [btts_actual]), 6)
        metrics["btts_brier"] = round(
            met.binary_brier([btts_p], [btts_actual]), 6)

    grid = prediction.get("score_probabilities") or {}
    if isinstance(grid, dict) and grid:
        actual_key = f"{home_goals}-{away_goals}"
        best_key, best_val = None, None
        for key, value in grid.items():
            v = _num(value)
            if v is None:
                continue
            if best_val is None or v > best_val:
                best_key, best_val = key, v
        metrics["exact_score_hit"] = (
            1 if best_key == actual_key else 0)
        metrics["predicted_top_score"] = best_key
        actual_prob = _num(grid.get(actual_key))
        metrics["actual_score_log_prob"] = (
            round(math.log(max(actual_prob, _EPS)), 6)
            if actual_prob is not None else None)

    return metrics
