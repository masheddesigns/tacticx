"""Player appearance history from cutoff-safe lineup rows (Phase 9).

Appearances (matches played, starts, substitute appearances) are directly
supported. Minutes are NOT in the lineup schema: minutes-based features
(minutes played, minutes share, per-90 rates, workload-minutes) are reported
unavailable/unknown, never synthesized from starts (a start is not 90
minutes of evidence). Windows are chronological: last 3/5/10 appearances
and season-to-date.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.core import Lineup, Match, Player
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.player_intelligence.repository import PlayerEventRepository

WINDOWS = (3, 5, 10)


def team_appearances(db: Session, team_id: int, cutoff: datetime,
                     mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                     target_match_id: Optional[int] = None) -> Dict:
    """Per-player appearance histories for one team.

    Returns {players: {canonical_id_or_provider_key: history}, unresolved,
    matches_considered}. Unresolved provider IDs stay keyed by source:id and
    are never merged with each other or with canonical players.
    """
    repo = PlayerEventRepository(db, cutoff, mode, target_match_id)
    lineups = repo.team_lineups_before(team_id)
    # Batch-resolve provider IDs to canonical players (no N+1 lookups).
    from app.db.models.core import Player
    from app.db.models.provenance import PlayerProviderMapping

    provider_ids = {l.player_provider_id for _, l, _ in lineups if l.player_provider_id}
    resolved: Dict[str, tuple] = {}
    if provider_ids:
        sources = {l.source or "" for _, l, _ in lineups}
        for mapping in db.query(PlayerProviderMapping).filter(
                PlayerProviderMapping.provider_player_id.in_(list(provider_ids))).all():
            if mapping.source in sources or True:
                resolved[(mapping.source, mapping.provider_player_id)] = (
                    mapping.player_id, "existing_mapping")
        for player in db.query(Player).filter(
                Player.provider_player_id.in_(list(provider_ids))).all():
            key = (player.provider, player.provider_player_id)
            if key not in resolved:
                resolved[key] = (player.id, "legacy_provider_id")
    names = {p.id: p.name for p in db.query(Player).filter(
        Player.id.in_([pid for pid, _ in resolved.values()])).all()} if resolved else {}
    players: Dict[str, Dict] = {}
    unresolved = 0
    match_ids = []
    for match, lineup, quality in lineups:
        if match.id not in match_ids:
            match_ids.append(match.id)
        source = lineup.source or ""
        provider_id = lineup.player_provider_id or ""
        resolved_hit = resolved.get((source, provider_id))
        if resolved_hit is None and provider_id:
            # Cross-source fallback: same provider id under any source is
            # still exact-ID evidence (never name-based).
            for (src, pid_key), value in resolved.items():
                if pid_key == provider_id:
                    resolved_hit = value
                    break
        if resolved_hit is None:
            unresolved += 1
            key = f"unresolved:{source}:{provider_id}"
            entry = players.setdefault(key, _blank_history(lineup.player_name))
            entry["unresolved"] = True
        else:
            pid, method = resolved_hit
            key = f"player:{pid}"
            entry = players.setdefault(key, _blank_history(names.get(pid, "")))
            entry["canonical_player_id"] = pid
            entry["resolution_method"] = method
        entry["appearances"].append({
            "match_id": match.id,
            "kickoff": str(match.kickoff_at),
            "starting": bool(lineup.is_starting),
            "position": lineup.position,
            "formation": lineup.formation,
            "quality": quality,
        })
    naive_cutoff = as_naive_utc(cutoff)
    for entry in players.values():
        _summarize(entry)
        if entry["appearances"] and naive_cutoff is not None:
            try:
                last = entry["appearances"][-1]["kickoff"]
                from datetime import datetime as _dt

                last_dt = _dt.fromisoformat(str(last).replace("Z", "+00:00"))
                last_naive = last_dt.replace(tzinfo=None)
                entry["days_since_last_appearance"] = round(
                    max(0.0, (naive_cutoff - last_naive).total_seconds() / 86400.0), 2)
            except Exception:
                entry["days_since_last_appearance"] = None
    return {"players": players, "unresolved_appearances": unresolved,
            "matches_considered": len(match_ids),
            "mode": mode.value,
            "as_of": str(as_naive_utc(cutoff))}


def _blank_history(name: str) -> Dict:
    return {"player_name": name or "", "appearances": []}


def _summarize(entry: Dict) -> None:
    apps = sorted(entry["appearances"], key=lambda a: (a["kickoff"], a["match_id"]))
    entry["appearances"] = apps
    entry["matches_played"] = len(apps)
    entry["starts"] = sum(1 for a in apps if a["starting"])
    entry["substitute_appearances"] = entry["matches_played"] - entry["starts"]
    entry["minutes_played"] = None  # not in schema: unknown, never synthesized
    for window in WINDOWS:
        recent = apps[-window:]
        entry[f"starts_last_{window}"] = sum(1 for a in recent if a["starting"])
        entry[f"appearances_last_{window}"] = len(recent)
        entry[f"appearance_frequency_{window}"] = (
            round(len(recent) / window, 4) if window else None)
        entry[f"starting_frequency_{window}"] = (
            round(sum(1 for a in recent if a["starting"]) / len(recent), 4)
            if recent else None)
    entry["days_since_last_appearance"] = None  # set by caller with cutoff
    entry["season_appearances"] = entry["matches_played"]
