"""Subgroup, extreme-probability, draw, goal-distribution, score and drift analyses."""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from app.services.backtesting import metrics as met

MIN_SUBGROUP_N = 50


def bucketize(details: List[Dict], key_fn, label: str = "bucket") -> Dict:
    """Group detail rows by a caller-supplied bucket key with min-N gating."""
    groups: Dict[str, List[Dict]] = {}
    for row in details:
        groups.setdefault(str(key_fn(row)), []).append(row)
    out = {}
    for name in sorted(groups):
        rows = groups[name]
        if len(rows) < MIN_SUBGROUP_N:
            out[name] = {"n": len(rows), "status": "insufficient_sample"}
            continue
        probs = [r["probs"] for r in rows]
        actual = [r["actual"] for r in rows]
        out[name] = {"n": len(rows), "status": "ok",
                     "accuracy": round(met.accuracy_from_probs(probs, actual), 4),
                     "log_loss": round(met.multiclass_log_loss(probs, actual), 4),
                     "brier": round(met.multiclass_brier(probs, actual), 4)}
    return {"label": label, "min_n": MIN_SUBGROUP_N, "groups": out}


def subgroup_analysis(details: List[Dict]) -> Dict:
    """League/season-agnostic slices: favorite buckets, entropy buckets."""
    from app.services.evaluation.uncertainty import describe_details

    enriched = describe_details(details)

    def fav_bucket(row):
        top = row["top_probability"]
        if top < 0.45:
            return "tossup(<0.45)"
        if top < 0.60:
            return "lean(0.45-0.60)"
        if top < 0.75:
            return "favorite(0.60-0.75)"
        return "strong-favorite(>=0.75)"

    def entropy_bucket(row):
        ent = row["entropy"]
        if ent < 0.80:
            return "sharp(<0.80)"
        if ent < 1.00:
            return "medium(0.80-1.00)"
        return "flat(>=1.00)"

    return {"favorite": bucketize(enriched, fav_bucket, "top-probability"),
            "entropy": bucketize(enriched, entropy_bucket, "predictive-entropy")}


def extreme_probability_audit(details: List[Dict],
                              thresholds: Optional[List[float]] = None) -> Dict:
    """Overconfidence audit: for max-prob >= T, report N, mean predicted,
    observed frequency, Brier, log-loss. Small-N buckets flagged."""
    thresholds = thresholds or [0.75, 0.80, 0.90]
    out = {}
    for threshold in thresholds:
        selected = []
        for row in details:
            top = max(float(row["probs"][0]), float(row["probs"][1]), float(row["probs"][2]))
            if top >= threshold:
                selected.append(row)
        if len(selected) < MIN_SUBGROUP_N:
            out[str(threshold)] = {"n": len(selected), "status": "insufficient_sample"}
            continue
        import numpy as np

        top_probs, hits = [], []
        for row in selected:
            top_idx = max(range(3), key=lambda i: row["probs"][i])
            top_probs.append(float(row["probs"][top_idx]))
            hits.append(1 if row["actual"] == top_idx else 0)
        out[str(threshold)] = {
            "n": len(selected), "status": "ok",
            "mean_predicted": round(float(np.mean(top_probs)), 4),
            "observed_frequency": round(float(np.mean(hits)), 4),
            "brier": round(met.binary_brier(top_probs, hits), 4),
            "log_loss": round(met.binary_log_loss(top_probs, hits), 4),
        }
    return {"thresholds": thresholds, "min_n": MIN_SUBGROUP_N, "buckets": out}


def draw_calibration(details: List[Dict], league_draw_baseline: Optional[float] = None,
                     n_bins: int = 10) -> Dict:
    """Draw-specific audit vs the league empirical draw baseline (pre-cutoff
    supplied by the caller; never fitted on the evaluated population)."""
    from app.services.evaluation.calibration import per_class_calibration

    per_class = per_class_calibration(details, n_bins=n_bins)
    draw = per_class["draw"]
    draw_probs = [r["probs"][1] for r in details]
    draw_out = [1 if r["actual"] == 1 else 0 for r in details]
    result = {"n": len(details), "calibration": draw,
              "brier": round(met.binary_brier(draw_probs, draw_out), 4) if details else None,
              "log_loss": round(met.binary_log_loss(draw_probs, draw_out), 4) if details else None}
    if league_draw_baseline is not None:
        import numpy as np

        base = [league_draw_baseline] * len(details)
        result["baseline_brier"] = round(met.binary_brier(base, draw_out), 4) if details else None
        result["baseline_log_loss"] = round(
            met.binary_log_loss(base, draw_out), 4) if details else None
    return result


def goal_distribution_audit(details_with_goals: List[Dict]) -> Dict:
    """Total-goal distribution quality: goal MAE/RMSE plus distributional
    log score of the actual total under the predicted total-goal distribution.
    Rows: {"expected_home_goals", "expected_away_goals", "actual_home_goals",
    "actual_away_goals"}. Poisson totals assumed (documented)."""
    import numpy as np

    from app.services.predictions.math_utils import poisson_pmf

    mae_h, mae_a, sq_err, log_scores, totals_pred, totals_act = [], [], [], [], [], []
    for row in details_with_goals:
        lh, la = row["expected_home_goals"], row["expected_away_goals"]
        ah, aa = row["actual_home_goals"], row["actual_away_goals"]
        if None in (lh, la, ah, aa):
            continue
        mae_h.append(abs(lh - ah))
        mae_a.append(abs(la - aa))
        sq_err.append((lh - ah) ** 2)
        sq_err.append((la - aa) ** 2)
        total_dist = {}
        for home in range(11):
            for away in range(11):
                total_dist[home + away] = total_dist.get(home + away, 0.0) + \
                    poisson_pmf(home, lh) * poisson_pmf(away, la)
        mass = sum(total_dist.values())
        actual_total = int(ah + aa)
        prob = total_dist.get(actual_total, 0.0) / mass if mass > 0 else 0.0
        log_scores.append(-math.log(max(prob, 1e-12)))
        totals_pred.append(sum(k * v for k, v in total_dist.items()) / mass if mass else 0.0)
        totals_act.append(float(actual_total))
    n = len(log_scores)
    if not n:
        return {"n": 0, "status": "insufficient_sample"}
    return {"n": n, "status": "ok",
            "goal_mae": round(float(np.mean(mae_h + mae_a)), 4),
            "goal_rmse": round(float(np.sqrt(np.mean(sq_err))), 4),
            "distributional_log_score": round(float(np.mean(log_scores)), 4),
            "total_goals_mae": round(float(np.mean(
                [abs(p - a) for p, a in zip(totals_pred, totals_act)])), 4)}


def score_distribution_audit(details_with_grids: List[Dict],
                             top_scores: Optional[List[str]] = None) -> Dict:
    """Correct-score audit: log probability of the actual score, mass on the
    required 16 scorelines, aggregate tail. Tests the whole distribution."""
    required = top_scores or ["0-0", "1-0", "0-1", "1-1", "2-0", "0-2", "2-1",
                              "1-2", "2-2", "3-0", "0-3", "3-1", "1-3", "3-2", "2-3"]
    log_scores, covered, tails = [], [], []
    for row in details_with_grids:
        grid = row.get("score_probabilities") or {}
        actual = row.get("actual_score")
        if not grid or actual is None:
            continue
        total = sum(grid.values())
        if total <= 0:
            continue
        prob = grid.get(actual, 0.0) / total
        log_scores.append(-math.log(max(prob, 1e-12)))
        covered.append(sum(grid.get(s, 0.0) for s in required) / total)
        tails.append(max(0.0, 1.0 - sum(grid.get(s, 0.0) for s in required) / total))
    if not log_scores:
        return {"n": 0, "status": "insufficient_sample"}
    import numpy as np

    return {"n": len(log_scores), "status": "ok",
            "mean_log_probability": round(float(-np.mean(log_scores)), 4),
            "mean_required16_mass": round(float(np.mean(covered)), 4),
            "mean_tail_mass": round(float(np.mean(tails)), 4)}


def drift_diagnostics(train_rows: List[Dict], test_rows: List[Dict]) -> Dict:
    """Compare feature/outcome distributions between periods. Diagnostic
    only — shift is reported, never labeled failure automatically."""
    import numpy as np

    def outcome_rate(rows):
        if not rows:
            return None
        n = len(rows)
        return {"home": round(sum(1 for r in rows if r["actual"] == 0) / n, 4),
                "draw": round(sum(1 for r in rows if r["actual"] == 1) / n, 4),
                "away": round(sum(1 for r in rows if r["actual"] == 2) / n, 4)}

    def entropy_mean(rows):
        if not rows:
            return None
        vals = []
        for r in rows:
            probs = r["probs"]
            vals.append(-sum(p * math.log(p) for p in probs if p > 0))
        return round(float(np.mean(vals)), 4)

    return {"train_n": len(train_rows), "test_n": len(test_rows),
            "train_outcome_rates": outcome_rate(train_rows),
            "test_outcome_rates": outcome_rate(test_rows),
            "train_mean_entropy": entropy_mean(train_rows),
            "test_mean_entropy": entropy_mean(test_rows),
            "note": "Shifts are diagnostic context, not model failure."}
