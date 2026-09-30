"""Phase 11 tests: universe, acquisition, activation, snapshot, readiness,
boundaries, idempotency. No live network calls."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.acquisition import AcquisitionRun, SourceActivation
from app.db.models.core import League, Match, Team
from app.db.models.freshness import MatchObservation
from app.services.acquisition import activation, snapshot, universe, workflow
from app.services.freshness import fixtures as fixture_svc
from app.services.lifecycle import sync as sync_service
from app.services.lifecycle import upcoming as upcoming_service

BASE = datetime(2024, 9, 1, 12, 0)


def _league(db, code="P11"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p11", season="2024")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for name in names:
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=f"p11-{league.code}-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _names(teams):
    return list(teams)


_COUNTER = {"n": 0}


def _match(db, league, teams, kickoff=None, status="SCHEDULED", hs=None, aws=None):
    names = list(teams)
    _COUNTER["n"] += 1
    match = Match(
        league_id=league.id, home_team_id=teams[names[0]].id,
        away_team_id=teams[names[1]].id,
        kickoff_at=kickoff or BASE, status=status, home_score=hs, away_score=aws,
        provider="test",
        provider_match_id=f"p11-{kickoff}-{_COUNTER['n']}")
    db.add(match)
    db.commit()
    return match


def _rec(home, away, kickoff, league="P11", status="scheduled", source="src",
         sid="s1"):
    return upcoming_service.UpcomingMatch(
        league_code=league, home_team=home, away_team=away,
        kickoff_utc=kickoff, kickoff_source=str(kickoff), kickoff_timezone="UTC",
        status=status, source=source, source_match_id=sid)


# -- universe --------------------------------------------------------------------

def test_universe_entry_and_lifecycle(db):
    league = _league(db)
    teams = _teams(db, league, ("H", "A"))
    match = _match(db, league, teams)
    fixture_svc.observe_fixture(db, match.id, "src", {"status": "SCHEDULED"})
    fixture_svc.observe_fixture(db, match.id, "src",
                                {"kickoff_at": BASE + timedelta(hours=1)})
    fixture_svc.observe_fixture(db, match.id, "src",
                                {"kickoff_at": BASE + timedelta(hours=2)})
    entry = universe.entry(db, match)
    assert entry["lifecycle"] == "rescheduled"
    assert entry["competition"] == "P11"
    assert entry["confidence"]["level"] in ("high", "medium", "low", "unresolved")
    assert entry["source_count"] >= 1
    listed = universe.universe(db, league_code="P11")
    assert listed["n"] == 1 and "agreement" in listed


def test_lifecycle_finished_and_unknown(db):
    league = _league(db, code="P11L")
    teams = _teams(db, league, ("H", "A"))
    finished = _match(db, league, teams, status="FINISHED", hs=1, aws=0)
    assert universe.lifecycle_of(db, finished)["lifecycle"] == "finished"
    naked = Match(league_id=league.id, status="")
    db.add(naked)
    db.commit()
    assert universe.lifecycle_of(db, naked)["lifecycle"] == "unknown"


# -- acquisition workflow ----------------------------------------------------------

def test_acquisition_success_and_idempotency(db):
    league = _league(db, code="P11A")
    _teams(db, league, ("H", "A"))
    kickoff = datetime.now(timezone.utc) + timedelta(days=2)
    records = [_rec("H", "A", kickoff, league="P11A")]
    first = workflow.run_acquisition(db, "src", records, job="fixture_discovery",
                                     requested_scope={"league": "P11A"})
    assert first["status"] == "success" and first["created"] == 1
    second = workflow.run_acquisition(db, "src", records, job="fixture_discovery",
                                      requested_scope={"league": "P11A"})
    assert second["created"] == 0
    assert second["content_hash"] == first["content_hash"]
    runs = db.query(AcquisitionRun).filter_by(source="src").all()
    assert len(runs) == 2 and all(r.status == "success" for r in runs)


def test_acquisition_partial_and_empty(db):
    _league(db, code="P11P")
    result = workflow.run_acquisition(db, "src", [], job="fixture_discovery")
    assert result["status"] == "empty"
    assert result["classification"] == "provider_empty"

    class Boom(Exception):
        status = 429

    failed = workflow.run_acquisition(db, "src", [], job="x",
                                      failure=Boom("slow down"))
    assert failed["classification"] == "rate_limited"

    class Denied(Exception):
        status = 401

    denied = workflow.run_acquisition(db, "src", [], job="x",
                                      failure=Denied("nope"))
    assert denied["classification"] == "authentication_failure"

    class Server(Exception):
        status = 503

    assert workflow.classify_failure(Server("down")) == "temporary_failure"
    assert workflow.classify_failure(TimeoutError("t")) == "temporary_failure"
    assert workflow.classify_failure(ValueError("schema changed")) == \
        "provider_schema_error"


def test_kickoff_change_preserves_history(db):
    league = _league(db, code="P11K")
    teams = _teams(db, league, ("H", "A"))
    match = _match(db, league, teams)
    fixture_svc.observe_fixture(db, match.id, "src", {"kickoff_at": BASE})
    fixture_svc.observe_fixture(db, match.id, "src",
                                {"kickoff_at": BASE + timedelta(hours=1, minutes=30)})
    fixture_svc.observe_fixture(db, match.id, "src",
                                {"kickoff_at": BASE + timedelta(hours=2)})
    history = fixture_svc.observation_history(db, match.id, field="kickoff_at")
    assert [r["new_value"] for r in history] == [
        str(BASE + timedelta(hours=1, minutes=30)),
        str(BASE + timedelta(hours=2))]
    assert history[0]["previous_value"] == str(BASE)
    assert universe.lifecycle_of(db, match)["lifecycle"] == "rescheduled"


# -- activation + scheduler + enrichment ----------------------------------------------

def test_activation_gate_blocks_and_records(db):
    evidence = {check: (True, "ok") for check in activation.GATE_CHECKS}
    result = activation.activation_gate(db, "good_src", evidence)
    assert result["state"] == "active" and result["failures"] == []
    bad = dict(evidence)
    bad["idempotency"] = (False, "duplicates found")
    result2 = activation.activation_gate(db, "bad_src", bad)
    assert result2["state"] == "candidate"
    assert result2["failures"] == ["idempotency"]
    assert activation.current_state(db, "good_src") == "active"
    assert activation.current_state(db, "never_seen") == "candidate"
    moved = activation.set_state(db, "bad_src", "disabled", reason="manual")
    assert moved["state"] == "disabled"
    with pytest.raises(ValueError):
        activation.set_state(db, "bad_src", "nope")


def test_scheduler_jobs_registered(db):
    jobs = activation.ensure_jobs(db)
    assert {job["name"] for job in jobs} == {"fixture_discovery", "fixture_refresh",
                                            "completed_match_refresh",
                                            "historical_backfill"}
    activation.mark_job_run(db, "fixture_discovery")
    jobs2 = activation.ensure_jobs(db)
    assert next(job for job in jobs2 if job["name"] == "fixture_discovery")[
        "last_run"] is not None


def test_enrichment_capability_checked(db):
    league = _league(db, code="P11EN")
    teams = _teams(db, league, ("H", "A"))
    match = _match(db, league, teams, status="FINISHED", hs=1, aws=0)
    result = activation.enrichment_request(db, match.id, "odds_api",
                                           ["result", "xg"])
    assert result["granted"] == [] and len(result["skipped"]) == 2
    result2 = activation.enrichment_request(db, match.id, "api_football",
                                            ["result", "xg"])
    assert [g["kind"] for g in result2["granted"]] == ["result"]
    assert result2["granted"][0]["quality"] == "unknown"


# -- snapshot + readiness + boundaries -----------------------------------------------------

def test_production_snapshot_deterministic(db):
    league = _league(db, code="P11SN")
    teams = _teams(db, league, ("H", "A"))
    first = _match(db, league, teams)
    second = _match(db, league, teams)
    snap = snapshot.production_snapshot(db, [first.id, second.id])
    assert snap["snapshot_id"].startswith("universe_")
    again = snapshot.production_snapshot(db, [second.id, first.id])
    assert again["hash"] == snap["hash"]
    assert snap["match_count"] == 2


def test_dataset_boundaries_labeled():
    assert snapshot.dataset_boundary(datetime(2023, 6, 1)) == "historical"
    assert snapshot.dataset_boundary(datetime(2024, 6, 1)) == "validation"
    assert snapshot.dataset_boundary(datetime(2025, 6, 1)) == "test"
    assert snapshot.dataset_boundary(
        datetime.now(timezone.utc) + timedelta(days=30)) == "production"
    assert snapshot.dataset_boundary(None) == "unknown"


def test_readiness_report_shape(db):
    league = _league(db, code="P11RD")
    teams = _teams(db, league, ("H", "A"))
    match = _match(db, league, teams,
                   kickoff=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2))
    report = snapshot.readiness_report(db, match.id)
    assert report["prediction"] in ("ELIGIBLE", "INELIGIBLE")
    assert report["mode"] in ("FULL", "DEGRADED")
    assert "No betting" not in str(report)  # no recommendation language
    assert snapshot.readiness_report(db, 999999).get("error") == "match missing"


# -- data boundary adversarial ---------------------------------------------------------------

def test_future_fixture_leaves_backtest_scope_unchanged(db):
    from app.services.backtesting.runner import scope_matches

    league = _league(db, code="P11B")
    teams = _teams(db, league, ("H", "A"))
    past = _match(db, league, teams,
                  kickoff=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=10),
                  status="FINISHED", hs=1, aws=0)
    before = [m.id for m in scope_matches(db, league_code="P11B")]
    assert before == [past.id]
    future = _match(db, league, teams,
                    kickoff=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=10))
    after = [m.id for m in scope_matches(db, league_code="P11B")]
    assert after == before and future.id not in after


def test_kickoff_update_preserves_history(db):
    league = _league(db, code="P11KH")
    teams = _teams(db, league, ("H", "A"))
    match = _match(db, league, teams)
    fixture_svc.observe_fixture(db, match.id, "src", {"kickoff_at": BASE})
    fixture_svc.observe_fixture(db, match.id, "src",
                                {"kickoff_at": BASE + timedelta(hours=2)})
    history = fixture_svc.observation_history(db, match.id, field="kickoff_at")
    assert [r["new_value"] for r in history] == [
        str(BASE + timedelta(hours=2))]
    assert history[0]["previous_value"] == str(BASE)


def test_source_removal_keeps_canonical(db):
    league = _league(db, code="P11SR")
    teams = _teams(db, league, ("H", "A"))
    match = _match(db, league, teams)
    fixture_svc.observe_fixture(db, match.id, "dying_source", {"status": "SCHEDULED"})
    db.query(MatchObservation).filter_by(source="dying_source").delete()
    db.commit()
    assert db.get(Match, match.id) is not None
    assert universe.entry(db, db.get(Match, match.id))["match_id"] == match.id


def test_event_injection_leaves_snapshot_unchanged(db):
    from app.db.models.core import MatchEvent
    from app.services.player_intelligence import feature_snapshot
    from app.services.features.temporal import TemporalMode

    league = _league(db, code="P11EV")
    teams = _teams(db, league, ("H", "A"))
    for day in range(3):
        _match(db, league, teams,
               kickoff=datetime(2024, 8, 1 + day), status="FINISHED", hs=1, aws=0)
    target = _match(db, league, teams, kickoff=datetime(2024, 8, 20))
    before = feature_snapshot.build_snapshot(db, target.id, target.kickoff_at,
                                             TemporalMode.STRICT_PREMATCH,
                                             persist=False)
    db.add(MatchEvent(match_id=target.id, minute=10, event_type="goal",
                      team="home", player_name="X", provider="t",
                      provider_event_id="t-1", source="t"))
    db.commit()
    after = feature_snapshot.build_snapshot(db, target.id, target.kickoff_at,
                                            TemporalMode.STRICT_PREMATCH,
                                            persist=False)
    assert after["payload_hash"] == before["payload_hash"]


# -- regression: models untouched ------------------------------------------------------------------

def test_phase11_model_files_untouched():
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

