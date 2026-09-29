"""Phase 33 — real-world performance evidence tests.

Covers: no-data/insufficient states, eligibility, cohort determinism,
pairing, outcome identity, temporal validation, metrics, paired diffs,
bootstrap/uncertainty, calibration, breakdowns, windows, evidence hash,
deterministic rerun, corrected outcomes, immutability, API, CLI,
migration, isolation, no-auto-decision, performance, Phase 27/28
regression, golden regression.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.evidence import EvidenceCohort, EvidenceSnapshot
from app.db.models.governance import ShadowEvaluationRecord
from app.services.acquisition.readiness_gate import (
    generate_readiness_certificate,
)
from app.services.evidence import (
    audit_cohort,
    build_cohort,
    generate_snapshot,
    get_snapshot,
)
from app.services.evidence.cohort import CohortError
from app.services.model_governance import (
    decide as decide_fn,
)
from app.services.model_governance import (
    ensure_champion,
    request_promotion,
    resolve_active_model_id,
    start_shadow,
)
from app.services.model_governance.service import (
    register_candidate_artifact as register_artifact,
)
from app.services.model_governance.validation import validate_candidate
from app.services.prediction_execution import execute_pre_match_prediction
from app.services.research import (
    build_dataset,
    register_builtin,
    run_experiment,
)
from app.services.shadow_execution import (
    evaluate_shadow_pair,
    execute_shadow,
)


def _round_robin(db, code="P33R", days=40):
    league = League(code=code, name=f"{code} league", provider="t",
                    provider_league_id=f"p33-{code}", season="2024")
    db.add(league)
    db.commit()
    teams = {}
    for name in ("A", "B", "C", "D"):
        team = Team(league_id=league.id, name=name, provider="t",
                    provider_team_id=f"p33-{code}-{name}")
        db.add(team)
        db.flush()
        teams[name] = team
    now = datetime.now(timezone.utc)
    names = ["A", "B", "C", "D"]
    idx = 0
    for day in range(days):
        order = names[day % 4:] + names[:day % 4]
        for i in range(0, 3, 2):
            home, away = teams[order[i]], teams[order[i + 1]]
            hs, aws = [(2, 0), (1, 1), (0, 1), (3, 1)][idx % 4]
            idx += 1
            db.add(Match(
                league_id=league.id, home_team_id=home.id,
                away_team_id=away.id,
                kickoff_at=now - timedelta(days=days + 5 - day),
                status="FINISHED", home_score=hs, away_score=aws,
                provider="t", provider_match_id=f"p33-{code}-{idx}"))
    db.commit()
    return league


def _evaluated_shadows(db, code="P33E", count=3, key="elo_only"):
    """Build history + N upcoming→predicted→shadowed→finished→evaluated."""
    league = _round_robin(db, code=code)
    home = db.query(Team).filter_by(
        league_id=league.id, provider_team_id=f"p33-{code}-A").one()
    away = db.query(Team).filter_by(
        league_id=league.id, provider_team_id=f"p33-{code}-B").one()
    ds = build_dataset(db, competitions=[code])
    cand = register_builtin(db, key)
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
    now = datetime.now(timezone.utc)
    out = []
    champ_pred_ids = []
    for i in range(count):
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5 + i), status="SCHEDULED",
            provider="t", provider_match_id=f"p33-{code}-t{i}")
        db.add(target)
        db.commit()
        db.refresh(target)
        cutoff = now + timedelta(hours=1)
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        champ_pred = execute_pre_match_prediction(db, target.id, cutoff)
        champ_pred_ids.append(champ_pred["prediction_id"])
        res = execute_shadow(db, target.id, art["artifact_id"])
        target.status = "FINISHED"
        target.home_score = 2 if i % 2 == 0 else 0
        target.away_score = 1 if i % 2 == 0 else 0
        db.commit()
        out.append(evaluate_shadow_pair(db, res["shadow_id"]))
    # Champion arm evaluated through the Phase 27 path as well, so both
    # evaluation populations exist side by side.
    from app.services.prediction_evaluation import (
        evaluate_prediction_snapshot,
    )

    for prediction_id in champ_pred_ids:
        evaluate_prediction_snapshot(db, prediction_id)
    return {"challenger_id": art["artifact_id"], "evaluations": out}


# -- 1/2. no-data + insufficient states -----------------------------------------------------------------------------------

class TestZeroData:
    def test_empty_db_status(self, client):
        body = client.get("/api/v1/evidence/status").json()
        assert body["state"] == "NO_DATA"
        assert body["champion_evaluations"] == 0
        assert body["challenger_evaluations"] == 0
        assert body["paired_observations"] == 0
        assert body["synthetic_observations"] == 0

    def test_empty_cohort_snapshot(self, db):
        cohort = build_cohort(db, challenger_artifact_id="art_missing")
        result = generate_snapshot(db, cohort.cohort_id)
        assert result["evidence_state"] in ("NO_DATA", "INSUFFICIENT_REAL_DATA")
        assert result["paired_count"] == 0
        assert "winner" not in str(result).lower()

    def test_no_fake_metrics(self, db):
        cohort = build_cohort(db, challenger_artifact_id="art_missing")
        result = generate_snapshot(db, cohort.cohort_id)
        assert result["champion_metrics"]["sample_count"] == 0
        assert result["uncertainty"] == {} or \
            result["uncertainty"].get("delta_log_loss_1x2_ci") is None


# -- 3/4. eligibility + cohort determinism -------------------------------------------------------------------------------------

class TestEligibilityCohort:
    def test_cohort_reuse_by_hash(self, db):
        first = build_cohort(db, challenger_artifact_id="art_x",
                             competitions=["EPL"])
        second = build_cohort(db, challenger_artifact_id="art_x",
                              competitions=["EPL"])
        assert second.cohort_id == first.cohort_id
        assert second.cohort_hash == first.cohort_hash

    def test_invalid_date_range(self, db):
        now = datetime.now(timezone.utc)
        with pytest.raises(CohortError):
            build_cohort(db, date_from=now + timedelta(days=1),
                         date_to=now - timedelta(days=1))

    def test_unknown_cohort(self, db):
        from app.services.evidence.cohort import get_cohort as get_c

        with pytest.raises(CohortError):
            get_c(db, "coh_nope_00000000")

    def test_excluded_classified(self, db):
        _evaluated_shadows(db, code="P33EX", count=2)
        cohort = build_cohort(db, competitions=["NOPE"])
        audit = audit_cohort(db, cohort)
        assert audit["paired_count"] == 0
        assert audit["excluded_count"] >= 2
        assert all(e["code"] == "FILTER_EXCLUDED"
                   for e in audit["excluded"])

    def test_eligibility_counts(self, db):
        ctx = _evaluated_shadows(db, code="P33EL", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["challenger_id"])
        audit = audit_cohort(db, cohort)
        assert audit["paired_count"] == 2
        assert audit["temporal"]["temporal_valid"] == 2
        assert audit["temporal"]["temporal_invalid"] == 0


# -- 5/6. pairing + outcome identity -----------------------------------------------------------------------------------------------

class TestPairingOutcome:
    def test_shared_outcome_hash(self, db):
        ctx = _evaluated_shadows(db, code="P33PO", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["challenger_id"])
        audit = audit_cohort(db, cohort)
        hashes = {p["outcome_hash"] for p in audit["paired"]}
        assert len(hashes) == 2
        for obs in audit["paired"]:
            assert obs["feature_snapshot_id"]
            assert obs["feature_snapshot_hash"]

    def test_corrected_outcome_new_snapshot(self, db):
        ctx = _evaluated_shadows(db, code="P33CO", count=1)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["challenger_id"])
        first = generate_snapshot(db, cohort.cohort_id)
        league = db.query(League).filter_by(code="P33CO").one()
        target = db.query(Match).filter_by(
            league_id=league.id,
            provider_match_id="p33-P33CO-t0").one()
        target.home_score = 0
        target.away_score = 5
        db.commit()
        from app.services.prediction_evaluation import capture_outcome_snapshot
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        capture_outcome_snapshot(db, target.id)
        shadow = db.query(ShadowEvaluationRecord).filter_by(
            match_id=target.id).one()
        corrected = ev(db, shadow.shadow_id)
        assert corrected["cache_hit"] is False
        # Old evaluation still references the old outcome hash.
        assert shadow.outcome_hash != corrected["outcome_hash"]
        second = generate_snapshot(db, cohort.cohort_id)
        assert second["snapshot_id"] != first["snapshot_id"]
        assert second["rerun"] is False
        assert second["paired_count"] == 1  # deduped: no double-count
        # Old snapshot immutable.
        again = get_snapshot(db, first["snapshot_id"])
        assert again.snapshot_hash == first["snapshot_hash"]


# -- 7. temporal validation ----------------------------------------------------------------------------------------------------------------

class TestTemporal:
    def test_cutoff_before_kickoff_all_paired(self, db):
        ctx = _evaluated_shadows(db, code="P33TV", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["challenger_id"])
        audit = audit_cohort(db, cohort)
        assert audit["temporal"]["excluded_post_cutoff"] == 0
        assert audit["temporal"]["excluded_unknown_timing"] == 0


# -- 8/9. metrics + paired differences ----------------------------------------------------------------------------------------------------------------

class TestMetrics:
    def test_paired_means_and_diffs(self, db):
        ctx = _evaluated_shadows(db, code="P33MM", count=3)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["challenger_id"])
        result = generate_snapshot(db, cohort.cohort_id)
        assert result["paired_count"] == 3
        assert result["champion_metrics"]["sample_count"] == 3
        assert result["challenger_metrics"]["sample_count"] == 3
        assert "delta_log_loss_1x2" in result["differences"]
        assert "delta_brier_1x2" in result["differences"]
        assert "delta_accuracy_1x2" in result["differences"]

    def test_no_single_score(self, db):
        ctx = _evaluated_shadows(db, code="P33MS", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["challenger_id"])
        result = generate_snapshot(db, cohort.cohort_id)
        keys = " ".join(result["differences"].keys())
        assert "winner" not in keys
        assert "best" not in keys
        assert "rank" not in keys


# -- 10/11. bootstrap + uncertainty --------------------------------------------------------------------------------------------------------------------

class TestUncertainty:
    def test_ci_present_and_seeded(self, db):
        ctx = _evaluated_shadows(db, code="P33UC", count=3)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["challenger_id"])
        result = generate_snapshot(db, cohort.cohort_id)
        unc = result["uncertainty"]
        assert unc["delta_log_loss_1x2_ci"] is not None
        assert unc["delta_brier_1x2_ci"] is not None
        assert unc["delta_log_loss_1x2_ci"]["method"] == "bootstrap_mean"
        assert unc["champion_accuracy_ci"]["method"] == "wilson"

    def test_deterministic_rerun(self, db):
        ctx = _evaluated_shadows(db, code="P33UR", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["challenger_id"])
        first = generate_snapshot(db, cohort.cohort_id)
        second = generate_snapshot(db, cohort.cohort_id)
        assert second["rerun"] is True
        assert second["snapshot_hash"] == first["snapshot_hash"]
        assert second["snapshot_id"] == first["snapshot_id"]


# -- 12. calibration ------------------------------------------------------------------------------------------------------------------------------------------

class TestCalibration:
    def test_insufficient_flag_small_n(self, db):
        _evaluated_shadows(db, code="P33CB", count=2)
        cohort = build_cohort(db)
        result = generate_snapshot(db, cohort.cohort_id)
        assert result["calibration"]["state"] == "INSUFFICIENT_DATA"

    def test_available_with_data(self, db):
        _evaluated_shadows(db, code="P33CA", count=12)
        cohort = build_cohort(db)
        result = generate_snapshot(db, cohort.cohort_id)
        assert result["paired_count"] == 12
        assert result["calibration"]["state"] == "AVAILABLE"
        assert set(result["calibration"]["per_outcome_by_arm"][
            "champion"]) == {"home", "draw", "away"}


# -- 13. breakdowns -----------------------------------------------------------------------------------------------------------------------------------------------

class TestBreakdowns:
    def test_competition_breakdown(self, client, db):
        _evaluated_shadows(db, code="P33BD", count=2)
        body = client.get(
            "/api/v1/evidence/breakdown/art_x?by=competition").json()
        assert "groups" in body
        assert "P33BD" in body["groups"]
        assert body["groups"]["P33BD"]["sample_count"] >= 1
        assert "best" not in str(body).lower().replace(
            "best_model", "").replace("best model", "")


# -- 14. windows -----------------------------------------------------------------------------------------------------------------------------------------------------

class TestWindows:
    def test_date_range_filters(self, db):
        _evaluated_shadows(db, code="P33WR", count=2)
        now = datetime.now(timezone.utc)
        empty = build_cohort(
            db, date_from=now + timedelta(days=30),
            date_to=now + timedelta(days=60))
        result = generate_snapshot(db, empty.cohort_id)
        assert result["paired_count"] == 0
        assert result["evidence_state"] == "INSUFFICIENT_REAL_DATA"

    def test_invalid_range_rejected(self, client):
        resp = client.post(
            "/api/v1/evidence/cohorts",
            json={"date_from": "2024-02-01T00:00:00",
                  "date_to": "2024-01-01T00:00:00"})
        assert resp.status_code == 422


# -- 15. hash ---------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestEvidenceHash:
    def test_hash_covers_inputs(self, db):
        first = _evaluated_shadows(db, code="P33H1", count=1)
        second = _evaluated_shadows(db, code="P33H2", count=1)
        coh1 = build_cohort(
            db, challenger_artifact_id=first["challenger_id"])
        coh2 = build_cohort(
            db, challenger_artifact_id=second["challenger_id"])
        r1 = generate_snapshot(db, coh1.cohort_id)
        r2 = generate_snapshot(db, coh2.cohort_id)
        assert r1["snapshot_hash"] != r2["snapshot_hash"]

    def test_unknown_snapshot(self, db):
        from app.services.evidence.snapshot import EvidenceError

        with pytest.raises(EvidenceError):
            get_snapshot(db, "evd_nope_00000000")


# -- 17. corrected outcomes (covered in §6) --------------------------------------------------------------------------------------------------------------------------------
# -- 18. historical immutability -----------------------------------------------------------------------------------------------------------------------------------------------

class TestImmutability:
    def test_snapshot_frozen(self, db):
        ctx = _evaluated_shadows(db, code="P33IM", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["challenger_id"])
        first = generate_snapshot(db, cohort.cohort_id)
        before = dict(first["champion_metrics"])
        _evaluated_shadows(db, code="P33IM2", count=1)
        stored = get_snapshot(db, first["snapshot_id"])
        assert stored.champion_metrics == before
        assert stored.snapshot_hash == first["snapshot_hash"]

    def test_mutation_rejected_no_update_path(self, db):
        import app.services.evidence as ev_mod

        assert not hasattr(ev_mod, "update_snapshot")
        assert not hasattr(ev_mod, "delete_snapshot")
        assert not hasattr(ev_mod, "rewrite_snapshot")


# -- 19. API ------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestEvidenceAPI:
    def test_status_empty(self, client):
        body = client.get("/api/v1/evidence/status").json()
        assert body["state"] == "NO_DATA"
        assert body["synthetic_observations"] == 0

    def test_cohort_lifecycle(self, client, db):
        _evaluated_shadows(db, code="P33APIC", count=1)
        created = client.post(
            "/api/v1/evidence/cohorts",
            json={"challenger_artifact_id": "art_x"}).json()
        assert created["cohort_hash"]
        detail = client.get(
            f"/api/v1/evidence/cohorts/{created['cohort_id']}").json()
        assert detail["cohort_id"] == created["cohort_id"]
        listed = client.get("/api/v1/evidence/cohorts").json()
        assert any(c["cohort_id"] == created["cohort_id"]
                   for c in listed["cohorts"])

    def test_compare_read_only(self, client, db):
        ctx = _evaluated_shadows(db, code="P33APIR", count=2)
        cohorts_before = db.query(EvidenceCohort).count()
        snaps_before = db.query(EvidenceSnapshot).count()
        body = client.get(
            f"/api/v1/evidence/compare/{ctx['challenger_id']}").json()
        assert body["paired_count"] == 2
        assert db.query(EvidenceCohort).count() == cohorts_before
        assert db.query(EvidenceSnapshot).count() == snaps_before

    def test_snapshots_and_uncertainty(self, client, db):
        ctx = _evaluated_shadows(db, code="P33APIS", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["challenger_id"])
        created = generate_snapshot(db, cohort.cohort_id)
        detail = client.get(
            f"/api/v1/evidence/snapshots/{created['snapshot_id']}").json()
        assert detail["snapshot_hash"] == created["snapshot_hash"]
        unc = client.get(
            f"/api/v1/evidence/uncertainty/{created['snapshot_id']}").json()
        assert "uncertainty" in unc
        listed = client.get("/api/v1/evidence/snapshots").json()
        assert any(s["snapshot_id"] == created["snapshot_id"]
                   for s in listed["snapshots"])

    def test_refresh_guarded(self, client):
        from unittest.mock import patch

        with patch("app.config.Settings.operational_endpoints_enabled",
                   False):
            resp = client.post("/api/v1/evidence/refresh")
            assert resp.status_code == 403
            resp = client.post("/api/v1/evidence/cohorts", json={})
            assert resp.status_code == 403

    def test_refresh_appends(self, client, db):
        _evaluated_shadows(db, code="P33APIF", count=1)
        first = client.post("/api/v1/evidence/refresh").json()
        second = client.post("/api/v1/evidence/refresh").json()
        assert second["rerun"] is True
        assert second["snapshot_id"] == first["snapshot_id"]


# -- 20. CLI --------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestEvidenceCLI:
    def test_status(self, db):
        import scripts.tacticx as cli
        import argparse

        args = argparse.Namespace(action="status", challenger="",
                                  snapshot="", competition="", as_json=True)
        assert cli._cmd_evidence(db, args) == 0

    def test_generate_compare_show(self, db):
        import scripts.tacticx as cli
        import argparse

        ctx = _evaluated_shadows(db, code="P33CLI", count=1)
        args = argparse.Namespace(
            action="generate", challenger=ctx["challenger_id"], snapshot="",
            competition="", as_json=True)
        assert cli._cmd_evidence(db, args) == 0
        args = argparse.Namespace(
            action="compare", challenger=ctx["challenger_id"], snapshot="",
            competition="", as_json=True)
        assert cli._cmd_evidence(db, args) == 0
        row = db.query(EvidenceSnapshot).order_by(
            EvidenceSnapshot.id.desc()).first()
        args = argparse.Namespace(
            action="show", challenger="", snapshot=row.snapshot_id,
            competition="", as_json=True)
        assert cli._cmd_evidence(db, args) == 0


# -- 22. migration -----------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestMigrationChain:
    def test_0016_chain(self):
        import importlib.util
        from pathlib import Path

        path = (Path(__file__).parent.parent / "migrations" / "versions"
                / "0016_evidence.py")
        spec = importlib.util.spec_from_file_location("mig_0016", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "0016_evidence"
        assert mod.down_revision == "0015_shadow_execution"
        assert mod.branch_labels is None

    def test_0016_links_into_chain(self):
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
        # 0016 must chain 0015 -> 0016; head ownership belongs to the
        # latest phase test (no branch divergence).
        assert revisions["0016_evidence"] == \
            "0015_shadow_execution"
        down_revs = {v for v in revisions.values() if v is not None}
        heads = [r for r in revisions if r not in down_revs]
        assert len(heads) == 1

    def test_tables_exist(self, db):
        assert db.query(EvidenceCohort).count() == 0
        assert db.query(EvidenceSnapshot).count() == 0


# -- 23. production isolation ---------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestIsolation:
    def test_evidence_writes_nothing_else(self, db):
        from app.db.models.evaluation_records import (
            MatchOutcomeSnapshot,
            PredictionEvaluationRecord,
        )
        from app.db.models.governance import (
            ModelGovernanceEvent,
            ModelRegistry,
            ShadowEvaluationRecord,
        )
        from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot

        ctx = _evaluated_shadows(db, code="P33PI", count=2)
        counts = {
            "pred": db.query(PreMatchPredictionSnapshot).count(),
            "eval": db.query(PredictionEvaluationRecord).count(),
            "outcome": db.query(MatchOutcomeSnapshot).count(),
            "shadow_eval": db.query(ShadowEvaluationRecord).count(),
            "registry": db.query(ModelRegistry).count(),
            "events": db.query(ModelGovernanceEvent).count(),
        }
        champion = resolve_active_model_id(db)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["challenger_id"])
        generate_snapshot(db, cohort.cohort_id)
        assert db.query(PreMatchPredictionSnapshot).count() == counts["pred"]
        assert db.query(PredictionEvaluationRecord).count() == counts["eval"]
        assert db.query(MatchOutcomeSnapshot).count() == counts["outcome"]
        assert db.query(ShadowEvaluationRecord).count() == counts["shadow_eval"]
        assert db.query(ModelRegistry).count() == counts["registry"]
        assert db.query(ModelGovernanceEvent).count() == counts["events"]
        assert resolve_active_model_id(db) == champion


# -- 24. no-auto-decision ----------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestNoAutoDecision:
    def _flow(self, db, code):
        return _evaluated_shadows(db, code=code, count=3)

    def test_supported_difference_no_promotion(self, db):
        from app.db.models.governance import ModelPromotionRequest

        self._flow(db, "P33NAD")
        cohort = build_cohort(db)
        result = generate_snapshot(db, cohort.cohort_id)
        assert result["evidence_state"] in (
            "DESCRIPTIVE_ONLY", "INCONCLUSIVE", "SUPPORTED_DIFFERENCE",
            "CONFLICTING_EVIDENCE", "INSUFFICIENT_REAL_DATA")
        assert db.query(ModelPromotionRequest).count() == 1  # setup only
        assert resolve_active_model_id(db) == "ensemble_v1-elo+poisson"

    def test_scheduler_refresh_no_governance(self, db):
        from app.db.models.governance import ModelGovernanceEvent
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import (
            JOB_PERFORMANCE_EVIDENCE_REFRESH,
        )
        from app.services.scheduler.executors import get_executor

        ctx = _evaluated_shadows(db, code="P33NAS", count=2)
        events_before = db.query(ModelGovernanceEvent).count()
        cfg = get_job_config(JOB_PERFORMANCE_EVIDENCE_REFRESH)
        cfg["challenger_artifact_id"] = ctx["challenger_id"]
        out = get_executor(JOB_PERFORMANCE_EVIDENCE_REFRESH)(db, cfg,
                                                             dry_run=False)
        assert out["status"] == "succeeded"
        assert db.query(ModelGovernanceEvent).count() == events_before
        assert resolve_active_model_id(db) == "ensemble_v1-elo+poisson"

    def test_anomaly_no_transition(self, db):
        from app.services.model_governance.artifact import get_artifact as g
        from app.services.production_monitoring import detect_anomalies

        ctx = _evaluated_shadows(db, code="P33NAA", count=2)
        before = g(db, ctx["challenger_id"]).lifecycle_state
        detect_anomalies(db)
        after = g(db, ctx["challenger_id"]).lifecycle_state
        assert after == before


# -- 25. performance -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestPerformance:
    def test_generation_bounded_queries(self, db):
        import time

        _evaluated_shadows(db, code="P33PF", count=5)
        cohort = build_cohort(db)
        start = time.monotonic()
        result = generate_snapshot(db, cohort.cohort_id)
        duration = time.monotonic() - start
        assert result["paired_count"] == 5
        assert duration < 30.0


# -- 26. regression 27/28 -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestRegression2728:
    def test_phase27_summary_stable(self, db):
        from app.services.prediction_evaluation import summarize_evaluations

        _evaluated_shadows(db, code="P33R27", count=2)
        summary = summarize_evaluations(db)
        assert summary["metrics"]["sample_count"] >= 2
        assert summary["metrics"]["accuracy_1x2"] is not None

    def test_phase28_monitoring_stable(self, db):
        from app.services.production_monitoring import performance_overview

        _evaluated_shadows(db, code="P33R28", count=2)
        perf = performance_overview(db)
        assert perf["metrics"]["sample_count"] >= 2


# -- golden regression --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestGoldenRegression:
    def test_ensemble_values_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P33GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"
