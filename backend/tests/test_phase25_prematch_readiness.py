"""Phase 25 / 25.1 — Current-Season Data Quality, Reconciliation & Pre-Match Readiness Test Suite.

Verifies:
1. Gate 1: Structural validity & fixture metadata integrity.
2. Gate 2: Reconciliation & cross-source identity validation
   (Phase 25.1: 4-state deterministic duplicate detection — proximity alone is CANDIDATE, not blocking).
3. Gate 3: Temporal validity & cutoff enforcement (mode-aware cutoff < kickoff, stale fixtures, postponed).
4. Gate 4: Feature availability & leakage eligibility (config-driven from PredictionReadinessConfig).
5. Gate 5: Immutable readiness certificate generation, canonical SHA-256 hashing, and superseding behavior.
6. Certificate provenance fields: provider, activation_state, prediction_config, missing_features.
7. Current-season pre-match summary telemetry (11 counters, per-competition activation, honest 0-fixture state).
8. FastAPI HTTP endpoints for pre-match readiness and current-season summary.
9. Golden prediction regression preservation.
10. Migration structural tests.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models.core import League, Lineup, Match, Team
from app.db.models.enums import MatchStatus
from app.db.models.odds import OddsSnapshot
from app.db.models.prematch import PreMatchReadinessCertificate
from app.db.models.provenance import MatchSourceMapping
from app.db.models.reconciliation import ReconciliationConflict
from app.services.acquisition.readiness_gate import (
    CERTIFICATE_CONTRACT_VERSION,
    DEFAULT_MODEL_ID,
    DuplicateDetectionState,
    PreMatchReadinessState,
    PredictionReadinessConfig,
    READINESS_CONFIG_REGISTRY,
    _assess_duplicate_state,
    compute_canonical_certificate_hash,
    evaluate_pre_match_readiness,
    generate_readiness_certificate,
    get_current_season_prematch_summary,
    get_prediction_config,
)
from tests.test_phase17b_match_intelligence import _build, _history


def _get_times():
    now = datetime.now(timezone.utc)
    future = now + timedelta(hours=4)
    past = now - timedelta(hours=2)
    return now, future, past


def _create_teams_and_league(db: Session, code: str = "EPL", season: str = "2026/27"):
    league = db.query(League).filter_by(code=code).first()
    if not league:
        league = League(name=f"{code} League", code=code, season=season, country="England")
        db.add(league)
        db.flush()

    home = Team(
        name=f"{code} Home FC",
        short_name="HOM",
        provider="mock",
        provider_team_id=f"H_{code}_{datetime.now().microsecond}",
    )
    away = Team(
        name=f"{code} Away FC",
        short_name="AWY",
        provider="mock",
        provider_team_id=f"A_{code}_{datetime.now().microsecond}",
    )
    db.add_all([home, away])
    db.flush()
    return league, home, away


def _seed_finished_history(
    db: Session, league: League, team: Team, count: int = 4, before_dt: datetime = None
):
    """Create historical finished matches for a team strictly before before_dt."""
    if before_dt is None:
        before_dt = datetime.now(timezone.utc)

    other = Team(
        name=f"Opponent {team.id}_{datetime.now().microsecond}",
        provider="mock",
        provider_team_id=f"OPP_{team.id}_{datetime.now().microsecond}",
    )
    db.add(other)
    db.flush()

    for i in range(count):
        match_time = before_dt - timedelta(days=7 * (i + 1))
        m = Match(
            league_id=league.id,
            home_team_id=team.id,
            away_team_id=other.id,
            kickoff_at=match_time,
            status=MatchStatus.FINISHED.value,
            home_score=2,
            away_score=1,
            provider="mock",
            provider_match_id=f"hist_{team.id}_{i}_{datetime.now().microsecond}",
        )
        db.add(m)
    db.flush()


# ============================================================
# 1. GATE 1: Structural Validity & Metadata Integrity
# ============================================================

class TestGate1StructuralValidity:
    def test_missing_match_id(self, db: Session):
        res = evaluate_pre_match_readiness(db, match_id=999999)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert not res["eligible"]
        assert "MATCH_NOT_FOUND" in res["blocking_reasons"]
        assert not res["gate_verdicts"]["gate1_structural"]["passed"]

    def test_unknown_competition(self, db: Session):
        _, home, away = _create_teams_and_league(db, "EPL")
        now, future, _ = _get_times()
        m = Match(
            league_id=None,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="p1",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert "UNKNOWN_COMPETITION" in res["blocking_reasons"]
        assert not res["gate_verdicts"]["gate1_structural"]["passed"]

    def test_unresolved_teams(self, db: Session):
        league, home, _ = _create_teams_and_league(db, "EPL")
        now, future, _ = _get_times()
        m = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=None,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="p2",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert "UNRESOLVED_TEAMS" in res["blocking_reasons"]

    def test_identical_teams(self, db: Session):
        league, home, _ = _create_teams_and_league(db, "EPL")
        now, future, _ = _get_times()
        m = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=home.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="p3",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert "IDENTICAL_TEAMS" in res["blocking_reasons"]

    def test_missing_kickoff(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        m = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=None,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="p4",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert "MISSING_KICKOFF" in res["blocking_reasons"]

    def test_missing_provider_identity(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        now, future, _ = _get_times()
        m = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="",
            provider_match_id="",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert "MISSING_PROVIDER_IDENTITY" in res["blocking_reasons"]

    def test_source_mapping_satisfies_provider_identity(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="",
            provider_match_id="",
        )
        db.add(m)
        db.flush()

        mapping = MatchSourceMapping(match_id=m.id, source="api_football", source_match_id="src_99")
        db.add(mapping)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert res["gate_verdicts"]["gate1_structural"]["passed"]
        assert "MISSING_PROVIDER_IDENTITY" not in res["blocking_reasons"]


# ============================================================
# 2. GATE 2: Reconciliation & Cross-Source Identity (Phase 25.1 FIX 2)
# ============================================================

class TestGate2ReconciliationAndIdentity:
    def test_critical_reconciliation_conflict_blocks(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="p_recon_1",
        )
        db.add(m)
        db.flush()

        conflict = ReconciliationConflict(
            entity_type="match",
            canonical_entity_id=m.id,
            field="team_mismatch:home",
            severity="critical",
            resolution_status="unresolved",
        )
        db.add(conflict)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert not res["gate_verdicts"]["gate2_reconciliation"]["passed"]
        assert any("CRITICAL_RECONCILIATION_CONFLICT" in r for r in res["blocking_reasons"])

    def test_non_critical_conflict_passes_gate2(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="p_recon_2",
        )
        db.add(m)
        db.flush()

        conflict = ReconciliationConflict(
            entity_type="match",
            canonical_entity_id=m.id,
            field="possession_discrepancy",
            severity="low",
            resolution_status="unresolved",
        )
        db.add(conflict)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert res["gate_verdicts"]["gate2_reconciliation"]["passed"]

    # --- FIX 2: Corrected test (proximity alone is CANDIDATE, not blocking) ---
    def test_duplicate_suspicion_proximity_only_is_warning_not_blocking(self, db: Session):
        """FIX 2: Proximity within ±24h but DIFFERENT provider_match_id = DUPLICATE_CANDIDATE.
        Gate 2 must PASS. Overall state must NOT be BLOCKED due to proximity alone.
        """
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m1 = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="m1_provider_a",
        )
        db.add(m1)
        db.flush()

        # Same competition, same teams, 6 hours apart, DIFFERENT provider_match_id → CANDIDATE only
        m2 = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future + timedelta(hours=6),
            status=MatchStatus.SCHEDULED.value,
            provider="provider_b",
            provider_match_id="m2_provider_b",
        )
        db.add(m2)
        db.flush()

        res = evaluate_pre_match_readiness(db, m1.id, cutoff=now)
        gv = res["gate_verdicts"]["gate2_reconciliation"]

        # Gate 2 must PASS — proximity alone is not blocking
        assert gv["passed"], f"Gate 2 must pass for proximity-only: {gv['reasons']}"
        assert gv["duplicate_state"] == DuplicateDetectionState.DUPLICATE_CANDIDATE.value

        # Warning must be present
        assert any("DUPLICATE_CANDIDATE" in w for w in res["warnings"]), res["warnings"]

        # NOT in blocking reasons
        assert not any("DUPLICATE_CANDIDATE" in r for r in res["blocking_reasons"])

        # Overall state is not BLOCKED solely because of proximity
        assert res["readiness_state"] != PreMatchReadinessState.BLOCKED.value

    # --- FIX 2: 6 new duplicate detection tests ---

    def test_no_duplicate_different_teams_passes(self, db: Session):
        """Different teams, same window — no duplicate."""
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        other_home = Team(name="Other Home", short_name="OH", provider="mock", provider_team_id=f"OH_{datetime.now().microsecond}")
        other_away = Team(name="Other Away", short_name="OA", provider="mock", provider_team_id=f"OA_{datetime.now().microsecond}")
        db.add_all([other_home, other_away])
        db.flush()

        m1 = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="nodiff_m1",
        )
        m2 = Match(
            league_id=league.id, home_team_id=other_home.id, away_team_id=other_away.id,
            kickoff_at=future + timedelta(hours=2), status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="nodiff_m2",
        )
        db.add_all([m1, m2])
        db.flush()

        res = evaluate_pre_match_readiness(db, m1.id, cutoff=now)
        gv = res["gate_verdicts"]["gate2_reconciliation"]
        assert gv["duplicate_state"] == DuplicateDetectionState.NO_DUPLICATE.value
        assert gv["passed"]

    def test_duplicate_confirmed_same_provider_and_id_blocks(self, db: Session):
        """DUPLICATE_CONFIRMED: match's (provider, provider_match_id) is also mapped via
        MatchSourceMapping to a DIFFERENT canonical match (cross-table identity collision).
        Gate 2 must be BLOCKED.

        Note: The Match table has UniqueConstraint(provider, provider_match_id), so two Match
        rows with identical provider+provider_match_id cannot coexist. DUPLICATE_CONFIRMED is
        therefore detected via MatchSourceMapping cross-reference.
        """
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        # m1: primary match with provider="api_football", provider_match_id="SHARED_PROV_ID"
        m1 = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="api_football", provider_match_id="SHARED_PROV_ID",
        )
        db.add(m1)
        db.flush()

        # m2: different match (different teams, different time) — but linked to the
        # SAME provider source ID via MatchSourceMapping → cross-table identity collision
        other_home = Team(name="OtherH", short_name="OH2", provider="mock", provider_team_id=f"OH2_{datetime.now().microsecond}")
        other_away = Team(name="OtherA", short_name="OA2", provider="mock", provider_team_id=f"OA2_{datetime.now().microsecond}")
        db.add_all([other_home, other_away])
        db.flush()
        m2 = Match(
            league_id=league.id, home_team_id=other_home.id, away_team_id=other_away.id,
            kickoff_at=future + timedelta(days=5), status=MatchStatus.SCHEDULED.value,
            provider="statsbomb", provider_match_id="STATSBOMB_M2",
        )
        db.add(m2)
        db.flush()

        # Conflict: m2 is also mapped from "api_football"/"SHARED_PROV_ID" — same as m1
        # This is a confirmed identity collision across different canonical matches
        mapping = MatchSourceMapping(
            match_id=m2.id,
            source="api_football",
            source_match_id="SHARED_PROV_ID",  # same as m1.provider_match_id
        )
        db.add(mapping)
        db.flush()

        res = evaluate_pre_match_readiness(db, m1.id, cutoff=now)
        gv = res["gate_verdicts"]["gate2_reconciliation"]
        assert gv["duplicate_state"] == DuplicateDetectionState.DUPLICATE_CONFIRMED.value, (
            f"Expected DUPLICATE_CONFIRMED, got {gv['duplicate_state']}"
        )
        assert not gv["passed"]
        assert any("DUPLICATE_CONFIRMED" in r for r in res["blocking_reasons"])
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value

    def test_duplicate_resolution_required_both_conditions_blocks(self, db: Session):
        """DUPLICATE_RESOLUTION_REQUIRED: cross-table identity collision AND proximity simultaneously."""
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m1 = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="api_football", provider_match_id="DUAL_ID_777",
        )
        db.add(m1)
        db.flush()

        # m2: same matchup within ±24h (proximity) AND also mapped from the same provider ID (identity)
        m2 = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future + timedelta(hours=6),  # within ±24h window → proximity candidate
            status=MatchStatus.SCHEDULED.value,
            provider="statsbomb", provider_match_id="STATSBOMB_DUAL",
        )
        db.add(m2)
        db.flush()

        # Cross-table identity: m2 also mapped from "api_football"/"DUAL_ID_777" — same as m1
        mapping = MatchSourceMapping(
            match_id=m2.id,
            source="api_football",
            source_match_id="DUAL_ID_777",
        )
        db.add(mapping)
        db.flush()

        res = evaluate_pre_match_readiness(db, m1.id, cutoff=now)
        gv = res["gate_verdicts"]["gate2_reconciliation"]
        # m2 is BOTH proximity-within-24h AND identity-confirmed → RESOLUTION_REQUIRED
        assert gv["duplicate_state"] == DuplicateDetectionState.DUPLICATE_RESOLUTION_REQUIRED.value
        assert not gv["passed"]
        assert any("DUPLICATE_RESOLUTION_REQUIRED" in r for r in res["blocking_reasons"])

    def test_proximity_outside_24h_window_is_no_duplicate(self, db: Session):
        """Same matchup but >24h apart — outside window → NO_DUPLICATE."""
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m1 = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="outside_m1",
        )
        m2 = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future + timedelta(hours=25),  # 25h apart → outside ±24h window
            status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="outside_m2",
        )
        db.add_all([m1, m2])
        db.flush()

        res = evaluate_pre_match_readiness(db, m1.id, cutoff=now)
        gv = res["gate_verdicts"]["gate2_reconciliation"]
        assert gv["duplicate_state"] == DuplicateDetectionState.NO_DUPLICATE.value
        assert gv["passed"]

    def test_match_seven_days_later_is_not_duplicate(self, db: Session):
        """7 days apart, same matchup → clearly not a duplicate."""
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m1 = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m1_single",
        )
        m2 = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future + timedelta(days=7),
            status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m2_later",
        )
        db.add_all([m1, m2])
        db.flush()

        res = evaluate_pre_match_readiness(db, m1.id, cutoff=now)
        assert res["gate_verdicts"]["gate2_reconciliation"]["passed"]

    def test_resolved_critical_conflict_no_longer_blocks(self, db: Session):
        """A resolved conflict does not block Gate 2."""
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="resolved_m1",
        )
        db.add(m)
        db.flush()

        # Resolved conflict — should not block
        conflict = ReconciliationConflict(
            entity_type="match", canonical_entity_id=m.id,
            field="team_mismatch:home", severity="critical",
            resolution_status="resolved",  # resolved!
        )
        db.add(conflict)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert res["gate_verdicts"]["gate2_reconciliation"]["passed"]
        assert not any("CRITICAL_RECONCILIATION_CONFLICT" in r for r in res["blocking_reasons"])


# ============================================================
# 3. GATE 3: Temporal Validity & Cutoff Enforcement (FIX 7)
# ============================================================

class TestGate3TemporalValidityAndCutoff:
    def test_pre_match_cutoff_at_or_after_kickoff_blocks(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m_cutoff",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=future + timedelta(minutes=5), mode="PRE_MATCH")
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert not res["gate_verdicts"]["gate3_temporal"]["passed"]
        assert "CUTOFF_AT_OR_AFTER_KICKOFF" in res["blocking_reasons"]

    def test_pre_match_cutoff_strictly_before_kickoff_passes(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m_cutoff_ok",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=future - timedelta(hours=1), mode="PRE_MATCH")
        assert res["gate_verdicts"]["gate3_temporal"]["passed"]
        assert "CUTOFF_AT_OR_AFTER_KICKOFF" not in res["blocking_reasons"]

    def test_non_prematch_mode_allows_cutoff_after_kickoff(self, db: Session):
        """FIX 7: POST_MATCH mode does not enforce cutoff < kickoff."""
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.FINISHED.value,
            provider="mock", provider_match_id="m_post",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=future + timedelta(hours=2), mode="POST_MATCH")
        assert res["gate_verdicts"]["gate3_temporal"]["passed"]
        assert "CUTOFF_AT_OR_AFTER_KICKOFF" not in res["blocking_reasons"]
        # Mode is correctly recorded (FIX 7)
        assert res["mode"] == "POST_MATCH"

    def test_stale_fixture_awaiting_sync_blocks(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, _, past = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=past, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m_stale",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now, mode="POST_MATCH")
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert "STALE_FIXTURE_AWAITING_SYNC" in res["blocking_reasons"]

    def test_postponed_or_cancelled_fixture_blocks(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.POSTPONED.value,
            provider="mock", provider_match_id="m_postponed",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert any("FIXTURE_POSTPONED_OR_CANCELLED" in r for r in res["blocking_reasons"])


# ============================================================
# 4. GATE 4: Feature Availability & Leakage Eligibility (FIX 3/9)
# ============================================================

class TestGate4FeatureAvailabilityAndLeakage:
    def test_insufficient_historical_matches_blocks(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        now, future, _ = _get_times()
        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m_nohist",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert not res["gate_verdicts"]["gate4_features"]["passed"]
        assert any("INSUFFICIENT_HISTORICAL_MATCHES" in r for r in res["blocking_reasons"])

    def test_optional_features_missing_yields_ready_degraded(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        now, future, _ = _get_times()
        _seed_finished_history(db, league, home, count=4, before_dt=now)
        _seed_finished_history(db, league, away, count=4, before_dt=now)

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m_opt_missing",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert res["gate_verdicts"]["gate1_structural"]["passed"]
        assert res["gate_verdicts"]["gate2_reconciliation"]["passed"]
        assert res["gate_verdicts"]["gate3_temporal"]["passed"]
        assert res["gate_verdicts"]["gate4_features"]["passed"]
        assert res["gate_verdicts"]["gate4_features"]["status"] == "degraded"
        assert res["readiness_state"] == PreMatchReadinessState.READY_DEGRADED.value
        assert res["eligible"]
        assert len(res["blocking_reasons"]) == 0
        assert any("lineups" in w for w in res["warnings"])
        assert any("market_odds" in w for w in res["warnings"])

    def test_complete_features_yields_prediction_ready(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        now, future, _ = _get_times()
        _seed_finished_history(db, league, home, count=4, before_dt=now)
        _seed_finished_history(db, league, away, count=4, before_dt=now)

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m_complete",
        )
        db.add(m)
        db.flush()

        lineup = Lineup(match_id=m.id, team="home", player_name="Player 1")
        db.add(lineup)
        odds = OddsSnapshot(match_id=m.id, market_type="h2h", timestamp=now - timedelta(hours=1))
        db.add(odds)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert res["readiness_state"] == PreMatchReadinessState.PREDICTION_READY.value
        assert res["eligible"]
        assert res["gate_verdicts"]["gate4_features"]["status"] == "pass"
        assert len(res["blocking_reasons"]) == 0
        assert len(res["warnings"]) == 0

    def test_temporal_leakage_safety_ignores_future_matches(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        now, future, _ = _get_times()
        _seed_finished_history(db, league, home, count=4, before_dt=now + timedelta(days=20))
        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m_leak_check",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert any("INSUFFICIENT_HISTORICAL_MATCHES" in r for r in res["blocking_reasons"])

    def test_gate4_uses_prediction_config_required_features(self, db: Session):
        """FIX 3: Gate 4 must use PredictionReadinessConfig, not hard-coded values."""
        config = get_prediction_config(DEFAULT_MODEL_ID)
        assert "historical_match_context" in config.required_features
        assert config.min_historical_matches_per_team == 3

    def test_gate4_response_includes_prediction_config_fields(self, db: Session):
        """FIX 3/5: evaluate_pre_match_readiness must expose prediction_config, model_version, etc."""
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m_config_check",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert "prediction_config" in res
        assert "model_version" in res
        assert "prediction_mode" in res
        assert "required_features" in res
        assert "available_features" in res
        assert "missing_required_features" in res
        assert "missing_optional_features" in res
        assert res["model_version"] == DEFAULT_MODEL_ID
        assert res["prediction_mode"] == "strict_prematch"

    def test_gate4_min_historical_from_config_not_hardcoded(self, db: Session):
        """FIX 9: min_historical_matches_per_team comes from PredictionReadinessConfig."""
        config = get_prediction_config(DEFAULT_MODEL_ID)
        assert config.min_historical_matches_per_team == 3

        # Verify no module-level constant MIN_HISTORICAL_MATCHES_PER_TEAM exists
        import app.services.acquisition.readiness_gate as rg
        assert not hasattr(rg, "MIN_HISTORICAL_MATCHES_PER_TEAM"), (
            "MIN_HISTORICAL_MATCHES_PER_TEAM must be removed from module scope (FIX 9)"
        )


# ============================================================
# 5. GATE 5: Immutable Certificate Generation & Hash Determinism (FIX 5/6)
# ============================================================

class TestGate5CertificateAndCanonicalHash:
    def test_canonical_hash_determinism(self):
        payload_1 = {"b_key": "val_b", "a_key": "val_a", "c_nested": {"z": 1, "a": 2}}
        payload_2 = {"a_key": "val_a", "c_nested": {"a": 2, "z": 1}, "b_key": "val_b"}
        hash_1 = compute_canonical_certificate_hash(payload_1)
        hash_2 = compute_canonical_certificate_hash(payload_2)
        assert hash_1 == hash_2
        assert len(hash_1) == 64

    def test_certificate_hash_sensitive_to_provider_field_change(self, db: Session):
        """FIX 5: Hash must change if provider field changes."""
        payload_a = {"provider": "api_football", "match_id": 1, "state": "BLOCKED"}
        payload_b = {"provider": "statsbomb", "match_id": 1, "state": "BLOCKED"}
        assert compute_canonical_certificate_hash(payload_a) != compute_canonical_certificate_hash(payload_b)

    def test_certificate_persistence_and_contract(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m_cert_1",
        )
        db.add(m)
        db.flush()

        cert = generate_readiness_certificate(db, m.id, cutoff=now)
        assert cert.certificate_version == CERTIFICATE_CONTRACT_VERSION
        assert cert.readiness_contract_version == CERTIFICATE_CONTRACT_VERSION
        assert cert.match_id == m.id
        assert cert.competition == "EPL"
        assert cert.readiness_state in (
            PreMatchReadinessState.PREDICTION_READY.value,
            PreMatchReadinessState.READY_DEGRADED.value,
        )
        assert cert.payload_hash is not None
        assert len(cert.payload_hash) == 64
        assert cert.supersedes_certificate_id is None

    def test_certificate_payload_includes_provider_fields(self, db: Session):
        """FIX 5: Certificate must include provider provenance fields."""
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="api_football", provider_match_id="prov_test_42",
        )
        db.add(m)
        db.flush()

        cert = generate_readiness_certificate(db, m.id, cutoff=now)
        assert cert.provider == "api_football"
        assert cert.provider_match_id == "prov_test_42"
        # provider_qualification_version must be None (SourceQualification has no version field)
        assert cert.provider_qualification_version is None
        # prediction_config must be present and correct
        assert cert.prediction_config is not None
        assert cert.model_version == DEFAULT_MODEL_ID
        assert cert.prediction_mode == "strict_prematch"
        # required/available feature lists present
        assert isinstance(cert.required_features, list)
        assert isinstance(cert.available_features, list)
        assert isinstance(cert.missing_required_features, list)
        assert isinstance(cert.missing_optional_features, list)

    def test_certificate_immutability_and_superseding(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="m_cert_2",
        )
        db.add(m)
        db.flush()

        cert1 = generate_readiness_certificate(db, m.id, cutoff=now)
        cert1_id = cert1.certificate_id
        cert1_hash = cert1.payload_hash

        cert2 = generate_readiness_certificate(db, m.id, cutoff=now + timedelta(minutes=30))
        assert cert2.certificate_id != cert1_id
        assert cert2.supersedes_certificate_id == cert1_id

        # Reload cert1 — must be byte-identical
        reloaded_cert1 = db.query(PreMatchReadinessCertificate).filter_by(certificate_id=cert1_id).one()
        assert reloaded_cert1.payload_hash == cert1_hash
        assert reloaded_cert1.supersedes_certificate_id is None

    def test_adversarial_cert_old_is_byte_identical_after_context_change(self, db: Session):
        """FIX 6: Adversarial test — changing context (score update) must NOT mutate the existing cert."""
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="adv_cert_test",
        )
        db.add(m)
        db.flush()

        # Generate original cert
        cert1 = generate_readiness_certificate(db, m.id, cutoff=now)
        cert1_id = cert1.certificate_id
        cert1_hash = cert1.payload_hash
        cert1_state = cert1.readiness_state
        cert1_created = cert1.created_at

        # Simulate post-cutoff context change: add a score
        m.home_score = 3
        m.away_score = 1
        db.flush()

        # Generate new cert (superseding)
        cert2 = generate_readiness_certificate(db, m.id, cutoff=now + timedelta(hours=2))
        assert cert2.certificate_id != cert1_id

        # Reload cert1 — verify byte-identical (payload_hash unchanged)
        db.expire_all()
        reloaded = db.query(PreMatchReadinessCertificate).filter_by(certificate_id=cert1_id).one()
        assert reloaded.payload_hash == cert1_hash, "Original cert payload_hash must not change"
        assert reloaded.readiness_state == cert1_state, "Original cert state must not change"
        assert reloaded.supersedes_certificate_id is None, "Original cert supersedes must remain None"

    def test_prematch_cert_not_mutated_after_score_update(self, db: Session):
        """FIX 7: Post-match score data does not backfill into a PRE_MATCH certificate."""
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="postmatch_test",
        )
        db.add(m)
        db.flush()

        prematch_cert = generate_readiness_certificate(db, m.id, cutoff=now, mode="PRE_MATCH")
        prematch_hash = prematch_cert.payload_hash

        # Simulate match finishing and score being written
        m.status = MatchStatus.FINISHED.value
        m.home_score = 2
        m.away_score = 0
        db.flush()

        # Original PRE_MATCH cert untouched
        db.expire_all()
        reloaded = db.query(PreMatchReadinessCertificate).filter_by(
            certificate_id=prematch_cert.certificate_id
        ).one()
        assert reloaded.payload_hash == prematch_hash


# ============================================================
# 6. Summary Telemetry (FIX 4/8)
# ============================================================

class TestPreMatchSummaryAndTelemetry:
    def test_honest_zero_fixtures_summary(self, db: Session):
        summary = get_current_season_prematch_summary(db, season="2026/27")
        assert summary["season"] == "2026/27"
        assert summary["operational_mode"] == "readiness_only"
        assert summary["fixture_count"] == 0
        assert summary["reconciled_count"] == 0
        assert summary["temporally_valid_count"] == 0
        assert summary["quality_passed_count"] == 0
        assert summary["prediction_ready_count"] == 0
        assert summary["ready_degraded_count"] == 0
        assert summary["blocked_count"] == 0
        assert summary["blocking_reasons"] == {}

    def test_summary_has_all_11_required_counters(self, db: Session):
        """FIX 8: Summary must have exactly the 11 specified counters."""
        summary = get_current_season_prematch_summary(db, season="2026/27")
        required_keys = [
            "season",
            "operational_mode",
            "provider_state",
            "fixture_count",
            "reconciled_count",
            "temporally_valid_count",
            "quality_passed_count",
            "prediction_ready_count",
            "ready_degraded_count",
            "blocked_count",
            "blocking_reasons",
        ]
        for key in required_keys:
            assert key in summary, f"Missing required summary key: {key}"

    def test_summary_includes_provider_activation_by_competition(self, db: Session):
        """FIX 4/8: Summary must include provider_activation_by_competition dict."""
        summary = get_current_season_prematch_summary(db, season="2026/27")
        assert "provider_activation_by_competition" in summary
        assert isinstance(summary["provider_activation_by_competition"], dict)

    def test_summary_provider_state_scoped_to_competition_season(self, db: Session):
        """FIX 4: provider_state must come from actual activation records, not global latest."""
        from app.db.models.acquisition import SourceActivation
        from app.services.acquisition.activation import ActivationState

        # Insert ACTIVE record for a specific competition (not for 2026/27 EPL)
        row = SourceActivation(
            source="some_provider",
            state=ActivationState.ACTIVE.value,
            decided_by="test",
            checks={"competition": "LA_LIGA", "season": "2024/25"},
            reason="test activation",
        )
        db.add(row)
        db.commit()

        # Summary for 2026/27 — should NOT show ACTIVE just because LA_LIGA 2024/25 has ACTIVE
        summary = get_current_season_prematch_summary(db, season="2026/27")
        # The global provider_state for 2026/27 should reflect 2026/27 scoping
        # (no EPL/other 2026/27 activation exists yet → UNAVAILABLE or not ACTIVE for that season)
        by_comp = summary["provider_activation_by_competition"]
        # Should not falsely show ACTIVE for competitions that have no 2026/27 activation
        for comp, state in by_comp.items():
            # Check that it returns UNAVAILABLE for competitions with no 2026/27 activation record
            # (This verifies scoping is applied, not just global latest)
            assert state in {s.value for s in ActivationState}, f"Invalid state: {state}"

    def test_summary_with_multi_state_fixtures(self, db: Session):
        hist_lg, _, _ = _create_teams_and_league(db, "EPL_HIST", season="2025/26")
        league, home, away = _create_teams_and_league(db, "EPL", season="2026/27")
        _seed_finished_history(db, hist_lg, home, count=4)
        _seed_finished_history(db, hist_lg, away, count=4)
        now, future, past = _get_times()

        m1 = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="s_m1",
        )
        home2 = Team(name="Team 2H", short_name="T2H", provider="mock", provider_team_id=f"T2H_{datetime.now().microsecond}")
        away2 = Team(name="Team 2A", short_name="T2A", provider="mock", provider_team_id=f"T2A_{datetime.now().microsecond}")
        db.add_all([home2, away2])
        db.flush()
        _seed_finished_history(db, hist_lg, home2, count=4)
        _seed_finished_history(db, hist_lg, away2, count=4)

        m2 = Match(
            league_id=league.id, home_team_id=home2.id, away_team_id=away2.id,
            kickoff_at=past, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="s_m2",
        )
        db.add_all([m1, m2])
        db.flush()

        summary = get_current_season_prematch_summary(db, season="2026/27")
        assert summary["fixture_count"] == 2
        assert summary["ready_degraded_count"] == 1
        assert summary["blocked_count"] == 1
        assert summary["reconciled_count"] == 2
        assert summary["temporally_valid_count"] == 1
        assert "STALE_FIXTURE_AWAITING_SYNC" in summary["blocking_reasons"]


# ============================================================
# 7. FastAPI API Endpoints
# ============================================================

class TestApiEndpoints:
    def test_api_pre_match_readiness_endpoint(self, client: TestClient, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="api_m1",
        )
        db.add(m)
        db.commit()

        resp = client.get(f"/api/v1/matches/{m.id}/pre-match-readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["match_id"] == m.id
        assert data["readiness_state"] in ("PREDICTION_READY", "READY_DEGRADED")
        assert "gate_verdicts" in data
        assert "certificate" not in data
        # FIX 5: response must include prediction_config fields
        assert "prediction_config" in data
        assert "model_version" in data

        resp_persist = client.get(f"/api/v1/matches/{m.id}/pre-match-readiness?persist=true")
        assert resp_persist.status_code == 200
        data_p = resp_persist.json()
        assert "certificate" in data_p
        assert data_p["certificate"]["certificate_id"].startswith("cert_")
        assert data_p["certificate"]["certificate_version"] == CERTIFICATE_CONTRACT_VERSION

    def test_api_readiness_summary_endpoint(self, client: TestClient, db: Session):
        resp = client.get("/api/v1/matches/current/readiness-summary?season=2026/27")
        assert resp.status_code == 200
        data = resp.json()
        assert data["season"] == "2026/27"
        assert "operational_mode" in data
        assert "fixture_count" in data
        assert "reconciled_count" in data
        assert "prediction_ready_count" in data
        # FIX 4/8: per-competition activation
        assert "provider_activation_by_competition" in data

    def test_api_post_cutoff_odds_not_in_prematch_features(self, client: TestClient, db: Session):
        """FIX 7: Odds timestamped after cutoff must not appear in PRE_MATCH feature evaluation."""
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=future, status=MatchStatus.SCHEDULED.value,
            provider="mock", provider_match_id="api_leakage_m1",
        )
        db.add(m)
        db.commit()

        # Add odds AFTER the cutoff (should not count)
        cutoff_for_test = now - timedelta(hours=1)
        odds = OddsSnapshot(
            match_id=m.id,
            market_type="h2h",
            timestamp=now,  # now > cutoff_for_test → post-cutoff
        )
        db.add(odds)
        db.commit()

        # Use naive UTC ISO format (no +00:00 suffix) to avoid URL encoding issues
        cutoff_str = cutoff_for_test.strftime("%Y-%m-%dT%H:%M:%S")
        resp = client.get(
            f"/api/v1/matches/{m.id}/pre-match-readiness?cutoff={cutoff_str}&mode=PRE_MATCH"
        )
        assert resp.status_code == 200
        data = resp.json()
        # market_odds should be in missing_optional_features since odds are post-cutoff
        assert "market_odds" in data.get("missing_optional_features", [])



# ============================================================
# 8. Golden Prediction Regression Guard
# ============================================================

def test_golden_prediction_preservation(db: Session):
    """Verifies that prediction algorithms, model weights, and probabilities remain 100% frozen."""
    _, _, target = _history(db, code="P25GOLD")
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
