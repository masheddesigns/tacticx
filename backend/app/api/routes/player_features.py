"""Player-feature inspection endpoints (Phase 9).

Read-only: versioned feature snapshots, availability, contributors, quality.
No model training, no prediction mutation, no fabricated ratings.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import Match
from app.services.features.temporal import TemporalMode

router = APIRouter(tags=["player-features"])


def _resolve(match_id: int, db: Session, mode: str, cutoff: Optional[str]):
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "match not found")
    try:
        resolved_mode = TemporalMode(mode)
    except ValueError:
        raise HTTPException(400, "mode must be strict_prematch or historical_estimated")
    try:
        resolved_cutoff = datetime.fromisoformat(cutoff) if cutoff else match.kickoff_at
    except ValueError:
        raise HTTPException(400, "cutoff must be ISO format")
    if resolved_cutoff is None:
        raise HTTPException(400, "match has no kickoff; pass cutoff explicitly")
    return match, resolved_cutoff, resolved_mode


@router.get("/features/player/{match_id}", summary="Player-feature snapshot")
def player_features(match_id: int, db: Session = Depends(get_db),
                    mode: str = "strict_prematch", cutoff: Optional[str] = None):
    from app.services.player_intelligence import feature_snapshot

    _, resolved_cutoff, resolved_mode = _resolve(match_id, db, mode, cutoff)
    try:
        return feature_snapshot.build_snapshot(db, match_id, resolved_cutoff,
                                               resolved_mode, persist=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/features/player/{match_id}/availability", summary="Family availability")
def player_availability(match_id: int, db: Session = Depends(get_db),
                        cutoff: Optional[str] = None):
    from app.services.player_intelligence import availability as availability_svc

    match, resolved_cutoff, _ = _resolve(match_id, db, "strict_prematch", cutoff)
    if match.home_team_id is None:
        raise HTTPException(400, "match has no home team")
    return availability_svc.family_availability(db, match.home_team_id,
                                                resolved_cutoff, match_id)


@router.get("/features/player/{match_id}/contributors", summary="Contributing players")
def player_contributors(match_id: int, db: Session = Depends(get_db),
                        mode: str = "strict_prematch", cutoff: Optional[str] = None):
    from app.services.player_intelligence import feature_snapshot

    _, resolved_cutoff, resolved_mode = _resolve(match_id, db, mode, cutoff)
    try:
        snapshot = feature_snapshot.build_snapshot(db, match_id, resolved_cutoff,
                                                   resolved_mode, persist=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"home": snapshot["home"].get("contributors", []),
            "away": snapshot["away"].get("contributors", []),
            "mode": snapshot["mode"], "payload_hash": snapshot["payload_hash"]}


@router.get("/features/player/{match_id}/quality", summary="Feature quality")
def player_quality(match_id: int, db: Session = Depends(get_db),
                   mode: str = "strict_prematch", cutoff: Optional[str] = None):
    from app.services.player_intelligence import feature_snapshot

    _, resolved_cutoff, resolved_mode = _resolve(match_id, db, mode, cutoff)
    try:
        snapshot = feature_snapshot.build_snapshot(db, match_id, resolved_cutoff,
                                                   resolved_mode, persist=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"home": snapshot["home"].get("quality", {}),
            "away": snapshot["away"].get("quality", {}),
            "mode": snapshot["mode"], "payload_hash": snapshot["payload_hash"]}
