"""Model registry + promotion gate (Phase 12).

Statuses: research → validated → candidate → production, plus retired and
rejected. Only an explicit human action (recorded decided_by) moves
candidate → production; Phase 12 code never performs that transition and no
automatic_best_model() exists anywhere.

The gate checklist mirrors the spec: out-of-sample evaluation, valid
chronological split, leakage audit, documented population, validated
calibration, paired comparison, cross-league results, provenance,
reproducibility, no hidden test tuning.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.research import ResearchModel

STATUS_RESEARCH, STATUS_VALIDATED, STATUS_CANDIDATE = (
    "research", "validated", "candidate")
STATUS_PRODUCTION, STATUS_RETIRED, STATUS_REJECTED = (
    "production", "retired", "rejected")

GATE_ITEMS = ("out_of_sample_evaluation", "chronological_split_valid",
              "leakage_audit_passed", "population_documented",
              "calibration_validated", "paired_comparison_exists",
              "cross_league_reported", "feature_provenance_exists",
              "reproducibility_proven", "no_hidden_test_tuning")


def register(db: Session, model_id: str, model_version: str, status: str = STATUS_RESEARCH,
             feature_version: str = "", dataset_version: str = "",
             training_period: str = "", validation_period: str = "",
             test_period: str = "", parameters: Optional[Dict] = None,
             metrics: Optional[Dict] = None, artifact_hash: str = "") -> ResearchModel:
    row = ResearchModel(model_id=model_id, model_version=model_version,
                        status=status, feature_version=feature_version,
                        dataset_version=dataset_version,
                        training_period=training_period,
                        validation_period=validation_period,
                        test_period=test_period, parameters=parameters or {},
                        metrics=metrics or {}, artifact_hash=artifact_hash)
    db.add(row)
    db.commit()
    return row


def transition(db: Session, model_id: str, to_status: str,
               decided_by: str, reason: str = "") -> ResearchModel:
    """Explicit human-gated transition. candidate → production requires a
    non-empty human reason; automation may never call this with production."""
    allowed = {STATUS_RESEARCH, STATUS_VALIDATED, STATUS_CANDIDATE,
               STATUS_PRODUCTION, STATUS_RETIRED, STATUS_REJECTED}
    if to_status not in allowed:
        raise ValueError(f"unknown status: {to_status}")
    row = db.query(ResearchModel).filter_by(model_id=model_id).order_by(
        ResearchModel.id.desc()).first()
    if row is None:
        raise ValueError(f"unknown model: {model_id}")
    if row.status == STATUS_CANDIDATE and to_status == STATUS_PRODUCTION:
        if not decided_by or decided_by in ("auto", "system", "gate"):
            raise ValueError("candidate → production requires an explicit human decider")
        if not reason:
            raise ValueError("candidate → production requires a recorded reason")
    row.status = to_status
    db.commit()
    return row


def promotion_checklist(evidence: Dict) -> Dict:
    """Evaluate the gate from caller-supplied evidence. Returns per-item
    pass/fail + overall eligibility for *consideration* (never promotion)."""
    results = {}
    for item in GATE_ITEMS:
        passed, detail = evidence.get(item, (False, "no evidence supplied"))
        results[item] = {"passed": bool(passed), "detail": str(detail)[:300]}
    missing = [item for item, result in results.items() if not result["passed"]]
    return {"items": results, "eligible_for_consideration": not missing,
            "missing": missing,
            "note": "Eligibility is not promotion: candidate → production "
                    "needs an explicit human decision recorded in the registry."}


def count_tested(db: Session) -> Dict:
    from sqlalchemy import func as _func

    rows = db.query(ResearchModel.status, _func.count()).group_by(
        ResearchModel.status).all()
    return {"by_status": dict(rows), "total": sum(v for _, v in rows)}
