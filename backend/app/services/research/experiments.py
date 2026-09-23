"""Phase 29 experiment runner + deterministic comparison.

Every experiment evaluates the production baseline and the candidate on
the exact same test observations with the same scoring implementation.
Comparison states follow documented rules; uncertainty comes from paired
bootstrap CIs. Re-runs with identical inputs return the existing record.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.research_registry import ResearchExperiment
from app.services.backtesting import metrics as met
from app.services.evaluation.compare import paired_metric_difference
from app.services.prediction_evaluation.metrics import score_snapshot

from .candidates import (
    get_candidate,
    predict_with_candidate,
)
from .contracts import (
    BASELINE_MODEL_ID,
    EVALUATION_PROTOCOL,
    EVALUATION_PROTOCOL_VERSION,
    EVIDENCE_IMPROVEMENT,
    EVIDENCE_INSUFFICIENT,
    EVIDENCE_NONE,
    EVIDENCE_REGRESSION,
    LEAKAGE_INVALID,
    LEAKAGE_PASS,
    MIN_EVIDENCE_SAMPLE,
    STATUS_INVALID,
    canonical_hash,
)
from .datasets import (
    audit_temporal_integrity,
    split_observations,
)


class ExperimentError(Exception):
    def __init__(self, reason: str, *, code: str = "EXPERIMENT_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def _code_hash() -> str:
    from .candidates import _code_hash as _candidate_code_hash

    return _candidate_code_hash()


def _means(rows: List[Dict[str, Any]], keys: List[str]) -> Dict[str, Any]:
    out = {}
    for key in keys:
        vals = [r.get(key) for r in rows
                if isinstance(r.get(key), (int, float))
                and not isinstance(r.get(key), bool)
                and math.isfinite(r.get(key))]
        out[key] = round(sum(vals) / len(vals), 6) if vals else None
    return out


METRIC_KEYS = ["accuracy_1x2", "log_loss_1x2", "brier_1x2", "goal_mae",
               "total_goal_error", "ou_1_5_accuracy", "ou_2_5_accuracy",
               "ou_3_5_accuracy", "btts_accuracy", "exact_score_hit"]


def _compare(baseline_probs: List[List[float]],
             candidate_probs: List[List[float]],
             actual: List[int], n: int) -> Dict[str, Any]:
    """Deterministic candidate-vs-baseline comparison.

    paired_metric_difference(a, b) returns mean(metric(a) - metric(b));
    called here as (candidate, baseline), so a negative mean favors the
    candidate on lower-is-better metrics.
    """
    logloss = paired_metric_difference(
        met.multiclass_log_loss, candidate_probs, actual,
        baseline_probs, actual)
    brier = paired_metric_difference(
        met.multiclass_brier, candidate_probs, actual,
        baseline_probs, actual)
    diffs = {
        "delta_log_loss": logloss["mean"],
        "delta_log_loss_ci": logloss["ci"],
        "delta_brier": brier["mean"],
        "delta_brier_ci": brier["ci"],
    }
    if n < MIN_EVIDENCE_SAMPLE:
        state = EVIDENCE_INSUFFICIENT
    else:
        ll_ci, br_ci = logloss["ci"], brier["ci"]
        ll_good = ll_ci is not None and ll_ci["hi"] < 0
        br_good = br_ci is not None and br_ci["hi"] < 0
        ll_bad = ll_ci is not None and ll_ci["lo"] > 0
        br_bad = br_ci is not None and br_ci["lo"] > 0
        if ll_good and br_good:
            state = EVIDENCE_IMPROVEMENT
        elif ll_bad and br_bad:
            state = EVIDENCE_REGRESSION
        else:
            state = EVIDENCE_NONE
    diffs["evidence_state"] = state
    diffs["evidence_rules"] = {
        "INSUFFICIENT_EVIDENCE": f"n < {MIN_EVIDENCE_SAMPLE}",
        "IMPROVEMENT_EVIDENCE": "Δlogloss CI entirely < 0 AND Δbrier CI "
                                "entirely < 0 (candidate lower is better)",
        "REGRESSION_EVIDENCE": "Δlogloss CI entirely > 0 AND Δbrier CI "
                               "entirely > 0",
        "NO_CLEAR_DIFFERENCE": "otherwise; CIs describe uncertainty, "
                               "never a selection mechanism",
    }
    return diffs


def run_experiment(
    db: Session,
    candidate_id: str,
    dataset_id: str,
    *,
    seed: int = 7,
    limit_test: Optional[int] = None,
) -> Dict[str, Any]:
    """Run baseline + candidate over the dataset test split. Idempotent."""
    from app.db.models.research_registry import ResearchDataset

    candidate = get_candidate(db, candidate_id)
    dataset = db.query(ResearchDataset).filter_by(
        dataset_id=dataset_id).first()
    if dataset is None:
        raise ExperimentError(f"unknown dataset: {dataset_id}",
                              code="UNKNOWN_DATASET")

    code_hash = _code_hash()
    existing = db.query(ResearchExperiment).filter_by(
        candidate_id=candidate.candidate_id,
        dataset_id=dataset.dataset_id,
        random_seed=seed).all()
    for row in existing:
        repro = row.reproducibility or {}
        if repro.get("runner_code_hash") == code_hash:
            result = experiment_to_dict(row)
            result["rerun"] = True
            return result

    audit = audit_temporal_integrity(dataset)
    test_obs = split_observations(dataset)["test"]
    if limit_test is not None:
        test_obs = test_obs[:limit_test]

    if audit["status"] == LEAKAGE_INVALID or \
            candidate.status == STATUS_INVALID:
        return _record_invalid(db, candidate, dataset, seed, code_hash, audit)

    baseline_rows, candidate_rows = [], []
    baseline_probs, candidate_probs, actual_idx = [], [], []
    skipped = 0
    for obs in test_obs:
        match = db.get(Match, obs["match_id"])
        if match is None or match.home_score is None \
                or match.away_score is None:
            skipped += 1
            continue
        cutoff = datetime.fromisoformat(obs["cutoff"])
        try:
            base_pred = _baseline_predict(db, match.id, cutoff)
            cand_pred = predict_with_candidate(
                db, candidate, match.id, cutoff)
        except Exception:
            skipped += 1
            continue
        if base_pred.get("status") != "valid" \
                or cand_pred.get("status") != "valid":
            skipped += 1
            continue
        b_metrics = score_snapshot(base_pred, match.home_score,
                                   match.away_score)
        c_metrics = score_snapshot(cand_pred, match.home_score,
                                   match.away_score)
        baseline_rows.append(b_metrics)
        candidate_rows.append(c_metrics)
        baseline_probs.append([base_pred["home_win_probability"],
                               base_pred["draw_probability"],
                               base_pred["away_win_probability"]])
        candidate_probs.append([cand_pred["home_win_probability"],
                                cand_pred["draw_probability"],
                                cand_pred["away_win_probability"]])
        actual_idx.append({"home": 0, "draw": 1, "away": 2}[
            b_metrics["actual_result"]])

    n = len(baseline_rows)
    baseline_means = _means(baseline_rows, METRIC_KEYS)
    candidate_means = _means(candidate_rows, METRIC_KEYS)
    comparison = _compare(baseline_probs, candidate_probs, actual_idx, n)
    comparison["n"] = n
    comparison["skipped"] = skipped

    calibration = _calibration(candidate_probs, actual_idx)
    family_count = db.query(ResearchExperiment).filter(
        ResearchExperiment.candidate_id == candidate.candidate_id).count()

    semantic = {
        "contract": "RESEARCH_EXPERIMENT_V1",
        "candidate_id": candidate.candidate_id,
        "candidate_version": candidate.version,
        "dataset_id": dataset.dataset_id,
        "dataset_hash": dataset.dataset_hash,
        "baseline": BASELINE_MODEL_ID,
        "seed": seed,
        "n": n,
        "baseline_metrics": baseline_means,
        "candidate_metrics": candidate_means,
        "comparison": comparison,
        "code_hash": code_hash,
    }
    result_hash = canonical_hash(semantic)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    row = ResearchExperiment(
        experiment_id=f"exp_{uuid.uuid4().hex[:12]}",
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.version,
        dataset_id=dataset.dataset_id,
        dataset_hash=dataset.dataset_hash,
        baseline_model_id=BASELINE_MODEL_ID,
        baseline_model_version=BASELINE_MODEL_ID,
        evaluation_protocol=EVALUATION_PROTOCOL,
        evaluation_protocol_version=EVALUATION_PROTOCOL_VERSION,
        random_seed=seed,
        baseline_metrics=baseline_means,
        candidate_metrics=candidate_means,
        comparison=comparison,
        uncertainty={"logloss_paired_bootstrap": comparison.get(
            "delta_log_loss_ci"),
            "brier_paired_bootstrap": comparison.get("delta_brier_ci"),
            "method": "paired bootstrap, seed=7, n_boot=2000 (see "
                      "evaluation.compare.paired_metric_difference)"},
        calibration=calibration,
        leakage_status=LEAKAGE_PASS,
        evidence_state=comparison["evidence_state"],
        reproducibility={
            "random_seed": seed,
            "dataset_hash": dataset.dataset_hash,
            "feature_version": "features_v1",
            "candidate_version": candidate.version,
            "candidate_code_hash": candidate.code_hash,
            "runner_code_hash": code_hash,
            "evaluation_protocol": EVALUATION_PROTOCOL,
            "evaluation_protocol_version": EVALUATION_PROTOCOL_VERSION,
        },
        execution_metadata={
            "test_observations": n,
            "skipped_observations": skipped,
            "family_experiment_count": family_count + 1,
            "multiple_comparison_note": "evidence state describes one "
                "experiment; selection across experiments must account "
                "for the family count reported here",
            "executed_at": now,
        },
        result_hash=result_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        candidate.status = "COMPLETED"
        db.commit()
    except Exception:
        db.rollback()
    result = experiment_to_dict(row)
    result["rerun"] = False
    return result


def _baseline_predict(db: Session, match_id: int, cutoff: datetime) -> Dict[str, Any]:
    """Exact production baseline path, invoked read-only."""
    from app.services.features.temporal import TemporalMode
    from app.services.predictions.ensemble import EnsembleModel

    model = EnsembleModel.from_names(["elo", "poisson"])
    full = model.predict(db, match_id, cutoff, TemporalMode.STRICT_PREMATCH)
    return full.model_dump(mode="json")


def _calibration(probs: List[List[float]],
                 actual: List[int]) -> Dict[str, Any]:
    from app.services.backtesting import metrics as met

    out = {}
    for i, outcome in enumerate(("home", "draw", "away")):
        p = [row[i] for row in probs]
        y = [1 if a == i else 0 for a in actual]
        out[outcome] = {
            "sample_count": len(p),
            "ece": met.expected_calibration_error(p, y),
        }
    return out


def _record_invalid(db: Session, candidate, dataset, seed: int,
                    code_hash: str, audit: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    semantic = {
        "contract": "RESEARCH_EXPERIMENT_V1",
        "candidate_id": candidate.candidate_id,
        "dataset_id": dataset.dataset_id,
        "dataset_hash": dataset.dataset_hash,
        "seed": seed,
        "leakage": LEAKAGE_INVALID,
        "code_hash": code_hash,
    }
    row = ResearchExperiment(
        experiment_id=f"exp_{uuid.uuid4().hex[:12]}",
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.version,
        dataset_id=dataset.dataset_id,
        dataset_hash=dataset.dataset_hash,
        baseline_model_id=BASELINE_MODEL_ID,
        baseline_model_version=BASELINE_MODEL_ID,
        evaluation_protocol=EVALUATION_PROTOCOL,
        evaluation_protocol_version=EVALUATION_PROTOCOL_VERSION,
        random_seed=seed,
        baseline_metrics={},
        candidate_metrics={},
        comparison={"evidence_state": LEAKAGE_INVALID,
                    "violations": audit.get("violations", [])},
        uncertainty={},
        calibration={},
        leakage_status=LEAKAGE_INVALID,
        evidence_state=LEAKAGE_INVALID,
        reproducibility={"random_seed": seed,
                         "dataset_hash": dataset.dataset_hash,
                         "runner_code_hash": code_hash},
        execution_metadata={"executed_at": now,
                            "note": "recorded as invalid; no metrics"},
        result_hash=canonical_hash(semantic),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        candidate.status = STATUS_INVALID
        db.commit()
    except Exception:
        db.rollback()
    result = experiment_to_dict(row)
    result["rerun"] = False
    return result


def experiment_to_dict(row: ResearchExperiment) -> Dict[str, Any]:
    return {
        "experiment_id": row.experiment_id,
        "candidate_id": row.candidate_id,
        "candidate_version": row.candidate_version,
        "dataset_id": row.dataset_id,
        "dataset_hash": row.dataset_hash,
        "baseline_model_id": row.baseline_model_id,
        "baseline_model_version": row.baseline_model_version,
        "evaluation_protocol": row.evaluation_protocol,
        "evaluation_protocol_version": row.evaluation_protocol_version,
        "random_seed": row.random_seed,
        "baseline_metrics": row.baseline_metrics,
        "candidate_metrics": row.candidate_metrics,
        "comparison": row.comparison,
        "uncertainty": row.uncertainty,
        "calibration": row.calibration,
        "leakage_status": row.leakage_status,
        "evidence_state": row.evidence_state,
        "reproducibility": row.reproducibility,
        "execution_metadata": row.execution_metadata,
        "result_hash": row.result_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
