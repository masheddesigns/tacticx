"""Operational monitoring — alert conditions, anomaly detection, freshness.

Alerts are machine-readable events (not external notification integrations).
Anomaly detection uses conservative heuristic checks, never ML. All checks
are descriptive — they never trigger automatic remediation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.db.models.lifecycle import SourceHealth
from app.db.models.scheduler import AcquisitionJobRecord


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Alert conditions ---


def check_alerts(db: Session) -> list[dict[str, Any]]:
    """Evaluate all alert conditions and return machine-readable events."""
    alerts: list[dict[str, Any]] = []
    alerts.extend(_no_qualified_source_alerts(db))
    alerts.extend(_provider_unavailable_alerts(db))
    alerts.extend(_repeated_failures_alerts(db))
    alerts.extend(_rate_limited_alerts(db))
    alerts.extend(_stale_source_alerts(db))
    alerts.extend(_zero_fixtures_alerts(db))
    alerts.extend(_fixture_count_drop_alerts(db))
    alerts.extend(_job_stuck_alerts(db))
    alerts.extend(_lock_stale_alerts(db))
    return alerts


def _no_qualified_source_alerts(db: Session) -> list[dict[str, Any]]:
    from app.services.provider_qualification import registry as reg_mod

    alerts = []
    reg = reg_mod.get_registry()
    for entry in reg.ordered(enabled_only=True):
        if entry.qualification_status in ("unqualified", "rejected",
                                           "unavailable"):
            alerts.append({
                "severity": "warning",
                "condition": "no_qualified_source",
                "source": entry.source_id,
                "detail": f"qualification={entry.qualification_status}",
            })
    return alerts


def _provider_unavailable_alerts(db: Session) -> list[dict[str, Any]]:
    alerts = []
    for row in db.query(SourceHealth).filter(
            SourceHealth.state.in_(["unavailable", "authentication_error"])).all():
        alerts.append({
            "severity": "warning",
            "condition": "provider_unavailable",
            "source": row.source,
            "detail": f"state={row.state}, consecutive_failures={row.consecutive_failures or 0}",
        })
    return alerts


def _repeated_failures_alerts(db: Session) -> list[dict[str, Any]]:
    alerts = []
    for row in db.query(SourceHealth).filter(
            SourceHealth.consecutive_failures >= 3).all():
        alerts.append({
            "severity": "warning",
            "condition": "repeated_failures",
            "source": row.source,
            "detail": f"consecutive_failures={row.consecutive_failures}",
        })
    return alerts


def _rate_limited_alerts(db: Session) -> list[dict[str, Any]]:
    alerts = []
    for row in db.query(SourceHealth).filter(
            SourceHealth.state == "rate_limited").all():
        alerts.append({
            "severity": "info",
            "condition": "rate_limited",
            "source": row.source,
            "detail": f"backoff_until={row.backoff_until}",
        })
    return alerts


def _stale_source_alerts(db: Session) -> list[dict[str, Any]]:
    from app.services.provider_qualification.freshness import freshness_for

    alerts = []
    for league in db.query(League).all():
        freshness = freshness_for(db, "", league.code)
        state = freshness.get("state", "unknown")
        if state in ("stale", "expired"):
            alerts.append({
                "severity": "warning",
                "condition": "stale_source",
                "source": freshness.get("source", ""),
                "competition": league.code,
                "detail": f"freshness={state}",
            })
    return alerts


def _zero_fixtures_alerts(db: Session) -> list[dict[str, Any]]:
    alerts = []
    now = _now()
    for league in db.query(League).all():
        count = db.query(Match).filter(
            Match.league_id == league.id,
            Match.kickoff_at > now).count()
        if count == 0:
            alerts.append({
                "severity": "info",
                "condition": "unexpected_zero_fixtures",
                "competition": league.code,
                "detail": "no upcoming fixtures found",
            })
    return alerts


def _fixture_count_drop_alerts(db: Session) -> list[dict[str, Any]]:
    """Detect sudden fixture-count drops: compare latest two runs per job type."""
    alerts = []
    for job_type in ("fixture_refresh", "status_refresh"):
        runs = db.query(AcquisitionJobRecord).filter(
            AcquisitionJobRecord.job_type == job_type,
            AcquisitionJobRecord.status.in_(["succeeded", "partial"])
        ).order_by(AcquisitionJobRecord.id.desc()).limit(2).all()
        if len(runs) == 2:
            prev = runs[1].details or {}
            curr = runs[0].details or {}
            prev_count = prev.get("total_fixtures", 0)
            curr_count = curr.get("total_fixtures", 0)
            if prev_count > 0 and curr_count < prev_count * 0.5:
                alerts.append({
                    "severity": "warning",
                    "condition": "fixture_count_drop",
                    "detail": f"from {prev_count} to {curr_count} fixtures "
                              f"(job {runs[0].job_id})",
                })
    return alerts


def _job_stuck_alerts(db: Session) -> list[dict[str, Any]]:
    """Detect jobs stuck in 'running' beyond their timeout."""
    alerts = []
    now = _now()
    running = db.query(AcquisitionJobRecord).filter(
        AcquisitionJobRecord.status == "running").all()
    for record in running:
        if record.started_at:
            age_seconds = (now - record.started_at).total_seconds()
            config = {}
            try:
                from app.services.scheduler.config import get_job_config
                config = get_job_config(record.job_type)
            except ValueError:
                pass
            timeout = config.get("timeout_seconds", 300)
            if age_seconds > timeout * 2:
                alerts.append({
                    "severity": "critical",
                    "condition": "acquisition_job_stuck",
                    "job_id": record.job_id,
                    "detail": f"running for {int(age_seconds)}s (timeout={int(timeout)}s)",
                })
    return alerts


def _lock_stale_alerts(db: Session) -> list[dict[str, Any]]:
    from app.db.models.scheduler import AcquisitionJobLock

    alerts = []
    now = _now()
    locks = db.query(AcquisitionJobLock).all()
    for lock in locks:
        expires = lock.expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires and expires < now:
            age = (now - expires).total_seconds()
            alerts.append({
                "severity": "warning",
                "condition": "lock_stale",
                "lock_key": lock.lock_key,
                "detail": f"expired {int(age)}s ago",
            })
    return alerts


# --- Anomaly detection ---


def detect_anomalies(db: Session) -> list[dict[str, Any]]:
    """Conservative heuristic anomaly checks. No ML, no prediction signals."""
    anomalies: list[dict[str, Any]] = []
    anomalies.extend(_fixture_count_anomaly(db))
    anomalies.extend(_identity_degradation_anomaly(db))
    anomalies.extend(_conflict_spike_anomaly(db))
    anomalies.extend(_impossible_status_transition_anomaly(db))
    anomalies.extend(_duplicate_rate_anomaly(db))
    return anomalies


def _fixture_count_anomaly(db: Session) -> list[dict[str, Any]]:
    """If historical range exists, detect unusual fixture-count changes."""
    anomalies = []
    for league in db.query(League).all():
        counts = []
        for run in db.query(AcquisitionJobRecord).filter(
                AcquisitionJobRecord.job_type == "fixture_refresh",
                AcquisitionJobRecord.competition == league.code,
                AcquisitionJobRecord.status.in_(["succeeded", "partial"])
        ).order_by(AcquisitionJobRecord.id.desc()).limit(10).all():
            details = run.details or {}
            counts.append(details.get("total_fixtures", 0))
        if len(counts) >= 3:
            avg = sum(counts[1:]) / max(1, len(counts) - 1)
            current = counts[0]
            if avg > 0 and current < avg * 0.3:
                anomalies.append({
                    "type": "fixture_count_anomaly",
                    "competition": league.code,
                    "detail": f"current={current}, avg={avg:.0f}",
                })
    return anomalies


def _identity_degradation_anomaly(db: Session) -> list[dict[str, Any]]:
    """Detect significant increases in unresolved teams."""
    from app.db.models.reconciliation import UnresolvedRecord

    anomalies = []
    recent = db.query(UnresolvedRecord).filter(
        UnresolvedRecord.entity_type == "team",
        UnresolvedRecord.status == "pending").count()
    if recent > 50:
        anomalies.append({
            "type": "identity_degradation",
            "detail": f"{recent} unresolved teams pending",
        })
    return anomalies


def _conflict_spike_anomaly(db: Session) -> list[dict[str, Any]]:
    """Detect sudden reconciliation conflict increases."""
    from app.db.models.reconciliation import ReconciliationConflict

    anomalies = []
    unresolved = db.query(ReconciliationConflict).filter(
        ReconciliationConflict.resolution_status == "unresolved").count()
    if unresolved > 100:
        anomalies.append({
            "type": "conflict_spike",
            "detail": f"{unresolved} unresolved conflicts",
        })
    return anomalies


def _impossible_status_transition_anomaly(db: Session) -> list[dict[str, Any]]:
    """Detect observations suggesting impossible status transitions
    (e.g. finished → scheduled)."""
    from app.db.models.freshness import MatchObservation

    anomalies = []
    bad = db.query(MatchObservation).filter(
        MatchObservation.field == "status",
        MatchObservation.new_value == "SCHEDULED",
        MatchObservation.previous_value == "FINISHED").count()
    if bad > 0:
        anomalies.append({
            "type": "impossible_status_transition",
            "detail": f"{bad} observations: FINISHED → SCHEDULED",
        })
    return anomalies


def _duplicate_rate_anomaly(db: Session) -> list[dict[str, Any]]:
    """Detect sudden increases in duplicate observation rates."""
    anomalies = []
    runs = db.query(AcquisitionJobRecord).filter(
        AcquisitionJobRecord.status.in_(["succeeded", "partial"])
    ).order_by(AcquisitionJobRecord.id.desc()).limit(10).all()
    for run in runs:
        total = run.new_observations + run.duplicate_observations
        if total > 0 and run.duplicate_observations / total > 0.9:
            anomalies.append({
                "type": "duplicate_rate_anomaly",
                "job_id": run.job_id,
                "detail": f"duplicates={run.duplicate_observations}/{total}",
            })
    return anomalies


# --- Operational summary ---


def operational_summary(db: Session) -> dict[str, Any]:
    """Combine alerts + anomalies + job stats into one summary dict."""
    alerts = check_alerts(db)
    anomalies = detect_anomalies(db)
    recent = db.query(AcquisitionJobRecord).order_by(
        AcquisitionJobRecord.id.desc()).limit(20).all()
    by_status = {}
    for rec in recent:
        by_status[rec.status] = by_status.get(rec.status, 0) + 1
    from app.db.models.scheduler import AcquisitionJobLock

    active_locks = db.query(AcquisitionJobLock).count()
    return {
        "as_of": _now().isoformat(),
        "alerts": alerts,
        "alert_count": len(alerts),
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
        "recent_job_status_distribution": by_status,
        "active_locks": active_locks,
    }
