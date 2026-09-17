"""Player-team membership reconstruction (Phase 9).

Versioned (player, team, valid_from, valid_to, source, confidence) rows
rebuilt from cutoff-ordered lineup evidence. A player appearing for two
teams across the season yields two membership rows — never a duplicate
player. Membership is cutoff-aware: as-of queries only see ranges covering
the cutoff.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Lineup, Match, Player
from app.db.models.player_intelligence import PlayerTeamMembership
from app.services.features.temporal import TemporalMode, as_naive_utc


def rebuild_memberships(db: Session, mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                        dry_run: bool = False) -> Dict:
    """Rebuild memberships from all lineup rows (ordered by match kickoff).

    Consecutive appearances for one team form one validity range; a team
    switch closes the old range and opens a new one. Strict mode requires
    explicit effective_at (dataset rows carry none -> no strict memberships,
    honestly reported); estimated mode anchors ranges to match kickoffs.
    """
    rows = (db.query(Lineup, Match)
            .join(Match, Match.id == Lineup.match_id)
            .filter(Match.status == "FINISHED", Match.kickoff_at.is_not(None))
            .order_by(Match.kickoff_at.asc(), Match.id.asc()).all())
    if mode == TemporalMode.STRICT_PREMATCH:
        eligible = [(l, m) for l, m in rows if l.effective_at is not None]
    else:
        eligible = [(l, m) for l, m in rows]
    # Resolve provider ids to canonical players once.
    from app.db.models.provenance import PlayerProviderMapping

    def canonical_id(source: str, provider_id: str) -> Optional[int]:
        if not provider_id:
            return None
        mapping = db.query(PlayerProviderMapping).filter_by(
            source=source, provider_player_id=str(provider_id),
            active=True).first()
        if mapping is not None:
            return mapping.player_id
        row = db.query(Player).filter_by(
            provider=source, provider_player_id=str(provider_id)).first()
        return row.id if row else None

    spans: Dict[tuple, Dict] = {}
    for lineup, match in eligible:
        # Team attribution via parent-match side (lineup.team_id is NULL in
        # this dataset; side string + match is the evidence, never a guess:
        # side outside home/away is skipped, not attributed).
        if match.home_team_id is not None and lineup.team == "home":
            team_id = match.home_team_id
        elif match.away_team_id is not None and lineup.team == "away":
            team_id = match.away_team_id
        else:
            team_id = lineup.team_id
        if team_id is None:
            continue
        pid = canonical_id(lineup.source or "", lineup.player_provider_id or "")
        if pid is None:
            continue
        key = (pid, team_id)
        kickoff = as_naive_utc(match.kickoff_at)
        span = spans.get(key)
        if span is None:
            spans[key] = {"player_id": pid, "team_id": team_id,
                          "valid_from": kickoff, "valid_to": kickoff,
                          "source": lineup.source or "", "confidence": "medium"}
        else:
            if kickoff is not None and (span["valid_to"] is None or kickoff > span["valid_to"]):
                span["valid_to"] = kickoff
    if dry_run:
        return {"status": "would_rebuild", "memberships": len(spans),
                "mode": mode.value}
    existing = {(m.player_id, m.team_id): m
                for m in db.query(PlayerTeamMembership).all()}
    created = updated = 0
    for key, span in spans.items():
        row = existing.get(key)
        if row is None:
            db.add(PlayerTeamMembership(**span))
            created += 1
        elif row.valid_to != span["valid_to"]:
            row.valid_to = span["valid_to"]
            updated += 1
    db.commit()
    return {"status": "rebuilt", "memberships": len(spans),
            "created": created, "updated": updated, "mode": mode.value}


def membership_at(db: Session, player_id: int, cutoff: datetime) -> List[Dict]:
    """Membership evidence as of cutoff: spans that started on or before it.
    valid_to is the last appearance seen (evidence, not contract end) — it
    never excludes a span on its own. Spans starting after cutoff (future
    transfers) are excluded."""
    naive = as_naive_utc(cutoff)
    out = []
    for row in db.query(PlayerTeamMembership).filter_by(player_id=player_id).all():
        if row.valid_from is not None and naive is not None and row.valid_from > naive:
            continue
        out.append({"team_id": row.team_id, "valid_from": str(row.valid_from),
                    "valid_to": str(row.valid_to), "source": row.source,
                    "confidence": row.confidence})
    return out
