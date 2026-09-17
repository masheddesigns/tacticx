"""Versioned player-feature snapshots (Phase 9).

player_features_v1 payload per side: appearances, form, team aggregates,
lineup/formation features — each with quality + contributors + provenance.
Snapshots are deterministic (sorted keys, payload hash) and persisted
additively (never overwritten). Repeated generation with identical inputs
yields identical output including the hash.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.player_intelligence import (
    PlayerFeatureProvenance,
    PlayerFeatureSnapshot,
)
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.player_intelligence import (
    appearances,
    availability as availability_svc,
    lineup_features,
    player_form,
    quality as quality_svc,
    team_event_features,
)

FEATURE_VERSION = "player_features_v1"


def _hash(payload: Dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     default=str).encode()).hexdigest()


def build_snapshot(db: Session, match_id: int, cutoff: datetime,
                   mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                   persist: bool = True) -> Dict:
    """Build (and optionally persist) the player-feature snapshot."""
    match = db.get(Match, match_id)
    if match is None:
        raise ValueError(f"unknown match: {match_id}")
    naive_cutoff = as_naive_utc(cutoff)
    if naive_cutoff is None:
        raise ValueError("cutoff is required")

    def side(team_id: Optional[int]) -> Dict:
        if team_id is None:
            return {"status": "unavailable",
                    "reason": "team missing on canonical match"}
        apps = appearances.team_appearances(db, team_id, cutoff, mode, match_id)
        forms = player_form.player_form(db, team_id, cutoff, mode, match_id)
        team = team_event_features.team_features(db, team_id, cutoff, mode,
                                                 match_id,
                                                 precomputed_forms=forms,
                                                 precomputed_appearances=apps)
        lineups = lineup_features.lineup_features(db, team_id, cutoff, mode,
                                                  match_id)
        n_matches = apps["matches_considered"]
        return {
            "status": "ok" if n_matches else "unavailable",
            "appearances": {"players": apps["players"],
                            "matches_considered": n_matches,
                            "unresolved_appearances": apps["unresolved_appearances"]},
            "form": {"players": forms["players"],
                     "matches_considered": forms["matches_considered"]},
            "team": team,
            "lineups": lineups,
            "quality": quality_svc.for_mode(
                mode.value, n_matches,
                identity_ok=apps["unresolved_appearances"] == 0),
            "contributors": [
                {"key": key,
                 "canonical_player_id": entry.get("canonical_player_id"),
                 "player_name": entry.get("player_name"),
                 "matches_played": entry.get("matches_played")}
                for key, entry in sorted(apps["players"].items())],
        }

    home_id, away_id = match.home_team_id, match.away_team_id
    home = side(home_id)
    away = side(away_id)
    availability = availability_svc.family_availability(
        db, home_id, cutoff, match_id) if home_id is not None else {"families": {}}
    payload = {"match_id": match_id, "cutoff": str(naive_cutoff),
               "feature_version": FEATURE_VERSION, "mode": mode.value,
               "home": home, "away": away, "availability": availability}
    digest = _hash(payload)
    provenance = {"feature_version": FEATURE_VERSION, "mode": mode.value,
                  "cutoff": str(naive_cutoff),
                  "sources": ["lineups:statsbomb", "events:statsbomb",
                              "identity:phase8-mappings"],
                  "payload_hash": digest}
    snapshot_id = None
    if persist:
        existing = db.query(PlayerFeatureSnapshot).filter_by(
            match_id=match_id, cutoff=naive_cutoff,
            feature_version=FEATURE_VERSION, mode=mode.value).all()
        same = next((r for r in existing if r.payload_hash == digest), None)
        if same is not None:
            snapshot_id = same.id
        else:
            row = PlayerFeatureSnapshot(
                match_id=match_id, cutoff=naive_cutoff,
                feature_version=FEATURE_VERSION, mode=mode.value,
                payload=payload, payload_hash=digest, provenance=provenance)
            db.add(row)
            db.flush()
            snapshot_id = row.id
            _record_provenance(db, snapshot_id, home, away)
            db.commit()
    return {"match_id": match_id, "cutoff": str(naive_cutoff),
            "feature_version": FEATURE_VERSION, "mode": mode.value,
            "home": _slim(home), "away": _slim(away),
            "availability": availability, "provenance": provenance,
            "payload_hash": digest, "snapshot_id": snapshot_id}


def _slim(side: Dict) -> Dict:
    """API-sized view (full payload stays in the stored snapshot)."""
    if side.get("status") != "ok":
        return {"status": side.get("status"), "reason": side.get("reason", ""),
                "quality": side.get("quality", {})}
    return {"status": "ok",
            "team": side.get("team", {}),
            "lineups": side.get("lineups", {}),
            "quality": side.get("quality", {}),
            "contributors": side.get("contributors", [])[:25],
            "n_form_players": len((side.get("form", {}) or {}).get("players", {}))}


def _record_provenance(db: Session, snapshot_id: int, home: Dict, away: Dict) -> None:
    for side_name, side in (("home", home), ("away", away)):
        if side.get("status") != "ok":
            continue
        for feature in ("team", "lineups"):
            db.add(PlayerFeatureProvenance(
                snapshot_id=snapshot_id,
                feature_name=f"{side_name}.{feature}",
                source="statsbomb",
                source_record_ids={"mode": side.get("team", {}).get("mode", "")},
                canonical_ids={},
                quality=(side.get("quality", {}) or {}).get("quality", "unknown")))
