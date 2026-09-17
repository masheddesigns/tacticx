"""Team/player identity + unresolved queue + manual mapping (Phase 8).

Wraps the Phase 1.6 resolvers with mapping records
(canonical id, source, source id/name, method, confidence) and a persistent
unresolved queue (open/resolved/ignored/needs_manual_mapping). Manual
mappings are audited, versioned and source-specific; superseding never
rewrites history silently.

Player identity uses source ID + team + competition + season as supporting
evidence — names alone are never sufficient for duplicates. Transfers are
player-team relationships, never duplicate players.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.reconciliation import ManualMapping, UnresolvedRecord

METHOD_CONFIDENCE = {
    "explicit": 1.0,
    "existing_mapping": 0.95,
    "deterministic_normalization": 0.8,
    "manual": 1.0,
    "alias": 0.7,
}

QUEUE_OPEN, QUEUE_RESOLVED, QUEUE_IGNORED, QUEUE_MANUAL = (
    "open", "resolved", "ignored", "needs_manual_mapping")


def _queue_key(entity_type: str, source: str, source_record_id: str) -> str:
    import hashlib

    return hashlib.sha256(
        f"{entity_type}:{source}:{source_record_id}".encode()).hexdigest()[:32]


def enqueue_unresolved(db: Session, entity_type: str, source: str,
                       source_record_id: str, reason: str,
                       dry_run: bool = False) -> Optional[UnresolvedRecord]:
    """Persistent queue entry (idempotent on dedup key). Nothing is discarded."""
    key = _queue_key(entity_type, source, source_record_id)
    existing = db.query(UnresolvedRecord).filter_by(dedup_key=key).first()
    now = datetime.now(timezone.utc)
    if existing is not None:
        if existing.status == QUEUE_OPEN:
            existing.last_seen = now
            if not dry_run:
                db.commit()
        return existing
    if dry_run:
        return None
    row = UnresolvedRecord(entity_type=entity_type, source=source or "",
                           source_record_id=str(source_record_id),
                           reason=reason[:500], first_seen=now, last_seen=now,
                           status=QUEUE_OPEN, dedup_key=key)
    db.add(row)
    db.commit()
    return row


def resolve_team(db: Session, source: str, provider_team_id: str = "",
                 provider_team_name: str = "", league: str = "") -> Dict:
    """Canonical team resolution with mapping-method record."""
    from app.services.identity.teams import TeamIdentityResolver

    team_id, method = TeamIdentityResolver(db).resolve(
        source, provider_team_id=provider_team_id,
        provider_team_name=provider_team_name, league=league)
    confidence = METHOD_CONFIDENCE.get(
        "existing_mapping" if method in ("mapping", "legacy") else method, 0.5)
    if team_id is None:
        enqueue_unresolved(db, "team", source, provider_team_id or provider_team_name,
                           f"unresolved team name={provider_team_name!r}")
    return {"canonical_team_id": team_id, "source": source,
            "source_team_id": provider_team_id, "source_team_name": provider_team_name,
            "mapping_method": method, "confidence": confidence}


def resolve_player(db: Session, source: str, provider_player_id: str = "",
                   name: str = "", team: str = "", competition: str = "",
                   season: str = "") -> Dict:
    """Canonical player resolution with team/competition/season evidence."""
    from app.services.identity.players import PlayerIdentityResolver
    from app.services.identity.teams import TeamIdentityResolver

    team_id = None
    if team:
        # Supporting team context (queue side-effects stay inside resolvers).
        team_id, _ = TeamIdentityResolver(db).resolve(
            source, provider_team_name=team)
    player_id, method = PlayerIdentityResolver(db).resolve(
        source, provider_player_id=provider_player_id,
        provider_player_name=name, team_id=team_id)
    if player_id is not None and not provider_player_id and team_id is not None:
        # No source ID and team context given: a same-name player on a
        # DIFFERENT team must not merge on the name alone (transfers and
        # duplicates stay distinct without ID evidence).
        from app.db.models.core import Player

        row = db.get(Player, player_id)
        if row is not None and row.team_id is not None and row.team_id != team_id:
            player_id, method = None, "unresolved"
    if player_id is None:
        enqueue_unresolved(
            db, "player", source, provider_player_id or name,
            f"unresolved player name={name!r} team={team!r} "
            f"competition={competition!r} season={season!r}")
    return {"canonical_player_id": player_id, "source": source,
            "source_player_id": provider_player_id, "source_name": name,
            "normalized_name": name.strip().lower() if name else "",
            "team_context": team, "mapping_method": method,
            "confidence": METHOD_CONFIDENCE.get(method, 0.5)}


def apply_manual_mapping(db: Session, entity_type: str, source: str,
                         source_record_id: str, canonical_entity_id: int,
                         created_by: str = "cli", dry_run: bool = False) -> Dict:
    """Explicit audited mapping. Previous live mapping for the same key is
    superseded (versioned), never edited. Unresolved queue entry flips to
    resolved."""
    if entity_type not in ("team", "player", "match", "bookmaker"):
        raise ValueError(f"unsupported entity_type: {entity_type}")
    if canonical_entity_id is None or canonical_entity_id <= 0:
        raise ValueError("canonical_entity_id must be positive")
    key = _queue_key(entity_type, source, source_record_id)
    if dry_run:
        return {"status": "would_apply", "entity_type": entity_type,
                "source": source, "source_record_id": source_record_id,
                "canonical_entity_id": canonical_entity_id}
    live = db.query(ManualMapping).filter_by(
        entity_type=entity_type, source=source,
        source_record_id=str(source_record_id), superseded_by=None).all()
    version = max([m.version for m in live], default=0) + 1
    row = ManualMapping(entity_type=entity_type, source=source or "",
                        source_record_id=str(source_record_id),
                        canonical_entity_id=canonical_entity_id,
                        created_by=created_by, version=version)
    db.add(row)
    db.flush()
    for old in live:
        old.superseded_by = row.id
    queue_row = db.query(UnresolvedRecord).filter_by(dedup_key=key).first()
    if queue_row is not None and queue_row.status == QUEUE_OPEN:
        queue_row.status = QUEUE_RESOLVED
    # Mirror into the native mapping tables so resolvers pick it up.
    _mirror_native(db, entity_type, source, source_record_id,
                   canonical_entity_id)
    db.commit()
    return {"status": "applied", "mapping_id": row.id, "version": version}


def _mirror_native(db: Session, entity_type: str, source: str,
                   source_record_id: str, canonical_id: int) -> None:
    if entity_type == "team":
        from app.db.models.provenance import TeamProviderMapping
        from app.services.identity.normalize import normalize_name

        exists = db.query(TeamProviderMapping).filter_by(
            source=source, provider_team_id=str(source_record_id)).first()
        if exists is None:
            db.add(TeamProviderMapping(
                team_id=canonical_id, source=source,
                provider_team_id=str(source_record_id),
                normalized_name=normalize_name(str(source_record_id)),
                resolution_method="manual", active=True))
    elif entity_type == "match":
        from app.db.models.provenance import MatchSourceMapping

        exists = db.query(MatchSourceMapping).filter_by(
            source=source, source_match_id=str(source_record_id)).first()
        if exists is None:
            db.add(MatchSourceMapping(match_id=canonical_id, source=source,
                                      source_match_id=str(source_record_id)))
    elif entity_type == "player":
        from app.db.models.provenance import PlayerProviderMapping

        exists = db.query(PlayerProviderMapping).filter_by(
            source=source, provider_player_id=str(source_record_id)).first()
        if exists is None:
            db.add(PlayerProviderMapping(
                player_id=canonical_id, source=source,
                provider_player_id=str(source_record_id)))


def queue_summary(db: Session) -> Dict:
    from sqlalchemy import func

    by_status = dict(db.query(UnresolvedRecord.status, func.count()).group_by(
        UnresolvedRecord.status).all())
    by_entity = dict(db.query(UnresolvedRecord.entity_type, func.count()).group_by(
        UnresolvedRecord.entity_type).all())
    return {"total": sum(by_status.values()), "by_status": by_status,
            "by_entity": by_entity}
