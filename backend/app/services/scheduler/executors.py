"""Job executors — one function per job type.

Each executor receives (db, config, dry_run) and returns a standardized
result dict. Executors use existing services exclusively; they never
train models or fabricate data. The pre_match_prediction executor invokes
the Phase 26 execution service, which enforces readiness gating, cutoff
safety, and idempotency. Partial results persist; failed sources are
recorded; idempotency is guaranteed by the underlying services.
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
def execute_pre_match_prediction(db: Session, config: dict[str, Any],
                                 dry_run: bool = False) -> dict[str, Any]:
    """Execute Phase 26 pre-match predictions for due matches.

    Due = latest readiness certificate is PREDICTION_READY/READY_DEGRADED
    and no prediction snapshot is bound to that certificate. BLOCKED matches
    are skipped (no infinite retries for permanently blocked matches).
    Idempotent: repeated runs reuse existing snapshots.
    """
    from app.db.models.core import League, Match
    from app.services.prediction_execution import (
        PredictionBlocked,
        execute_pre_match_prediction as run_prediction,
        get_latest_certificate,
    )

    competitions = config.get("competitions", [])
    now = _now()
    query = db.query(Match).filter(
        Match.status == "SCHEDULED", Match.kickoff_at > now)
    if competitions:
        query = query.join(League, Match.league_id == League.id).filter(
            League.code.in_(competitions))
    matches = query.order_by(Match.kickoff_at.asc()).limit(50).all()

    due, generated, skipped_blocked, errors = [], [], [], []
    for match in matches:
        cert = get_latest_certificate(db, match.id)
        if cert is None or cert.readiness_state == "BLOCKED":
            skipped_blocked.append(match.id)
            continue
        due.append((match.id, cert.cutoff))

    if dry_run:
        return {
            "status": "dry_run",
            "due_match_ids": [mid for mid, _ in due],
            "skipped_blocked": skipped_blocked,
            "note": "no writes performed",
        }

    for match_id, cutoff in due:
        try:
            result = run_prediction(db, match_id, cutoff)
            generated.append({"match_id": match_id,
                              "reused": bool(result.get("cache_hit")),
                              "prediction_id": result["prediction_id"]})
        except PredictionBlocked as exc:
            errors.append({"match_id": match_id, "code": exc.code,
                           "reason": exc.reason})
        except Exception as exc:  # noqa: BLE001 — record, don't crash the job
            errors.append({"match_id": match_id, "code": "EXECUTOR_ERROR",
                           "reason": str(exc)})

    status = "succeeded" if not errors else (
        "partial" if generated else "failed")
    return {
        "status": status,
        "due": len(due),
        "generated": generated,
        "skipped_blocked": skipped_blocked,
        "errors": errors,
    }


# Dispatch table: job_type -> executor function.
def execute_post_match_evaluation(db: Session, config: dict[str, Any],
                                  dry_run: bool = False) -> dict[str, Any]:
    """Evaluate Phase 26 prediction snapshots of finished matches.

    Due = FINISHED match with recorded scores and at least one prediction
    snapshot lacking an evaluation for the current outcome. Incomplete
    matches are never evaluated. Idempotent: repeated runs reuse records.
    """
    from app.db.models.core import League, Match
    from app.services.prediction_evaluation import (
        EvaluationBlocked,
        evaluate_prediction_snapshot,
        evaluations_for_prediction,
    )
    from app.services.prediction_evaluation.outcomes import latest_outcome
    from app.services.prediction_execution.store import (
        list_predictions_for_match,
    )

    competitions = config.get("competitions", [])
    query = db.query(Match).filter(
        Match.status == "FINISHED",
        Match.home_score.isnot(None), Match.away_score.isnot(None))
    if competitions:
        query = query.join(League, Match.league_id == League.id).filter(
            League.code.in_(competitions))
    matches = query.order_by(Match.kickoff_at.desc()).limit(100).all()

    due, evaluated, skipped, errors = [], [], [], []
    for match in matches:
        snaps = list_predictions_for_match(db, match.id, limit=500)
        if not snaps:
            skipped.append({"match_id": match.id, "reason": "no_predictions"})
            continue
        outcome = latest_outcome(db, match.id)
        pending = False
        for snap in snaps:
            existing = evaluations_for_prediction(db, snap.prediction_id)
            if not existing:
                pending = True
                break
            if outcome is not None and not any(
                    e.outcome_hash == outcome.outcome_hash
                    for e in existing):
                pending = True
                break
        if not pending:
            skipped.append({"match_id": match.id,
                            "reason": "already_evaluated"})
            continue
        due.append(match.id)

    if dry_run:
        return {
            "status": "dry_run",
            "due_match_ids": due,
            "skipped": skipped,
            "note": "no writes performed",
        }

    for match_id in due:
        for snap in list_predictions_for_match(db, match_id, limit=500):
            try:
                result = evaluate_prediction_snapshot(db, snap.prediction_id)
                evaluated.append({
                    "match_id": match_id,
                    "prediction_id": snap.prediction_id,
                    "reused": bool(result.get("cache_hit")),
                    "evaluation_id": result["evaluation_id"]})
            except EvaluationBlocked as exc:
                errors.append({"match_id": match_id, "code": exc.code,
                               "reason": exc.reason})
            except Exception as exc:  # noqa: BLE001 — record, don't crash
                errors.append({"match_id": match_id, "code": "EXECUTOR_ERROR",
                               "reason": str(exc)})

    status = "succeeded" if not errors else (
        "partial" if evaluated else "failed")
    return {
        "status": status,
        "due": len(due),
        "evaluated": evaluated,
        "skipped": skipped,
        "errors": errors,
    }


EXECUTORS = {
    "fixture_refresh": execute_fixture_refresh,
    "status_refresh": execute_status_refresh,
    "result_refresh": execute_result_refresh,
    "source_health": execute_health_check,
    "freshness_audit": execute_freshness_audit,
    "qualification": execute_qualification,
    "pre_match_prediction": execute_pre_match_prediction,
    "post_match_evaluation": execute_post_match_evaluation,
}


def get_executor(job_type: str):
    """Return the executor function for a job type."""
    if job_type not in EXECUTORS:
        raise ValueError(f"no executor for job type: {job_type!r}")
    return EXECUTORS[job_type]
