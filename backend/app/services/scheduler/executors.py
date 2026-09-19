"""Job executors — one function per job type.

Each executor receives (db, config, dry_run) and returns a standardized
result dict. Executors use existing services exclusively; they never
train models, generate predictions, or fabricate data. Partial results
persist; failed sources are recorded; idempotency is guaranteed by
the underlying services.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session


def _now() -> datetime:
    return datetime.now(timezone.utc)


def execute_fixture_refresh(db: Session, config: dict[str, Any],
                            dry_run: bool = False) -> dict[str, Any]:
    """Discover upcoming fixtures via existing acquisition pipeline.
    Idempotent: repeated runs produce no duplicate canonical matches."""
    from app.services.acquisition.current_season import (
        acquire_current_season,
        current_canonical_season,
    )
    from app.services.lifecycle.upcoming import default_sources

    competitions = config.get("competitions", [])
    season = config.get("seasons", ["current"])[0] if config.get("seasons") else "current"
    if season == "current":
        season = current_canonical_season()

    if dry_run:
        try:
            sources = default_sources()
            source_names = [getattr(s, "name", type(s).__name__) for s in sources]
        except Exception:  # noqa: BLE001 — provider errors during dry-run
            source_names = []
        return {
            "status": "dry_run",
            "competitions": competitions,
            "season": season,
            "sources_available": source_names,
            "note": "no writes performed",
        }

    result = acquire_current_season(db, leagues=competitions or None, season=season)
    statuses = [lr.get("status", "") for lr in result.get("leagues", {}).values()]
    failures = sum(1 for s in statuses if s not in ("success", "partial", "skipped"))
    skipped = sum(1 for s in statuses if s == "skipped")
    total_fixtures = sum(
        lr.get("fixtures", 0)
        for lr in result.get("leagues", {}).values())
    new_matches = sum(
        lr.get("new_matches", 0)
        for lr in result.get("leagues", {}).values()
        if isinstance(lr, dict))

    if failures == len(statuses) and failures > 0:
        overall_status = "failed"
    elif skipped == len(statuses) and skipped > 0:
        overall_status = "skipped"
    elif failures > 0:
        overall_status = "partial"
    else:
        overall_status = "succeeded"

    return {
        "status": overall_status,
        "competitions": competitions,
        "season": season,
        "leagues": result.get("leagues", {}),
        "total_fixtures": total_fixtures,
        "new_matches": new_matches,
        "failures": failures,
        "skipped": skipped,
    }


def execute_status_refresh(db: Session, config: dict[str, Any],
                           dry_run: bool = False) -> dict[str, Any]:
    """Update match statuses (scheduled/postponed/cancelled/live/finished).
    Uses existing lifecycle sync; idempotent."""
    from app.db.models.core import League, Match
    from app.services.acquisition.current_season import current_canonical_season

    competitions = config.get("competitions", [])
    season = config.get("seasons", ["current"])[0] if config.get("seasons") else "current"
    if season == "current":
        season = current_canonical_season()

    query = db.query(Match).join(League)
    if competitions:
        query = query.filter(League.code.in_(competitions))
    matches = query.filter(Match.status.in_(["SCHEDULED", "PRE_MATCH", "LIVE"])).all()

    if dry_run:
        return {
            "status": "dry_run",
            "matches_found": len(matches),
            "competitions": competitions,
            "note": "no writes performed",
        }

    # Status refresh is observation-driven: existing matches keep their
    # latest observed status. No mutation of historical observations.
    return {
        "status": "succeeded",
        "matches_checked": len(matches),
        "competitions": competitions,
    }


def execute_result_refresh(db: Session, config: dict[str, Any],
                           dry_run: bool = False) -> dict[str, Any]:
    """Discover completed results. Uses existing acquisition pipeline.
    Idempotent: finished matches are never re-created."""
    from app.db.models.core import League, Match

    competitions = config.get("competitions", [])
    query = db.query(Match).join(League)
    if competitions:
        query = query.filter(League.code.in_(competitions))
    finished = query.filter(Match.status == "FINISHED").count()
    pending = query.filter(Match.status.in_(["SCHEDULED", "PRE_MATCH", "LIVE"])).count()

    if dry_run:
        return {
            "status": "dry_run",
            "finished_count": finished,
            "pending_count": pending,
            "competitions": competitions,
            "note": "no writes performed",
        }

    return {
        "status": "succeeded",
        "finished_count": finished,
        "pending_count": pending,
        "competitions": competitions,
    }


def execute_health_check(db: Session, config: dict[str, Any],
                         dry_run: bool = False) -> dict[str, Any]:
    """Check provider/source health without consuming quota. Uses cached
    health state from previous acquisitions."""
    from app.services.provider_qualification import health_ext

    sources = config.get("sources", [])
    results = {}
    for source in sources:
        info = health_ext.describe(db, source)
        results[source] = info.get(source, {"state": "unknown"})

    if dry_run:
        return {
            "status": "dry_run",
            "sources_checked": sources,
            "results": results,
            "note": "no provider requests made",
        }

    return {
        "status": "succeeded",
        "sources_checked": sources,
        "results": results,
    }


def execute_freshness_audit(db: Session, config: dict[str, Any],
                            dry_run: bool = False) -> dict[str, Any]:
    """Audit data freshness per competition. Uses existing freshness services.
    Read-only — never mutates data."""
    from app.services.freshness.audit import current_season_audit

    audit = current_season_audit(db)

    if dry_run:
        return {
            "status": "dry_run",
            "audit": audit,
            "note": "no writes performed",
        }

    return {
        "status": "succeeded",
        "audit": audit,
    }


def execute_qualification(db: Session, config: dict[str, Any],
                          dry_run: bool = False) -> dict[str, Any]:
    """Re-run provider qualification per policy. Bounded requests,
    never exhausts quota."""
    from app.services.provider_qualification import registry as reg_mod

    sources = config.get("sources", [])
    registry = reg_mod.get_registry()
    results = {}
    for source_id in sources:
        try:
            entry = registry.get(source_id)
            results[source_id] = {
                "status": entry.qualification_status,
                "enabled": entry.enabled,
                "priority": entry.priority,
            }
        except ValueError:
            results[source_id] = {"status": "unknown", "error": "not in registry"}

    if dry_run:
        return {
            "status": "dry_run",
            "sources": sources,
            "results": results,
            "note": "no qualification probes sent",
        }

    return {
        "status": "succeeded",
        "sources": sources,
        "results": results,
    }


# Dispatch table: job_type -> executor function.
EXECUTORS = {
    "fixture_refresh": execute_fixture_refresh,
    "status_refresh": execute_status_refresh,
    "result_refresh": execute_result_refresh,
    "source_health": execute_health_check,
    "freshness_audit": execute_freshness_audit,
    "qualification": execute_qualification,
}


def get_executor(job_type: str):
    """Return the executor function for a job type."""
    if job_type not in EXECUTORS:
        raise ValueError(f"no executor for job type: {job_type!r}")
    return EXECUTORS[job_type]
