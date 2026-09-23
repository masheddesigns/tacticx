"""Phase 29 candidate registry + built-in research candidates.

Candidates invoke existing production model classes read-only through the
same cutoff-safe predict() path. Declared input tables are allowlisted:
anything outside CUTOFF_SAFE_TABLES marks the candidate INVALID_EXPERIMENT
at registration or run time — never "high performing".
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.research_registry import ResearchCandidate

from .contracts import (
    CUTOFF_SAFE_TABLES,
    LEAKAGE_INVALID,
    STATUS_COMPLETED,
    STATUS_DRAFT,
    STATUS_INVALID,
    STATUS_RUNNING,
    STATUS_SUPERSEDED,
)

ALLOWED_STATUSES = (STATUS_DRAFT, STATUS_RUNNING, STATUS_COMPLETED,
                    STATUS_INVALID, STATUS_SUPERSEDED)

# Built-in research candidates (framework proofs, not production models).
BUILTIN_CANDIDATES: Dict[str, Dict[str, Any]] = {
    "baseline_repro": {
        "name": "Production baseline reproduction",
        "description": "Re-runs ensemble_v1-elo+poisson through the "
                       "research pipeline for protocol validation.",
        "hypothesis": "The research pipeline reproduces production "
                      "predictions within documented tolerance.",
        "model_family": "ensemble",
        "members": ["elo", "poisson"],
        "weights": [0.5, 0.5],
        "declared_inputs": {"tables": ["matches", "match_statistics",
                                       "teams", "leagues"]},
    },
    "poisson_only": {
        "name": "Poisson-only family alternative",
        "description": "Single-member Poisson model as a controlled "
                       "family alternative.",
        "hypothesis": "A single Poisson member differs measurably from "
                      "the two-member ensemble on identical observations.",
        "model_family": "poisson",
        "members": ["poisson"],
        "weights": [1.0],
        "declared_inputs": {"tables": ["matches", "match_statistics",
                                       "teams", "leagues"]},
    },
    "elo_only": {
        "name": "Elo-only family alternative",
        "description": "Single-member Elo model as a controlled family "
                       "alternative.",
        "hypothesis": "A single Elo member differs measurably from the "
                      "two-member ensemble on identical observations.",
        "model_family": "elo",
        "members": ["elo"],
        "weights": [1.0],
        "declared_inputs": {"tables": ["matches", "teams", "leagues"]},
    },
    "ensemble_weighted_60_40": {
        "name": "Ensemble weight variant 60/40",
        "description": "Same members as production with 0.6/0.4 weights "
                       "as a hyperparameter variant.",
        "hypothesis": "Weight perturbation shifts metrics within a small, "
                      "measurable band on identical observations.",
        "model_family": "ensemble",
        "members": ["elo", "poisson"],
        "weights": [0.6, 0.4],
        "declared_inputs": {"tables": ["matches", "match_statistics",
                                       "teams", "leagues"]},
    },
}


class CandidateError(Exception):
    def __init__(self, reason: str, *, code: str = "CANDIDATE_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def _code_hash() -> str:
    """Hash of this registry module: binds candidate definitions to code."""
    path = Path(__file__)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_declared_inputs(declared: Dict[str, Any]) -> List[str]:
    """Return violations; empty means all declared inputs are cutoff-safe."""
    tables = (declared or {}).get("tables", [])
    return [t for t in tables if t not in CUTOFF_SAFE_TABLES]


def register_candidate(
    db: Session,
    *,
    name: str,
    description: str = "",
    hypothesis: str = "",
    model_family: str = "",
    members: Optional[List[str]] = None,
    weights: Optional[List[float]] = None,
    declared_inputs: Optional[Dict[str, Any]] = None,
    version: str = "v1",
    supersedes_candidate_id: Optional[str] = None,
) -> ResearchCandidate:
    """Register a hypothesis. Leaking declarations -> INVALID_EXPERIMENT."""
    declared_inputs = declared_inputs or {"tables": ["matches"]}
    violations = validate_declared_inputs(declared_inputs)
    status = STATUS_INVALID if violations else STATUS_DRAFT
    row = ResearchCandidate(
        candidate_id=f"cand_{uuid.uuid4().hex[:12]}",
        name=name,
        version=version,
        description=description,
        hypothesis=hypothesis,
        feature_set={"members": members or [], "feature_version": "features_v1"},
        model_family=model_family,
        hyperparameters={"members": members or [], "weights": weights or []},
        declared_inputs={**declared_inputs,
                         "leakage_violations": violations},
        code_hash=_code_hash(),
        status=status,
        supersedes_candidate_id=supersedes_candidate_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def register_builtin(db: Session, key: str) -> ResearchCandidate:
    """Register one of the controlled built-in candidates."""
    if key not in BUILTIN_CANDIDATES:
        raise CandidateError(f"unknown builtin candidate: {key}",
                             code="UNKNOWN_CANDIDATE")
    spec = BUILTIN_CANDIDATES[key]
    existing = db.query(ResearchCandidate).filter_by(
        name=spec["name"], version="v1").first()
    if existing is not None:
        return existing
    return register_candidate(
        db, name=spec["name"], description=spec["description"],
        hypothesis=spec["hypothesis"], model_family=spec["model_family"],
        members=spec["members"], weights=spec["weights"],
        declared_inputs=spec["declared_inputs"])


def get_candidate(db: Session, candidate_id: str) -> ResearchCandidate:
    row = db.query(ResearchCandidate).filter_by(
        candidate_id=candidate_id).first()
    if row is None:
        raise CandidateError(f"unknown candidate: {candidate_id}",
                             code="UNKNOWN_CANDIDATE")
    return row


def candidate_to_dict(row: ResearchCandidate) -> Dict[str, Any]:
    return {
        "candidate_id": row.candidate_id,
        "name": row.name,
        "version": row.version,
        "description": row.description,
        "hypothesis": row.hypothesis,
        "feature_set": row.feature_set,
        "model_family": row.model_family,
        "hyperparameters": row.hyperparameters,
        "declared_inputs": row.declared_inputs,
        "code_hash": row.code_hash,
        "status": row.status,
        "supersedes_candidate_id": row.supersedes_candidate_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def predict_with_candidate(db: Session, candidate: ResearchCandidate,
                           match_id: int, cutoff: datetime):
    """Run a registered candidate read-only at one cutoff.

    Only ensemble/elo/poisson families over cutoff-safe inputs are
    supported; anything else (or a leaked declaration) refuses with
    INVALID_EXPERIMENT instead of executing.
    """
    from app.services.features.temporal import TemporalMode

    if candidate.status == STATUS_INVALID or \
            (candidate.declared_inputs or {}).get("leakage_violations"):
        raise CandidateError(
            "candidate declares non-cutoff-safe inputs",
            code=LEAKAGE_INVALID)
    hyper = candidate.hyperparameters or {}
    members = hyper.get("members") or []
    weights = hyper.get("weights") or None
    if candidate.model_family not in ("ensemble", "elo", "poisson"):
        raise CandidateError(
            f"unsupported research model family: {candidate.model_family}",
            code="UNSUPPORTED_FAMILY")
    if not members:
        raise CandidateError("candidate has no members",
                             code="INVALID_CANDIDATE")
    from app.services.predictions.ensemble import EnsembleModel

    model = EnsembleModel.from_names(list(members),
                                     list(weights) if weights else None)
    full = model.predict(db, match_id, cutoff, TemporalMode.STRICT_PREMATCH)
    return full.model_dump(mode="json")
