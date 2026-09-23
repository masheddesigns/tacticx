"""Phase 28 — production monitoring, analysis & data-quality tests.

Covers: performance, coverage, calibration, drift, uncertainty, data
quality, providers, anomalies, API read-only enforcement, adversarial
integrity, golden regression.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.evaluation_records import (
    MatchOutcomeSnapshot,
    PredictionEvaluationRecord,
)
from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot
from app.services.acquisition.readiness_gate import (
    generate_readiness_certificate,
)
from app.services.prediction_evaluation import evaluate_prediction_snapshot
from app.services.prediction_execution import execute_pre_match_prediction
from app.services.production_monitoring import (
    calibration_detail,
    coverage_funnel,
    data_quality_report,
    detect_anomalies,
    drift_analysis,
    performance_overview,
    provider_report,
    temporal_windows,
)
from app.services.production_monitoring.contracts import (
    bootstrap_mean_ci,
    safe_rate,
    wilson_interval,
)


def _league(db, code, season="2024"):
    lg = League(code=code, name=f"{code} league", provider="t",
                provider_league_id=f"p28-{code}", season=season)
    db.add(lg)
    db.commit()
    return lg


def _teams(db, league, code):
    home = Team(league_id=league.id, name="Home", provider="t",
                provider_team_id=f"p28-{code}-h")
    away = Team(league_id=league.id, name="Away", provider="t",
                provider_team_id=f"p28-{code}-a")
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
                provider_match_id=f"p28-{code}-{tag}{i}"))
    db.commit()
    return now


def _evaluated(db, code="P28E", hs=2, aws=1, season="2024"):
    league = _league(db, code, season=season)
    home, away = _teams(db, league, code)
    now = _history(db, league, home.id, away.id, code)
    target = Match(
        league_id=league.id, home_team_id=home.id, away_team_id=away.id,
        kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
        provider="t", provider_match_id=f"p28-{code}-target")
    db.add(target)
    db.commit()
    db.refresh(target)
    cutoff = now + timedelta(hours=1)
    generate_readiness_certificate(db, target.id, cutoff=cutoff)
    pred = execute_pre_match_prediction(db, target.id, cutoff)
    target.status = "FINISHED"
    target.home_score = hs
    target.away_score = aws
    db.commit()
    ev = evaluate_prediction_snapshot(db, pred["prediction_id"])
    return {"target": target, "pred": pred, "eval": ev}


# -- performance ----------------------------------------------------------------------------------------

class TestPerformance:
    def test_overview_metrics_with_denominators(self, db):
        _evaluated(db, code="P28P")
        perf = performance_overview(db)
        m = perf["metrics"]
        assert m["sample_count"] >= 1
        assert 0.0 <= m["accuracy_1x2"] <= 1.0
        assert m["log_loss_1x2"] >= 0.0
        assert 0.0 <= m["brier_1x2"] <= 2.0
        assert m["goal_mae"] is not None
        assert perf["metric_definition_version"] == "monitoring_metrics_v1"

    def test_empty_scope(self, db):
        perf = performance_overview(db, model_id="nope_v9")
        assert perf["metrics"]["sample_count"] == 0
        assert perf["metrics"]["accuracy_1x2"] is None

    def test_windows_and_ranges(self, db):
        _evaluated(db, code="P28W")
        out = temporal_windows(db)
        assert set(out["windows"]) == {"20", "50", "100"}
        assert out["windows"]["20"]["metrics"]["sample_count"] >= 1
        assert out["windows"]["20"]["sufficient_sample"] is False
        now = datetime.now(timezone.utc)
        ranged = temporal_windows(
            db, date_from=now - timedelta(days=1),
            date_to=now + timedelta(days=1))
        assert "custom_range" in ranged

    def test_competition_season_filters(self, db):
        _evaluated(db, code="P28F1")
        _evaluated(db, code="P28F2", season="2023")
        by_comp = performance_overview(db, competition="P28F1")
        assert by_comp["metrics"]["sample_count"] >= 1
        by_season = performance_overview(db, season="2023")
        assert by_season["metrics"]["sample_count"] >= 1
        assert performance_overview(db, competition="nope")["metrics"][
            "sample_count"] == 0


# -- coverage ----------------------------------------------------------------------------------------------

class TestCoverage:
    def test_funnel_counts_and_rates(self, db):
        _evaluated(db, code="P28CV")
        funnel = coverage_funnel(db)
        assert funnel["eligible_count"] >= 7
        assert funnel["ready_count"] >= 1
        assert funnel["predicted_count"] >= 1
        assert funnel["completed_count"] >= 1
        assert funnel["evaluated_count"] >= 1
        assert 0.0 <= funnel["prediction_readiness_rate"] <= 1.0
        assert 0.0 <= funnel["prediction_coverage_rate"] <= 1.0
        assert funnel["denominators"]["prediction_coverage_rate"] == \
            funnel["ready_count"]

    def test_zero_denominator_returns_none(self, db):
        funnel = coverage_funnel(db, competition="nope")
        assert funnel["eligible_count"] == 0
        assert funnel["prediction_readiness_rate"] is None
        assert funnel["prediction_coverage_rate"] is None
        assert funnel["completion_rate"] is None
        assert funnel["evaluation_coverage_rate"] is None

    def test_partial_lifecycle(self, db):
        league = _league(db, "P28PL")
        home, away = _teams(db, league, "P28PL")
        now = _history(db, league, home.id, away.id, "P28PL")
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p28-P28PL-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        generate_readiness_certificate(
            db, target.id, cutoff=now + timedelta(hours=1))
        funnel = coverage_funnel(db, competition="P28PL")
        assert funnel["ready_count"] >= 1
        assert funnel["predicted_count"] == 0
        assert funnel["completion_rate"] is None
        assert funnel["evaluation_coverage_rate"] is None


# -- calibration -----------------------------------------------------------------------------------------------

class TestCalibration:
    def test_deterministic_buckets(self, db):
        _evaluated(db, code="P28CB")
        first = calibration_detail(db)
        assert first["bucket_definition_version"] == "reliability_buckets_v1"
        assert first["n_bins"] == 10
        for outcome in ("home", "draw", "away"):
            entry = first["per_outcome"][outcome]
            assert len(entry["buckets"]) == 10
            assert entry["sample_count"] >= 1
            assert entry["ece"] is None or entry["ece"] >= 0.0
            assert entry["mce"] is None or entry["mce"] >= 0.0
            if entry["ece"] is not None:
                assert entry["mce"] >= entry["ece"]

    def test_empty_dataset(self, db):
        report = calibration_detail(db, model_id="nope_v9")
        assert report["sample_count"] == 0
        for outcome in ("home", "draw", "away"):
            assert report["per_outcome"][outcome]["ece"] is None
            assert report["per_outcome"][outcome]["mce"] is None

    def test_bucket_contract(self, db):
        _evaluated(db, code="P28BC")
        report = calibration_detail(db)
        bucket = report["per_outcome"]["home"]["buckets"][0]
        assert {"bin_low", "bin_high", "count", "mean_predicted",
                "empirical_rate", "frequency_ci"} <= set(bucket)


# -- drift ----------------------------------------------------------------------------------------------------------------

class TestDrift:
    def test_insufficient_data_state(self, db):
        _evaluated(db, code="P28DI")
        report = drift_analysis(db)
        assert report["state"] == "INSUFFICIENT_DATA"
        assert report["recent_sample"] < 20

    def test_stable_or_watch_with_samples(self, db):
        for i in range(21):
            _evaluated(db, code=f"P28DS{i:02d}",
                       hs=2 if i % 2 == 0 else 0,
                       aws=1 if i % 2 == 0 else 0)
        report = drift_analysis(db)
        assert report["state"] in ("STABLE", "WATCH")
        assert report["recent_sample"] >= 20
        assert "relative_differences" in report
        assert "degradation verdict" in \
            report["state_rules"]["WATCH"]

    def test_never_degraded_verdict(self, db):
        _evaluated(db, code="P28DN")
        report = drift_analysis(db)
        assert report["state"] != "DEGRADED"
        assert "DEGRADED" not in report["state_rules"]


# -- uncertainty -----------------------------------------------------------------------------------------------------------------

class TestUncertainty:
    def test_wilson_basic(self):
        ci = wilson_interval(6, 10)
        assert ci["method"] == "wilson"
        assert ci["lo"] <= ci["proportion"] <= ci["hi"]
        assert 0.0 <= ci["lo"] and ci["hi"] <= 1.0

    def test_wilson_boundary(self):
        ci = wilson_interval(0, 5)
        assert ci["lo"] == 0.0
        assert ci["hi"] > 0.0
        full = wilson_interval(5, 5)
        assert full["hi"] == 1.0
        assert full["lo"] < 1.0

    def test_wilson_zero_trials(self):
        assert wilson_interval(0, 0) is None

    def test_wilson_deterministic(self):
        assert wilson_interval(7, 23) == wilson_interval(7, 23)

    def test_bootstrap_deterministic(self):
        vals = [0.1, 0.2, 0.15, 0.3, 0.25]
        first = bootstrap_mean_ci(vals)
        assert first == bootstrap_mean_ci(vals)
        assert first["lo"] <= first["hi"]
        assert bootstrap_mean_ci([]) is None

    def test_safe_rate(self):
        assert safe_rate(3, 4) == 0.75
        assert safe_rate(0, 0) is None
        assert safe_rate(5, 0) is None


# -- data quality -------------------------------------------------------------------------------------------------------------------

class TestDataQuality:
    def test_readiness_states(self, db):
        _evaluated(db, code="P28DQ")
        from app.services.production_monitoring.data_quality import (
            readiness_quality,
        )

        rep = readiness_quality(db)
        assert rep["certificate_count"] >= 1
        assert rep["state"] in ("DATA_VALID", "DATA_DEGRADED",
                                "DATA_UNAVAILABLE", "DATA_BLOCKED")

    def test_empty_is_unavailable(self, db):
        from app.services.production_monitoring.data_quality import (
            readiness_quality,
        )

        assert readiness_quality(db)["state"] == "DATA_UNAVAILABLE"

    def test_outcome_gaps(self, db):
        _evaluated(db, code="P28DG")
        from app.services.production_monitoring.data_quality import (
            outcome_gaps,
        )

        gaps = outcome_gaps(db)
        assert gaps["finished_predicted_count"] >= 1
        assert gaps["missing_outcomes"] == 0

    def test_full_report(self, db):
        _evaluated(db, code="P28DF")
        report = data_quality_report(db)
        assert {"readiness", "conflicts", "outcome_gaps"} <= set(report)
        assert report["state"] in ("DATA_VALID", "DATA_DEGRADED",
                                   "DATA_UNAVAILABLE", "DATA_BLOCKED")


# -- providers ----------------------------------------------------------------------------------------------------------------------------

class TestProviders:
    def test_scoped_report(self, db):
        _evaluated(db, code="P28PV")
        report = provider_report(db, competition="P28PV")
        assert "t" in report["providers"]
        entry = report["providers"]["t"]
        assert entry["competition"] == "P28PV"
        assert entry["fixture_count"] >= 1
        assert entry["activation_state"] in (
            "UNAVAILABLE", "DISCOVERY", "PROBING", "QUALIFYING",
            "QUALIFIED", "ACTIVE", "DEGRADED", "REVOKED",
            "candidate", "validated", "active", "degraded", "disabled")

    def test_fixture_result_counts(self, db):
        _evaluated(db, code="P28PC")
        report = provider_report(db)
        assert report["fixture_count"] >= 7
        assert report["result_count"] >= 7


# -- anomalies -------------------------------------------------------------------------------------------------------------------------------

class TestAnomalies:
    def test_normal_data_no_critical(self, db):
        _evaluated(db, code="P28AN")
        result = detect_anomalies(db)
        critical = [a for a in result["anomalies"]
                    if a["severity"] == "CRITICAL"]
        assert critical == []
        for anomaly in result["anomalies"]:
            assert {"anomaly_id", "anomaly_type", "severity",
                    "detected_at", "observed_value", "reference_value",
                    "sample_size", "evidence", "scope"} <= set(anomaly)

    def test_zero_generation_critical(self, db):
        league = _league(db, "P28AZ")
        home, away = _teams(db, league, "P28AZ")
        now = _history(db, league, home.id, away.id, "P28AZ")
        for i in range(10):
            target = Match(
                league_id=league.id, home_team_id=home.id,
                away_team_id=away.id,
                kickoff_at=now + timedelta(hours=5 + i), status="SCHEDULED",
                provider="t", provider_match_id=f"p28-P28AZ-t{i}")
            db.add(target)
            db.commit()
            db.refresh(target)
            generate_readiness_certificate(
                db, target.id, cutoff=now + timedelta(hours=1))
        result = detect_anomalies(db)
        types = [a["anomaly_type"] for a in result["anomalies"]]
        assert "ZERO_PREDICTION_GENERATION" in types

    def test_block_spike(self, db):
        for i in range(10):
            league = _league(db, f"P28AB{i:02d}")
            home, away = _teams(db, league, f"P28AB{i:02d}")
            now = datetime.now(timezone.utc)
            target = Match(
                league_id=league.id, home_team_id=home.id,
                away_team_id=away.id,
                kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
                provider="t", provider_match_id=f"p28-P28AB{i:02d}-t")
            db.add(target)
            db.commit()
            db.refresh(target)
            generate_readiness_certificate(
                db, target.id, cutoff=now + timedelta(hours=1))
        result = detect_anomalies(db)
        types = [a["anomaly_type"] for a in result["anomalies"]]
        assert "READINESS_BLOCK_SPIKE" in types

    def test_insufficient_samples_no_anomaly(self, db):
        result = detect_anomalies(db)
        assert result["anomaly_count"] == 0


# -- API -------------------------------------------------------------------------------------------------------------------------------------

class TestMonitoringAPI:
    def _seed(self, db):
        return _evaluated(db, code="P28API")

    def test_overview(self, client, db):
        self._seed(db)
        body = client.get("/api/v1/monitoring/overview").json()
        assert body["evaluation_count"] >= 1
        assert body["accuracy"] is not None
        assert "rank" not in body and "winner" not in body
        assert body["drift_state"] in ("STABLE", "WATCH", "INSUFFICIENT_DATA")

    def test_performance(self, client, db):
        self._seed(db)
        body = client.get("/api/v1/monitoring/performance").json()
        assert {"20", "50", "100"} <= set(body["windows"])
        assert "breakdown" in body

    def test_performance_invalid_range(self, client):
        resp = client.get(
            "/api/v1/monitoring/performance?start_date=2024-02-01T00:00:00"
            "&end_date=2024-01-01T00:00:00")
        assert resp.status_code == 422

    def test_calibration(self, client, db):
        self._seed(db)
        body = client.get("/api/v1/monitoring/calibration").json()
        assert body["n_bins"] == 10
        assert set(body["per_outcome"]) == {"home", "draw", "away"}

    def test_drift(self, client, db):
        self._seed(db)
        body = client.get("/api/v1/monitoring/drift?window=50").json()
        assert body["state"] in ("STABLE", "WATCH", "INSUFFICIENT_DATA")
        assert "degraded" not in body["state"].lower()

    def test_data_quality(self, client, db):
        self._seed(db)
        body = client.get("/api/v1/monitoring/data-quality").json()
        assert "readiness" in body and "state" in body

    def test_coverage(self, client, db):
        self._seed(db)
        body = client.get("/api/v1/monitoring/coverage").json()
        assert body["eligible_count"] >= 1
        assert body["evaluated_count"] >= 1

    def test_providers(self, client, db):
        self._seed(db)
        body = client.get("/api/v1/monitoring/providers").json()
        assert "providers" in body

    def test_anomalies(self, client, db):
        self._seed(db)
        body = client.get("/api/v1/monitoring/anomalies").json()
        assert "anomalies" in body and "anomaly_count" in body

    def test_read_only_no_mutation(self, client, db):
        ctx = self._seed(db)
        pred_before = db.query(PreMatchPredictionSnapshot).count()
        eval_before = db.query(PredictionEvaluationRecord).count()
        out_before = db.query(MatchOutcomeSnapshot).count()
        for path in ("/api/v1/monitoring/overview",
                     "/api/v1/monitoring/performance",
                     "/api/v1/monitoring/calibration",
                     "/api/v1/monitoring/drift",
                     "/api/v1/monitoring/data-quality",
                     "/api/v1/monitoring/coverage",
                     "/api/v1/monitoring/providers",
                     "/api/v1/monitoring/anomalies",
                     f"/api/v1/matches/{ctx['target'].id}/evaluation"):
            resp = client.get(path)
            assert resp.status_code == 200, path
        assert db.query(PreMatchPredictionSnapshot).count() == pred_before
        assert db.query(PredictionEvaluationRecord).count() == eval_before
        assert db.query(MatchOutcomeSnapshot).count() == out_before
        row = db.query(PreMatchPredictionSnapshot).filter_by(
            prediction_id=ctx["pred"]["prediction_id"]).one()
        assert row.prediction_hash == ctx["pred"]["prediction_hash"]


# -- adversarial / integrity ----------------------------------------------------------------------------------------------------------------------

class TestAdversarialIntegrity:
    def _two(self, db):
        first = _evaluated(db, code="P28X1", hs=2, aws=0)
        second = _evaluated(db, code="P28X2", hs=0,  aws=0)
        return first, second

    def test_reordering_stable(self, db):
        from app.services.prediction_evaluation.aggregation import (
            summarize_evaluations,
        )

        self._two(db)
        base = summarize_evaluations(db)["metrics"]
        # Re-read in reverse id order; means must match.
        rows = db.query(PredictionEvaluationRecord).order_by(
            PredictionEvaluationRecord.id.desc()).all()
        from app.services.prediction_evaluation.aggregation import _mean

        for key in ("accuracy_1x2", "log_loss_1x2", "brier_1x2"):
            vals = [r.metrics.get(key) for r in rows
                    if isinstance(r.metrics, dict)]
            assert _mean(vals) == base[key]

    def test_unevaluated_excluded(self, db):
        self._two(db)
        from app.services.prediction_evaluation.aggregation import (
            summarize_evaluations,
        )

        before = summarize_evaluations(db)["metrics"]["sample_count"]
        # Add an unevaluated prediction: finish another match + predict.
        league = _league(db, "P28XU")
        home, away = _teams(db, league, "P28XU")
        now = _history(db, league, home.id, away.id, "P28XU")
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p28-P28XU-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        cutoff = now + timedelta(hours=1)
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        execute_pre_match_prediction(db, target.id, cutoff)
        after = summarize_evaluations(db)["metrics"]["sample_count"]
        assert after == before

    def test_missing_outcome_not_failure(self, db):
        league = _league(db, "P28XM")
        home, away = _teams(db, league, "P28XM")
        now = _history(db, league, home.id, away.id, "P28XM")
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now - timedelta(hours=1), status="POSTPONED",
            provider="t", provider_match_id="p28-P28XM-target")
        db.add(target)
        db.commit()
        funnel = coverage_funnel(db, competition="P28XM")
        assert funnel["completed_count"] == 0
        assert funnel["evaluated_count"] == 0
        assert funnel["evaluation_coverage_rate"] is None

    def test_records_unchanged_by_monitoring(self, db):
        ctx = _evaluated(db, code="P28XK")
        pred_hash = ctx["pred"]["prediction_hash"]
        eval_hash = ctx["eval"]["evaluation_hash"]
        performance_overview(db)
        temporal_windows(db)
        calibration_detail(db)
        drift_analysis(db)
        coverage_funnel(db)
        data_quality_report(db)
        detect_anomalies(db)
        row = db.query(PreMatchPredictionSnapshot).filter_by(
            prediction_id=ctx["pred"]["prediction_id"]).one()
        assert row.prediction_hash == pred_hash
        erow = db.query(PredictionEvaluationRecord).filter_by(
            evaluation_id=ctx["eval"]["evaluation_id"]).one()
        assert erow.evaluation_hash == eval_hash

    def test_monitoring_deterministic(self, db):
        _evaluated(db, code="P28XD")
        first = performance_overview(db)["metrics"]
        second = performance_overview(db)["metrics"]
        assert first == second
        assert coverage_funnel(db) == coverage_funnel(db)

    def test_model_config_and_activation_unchanged(self, db):
        from app.services.acquisition.activation import get_activation_state
        from app.services.acquisition.readiness_gate import get_prediction_config

        _evaluated(db, code="P28XC")
        cfg_before = get_prediction_config("ensemble_v1-elo+poisson")
        act_before = get_activation_state(db, "t")
        performance_overview(db)
        detect_anomalies(db)
        assert get_prediction_config("ensemble_v1-elo+poisson") == cfg_before
        assert get_activation_state(db, "t") == act_before


# -- golden regression -----------------------------------------------------------------------------------------------------------------------------------

class TestGoldenRegression:
    def test_ensemble_values_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P28GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"
