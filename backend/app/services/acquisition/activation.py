"""Source activation gate + scheduler abstraction + enrichment (Phase 11).

Activation states: candidate → validated → active, with degraded/disabled.
A source becomes active only after identity, fixture, timestamp, duplicate,
season, status, idempotency, secret-scan, rate-limit and failure-path
checks. The decision record (checks + reason) is the audit trail.

Scheduler: job registry with scope/source/priority/last/next run. The real
scheduler stays outside this phase.

Enrichment: completed-match detail requests (result/events/stats/lineups/xG)
only where the source supports them; every result preserves source,
retrieved_at, effective_at and quality; unknown timing stays ineligible.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.acquisition import AcquisitionJob, SourceActivation

STATE_CANDIDATE, STATE_VALIDATED, STATE_ACTIVE = "candidate", "validated", "active"
STATE_DEGRADED, STATE_DISABLED = "degraded", "disabled"

GATE_CHECKS = ("identity", "fixture", "timestamp", "duplicate", "season",
               "status", "idempotency", "secret_scan", "rate_limit",
               "failure_path")


def activation_gate(db: Session, source: str, evidence: Dict,
                    decided_by: str = "validation-gate") -> Dict:
    """Evaluate gate checks from caller-supplied evidence. All ten must pass
    for activation; anything else stays candidate with reasons recorded."""
    results = {}
    for check in GATE_CHECKS:
        passed, detail = evidence.get(check, (False, "no evidence supplied"))
        results[check] = {"passed": bool(passed), "detail": str(detail)[:300]}
    failures = [check for check, result in results.items() if not result["passed"]]
    state = STATE_ACTIVE if not failures else STATE_CANDIDATE
    row = SourceActivation(source=source, state=state, decided_by=decided_by,
                           checks=results,
                           reason="" if not failures else
                           f"blocked by: {', '.join(failures)}")
    db.add(row)
    db.commit()
    return {"source": source, "state": state, "checks": results,
            "failures": failures, "activation_id": row.id}


def set_state(db: Session, source: str, state: str,
              reason: str = "", decided_by: str = "operator") -> Dict:
    if state not in (STATE_CANDIDATE, STATE_VALIDATED, STATE_ACTIVE,
                     STATE_DEGRADED, STATE_DISABLED):
        raise ValueError(f"unknown activation state: {state}")
    row = SourceActivation(source=source, state=state, decided_by=decided_by,
                           checks={}, reason=reason[:500])
    db.add(row)
    db.commit()
    return {"source": source, "state": state, "activation_id": row.id}


def current_state(db: Session, source: str) -> str:
    row = db.query(SourceActivation).filter_by(source=source).order_by(
        SourceActivation.id.desc()).first()
    return row.state if row else STATE_CANDIDATE


def ensure_jobs(db: Session) -> List[Dict]:
    """Conceptual job registry (fixture_discovery, fixture_refresh,
    completed_match_refresh, historical_backfill)."""
    defaults = [
        {"name": "fixture_discovery", "source": "", "priority": 10,
         "scope": {"window": "upcoming"}},
        {"name": "fixture_refresh", "source": "", "priority": 20,
         "scope": {"window": "upcoming"}},
        {"name": "completed_match_refresh", "source": "", "priority": 30,
         "scope": {"window": "recent-results"}},
        {"name": "historical_backfill", "source": "", "priority": 100,
         "scope": {"window": "historical"}},
    ]
    out = []
    for default in defaults:
        row = db.query(AcquisitionJob).filter_by(name=default["name"]).first()
        if row is None:
            row = AcquisitionJob(name=default["name"], source=default["source"],
                                 priority=default["priority"], scope=default["scope"])
            db.add(row)
            db.commit()
        out.append({"name": row.name, "source": row.source,
                    "priority": row.priority, "scope": row.scope,
                    "last_run": str(row.last_run) if row.last_run else None,
                    "next_run": str(row.next_run) if row.next_run else None})
    return out


def mark_job_run(db: Session, name: str) -> None:
    row = db.query(AcquisitionJob).filter_by(name=name).first()
    if row is not None:
        row.last_run = datetime.now(timezone.utc)
        db.commit()


SUPPORT_MATRIX = {
    "api_football": ("result", "events", "statistics", "lineups"),
    "odds_api": (),
    "football_data_co_uk": ("result", "statistics"),
    "statsbomb": ("events", "lineups", "xg"),
    "csv": ("result", "statistics"),
}


def enrichment_request(db: Session, match_id: int, source: str,
                       kinds: Optional[List[str]] = None) -> Dict:
    """Describe what enrichment a source can provide for a finished match.
    Capability-checked: unsupported kinds are skipped with reasons, never
    requested. Timing/quality travel with every granted item."""
    from app.db.models.core import Match

    match = db.get(Match, match_id)
    if match is None:
        return {"error": "match missing"}
    supported = SUPPORT_MATRIX.get(source, ())
    requested = kinds or ["result", "events", "statistics", "lineups", "xg"]
    granted, skipped = [], []
    for kind in requested:
        if kind in supported:
            granted.append({"kind": kind, "source": source,
                            "retrieved_at": None, "effective_at": None,
                            "quality": "unknown",
                            "note": "timing established on retrieval; "
                                    "strict eligibility needs effective_at"})
        else:
            skipped.append({"kind": kind, "reason": f"{source} does not "
                                                    f"support {kind}"})
    return {"match_id": match_id, "source": source, "granted": granted,
            "skipped": skipped}
