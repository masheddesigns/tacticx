"""Phase 33 paired metrics, uncertainty, and calibration.

Reuses Phase 2/27/28 primitives exclusively: means, paired bootstrap
CIs on difference series, Wilson intervals, reliability curves + ECE,
MCE. No new formulas.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from app.services.backtesting import metrics as met
from app.services.production_monitoring.contracts import (
    bootstrap_mean_ci,
    max_calibration_error,
    wilson_interval,
)
from app.db.models.governance import ShadowPredictionSnapshot
from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot

from .contracts import (
    BOOTSTRAP_CONFIDENCE,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    CALIBRATION_BINS,
)

METRIC_KEYS = ("accuracy_1x2", "log_loss_1x2", "brier_1x2", "goal_mae",
               "total_goal_error", "ou_1_5_accuracy", "ou_2_5_accuracy",
               "ou_3_5_accuracy", "btts_accuracy", "exact_score_hit")


def _mean(values: List[Any]) -> Optional[float]:
    vals = [v for v in values if isinstance(v, (int, float))
            and not isinstance(v, bool) and math.isfinite(v)]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def paired_metrics(paired: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Means per arm + paired differences + uncertainty. Deterministic."""
    champion: Dict[str, Any] = {"sample_count": len(paired)}
    challenger: Dict[str, Any] = {"sample_count": len(paired)}
    differences: Dict[str, Any] = {}
    uncertainty: Dict[str, Any] = {}
    for key in METRIC_KEYS:
        champ_vals = [(p["champion_metrics"] or {}).get(key) for p in paired]
        chal_vals = [(p["challenger_metrics"] or {}).get(key) for p in paired]
        champion[key] = _mean(champ_vals)
        challenger[key] = _mean(chal_vals)
        series = []
        for champ_v, chal_v in zip(champ_vals, chal_vals):
            if isinstance(champ_v, (int, float)) and not isinstance(champ_v, bool) \
                    and isinstance(chal_v, (int, float)) \
                    and not isinstance(chal_v, bool) \
                    and math.isfinite(champ_v) and math.isfinite(chal_v):
                series.append(round(chal_v - champ_v, 6))
        differences[f"delta_{key}"] = _mean(series)
        differences[f"delta_{key}_n"] = len(series)
        uncertainty[f"delta_{key}_ci"] = bootstrap_mean_ci(
            series, n_boot=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED,
            ci=BOOTSTRAP_CONFIDENCE)
    # Wilson interval on paired accuracy agreement is not meaningful;
    # report per-arm hit-rate intervals instead.
    for arm, label in (("champion_metrics", "champion"),
                       ("challenger_metrics", "challenger")):
        hits = sum(1 for p in paired
                   if (p[arm] or {}).get("accuracy_1x2") == 1)
        total = sum(1 for p in paired
                    if (p[arm] or {}).get("accuracy_1x2") in (0, 1))
        uncertainty[f"{label}_accuracy_ci"] = wilson_interval(hits, total)
    uncertainty["method"] = {
        "paired_bootstrap": f"seeded percentile bootstrap over paired "
                            f"difference series (seed={BOOTSTRAP_SEED}, "
                            f"n_boot={BOOTSTRAP_RESAMPLES}, "
                            f"ci={BOOTSTRAP_CONFIDENCE})",
        "wilson": "Wilson score interval for hit-rate proportions",
        "calculation_version": "evidence_calc_v1",
    }
    return {"champion": champion, "challenger": challenger,
            "differences": differences, "uncertainty": uncertainty}


def paired_calibration(
    db,
    paired: List[Dict[str, Any]],
    n_bins: int = CALIBRATION_BINS,
) -> Dict[str, Any]:
    """Reliability + ECE + MCE recomputed from stored immutable payloads."""
    arms: Dict[str, Any] = {}
    shadow_ids = [obs["shadow_id"] for obs in paired]
    rows = {row.shadow_id: row
            for row in db.query(ShadowPredictionSnapshot).filter(
                ShadowPredictionSnapshot.shadow_id.in_(shadow_ids)).all()} \
        if shadow_ids else {}
    prod_ids = [r.production_prediction_id for r in rows.values()
                if r.production_prediction_id]
    prods = {row.prediction_id: row
             for row in db.query(PreMatchPredictionSnapshot).filter(
                 PreMatchPredictionSnapshot.prediction_id.in_(prod_ids)).all()} \
        if prod_ids else {}
    outcome_map = {}
    for obs in paired:
        key = (obs["match_id"], obs["outcome_hash"])
        if key not in outcome_map:
            outcome_map[key] = row_outcome(db, obs)
    for arm in ("champion", "challenger"):
        probs: Dict[str, List[float]] = {"home": [], "draw": [], "away": []}
        labels: Dict[str, List[int]] = {"home": [], "draw": [], "away": []}
        for obs in paired:
            row = rows.get(obs["shadow_id"])
            if row is None:
                continue
            if arm == "champion":
                if not obs.get("champion_eval_present"):
                    continue
                prod = prods.get(row.production_prediction_id)
                if prod is None:
                    continue
                payload = (prod.prediction_payload or {}).get("prediction", {})
            else:
                payload = row.challenger_output or {}
            actual = (outcome_map.get(
                (obs["match_id"], obs["outcome_hash"])) or {}).get("actual")
            if actual not in ("home", "draw", "away"):
                continue
            triple = [payload.get("home_win_probability"),
                      payload.get("draw_probability"),
                      payload.get("away_win_probability")]
            if any(not isinstance(v, (int, float)) or isinstance(v, bool)
                   or not math.isfinite(v) for v in triple):
                continue
            for outcome, value in zip(("home", "draw", "away"), triple):
                probs[outcome].append(float(value))
                labels[outcome].append(1 if actual == outcome else 0)
        per_outcome = {}
        for outcome in ("home", "draw", "away"):
            curve = met.reliability_curve(
                probs[outcome], labels[outcome], n_bins=n_bins)
            per_outcome[outcome] = {
                "sample_count": len(probs[outcome]),
                "buckets": curve["bins"],
                "ece": met.expected_calibration_error(
                    probs[outcome], labels[outcome], n_bins=n_bins),
                "mce": max_calibration_error(curve),
            }
        arms[arm] = per_outcome
    return {"n_bins": n_bins, "per_outcome_by_arm": arms,
            "method": "reliability_buckets_v1 over stored immutable payloads"}


def row_outcome(db, obs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from app.db.models.evaluation_records import MatchOutcomeSnapshot

    outcome = db.query(MatchOutcomeSnapshot).filter_by(
        match_id=obs["match_id"],
        outcome_hash=obs["outcome_hash"]).first()
    if outcome is None:
        return None
    return {"actual": outcome.final_result,
            "home_goals": outcome.final_home_goals,
            "away_goals": outcome.final_away_goals}
