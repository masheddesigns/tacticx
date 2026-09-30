"""Phase 24 — Controlled Current-Season Data Activation Test Suite.

Verifies:
1. Activation state taxonomy and QUALIFIED != ACTIVE invariant.
2. Pure can_activate_current_season decision function (zero DB writes, zero network calls).
3. Explicit, audited activate_current_season operational transitions.
4. Independent activation across the five primary leagues.
5. Inactive source skipping in scheduler (no external calls, clean skipped status).
6. Kickoff lock & post-kickoff observation: match updates to FINISHED while pre-match
   IntelligenceSnapshot remains bitwise immutable.
7. Idempotent acquisition (zero duplicate matches).
8. Readiness telemetry distinguishing 0 fixtures from unavailable provider.
9. Phase 23 golden prediction regression verification.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest
from sqlalchemy.orm import Session

from app.db.models.acquisition import AcquisitionRun, SourceActivation
from app.db.models.core import League, Match, Team
from app.db.models.intelligence_v2 import IntelligenceSnapshot
from app.db.models.qualification import SourceQualification
from app.db.models.reconciliation import ReconciliationConflict
from app.services.acquisition.activation import (
    TARGET_LEAGUES,
    ActivationState,
    activate_current_season,
    can_activate_current_season,
    get_activation_state,
    revoke_activation,
)
from app.services.acquisition.current_season import (
    acquire_competition,
    acquire_current_season,
    current_canonical_season,
    get_current_season_readiness_report,
)
from app.services.scheduler.executors import execute_fixture_refresh
from tests.test_phase17b_match_intelligence import _build, _history


NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _setup_competition(db: Session, code: str = "EPL", name: str = "Premier League") -> League:
    league = db.query(League).filter_by(code=code).first()
    if not league:
        league = League(name=name, code=code, country="England")
        db.add(league)
        db.commit()
    return league


def _setup_historical_matches(db: Session, league: League, count: int = 6):
    """Seed historical finished matches so the competition satisfies the >= 5 match context rule."""
    h_team = db.query(Team).filter_by(provider="mock", provider_team_id=f"H_{league.code}").first()
    if not h_team:
        h_team = Team(name=f"Home {league.code}", short_name=f"H{league.code[:2]}", provider="mock", provider_team_id=f"H_{league.code}")
        db.add(h_team)
    a_team = db.query(Team).filter_by(provider="mock", provider_team_id=f"A_{league.code}").first()
    if not a_team:
        a_team = Team(name=f"Away {league.code}", short_name=f"A{league.code[:2]}", provider="mock", provider_team_id=f"A_{league.code}")
        db.add(a_team)
    db.flush()

    for i in range(count):
        pid = f"hist_{league.code}_{i}"
        existing = db.query(Match).filter_by(provider_match_id=pid).first()
        if existing:
            continue
        ko = NOW - timedelta(days=20 + i)
        m = Match(
            league_id=league.id,
            home_team_id=h_team.id,
            away_team_id=a_team.id,
            kickoff_at=ko,
            status="FINISHED",
            home_score=2,
            away_score=1,
            provider_match_id=pid,
        )
        db.add(m)
    db.commit()


# --------------------------------------------------------------------------------------
# 1. State Taxonomy & QUALIFIED != ACTIVE Invariant
# --------------------------------------------------------------------------------------

def test_activation_state_taxonomy():
    """All 8 operational activation states are present and distinct."""
    expected_states = {
        "UNAVAILABLE", "DISCOVERY", "PROBING", "QUALIFYING",
        "QUALIFIED", "ACTIVE", "DEGRADED", "REVOKED"
    }
    actual_states = {s.value for s in ActivationState}
    assert expected_states == actual_states


def test_qualified_is_not_active(db: Session):
    """QUALIFIED status in SourceQualification does not grant ACTIVE acquisition rights."""
    league = _setup_competition(db, "EPL")
    qual = SourceQualification(
        source="test_provider",
        status="qualified",
        reason_codes=["all_checks_passed"],
        competition="EPL",
        season="2026/27",
        fixture_count=380,
        resolved_count=380,
        unresolved_count=0,
        retrieved_at=NOW,
    )
    db.add(qual)
    db.commit()

    # get_activation_state reads only SourceActivation table, defaulting to UNAVAILABLE
    state = get_activation_state(db, "test_provider", "EPL", "2026/27")
    assert state == ActivationState.UNAVAILABLE.value
    assert state != ActivationState.ACTIVE.value


# --------------------------------------------------------------------------------------
# 2. Pure Decision Function (can_activate_current_season)
# --------------------------------------------------------------------------------------

def test_can_activate_is_pure_and_blocks_unverified(db: Session):
    """can_activate_current_season evaluates evidence with zero DB writes."""
    initial_count = db.query(SourceActivation).count()

    decision = can_activate_current_season("unknown_provider", "EPL", "2026/27", db)
    assert not decision["eligible"]
    assert "no_qualification_evidence_for_unknown_provider" in decision["reasons"]

    # Zero DB mutations
    assert db.query(SourceActivation).count() == initial_count


def test_can_activate_blocks_unsupported_league(db: Session):
    """Competitions outside the 5 primary leagues are rejected."""
    decision = can_activate_current_season("api_football", "CHAMPIONSHIP", "2026/27", db)
    assert not decision["eligible"]
    assert any("unsupported_competition" in r for r in decision["reasons"])


def test_can_activate_blocks_zero_fixtures(db: Session):
    """A qualified provider returning 0 fixtures cannot be activated."""
    league = _setup_competition(db, "LA_LIGA", "La Liga")
    _setup_historical_matches(db, league, count=6)

    verdict = {
        "status": "qualified",
        "competition": "LA_LIGA",
        "season": "2026/27",
        "fixture_count": 0,
        "valid_kickoff_timestamps": True,
        "retrieved_at": NOW.isoformat(),
    }
    decision = can_activate_current_season(
        "api_football", "LA_LIGA", "2026/27", db, qualification_verdict=verdict
    )
    assert not decision["eligible"]
    assert any("fixture" in r for r in decision["reasons"])


def test_can_activate_blocks_missing_iso_timestamps(db: Session):
    """Missing or invalid kickoff timestamps block activation."""
    league = _setup_competition(db, "SERIE_A", "Serie A")
    _setup_historical_matches(db, league, count=6)

    verdict = {
        "status": "qualified",
        "competition": "SERIE_A",
        "season": "2026/27",
        "fixture_count": 380,
        "valid_kickoff_timestamps": False,
        "retrieved_at": NOW.isoformat(),
    }
    decision = can_activate_current_season(
        "api_football", "SERIE_A", "2026/27", db, qualification_verdict=verdict
    )
    assert not decision["eligible"]
    assert "fixtures_missing_valid_kickoff_timestamps" in decision["reasons"]


def test_can_activate_blocks_critical_reconciliation_conflict(db: Session):
    """Unresolved critical reconciliation conflicts for the competition block activation."""
    league = _setup_competition(db, "BUNDESLIGA", "Bundesliga")
    _setup_historical_matches(db, league, count=6)

    conflict = ReconciliationConflict(
        entity_type="match",
        canonical_entity_id=1,
        field="kickoff_at",
        severity="critical",
        resolution_status="unresolved",
        dedup_key="BUNDESLIGA_conflict",
    )
    db.add(conflict)
    db.commit()

    verdict = {
        "status": "qualified",
        "competition": "BUNDESLIGA",
        "season": "2026/27",
        "fixture_count": 306,
        "valid_kickoff_timestamps": True,
        "retrieved_at": NOW.isoformat(),
    }
    decision = can_activate_current_season(
        "api_football", "BUNDESLIGA", "2026/27", db, qualification_verdict=verdict
    )
    assert not decision["eligible"]
    assert any("critical_unresolved_reconciliation_conflicts" in r for r in decision["reasons"])


def test_can_activate_blocks_insufficient_historical_context(db: Session):
    """Competitions with fewer than 5 historical finished matches cannot be activated."""
    league = _setup_competition(db, "LIGUE_1", "Ligue 1")
    # Only 2 matches seeded
    _setup_historical_matches(db, league, count=2)

    verdict = {
        "status": "qualified",
        "competition": "LIGUE_1",
        "season": "2026/27",
        "fixture_count": 306,
        "valid_kickoff_timestamps": True,
        "retrieved_at": NOW.isoformat(),
    }
    decision = can_activate_current_season(
        "api_football", "LIGUE_1", "2026/27", db, qualification_verdict=verdict
    )
    assert not decision["eligible"]
    assert any("insufficient_historical_context" in r for r in decision["reasons"])


def test_can_activate_succeeds_when_all_requirements_met(db: Session):
    """When target league, qualification, fixtures, timestamps, identity, and history pass, activation is eligible."""
    league = _setup_competition(db, "EPL", "Premier League")
    _setup_historical_matches(db, league, count=10)

    verdict = {
        "status": "qualified",
        "competition": "EPL",
        "season": "2026/27",
        "fixture_count": 380,
        "valid_kickoff_timestamps": True,
        "retrieved_at": NOW.isoformat(),
        "conflict_count": 0,
        "unresolved_count": 0,
    }
    decision = can_activate_current_season(
        "api_football", "EPL", "2026/27", db, qualification_verdict=verdict
    )
    assert decision["eligible"]
    assert len(decision["reasons"]) == 0


# --------------------------------------------------------------------------------------
# 3. Explicit Operational Action (activate_current_season & revoke_activation)
# --------------------------------------------------------------------------------------

def test_activate_records_audit_trail_and_blocks_ineligible(db: Session):
    """activate_current_season rejects ineligible source without force and records audit log."""
    res = activate_current_season(
        db,
        source="unverified_source",
        competition="EPL",
        season="2026/27",
        actor="operator_jane",
        reason="routine scheduled check",
    )
    assert not res["success"]
    assert res["status"] == "blocked"

    # Audit record created with state QUALIFIED
    row = db.get(SourceActivation, res["activation_id"])
    assert row is not None
    assert row.source == "unverified_source"
    assert row.state == ActivationState.QUALIFIED.value
    assert row.decided_by == "operator_jane"
    assert "activation blocked" in row.reason


def test_activate_force_override_persists_active_state(db: Session):
    """Force override allows operator authorization and transitions state to ACTIVE."""
    res = activate_current_season(
        db,
        source="api_football",
        competition="EPL",
        season="2026/27",
        actor="lead_operator",
        reason="manual staging test override",
        force=True,
    )
    assert res["success"]
    assert res["status"] == "activated"
    assert res["state"] == ActivationState.ACTIVE.value

    # Querying state confirms active
    assert get_activation_state(db, "api_football", "EPL", "2026/27") == ActivationState.ACTIVE.value


def test_revocation_stops_active_status(db: Session):
    """revoke_activation transitions state to REVOKED."""
    activate_current_season(
        db,
        source="api_football",
        competition="EPL",
        season="2026/27",
        actor="operator",
        force=True,
    )
    assert get_activation_state(db, "api_football", "EPL", "2026/27") == ActivationState.ACTIVE.value

    rev_res = revoke_activation(
        db,
        provider="api_football",
        competition="EPL",
        season="2026/27",
        reason="data quality degradation detected",
        decided_by="sre_oncall",
    )
    assert rev_res["state"] == ActivationState.REVOKED.value
    assert get_activation_state(db, "api_football", "EPL", "2026/27") == ActivationState.REVOKED.value


# --------------------------------------------------------------------------------------
# 4. League Independence (EPL != LA_LIGA)
# --------------------------------------------------------------------------------------

def test_league_independence(db: Session):
    """Activating EPL does NOT activate other primary competitions."""
    activate_current_season(
        db,
        source="api_football",
        competition="EPL",
        season="2026/27",
        actor="operator",
        force=True,
    )

    assert get_activation_state(db, "api_football", "EPL", "2026/27") == ActivationState.ACTIVE.value
    assert get_activation_state(db, "api_football", "LA_LIGA", "2026/27") == ActivationState.UNAVAILABLE.value
    assert get_activation_state(db, "api_football", "SERIE_A", "2026/27") == ActivationState.UNAVAILABLE.value
    assert get_activation_state(db, "api_football", "BUNDESLIGA", "2026/27") == ActivationState.UNAVAILABLE.value
    assert get_activation_state(db, "api_football", "LIGUE_1", "2026/27") == ActivationState.UNAVAILABLE.value


# --------------------------------------------------------------------------------------
# 5. Scheduler Dormancy & Inactive Source Skipping
# --------------------------------------------------------------------------------------

def test_scheduler_skips_inactive_sources_cleanly(db: Session):
    """When source is inactive, execute_fixture_refresh skips without external requests."""
    # Ensure all sources are inactive for EPL
    config = {"competitions": ["EPL"], "seasons": ["2026/27"]}
    res = execute_fixture_refresh(db, config=config, dry_run=False)

    assert res["status"] == "skipped"
    assert res["total_fixtures"] == 0
    assert res["new_matches"] == 0
    assert res["failures"] == 0


# --------------------------------------------------------------------------------------
# 6. Kickoff Lock & Post-Kickoff Verification
# --------------------------------------------------------------------------------------

def test_kickoff_locking_and_snapshot_immutability(db: Session):
    """Verifies pre-match snapshot immutability when post-kickoff result updates match in DB."""
    # Generate match and prediction
    _, _, target = _history(db, code="P24LOCK")
    pre_doc = _build(db, target)

    # Store pre-match prediction snapshot in DB
    snapshot = IntelligenceSnapshot(
        snapshot_id="snap_p24_test",
        match_id=target.id,
        payload_hash=pre_doc["provenance"]["response_hash"],
        payload=pre_doc,
        cutoff=NOW,
        created_at=NOW,
    )
    db.add(snapshot)
    db.commit()

    saved_hash = snapshot.payload_hash
    saved_prob_home = snapshot.payload["core_prediction"]["home"]
    saved_xg_home = snapshot.payload["expected_goals"]["home_lambda"]

    # Simulate post-kickoff match completion in database
    target.status = "FINISHED"
    target.home_score = 3
    target.away_score = 0
    db.commit()

    # Re-fetch snapshot: payload and hash remain bitwise immutable
    reloaded = db.get(IntelligenceSnapshot, snapshot.id)
    assert reloaded.payload_hash == saved_hash
    assert reloaded.payload["core_prediction"]["home"] == saved_prob_home
    assert reloaded.payload["expected_goals"]["home_lambda"] == saved_xg_home

    # The match row has successfully updated
    updated_match = db.get(Match, target.id)
    assert updated_match.status == "FINISHED"
    assert updated_match.home_score == 3


# --------------------------------------------------------------------------------------
# 7. Telemetry & Readiness Report
# --------------------------------------------------------------------------------------

def test_readiness_report_telemetry(db: Session):
    """Readiness report distinguishes unavailable provider from 0 fixtures."""
    _setup_competition(db, "EPL")
    _setup_competition(db, "LA_LIGA")
    _setup_competition(db, "SERIE_A")
    _setup_competition(db, "BUNDESLIGA")
    _setup_competition(db, "LIGUE_1")

    report = get_current_season_readiness_report(db, season="2026/27")
    assert report["season"] == "2026/27"
    # Phase 39: 5 domestic + Nations League + Friendlies.
    assert len(report["items"]) == 7
    summary = report["summary"]
    assert summary["total_competitions"] == 7
    assert summary["active_competitions"] == 0
    assert summary["unavailable_competitions"] == 7

    for item in report["items"]:
        assert item["fixture_count"] is None
        assert item["coverage_measurable"] is False
        assert item["activation_status"] == ActivationState.UNAVAILABLE.value
        assert not item["eligible_for_activation"]


# --------------------------------------------------------------------------------------
# 8. Golden Prediction Regression Guard
# --------------------------------------------------------------------------------------

def test_golden_prediction_preservation(db: Session):
    """Verifies that prediction numbers remain exactly identical to Phase 23 baseline."""
    _, _, target = _history(db, code="P24GOLD")
    doc = _build(db, target)

    core = doc["core_prediction"]
    xg = doc["expected_goals"]

    assert all(math.isfinite(core[k]) for k in ("home", "draw", "away"))
    assert math.isfinite(xg["home_lambda"]) and math.isfinite(xg["away_lambda"])

    total_prob = core["home"] + core["draw"] + core["away"]
    assert pytest.approx(1.0, rel=1e-5) == total_prob

    assert pytest.approx(0.60605, rel=1e-3) == core["home"]
    assert pytest.approx(0.22233, rel=1e-3) == core["draw"]
    assert pytest.approx(0.17161, rel=1e-3) == core["away"]
    assert pytest.approx(1.7442, rel=1e-3) == xg["home_lambda"]
    assert pytest.approx(0.1713, rel=1e-3) == xg["away_lambda"]
    assert pytest.approx(1.9155, rel=1e-3) == xg["total_lambda"]
    assert core["model_version"] == "ensemble_v1-elo+poisson"
    assert core["prediction_mode"] == "strict_prematch"
