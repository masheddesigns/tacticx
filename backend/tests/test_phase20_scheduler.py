"""Phase 20 tests — production acquisition scheduler, monitoring, reliability.

Covers: scheduler config, job store, locking, due calculation, orchestrator,
executors, dry-run, monitoring, alerts, anomaly detection, dashboard, API,
CLI, idempotency, five-league operational validation, historical integrity.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.lifecycle import SourceHealth
from app.db.models.scheduler import AcquisitionJobLock, AcquisitionJobRecord

NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _league(db, code="EPL"):
    lg = League(code=code, name=f"{code} League", provider="api_football",
                provider_league_id="39", season="2024")
    db.add(lg)
    db.flush()
    return lg


def _team(db, league, name="Team A", pid="1"):
    t = Team(league_id=league.id, name=name, provider="api_football",
             provider_team_id=pid)
    db.add(t)
    db.flush()
    return t


def _match(db, league, home, away, status="SCHEDULED", hours_from_now=5):
    m = Match(league_id=league.id, home_team_id=home.id, away_team_id=away.id,
              kickoff_at=NOW + timedelta(hours=hours_from_now),
              status=status, provider="api_football",
              provider_match_id=f"m-{home.id}-{away.id}")
    db.add(m)
    db.flush()
    return m


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestSchedulerConfig:
    def test_all_job_types(self):
        from app.services.scheduler.config import ALL_JOB_TYPES, DEFAULT_JOBS
        assert len(ALL_JOB_TYPES) == 7  # Phase 26 adds pre_match_prediction
        assert "pre_match_prediction" in ALL_JOB_TYPES
        for jt in ALL_JOB_TYPES:
            assert jt in DEFAULT_JOBS

    def test_get_job_config(self):
        from app.services.scheduler.config import get_job_config
        cfg = get_job_config("fixture_refresh")
        assert cfg["enabled"] is True
        assert cfg["interval_seconds"] > 0
        assert "competitions" in cfg

    def test_get_job_config_unknown(self):
        from app.services.scheduler.config import get_job_config
        with pytest.raises(ValueError, match="unknown job type"):
            get_job_config("nonexistent")

    def test_lock_key(self):
        from app.services.scheduler.config import lock_key
        assert lock_key("fixture_refresh", "EPL") == "fixture_refresh|EPL"
        assert lock_key("fixture_refresh") == "fixture_refresh"

    def test_get_scheduler_config(self):
        from app.services.scheduler.config import get_scheduler_config
        cfg = get_scheduler_config()
        assert cfg["enabled"] is True
        assert cfg["timezone"] == "UTC"
        assert cfg["max_concurrency"] > 0


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestJobRecordModel:
    def test_create_record(self, db):
        from app.services.scheduler.store import create_record
        rec = create_record(db, job_type="fixture_refresh", competition="EPL")
        assert rec.id is not None
        assert rec.job_type == "fixture_refresh"
        assert rec.status == "queued"
        assert rec.dry_run == 0

    def test_record_dry_run_flag(self, db):
        from app.services.scheduler.store import create_record
        rec = create_record(db, job_type="source_health", dry_run=True)
        assert rec.dry_run == 1

    def test_mark_running(self, db):
        from app.services.scheduler.store import create_record, mark_running
        rec = create_record(db, job_type="fixture_refresh")
        mark_running(db, rec)
        assert rec.status == "running"
        assert rec.started_at is not None

    def test_mark_terminal(self, db):
        from app.services.scheduler.store import (
            create_record, mark_running, mark_terminal)
        rec = create_record(db, job_type="fixture_refresh")
        mark_running(db, rec)
        mark_terminal(db, rec, "succeeded", new_matches=5)
        assert rec.status == "succeeded"
        assert rec.completed_at is not None
        assert rec.duration_ms is not None
        assert rec.new_matches == 5

    def test_mark_terminal_invalid_status(self, db):
        from app.services.scheduler.store import create_record, mark_terminal
        rec = create_record(db, job_type="fixture_refresh")
        with pytest.raises(ValueError, match="not terminal"):
            mark_terminal(db, rec, "running")


# ---------------------------------------------------------------------------
# Locking tests
# ---------------------------------------------------------------------------

class TestLocking:
    def test_acquire_and_release(self, db):
        from app.services.scheduler.store import acquire_lock, release_lock
        lock = acquire_lock(db, "fixture_refresh", "EPL", ttl_seconds=60)
        assert lock is not None
        assert lock.owner
        release_lock(db, lock)
        assert db.query(AcquisitionJobLock).count() == 0

    def test_concurrent_lock_prevention(self, db):
        from app.services.scheduler.store import acquire_lock, release_lock
        lock1 = acquire_lock(db, "fixture_refresh", "EPL", ttl_seconds=60)
        assert lock1 is not None
        lock2 = acquire_lock(db, "fixture_refresh", "EPL", ttl_seconds=60)
        assert lock2 is None
        release_lock(db, lock1)

    def test_different_competition_no_conflict(self, db):
        from app.services.scheduler.store import acquire_lock, release_lock
        lock1 = acquire_lock(db, "fixture_refresh", "EPL", ttl_seconds=60)
        lock2 = acquire_lock(db, "fixture_refresh", "LA_LIGA", ttl_seconds=60)
        assert lock1 is not None
        assert lock2 is not None
        release_lock(db, lock1)
        release_lock(db, lock2)

    def test_stale_lock_reclamation(self, db):
        from app.services.scheduler.store import acquire_lock
        lock1 = acquire_lock(db, "fixture_refresh", "EPL", ttl_seconds=60)
        assert lock1 is not None
        lock1.expires_at = datetime.utcnow() - timedelta(seconds=10)
        db.commit()
        lock2 = acquire_lock(db, "fixture_refresh", "EPL", ttl_seconds=60)
        assert lock2 is not None
        assert lock2.owner != lock1.owner

    def test_release_none_safe(self, db):
        from app.services.scheduler.store import release_lock
        release_lock(db, None)


# ---------------------------------------------------------------------------
# Due calculation tests
# ---------------------------------------------------------------------------

class TestDueCalculation:
    def test_never_run_is_due(self, db):
        from app.services.scheduler.store import is_due
        assert is_due(db, "fixture_refresh", "EPL") is True

    def test_recently_completed_not_due(self, db):
        from app.services.scheduler.store import (
            create_record, mark_running, mark_terminal, is_due)
        rec = create_record(db, job_type="fixture_refresh", competition="EPL")
        mark_running(db, rec)
        mark_terminal(db, rec, "succeeded")
        assert is_due(db, "fixture_refresh", "EPL") is False

    def test_old_completion_is_due(self, db):
        from app.services.scheduler.store import (
            create_record, mark_running, mark_terminal, is_due)
        rec = create_record(db, job_type="fixture_refresh", competition="EPL")
        mark_running(db, rec)
        mark_terminal(db, rec, "succeeded")
        rec.completed_at = datetime.utcnow() - timedelta(hours=13)
        db.commit()
        assert is_due(db, "fixture_refresh", "EPL") is True

    def test_disabled_job_not_due(self, db):
        from app.services.scheduler.config import DEFAULT_JOBS
        from app.services.scheduler.store import is_due
        with patch.dict(DEFAULT_JOBS, {"fixture_refresh": {"enabled": False,
                        "interval_seconds": 100, "competitions": [],
                        "priority": 20, "lock_ttl_seconds": 60,
                        "retry_max": 1, "retry_base_seconds": 5,
                        "timeout_seconds": 30}}):
            assert is_due(db, "fixture_refresh", "EPL") is False

    def test_find_due_jobs_sorted_by_priority(self, db):
        from app.services.scheduler.store import find_due_jobs
        due = find_due_jobs(db)
        assert isinstance(due, list)
        priorities = [d["priority"] for d in due]
        assert priorities == sorted(priorities)


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------

class TestOrchestrator:
    def test_run_job_dry_run(self, db):
        from app.services.scheduler.orchestrator import run_job
        result = run_job(db, "fixture_refresh", competition="EPL",
                         dry_run=True, force=True)
        assert result["status"] == "succeeded"
        assert result["dry_run"] is True

    def test_run_job_lock_skip(self, db):
        from app.services.scheduler.store import acquire_lock
        from app.services.scheduler.orchestrator import run_job
        lock = acquire_lock(db, "fixture_refresh", "EPL", ttl_seconds=60)
        result = run_job(db, "fixture_refresh", competition="EPL",
                         force=False)
        assert result["status"] == "skipped"
        assert result["error_code"] == "lock_held"
        from app.services.scheduler.store import release_lock
        release_lock(db, lock)

    def test_run_job_force_skips_lock(self, db):
        from app.services.scheduler.store import acquire_lock
        from app.services.scheduler.orchestrator import run_job
        lock = acquire_lock(db, "fixture_refresh", "EPL", ttl_seconds=60)
        result = run_job(db, "fixture_refresh", competition="EPL",
                         dry_run=True, force=True)
        assert result["status"] == "succeeded"
        from app.services.scheduler.store import release_lock
        release_lock(db, lock)

    def test_run_job_records_exception(self, db):
        from app.services.scheduler.orchestrator import run_job
        from app.services.scheduler.executors import EXECUTORS
        def failing_executor(db, config, dry_run=False):
            raise RuntimeError("test failure")
        with patch.dict(EXECUTORS, {"source_health": failing_executor}):
            with pytest.raises(RuntimeError, match="test failure"):
                run_job(db, "source_health", force=True)

    def test_run_job_manual(self, db):
        from app.services.scheduler.orchestrator import run_job_manual
        result = run_job_manual(db, "freshness_audit", dry_run=True)
        assert result["status"] == "succeeded"
        assert result["trigger"] == "manual"


# ---------------------------------------------------------------------------
# Executor tests
# ---------------------------------------------------------------------------

class TestExecutors:
    def test_fixture_refresh_dry_run(self, db):
        from app.services.scheduler.executors import execute_fixture_refresh
        result = execute_fixture_refresh(db, {"competitions": ["EPL"],
                                               "seasons": ["current"]},
                                         dry_run=True)
        assert result["status"] == "dry_run"
        assert "note" in result

    def test_status_refresh_dry_run(self, db):
        from app.services.scheduler.executors import execute_status_refresh
        lg = _league(db)
        home = _team(db, lg, "Team A", "1")
        away = _team(db, lg, "Team B", "2")
        _match(db, lg, home, away)
        result = execute_status_refresh(db, {"competitions": ["EPL"],
                                              "seasons": ["current"]},
                                        dry_run=True)
        assert result["status"] == "dry_run"
        assert result["matches_found"] >= 1

    def test_result_refresh_dry_run(self, db):
        from app.services.scheduler.executors import execute_result_refresh
        lg = _league(db)
        home = _team(db, lg, "Team A", "1")
        away = _team(db, lg, "Team B", "2")
        _match(db, lg, home, away, status="FINISHED", hours_from_now=-5)
        result = execute_result_refresh(db, {"competitions": ["EPL"]},
                                        dry_run=True)
        assert result["status"] == "dry_run"
        assert result["finished_count"] >= 1

    def test_health_check_dry_run(self, db):
        from app.services.scheduler.executors import execute_health_check
        result = execute_health_check(db, {"sources": ["api_football"]},
                                      dry_run=True)
        assert result["status"] == "dry_run"
        assert "api_football" in result["results"]

    def test_freshness_audit_dry_run(self, db):
        from app.services.scheduler.executors import execute_freshness_audit
        _league(db)
        result = execute_freshness_audit(db, {}, dry_run=True)
        assert result["status"] == "dry_run"
        assert "audit" in result

    def test_qualification_dry_run(self, db):
        from app.services.scheduler.executors import execute_qualification
        result = execute_qualification(db, {"sources": ["api_football"]},
                                       dry_run=True)
        assert result["status"] == "dry_run"
        assert "results" in result


# ---------------------------------------------------------------------------
# Monitoring tests
# ---------------------------------------------------------------------------

class TestMonitoring:
    def test_no_qualified_source_alert(self, db):
        from app.services.scheduler.monitoring import check_alerts
        alerts = check_alerts(db)
        assert isinstance(alerts, list)
        unqualified = [a for a in alerts
                       if a["condition"] == "no_qualified_source"]
        assert len(unqualified) >= 1

    def test_provider_unavailable_alert(self, db):
        from app.services.scheduler.monitoring import check_alerts
        sh = SourceHealth(source="test_src", state="unavailable",
                          consecutive_failures=5)
        db.add(sh)
        db.commit()
        alerts = check_alerts(db)
        unavail = [a for a in alerts
                   if a["condition"] == "provider_unavailable"
                   and a["source"] == "test_src"]
        assert len(unavail) == 1

    def test_repeated_failures_alert(self, db):
        from app.services.scheduler.monitoring import check_alerts
        sh = SourceHealth(source="fail_src", state="degraded",
                          consecutive_failures=5)
        db.add(sh)
        db.commit()
        alerts = check_alerts(db)
        repeated = [a for a in alerts
                    if a["condition"] == "repeated_failures"
                    and a["source"] == "fail_src"]
        assert len(repeated) == 1

    def test_zero_fixtures_alert(self, db):
        from app.services.scheduler.monitoring import check_alerts
        _league(db)
        alerts = check_alerts(db)
        zero = [a for a in alerts
                if a["condition"] == "unexpected_zero_fixtures"
                and a["competition"] == "EPL"]
        assert len(zero) == 1

    def test_anomalies_empty_db(self, db):
        from app.services.scheduler.monitoring import detect_anomalies
        anomalies = detect_anomalies(db)
        assert isinstance(anomalies, list)

    def test_impossible_status_transition(self, db):
        from app.db.models.freshness import MatchObservation
        from app.services.scheduler.monitoring import detect_anomalies
        lg = _league(db)
        home = _team(db, lg, "A", "1")
        away = _team(db, lg, "B", "2")
        m = _match(db, lg, home, away, status="FINISHED")
        obs = MatchObservation(
            match_id=m.id, source="test",
            raw_reference="test:1", field="status",
            previous_value="FINISHED", new_value="SCHEDULED",
            effective_at=NOW)
        db.add(obs)
        db.commit()
        anomalies = detect_anomalies(db)
        bad = [a for a in anomalies
               if a["type"] == "impossible_status_transition"]
        assert len(bad) == 1

    def test_operational_summary(self, db):
        from app.services.scheduler.monitoring import operational_summary
        summary = operational_summary(db)
        assert "alerts" in summary
        assert "anomalies" in summary
        assert "recent_job_status_distribution" in summary
        assert "active_locks" in summary


# ---------------------------------------------------------------------------
# Dashboard tests
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_scheduler_status(self, db):
        from app.services.scheduler.dashboard import scheduler_status
        status = scheduler_status(db)
        assert "as_of" in status
        assert "sources" in status
        assert "jobs" in status
        assert "competitions" in status
        assert "locks" in status
        assert "recent_runs" in status

    def test_source_summaries(self, db):
        from app.services.scheduler.dashboard import scheduler_status
        status = scheduler_status(db)
        sources = status["sources"]
        assert "api_football" in sources
        assert "qualification" in sources["api_football"]

    def test_job_summaries(self, db):
        from app.services.scheduler.dashboard import scheduler_status
        status = scheduler_status(db)
        jobs = status["jobs"]
        assert "fixture_refresh" in jobs
        assert "status_refresh" in jobs
        assert jobs["fixture_refresh"]["enabled"] is True

    def test_competition_summaries(self, db):
        from app.services.scheduler.dashboard import scheduler_status
        _league(db)
        status = scheduler_status(db)
        comps = status["competitions"]
        assert "EPL" in comps
        assert comps["EPL"]["fixture_count"] == 0


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class TestJobsAPI:
    def test_list_jobs(self, client):
        resp = client.get("/api/v1/jobs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_job_not_found(self, client):
        resp = client.get("/api/v1/jobs/99999")
        assert resp.status_code == 404

    def test_list_due_jobs(self, client):
        resp = client.get("/api/v1/jobs/due")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_alerts(self, client):
        resp = client.get("/api/v1/jobs/alerts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_anomalies(self, client):
        resp = client.get("/api/v1/jobs/anomalies")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_dashboard(self, client):
        resp = client.get("/api/v1/jobs/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert "jobs" in data

    def test_cleanup_locks(self, client):
        resp = client.post("/api/v1/jobs/locks/cleanup")
        assert resp.status_code == 200
        assert "cleaned" in resp.json()

    def test_run_job_invalid_type(self, client):
        resp = client.post("/api/v1/jobs/nonexistent/run")
        assert resp.status_code == 400

    def test_run_job_dry_run(self, client):
        resp = client.post("/api/v1/jobs/fixture_refresh/run?dry_run=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "succeeded"
        assert data["dry_run"] is True


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestCLI:
    def test_jobs_status(self, db):
        from app.services.scheduler.orchestrator import run_job
        run_job(db, "fixture_refresh", dry_run=True, force=True)
        import scripts.tacticx as cli
        import argparse
        args = argparse.Namespace(action="status", job_type=None,
                                  competition="", season="", source="",
                                  dry_run=False, as_json=False)
        result = cli._cmd_jobs(db, args)
        assert result == 0

    def test_jobs_list(self, db):
        from app.services.scheduler.orchestrator import run_job
        run_job(db, "fixture_refresh", dry_run=True, force=True)
        import scripts.tacticx as cli
        import argparse
        args = argparse.Namespace(action="list", job_type=None,
                                  competition="", season="", source="",
                                  dry_run=False, as_json=False)
        result = cli._cmd_jobs(db, args)
        assert result == 0

    def test_jobs_list_json(self, db):
        import scripts.tacticx as cli
        import argparse
        args = argparse.Namespace(action="list", job_type=None,
                                  competition="", season="", source="",
                                  dry_run=False, as_json=True)
        result = cli._cmd_jobs(db, args)
        assert result == 0

    def test_jobs_run_dry(self, db):
        import scripts.tacticx as cli
        import argparse
        args = argparse.Namespace(action="run", job_type="fixture_refresh",
                                  competition="EPL", season="",
                                  source="", dry_run=True, as_json=False)
        result = cli._cmd_jobs(db, args)
        assert result == 0

    def test_jobs_run_unknown_type(self, db):
        import scripts.tacticx as cli
        import argparse
        args = argparse.Namespace(action="run", job_type="nonexistent",
                                  competition="", season="",
                                  source="", dry_run=False, as_json=False)
        result = cli._cmd_jobs(db, args)
        assert result == 1

    def test_jobs_run_due(self, db):
        import scripts.tacticx as cli
        import argparse
        args = argparse.Namespace(action="run-due", job_type=None,
                                  competition="", season="",
                                  source="", dry_run=True, as_json=False)
        result = cli._cmd_jobs(db, args)
        assert result == 0

    def test_jobs_alerts(self, db):
        import scripts.tacticx as cli
        import argparse
        args = argparse.Namespace(action="alerts", job_type=None,
                                  competition="", season="",
                                  source="", dry_run=False, as_json=False)
        result = cli._cmd_jobs(db, args)
        assert result == 0

    def test_jobs_anomalies(self, db):
        import scripts.tacticx as cli
        import argparse
        args = argparse.Namespace(action="anomalies", job_type=None,
                                  competition="", season="",
                                  source="", dry_run=False, as_json=False)
        result = cli._cmd_jobs(db, args)
        assert result == 0

    def test_jobs_dashboard(self, db):
        import scripts.tacticx as cli
        import argparse
        args = argparse.Namespace(action="dashboard", job_type=None,
                                  competition="", season="",
                                  source="", dry_run=False, as_json=False)
        result = cli._cmd_jobs(db, args)
        assert result == 0


# ---------------------------------------------------------------------------
# Idempotency tests
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_repeated_dry_runs_no_side_effects(self, db):
        from app.services.scheduler.orchestrator import run_job
        r1 = run_job(db, "fixture_refresh", dry_run=True, force=True)
        r2 = run_job(db, "fixture_refresh", dry_run=True, force=True)
        assert r1["status"] == "succeeded"
        assert r2["status"] == "succeeded"
        assert db.query(AcquisitionJobRecord).count() == 2

    def test_lock_release_on_exception(self, db):
        from app.services.scheduler.orchestrator import run_job
        from app.services.scheduler.executors import EXECUTORS
        def fail_once(db, config, dry_run=False):
            raise RuntimeError("boom")
        with patch.dict(EXECUTORS, {"source_health": fail_once}):
            with pytest.raises(RuntimeError):
                run_job(db, "source_health", force=True)
        assert db.query(AcquisitionJobLock).count() == 0


# ---------------------------------------------------------------------------
# Five-league operational validation (mock mode)
# ---------------------------------------------------------------------------

class TestFiveLeagueValidation:
    LEAGUES = ["EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1"]

    def test_five_league_fixture_refresh_dry_run(self, db):
        from app.services.scheduler.orchestrator import run_job
        for league in self.LEAGUES:
            result = run_job(db, "fixture_refresh", competition=league,
                             dry_run=True, force=True)
            assert result["status"] == "succeeded"
            assert result["dry_run"] is True

    def test_five_league_status_refresh_dry_run(self, db):
        from app.services.scheduler.orchestrator import run_job
        for league in self.LEAGUES:
            result = run_job(db, "status_refresh", competition=league,
                             dry_run=True, force=True)
            assert result["status"] == "succeeded"

    def test_five_league_health_check(self, db):
        from app.services.scheduler.orchestrator import run_job
        result = run_job(db, "source_health", dry_run=True, force=True)
        assert result["status"] == "succeeded"

    def test_five_league_freshness_audit(self, db):
        from app.services.scheduler.orchestrator import run_job
        for league in self.LEAGUES:
            _league(db, league)
        result = run_job(db, "freshness_audit", dry_run=True, force=True)
        assert result["status"] == "succeeded"

    def test_five_league_qualification(self, db):
        from app.services.scheduler.orchestrator import run_job
        result = run_job(db, "qualification", dry_run=True, force=True)
        assert result["status"] == "succeeded"

    def test_status_transitions(self, db):
        from app.db.models.freshness import MatchObservation
        from app.services.scheduler.monitoring import detect_anomalies
        lg = _league(db)
        home = _team(db, lg, "A", "1")
        away = _team(db, lg, "B", "2")
        m = _match(db, lg, home, away, status="LIVE")
        obs1 = MatchObservation(
            match_id=m.id, source="test", raw_reference="test:1",
            field="status", previous_value="SCHEDULED", new_value="LIVE",
            effective_at=NOW)
        obs2 = MatchObservation(
            match_id=m.id, source="test", raw_reference="test:2",
            field="status", previous_value="LIVE", new_value="FINISHED",
            effective_at=NOW + timedelta(hours=2))
        db.add_all([obs1, obs2])
        db.commit()
        anomalies = detect_anomalies(db)
        impossible = [a for a in anomalies
                      if a["type"] == "impossible_status_transition"]
        assert len(impossible) == 0


# ---------------------------------------------------------------------------
# Historical integrity tests
# ---------------------------------------------------------------------------

class TestHistoricalIntegrity:
    def test_prediction_code_paths_unmodified(self):
        import app.services.scheduler.config as sched_cfg
        import app.services.scheduler.store as sched_store
        import app.services.scheduler.orchestrator as sched_orch
        import app.services.scheduler.executors as sched_exec
        sched_modules = [sched_cfg, sched_store, sched_orch, sched_exec]
        for mod in sched_modules:
            source = open(mod.__file__).read()
            assert "PredictionComposer" not in source
            assert "train_logreg" not in source
            assert "generate_version" not in source
            assert "fit_temperature" not in source

    def test_no_prediction_imports_in_scheduler(self):
        import importlib
        import app.services.scheduler
        for name in dir(app.services.scheduler):
            mod = getattr(app.services.scheduler, name)
            if hasattr(mod, "__module__") and mod.__module__:
                assert "prediction" not in mod.__module__.lower()
                assert "training" not in mod.__module__.lower()
