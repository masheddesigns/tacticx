"""Cutoff-safe player form (Phase 9).

player_form_3/5/10 from explicit measurable statistics: appearance/start
rates, per-appearance event rates (minutes unavailable, so per-90 is not
computed — per-appearance is the honest denominator). Minimum sample gates
are explicit: below threshold -> unavailable/low quality, never zero-filled
(zero goals in 1 appearance is not evidence of anything).
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.features.temporal import TemporalMode
from app.services.player_intelligence import appearances as appearance_svc
from app.services.player_intelligence import event_features as registry

WINDOWS = (3, 5, 10)
MIN_APPEARANCES_FOR_RATES = 3


def _event_index(db: Session, team_id: int,
                 match_ids: List[int]) -> Dict:
    """One indexed fetch: (match_id, player_name) -> event types, side-
    attributed to the team. Callers count per player/window in Python
    (no N+1 queries)."""
    from app.db.models.core import Match, MatchEvent

    sides = {}
    for match in db.query(Match).filter(Match.id.in_(match_ids)).all():
        if match.home_team_id == team_id:
            sides[match.id] = "home"
        elif match.away_team_id == team_id:
            sides[match.id] = "away"
    index: Dict = {}
    if not match_ids:
        return {"sides": sides, "events": index}
    for row in db.query(MatchEvent).filter(
            MatchEvent.match_id.in_(match_ids)).all():
        if sides.get(row.match_id) is None or row.team != sides[row.match_id]:
            continue
        if not row.player_name:
            continue
        index.setdefault((row.match_id, row.player_name), []).append(
            (row.event_type or "").lower())
    return {"sides": sides, "events": index}


def _count_indexed(index: Dict, canonical_name: str,
                   match_id_set) -> Dict[str, int]:
    counts = {name: 0 for name in registry.registered_names()}
    if not canonical_name:
        return counts
    events = index["events"]
    for mid in match_id_set:
        for event_type in events.get((mid, canonical_name), []):
            for name, spec in registry.EVENT_FEATURE_DEFINITIONS.items():
                if event_type in spec["source_event_types"]:
                    counts[name] += 1
                    break
    return counts


def player_form(db: Session, team_id: int, cutoff: datetime,
                mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                target_match_id: Optional[int] = None) -> Dict:
    """Per-player form envelopes with sample gates."""
    base = appearance_svc.team_appearances(db, team_id, cutoff, mode,
                                           target_match_id)
    match_ids: List[int] = []
    for entry in base["players"].values():
        for app in entry["appearances"]:
            if app["match_id"] not in match_ids:
                match_ids.append(app["match_id"])
    index = _event_index(db, team_id, match_ids)
    from app.db.models.core import Player as PlayerModel

    names = {}
    for key, entry in base["players"].items():
        pid = entry.get("canonical_player_id")
        if pid is not None:
            player = db.get(PlayerModel, pid)
            names[key] = (player.name if player else "") or ""
        else:
            names[key] = ""
    forms = {}
    for key, entry in base["players"].items():
        counts = _count_indexed(index, names[key], set(match_ids))
        form_entry = {"player_name": entry["player_name"],
                      "canonical_player_id": entry.get("canonical_player_id"),
                      "unresolved": bool(entry.get("unresolved", False)),
                      "matches_played": entry["matches_played"],
                      "event_counts": counts}
        for window in WINDOWS:
            recent = entry["appearances"][-window:]
            n = len(recent)
            gate_ok = n >= MIN_APPEARANCES_FOR_RATES
            form_entry[f"form_{window}"] = {
                "available": gate_ok,
                "appearances": n,
                "starts": sum(1 for a in recent if a["starting"]),
                "appearance_frequency": round(n / window, 4),
            }
            if gate_ok:
                recent_ids = {a["match_id"] for a in recent}
                window_counts = _count_indexed(index, names[key], recent_ids)
                for name in registry.registered_names():
                    form_entry[f"form_{window}"][f"{name}_per_appearance"] = round(
                        window_counts[name] / n, 4)
            else:
                form_entry[f"form_{window}"]["reason"] = (
                    f"below minimum sample ({n} < {MIN_APPEARANCES_FOR_RATES}); "
                    "unavailable, not zero")
        # Quality: sample-size driven, identity-aware.
        if entry.get("unresolved"):
            form_entry["sample_quality"] = "low"
        elif entry["matches_played"] >= 5:
            form_entry["sample_quality"] = "high"
        elif entry["matches_played"] >= MIN_APPEARANCES_FOR_RATES:
            form_entry["sample_quality"] = "medium"
        else:
            form_entry["sample_quality"] = "low"
        forms[key] = form_entry
    return {"players": forms, "matches_considered": base["matches_considered"],
            "unresolved_appearances": base["unresolved_appearances"],
            "mode": base["mode"], "as_of": base["as_of"]}
