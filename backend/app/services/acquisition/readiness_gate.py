"""Current-Season Data Quality, Reconciliation & Pre-Match Readiness Gate (Phase 25).

Provides a strict multi-stage validation gate between acquired current-season fixtures
and downstream prediction / intelligence execution:

  ACTIVE PROVIDER -> CURRENT-SEASON FIXTURE ->
    Gate 1: Structural Validity & Metadata Integrity ->
    Gate 2: Reconciliation & Cross-Source Identity ->
    Gate 3: Temporal Validity & Cutoff Policy ->
    Gate 4: Feature Availability & Leakage Eligibility ->
    Gate 5: Canonical Certificate Generation (PREMATCH_CERTIFICATE_V1) ->
      PREDICTION_READY | READY_DEGRADED | BLOCKED

ZERO FABRICATED DATA: Operates in readiness-only mode when 2026/27 fixture coverage is 0.
"""
from __future__ import annotations

import enum
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.core import League, Lineup, Match, Team
from app.db.models.enums import MatchStatus
from app.db.models.odds import OddsSnapshot
from app.db.models.prematch import PreMatchReadinessCertificate
from app.db.models.provenance import MatchSourceMapping, TeamProviderMapping
from app.db.models.reconciliation import ReconciliationConflict
from app.services.acquisition.current_season import current_canonical_season
from app.services.features.temporal import as_naive_utc


class PreMatchReadinessState(str, enum.Enum):
    PREDICTION_READY = "PREDICTION_READY"
    READY_DEGRADED = "READY_DEGRADED"
    BLOCKED = "BLOCKED"


CERTIFICATE_CONTRACT_VERSION = "PREMATCH_CERTIFICATE_V1"
MIN_HISTORICAL_MATCHES_PER_TEAM = 3  # Minimum past finished matches before cutoff


def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


def compute_canonical_certificate_hash(payload: Dict[str, Any]) -> str:
    """Deterministically compute SHA-256 hash of canonical certificate JSON."""
    canonical_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def evaluate_pre_match_readiness(
    db: Session,
    match_id: int,
    cutoff: Optional[datetime] = None,
    mode: str = "PRE_MATCH",
) -> Dict[str, Any]:
    """Pure, side-effect-free evaluation of a match through Gates 1 to 4.

    Evaluates:
    - Gate 1: Structural validity & metadata integrity
    - Gate 2: Reconciliation & cross-source identity validation
    - Gate 3: Temporal validity & cutoff enforcement
    - Gate 4: Feature availability & leakage eligibility

    Returns structured evaluation verdict without mutating database.
    """
    now = datetime.now(timezone.utc)
    now_naive = as_naive_utc(now)

    match = db.get(Match, match_id)
    if match is None:
        return {
            "match_id": match_id,
            "competition": "UNKNOWN",
            "season": "UNKNOWN",
            "home_team_id": 0,
            "away_team_id": 0,
            "kickoff_at": None,
            "cutoff": _iso_utc(cutoff or now),
            "readiness_state": PreMatchReadinessState.BLOCKED.value,
            "eligible": False,
            "mode": mode,
            "gate_verdicts": {
                "gate1_structural": {"passed": False, "reasons": ["MATCH_NOT_FOUND"]},
                "gate2_reconciliation": {"passed": False, "reasons": ["MATCH_NOT_FOUND"]},
                "gate3_temporal": {"passed": False, "reasons": ["MATCH_NOT_FOUND"]},
                "gate4_features": {"passed": False, "status": "fail", "reasons": ["MATCH_NOT_FOUND"], "warnings": []},
            },
            "blocking_reasons": ["MATCH_NOT_FOUND"],
            "warnings": [],
            "missing_features": {"core": ["match"], "optional": []},
            "evaluated_at": now.isoformat(),
        }

    # Derive competition & season
    league = db.get(League, match.league_id) if match.league_id else None
    competition = league.code if league else "UNKNOWN"
    season = league.season if (league and league.season) else current_canonical_season()

    kickoff_naive = as_naive_utc(match.kickoff_at)
    if cutoff is None:
        # Default cutoff is now, unless in pre-match where cutoff must be strictly before kickoff
        eval_cutoff = now
    else:
        eval_cutoff = cutoff
    eval_cutoff_naive = as_naive_utc(eval_cutoff)

    blocking_reasons: List[str] = []
    warnings: List[str] = []
    missing_core: List[str] = []
    missing_optional: List[str] = []

    # -------------------------------------------------------------
    # GATE 1: Structural Validity & Metadata Integrity
    # -------------------------------------------------------------
    g1_reasons: List[str] = []
    if not match.league_id or league is None:
        g1_reasons.append("UNKNOWN_COMPETITION")
    if match.home_team_id is None or match.away_team_id is None:
        g1_reasons.append("UNRESOLVED_TEAMS")
    elif match.home_team_id == match.away_team_id:
        g1_reasons.append("IDENTICAL_TEAMS")
    if match.kickoff_at is None:
        g1_reasons.append("MISSING_KICKOFF")

    # Provider identification check
    has_provider_identity = bool(match.provider and match.provider_match_id)
    if not has_provider_identity:
        source_mapping = db.query(MatchSourceMapping).filter_by(match_id=match.id).first()
        if source_mapping:
            has_provider_identity = True
    if not has_provider_identity:
        g1_reasons.append("MISSING_PROVIDER_IDENTITY")

    g1_passed = len(g1_reasons) == 0
    blocking_reasons.extend(g1_reasons)

    # -------------------------------------------------------------
    # GATE 2: Reconciliation & Cross-Source Identity Validation
    # -------------------------------------------------------------
    g2_reasons: List[str] = []

    # Check existing reconciliation conflicts
    conflicts = db.query(ReconciliationConflict).filter_by(
        entity_type="match",
        canonical_entity_id=match.id,
        resolution_status="unresolved",
    ).all()

    critical_fields = ("score_mismatch", "team_mismatch", "league_mismatch", "duplicate_source_match")
    for conflict in conflicts:
        field_prefix = conflict.field.split(":")[0] if conflict.field else ""
        if conflict.severity == "critical" or field_prefix in critical_fields:
            g2_reasons.append(f"CRITICAL_RECONCILIATION_CONFLICT: {conflict.field}")

    # Proximity check for duplicate suspicion
    if match.league_id and match.home_team_id and match.away_team_id and kickoff_naive:
        window_start = kickoff_naive - timedelta(hours=24)
        window_end = kickoff_naive + timedelta(hours=24)
        duplicates = db.query(Match).filter(
            Match.id != match.id,
            Match.league_id == match.league_id,
            Match.home_team_id == match.home_team_id,
            Match.away_team_id == match.away_team_id,
            Match.kickoff_at >= window_start,
            Match.kickoff_at <= window_end,
        ).all()
        if duplicates:
            dup_ids = [str(d.id) for d in duplicates]
            g2_reasons.append(f"DUPLICATE_SUSPICION_AWAITING_RECONCILIATION: matches={','.join(dup_ids)}")

    g2_passed = len(g2_reasons) == 0
    blocking_reasons.extend(g2_reasons)

    # -------------------------------------------------------------
    # GATE 3: Temporal Validity & Cutoff Enforcement
    # -------------------------------------------------------------
    g3_reasons: List[str] = []

    # Check cancelled / postponed status
    if match.status in (MatchStatus.POSTPONED.value, MatchStatus.CANCELLED.value, "SUSPENDED", "ABANDONED"):
        g3_reasons.append(f"FIXTURE_POSTPONED_OR_CANCELLED: status={match.status}")

    # Stale fixture check: kickoff passed while status is still scheduled / pre-match
    ref_time = now_naive
    if eval_cutoff_naive is not None and eval_cutoff_naive > now_naive:
        ref_time = eval_cutoff_naive
    if kickoff_naive and ref_time and kickoff_naive < ref_time:
        if match.status in (MatchStatus.SCHEDULED.value, MatchStatus.PRE_MATCH.value):
            g3_reasons.append("STALE_FIXTURE_AWAITING_SYNC")

    # Mode-dependent cutoff evaluation
    if mode == "PRE_MATCH":
        if kickoff_naive is not None and eval_cutoff_naive is not None:
            if eval_cutoff_naive >= kickoff_naive:
                g3_reasons.append("CUTOFF_AT_OR_AFTER_KICKOFF")

    g3_passed = len(g3_reasons) == 0
    blocking_reasons.extend(g3_reasons)

    # -------------------------------------------------------------
    # GATE 4: Feature Availability & Leakage Eligibility
    # -------------------------------------------------------------
    g4_reasons: List[str] = []
    g4_warnings: List[str] = []

    # Historical context: strictly query data before eval_cutoff
    home_matches_count = 0
    away_matches_count = 0
    if match.home_team_id and match.away_team_id and eval_cutoff_naive:
        home_matches_count = db.query(Match).filter(
            (Match.home_team_id == match.home_team_id) | (Match.away_team_id == match.home_team_id),
            Match.status == MatchStatus.FINISHED.value,
            Match.kickoff_at < eval_cutoff_naive,
        ).count()

        away_matches_count = db.query(Match).filter(
            (Match.home_team_id == match.away_team_id) | (Match.away_team_id == match.away_team_id),
            Match.status == MatchStatus.FINISHED.value,
            Match.kickoff_at < eval_cutoff_naive,
        ).count()

    if home_matches_count < MIN_HISTORICAL_MATCHES_PER_TEAM or away_matches_count < MIN_HISTORICAL_MATCHES_PER_TEAM:
        g4_reasons.append(
            f"INSUFFICIENT_HISTORICAL_MATCHES: home={home_matches_count}, away={away_matches_count} "
            f"(minimum {MIN_HISTORICAL_MATCHES_PER_TEAM} required)"
        )
        missing_core.append("historical_match_context")

    # Optional features: Lineups & Market Odds
    has_lineups = False
    if match.id:
        lineup_count = db.query(Lineup).filter_by(match_id=match.id).count()
        has_lineups = lineup_count > 0
    if not has_lineups:
        missing_optional.append("lineups")
        g4_warnings.append("OPTIONAL_FEATURE_MISSING: lineups")

    has_odds = False
    if match.id and eval_cutoff_naive:
        odds_count = db.query(OddsSnapshot).filter(
            OddsSnapshot.match_id == match.id,
            OddsSnapshot.timestamp <= eval_cutoff_naive,
        ).count()
        has_odds = odds_count > 0
    if not has_odds:
        missing_optional.append("market_odds")
        g4_warnings.append("OPTIONAL_FEATURE_MISSING: market_odds")

    g4_status = "fail" if g4_reasons else ("degraded" if (missing_optional or g4_warnings) else "pass")
    g4_passed = len(g4_reasons) == 0
    blocking_reasons.extend(g4_reasons)
    warnings.extend(g4_warnings)

    # -------------------------------------------------------------
    # OVERALL READINESS STATE SYNTHESIS
    # -------------------------------------------------------------
    if not g1_passed or not g2_passed or not g3_passed or not g4_passed:
        overall_state = PreMatchReadinessState.BLOCKED
    elif g4_status == "degraded" or len(warnings) > 0:
        overall_state = PreMatchReadinessState.READY_DEGRADED
    else:
        overall_state = PreMatchReadinessState.PREDICTION_READY

    return {
        "match_id": match.id,
        "competition": competition,
        "season": season,
        "home_team_id": match.home_team_id or 0,
        "away_team_id": match.away_team_id or 0,
        "kickoff_at": _iso_utc(match.kickoff_at),
        "cutoff": _iso_utc(eval_cutoff),
        "readiness_state": overall_state.value,
        "eligible": overall_state in (PreMatchReadinessState.PREDICTION_READY, PreMatchReadinessState.READY_DEGRADED),
        "mode": mode,
        "gate_verdicts": {
            "gate1_structural": {"passed": g1_passed, "reasons": g1_reasons},
            "gate2_reconciliation": {"passed": g2_passed, "reasons": g2_reasons},
            "gate3_temporal": {"passed": g3_passed, "reasons": g3_reasons},
            "gate4_features": {
                "passed": g4_passed,
                "status": g4_status,
                "reasons": g4_reasons,
                "warnings": g4_warnings,
            },
        },
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "missing_features": {
            "core": missing_core,
            "optional": missing_optional,
        },
        "evaluated_at": now.isoformat(),
    }


def generate_readiness_certificate(
    db: Session,
    match_id: int,
    cutoff: Optional[datetime] = None,
    mode: str = "PRE_MATCH",
) -> PreMatchReadinessCertificate:
    """Generate and persist an immutable pre-match readiness certificate.

    CRITICAL INVARIANTS:
    - Evaluates Gates 1-4 via evaluate_pre_match_readiness.
    - Contract version: PREMATCH_CERTIFICATE_V1.
    - Canonical JSON hashing (SHA-256) over normalized payload.
    - Post-cutoff changes never overwrite existing certificate rows in-place.
    - If a previous certificate exists, links supersedes_certificate_id.
    """
    evaluation = evaluate_pre_match_readiness(db, match_id, cutoff=cutoff, mode=mode)

    # Find existing certificate for this match (if any)
    existing = (
        db.query(PreMatchReadinessCertificate)
        .filter_by(match_id=match_id)
        .order_by(PreMatchReadinessCertificate.id.desc())
        .first()
    )

    cert_uuid = uuid.uuid4().hex[:12]
    cert_id = f"cert_{match_id}_{cert_uuid}"

    # Build canonical payload for hashing
    payload = {
        "certificate_version": CERTIFICATE_CONTRACT_VERSION,
        "readiness_contract_version": CERTIFICATE_CONTRACT_VERSION,
        "match_id": evaluation["match_id"],
        "competition": evaluation["competition"],
        "season": evaluation["season"],
        "home_team_id": evaluation["home_team_id"],
        "away_team_id": evaluation["away_team_id"],
        "kickoff_at": evaluation["kickoff_at"],
        "cutoff": evaluation["cutoff"],
        "readiness_state": evaluation["readiness_state"],
        "gate_verdicts": evaluation["gate_verdicts"],
        "blocking_reasons": sorted(evaluation["blocking_reasons"]),
        "warnings": sorted(evaluation["warnings"]),
    }
    payload_hash = compute_canonical_certificate_hash(payload)

    # Parse cutoff & kickoff datetimes for SQL storage
    cutoff_dt = datetime.fromisoformat(evaluation["cutoff"]) if evaluation["cutoff"] else datetime.now(timezone.utc)
    kickoff_dt = datetime.fromisoformat(evaluation["kickoff_at"]) if evaluation["kickoff_at"] else cutoff_dt

    certificate = PreMatchReadinessCertificate(
        certificate_id=cert_id,
        certificate_version=CERTIFICATE_CONTRACT_VERSION,
        readiness_contract_version=CERTIFICATE_CONTRACT_VERSION,
        match_id=evaluation["match_id"],
        competition=evaluation["competition"],
        season=evaluation["season"],
        home_team_id=evaluation["home_team_id"],
        away_team_id=evaluation["away_team_id"],
        kickoff_at=kickoff_dt,
        cutoff=cutoff_dt,
        readiness_state=evaluation["readiness_state"],
        gate_verdicts=evaluation["gate_verdicts"],
        blocking_reasons=evaluation["blocking_reasons"],
        warnings=evaluation["warnings"],
        payload_hash=payload_hash,
        supersedes_certificate_id=existing.certificate_id if existing else None,
    )

    db.add(certificate)
    db.commit()
    db.refresh(certificate)
    return certificate


def get_current_season_prematch_summary(
    db: Session,
    season: str = "current",
) -> Dict[str, Any]:
    """Compile distinct, non-collapsing operational counters for current-season readiness.

    Accurately reports:
    - season
    - operational_mode ("readiness_only" vs "operational")
    - provider_state (e.g. UNAVAILABLE, ACTIVE, etc.)
    - fixture_count (total fixtures)
    - reconciled_count (passed Gates 1 & 2)
    - temporally_valid_count (passed Gate 3)
    - quality_passed_count (passed Gate 4)
    - prediction_ready_count
    - ready_degraded_count
    - blocked_count
    - blocking_reasons breakdown
    """
    canonical_season = current_canonical_season() if season == "current" else season
    now = datetime.now(timezone.utc)

    # Determine provider state
    from app.db.models.acquisition import SourceActivation
    from app.services.acquisition.activation import ActivationState

    latest_activation = (
        db.query(SourceActivation)
        .order_by(SourceActivation.id.desc())
        .first()
    )
    provider_state = latest_activation.state if latest_activation else ActivationState.UNAVAILABLE.value

    # Find current-season leagues
    leagues = db.query(League).filter_by(season=canonical_season).all()
    league_ids = [lg.id for lg in leagues]

    matches: List[Match] = []
    if league_ids:
        matches = db.query(Match).filter(Match.league_id.in_(league_ids)).all()

    fixture_count = len(matches)
    operational_mode = "readiness_only" if fixture_count == 0 or provider_state != ActivationState.ACTIVE.value else "operational"

    if fixture_count == 0:
        return {
            "season": canonical_season,
            "operational_mode": operational_mode,
            "provider_state": provider_state,
            "fixture_count": 0,
            "reconciled_count": 0,
            "temporally_valid_count": 0,
            "quality_passed_count": 0,
            "prediction_ready_count": 0,
            "ready_degraded_count": 0,
            "blocked_count": 0,
            "blocking_reasons": {},
            "checked_at": now.isoformat(),
        }

    # Evaluate each current-season match
    reconciled_count = 0
    temporally_valid_count = 0
    quality_passed_count = 0
    prediction_ready_count = 0
    ready_degraded_count = 0
    blocked_count = 0
    blocking_reasons_counter: Dict[str, int] = {}

    for m in matches:
        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        gv = res["gate_verdicts"]

        # Reconciled = Gate 1 & Gate 2 passed
        if gv["gate1_structural"]["passed"] and gv["gate2_reconciliation"]["passed"]:
            reconciled_count += 1

        # Temporally valid = Gate 3 passed
        if gv["gate3_temporal"]["passed"]:
            temporally_valid_count += 1

        # Quality passed = Gate 4 passed (even if degraded)
        if gv["gate4_features"]["passed"]:
            quality_passed_count += 1

        st = res["readiness_state"]
        if st == PreMatchReadinessState.PREDICTION_READY.value:
            prediction_ready_count += 1
        elif st == PreMatchReadinessState.READY_DEGRADED.value:
            ready_degraded_count += 1
        else:
            blocked_count += 1

        for r in res["blocking_reasons"]:
            reason_key = r.split(":")[0]
            blocking_reasons_counter[reason_key] = blocking_reasons_counter.get(reason_key, 0) + 1

    return {
        "season": canonical_season,
        "operational_mode": operational_mode,
        "provider_state": provider_state,
        "fixture_count": fixture_count,
        "reconciled_count": reconciled_count,
        "temporally_valid_count": temporally_valid_count,
        "quality_passed_count": quality_passed_count,
        "prediction_ready_count": prediction_ready_count,
        "ready_degraded_count": ready_degraded_count,
        "blocked_count": blocked_count,
        "blocking_reasons": blocking_reasons_counter,
        "checked_at": now.isoformat(),
    }
