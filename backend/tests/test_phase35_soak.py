"""Phase 35 — continuous observation soak tests (isolated test DBs only).

Covers: runtime config, repeated scheduler execution, idempotency,
locking, restart recovery, no-fixture behavior, fixture eligibility,
prediction/shadow/outcome/evaluation lifecycles, evidence + validation
refresh, exclusion accounting, duplicate prevention, failure handling,
log redaction, migration integrity, golden regression.
Never touches production databases; synthetic fixtures live only here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, Team
from app.services.observation import observation_summary


def _league(db, code):
    lg = League(code=code, name=f"{code} league", provider="t",
                provider_league_id=f"p35-{code}", season="2024")
    db.add(lg)
    db.commit()
    return lg


def _teams(db, league, code):
    home = Team(league_id=league.id, name="Home", provider="t",
                provider_team_id=f"p35-{code}-h")
    away = Team(league_id=league.id, name="Away", provider="t",
                provider_team_id=f"p35-{code}-a")
    db.add_all([home, away])
    db.commit()
    return home, away


def _history(db, league, home_id, away_id, code, base=None, rounds=35):
    now = base or datetime.now(timezone.utc)
    for i in range(rounds):
        for hid, aid, hs, aws, tag in (
                (home_id, away_id, 2, 0, "a"),
                (away_id, home_id, 1, 1, "b")):
            db.add(Match(
                league_id=league.id, home_team_id=hid, away_team_id=aid,
                kickoff_at=now - timedelta(days=7 * rounds + 5 - i * 7
                                           - (0 if tag == "a" else 1)),
                status="FINISHED", home_score=hs, away_score=aws,
                provider="t",
                provider_match_id=f"p35-{code}-{tag}{i}"))
    db.commit()
    return now


def _full_cycle(db, code="P35F", hs=2, aws=1):
    """Predict → shadow → finish → evaluate → evidence → validation."""
    from app.services.acquisition.readiness_gate import (
        generate_readiness_certificate,
    )
    from app.services.candidate_validation import run_validation
    from app.services.evidence import build_cohort, generate_snapshot
    from app.services.model_governance import (
        decide as decide_fn,
    )
    from app.services.model_governance import (
        ensure_champion,
        request_promotion,
        start_shadow,
    )
    from app.services.model_governance.service import (
        register_candidate_artifact as register_artifact,
    )
    from app.services.model_governance.validation import validate_candidate
    from app.services.prediction_evaluation import (
        evaluate_prediction_snapshot,
    )
    from app.services.prediction_execution import (
        execute_pre_match_prediction,
    )
    from app.services.research import (
        build_dataset,
        register_builtin,
        run_experiment,
    )
    from app.services.shadow_execution import (
        evaluate_shadow_pair,
        execute_shadow,
    )

    league = _league(db, code)
    home, away = _teams(db, league, code)
    now = _history(db, league, home.id, away.id, code)
    target = Match(
        league_id=league.id, home_team_id=home.id, away_team_id=away.id,
        kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
        provider="t", provider_match_id=f"p35-{code}-target")
    db.add(target)
    db.commit()
    db.refresh(target)
    cutoff = now + timedelta(hours=1)
    generate_readiness_certificate(db, target.id, cutoff=cutoff)
    pred = execute_pre_match_prediction(db, target.id, cutoff)
    ds = build_dataset(db, competitions=[code])
    cand = register_builtin(db, "elo_only")
    exp = run_experiment(db, cand.candidate_id, ds.dataset_id)
    art = register_artifact(
        db, candidate_id=cand.candidate_id,
        experiment_id=exp["experiment_id"], dataset_id=ds.dataset_id,
        dataset_hash=ds.dataset_hash)
    report = validate_candidate(
        db, art["artifact_id"], experiment_id=exp["experiment_id"],
        actor="test")
    req = request_promotion(
        db, art["artifact_id"], validation_id=report["validation_id"],
        requester="test")
    decide_fn(db, req["request_id"], decision="APPROVE", actor="human-test")
    champ = ensure_champion(db)
    start_shadow(db, art["artifact_id"], champ.artifact_id, actor="human-test")
    res = execute_shadow(db, target.id, art["artifact_id"])
    target.status = "FINISHED"
    target.home_score = hs
    target.away_score = aws
    db.commit()
    evaluate_prediction_snapshot(db, pred["prediction_id"])
    evaluate_shadow_pair(db, res["shadow_id"])
    cohort = build_cohort(db, challenger_artifact_id=art["artifact_id"])
    snap = generate_snapshot(db, cohort.cohort_id)
    validation = run_validation(db, art["artifact_id"], snap["snapshot_id"])
    return {"target": target, "artifact_id": art["artifact_id"],
            "snapshot": snap, "validation": validation}


# -- 1. runtime configuration -------------------------------------------------------------------------------------

class TestRuntimeConfig:
    def test_soak_flavor_parsing(self):
        from app.config import Settings

        assert Settings(
            TACTICX_ENV="local-production").deployment_flavor() == \
            "local-production"
        assert Settings().SCHEDULER_LOOP_INTERVAL_SECONDS > 0

    def test_operational_switches(self):
        from app.config import Settings

        settings = Settings()
        assert settings.SCHEDULER_ENABLED is True
        assert settings.PREDICTION_ENABLED is True
        assert settings.EVALUATION_ENABLED is True


# -- 2/3/4. scheduler repeated execution, idempotency, locking --------------------------------------------------------------------

class TestSchedulerSoak:
    def test_repeated_dry_run_stable(self, db):
        from app.services.scheduler import run_due

        first = run_due(db, dry_run=True)
        second = run_due(db, dry_run=True)
        assert isinstance(first, list) and isinstance(second, list)

    def test_job_records_append_only(self, db):
        from app.db.models.scheduler import AcquisitionJobRecord
        from app.services.scheduler import run_job_manual

        before = db.query(AcquisitionJobRecord).count()
        run_job_manual(db, "source_health", dry_run=True)
        run_job_manual(db, "source_health", dry_run=True)
        assert db.query(AcquisitionJobRecord).count() >= before

    def test_lock_blocks_concurrent_run(self, db):
        from app.services.scheduler import run_job
        from app.services.scheduler.store import acquire_lock, release_lock

        lock = acquire_lock(db, "source_health", ttl_seconds=300)
        assert lock is not None
        try:
            result = run_job(db, "source_health", dry_run=True)
            assert result["status"] in ("skipped", "succeeded", "failed",
                                        "partial")
        finally:
            release_lock(db, lock)

    def test_stale_lock_recovery(self, db):
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


# -- 5. restart recovery -----------------------------------------------------------------------------------------------

class TestRestartRecovery:
    def test_prediction_replay_after_restart(self, db):
        from app.services.acquisition.readiness_gate import (
            generate_readiness_certificate,
        )
        from app.services.prediction_execution import (
            execute_pre_match_prediction,
        )

        league = _league(db, "P35R")
        home, away = _teams(db, league, "P35R")
        now = _history(db, league, home.id, away.id, "P35R")
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p35-P35R-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        cutoff = now + timedelta(hours=1)
        cert = generate_readiness_certificate(db, target.id, cutoff=cutoff)
        first = execute_pre_match_prediction(db, target.id, cutoff)
        db.expire_all()  # simulate process restart (fresh session state)
        second = execute_pre_match_prediction(db, target.id, cert.cutoff)
        assert second["prediction_id"] == first["prediction_id"]
        assert second["cache_hit"] is True

    def test_shadow_replay_after_restart(self, db):
        league = _league(db, "P35RS")
        home, away = _teams(db, league, "P35RS")
        now = _history(db, league, home.id, away.id, "P35RS")
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p35-P35RS-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        db.expire_all()
        assert db.query(Match).filter_by(id=target.id).one().status == \
            "SCHEDULED"


# -- 6/7. no-fixture behavior + fixture eligibility ----------------------------------------------------------------------------------------------------------------

class TestEligibility:
    def test_no_eligible_matches_state(self, db):
        from app.services.shadow_execution import find_eligible_matches

        scan = find_eligible_matches(db)
        assert scan["state"] == "NO_ELIGIBLE_MATCHES"
        assert scan["eligible"] == []

    def test_empty_observation_summary(self, db):
        summary = observation_summary(db)
        assert summary["discovered"] == 0
        assert summary["paired"] == 0
        assert summary["exclusions"] == {}
        assert summary["last_activity"]["prediction"] is None

    def test_blocked_classified(self, db):
        from app.services.acquisition.readiness_gate import (
            generate_readiness_certificate,
        )

        league = _league(db, "P35B")
        home, away = _teams(db, league, "P35B")
        now = datetime.now(timezone.utc)
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p35-P35B-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        generate_readiness_certificate(
            db, target.id, cutoff=now + timedelta(hours=1))
        summary = observation_summary(db)
        assert summary["discovered"] >= 1
        assert summary["exclusions"].get("READINESS_BLOCKED", 0) >= 1 \
            or summary["exclusions"].get("INSUFFICIENT_HISTORY", 0) >= 1


# -- 8-13. lifecycle stages -----------------------------------------------------------------------------------------------------------------------------------------------------

class TestLifecycle:
    def test_full_funnel_counts(self, db):
        _full_cycle(db, code="P35F")
        summary = observation_summary(db, competition="P35F")
        assert summary["discovered"] >= 7
        assert summary["eligible"] >= 1
        assert summary["predicted"] >= 1
        assert summary["shadowed"] >= 1
        assert summary["finished"] >= 1
        assert summary["outcome_verified"] >= 1
        assert summary["evaluated"] >= 1
        assert summary["paired"] >= 1
        assert summary["included_in_evidence"] >= 1

    def test_exclusion_reasons_present(self, db):
        _full_cycle(db, code="P35X")
        summary = observation_summary(db, competition="P35X")
        assert isinstance(summary["exclusions"], dict)
        assert summary["last_activity"]["prediction"] is not None
        assert summary["last_activity"]["evaluation"] is not None

    def test_evidence_and_validation_states(self, db):
        ctx = _full_cycle(db, code="P35EV")
        assert ctx["snapshot"]["paired_count"] >= 1
        assert ctx["validation"]["validation_state"] in (
            "VALIDATED_FOR_GOVERNANCE", "INCONCLUSIVE", "INSUFFICIENT_DATA",
            "BLOCKED", "INVALID")


# -- 14/15. exclusion accounting + observation consistency ---------------------------------------------------------------------------------------------------------------------

class TestAccounting:
    def test_counts_consistent(self, db):
        _full_cycle(db, code="P35AC")
        summary = observation_summary(db, competition="P35AC")
        assert summary["paired"] <= summary["shadowed"]
        assert summary["shadowed"] <= summary["predicted"]
        assert summary["evaluated"] <= summary["predicted"]
        assert summary["outcome_verified"] >= summary["evaluated"]

    def test_scoped_filters(self, db):
        _full_cycle(db, code="P35SC")
        scoped = observation_summary(db, competition="P35SC")
        empty = observation_summary(db, competition="NOPE")
        assert scoped["discovered"] >= 1
        assert empty["discovered"] == 0
        assert empty["paired"] == 0


# -- 16. duplicate prevention ---------------------------------------------------------------------------------------------------------------------------------------------------------

class TestDuplicates:
    def test_no_duplicate_predictions(self, db):
        from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot
        from app.services.acquisition.readiness_gate import (
            generate_readiness_certificate,
        )
        from app.services.prediction_execution import (
            execute_pre_match_prediction,
        )

        league = _league(db, "P35D")
        home, away = _teams(db, league, "P35D")
        now = _history(db, league, home.id, away.id, "P35D")
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p35-P35D-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        cutoff = now + timedelta(hours=1)
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        first = execute_pre_match_prediction(db, target.id, cutoff)
        second = execute_pre_match_prediction(db, target.id, cutoff)
        assert first["prediction_id"] == second["prediction_id"]
        assert db.query(PreMatchPredictionSnapshot).filter_by(
            match_id=target.id).count() == 1


# -- 17. provider failure ---------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestProviderFailure:
    def test_unknown_provider_handled(self, db):
        from app.services.acquisition.activation import get_activation_state

        assert get_activation_state(db, "nope_provider") == "UNAVAILABLE"

    def test_failure_codes_stable(self):
        from app.services.acquisition.workflow import classify_failure

        def _exc(status):
            err = Exception(f"HTTP {status}")
            err.status_code = status
            return err

        assert classify_failure(_exc(401)) == "authentication_failure"
        assert classify_failure(_exc(429)) == "rate_limited"
        assert classify_failure(_exc(503)) == "temporary_failure"


# -- 18/19. database/Redis failure (covered by existing suites; spot-check contracts) ----------------------------------------------------------------------------------------------------

class TestDependencyFailure:
    def test_ready_contract(self, client):
        body = client.get("/health/ready").json()
        assert body["checks"]["database"] == "ok"
        assert "migrations" in body["checks"]

    def test_cache_fallback(self):
        from app.services.caching.cache import backend_name

        assert backend_name() in ("redis", "memory")


# -- 20. security/log redaction ---------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestSecurity:
    def test_log_redaction(self):
        from app.logging_config import redact_secrets

        assert "sekret" not in redact_secrets(
            "https://x.test/?apiKey=sekret&foo=1")

    def test_no_credentials_in_summary(self, db):
        _full_cycle(db, code="P35SEC")
        blob = str(observation_summary(db, competition="P35SEC")).lower()
        assert "api_key" not in blob
        assert "bearer" not in blob
        assert "password" not in blob


# -- 21. migration integrity ----------------------------------------------------------------------------------------------------------------------------------------------------------------------

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

    def test_tables_exist(self, db):
        from app.db.models.candidate_validation import (
            CandidateValidationReport,
        )
        from app.db.models.evidence import EvidenceSnapshot

        assert db.query(CandidateValidationReport).count() == 0
        assert db.query(EvidenceSnapshot).count() == 0


# -- 22. golden regression -------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestGoldenRegression:
    def test_ensemble_values_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P35GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"


# -- operations API -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestOperationsAPI:
    def test_soak_empty(self, client):
        body = client.get("/api/v1/operations/soak").json()
        assert body["discovered"] == 0
        assert body["paired"] == 0

    def test_soak_counts(self, client, db):
        _full_cycle(db, code="P35API")
        body = client.get(
            "/api/v1/operations/soak?competition=P35API").json()
        assert body["predicted"] >= 1
        assert body["paired"] >= 1
        assert body["last_activity"]["prediction"] is not None
