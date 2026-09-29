"""Phase 33 immutable evidence snapshots + state machine."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.evaluation_records import PredictionEvaluationRecord
from app.db.models.evidence import EvidenceSnapshot
from app.db.models.governance import ShadowEvaluationRecord

from .cohort import get_cohort
from .contracts import (
    CALCULATION_VERSION,
    MIN_CALIBRATION_PAIRS,
    MIN_PAIRED_EVIDENCE,
    STATE_CONFLICTING,
    STATE_DESCRIPTIVE,
    STATE_INCONCLUSIVE,
    STATE_INSUFFICIENT,
    STATE_INVALID,
    STATE_NO_DATA,
    STATE_SUPPORTED,
    canonical_hash,
)
from .eligibility import audit_cohort
from .metrics import paired_calibration, paired_metrics


class EvidenceError(Exception):
    def __init__(self, reason: str, *, code: str = "EVIDENCE_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def _ci_excludes_zero(ci: Optional[Dict[str, Any]]) -> Optional[bool]:
    if not ci or ci.get("lo") is None or ci.get("hi") is None:
        return None
    if ci["lo"] > 0:
        return True
    if ci["hi"] < 0:
        return True
    return False


def decide_state(n: int, differences: Dict[str, Any],
                 uncertainty: Dict[str, Any],
                 temporal_invalid: int) -> str:
    """Deterministic evidence state from data only."""
    if temporal_invalid > 0:
        return STATE_INVALID
    if n == 0:
        return STATE_INSUFFICIENT
    if n < MIN_PAIRED_EVIDENCE:
        return STATE_DESCRIPTIVE
    ll_ci = (uncertainty.get("delta_log_loss_1x2_ci") or {})
    br_ci = (uncertainty.get("delta_brier_1x2_ci") or {})
    ll_out = _ci_excludes_zero(ll_ci)
    br_out = _ci_excludes_zero(br_ci)
    if ll_out is None or br_out is None:
        return STATE_INCONCLUSIVE
    ll_sign = 1 if ll_ci["lo"] > 0 else -1
    br_sign = 1 if br_ci["lo"] > 0 else -1
    if ll_out and br_out and ll_sign == br_sign:
        return STATE_SUPPORTED
    if ll_out and br_out and ll_sign != br_sign:
        return STATE_CONFLICTING
    return STATE_INCONCLUSIVE


def compute_evidence(db: Session, cohort) -> Dict[str, Any]:
    """Pure computation over a cohort (persisted or ephemeral). No writes."""
    audit = audit_cohort(db, cohort)
    paired = audit["paired"]
    n = len(paired)

    total_shadow = db.query(ShadowEvaluationRecord).count()
    total_champion = db.query(PredictionEvaluationRecord).count()
    if n == 0 and total_shadow == 0 and total_champion == 0:
        state = STATE_NO_DATA
    else:
        state = None

    computed = paired_metrics(paired) if n else {
        "champion": {"sample_count": 0}, "challenger": {"sample_count": 0},
        "differences": {}, "uncertainty": {}}
    uncertainty = computed.get("uncertainty", {})
    differences = computed.get("differences", {})
    if state is None:
        state = decide_state(
            n, differences, uncertainty, audit["temporal"]["temporal_invalid"])

    calibration: Dict[str, Any] = {"state": "INSUFFICIENT_DATA"}
    if n >= MIN_CALIBRATION_PAIRS:
        calibration = paired_calibration(db, paired)
        calibration["state"] = "AVAILABLE"

    data_quality = {
        "observation_count": audit["candidates"],
        "paired_count": n,
        "excluded_count": audit["excluded_count"],
        "excluded_by_code": _count_codes(audit["excluded"]),
        "champion_eval_coverage": _coverage(paired),
    }
    observation_ids = sorted(p["shadow_evaluation_id"] for p in paired)
    outcome_hashes = sorted({p["outcome_hash"] for p in paired})
    semantic = {
        "contract": "REAL_WORLD_EVIDENCE_V1",
        "cohort_hash": cohort.cohort_hash,
        "observation_ids": observation_ids,
        "outcome_hashes": outcome_hashes,
        "metric_definition": "monitoring_metrics_v1",
        "uncertainty_config": {
            "bootstrap_seed": 7, "bootstrap_resamples": 500,
            "confidence": 95.0, "wilson": True},
        "calculation_version": CALCULATION_VERSION,
        "champion_metrics": computed.get("champion", {}),
        "challenger_metrics": computed.get("challenger", {}),
        "differences": differences,
    }
    snapshot_hash = canonical_hash(semantic)
    return {
        "cohort_id": cohort.cohort_id,
        "cohort_hash": cohort.cohort_hash,
        "observation_count": audit["candidates"],
        "paired_count": n,
        "excluded_count": audit["excluded_count"],
        "observation_ids": observation_ids,
        "outcome_hashes": outcome_hashes,
        "excluded": audit["excluded"][:500],
        "champion_metrics": computed.get("champion", {}),
        "challenger_metrics": computed.get("challenger", {}),
        "differences": differences,
        "uncertainty": uncertainty,
        "calibration": calibration,
        "data_quality": data_quality,
        "temporal_audit": audit["temporal"],
        "evidence_state": state,
        "snapshot_hash": snapshot_hash,
    }


def generate_snapshot(db: Session, cohort_id: str) -> Dict[str, Any]:
    """Compute and persist (or reuse) the evidence snapshot for a cohort."""
    cohort = get_cohort(db, cohort_id)
    computed = compute_evidence(db, cohort)
    existing = db.query(EvidenceSnapshot).filter_by(
        snapshot_hash=computed["snapshot_hash"]).first()
    if existing is not None:
        result = snapshot_to_dict(existing)
        result["rerun"] = True
        return result

    row = EvidenceSnapshot(
        snapshot_id=f"evd_{uuid.uuid4().hex[:12]}",
        cohort_id=cohort.cohort_id,
        cohort_hash=cohort.cohort_hash,
        calculation_version=CALCULATION_VERSION,
        observation_count=computed["observation_count"],
        paired_count=computed["paired_count"],
        excluded_count=computed["excluded_count"],
        observation_ids={"shadow_evaluation_ids": computed["observation_ids"],
                         "excluded": computed["excluded"]},
        champion_metrics=computed["champion_metrics"],
        challenger_metrics=computed["challenger_metrics"],
        differences=computed["differences"],
        uncertainty=computed["uncertainty"],
        calibration=computed["calibration"],
        data_quality=computed["data_quality"],
        temporal_audit=computed["temporal_audit"],
        evidence_state=computed["evidence_state"],
        snapshot_hash=computed["snapshot_hash"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    result = snapshot_to_dict(row)
    result["rerun"] = False
    return result


def _count_codes(excluded: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in excluded:
        code = item.get("code", "UNKNOWN")
        counts[code] = counts.get(code, 0) + 1
    return counts


def _coverage(paired: List[Dict[str, Any]]) -> Dict[str, Any]:
    present = sum(1 for p in paired if p.get("champion_eval_present"))
    return {"paired": len(paired), "with_champion_eval": present}


def snapshot_to_dict(row: EvidenceSnapshot) -> Dict[str, Any]:
    return {
        "snapshot_id": row.snapshot_id,
        "cohort_id": row.cohort_id,
        "cohort_hash": row.cohort_hash,
        "calculation_version": row.calculation_version,
        "observation_count": row.observation_count,
        "paired_count": row.paired_count,
        "excluded_count": row.excluded_count,
        "observation_ids": row.observation_ids,
        "champion_metrics": row.champion_metrics,
        "challenger_metrics": row.challenger_metrics,
        "differences": row.differences,
        "uncertainty": row.uncertainty,
        "calibration": row.calibration,
        "data_quality": row.data_quality,
        "temporal_audit": row.temporal_audit,
        "evidence_state": row.evidence_state,
        "snapshot_hash": row.snapshot_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def get_snapshot(db: Session, snapshot_id: str) -> EvidenceSnapshot:
    row = db.query(EvidenceSnapshot).filter_by(
        snapshot_id=snapshot_id).first()
    if row is None:
        raise EvidenceError(f"unknown snapshot: {snapshot_id}",
                            code="UNKNOWN_SNAPSHOT")
    return row


def generated_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
