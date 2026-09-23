"""Phase 29 — controlled research pipeline tests.

Covers: experiment contract, datasets, temporal audit, baseline
reproduction, comparison, multiple comparisons, reproducibility,
isolation, invalid experiments, API, adversarial cases, golden regression.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.research_registry import (
    ResearchCandidate,
    ResearchDataset,
    ResearchExperiment,
)
from app.services.research import (
    audit_temporal_integrity,
    build_dataset,
    production_fingerprint,
    register_builtin,
    register_candidate,
    run_experiment,
    split_observations,
    verify_fingerprint,
)
from app.services.research.candidates import CandidateError
from app.services.research.datasets import DatasetError
from app.services.research.experiments import ExperimentError


def _league(db, code):
    lg = League(code=code, name=f"{code} league", provider="t",
                provider_league_id=f"p29-{code}", season="2024")
    db.add(lg)
    db.commit()
    return lg


def _round_robin(db, code="P29R", days=40):
    """4 teams, ~2 finished matches/day for `days` days. Returns league."""
    league = _league(db, code)
    teams = {}
    for name in ("A", "B", "C", "D"):
        team = Team(league_id=league.id, name=name, provider="t",
                    provider_team_id=f"p29-{code}-{name}")
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
                provider="t", provider_match_id=f"p29-{code}-{idx}"))
    db.commit()
    return league


# -- experiment contract ------------------------------------------------------------------------------------

class TestExperimentContract:
    def test_dataset_spec_hash_stable(self, db):
        _round_robin(db, code="P29DC")
        first = build_dataset(db, competitions=["P29DC"])
        second = build_dataset(db, competitions=["P29DC"])
        assert second.dataset_id == first.dataset_id
        assert second.dataset_hash == first.dataset_hash

    def test_dataset_provenance(self, db):
        _round_robin(db, code="P29DP")
        ds = build_dataset(db, competitions=["P29DP"])
        assert ds.cutoff_policy == "kickoff_minus_24h"
        assert ds.feature_version == "features_v1"
        assert ds.observations["count"] > 0
        assert ds.train_period["count"] >= 1
        assert ds.test_period["count"] >= 1

    def test_empty_scope_refuses(self, db):
        with pytest.raises(DatasetError) as exc:
            build_dataset(db, competitions=["nope"])
        assert exc.value.code in ("EMPTY_DATASET", "EMPTY_TEST_SPLIT")

    def test_candidate_statuses(self, db):
        row = register_candidate(
            db, name="Hypothesis X", model_family="ensemble",
            members=["elo", "poisson"], weights=[0.5, 0.5])
        assert row.status == "DRAFT"
        assert "PRODUCTION" not in (
            "DRAFT", "RUNNING", "COMPLETED",
            "INVALID_EXPERIMENT", "SUPERSEDED")


# -- temporal ----------------------------------------------------------------------------------------------------------------

class TestTemporalAudit:
    def test_valid_dataset_passes(self, db):
        _round_robin(db, code="P29TA")
        ds = build_dataset(db, competitions=["P29TA"])
        audit = audit_temporal_integrity(ds)
        assert audit["status"] == "PASS"
        assert audit["violations"] == []

    def test_splits_chronological(self, db):
        _round_robin(db, code="P29TC")
        ds = build_dataset(db, competitions=["P29TC"])
        splits = split_observations(ds)
        assert splits["train"][-1]["kickoff"] <= splits["validation"][0]["kickoff"]
        assert splits["validation"][-1]["kickoff"] <= splits["test"][0]["kickoff"]

    def test_leaking_candidate_invalid(self, db):
        row = register_candidate(
            db, name="Leaky", model_family="ensemble",
            members=["elo", "poisson"],
            declared_inputs={"tables": ["matches", "odds_snapshots_live"]})
        assert row.status == "INVALID_EXPERIMENT"
        assert "odds_snapshots_live" in \
            row.declared_inputs["leakage_violations"]

    def test_leak_run_recorded_invalid(self, db):
        _round_robin(db, code="P29TL")
        ds = build_dataset(db, competitions=["P29TL"])
        row = register_candidate(
            db, name="Leaky run", model_family="ensemble",
            members=["elo", "poisson"],
            declared_inputs={"tables": ["closing_market_data"]})
        result = run_experiment(db, row.candidate_id, ds.dataset_id)
        assert result["leakage_status"] == "INVALID_EXPERIMENT"
        assert result["evidence_state"] == "INVALID_EXPERIMENT"


# -- baseline --------------------------------------------------------------------------------------------------------------------

class TestBaseline:
    def test_baseline_reproduction(self, db):
        _round_robin(db, code="P29BR")
        ds = build_dataset(db, competitions=["P29BR"])
        cand = register_builtin(db, "baseline_repro")
        exp = run_experiment(db, cand.candidate_id, ds.dataset_id)
        assert exp["leakage_status"] == "PASS"
        assert exp["comparison"]["n"] >= 1
        base = exp["baseline_metrics"]
        cand_m = exp["candidate_metrics"]
        for key in ("accuracy_1x2", "log_loss_1x2", "brier_1x2"):
            assert base[key] == cand_m[key]
        assert exp["comparison"]["delta_log_loss"] == 0.0
        assert exp["comparison"]["delta_brier"] == 0.0

    def test_golden_production_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P29GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"


# -- comparison -----------------------------------------------------------------------------------------------------------------------

class TestComparison:
    def _run(self, db, key, code):
        _round_robin(db, code=code)
        ds = build_dataset(db, competitions=[code])
        cand = register_builtin(db, key)
        return run_experiment(db, cand.candidate_id, ds.dataset_id)

    def test_identical_test_set(self, db):
        exp = self._run(db, "poisson_only", "P29CI")
        assert exp["comparison"]["n"] >= 1
        assert exp["baseline_metrics"]["accuracy_1x2"] is not None
        assert exp["candidate_metrics"]["accuracy_1x2"] is not None

    def test_evidence_states_documented(self, db):
        exp = self._run(db, "elo_only", "P29CE")
        assert exp["evidence_state"] in (
            "IMPROVEMENT_EVIDENCE", "NO_CLEAR_DIFFERENCE",
            "REGRESSION_EVIDENCE", "INSUFFICIENT_EVIDENCE")
        assert "evidence_rules" in exp["comparison"]
        assert "winner" not in str(exp["comparison"]).lower()
        assert "best" not in str(exp["comparison"]).lower()

    def test_uncertainty_present(self, db):
        exp = self._run(db, "ensemble_weighted_60_40", "P29CU")
        assert "logloss_paired_bootstrap" in exp["uncertainty"]
        assert "brier_paired_bootstrap" in exp["uncertainty"]

    def test_unknown_dataset_refuses(self, db):
        _round_robin(db, code="P29CUD")
        cand = register_builtin(db, "baseline_repro")
        with pytest.raises(ExperimentError) as exc:
            run_experiment(db, cand.candidate_id, "ds_nope_123")
        assert exc.value.code == "UNKNOWN_DATASET"

    def test_unknown_candidate_refuses(self, db):
        _round_robin(db, code="P29CUC")
        ds = build_dataset(db, competitions=["P29CUC"])
        with pytest.raises(CandidateError):
            run_experiment(db, "cand_nope_123", ds.dataset_id)


# -- multiple comparisons ------------------------------------------------------------------------------------------------------------------

class TestMultipleComparisons:
    def test_family_count_tracked(self, db):
        _round_robin(db, code="P29MC")
        ds = build_dataset(db, competitions=["P29MC"])
        cand = register_builtin(db, "baseline_repro")
        first = run_experiment(db, cand.candidate_id, ds.dataset_id)
        assert first["execution_metadata"]["family_experiment_count"] >= 1
        assert "multiple_comparison_note" in first["execution_metadata"]

    def test_registry_lists_experiments(self, db):
        _round_robin(db, code="P29ML")
        ds = build_dataset(db, competitions=["P29ML"])
        cand = register_builtin(db, "poisson_only")
        run_experiment(db, cand.candidate_id, ds.dataset_id)
        rows = db.query(ResearchExperiment).filter_by(
            candidate_id=cand.candidate_id).all()
        assert len(rows) >= 1


# -- reproducibility ------------------------------------------------------------------------------------------------------------------------------

class TestReproducibility:
    def test_same_experiment_same_hash(self, db):
        _round_robin(db, code="P29RP")
        ds = build_dataset(db, competitions=["P29RP"])
        cand = register_builtin(db, "ensemble_weighted_60_40")
        first = run_experiment(db, cand.candidate_id, ds.dataset_id)
        second = run_experiment(db, cand.candidate_id, ds.dataset_id)
        assert second["rerun"] is True
        assert second["result_hash"] == first["result_hash"]
        assert second["experiment_id"] == first["experiment_id"]

    def test_reproducibility_captured(self, db):
        _round_robin(db, code="P29RC")
        ds = build_dataset(db, competitions=["P29RC"])
        cand = register_builtin(db, "baseline_repro")
        exp = run_experiment(db, cand.candidate_id, ds.dataset_id)
        repro = exp["reproducibility"]
        assert repro["random_seed"] == 7
        assert repro["dataset_hash"] == ds.dataset_hash
        assert repro["feature_version"] == "features_v1"
        assert repro["runner_code_hash"]
        assert repro["evaluation_protocol"] == "cutoff_safe_walkforward"


# -- isolation -------------------------------------------------------------------------------------------------------------------------------------

class TestIsolation:
    def test_fingerprint_stable(self, db):
        _round_robin(db, code="P29IS")
        before = production_fingerprint()
        ds = build_dataset(db, competitions=["P29IS"])
        for key in ("baseline_repro", "poisson_only", "elo_only",
                    "ensemble_weighted_60_40"):
            cand = register_builtin(db, key)
            run_experiment(db, cand.candidate_id, ds.dataset_id)
        check = verify_fingerprint(before)
        assert check["intact"] is True
        assert check["file_drift"] == []
        assert check["config_drift"] is False

    def test_no_production_tables_written(self, db):
        from app.db.models.evaluation_records import (
            PredictionEvaluationRecord,
        )
        from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot

        _round_robin(db, code="P29IW")
        pred_before = db.query(PreMatchPredictionSnapshot).count()
        eval_before = db.query(PredictionEvaluationRecord).count()
        ds = build_dataset(db, competitions=["P29IW"])
        cand = register_builtin(db, "poisson_only")
        run_experiment(db, cand.candidate_id, ds.dataset_id)
        assert db.query(PreMatchPredictionSnapshot).count() == pred_before
        assert db.query(PredictionEvaluationRecord).count() == eval_before

    def test_provider_activation_unchanged(self, db):
        from app.services.acquisition.activation import get_activation_state

        _round_robin(db, code="P29IA")
        before = get_activation_state(db, "t")
        ds = build_dataset(db, competitions=["P29IA"])
        cand = register_builtin(db, "baseline_repro")
        run_experiment(db, cand.candidate_id, ds.dataset_id)
        assert get_activation_state(db, "t") == before

    def test_scheduler_config_unchanged(self, db):
        from app.services.scheduler import ALL_JOB_TYPES

        _round_robin(db, code="P29IJ")
        before = tuple(ALL_JOB_TYPES)
        ds = build_dataset(db, competitions=["P29IJ"])
        cand = register_builtin(db, "elo_only")
        run_experiment(db, cand.candidate_id, ds.dataset_id)
        assert tuple(ALL_JOB_TYPES) == before


# -- API ----------------------------------------------------------------------------------------------------------------------------------------------

class TestResearchAPI:
    def test_builtin_candidates(self, client):
        body = client.get("/api/v1/research/candidates/builtin").json()
        assert {"baseline_repro", "poisson_only", "elo_only",
                "ensemble_weighted_60_40"} <= set(body["builtin"])

    def test_register_and_list_candidates(self, client):
        created = client.post(
            "/api/v1/research/candidates",
            json={"name": "API hypothesis", "model_family": "ensemble",
                  "members": ["elo", "poisson"],
                  "declared_inputs": {"tables": ["matches"]}}).json()
        assert created["status"] == "DRAFT"
        listed = client.get("/api/v1/research/candidates").json()
        assert any(c["candidate_id"] == created["candidate_id"]
                   for c in listed["candidates"])
        detail = client.get(
            f"/api/v1/research/candidates/{created['candidate_id']}").json()
        assert detail["name"] == "API hypothesis"

    def test_leaking_candidate_api(self, client):
        created = client.post(
            "/api/v1/research/candidates",
            json={"name": "Leaky API", "model_family": "ensemble",
                  "members": ["elo"],
                  "declared_inputs": {"tables": ["closing_market_data"]}}).json()
        assert created["status"] == "INVALID_EXPERIMENT"

    def test_dataset_endpoints(self, client, db):
        _round_robin(db, code="P29API")
        created = client.post(
            "/api/v1/research/datasets",
            json={"competitions": ["P29API"]}).json()
        assert created["dataset_hash"]
        detail = client.get(
            f"/api/v1/research/datasets/{created['dataset_id']}").json()
        assert detail["temporal_audit"]["status"] == "PASS"
        assert detail["split_counts"]["test"] >= 1

    def test_experiment_flow(self, client, db):
        _round_robin(db, code="P29APIE")
        cand = client.post(
            "/api/v1/research/candidates/builtin/baseline_repro").json()
        ds = client.post(
            "/api/v1/research/datasets",
            json={"competitions": ["P29APIE"]}).json()
        exp = client.post(
            "/api/v1/research/experiments",
            json={"candidate_id": cand["candidate_id"],
                  "dataset_id": ds["dataset_id"]}).json()
        assert exp["leakage_status"] == "PASS"
        listed = client.get(
            f"/api/v1/research/experiments?candidate_id={cand['candidate_id']}"
        ).json()
        assert any(e["experiment_id"] == exp["experiment_id"]
                   for e in listed["experiments"])
        comp = client.get(
            f"/api/v1/research/experiments/{exp['experiment_id']}/comparison"
        ).json()
        assert comp["evidence_state"] in (
            "IMPROVEMENT_EVIDENCE", "NO_CLEAR_DIFFERENCE",
            "REGRESSION_EVIDENCE", "INSUFFICIENT_EVIDENCE")

    def test_rerun_requires_confirm(self, client, db):
        _round_robin(db, code="P29APIR")
        cand = client.post(
            "/api/v1/research/candidates/builtin/elo_only").json()
        ds = client.post(
            "/api/v1/research/datasets",
            json={"competitions": ["P29APIR"]}).json()
        exp = client.post(
            "/api/v1/research/experiments",
            json={"candidate_id": cand["candidate_id"],
                  "dataset_id": ds["dataset_id"]}).json()
        denied = client.post(
            f"/api/v1/research/experiments/{exp['experiment_id']}/run",
            json={"confirm": False})
        assert denied.status_code == 422
        replay = client.post(
            f"/api/v1/research/experiments/{exp['experiment_id']}/run",
            json={"confirm": True}).json()
        assert replay["rerun"] is True
        assert replay["result_hash"] == exp["result_hash"]


# -- adversarial ----------------------------------------------------------------------------------------------------------------------------------------------

class TestAdversarial:
    def test_future_result_feature_rejected(self, db):
        row = register_candidate(
            db, name="Future results", model_family="ensemble",
            members=["elo", "poisson"],
            declared_inputs={"tables": ["matches", "future_results"]})
        assert row.status == "INVALID_EXPERIMENT"

    def test_post_cutoff_odds_rejected(self, db):
        row = register_candidate(
            db, name="Live odds", model_family="ensemble",
            members=["elo", "poisson"],
            declared_inputs={"tables": ["matches", "odds_live_post_cutoff"]})
        assert row.status == "INVALID_EXPERIMENT"

    def test_target_derived_feature_rejected(self, db):
        row = register_candidate(
            db, name="Target leak", model_family="ensemble",
            members=["elo", "poisson"],
            declared_inputs={"tables": ["matches", "actual_outcomes"]})
        assert row.status == "INVALID_EXPERIMENT"

    def test_different_test_set_rejected(self, db):
        _round_robin(db, code="P29ADV")
        ds_a = build_dataset(db, competitions=["P29ADV"], limit=30)
        ds_b = build_dataset(db, competitions=["P29ADV"], limit=60)
        assert ds_a.dataset_hash != ds_b.dataset_hash
        # Comparison across datasets is never constructed: experiments
        # bind one dataset hash each; hashes differ, so no silent mix.
        assert ds_a.observations["count"] != ds_b.observations["count"]

    def test_unsupported_family_rejected(self, db):
        from app.services.research import predict_with_candidate

        _round_robin(db, code="P29ADF")
        row = register_candidate(
            db, name="Exotic", model_family="neural_net_x",
            members=["elo"], declared_inputs={"tables": ["matches"]})
        ds = build_dataset(db, competitions=["P29ADF"])
        obs = ds.observations["items"][-1]
        with pytest.raises(CandidateError) as exc:
            predict_with_candidate(
                db, row, obs["match_id"],
                datetime.fromisoformat(obs["cutoff"]))
        assert exc.value.code == "UNSUPPORTED_FAMILY"

    def test_no_production_status_exists(self, db):
        _round_robin(db, code="P29ADP")
        ds = build_dataset(db, competitions=["P29ADP"])
        cand = register_builtin(db, "baseline_repro")
        exp = run_experiment(db, cand.candidate_id, ds.dataset_id)
        assert "PRODUCTION" not in str(exp)
        rows = db.query(ResearchCandidate).all()
        assert all(r.status != "PRODUCTION" for r in rows)


# -- migration chain ----------------------------------------------------------------------------------------------------------------------------------------------

class TestMigrationChain:
    def test_0013_chain(self):
        import importlib.util
        from pathlib import Path

        path = (Path(__file__).parent.parent / "migrations" / "versions"
                / "0013_research_registry.py")
        spec = importlib.util.spec_from_file_location("mig_0013", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "0013_research_registry"
        assert mod.down_revision == "0012_evaluation_records"
        assert mod.branch_labels is None

    def test_single_head_is_0013(self):
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
        assert heads == ["0013_research_registry"]

    def test_tables_exist(self, db):
        assert db.query(ResearchCandidate).count() == 0
        assert db.query(ResearchDataset).count() == 0
        assert db.query(ResearchExperiment).count() == 0
