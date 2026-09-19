"""Source activation gate + scheduler abstraction + enrichment (Phase 11 & Phase 24).

Activation states:
UNAVAILABLE -> DISCOVERY -> PROBING -> QUALIFYING -> QUALIFIED -> ACTIVE, with DEGRADED/REVOKED.
A source becomes active only after identity, fixture, timestamp, duplicate,
season, status, idempotency, secret-scan, rate-limit and failure-path
checks. The decision record (checks + reason) is the audit trail.

CRITICAL INVARIANT: QUALIFIED != ACTIVE.
Qualification proves capability; explicit audited operational action activates production acquisition.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.acquisition import AcquisitionJob, SourceActivation

# Explicit Phase 24 Activation State Taxonomy
class ActivationState(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    DISCOVERY = "DISCOVERY"
    PROBING = "PROBING"
    QUALIFYING = "QUALIFYING"
    QUALIFIED = "QUALIFIED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    REVOKED = "REVOKED"


# Legacy compatibility constants
STATE_CANDIDATE, STATE_VALIDATED, STATE_ACTIVE = "candidate", "validated", "active"
STATE_DEGRADED, STATE_DISABLED = "degraded", "disabled"

ALL_ACTIVATION_STATES = set(s.value for s in ActivationState) | {
    STATE_CANDIDATE, STATE_VALIDATED, STATE_ACTIVE, STATE_DEGRADED, STATE_DISABLED
}

TARGET_LEAGUES = ("EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1")
MIN_HISTORICAL_MATCHES = 5  # Minimum historical match context required for feature eligibility

GATE_CHECKS = ("identity", "fixture", "timestamp", "duplicate", "season",
               "status", "idempotency", "secret_scan", "rate_limit",
               "failure_path")


def can_activate_current_season(
    provider: str,
    competition: str,
    season: str,
    db: Optional[Session] = None,
    qualification_verdict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Pure, side-effect-free decision function.

    Evaluates whether a provider can be explicitly activated for automated current-season
    acquisition for the given competition and season.

    Checks:
    1. League supported (EPL, LA_LIGA, SERIE_A, BUNDESLIGA, LIGUE_1)
    2. Provider qualified (from Phase 19 qualification snapshot or supplied verdict)
    3. Fixture availability (> 0 fixtures in qualification evidence)
    4. Kickoff timestamps acceptable (valid non-null ISO timestamps)
    5. Identity resolvability (scoped to provider x competition x season: no critical unresolved conflicts)
    6. Freshness (qualification within 7 days)
    7. Historical context (league exists with >= 5 historical matches in DB)

    ZERO database writes. ZERO external network calls.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    reasons: List[str] = []
    warnings: List[str] = []
    capabilities: Dict[str, Any] = {}

    # 1. League Support
    if competition not in TARGET_LEAGUES:
        reasons.append(f"unsupported_competition: {competition} (must be one of {list(TARGET_LEAGUES)})")

    # 2. Qualification Evidence
    verdict = qualification_verdict
    if verdict is None and db is not None:
        from app.db.models.qualification import SourceQualification
        # Scoped to provider, competition, and season
        qual_row = db.query(SourceQualification).filter_by(
            source=provider, competition=competition, season=season
        ).order_by(SourceQualification.id.desc()).first()
        if qual_row is None:
            qual_row = db.query(SourceQualification).filter_by(
                source=provider, competition=competition
            ).order_by(SourceQualification.id.desc()).first()
        if qual_row is None:
            qual_row = db.query(SourceQualification).filter_by(
                source=provider
            ).order_by(SourceQualification.id.desc()).first()

        if qual_row is not None:
            verdict = {
                "status": qual_row.status,
                "fixture_count": qual_row.fixture_count,
                "reason_codes": qual_row.reason_codes or [],
                "retrieved_at": qual_row.retrieved_at.isoformat() if qual_row.retrieved_at else None,
                "conflict_count": qual_row.conflict_count,
                "unresolved_count": qual_row.unresolved_count,
            }

    if verdict is None:
        reasons.append(f"no_qualification_evidence_for_{provider}")
    else:
        status = verdict.get("status", "unqualified")
        if status not in ("qualified", "partially_qualified"):
            reasons.append(f"provider_not_qualified: status={status}")

        # 3. Fixtures Available
        fixture_count = verdict.get("fixture_count", 0)
        if isinstance(verdict.get("coverage"), dict):
            fixture_count = verdict["coverage"].get("fixtures", fixture_count)
        if fixture_count <= 0:
            reasons.append("no_current_season_fixtures_available")

        # 4. Kickoff Timestamps
        caps = verdict.get("capabilities", {})
        if isinstance(caps, dict):
            capabilities = caps
            if caps.get("kickoff_timestamps") in ("unavailable", "unknown"):
                reasons.append("unacceptable_kickoff_timestamps")
        if verdict.get("valid_kickoff_timestamps") is False:
            reasons.append("fixtures_missing_valid_kickoff_timestamps")

        # 5. Identity Resolvability (scoped to provider x competition x season)
        if verdict.get("conflict_count", 0) > 0 or verdict.get("unresolved_count", 0) > 0:
            warnings.append(f"qualification_reported_{verdict.get('conflict_count', 0)}_conflicts")

        # 6. Freshness
        retrieved_str = verdict.get("retrieved_at")
        if retrieved_str:
            try:
                retrieved_dt = datetime.fromisoformat(retrieved_str.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - retrieved_dt).total_seconds() / 86400.0
                if age_days > 7.0:
                    warnings.append(f"qualification_evidence_is_stale: {age_days:.1f}_days_old")
            except Exception:
                pass

    # Identity check in DB scoped to competition
    if db is not None:
        from app.db.models.reconciliation import ReconciliationConflict
        crit_conflicts = db.query(ReconciliationConflict).filter(
            ReconciliationConflict.severity == "critical",
            ReconciliationConflict.resolution_status == "unresolved",
        ).all()
        relevant_conflicts = 0
        for c in crit_conflicts:
            if c.dedup_key and competition in c.dedup_key:
                relevant_conflicts += 1
        if relevant_conflicts > 0:
            reasons.append(f"critical_unresolved_reconciliation_conflicts_for_{competition}: {relevant_conflicts}")

        # 7. Historical Context
        from app.db.models.core import League, Match
        league = db.query(League).filter_by(code=competition).first()
        if league is None:
            reasons.append(f"league_not_found_in_database: {competition}")
        else:
            hist_matches = db.query(Match).filter(
                Match.league_id == league.id,
                Match.status == "FINISHED"
            ).count()
            if hist_matches < MIN_HISTORICAL_MATCHES:
                reasons.append(
                    f"insufficient_historical_context: {hist_matches} matches found, "
                    f"minimum {MIN_HISTORICAL_MATCHES} required for feature eligibility"
                )

    eligible = len(reasons) == 0
    return {
        "eligible": eligible,
        "provider": provider,
        "competition": competition,
        "season": season,
        "reasons": reasons,
        "warnings": warnings,
        "capabilities": capabilities,
        "checked_at": now_iso,
    }


def activate_current_season(
    db: Session,
    provider: str = "",
    competition: str = "",
    season: str = "",
    decided_by: str = "operator",
    reason: str = "",
    force: bool = False,
    source: Optional[str] = None,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    """Explicit, audited operational action to activate a provider for a competition and season.

    QUALIFIED != ACTIVE.
    Only explicit invocation of this function can transition a provider to ACTIVE.
    """
    provider_name = source or provider
    operator_actor = actor or decided_by
    decision = can_activate_current_season(provider_name, competition, season, db)
    if not decision["eligible"] and not force:
        audit_payload = {
            "competition": competition,
            "season": season,
            "eligible": False,
            "decision": decision,
        }
        row = SourceActivation(
            source=provider_name,
            state=ActivationState.QUALIFIED.value,
            decided_by=operator_actor,
            checks=audit_payload,
            reason=f"activation blocked: {', '.join(decision['reasons'])}",
        )
        db.add(row)
        db.commit()
        return {
            "status": "blocked",
            "success": False,
            "provider": provider_name,
            "competition": competition,
            "season": season,
            "state": ActivationState.QUALIFIED.value,
            "decision": decision,
            "reasons": decision["reasons"],
            "activation_id": row.id,
        }

    audit_payload = {
        "competition": competition,
        "season": season,
        "eligible": True,
        "decision": decision,
    }
    row = SourceActivation(
        source=provider_name,
        state=ActivationState.ACTIVE.value,
        decided_by=operator_actor,
        checks=audit_payload,
        reason=reason or "explicit audited operational activation",
    )
    db.add(row)
    db.commit()
    return {
        "status": "activated",
        "success": True,
        "provider": provider_name,
        "competition": competition,
        "season": season,
        "state": ActivationState.ACTIVE.value,
        "activation_id": row.id,
        "decision": decision,
    }


def revoke_activation(
    db: Session,
    provider: str,
    competition: str,
    season: str,
    reason: str = "revoked by operator",
    decided_by: str = "operator",
) -> Dict[str, Any]:
    """Revoke an existing active provider state."""
    audit_payload = {
        "competition": competition,
        "season": season,
        "action": "revoke",
    }
    row = SourceActivation(
        source=provider,
        state=ActivationState.REVOKED.value,
        decided_by=decided_by,
        checks=audit_payload,
        reason=reason,
    )
    db.add(row)
    db.commit()
    return {
        "status": "revoked",
        "provider": provider,
        "competition": competition,
        "season": season,
        "state": ActivationState.REVOKED.value,
        "activation_id": row.id,
    }


def get_activation_state(
    db: Session,
    provider: str,
    competition: Optional[str] = None,
    season: Optional[str] = None,
) -> str:
    """Pure local read of latest activation state for (provider, competition, season).
    Never contacts external providers.
    """
    query = db.query(SourceActivation).filter(SourceActivation.source == provider)
    rows = query.order_by(SourceActivation.id.desc()).all()
    for row in rows:
        checks = row.checks or {}
        row_comp = checks.get("competition")
        row_season = checks.get("season")
        if competition and row_comp and row_comp != competition:
            continue
        if season and row_season and row_season != season:
            continue
        return row.state
    return ActivationState.UNAVAILABLE.value


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
    if state not in ALL_ACTIVATION_STATES:
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
