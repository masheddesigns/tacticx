"""Phase 27 — prediction evaluation lifecycle tests.

Covers: result eligibility, outcome snapshots, evaluation metrics,
immutability, idempotency, temporal safety, calibration, drift, API,
scheduler, migration chain, golden regression.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.evaluation_records import (
    MatchOutcomeSnapshot,
    PredictionEvaluationRecord,
)
from app.services.acquisition.readiness_gate import (
    generate_readiness_certificate,
)
from app.services.prediction_evaluation import (
    EvaluationBlocked,
    calibration_report,
    capture_outcome_snapshot,
    drift_report,
    evaluate_prediction_snapshot,
    evaluation_to_dict,
    outcome_eligibility,
    score_snapshot,
    summarize_evaluations,
)
from app.services.prediction_evaluation.outcomes import OutcomeNotReady
from app.services.prediction_execution import execute_pre_match_prediction


def _league(db, code):
    lg = League(code=code, name=f"{code} league", provider="t",
                provider_league_id=f"p27-{code}", season="2024")
    db.add(lg)
    db.commit()
    return lg


def _teams(db, league, code):
    home = Team(league_id=league.id, name="Home", provider="t",
                provider_team_id=f"p27-{code}-h")
    away = Team(league_id=league.id, name="Away", provider="t",
                provider_team_id=f"p27-{code}-a")
    db.add_all([home, away])
    db.commit()
    return home, away


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
                provider_match_id=f"p27-{code}-{tag}{i}"))
    db.commit()
    return now


def _evaluated(db, code="P27E", hs=2, aws=1):
    """Full pipeline: predict -> finish -> evaluate. Returns dict of rows."""
    league = _league(db, code)
    home, away = _teams(db, league, code)
    now = _history(db, league, home.id, away.id, code)
    target = Match(
        league_id=league.id, home_team_id=home.id, away_team_id=away.id,
        kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
        provider="t", provider_match_id=f"p27-{code}-target")
    db.add(target)
    db.commit()
    db.refresh(target)
    cutoff = now + timedelta(hours=1)
    cert = generate_readiness_certificate(db, target.id, cutoff=cutoff)
    pred = execute_pre_match_prediction(db, target.id, cutoff)
    target.status = "FINISHED"
    target.home_score = hs
    target.away_score = aws
    db.commit()
    ev = evaluate_prediction_snapshot(db, pred["prediction_id"])
    return {"league": league, "target": target, "cutoff": cutoff,
            "cert": cert, "pred": pred, "eval": ev}


# -- result eligibility ------------------------------------------------------------------------------

class TestResultEligibility:
    def test_scheduled_not_eligible(self, db):
        league = _league(db, "P27RS")
        home, away = _teams(db, league, "P27RS")
        now = datetime.now(timezone.utc)
        m = Match(league_id=league.id, home_team_id=home.id,
                  away_team_id=away.id, kickoff_at=now + timedelta(hours=5),
                  status="SCHEDULED", provider="t",
                  provider_match_id="p27-P27RS-t")
        db.add(m)
        db.commit()
        db.refresh(m)
        check = outcome_eligibility(db, m.id)
        assert check["eligible"] is False
        assert check["code"] == "MATCH_NOT_FINISHED"
        with pytest.raises(OutcomeNotReady):
            capture_outcome_snapshot(db, m.id)

    def test_postponed_cancelled_not_eligible(self, db):
        for status in ("POSTPONED", "CANCELLED", "SUSPENDED", "ABANDONED",
                       "LIVE", "HALFTIME"):
            league = _league(db, f"P27{status[:4]}")
            home, away = _teams(db, league, f"P27{status[:4]}")
            now = datetime.now(timezone.utc)
            m = Match(league_id=league.id, home_team_id=home.id,
                      away_team_id=away.id,
                      kickoff_at=now - timedelta(hours=2), status=status,
                      home_score=1, away_score=0, provider="t",
                      provider_match_id=f"p27-{status}-t")
            db.add(m)
            db.commit()
            db.refresh(m)
            assert outcome_eligibility(db, m.id)["eligible"] is False

    def test_finished_without_scores_not_eligible(self, db):
        league = _league(db, "P27NS")
        home, away = _teams(db, league, "P27NS")
        now = datetime.now(timezone.utc)
        m = Match(league_id=league.id, home_team_id=home.id,
                  away_team_id=away.id,
                  kickoff_at=now - timedelta(hours=2), status="FINISHED",
                  provider="t", provider_match_id="p27-P27NS-t")
        db.add(m)
        db.commit()
        db.refresh(m)
        check = outcome_eligibility(db, m.id)
        assert check["eligible"] is False
        assert check["code"] == "RESULT_SCORES_MISSING"

    def test_unknown_match(self, db):
        check = outcome_eligibility(db, 999999)
        assert check["eligible"] is False
        assert check["code"] == "UNKNOWN_MATCH"

    def test_finished_eligible(self, db):
        ctx = _evaluated(db, code="P27FE")
        check = outcome_eligibility(db, ctx["target"].id)
        assert check["eligible"] is True


# -- outcome snapshots ---------------------------------------------------------------------------------

class TestOutcomeSnapshots:
    def test_capture_canonical(self, db):
        ctx = _evaluated(db, code="P27OC")
        outcome = capture_outcome_snapshot(db, ctx["target"].id)
        assert outcome.final_home_goals == 2
        assert outcome.final_away_goals == 1
        assert outcome.final_result == "home"
        assert outcome.outcome_hash
        assert outcome.outcome_id.startswith("out_")

    def test_capture_idempotent(self, db):
        ctx = _evaluated(db, code="P27OI")
        first = capture_outcome_snapshot(db, ctx["target"].id)
        second = capture_outcome_snapshot(db, ctx["target"].id)
        assert second.outcome_id == first.outcome_id
        count = db.query(MatchOutcomeSnapshot).filter_by(
            match_id=ctx["target"].id).count()
        assert count == 1

    def test_corrected_result_supersedes(self, db):
        ctx = _evaluated(db, code="P27OS")
        first = capture_outcome_snapshot(db, ctx["target"].id)
        target = ctx["target"]
        target.home_score = 0
        target.away_score = 3
        db.commit()
        second = capture_outcome_snapshot(db, target.id)
        assert second.outcome_id != first.outcome_id
        assert second.supersedes_outcome_id == first.outcome_id
        assert second.final_result == "away"


# -- evaluation metrics -----------------------------------------------------------------------------------

class TestEvaluationMetrics:
    def test_correct_result_scores(self, db):
        ctx = _evaluated(db, code="P27MC", hs=2, aws=1)
        m = ctx["eval"]["metrics"]
        assert m["actual_result"] == "home"
        assert m["accuracy_1x2"] in (0, 1)
        assert 0.0 <= m["log_loss_1x2"] < 30.0
        assert 0.0 <= m["brier_1x2"] <= 2.0
        assert m["home_goal_error"] >= 0.0
        assert m["ou_2_5_accuracy"] in (0, 1)
        assert m["btts_accuracy"] in (0, 1)
        assert m["exact_score_hit"] in (0, 1)

    def test_draw_outcome(self, db):
        ctx = _evaluated(db, code="P27MD", hs=1, aws=1)
        assert ctx["eval"]["metrics"]["actual_result"] == "draw"

    def test_away_outcome(self, db):
        ctx = _evaluated(db, code="P27MA", hs=0, aws=2)
        assert ctx["eval"]["metrics"]["actual_result"] == "away"

    def test_probability_metrics_match_definitions(self, db):
        ctx = _evaluated(db, code="P27MV")
        m = ctx["eval"]["metrics"]
        p = ctx["pred"]["prediction_payload"]["prediction"]
        total = (p["home_win_probability"] + p["draw_probability"]
                 + p["away_win_probability"])
        norm = [p["home_win_probability"] / total,
                p["draw_probability"] / total, p["away_win_probability"] / total]
        idx = {"home": 0, "draw": 1, "away": 2}[m["actual_result"]]
        assert m["log_loss_1x2"] == pytest.approx(
            round(-math.log(max(norm[idx], 1e-12)), 6))
        assert m["brier_1x2"] == pytest.approx(
            round(sum((v - (1.0 if i == idx else 0.0)) ** 2
                      for i, v in enumerate(norm)), 6))
        assert m["accuracy_1x2"] == (
            1 if norm.index(max(norm)) == idx else 0)

    def test_unit_score_snapshot(self):
        payload = {
            "status": "valid",
            "home_win_probability": 0.6, "draw_probability": 0.25,
            "away_win_probability": 0.15,
            "expected_home_goals": 1.7, "expected_away_goals": 0.9,
            "expected_total_goals": 2.6,
            "over_2_5_probability": 0.55, "under_2_5_probability": 0.45,
            "btts_yes_probability": 0.5,
            "score_probabilities": {"2-1": 0.12, "1-0": 0.09},
        }
        m = score_snapshot(payload, 2, 1)
        assert m["actual_result"] == "home"
        assert m["accuracy_1x2"] == 1
        assert m["ou_2_5_accuracy"] == 1
        assert m["btts_accuracy"] == 1
        assert m["exact_score_hit"] == 1
        assert m["home_goal_error"] == pytest.approx(0.3)
        m2 = score_snapshot(payload, 0, 0)
        assert m2["actual_result"] == "draw"
        assert m2["accuracy_1x2"] == 0
        assert m2["ou_2_5_accuracy"] == 0
        assert m2["btts_accuracy"] == 0
        assert m2["exact_score_hit"] == 0

    def test_unknown_prediction_refuses(self, db):
        with pytest.raises(EvaluationBlocked) as exc:
            evaluate_prediction_snapshot(db, "pred_nope_123")
        assert exc.value.code == "UNKNOWN_PREDICTION"

    def test_unfinished_match_refuses(self, db):
        league = _league(db, "P27UF")
        home, away = _teams(db, league, "P27UF")
        now = _history(db, league, home.id, away.id, "P27UF")
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p27-P27UF-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        cutoff = now + timedelta(hours=1)
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        pred = execute_pre_match_prediction(db, target.id, cutoff)
        with pytest.raises(EvaluationBlocked) as exc:
            evaluate_prediction_snapshot(db, pred["prediction_id"])
        assert exc.value.code == "MATCH_NOT_FINISHED"


# -- immutability + idempotency ------------------------------------------------------------------------------

class TestEvalImmutabilityIdempotency:
    def test_repeated_evaluation_reuses(self, db):
        ctx = _evaluated(db, code="P27RE")
        again = evaluate_prediction_snapshot(db, ctx["pred"]["prediction_id"])
        assert again["cache_hit"] is True
        assert again["evaluation_id"] == ctx["eval"]["evaluation_id"]
        count = db.query(PredictionEvaluationRecord).filter_by(
            prediction_id=ctx["pred"]["prediction_id"]).count()
        assert count == 1

    def test_prediction_hash_stable_after_evaluation(self, db):
        from app.db.models.prediction_snapshots import (
            PreMatchPredictionSnapshot,
        )

        ctx = _evaluated(db, code="P27PH")
        row = db.query(PreMatchPredictionSnapshot).filter_by(
            prediction_id=ctx["pred"]["prediction_id"]).one()
        assert row.prediction_hash == ctx["pred"]["prediction_hash"]
        assert row.prediction_payload == ctx["pred"]["prediction_payload"]

    def test_corrected_outcome_new_version(self, db):
        ctx = _evaluated(db, code="P27CV")
        target = ctx["target"]
        target.home_score = 0
        target.away_score = 0
        db.commit()
        second = evaluate_prediction_snapshot(db, ctx["pred"]["prediction_id"])
        assert second["evaluation_id"] != ctx["eval"]["evaluation_id"]
        assert second["evaluation_version"] == (
            ctx["eval"]["evaluation_version"] + 1)
        assert second["metrics"]["actual_result"] == "draw"
        first = evaluation_to_dict(
            db.query(PredictionEvaluationRecord).filter_by(
                evaluation_id=ctx["eval"]["evaluation_id"]).one())
        assert first["metrics"]["actual_result"] == "home"

    def test_evaluation_key_deterministic(self):
        from app.services.prediction_evaluation.contracts import evaluation_key

        k1 = evaluation_key("pred_1", "hash_a")
        assert k1 == evaluation_key("pred_1", "hash_a")
        assert k1 != evaluation_key("pred_2", "hash_a")
        assert k1 != evaluation_key("pred_1", "hash_b")


# -- temporal safety --------------------------------------------------------------------------------------------

class TestTemporalSafety:
    def test_evaluation_cannot_mutate_prediction(self, db):
        import copy

        from app.db.models.prediction_snapshots import (
            PreMatchPredictionSnapshot,
        )

        ctx = _evaluated(db, code="P27TS")
        before = copy.deepcopy(ctx["pred"]["prediction_payload"])
        before_hash = ctx["pred"]["prediction_hash"]
        evaluate_prediction_snapshot(db, ctx["pred"]["prediction_id"])
        row = db.query(PreMatchPredictionSnapshot).filter_by(
            prediction_id=ctx["pred"]["prediction_id"]).one()
        assert row.prediction_payload == before
        assert row.prediction_hash == before_hash

    def test_post_match_data_excluded_from_features(self, db):
        from app.db.models.odds import OddsSnapshot

        ctx = _evaluated(db, code="P27TF")
        target, cutoff = ctx["target"], ctx["cutoff"]
        db.add(OddsSnapshot(match_id=target.id, market_type="1x2",
                            timestamp=cutoff + timedelta(hours=6)))
        db.commit()
        again = evaluate_prediction_snapshot(db, ctx["pred"]["prediction_id"])
        assert again["cache_hit"] is True
        # Feature snapshot for the original cutoff is unchanged.
        from app.services.prediction_execution.features import (
            build_cutoff_safe_snapshot,
        )

        rebuilt = build_cutoff_safe_snapshot(
            db, target.id, cutoff, ctx["pred"]["model_id"],
            ctx["pred"]["model_version"])
        assert rebuilt["snapshot_hash"] == ctx["pred"]["feature_snapshot_hash"]


# -- calibration + drift + aggregation -----------------------------------------------------------------------------

class TestCalibrationDriftAggregation:
    def _three(self, db, code, results):
        ctxs = []
        for i, (hs, aws) in enumerate(results):
            ctxs.append(_evaluated(db, code=f"{code}{i}", hs=hs, aws=aws))
        return ctxs

    def test_summary_counts_and_means(self, db):
        self._three(db, "P27S", [(2, 1), (1, 1), (0, 2)])
        summary = summarize_evaluations(db, competition=None)
        assert summary["metrics"]["sample_count"] >= 3
        assert 0.0 <= summary["metrics"]["accuracy_1x2"] <= 1.0
        assert summary["metrics"]["goal_rmse"] is not None
        assert summary["evaluation_period"]["from"] is not None

    def test_summary_filters(self, db):
        self._three(db, "P27SF", [(2, 0), (0, 0), (1, 2)])
        full = summarize_evaluations(db)
        none_match = summarize_evaluations(db, model_id="nope_v9")
        assert none_match["metrics"]["sample_count"] == 0
        assert none_match["metrics"]["accuracy_1x2"] is None
        assert full["metrics"]["sample_count"] >= 3

    def test_calibration_deterministic(self, db):
        self._three(db, "P27C", [(2, 1), (1, 1), (0, 1)])
        first = calibration_report(db, n_bins=10)
        second = calibration_report(db, n_bins=10)
        first.pop("generated_at", None)
        second.pop("generated_at", None)
        assert first == second
        assert set(first["per_outcome"]) == {"home", "draw", "away"}
        for outcome in ("home", "draw", "away"):
            assert first["per_outcome"][outcome]["reliability"]["n_bins"] == 10
            assert len(first["per_outcome"][outcome]["reliability"]["bins"]) == 10

    def test_calibration_empty(self, db):
        report = calibration_report(db, model_id="nope_v9")
        assert report["sample_count"] == 0
        for outcome in ("home", "draw", "away"):
            assert report["per_outcome"][outcome]["ece"] is None

    def test_drift_reports_samples(self, db):
        self._three(db, "P27D", [(2, 1), (1, 0), (0, 0)])
        report = drift_report(db, recent_n=50)
        assert report["recent_sample"] >= 3
        assert report["baseline_sample"] >= 3
        assert report["sufficient_sample"] is False  # < 20
        assert "differences_recent_minus_baseline" in report
        assert "no automatic degradation verdict" in report["note"]


# -- API -----------------------------------------------------------------------------------------------------------------

class TestEvaluationAPI:
    def test_match_evaluation(self, client, db):
        ctx = _evaluated(db, code="P27API")
        body = client.get(
            f"/api/v1/matches/{ctx['target'].id}/evaluation").json()
        assert body["match_status"] == "FINISHED"
        assert body["final_score"] == {"home": 2, "away": 1}
        assert body["evaluation_count"] == 1
        assert body["evaluations"][0]["evaluation_id"] == \
            ctx["eval"]["evaluation_id"]

    def test_match_evaluation_unknown(self, client):
        resp = client.get("/api/v1/matches/999999/evaluation")
        assert resp.status_code == 404

    def test_prediction_evaluation(self, client, db):
        ctx = _evaluated(db, code="P27APIP")
        body = client.get(
            f"/api/v1/prediction-snapshots/{ctx['pred']['prediction_id']}"
            "/evaluation").json()
        assert body["evaluation_count"] == 1

    def test_prediction_evaluation_empty(self, client, db):
        body = client.get(
            "/api/v1/prediction-snapshots/pred_nope_123/evaluation").json()
        assert body["evaluation_count"] == 0

    def test_summary_endpoint(self, client, db):
        _evaluated(db, code="P27APIS")
        body = client.get("/api/v1/evaluations/summary").json()
        assert body["metrics"]["sample_count"] >= 1

    def test_calibration_endpoint(self, client, db):
        _evaluated(db, code="P27APIC")
        body = client.get("/api/v1/evaluations/calibration").json()
        assert body["n_bins"] == 10
        assert "per_outcome" in body

    def test_drift_endpoint(self, client, db):
        _evaluated(db, code="P27APID")
        body = client.get("/api/v1/evaluations/drift?recent_n=50").json()
        assert body["recent_n_requested"] == 50
        assert "sufficient_sample" in body


# -- scheduler ----------------------------------------------------------------------------------------------------------------

class TestSchedulerIntegration:
    def test_job_registered(self):
        from app.services.scheduler import ALL_JOB_TYPES, get_job_config
        from app.services.scheduler.config import JOB_POST_MATCH_EVALUATION
        from app.services.scheduler.executors import get_executor

        assert JOB_POST_MATCH_EVALUATION in ALL_JOB_TYPES
        assert len(ALL_JOB_TYPES) == 10  # Phase 33 adds performance_evidence_refresh
        assert get_job_config(JOB_POST_MATCH_EVALUATION)["enabled"] is True
        assert get_executor(JOB_POST_MATCH_EVALUATION).__name__ == \
            "execute_post_match_evaluation"

    def test_executor_dry_run(self, db):
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import JOB_POST_MATCH_EVALUATION
        from app.services.scheduler.executors import get_executor

        league = _league(db, "P27SCHD")
        home, away = _teams(db, league, "P27SCHD")
        now = _history(db, league, home.id, away.id, "P27SCHD")
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p27-P27SCHD-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        cutoff = now + timedelta(hours=1)
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        execute_pre_match_prediction(db, target.id, cutoff)
        target.status = "FINISHED"
        target.home_score = 2
        target.away_score = 0
        db.commit()
        cfg = get_job_config(JOB_POST_MATCH_EVALUATION)
        cfg["competitions"] = ["P27SCHD"]
        result = get_executor(JOB_POST_MATCH_EVALUATION)(
            db, cfg, dry_run=True)
        assert result["status"] == "dry_run"
        assert target.id in result["due_match_ids"]

    def test_executor_skips_evaluated(self, db):
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import JOB_POST_MATCH_EVALUATION
        from app.services.scheduler.executors import get_executor

        ctx = _evaluated(db, code="P27SCHE")
        cfg = get_job_config(JOB_POST_MATCH_EVALUATION)
        cfg["competitions"] = ["P27SCHE"]
        result = get_executor(JOB_POST_MATCH_EVALUATION)(
            db, cfg, dry_run=True)
        assert ctx["target"].id not in result["due_match_ids"]

    def test_executor_skips_incomplete(self, db):
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import JOB_POST_MATCH_EVALUATION
        from app.services.scheduler.executors import get_executor

        league = _league(db, "P27SCHI")
        home, away = _teams(db, league, "P27SCHI")
        now = datetime.now(timezone.utc)
        m = Match(league_id=league.id, home_team_id=home.id,
                  away_team_id=away.id, kickoff_at=now + timedelta(hours=5),
                  status="SCHEDULED", provider="t",
                  provider_match_id="p27-P27SCHI-t")
        db.add(m)
        db.commit()
        cfg = get_job_config(JOB_POST_MATCH_EVALUATION)
        cfg["competitions"] = ["P27SCHI"]
        result = get_executor(JOB_POST_MATCH_EVALUATION)(
            db, cfg, dry_run=True)
        assert m.id not in result["due_match_ids"]


# -- migration chain ----------------------------------------------------------------------------------------------------------------

class TestMigrationChain:
    def _load(self, name):
        import importlib.util
        from pathlib import Path

        path = (Path(__file__).parent.parent / "migrations" / "versions"
                / f"{name}.py")
        spec = importlib.util.spec_from_file_location(f"mig_{name}", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_0012_chain(self):
        mod = self._load("0012_evaluation_records")
        assert mod.revision == "0012_evaluation_records"
        assert mod.down_revision == "0011_prediction_snapshots"
        assert mod.branch_labels is None

    def test_0012_links_into_chain(self):
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
        # 0012 must chain 0011 -> 0012; head ownership belongs to the
        # latest phase test (no branch divergence).
        assert revisions["0012_evaluation_records"] == \
            "0011_prediction_snapshots"
        down_revs = {v for v in revisions.values() if v is not None}
        heads = [r for r in revisions if r not in down_revs]
        assert len(heads) == 1

    def test_tables_exist(self, db):
        assert db.query(MatchOutcomeSnapshot).count() == 0
        assert db.query(PredictionEvaluationRecord).count() == 0


# -- golden regression ----------------------------------------------------------------------------------------------------------------

class TestGoldenRegression:
    def test_ensemble_values_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P27GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"
