"""Phase 30 governance facade: full lifecycle flows in one place."""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .artifact import get_artifact, register_artifact
from .contracts import CHALLENGER
from .lifecycle import transition
from .registry import bind_challenger


def register_candidate_artifact(
    db: Session,
    *,
    candidate_id: str,
    experiment_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    dataset_hash: Optional[str] = None,
    train_period: Optional[Dict[str, Any]] = None,
    evaluation_period: Optional[Dict[str, Any]] = None,
    code_hash: str = "",
) -> Dict[str, Any]:
    """Bridge a Phase 29 candidate into a governed artifact."""
    from app.services.research import get_candidate

    from .artifact import artifact_to_dict

    candidate = get_candidate(db, candidate_id)
    hyper = candidate.hyperparameters or {}
    members = list(hyper.get("members") or [])
    weights = list(hyper.get("weights") or [])
    if not members:
        from .lifecycle import GovernanceError

        raise GovernanceError("candidate has no model members",
                              code="INVALID_CANDIDATE")
    model_id = f"ensemble_v1-{'+'.join(members)}" \
        if candidate.model_family == "ensemble" \
        else f"{candidate.model_family}_v1"
    row = register_artifact(
        db, model_id=model_id, model_version=model_id,
        members=members, weights=weights or [1.0] * len(members),
        candidate_id=candidate.candidate_id,
        experiment_id=experiment_id,
        dataset_id=dataset_id, dataset_hash=dataset_hash,
        train_period=train_period, evaluation_period=evaluation_period,
        code_hash=code_hash or candidate.code_hash,
        provenance={"candidate_name": candidate.name,
                    "hypothesis": candidate.hypothesis})
    return artifact_to_dict(row)


def promote_to_challenger(
    db: Session,
    artifact_id: str,
    *,
    actor: str = "",
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: str = "PRE_MATCH",
) -> Dict[str, Any]:
    """Move a VALIDATED artifact into CHALLENGER + bind the role."""
    from .artifact import artifact_to_dict

    artifact = get_artifact(db, artifact_id)
    transition(db, artifact, CHALLENGER, actor=actor or "system",
               reason="registered as challenger")
    binding = bind_challenger(db, artifact_id, competition=competition,
                              season=season, prediction_mode=prediction_mode)
    return {"artifact": artifact_to_dict(artifact),
            "challenger_registry_id": binding.id}


def full_flow_status(db: Session, artifact_id: str) -> Dict[str, Any]:
    """One-call status across artifact, validation, requests, shadow."""
    from .audit import reconstruct
    from .deployment import check_canary_eligibility
    from .shadow import shadow_pairs

    view = reconstruct(db, artifact_id)
    try:
        canary = check_canary_eligibility(db, artifact_id)
    except Exception as exc:
        canary = {"eligible": False, "error": str(exc)[:200]}
    view["canary_eligibility"] = canary
    view["shadow_pairs"] = len(shadow_pairs(db, artifact_id, limit=10000))
    return view
