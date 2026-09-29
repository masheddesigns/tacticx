"""Phase 36 — continuous real-world observation soak tests.

Focused tests only for Phase 36 functionality: the system-status DB
fix, no-eligible-fixture behavior, exclusion accounting, restart
recovery at the loop level, migration integrity, golden regression.
All fixtures synthetic and isolated to test DBs; production paths
untouched. Live provider/Docker checks are operational, not unit tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, Team
from app.services.observation import observation_summary


def _league(db, code):
    lg = League(code=code, name=f"{code} league", provider="t",
                provider_league_id=f"p36-{code}", season="2024")
    db.add(lg)
    db.commit()
    return lg


# -- system status DB fix -------------------------------------------------------------------------------------

class TestSystemStatus:
    def test_reachable_despite_unstamped_db(self, db):
        import scripts.tacticx as cli
        import argparse

        args = argparse.Namespace(action="status", as_json=True)
        assert cli._cmd_system(db, args) == 0

    def test_migration_key_present(self, client):
        body = client.get("/health/ready").json()
        assert body["checks"]["database"] == "ok"
        assert "migrations" in body["checks"]


# -- no-fixture behavior --------------------------------------------------------------------------------------------

class TestNoEligibleMatches:
    def test_empty_shadow_scan(self, db):
        from app.services.shadow_execution import find_eligible_matches

        scan = find_eligible_matches(db)
        assert scan["state"] == "NO_ELIGIBLE_MATCHES"
        assert scan["eligible"] == []

    def test_empty_observation_summary(self, db):
        summary = observation_summary(db)
        assert summary["discovered"] == 0
        assert summary["paired"] == 0
        assert summary["exclusions"] == {}

    def test_scheduler_skips_without_challenger(self, db):
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import JOB_SHADOW_PREDICTION
        from app.services.scheduler.executors import get_executor

        cfg = get_job_config(JOB_SHADOW_PREDICTION)
        result = get_executor(JOB_SHADOW_PREDICTION)(db, cfg, dry_run=True)
        assert result["status"] == "skipped"

    def test_evidence_no_data(self, client):
        body = client.get("/api/v1/evidence/status").json()
        assert body["state"] == "NO_DATA"
        assert body["synthetic_observations"] == 0


# -- exclusion accounting -----------------------------------------------------------------------------------------------

class TestExclusions:
    def test_finished_without_readiness(self, db):
        league = _league(db, "P36E")
        home = Team(league_id=league.id, name="H", provider="t",
                    provider_team_id="p36-P36E-h")
        away = Team(league_id=league.id, name="A", provider="t",
                    provider_team_id="p36-P36E-a")
        db.add_all([home, away])
        db.commit()
        now = datetime.now(timezone.utc)
        db.add(Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now - timedelta(days=1), status="FINISHED",
            home_score=1, away_score=0, provider="t",
            provider_match_id="p36-P36E-m1"))
        db.commit()
        summary = observation_summary(db, competition="P36E")
        assert summary["discovered"] == 1
        assert summary["finished"] == 1
        assert summary["paired"] == 0
        assert summary["exclusions"].get("NO_READINESS", 0) == 1


# -- restart recovery at loop level ------------------------------------------------------------------------------------------

class TestLoopRestart:
    def test_repeated_run_due_stable(self, db):
        from app.services.scheduler import run_due

        first = run_due(db, dry_run=True)
        second = run_due(db, dry_run=True)
        assert isinstance(first, list) and isinstance(second, list)

    def test_abandoned_lock_recoverable(self, db):
        import time

        from app.services.scheduler.store import (
            acquire_lock,
            cleanup_expired_locks,
            release_lock,
        )

        assert acquire_lock(db, "source_health", ttl_seconds=1) is not None
        time.sleep(1.2)
        assert cleanup_expired_locks(db) >= 1
        lock = acquire_lock(db, "source_health", ttl_seconds=60)
        assert lock is not None
        release_lock(db, lock)
        from app.services.scheduler import run_due

        assert isinstance(run_due(db, dry_run=True), list)


# -- migration integrity ----------------------------------------------------------------------------------------------------------------

class TestMigrationIntegrity:
    def test_single_head_0017(self):
        import importlib.util
        from pathlib import Path

        mig_dir = Path(__file__).parent.parent / "migrations" / "versions"
        revisions = {}
        for mf in mig_dir.glob("*.py"):
            if mf.name == "__init__.py":
                continue
            spec = importlib.util.spec_from_file_location(mf.stem, str(mf))
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                if getattr(mod, "revision", None):
                    revisions[mod.revision] = mod.down_revision
            except Exception:
                pass
        down_revs = {v for v in revisions.values() if v is not None}
        heads = [r for r in revisions if r not in down_revs]
        assert heads == ["0017_candidate_validation"]


# -- golden regression -----------------------------------------------------------------------------------------------------------------------

class TestGoldenRegression:
    def test_ensemble_values_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P36GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"
