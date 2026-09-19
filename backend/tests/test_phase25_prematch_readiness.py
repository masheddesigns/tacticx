"""Phase 25 — Current-Season Data Quality, Reconciliation & Pre-Match Readiness Test Suite.

Verifies:
1. Gate 1: Structural validity & fixture metadata integrity.
2. Gate 2: Reconciliation & cross-source identity validation (conflicts + duplicate proximity check).
3. Gate 3: Temporal validity & cutoff enforcement (mode-aware cutoff < kickoff, stale fixtures, postponed).
4. Gate 4: Feature availability & leakage eligibility (core history vs optional lineups/odds).
5. Gate 5: Immutable readiness certificate generation, canonical SHA-256 hashing, and superseding behavior.
6. Current-season pre-match summary telemetry (distinct non-collapsing counters, honest 0-fixture state).
7. FastAPI HTTP endpoints for pre-match readiness and current-season summary.
8. Golden prediction regression preservation.
"""
from __future__ import annotations

import json
import math
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
    PreMatchReadinessState,
    compute_canonical_certificate_hash,
    evaluate_pre_match_readiness,
    generate_readiness_certificate,
    get_current_season_prematch_summary,
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

    home = Team(name=f"{code} Home FC", short_name="HOM", provider="mock", provider_team_id=f"H_{code}_{datetime.now().microsecond}")
    away = Team(name=f"{code} Away FC", short_name="AWY", provider="mock", provider_team_id=f"A_{code}_{datetime.now().microsecond}")
    db.add_all([home, away])
    db.flush()
    return league, home, away


def _seed_finished_history(db: Session, league: League, team: Team, count: int = 4, before_dt: datetime = None):
    """Create historical finished matches for a team strictly before before_dt."""
    if before_dt is None:
        before_dt = datetime.now(timezone.utc)

    other = Team(name=f"Opponent {team.id}_{datetime.now().microsecond}", provider="mock", provider_team_id=f"OPP_{team.id}_{datetime.now().microsecond}")
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


# --------------------------------------------------------------------------------------
# 1. GATE 1: Structural Validity & Metadata Integrity
# --------------------------------------------------------------------------------------

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


# --------------------------------------------------------------------------------------
# 2. GATE 2: Reconciliation & Cross-Source Identity Validation
# --------------------------------------------------------------------------------------

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

    def test_duplicate_suspicion_proximity_check_blocks(self, db: Session):
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
            provider_match_id="m1",
        )
        db.add(m1)
        db.flush()

        # Another match with same competition, same home/away, 6 hours apart
        m2 = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future + timedelta(hours=6),
            status=MatchStatus.SCHEDULED.value,
            provider="provider_b",
            provider_match_id="m2",
        )
        db.add(m2)
        db.flush()

        res = evaluate_pre_match_readiness(db, m1.id, cutoff=now)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert not res["gate_verdicts"]["gate2_reconciliation"]["passed"]
        assert any("DUPLICATE_SUSPICION_AWAITING_RECONCILIATION" in r for r in res["blocking_reasons"])

    def test_match_seven_days_later_is_not_duplicate(self, db: Session):
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
            provider_match_id="m1_single",
        )
        m2 = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future + timedelta(days=7),
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="m2_later",
        )
        db.add_all([m1, m2])
        db.flush()

        res = evaluate_pre_match_readiness(db, m1.id, cutoff=now)
        assert res["gate_verdicts"]["gate2_reconciliation"]["passed"]


# --------------------------------------------------------------------------------------
# 3. GATE 3: Temporal Validity & Cutoff Enforcement
# --------------------------------------------------------------------------------------

class TestGate3TemporalValidityAndCutoff:
    def test_pre_match_cutoff_at_or_after_kickoff_blocks(self, db: Session):
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
            provider_match_id="m_cutoff",
        )
        db.add(m)
        db.flush()

        # Cutoff is after kickoff
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
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="m_cutoff_ok",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=future - timedelta(hours=1), mode="PRE_MATCH")
        assert res["gate_verdicts"]["gate3_temporal"]["passed"]
        assert "CUTOFF_AT_OR_AFTER_KICKOFF" not in res["blocking_reasons"]

    def test_non_prematch_mode_allows_cutoff_after_kickoff(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, future, _ = _get_times()

        m = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.FINISHED.value,
            provider="mock",
            provider_match_id="m_post",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=future + timedelta(hours=2), mode="POST_MATCH")
        assert res["gate_verdicts"]["gate3_temporal"]["passed"]
        assert "CUTOFF_AT_OR_AFTER_KICKOFF" not in res["blocking_reasons"]

    def test_stale_fixture_awaiting_sync_blocks(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        _seed_finished_history(db, league, home, count=4)
        _seed_finished_history(db, league, away, count=4)
        now, _, past = _get_times()

        # Kickoff was 2 hours ago, but status is still SCHEDULED
        m = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=past,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="m_stale",
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
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.POSTPONED.value,
            provider="mock",
            provider_match_id="m_postponed",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert any("FIXTURE_POSTPONED_OR_CANCELLED" in r for r in res["blocking_reasons"])


# --------------------------------------------------------------------------------------
# 4. GATE 4: Feature Availability & Leakage Eligibility
# --------------------------------------------------------------------------------------

class TestGate4FeatureAvailabilityAndLeakage:
    def test_insufficient_historical_matches_blocks(self, db: Session):
        league, home, away = _create_teams_and_league(db, "EPL")
        now, future, _ = _get_times()
        # 0 finished history seeded
        m = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="m_nohist",
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
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="m_opt_missing",
        )
        db.add(m)
        db.flush()

        # No lineups and no odds snapshots added
        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        assert res["gate_verdicts"]["gate1_structural"]["passed"]
        assert res["gate_verdicts"]["gate2_reconciliation"]["passed"]
        assert res["gate_verdicts"]["gate3_temporal"]["passed"]
        assert res["gate_verdicts"]["gate4_features"]["passed"]
        assert res["gate_verdicts"]["gate4_features"]["status"] == "degraded"

        # Overall state is READY_DEGRADED, eligible for prediction
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
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="m_complete",
        )
        db.add(m)
        db.flush()

        # Add lineup
        lineup = Lineup(match_id=m.id, team="home", player_name="Player 1")
        db.add(lineup)

        # Add odds snapshot before cutoff
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
        # Seed matches AFTER cutoff
        _seed_finished_history(db, league, home, count=4, before_dt=now + timedelta(days=20))
        m = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="m_leak_check",
        )
        db.add(m)
        db.flush()

        res = evaluate_pre_match_readiness(db, m.id, cutoff=now)
        # Should be blocked because historical matches occurred after cutoff
        assert res["readiness_state"] == PreMatchReadinessState.BLOCKED.value
        assert any("INSUFFICIENT_HISTORICAL_MATCHES" in r for r in res["blocking_reasons"])


# --------------------------------------------------------------------------------------
# 5. GATE 5: Immutable Certificate Generation & Hash Determinism
# --------------------------------------------------------------------------------------

class TestGate5CertificateAndCanonicalHash:
    def test_canonical_hash_determinism(self):
        payload_1 = {
            "b_key": "val_b",
            "a_key": "val_a",
            "c_nested": {"z": 1, "a": 2},
        }
        payload_2 = {
            "a_key": "val_a",
            "c_nested": {"a": 2, "z": 1},
            "b_key": "val_b",
        }
        hash_1 = compute_canonical_certificate_hash(payload_1)
        hash_2 = compute_canonical_certificate_hash(payload_2)
        assert hash_1 == hash_2
        assert len(hash_1) == 64

    def test_certificate_persistence_and_contract(self, db: Session):
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
            provider_match_id="m_cert_1",
        )
        db.add(m)
        db.flush()

        cert = generate_readiness_certificate(db, m.id, cutoff=now)
        assert cert.certificate_version == CERTIFICATE_CONTRACT_VERSION
        assert cert.readiness_contract_version == CERTIFICATE_CONTRACT_VERSION
        assert cert.match_id == m.id
        assert cert.competition == "EPL"
        assert cert.readiness_state in (PreMatchReadinessState.PREDICTION_READY.value, PreMatchReadinessState.READY_DEGRADED.value)
        assert cert.payload_hash is not None
        assert len(cert.payload_hash) == 64
        assert cert.supersedes_certificate_id is None

    def test_certificate_immutability_and_superseding(self, db: Session):
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
            provider_match_id="m_cert_2",
        )
        db.add(m)
        db.flush()

        cert1 = generate_readiness_certificate(db, m.id, cutoff=now)
        cert1_id = cert1.certificate_id
        cert1_hash = cert1.payload_hash

        # Second observation / evaluation at a later cutoff
        cert2 = generate_readiness_certificate(db, m.id, cutoff=now + timedelta(minutes=30))
        assert cert2.certificate_id != cert1_id
        assert cert2.supersedes_certificate_id == cert1_id

        # Reload cert1 from DB: verify it was NOT mutated
        reloaded_cert1 = db.query(PreMatchReadinessCertificate).filter_by(certificate_id=cert1_id).one()
        assert reloaded_cert1.payload_hash == cert1_hash
        assert reloaded_cert1.supersedes_certificate_id is None


# --------------------------------------------------------------------------------------
# 6. Current-Season Pre-Match Summary Telemetry
# --------------------------------------------------------------------------------------

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

    def test_summary_with_multi_state_fixtures(self, db: Session):
        # Create prior historical season for finished matches
        hist_lg, _, _ = _create_teams_and_league(db, "EPL_HIST", season="2025/26")
        league, home, away = _create_teams_and_league(db, "EPL", season="2026/27")
        _seed_finished_history(db, hist_lg, home, count=4)
        _seed_finished_history(db, hist_lg, away, count=4)
        now, future, past = _get_times()

        # Fixture 1: Degraded (valid, missing optional features)
        m1 = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=future,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="s_m1",
        )
        # Fixture 2: Blocked (stale fixture with distinct teams)
        home2 = Team(name="Team 2H", short_name="T2H", provider="mock", provider_team_id=f"T2H_{datetime.now().microsecond}")
        away2 = Team(name="Team 2A", short_name="T2A", provider="mock", provider_team_id=f"T2A_{datetime.now().microsecond}")
        db.add_all([home2, away2])
        db.flush()
        _seed_finished_history(db, hist_lg, home2, count=4)
        _seed_finished_history(db, hist_lg, away2, count=4)

        m2 = Match(
            league_id=league.id,
            home_team_id=home2.id,
            away_team_id=away2.id,
            kickoff_at=past,
            status=MatchStatus.SCHEDULED.value,
            provider="mock",
            provider_match_id="s_m2",
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


# --------------------------------------------------------------------------------------
# 7. FastAPI API Endpoints
# --------------------------------------------------------------------------------------

class TestApiEndpoints:
    def test_api_pre_match_readiness_endpoint(self, client: TestClient, db: Session):
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
            provider_match_id="api_m1",
        )
        db.add(m)
        db.commit()

        # Regular evaluation (no persistence)
        resp = client.get(f"/api/v1/matches/{m.id}/pre-match-readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["match_id"] == m.id
        assert data["readiness_state"] in ("PREDICTION_READY", "READY_DEGRADED")
        assert "gate_verdicts" in data
        assert "certificate" not in data

        # Persisted evaluation
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


# --------------------------------------------------------------------------------------
# 8. Golden Prediction Regression Guard
# --------------------------------------------------------------------------------------

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
