"""Phase 10 tests: temporal provenance, freshness, registry, fixtures,
eligibility, audits, idempotency, CLI validation. No live network calls."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, MatchStatistic, Team
from app.db.models.freshness import MatchObservation
from app.services.features.temporal import TemporalMode
from app.services.freshness import audit, eligibility, fixtures, policies, provenance, registry

BASE = datetime(2024, 9, 1, 12, 0)
STRICT = TemporalMode.STRICT_PREMATCH


def _league(db, code="P10"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p10", season="2024")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for name in names:
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=f"p10-{league.code}-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _match(db, league, teams, kickoff=None, status="SCHEDULED", hs=None, aws=None):
    names = list(teams)
    match = Match(
        league_id=league.id, home_team_id=teams[names[0]].id,
        away_team_id=teams[names[1]].id,
        kickoff_at=kickoff or BASE, status=status, home_score=hs, away_score=aws,
        provider="test", provider_match_id=f"p10-{kickoff}")
    db.add(match)
    db.commit()
    return match


# -- temporal provenance ---------------------------------------------------------

def test_classify_known_unknown_estimated():
    cutoff = BASE
    assert provenance.classify(BASE - timedelta(days=1), cutoff) == "known_pre_cutoff"
    assert provenance.classify(BASE + timedelta(days=1), cutoff) == "known_post_cutoff"
    assert provenance.classify(BASE, cutoff) == "known_pre_cutoff"  # equality
    assert provenance.classify(None, cutoff) == "unknown"
    assert provenance.classify(None, cutoff, estimated=True,
                               anchor_before_cutoff=True) == "estimated_pre_cutoff"
    assert provenance.classify(None, cutoff, estimated=True,
                               anchor_before_cutoff=False) == "estimated_post_cutoff"
    # Estimated never presented as known.
    assert provenance.classify(None, cutoff, estimated=True,
                               anchor_before_cutoff=True) != "known_pre_cutoff"


def test_age_none_when_unknown():
    assert provenance.age_days(None, BASE) is None
    assert provenance.age_days(BASE - timedelta(days=2), BASE) == 2.0


# -- freshness policies -------------------------------------------------------------

def test_freshness_states_and_family_policies():
    fresh = policies.classify_freshness("odds", 0.5)
    assert fresh["state"] == "fresh"
    assert policies.classify_freshness("odds", 3)["state"] == "stale"
    assert policies.classify_freshness("odds", 30)["state"] == "expired"
    assert policies.classify_freshness("odds", None)["state"] == "unknown"
    # Family-specific: 20 days is fresh for membership, stale for odds.
    assert policies.classify_freshness("squad_membership", 20)["state"] == "fresh"
    assert policies.classify_freshness("lineup", 400)["state"] == "expired"


# -- fixture observations ---------------------------------------------------------------

def test_observation_append_only_and_idempotent(db):
    league = _league(db)
    teams = _teams(db, league, ("H", "A"))
    match = _match(db, league, teams)
    first = fixtures.observe_fixture(db, match.id, "src", {"status": "SCHEDULED"})
    assert first["appended"] == [] and first["unchanged"] == ["status"]
    changed = fixtures.observe_fixture(
        db, match.id, "src",
        {"status": "POSTPONED", "kickoff_at": BASE + timedelta(hours=2)})
    assert set(changed["appended"]) == {"status", "kickoff_at"}
    repeat = fixtures.observe_fixture(
        db, match.id, "src",
        {"status": "POSTPONED", "kickoff_at": BASE + timedelta(hours=2)})
    assert repeat["appended"] == []
    history = fixtures.observation_history(db, match.id)
    assert len(history) == 2
    status_row = next(r for r in history if r["field"] == "status")
    assert status_row["previous_value"] == "SCHEDULED"
    assert status_row["new_value"] == "POSTPONED"
    # Old observation never mutated by the repeat.
    assert db.query(MatchObservation).count() == 2


def test_fixture_freshness_states(db):
    league = _league(db, code="P10F")
    teams = _teams(db, league, ("H", "A"))
    future = _match(db, league, teams,
                    kickoff=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=3))
    assert fixtures.fixture_freshness(db, future.id)["state"] == "unknown"
    fixtures.observe_fixture(db, future.id, "src",
                             {"kickoff_at": future.kickoff_at + timedelta(hours=1)})
    assert fixtures.fixture_freshness(db, future.id)["state"] == "fresh"
    stale = _match(db, league, teams,
                   kickoff=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=3))
    assert fixtures.fixture_freshness(db, stale.id)["state"] == "unknown"
    finished = _match(db, league, teams, kickoff=BASE, status="FINISHED", hs=1, aws=0)
    assert fixtures.fixture_freshness(db, finished.id)["state"] == "expired"


# -- registry ------------------------------------------------------------------------------

def test_measured_capabilities_never_theoretical(db):
    league = _league(db, code="P10R")
    teams = _teams(db, league, ("H", "A"))
    _match(db, league, teams, status="FINISHED", hs=1, aws=0)
    caps = registry.measured_capabilities(db)
    assert caps["test"]["fixtures"] == "measured"
    assert caps["test"]["events"] == "unavailable"
    assert caps["test"]["current_season"] == "unavailable"
    quality = registry.temporal_metadata_quality(db)
    assert isinstance(quality, dict)


# -- eligibility -------------------------------------------------------------------------------

def test_eligibility_full_and_degraded(db):
    league = _league(db, code="P10E")
    teams = _teams(db, league, ("H", "A"))
    for day in range(6):
        _match(db, league, teams,
               kickoff=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30 - day),
               status="FINISHED", hs=2, aws=1)
    future = _match(db, league, teams,
                    kickoff=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2))
    verdict = eligibility.check_eligibility(
        db, future.id, datetime.now(timezone.utc), mode="production_strict")
    assert verdict["eligible"] is True
    assert verdict["families"]["team_form"]["eligible"] is True
    assert verdict["families"]["player_form"]["eligible"] is False
    assert verdict["families"]["xg"]["eligible"] is False
    assert verdict["degraded_mode"] is True  # reduced features, explicit
    assert verdict["temporal_quality"] == "strict"


def test_eligibility_strict_rejection(db):
    league = _league(db, code="P10E2")
    teams = _teams(db, league, ("H", "A"))
    lonely = _league(db, code="P10E3")
    lonely_teams = _teams(db, lonely, ("X", "Y"))
    target = _match(db, lonely, lonely_teams,
                    kickoff=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2))
    verdict = eligibility.check_eligibility(
        db, target.id, datetime.now(timezone.utc), mode="production_strict")
    assert verdict["eligible"] is False
    assert any("historical" in r for r in verdict["reasons"])
    # Post-kickoff cutoff refused.
    past = _match(db, league, teams, kickoff=BASE, status="FINISHED", hs=1, aws=0)
    verdict2 = eligibility.check_eligibility(db, past.id, BASE, mode="production_strict")
    assert verdict2["eligible"] is False


def test_eligibility_critical_conflict_blocks(db):
    from app.services.reconciliation import matches as match_recon

    league = _league(db, code="P10E4")
    teams = _teams(db, league, ("H", "A"))
    target = _match(db, league, teams,
                    kickoff=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2))
    for day in range(6):
        _match(db, league, teams,
               kickoff=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30 - day),
               status="FINISHED", hs=1, aws=0)
    match_recon.reconcile_match(db, target.id, "rogue",
                                {"home_team_id": teams["A"].id + 99999})
    verdict = eligibility.check_eligibility(
        db, target.id, datetime.now(timezone.utc), mode="production_strict")
    assert verdict["eligible"] is False
    assert any("critical" in r for r in verdict["reasons"])


# -- audits ------------------------------------------------------------------------------------------

def test_current_season_audit_honest(db):
    league = _league(db, code="P10S")
    teams = _teams(db, league, ("H", "A"))
    _match(db, league, teams, status="FINISHED", hs=1, aws=0)
    report = audit.current_season_audit(db)
    assert "current_season" in report
    assert report["leagues"]["P10S"]["status"] == "unavailable"
    assert "provider_plan_or_source_limit" in report["leagues"]["P10S"]["reason"]


def test_staleness_buckets_and_xg_player_audits(db):
    league = _league(db, code="P10ST")
    teams = _teams(db, league, ("H", "A"))
    for day in range(4):
        _match(db, league, teams,
               kickoff=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=day + 1),
               status="FINISHED", hs=1, aws=0)
    dist = audit.staleness_distribution(db, league_code="P10ST")
    assert dist["sampled"] >= 1
    assert set(dist["buckets"]) == {"0-7d", "8-30d", "31-90d", "91-365d",
                                    "1-3y", "3+y", "unknown"}
    assert dist["distribution"]["team_history"]["0-7d"] >= 1
    xg = audit.xg_temporal_audit(db)
    assert xg["unknown_effective_at"] >= 0
    assert "Phase 5" in xg["conclusion"]
    players = audit.player_temporal_audit(db)
    assert "appearances" in players and "memberships" in players


# -- upcoming readiness (controlled) ---------------------------------------------------------------------

def test_upcoming_readiness_end_to_end(db):
    from app.services.lifecycle import sync as sync_service
    from app.services.lifecycle import upcoming as upcoming_service

    league = _league(db, code="P10RDY")
    teams = _teams(db, league, ("H", "A"))
    for day in range(6):
        _match(db, league, teams,
               kickoff=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=10 - day),
               status="FINISHED", hs=2, aws=0)
    kickoff = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2)
    records = [upcoming_service.UpcomingMatch(
        league_code="P10RDY", home_team="H", away_team="A",
        kickoff_utc=kickoff.replace(tzinfo=timezone.utc),
        kickoff_source=str(kickoff), kickoff_timezone="UTC",
        status="scheduled", source="test", source_match_id="rdy-1")]
    stats = sync_service.sync_upcoming_matches(db, records)
    assert stats.inserted == 1
    from app.db.models.core import Match

    target = db.query(Match).filter_by(provider_match_id="rdy-1").one()
    verdict = eligibility.check_eligibility(db, target.id,
                                            datetime.now(timezone.utc),
                                            mode="production_strict")
    assert verdict["eligible"] is True
    assert verdict["families"]["team_form"]["freshness"]["state"] == "fresh"


# -- regression: models untouched -----------------------------------------------------------------------------

def test_phase10_model_files_untouched():
    import subprocess

    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "status", "--porcelain",
         "backend/app/services/predictions/",
         "backend/app/services/intelligence/",
         "backend/app/services/evaluation/",
         "backend/app/services/backtesting/",
         "backend/app/services/features/",
         "backend/app/services/player_intelligence/"],
        capture_output=True, text=True, cwd=repo_root)
    assert result.stdout.strip() == "", result.stdout



def test_future_injection_leaves_eligibility_unchanged(db):
    """Post-cutoff odds + future matches must not enter market freshness."""
    from app.db.models.odds import Bookmaker, OddsSnapshot

    league = _league(db, code="P10FI")
    teams = _teams(db, league, ("H", "A"))
    for day in range(6):
        _match(db, league, teams,
               kickoff=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=10 - day),
               status="FINISHED", hs=2, aws=0)
    target = _match(db, league, teams,
                    kickoff=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2))
    cutoff = datetime.now(timezone.utc)
    before = eligibility.check_eligibility(db, target.id, cutoff,
                                           mode="production_strict")
    book = Bookmaker(name="Future", provider="test", provider_bookmaker_id="F1")
    db.add(book)
    db.flush()
    db.add(OddsSnapshot(match_id=target.id, bookmaker_id=book.id,
                        market_type="h2h",
                        timestamp=cutoff + timedelta(days=1)))
    future_match = _match(db, league, teams,
                          kickoff=cutoff.replace(tzinfo=None) + timedelta(days=30),
                          status="FINISHED", hs=9, aws=9)
    _ = future_match
    after = eligibility.check_eligibility(db, target.id, cutoff,
                                          mode="production_strict")
    assert after["freshness"] == before["freshness"]
    assert after["eligible"] == before["eligible"]
