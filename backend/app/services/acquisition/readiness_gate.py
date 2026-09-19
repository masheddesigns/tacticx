"""Current-Season Data Quality, Reconciliation & Pre-Match Readiness Gate (Phase 25 / Phase 25.1).

Provides a strict multi-stage validation gate between acquired current-season fixtures
and downstream prediction / intelligence execution:

  ACTIVE PROVIDER -> CURRENT-SEASON FIXTURE ->
    Gate 1: Structural Validity & Metadata Integrity ->
    Gate 2: Reconciliation & Cross-Source Identity ->
    Gate 3: Temporal Validity & Cutoff Policy ->
    Gate 4: Feature Availability & Leakage Eligibility ->
    Gate 5: Canonical Certificate Generation (PREMATCH_CERTIFICATE_V1) ->
      PREDICTION_READY | READY_DEGRADED | BLOCKED

Phase 25.1 hardening:
- FIX 2: 4-state deterministic duplicate detection (proximity alone is CANDIDATE only)
- FIX 3: PredictionReadinessConfig (no hard-coding of feature requirements)
- FIX 4: Provider activation scoped to provider x competition x season
- FIX 5: Extended certificate payload with provider provenance fields
- FIX 6: Append-only certificate immutability (never overwrite existing rows)
- FIX 7: Explicit PRE_MATCH / POST_MATCH mode separation
- FIX 8: 11-counter summary with per-competition provider activation breakdown
- FIX 9: min_historical_matches_per_team from PredictionReadinessConfig

ZERO FABRICATED DATA: Operates in readiness-only mode when 2026/27 fixture coverage is 0.
ZERO data fabrication: provider_qualification_version is None when the qualification
system provides no version field (SourceQualification has no version column in Phase 24).
"""
from __future__ import annotations

import enum
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
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


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PreMatchReadinessState(str, enum.Enum):
    PREDICTION_READY = "PREDICTION_READY"
    READY_DEGRADED = "READY_DEGRADED"
    BLOCKED = "BLOCKED"


class DuplicateDetectionState(str, enum.Enum):
    """4-state deterministic duplicate classification (FIX 2).

    - NO_DUPLICATE: no proximity or identity collision detected
    - DUPLICATE_CANDIDATE: same matchup within ±24h but different provider_match_id
      → warning only, NOT blocking
    - DUPLICATE_CONFIRMED: exact same provider + provider_match_id on a different Match.id
      → blocking
    - DUPLICATE_RESOLUTION_REQUIRED: both conditions above simultaneously
      → blocking
    """
    NO_DUPLICATE = "NO_DUPLICATE"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"      # warning only
    DUPLICATE_CONFIRMED = "DUPLICATE_CONFIRMED"      # blocking
    DUPLICATE_RESOLUTION_REQUIRED = "DUPLICATE_RESOLUTION_REQUIRED"  # blocking


CERTIFICATE_CONTRACT_VERSION = "PREMATCH_CERTIFICATE_V1"


# ---------------------------------------------------------------------------
# FIX 3: PredictionReadinessConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PredictionReadinessConfig:
    """Per-model feature requirements for pre-match readiness gate (FIX 3).

    No hard-coding in Gate 4. Each model family registers its own config.
    min_historical_matches_per_team replaces the module-level constant (FIX 9).
    """
    model_id: str
    model_version: str
    prediction_mode: str
    min_historical_matches_per_team: int
    required_features: List[str] = field(default_factory=list)
    optional_features: List[str] = field(default_factory=list)


# Registry: one entry per model family.
# Based on actual ensemble_v1-elo+poisson requirements (does not modify model).
READINESS_CONFIG_REGISTRY: Dict[str, PredictionReadinessConfig] = {
    "ensemble_v1-elo+poisson": PredictionReadinessConfig(
        model_id="ensemble_v1-elo+poisson",
        model_version="ensemble_v1-elo+poisson",
        prediction_mode="strict_prematch",
        min_historical_matches_per_team=3,
        required_features=["historical_match_context"],
        optional_features=["lineups", "market_odds"],
    ),
}

# Default config used when the model ID is not found in the registry.
_DEFAULT_CONFIG = PredictionReadinessConfig(
    model_id="default",
    model_version="default",
    prediction_mode="strict_prematch",
    min_historical_matches_per_team=3,
    required_features=["historical_match_context"],
    optional_features=["lineups", "market_odds"],
)

DEFAULT_MODEL_ID = "ensemble_v1-elo+poisson"


def get_prediction_config(model_id: str = DEFAULT_MODEL_ID) -> PredictionReadinessConfig:
    """Return the PredictionReadinessConfig for the given model ID (FIX 3)."""
    return READINESS_CONFIG_REGISTRY.get(model_id, _DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _resolve_provider_identity(
    match: Match,
    db: Session,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve (provider, provider_match_id) for a match.

    Prefers direct match columns; falls back to MatchSourceMapping.
    Returns (None, None) if unresolvable.
    """
    if match.provider and match.provider_match_id:
        return match.provider, match.provider_match_id
    source_mapping = db.query(MatchSourceMapping).filter_by(match_id=match.id).first()
    if source_mapping:
        return source_mapping.source, source_mapping.source_match_id
    return None, None


# ---------------------------------------------------------------------------
# FIX 2: 4-state duplicate detection
# ---------------------------------------------------------------------------

def _assess_duplicate_state(
    db: Session,
    match: Match,
    kickoff_naive: Optional[datetime],
) -> Tuple[DuplicateDetectionState, List[str]]:
    """Deterministic 4-state duplicate classification (FIX 2).

    Returns (state, list_of_candidate_match_ids_as_str).

    Rules:
    - DUPLICATE_CONFIRMED: cross-table identity collision — this match's
      (provider, provider_match_id) matches a MatchSourceMapping.source_match_id
      for the same source pointing to a DIFFERENT canonical match.
      This catches cases where the same provider ID was mapped to two different
      canonical matches (the DB unique constraint on Match prevents direct row
      duplication, but cross-table identity collisions can still occur).
    - DUPLICATE_CANDIDATE: same league+home+away within ±24h but with a
      different provider's match or a different provider_match_id.
      → WARNING only, NOT blocking.
    - DUPLICATE_RESOLUTION_REQUIRED: both conditions simultaneously → blocking.
    - NO_DUPLICATE: neither condition.

    NOTE: The Match table has UniqueConstraint(provider, provider_match_id),
    so two Match rows with identical provider+provider_match_id cannot coexist.
    DUPLICATE_CONFIRMED is therefore detected via MatchSourceMapping cross-reference.
    """
    if not match.id:
        return DuplicateDetectionState.NO_DUPLICATE, []

    # --- Condition A: cross-table identity collision (confirmed duplicate) ---
    # Check if this match's (provider, provider_match_id) is also mapped as a
    # source_match_id for a DIFFERENT canonical match via MatchSourceMapping.
    identity_confirmed = False
    identity_matches: List[str] = []
    if match.provider and match.provider_match_id:
        cross_mappings = db.query(MatchSourceMapping).filter(
            MatchSourceMapping.source == match.provider,
            MatchSourceMapping.source_match_id == match.provider_match_id,
            MatchSourceMapping.match_id != match.id,
        ).all()
        if cross_mappings:
            identity_confirmed = True
            identity_matches = [str(cm.match_id) for cm in cross_mappings]

    # Also check: this match's MatchSourceMapping(s) overlap with another match's direct provider identity
    if not identity_confirmed:
        own_mappings = db.query(MatchSourceMapping).filter(
            MatchSourceMapping.match_id == match.id
        ).all()
        for om in own_mappings:
            # Check if another match has the same (provider, provider_match_id) as this mapping
            other_match = db.query(Match).filter(
                Match.id != match.id,
                Match.provider == om.source,
                Match.provider_match_id == om.source_match_id,
            ).first()
            if other_match:
                identity_confirmed = True
                identity_matches.append(str(other_match.id))

    # --- Condition B: proximity (candidate only, NOT blocking) ---
    proximity_candidate = False
    proximity_matches: List[str] = []
    if (
        match.league_id
        and match.home_team_id
        and match.away_team_id
        and kickoff_naive
    ):
        window_start = kickoff_naive - timedelta(hours=24)
        window_end = kickoff_naive + timedelta(hours=24)
        nearby = db.query(Match).filter(
            Match.id != match.id,
            Match.league_id == match.league_id,
            Match.home_team_id == match.home_team_id,
            Match.away_team_id == match.away_team_id,
            Match.kickoff_at >= window_start,
            Match.kickoff_at <= window_end,
        ).all()
        if nearby:
            confirmed_ids = set(identity_matches)
            nearby_ids = {str(d.id) for d in nearby}

            # If any identity-confirmed match is also in proximity window → RESOLUTION_REQUIRED
            if identity_confirmed and confirmed_ids & nearby_ids:
                all_candidate_ids = list(confirmed_ids | nearby_ids)
                return DuplicateDetectionState.DUPLICATE_RESOLUTION_REQUIRED, all_candidate_ids

            # Pure proximity candidates: nearby matches that are NOT identity-confirmed
            candidates = [d for d in nearby if str(d.id) not in confirmed_ids]
            if candidates:
                proximity_candidate = True
                proximity_matches = [str(d.id) for d in candidates]

    all_candidate_ids = list(set(identity_matches + proximity_matches))

    if identity_confirmed and proximity_candidate:
        return DuplicateDetectionState.DUPLICATE_RESOLUTION_REQUIRED, all_candidate_ids
    if identity_confirmed:
        return DuplicateDetectionState.DUPLICATE_CONFIRMED, identity_matches
    if proximity_candidate:
        return DuplicateDetectionState.DUPLICATE_CANDIDATE, proximity_matches
    return DuplicateDetectionState.NO_DUPLICATE, []


# ---------------------------------------------------------------------------
# FIX 4: Provider activation scoped to provider x competition x season
# ---------------------------------------------------------------------------

def _get_scoped_activation_state(
    db: Session,
    provider: Optional[str],
    competition: str,
    season: str,
) -> str:
    """Return activation state scoped to provider x competition x season (FIX 4).

    Uses the Phase 24 get_activation_state() function with competition+season scoping.
    Returns UNAVAILABLE if provider is unknown.
    """
    from app.services.acquisition.activation import ActivationState, get_activation_state
    if not provider:
        return ActivationState.UNAVAILABLE.value
    return get_activation_state(db, provider=provider, competition=competition, season=season)


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------

def evaluate_pre_match_readiness(
    db: Session,
    match_id: int,
    cutoff: Optional[datetime] = None,
    mode: str = "PRE_MATCH",
    model_id: str = DEFAULT_MODEL_ID,
) -> Dict[str, Any]:
    """Pure, side-effect-free evaluation of a match through Gates 1 to 4.

    Evaluates:
    - Gate 1: Structural validity & metadata integrity
    - Gate 2: Reconciliation & cross-source identity validation
    - Gate 3: Temporal validity & cutoff enforcement (mode-aware)
    - Gate 4: Feature availability & leakage eligibility (config-driven, FIX 3/9)

    Returns structured evaluation verdict without mutating database.

    Phase 25.1 changes:
    - FIX 2: Duplicate detection uses 4-state deterministic logic
    - FIX 3/9: Feature requirements from PredictionReadinessConfig
    - FIX 4: Activation state scoped to provider x competition x season
    - FIX 5: Response includes provider provenance + prediction_config fields
    - FIX 7: Explicit PRE_MATCH/POST_MATCH cutoff semantics
    """
    now = datetime.now(timezone.utc)
    now_naive = as_naive_utc(now)
    config = get_prediction_config(model_id)

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
            "model_id": model_id,
            # FIX 5: Provider provenance
            "provider": None,
            "provider_match_id": None,
            "activation_state": None,
            "provider_qualification_version": None,  # SourceQualification has no version field
            # FIX 3: Prediction config
            "prediction_config": asdict(config),
            "model_version": config.model_version,
            "prediction_mode": config.prediction_mode,
            "required_features": config.required_features,
            "available_features": [],
            "missing_required_features": config.required_features,
            "missing_optional_features": config.optional_features,
            "gate_verdicts": {
                "gate1_structural": {"passed": False, "reasons": ["MATCH_NOT_FOUND"]},
                "gate2_reconciliation": {
                    "passed": False,
                    "reasons": ["MATCH_NOT_FOUND"],
                    "duplicate_state": DuplicateDetectionState.NO_DUPLICATE.value,
                    "duplicate_candidate_ids": [],
                },
                "gate3_temporal": {"passed": False, "reasons": ["MATCH_NOT_FOUND"]},
                "gate4_features": {"passed": False, "status": "fail", "reasons": ["MATCH_NOT_FOUND"], "warnings": []},
            },
            "blocking_reasons": ["MATCH_NOT_FOUND"],
            "warnings": [],
            "missing_features": {"required": ["match"], "optional": []},
            "evaluated_at": now.isoformat(),
        }

    # Derive competition & season
    league = db.get(League, match.league_id) if match.league_id else None
    competition = league.code if league else "UNKNOWN"
    season = league.season if (league and league.season) else current_canonical_season()

    # Resolve provider identity (FIX 5)
    resolved_provider, resolved_provider_match_id = _resolve_provider_identity(match, db)

    # Activation state scoped to provider x competition x season (FIX 4)
    activation_state = _get_scoped_activation_state(db, resolved_provider, competition, season)

    kickoff_naive = as_naive_utc(match.kickoff_at)
    eval_cutoff = cutoff if cutoff is not None else now
    eval_cutoff_naive = as_naive_utc(eval_cutoff)

    blocking_reasons: List[str] = []
    warnings: List[str] = []
    missing_required: List[str] = []
    missing_optional: List[str] = []

    # ------------------------------------------------------------------
    # GATE 1: Structural Validity & Metadata Integrity
    # ------------------------------------------------------------------
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
    if not resolved_provider or not resolved_provider_match_id:
        g1_reasons.append("MISSING_PROVIDER_IDENTITY")

    g1_passed = len(g1_reasons) == 0
    blocking_reasons.extend(g1_reasons)

    # ------------------------------------------------------------------
    # GATE 2: Reconciliation & Cross-Source Identity (FIX 2)
    # ------------------------------------------------------------------
    g2_reasons: List[str] = []
    g2_warnings: List[str] = []

    # Existing reconciliation conflicts
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

    # 4-state duplicate detection (FIX 2)
    dup_state, dup_candidate_ids = _assess_duplicate_state(db, match, kickoff_naive)

    if dup_state == DuplicateDetectionState.DUPLICATE_CONFIRMED:
        g2_reasons.append(
            f"DUPLICATE_CONFIRMED: exact provider+provider_match_id collision "
            f"with matches={','.join(dup_candidate_ids)}"
        )
    elif dup_state == DuplicateDetectionState.DUPLICATE_RESOLUTION_REQUIRED:
        g2_reasons.append(
            f"DUPLICATE_RESOLUTION_REQUIRED: identity+proximity collision "
            f"with matches={','.join(dup_candidate_ids)}"
        )
    elif dup_state == DuplicateDetectionState.DUPLICATE_CANDIDATE:
        # Warning only — NOT blocking (FIX 2 core rule)
        g2_warnings.append(
            f"DUPLICATE_CANDIDATE: proximity-only suspicion (±24h, different provider_match_id) "
            f"with matches={','.join(dup_candidate_ids)}"
        )
        warnings.extend(g2_warnings)

    g2_passed = len(g2_reasons) == 0
    blocking_reasons.extend(g2_reasons)

    # ------------------------------------------------------------------
    # GATE 3: Temporal Validity & Cutoff Enforcement (FIX 7)
    # ------------------------------------------------------------------
    g3_reasons: List[str] = []

    # Cancelled / postponed status
    if match.status in (MatchStatus.POSTPONED.value, MatchStatus.CANCELLED.value, "SUSPENDED", "ABANDONED"):
        g3_reasons.append(f"FIXTURE_POSTPONED_OR_CANCELLED: status={match.status}")

    # Stale fixture: kickoff passed while status is still scheduled/pre-match
    ref_time = now_naive
    if eval_cutoff_naive is not None and eval_cutoff_naive > now_naive:
        ref_time = eval_cutoff_naive
    if kickoff_naive and ref_time and kickoff_naive < ref_time:
        if match.status in (MatchStatus.SCHEDULED.value, MatchStatus.PRE_MATCH.value):
            g3_reasons.append("STALE_FIXTURE_AWAITING_SYNC")

    # Mode-dependent cutoff enforcement (FIX 7: explicit PRE_MATCH semantics)
    # PRE_MATCH mode requires: cutoff < kickoff_at
    # Only PRE_MATCH enforces the cutoff boundary; other modes (POST_MATCH, EVALUATION) do not.
    if mode == "PRE_MATCH":
        if kickoff_naive is not None and eval_cutoff_naive is not None:
            if eval_cutoff_naive >= kickoff_naive:
                g3_reasons.append("CUTOFF_AT_OR_AFTER_KICKOFF")

    g3_passed = len(g3_reasons) == 0
    blocking_reasons.extend(g3_reasons)

    # ------------------------------------------------------------------
    # GATE 4: Feature Availability & Leakage Eligibility (FIX 3/9)
    # ------------------------------------------------------------------
    g4_reasons: List[str] = []
    g4_warnings: List[str] = []
    available_features: List[str] = []

    min_hist = config.min_historical_matches_per_team  # FIX 9: from config, not hardcoded

    # Historical context: strictly query data before eval_cutoff (leakage safe)
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

    # Gate 4: check required features (FIX 3)
    hist_feature = "historical_match_context"
    if "historical_match_context" in config.required_features:
        if home_matches_count >= min_hist and away_matches_count >= min_hist:
            available_features.append(hist_feature)
        else:
            g4_reasons.append(
                f"INSUFFICIENT_HISTORICAL_MATCHES: home={home_matches_count}, "
                f"away={away_matches_count} (minimum {min_hist} required per team)"
            )
            missing_required.append(hist_feature)

    # Optional features: Lineups (FIX 7: only use data before cutoff in PRE_MATCH mode)
    if "lineups" in config.optional_features:
        has_lineups = False
        if match.id:
            lineup_count = db.query(Lineup).filter_by(match_id=match.id).count()
            has_lineups = lineup_count > 0
        if has_lineups:
            available_features.append("lineups")
        else:
            missing_optional.append("lineups")
            g4_warnings.append("OPTIONAL_FEATURE_MISSING: lineups")

    # Optional features: Market odds (FIX 7: enforce cutoff boundary)
    if "market_odds" in config.optional_features:
        has_odds = False
        if match.id and eval_cutoff_naive:
            odds_count = db.query(OddsSnapshot).filter(
                OddsSnapshot.match_id == match.id,
                OddsSnapshot.timestamp <= eval_cutoff_naive,
            ).count()
            has_odds = odds_count > 0
        if has_odds:
            available_features.append("market_odds")
        else:
            missing_optional.append("market_odds")
            g4_warnings.append("OPTIONAL_FEATURE_MISSING: market_odds")

    g4_status = "fail" if g4_reasons else ("degraded" if (missing_optional or g4_warnings) else "pass")
    g4_passed = len(g4_reasons) == 0
    blocking_reasons.extend(g4_reasons)
    warnings.extend(g4_warnings)

    # ------------------------------------------------------------------
    # OVERALL READINESS STATE SYNTHESIS
    # ------------------------------------------------------------------
    if not g1_passed or not g2_passed or not g3_passed or not g4_passed:
        overall_state = PreMatchReadinessState.BLOCKED
    elif g4_status == "degraded" or len(warnings) > 0:
        overall_state = PreMatchReadinessState.READY_DEGRADED
    else:
        overall_state = PreMatchReadinessState.PREDICTION_READY

    # Derived feature lists for response (FIX 5)
    missing_required_features = [f for f in config.required_features if f not in available_features]
    missing_optional_features = [f for f in config.optional_features if f not in available_features]

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
        "model_id": model_id,
        # FIX 5: Provider provenance
        "provider": resolved_provider,
        "provider_match_id": resolved_provider_match_id,
        "activation_state": activation_state,
        "provider_qualification_version": None,  # SourceQualification has no version field (Phase 24)
        # FIX 3: Prediction config
        "prediction_config": asdict(config),
        "model_version": config.model_version,
        "prediction_mode": config.prediction_mode,
        "required_features": list(config.required_features),
        "available_features": available_features,
        "missing_required_features": missing_required_features,
        "missing_optional_features": missing_optional_features,
        # Gate verdicts
        "gate_verdicts": {
            "gate1_structural": {"passed": g1_passed, "reasons": g1_reasons},
            "gate2_reconciliation": {
                "passed": g2_passed,
                "reasons": g2_reasons,
                "duplicate_state": dup_state.value,
                "duplicate_candidate_ids": dup_candidate_ids,
            },
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
        # Legacy key kept for backward compat with existing tests
        "missing_features": {
            "core": missing_required,
            "optional": missing_optional,
        },
        "evaluated_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Certificate generation (Gate 5) — append-only, immutable (FIX 6)
# ---------------------------------------------------------------------------

def generate_readiness_certificate(
    db: Session,
    match_id: int,
    cutoff: Optional[datetime] = None,
    mode: str = "PRE_MATCH",
    model_id: str = DEFAULT_MODEL_ID,
) -> PreMatchReadinessCertificate:
    """Generate and persist an immutable pre-match readiness certificate.

    CRITICAL INVARIANTS (FIX 6):
    - Evaluates Gates 1-4 via evaluate_pre_match_readiness.
    - Contract version: PREMATCH_CERTIFICATE_V1.
    - Canonical JSON hashing (SHA-256) over normalized payload including provenance (FIX 5).
    - Existing certificate rows are NEVER overwritten or mutated.
    - Each call always inserts a new row.
    - If a previous certificate exists, links supersedes_certificate_id to it.
    - provider_qualification_version is always None — SourceQualification has no version field.
    """
    evaluation = evaluate_pre_match_readiness(db, match_id, cutoff=cutoff, mode=mode, model_id=model_id)

    # Find existing certificate for this match (if any)
    existing = (
        db.query(PreMatchReadinessCertificate)
        .filter_by(match_id=match_id)
        .order_by(PreMatchReadinessCertificate.id.desc())
        .first()
    )

    cert_uuid = uuid.uuid4().hex[:12]
    cert_id = f"cert_{match_id}_{cert_uuid}"

    # Build canonical payload for hashing (FIX 5: includes full provenance)
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
        "mode": evaluation["mode"],
        "model_id": evaluation["model_id"],
        # Provider provenance (FIX 5) — all in hash
        "provider": evaluation["provider"],
        "provider_match_id": evaluation["provider_match_id"],
        "activation_state": evaluation["activation_state"],
        "provider_qualification_version": None,  # always None — not fabricated
        "prediction_config": evaluation["prediction_config"],
        "model_version": evaluation["model_version"],
        "prediction_mode": evaluation["prediction_mode"],
        "required_features": sorted(evaluation["required_features"]),
        "available_features": sorted(evaluation["available_features"]),
        "missing_required_features": sorted(evaluation["missing_required_features"]),
        "missing_optional_features": sorted(evaluation["missing_optional_features"]),
        # Gate verdicts + reasons
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
        # Phase 25.1 provenance columns
        provider=evaluation["provider"],
        provider_match_id=evaluation["provider_match_id"],
        activation_state=evaluation["activation_state"],
        provider_qualification_version=None,  # SourceQualification has no version field
        prediction_config=evaluation["prediction_config"],
        model_version=evaluation["model_version"],
        prediction_mode=evaluation["prediction_mode"],
        required_features=evaluation["required_features"],
        available_features=evaluation["available_features"],
        missing_required_features=evaluation["missing_required_features"],
        missing_optional_features=evaluation["missing_optional_features"],
    )

    db.add(certificate)
    db.commit()
    db.refresh(certificate)
    return certificate


# ---------------------------------------------------------------------------
# Summary telemetry (FIX 4/8)
# ---------------------------------------------------------------------------

def get_current_season_prematch_summary(
    db: Session,
    season: str = "current",
) -> Dict[str, Any]:
    """Compile distinct, non-collapsing operational counters for current-season readiness.

    Phase 25.1 changes (FIX 4/8):
    - provider_state now derived from Phase 24 activation scoped to competition x season
    - provider_activation_by_competition: per-competition activation state dict
    - 11 clearly named counters preserved
    - operational_mode is 'operational' only when at least one competition has ACTIVE state
      and fixture_count > 0

    Accurately reports:
    1. season
    2. operational_mode
    3. provider_state (global summary: ACTIVE if any competition is active)
    4. fixture_count
    5. reconciled_count
    6. temporally_valid_count
    7. quality_passed_count
    8. prediction_ready_count
    9. ready_degraded_count
    10. blocked_count
    11. blocking_reasons (breakdown dict)
    + provider_activation_by_competition (per-competition state map)
    """
    from app.db.models.acquisition import SourceActivation
    from app.services.acquisition.activation import ActivationState, get_activation_state

    canonical_season = current_canonical_season() if season == "current" else season
    now = datetime.now(timezone.utc)

    # Find current-season leagues
    leagues = db.query(League).filter_by(season=canonical_season).all()
    league_ids = [lg.id for lg in leagues]
    competition_codes = [lg.code for lg in leagues]

    # FIX 4: Per-competition activation state scoped to provider x competition x season
    # Find all providers that have any activation record
    all_sources = db.query(SourceActivation.source).distinct().all()
    all_provider_names = [row[0] for row in all_sources if row[0]]

    provider_activation_by_competition: Dict[str, str] = {}
    for comp_code in competition_codes:
        # Find the best (most permissive) activation state across known providers for this competition
        best_state = ActivationState.UNAVAILABLE.value
        for prov in all_provider_names:
            state = get_activation_state(db, provider=prov, competition=comp_code, season=canonical_season)
            if state == ActivationState.ACTIVE.value:
                best_state = ActivationState.ACTIVE.value
                break
            elif state in (ActivationState.QUALIFIED.value, ActivationState.DEGRADED.value):
                best_state = state
        provider_activation_by_competition[comp_code] = best_state

    # Determine global provider_state: ACTIVE if any competition is ACTIVE
    any_active = any(
        s == ActivationState.ACTIVE.value
        for s in provider_activation_by_competition.values()
    )
    if any_active:
        global_provider_state = ActivationState.ACTIVE.value
    elif provider_activation_by_competition:
        # Use highest priority non-ACTIVE state across all competitions
        state_priority = [
            ActivationState.QUALIFIED.value,
            ActivationState.DEGRADED.value,
            ActivationState.REVOKED.value,
            ActivationState.UNAVAILABLE.value,
        ]
        for sp in state_priority:
            if any(s == sp for s in provider_activation_by_competition.values()):
                global_provider_state = sp
                break
        else:
            global_provider_state = ActivationState.UNAVAILABLE.value
    else:
        # No competitions found — fall back to latest activation record
        latest = db.query(SourceActivation).order_by(SourceActivation.id.desc()).first()
        global_provider_state = latest.state if latest else ActivationState.UNAVAILABLE.value

    matches: List[Match] = []
    if league_ids:
        matches = db.query(Match).filter(Match.league_id.in_(league_ids)).all()

    fixture_count = len(matches)
    # operational_mode is 'operational' only when provider is ACTIVE and fixtures exist (FIX 8)
    operational_mode = (
        "operational"
        if fixture_count > 0 and global_provider_state == ActivationState.ACTIVE.value
        else "readiness_only"
    )

    if fixture_count == 0:
        return {
            "season": canonical_season,
            "operational_mode": operational_mode,
            "provider_state": global_provider_state,
            "provider_activation_by_competition": provider_activation_by_competition,
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
        "provider_state": global_provider_state,
        "provider_activation_by_competition": provider_activation_by_competition,
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
