"""Phase 30 champion/challenger registry + active-model resolution."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.governance import ModelRegistry

from .artifact import (
    champion_artifact_identity,
    register_artifact,
)
from .contracts import (
    CHAMPION_MEMBERS,
    CHAMPION_MODEL_ID,
    CHAMPION_MODEL_VERSION,
    CHAMPION_WEIGHTS,
    ROLE_CHALLENGER,
    ROLE_CHAMPION,
)
from .lifecycle import GovernanceError, log_event


def _active_binding(db: Session, role: str,
                    competition: Optional[str] = None,
                    season: Optional[str] = None,
                    prediction_mode: str = "PRE_MATCH") -> Optional[ModelRegistry]:
    query = db.query(ModelRegistry).filter_by(
        role=role, state="ACTIVE", prediction_mode=prediction_mode)
    if competition is not None:
        query = query.filter_by(competition=competition)
    if season is not None:
        query = query.filter_by(season=season)
    return query.order_by(ModelRegistry.id.desc()).first()


def ensure_champion(
    db: Session,
    *,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: str = "PRE_MATCH",
) -> ModelRegistry:
    """Seed (once) the ensemble_v1 champion binding for a scope."""
    existing = _active_binding(db, ROLE_CHAMPION, competition, season,
                               prediction_mode)
    if existing is not None:
        return existing
    identity = champion_artifact_identity()
    artifact = register_artifact(
        db, model_id=CHAMPION_MODEL_ID,
        model_version=CHAMPION_MODEL_VERSION,
        members=CHAMPION_MEMBERS, weights=CHAMPION_WEIGHTS,
        provenance={"seeded": "production champion ensemble_v1",
                    "artifact_identity": identity},
        initial_state="PRODUCTION_ACTIVE")
    row = ModelRegistry(
        role=ROLE_CHAMPION, competition=competition, season=season,
        prediction_mode=prediction_mode, artifact_id=artifact.artifact_id,
        state="ACTIVE")
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(db, artifact_id=artifact.artifact_id, from_state="",
              to_state="CHAMPION_SEEDED", actor="system",
              reason="initial production champion binding",
              references={"registry_id": row.id})
    return row


def current_champion(
    db: Session,
    *,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: str = "PRE_MATCH",
):
    """Return the active champion binding (seeding the default scope)."""
    binding = _active_binding(db, ROLE_CHAMPION, competition, season,
                              prediction_mode)
    if binding is None and competition is None and season is None:
        binding = ensure_champion(db, prediction_mode=prediction_mode)
    if binding is None:
        raise GovernanceError("no champion bound for this scope",
                              code="NO_CHAMPION")
    return binding


def resolve_active_model_id(
    db: Session,
    *,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: str = "PRE_MATCH",
) -> str:
    """Governance authority answer: which model_id is production-active."""
    from .artifact import get_artifact

    binding = current_champion(db, competition=competition, season=season,
                               prediction_mode=prediction_mode)
    return get_artifact(db, binding.artifact_id).model_id


def bind_challenger(
    db: Session,
    artifact_id: str,
    *,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: str = "PRE_MATCH",
) -> ModelRegistry:
    row = ModelRegistry(
        role=ROLE_CHALLENGER, competition=competition, season=season,
        prediction_mode=prediction_mode, artifact_id=artifact_id,
        state="ACTIVE")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def supersede_binding(db: Session, binding: ModelRegistry,
                      new_id: Optional[int] = None) -> ModelRegistry:
    binding.state = "SUPERSEDED"
    binding.supersedes_registry_id = new_id
    db.commit()
    db.refresh(binding)
    return binding


def list_bindings(db: Session, role: Optional[str] = None,
                  limit: int = 200) -> List[Dict[str, Any]]:
    query = db.query(ModelRegistry)
    if role:
        query = query.filter_by(role=role)
    rows = query.order_by(ModelRegistry.id.desc()).limit(limit).all()
    return [{
        "registry_id": r.id, "role": r.role, "competition": r.competition,
        "season": r.season, "prediction_mode": r.prediction_mode,
        "artifact_id": r.artifact_id, "state": r.state,
        "supersedes_registry_id": r.supersedes_registry_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
