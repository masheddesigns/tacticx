"""Production snapshot + dataset boundaries + readiness report (Phase 11).

production_data_snapshot identifies the exact data universe a prediction run
consumed (snapshot id, timestamps, universe/feature/market/source versions,
hash). Historical predictions are never modified.

Dataset boundaries (historical / validation / test / production-upcoming)
are explicit labels by kickoff date + table: backtests must stay inside the
historical boundary; upcoming data belongs to production readiness.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Match

BOUNDARIES = ("historical", "validation", "test", "production")


def dataset_boundary(kickoff, validation_cut: Optional[datetime] = None,
                     test_cut: Optional[datetime] = None) -> str:
    """Label one kickoff by dataset boundary. Cutoffs explicit per call;
    default splits are documented, never hidden."""
    from app.services.features.temporal import as_naive_utc

    naive = as_naive_utc(kickoff)
    if naive is None:
        return "unknown"
    validation_cut = validation_cut or datetime(2024, 1, 1)
    test_cut = test_cut or datetime(2025, 1, 1)
    if naive < as_naive_utc(validation_cut):
        return "historical"
    if naive < as_naive_utc(test_cut):
        return "validation"
    if naive < as_naive_utc(datetime.now(timezone.utc)):
        return "test"
    return "production"


def production_snapshot(db: Session, match_ids: List[int],
                        feature_version: str = "features_v1",
                        model_version: str = "ensemble_v1") -> Dict:
    """Read-only snapshot descriptor for a prediction run's universe."""
    from app.db.models.freshness import MatchObservation
    from app.db.models.provenance import MatchSourceMapping

    matches = db.query(Match).filter(Match.id.in_(match_ids)).all() if match_ids else []
    sources = set()
    observations = 0
    for match in matches:
        if match.provider:
            sources.add(match.provider)
        for mapping in db.query(MatchSourceMapping).filter_by(match_id=match.id).all():
            sources.add(mapping.source)
        observations += db.query(MatchObservation).filter_by(match_id=match.id).count()
    canonical = json.dumps({
        "match_ids": sorted(match_ids),
        "sources": sorted(sources),
        "feature_version": feature_version,
        "model_version": model_version,
        "observations": observations,
    }, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return {
        "snapshot_id": f"universe_{digest}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "match_universe_version": digest,
        "feature_version": feature_version,
        "market_snapshot_version": "market_probability_v1",
        "source_versions": sorted(sources),
        "match_count": len(matches),
        "observation_count": observations,
        "hash": digest,
    }


def readiness_report(db: Session, match_id: int) -> Dict:
    """Per-match readiness (data only — never a betting recommendation)."""
    from app.services.acquisition.universe import entry
    from app.services.freshness import eligibility

    match = db.get(Match, match_id)
    if match is None:
        return {"error": "match missing"}
    now = datetime.now(timezone.utc)
    universe_entry = entry(db, match)
    verdict = eligibility.check_eligibility(db, match_id, now,
                                            mode="production_strict")
    families = verdict.get("families", {})
    league = db.get(League, match.league_id) if match.league_id else None
    home = universe_entry.get("home_team") or ""
    away = universe_entry.get("away_team") or ""
    return {
        "match": f"{home} vs {away}",
        "kickoff": universe_entry.get("scheduled_kickoff"),
        "competition": universe_entry.get("competition"),
        "home": home, "away": away,
        "fixture_status": universe_entry.get("lifecycle"),
        "source_count": universe_entry.get("source_count"),
        "freshness": verdict.get("freshness", {}),
        "temporal_quality": verdict.get("temporal_quality"),
        "historical_features": "AVAILABLE" if families.get(
            "team_form", {}).get("eligible") else "UNAVAILABLE",
        "player_features": "AVAILABLE" if families.get(
            "player_form", {}).get("eligible") else "UNAVAILABLE",
        "xg": "AVAILABLE" if families.get("xg", {}).get("eligible") else "UNAVAILABLE",
        "market": "AVAILABLE" if families.get("market", {}).get("eligible") else "UNAVAILABLE",
        "prediction": "ELIGIBLE" if verdict.get("eligible") else "INELIGIBLE",
        "mode": "DEGRADED" if verdict.get("degraded_mode") else "FULL",
        "warnings": verdict.get("reasons", []) + verdict.get("warnings", []),
    }
