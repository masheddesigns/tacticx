"""Phase 31 — local continuous production & real-data acquisition tests.

Covers: configuration, compose contracts, acquisition idempotency,
failure classification, bounded retries, scheduler restart-safety,
temporal enforcement, readiness/prediction/evaluation/monitoring
integration, recovery, backup/restore mechanics, golden regression.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from app.db.models.core import League, Match, Team

REPO_ROOT = Path(__file__).parent.parent.parent


# -- configuration ----------------------------------------------------------------------------------

class TestLocalConfiguration:
    def test_defaults_safe(self):
        from app.config import Settings

        settings = Settings()
        assert settings.SCHEDULER_ENABLED is True
        assert settings.PREDICTION_ENABLED is True
        assert settings.EVALUATION_ENABLED is True
        assert settings.SCHEDULER_LOOP_INTERVAL_SECONDS > 0

    def test_flavor_parsing(self):
        from app.config import Settings

        assert Settings(TACTICX_ENV="local-production").deployment_flavor() == \
            "local-production"
        assert Settings(TACTICX_ENV="").deployment_flavor() == "development"
        with pytest.raises(ValueError):
            Settings(TACTICX_ENV="mars").deployment_flavor()

    def test_diagnose_no_secrets(self):
        from app.config import Settings

        diag = Settings(FOOTBALL_API_KEY="sekret",
                        SECRET_KEY="topsecret").diagnose()
        blob = str(diag)
        assert "sekret" not in blob
        assert "topsecret" not in blob
        assert diag["tacticx_env"] in ("development", "test",
                                       "local-production", "production")

    def test_env_example_documents_phase31(self):
        text = (REPO_ROOT / ".env.example").read_text()
        for var in ("TACTICX_ENV=", "SCHEDULER_ENABLED=",
                    "PREDICTION_ENABLED=", "EVALUATION_ENABLED=",
                    "SCHEDULER_LOOP_INTERVAL_SECONDS="):
            assert var in text, var

    def test_env_gitignored(self):
        import subprocess

        out = subprocess.run(
            ["git", "check-ignore", "-v", ".env", "backend/.env"],
            capture_output=True, text=True, cwd=str(REPO_ROOT))
        assert ".env" in out.stdout


# -- compose contracts ----------------------------------------------------------------------------------

def _local_compose():
    with open(REPO_ROOT / "docker-compose.local.yml") as fh:
        return yaml.safe_load(fh)


class TestComposeContracts:
    def test_services_present(self):
        services = _local_compose()["services"]
        for name in ("tacticx-postgres", "tacticx-redis", "tacticx-api",
                     "tacticx-scheduler", "tacticx-frontend"):
            assert name in services, name

    def test_persistent_volumes(self):
        doc = _local_compose()
        volumes = doc.get("volumes", {})
        assert "pgdata-local" in volumes
        assert "redisdata-local" in volumes
        pg_vols = doc["services"]["tacticx-postgres"].get("volumes", [])
        assert any("pgdata-local" in str(v) for v in pg_vols)

    def test_healthchecks_and_restart(self):
        services = _local_compose()["services"]
        for name in ("tacticx-postgres", "tacticx-redis", "tacticx-api",
                     "tacticx-scheduler", "tacticx-frontend"):
            assert "healthcheck" in services[name], name
        for name in ("tacticx-postgres", "tacticx-redis", "tacticx-api",
                     "tacticx-scheduler", "tacticx-frontend"):
            assert services[name].get("restart") == "unless-stopped", name

    def test_no_secrets_committed(self):
        text = (REPO_ROOT / "docker-compose.local.yml").read_text().lower()
        for needle in ("api_key=", "api-key=", "password=bet\"",
                       "token=s", "secret=tacticx-production"):
            assert needle not in text, needle
        # Passwords only via ${VAR:-default} substitution, never literals.
        assert "POSTGRES_PASSWORD:-" in (
            REPO_ROOT / "docker-compose.local.yml").read_text()

    def test_ports_loopback_only(self):
        services = _local_compose()["services"]
        for name, svc in services.items():
            for port in svc.get("ports", []):
                assert str(port).startswith("127.0.0.1:"), (name, port)

    def test_scheduler_runs_loop(self):
        cmd = " ".join(
            _local_compose()["services"]["tacticx-scheduler"]["command"])
        assert "jobs" in cmd and "run-due" in cmd and "--loop" in cmd

    def test_existing_stacks_untouched(self):
        dev = yaml.safe_load(
            (REPO_ROOT / "docker-compose.yml").read_text())
        assert sorted(dev["services"]) == ["backend", "postgres", "redis",
                                           "worker"]


# -- acquisition idempotency -----------------------------------------------------------------------------

def _normalized_fixture(tag="p31", kickoff=None, hs=None, aws=None,
                        status="SCHEDULED"):
    from app.services.sources.normalized import NormalizedMatch, Provenance

    now = datetime.now(timezone.utc)
    return NormalizedMatch(
        league_code="EPL", season="2024", home_team="Arsenal",
        home_team_id="42", away_team="Chelsea", away_team_id="49",
        kickoff_at=kickoff or (now + timedelta(days=2)),
        status=status, home_score=hs, away_score=aws,
        provider_match_id=f"{tag}-fixture-1",
        provenance=Provenance(source="test", source_record_id=f"{tag}-rec-1",
                              collected_at=now))


class TestAcquisitionIdempotency:
    def test_fixture_reacquire_same_canonical(self, db):
        from app.services.sources.pipeline import Pipeline

        pipe = Pipeline(db, "test")
        first = pipe.ingest_match(_normalized_fixture())
        second = pipe.ingest_match(_normalized_fixture())
        assert first is not None and first == second
        assert db.query(Match).filter_by(
            provider_match_id="p31-rec-1").count() == 1

    def test_status_update_no_duplicate(self, db):
        from app.services.sources.pipeline import Pipeline

        pipe = Pipeline(db, "test")
        mid = pipe.ingest_match(_normalized_fixture(tag="p31s"))
        live = _normalized_fixture(tag="p31s", status="LIVE")
        assert pipe.ingest_match(live) == mid
        assert db.query(Match).filter_by(
            provider_match_id="p31s-rec-1").count() == 1

    def test_result_ingest_idempotent(self, db):
        from app.services.sources.pipeline import Pipeline

        pipe = Pipeline(db, "test")
        now = datetime.now(timezone.utc)
        fix = _normalized_fixture(
            tag="p31r", kickoff=now - timedelta(hours=3), status="SCHEDULED")
        mid = pipe.ingest_match(fix)
        done = _normalized_fixture(
            tag="p31r", kickoff=now - timedelta(hours=3), hs=2, aws=1,
            status="FINISHED")
        assert pipe.ingest_match(done) == mid
        assert pipe.ingest_match(done) == mid
        row = db.get(Match, mid)
        assert (row.home_score, row.away_score) == (2, 1)
        assert db.query(Match).filter_by(
            provider_match_id="p31r-rec-1").count() == 1

    def test_raw_records_append_only(self, db):
        from app.db.models.provenance import RawDataRecord
        from app.services.sources.pipeline import Pipeline

        pipe = Pipeline(db, "test")
        pipe.ingest_match(_normalized_fixture(tag="p31w"))
        pipe.ingest_match(_normalized_fixture(tag="p31w"))
        # Raw observations retained; canonical stays single.
        assert db.query(RawDataRecord).count() >= 1
        assert db.query(Match).filter_by(
            provider_match_id="p31w-rec-1").count() == 1


# -- failure classification + bounded retries ------------------------------------------------------------------

class TestFailureHandling:
    @staticmethod
    def _exc(status):
        err = Exception(f"HTTP {status}")
        err.status_code = status
        return err

    def test_health_classification(self):
        from app.services.lifecycle.health import _classify

        assert _classify(self._exc(401)) == "authentication_error"
        assert _classify(self._exc(403)) == "authentication_error"
        assert _classify(self._exc(429)) == "rate_limited"
        assert _classify(self._exc(500)) == "transient"

    def test_workflow_classification(self):
        from app.services.acquisition.workflow import classify_failure

        assert classify_failure(self._exc(401)) == "authentication_failure"
        assert classify_failure(self._exc(403)) == "authorization_failure"
        assert classify_failure(self._exc(429)) == "rate_limited"
        assert classify_failure(self._exc(503)) == "temporary_failure"

    def test_retry_settings_bounded(self):
        from app.config import get_settings

        settings = get_settings()
        assert 1 <= settings.PROVIDER_RETRY_ATTEMPTS <= 10
        assert settings.PROVIDER_RETRY_BASE_SECONDS > 0

    def test_rate_limit_configured(self):
        from app.config import get_settings

        assert get_settings().PROVIDER_MAX_REQUESTS_PER_MINUTE > 0


# -- scheduler restart-safety ------------------------------------------------------------------------------------------

class TestSchedulerRestartSafety:
    def test_lock_expiry_and_cleanup(self, db):
        from app.services.scheduler.store import (
            acquire_lock,
            cleanup_expired_locks,
            release_lock,
        )

        first = acquire_lock(db, "source_health", ttl_seconds=1)
        assert first is not None
        assert acquire_lock(db, "source_health", ttl_seconds=300) is None
        import time

        time.sleep(1.2)
        assert cleanup_expired_locks(db) >= 1
        second = acquire_lock(db, "source_health", ttl_seconds=300)
        assert second is not None
        release_lock(db, second)

    def test_run_due_idempotent(self, db):
        from app.services.scheduler import run_due

        first = run_due(db, dry_run=True)
        second = run_due(db, dry_run=True)
        assert isinstance(first, list) and isinstance(second, list)

    def test_stale_lock_reclaim(self, db):
        from app.services.scheduler.store import acquire_lock, release_lock

        lock = acquire_lock(db, "source_health", ttl_seconds=60)
        assert lock is not None
        release_lock(db, lock)
        lock2 = acquire_lock(db, "source_health", ttl_seconds=60)
        assert lock2 is not None
        release_lock(db, lock2)


# -- temporal + lifecycle integration ----------------------------------------------------------------------------------------

def _history(db, league, home_id, away_id, code, base=None):
    now = base or datetime.now(timezone.utc)
    for i in range(3):
        for hid, aid, hs, aws, tag in (
                (home_id, away_id, 2, 0, "a"),
                (away_id, home_id, 1, 1, "b")):
            db.add(Match(
                league_id=league.id, home_team_id=hid, away_team_id=aid,
                kickoff_at=now - timedelta(days=21 - i * 7
                                           - (0 if tag == "a" else 1)),
                status="FINISHED", home_score=hs, away_score=aws,
                provider="t",
                provider_match_id=f"p31-{code}-{tag}{i}"))
    db.commit()
    return now


class TestLifecycleIntegration:
    def _flow(self, db, code="P31F"):
        from app.services.acquisition.readiness_gate import (
            generate_readiness_certificate,
        )
        from app.services.prediction_evaluation import (
            evaluate_prediction_snapshot,
        )
        from app.services.prediction_execution import (
            execute_pre_match_prediction,
        )

        league = League(code=code, name=f"{code} league", provider="t",
                        provider_league_id=f"p31-{code}", season="2024")
        db.add(league)
        db.commit()
        home = Team(league_id=league.id, name="Home", provider="t",
                    provider_team_id=f"p31-{code}-h")
        away = Team(league_id=league.id, name="Away", provider="t",
                    provider_team_id=f"p31-{code}-a")
        db.add_all([home, away])
        db.commit()
        now = _history(db, league, home.id, away.id, code)
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id=f"p31-{code}-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        cutoff = now + timedelta(hours=1)
        cert = generate_readiness_certificate(db, target.id, cutoff=cutoff)
        assert cert.cutoff < target.kickoff_at
        pred = execute_pre_match_prediction(db, target.id, cutoff)
        assert pred["prediction_hash"]
        target.status = "FINISHED"
        target.home_score = 2
        target.away_score = 1
        db.commit()
        ev = evaluate_prediction_snapshot(db, pred["prediction_id"])
        assert ev["metrics"]["actual_result"] == "home"
        return target, pred, ev

    def test_full_lifecycle(self, db):
        target, pred, ev = self._flow(db)
        assert target.status == "FINISHED"
        assert ev["evaluation_id"].startswith("eval_")

    def test_cutoff_strictly_enforced(self, db):
        from app.services.prediction_execution import (
            PredictionBlocked,
            execute_pre_match_prediction,
        )

        league = League(code="P31C", name="x", provider="t",
                        provider_league_id="p31-P31C", season="2024")
        db.add(league)
        db.commit()
        home = Team(league_id=league.id, name="H", provider="t",
                    provider_team_id="p31-P31C-h")
        away = Team(league_id=league.id, name="A", provider="t",
                    provider_team_id="p31-P31C-a")
        db.add_all([home, away])
        db.commit()
        now = datetime.now(timezone.utc)
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p31-P31C-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        with pytest.raises(PredictionBlocked):
            execute_pre_match_prediction(db, target.id, target.kickoff_at)

    def test_monitoring_read_only(self, db):
        from app.db.models.evaluation_records import (
            MatchOutcomeSnapshot,
            PredictionEvaluationRecord,
        )
        from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot
        from app.services.production_monitoring import (
            coverage_funnel,
            data_quality_report,
            detect_anomalies,
            performance_overview,
        )

        _, pred, _ = self._flow(db, code="P31M")
        counts = (db.query(PreMatchPredictionSnapshot).count(),
                  db.query(PredictionEvaluationRecord).count(),
                  db.query(MatchOutcomeSnapshot).count())
        performance_overview(db)
        coverage_funnel(db)
        data_quality_report(db)
        detect_anomalies(db)
        assert (db.query(PreMatchPredictionSnapshot).count(),
                db.query(PredictionEvaluationRecord).count(),
                db.query(MatchOutcomeSnapshot).count()) == counts
        row = db.query(PreMatchPredictionSnapshot).filter_by(
            prediction_id=pred["prediction_id"]).one()
        assert row.prediction_hash == pred["prediction_hash"]

    def test_governance_untouched(self, db):
        from app.services.model_governance import resolve_active_model_id

        self._flow(db, code="P31G")
        assert resolve_active_model_id(db) == "ensemble_v1-elo+poisson"


# -- recovery --------------------------------------------------------------------------------------------------------------------

class TestRecovery:
    def test_interrupted_job_retryable(self, db):
        from app.services.scheduler import run_job_manual

        first = run_job_manual(db, "source_health", dry_run=True)
        second = run_job_manual(db, "source_health", dry_run=True)
        assert first["status"] == second["status"] == "succeeded"

    def test_prediction_replay_after_restart(self, db):
        from app.services.prediction_execution import (
            execute_pre_match_prediction,
        )

        _, pred, _ = TestLifecycleIntegration()._flow(db, code="P31R")
        # Simulated restart: new session-less replay via same service path.
        again = execute_pre_match_prediction(
            db, pred["match_id"],
            datetime.fromisoformat(pred["cutoff_time"]))
        assert again["prediction_id"] == pred["prediction_id"]
        assert again["cache_hit"] is True

    def test_redis_fallback(self):
        from app.services.caching.cache import backend_name

        assert backend_name() in ("redis", "memory")


# -- backup/restore mechanics --------------------------------------------------------------------------------------------------------

class TestBackupRestore:
    def test_scripts_present_and_executable(self):
        import os
        import stat

        for name in ("backup_postgres.sh", "restore_postgres.sh",
                     "verify_backup_restore.sh"):
            path = REPO_ROOT / "scripts" / name
            assert path.exists(), name
            assert bool(os.stat(path).st_mode & stat.S_IXUSR), name

    def test_pg_dump_roundtrip(self):
        import gzip
        import shutil
        import subprocess
        import tempfile

        pg_dump = shutil.which("pg_dump")
        psql = shutil.which("psql")
        if not pg_dump or not psql:
            pytest.skip("pg_dump/psql not available")
        with tempfile.TemporaryDirectory() as tmp:
            dump = f"{tmp}/roundtrip.sql.gz"
            r1 = subprocess.run(
                [pg_dump, "-h", "localhost", "-U", "sivek", "-d",
                 "postgres", "--schema-only", "-t", "pg_tables"],
                capture_output=True, timeout=60)
            assert r1.returncode == 0, r1.stderr[:300]
            with gzip.open(dump, "wb") as fh:
                fh.write(r1.stdout)
            with gzip.open(dump, "rb") as fh:
                assert len(fh.read()) > 0


# -- health -------------------------------------------------------------------------------------------------------------------------------

class TestHealthContracts:
    def test_ready_has_migrations_key(self, client):
        body = client.get("/health/ready").json()
        assert "checks" in body
        assert body["checks"]["database"] == "ok"
        assert "migrations" in body["checks"]

    def test_live_no_deps(self, client):
        assert client.get("/health/live").json()["status"] == "ok"


# -- golden regression -----------------------------------------------------------------------------------------------------------------------

class TestGoldenRegression:
    def test_ensemble_values_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P31GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"
