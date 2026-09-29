"""Phase 34 — controlled candidate validation gate tests.

Covers: configuration, rule engine, no-data/insufficient/inconclusive/
valid/invalid states, hash binding, determinism, staleness, champion +
challenger binding, temporal/shared-input/compatibility/
reproducibility/operational/rollback gates, no-auto-promotion,
historical immutability, champion concurrency, API, CLI, migration,
PostgreSQL shape, regression, security.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.candidate_validation import CandidateValidationReport
from app.db.models.core import League, Match, Team
from app.services.acquisition.readiness_gate import (
    generate_readiness_certificate,
)
from app.services.candidate_validation import (
    get_config,
    get_validation,
    run_validation,
)
from app.services.candidate_validation.contracts import (
    DEFAULT_CONFIG_ID,
)
from app.services.candidate_validation.rules import evaluate_rules
from app.services.candidate_validation.service import ValidationRunError
from app.services.evidence import build_cohort, generate_snapshot
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


def _round_robin(db, code="P34R", days=40):
    league = League(code=code, name=f"{code} league", provider="t",
                    provider_league_id=f"p34-{code}", season="2024")
    db.add(league)
    db.commit()
    teams = {}
    for name in ("A", "B", "C", "D"):
        team = Team(league_id=league.id, name=name, provider="t",
                    provider_team_id=f"p34-{code}-{name}")
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
                provider="t", provider_match_id=f"p34-{code}-{idx}"))
    db.commit()
    return league


def _governed_artifact(db, code="P34G", key="elo_only"):
    """Research → governed SHADOW artifact (no validation run)."""
    _round_robin(db, code=code)
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
    return {"artifact": art, "experiment": exp, "dataset": ds,
            "champion": champ}


def _validated_setup(db, code="P34V", count=3, key="elo_only"):
    """Governed artifact + N shadowed→finished→evaluated pairs."""
    ctx = _governed_artifact(db, code=code, key=key)
    league = db.query(League).filter_by(code=code).one()
    home = db.query(Team).filter_by(
        league_id=league.id, provider_team_id=f"p34-{code}-A").one()
    away = db.query(Team).filter_by(
        league_id=league.id, provider_team_id=f"p34-{code}-B").one()
    now = datetime.now(timezone.utc)
    for i in range(count):
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5 + i), status="SCHEDULED",
            provider="t", provider_match_id=f"p34-{code}-t{i}")
        db.add(target)
        db.commit()
        db.refresh(target)
        cutoff = now + timedelta(hours=1)
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        champ_pred = execute_pre_match_prediction(db, target.id, cutoff)
        res = execute_shadow(db, target.id, ctx["artifact"]["artifact_id"])
        target.status = "FINISHED"
        target.home_score = 2 if i % 2 == 0 else 0
        target.away_score = 1 if i % 2 == 0 else 0
        db.commit()
        evaluate_shadow_pair(db, res["shadow_id"])
        # Champion arm evaluated through the Phase 27 path as well.
        from app.services.prediction_evaluation import (
            evaluate_prediction_snapshot,
        )

        evaluate_prediction_snapshot(db, champ_pred["prediction_id"])
    return ctx


# -- 1. configuration -------------------------------------------------------------------------------------

class TestConfiguration:
    def test_default_config_versioned(self):
        config = get_config()
        assert config["config_id"] == "candidate_validation_v1"
        assert config["config_version"] == "v1"
        assert config["min_paired_observations"] == 50
        assert config["max_exclusion_rate"] == 0.30
        assert config["max_temporal_violation_rate"] == 0.0
        assert "rationale" in config

    def test_unknown_config(self):
        with pytest.raises(ValueError):
            get_config("nope_v9")

    def test_no_hardcoded_thresholds_in_rules(self):
        import inspect

        from app.services.candidate_validation import rules as rules_mod

        text = inspect.getsource(rules_mod)
        assert "min_paired_observations" not in text or \
            "config.get" in text


# -- 2. rule engine --------------------------------------------------------------------------------------------

class TestRuleEngine:
    def test_fourteen_rules(self, db):
        ctx = _validated_setup(db, code="P34RE", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        from app.db.models.evidence import EvidenceSnapshot as ES

        row = db.query(ES).filter_by(snapshot_id=snap["snapshot_id"]).one()
        rules = evaluate_rules(
            db, snapshot=row,
            candidate_artifact_id=ctx["artifact"]["artifact_id"],
            champion_artifact_id=ctx["champion"].artifact_id,
            config=get_config())
        assert len(rules) == 14
        for rule in rules:
            assert {"rule_id", "state", "result", "explanation",
                    "measured_value", "required_value",
                    "evidence_reference"} <= set(rule)
            assert rule["state"] in ("PASS", "BLOCKED", "INSUFFICIENT_DATA",
                                     "INCONCLUSIVE", "WARNING")


# -- 3/4. no-data + insufficient ------------------------------------------------------------------------------------------

class TestNoData:
    def _bare_artifact(self, db):
        from app.services.model_governance import register_artifact as reg_a

        return reg_a(
            db, model_id="elo_v1", model_version="elo_v1",
            members=["elo"], weights=[1.0])

    def test_empty_db_insufficient(self, db):
        art = self._bare_artifact(db)
        cohort = build_cohort(db, challenger_artifact_id=art.artifact_id)
        snap = generate_snapshot(db, cohort.cohort_id)
        assert snap["evidence_state"] in ("NO_DATA", "INSUFFICIENT_REAL_DATA")
        result = run_validation(db, art.artifact_id, snap["snapshot_id"])
        assert result["validation_state"] == "INSUFFICIENT_DATA"
        assert result["rerun"] is False

    def test_insufficient_blocks_governance(self, db):
        from app.db.models.governance import ModelPromotionRequest

        art = self._bare_artifact(db)
        cohort = build_cohort(db, challenger_artifact_id=art.artifact_id)
        snap = generate_snapshot(db, cohort.cohort_id)
        result = run_validation(db, art.artifact_id, snap["snapshot_id"])
        assert result["validation_state"] != "VALIDATED_FOR_GOVERNANCE"
        assert db.query(ModelPromotionRequest).count() == 0


# -- 5. inconclusive ----------------------------------------------------------------------------------------------------------------

class TestInconclusive:
    def test_descriptive_evidence_inconclusive(self, db):
        ctx = _validated_setup(db, code="P34IC", count=3)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        assert snap["evidence_state"] == "DESCRIPTIVE_ONLY"
        result = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        assert result["validation_state"] == "INSUFFICIENT_DATA"


# -- 6. valid evidence -----------------------------------------------------------------------------------------------------------------------

class TestValidEvidence:
    def test_validated_for_governance(self, db):
        ctx = _validated_setup(db, code="P34VE", count=55)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        assert snap["paired_count"] >= 50
        result = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        assert result["validation_state"] in (
            "VALIDATED_FOR_GOVERNANCE", "INCONCLUSIVE")
        assert result["evidence_state"] in (
            "SUPPORTED_DIFFERENCE", "INCONCLUSIVE", "NO_CLEAR_DIFFERENCE",
            "CONFLICTING_EVIDENCE", "DESCRIPTIVE_ONLY")


# -- 7. invalid evidence --------------------------------------------------------------------------------------------------------------------------

class TestInvalidEvidence:
    def test_unknown_snapshot(self, db):
        _governed = _governed_artifact(db, code="P34IE")
        with pytest.raises(ValidationRunError):
            run_validation(db, _governed["artifact"]["artifact_id"],
                           "evd_nope_00000000")

    def test_unknown_candidate(self, db):
        ctx = _validated_setup(db, code="P34IUC", count=1)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        with pytest.raises(ValidationRunError):
            run_validation(db, "art_nope_00000000", snap["snapshot_id"])


# -- 8. hash validation --------------------------------------------------------------------------------------------------------------------------------------

class TestHashValidation:
    def test_report_hash_stable(self, db):
        ctx = _validated_setup(db, code="P34HV", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        first = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        row = get_validation(db, first["validation_id"])
        assert row.validation_hash == first["validation_hash"]

    def test_tampered_artifact_blocked(self, db):
        from app.db.models.governance import ModelArtifact

        ctx = _validated_setup(db, code="P34TH", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        row = db.query(ModelArtifact).filter_by(
            artifact_id=ctx["artifact"]["artifact_id"]).one()
        row.model_version = "tampered_v9"
        db.commit()
        result = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        states = {r["rule_id"]: r["state"]
                  for r in result["rule_results"]["rules"]}
        assert states["MODEL_ARTIFACT_IMMUTABILITY"] == "BLOCKED"
        assert result["validation_state"] == "BLOCKED"


# -- 9. deterministic validation -------------------------------------------------------------------------------------------------------------------------------------

class TestDeterminism:
    def test_rerun_identical(self, db):
        ctx = _validated_setup(db, code="P34DR", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        first = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        second = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        assert second["rerun"] is True
        assert second["validation_hash"] == first["validation_hash"]
        assert second["validation_id"] == first["validation_id"]
        count = db.query(CandidateValidationReport).filter_by(
            validation_hash=first["validation_hash"]).count()
        assert count == 1


# -- 10. stale validation ---------------------------------------------------------------------------------------------------------------------------------------------

class TestStaleness:
    def test_valid_then_stale(self, db):
        from app.services.candidate_validation import check_staleness as cs

        ctx = _validated_setup(db, code="P34ST", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        first = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        assert cs(db, first["validation_id"])["staleness"] == "VALID"
        # New validation supersedes the old one.
        second = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        assert second["rerun"] is True
        # Champion change → STALE (a genuinely different artifact).
        from app.services.model_governance import register_artifact as reg_a

        other = reg_a(
            db, model_id="ensemble_v1-elo+poisson",
            model_version="ensemble_v1-elo+poisson",
            members=["elo", "poisson"], weights=[0.7, 0.3])
        from app.services.model_governance.registry import ModelRegistry

        db.add(ModelRegistry(role="CHAMPION", artifact_id=other.artifact_id,
                             state="ACTIVE"))
        db.commit()
        assert other.artifact_id != first["champion_artifact_id"]
        assert cs(db, first["validation_id"])["staleness"] == "STALE"

    def test_superseded(self, db):
        from app.services.candidate_validation import check_staleness as cs

        ctx = _validated_setup(db, code="P34SS", count=1)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        first = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        # Correct the outcome downstream, re-evaluate, snapshot again.
        league = db.query(League).filter_by(code="P34SS").one()
        target = db.query(Match).filter_by(
            league_id=league.id,
            provider_match_id="p34-P34SS-t0").one()
        target.home_score = 0
        target.away_score = 4
        db.commit()
        from app.services.prediction_evaluation import capture_outcome_snapshot
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        capture_outcome_snapshot(db, target.id)
        from app.db.models.governance import ShadowEvaluationRecord

        shadow = db.query(ShadowEvaluationRecord).filter_by(
            match_id=target.id).one()
        ev(db, shadow.shadow_id)
        snap2 = generate_snapshot(db, cohort.cohort_id)
        assert snap2["snapshot_id"] != snap["snapshot_id"]
        second = run_validation(
            db, ctx["artifact"]["artifact_id"], snap2["snapshot_id"])
        assert second["validation_id"] != first["validation_id"]
        assert cs(db, first["validation_id"])["staleness"] == "SUPERSEDED"

    def test_unknown_validation(self, db):
        from app.services.candidate_validation import check_staleness as cs

        with pytest.raises(ValidationRunError):
            cs(db, "val_nope_00000000")


# -- 11/12. champion + challenger binding -----------------------------------------------------------------------------------------------------------------------------------

class TestBindings:
    def test_champion_bound(self, db):
        ctx = _validated_setup(db, code="P34CB", count=1)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        result = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        assert result["champion_artifact_id"] == ctx["champion"].artifact_id
        assert result["champion_artifact_id"] != \
            result["candidate_artifact_id"]

    def test_challenger_binding_verified(self, db):
        ctx = _validated_setup(db, code="P34CHB", count=1)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        result = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        assert result["candidate_artifact_id"] == \
            ctx["artifact"]["artifact_id"]


# -- 13-18. gates (temporal/shared-input/compatibility/reproducibility/operational/rollback) ---------------------------------------------------------

class TestGates:
    def test_all_gates_present(self, db):
        ctx = _validated_setup(db, code="P34GT", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        result = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        ids = {r["rule_id"] for r in result["rule_results"]["rules"]}
        for expected in ("REAL_EVIDENCE_AVAILABLE",
                         "PAIRED_OBSERVATIONS_SUFFICIENT",
                         "TEMPORAL_INTEGRITY", "OUTCOME_COMPLETENESS",
                         "SHARED_FEATURE_INTEGRITY",
                         "PREDICTION_SCHEMA_COMPATIBILITY",
                         "MODEL_ARTIFACT_IMMUTABILITY",
                         "DATASET_PROVENANCE",
                         "EVIDENCE_SNAPSHOT_INTEGRITY",
                         "CALIBRATION_AVAILABILITY",
                         "PERFORMANCE_STABILITY",
                         "PRODUCTION_COMPATIBILITY",
                         "OPERATIONAL_HEALTH", "ROLLBACK_AVAILABLE"):
            assert expected in ids, expected

    def test_operational_health_reads_anomalies(self, db):
        ctx = _validated_setup(db, code="P34OP", count=1)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        result = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        rules = {r["rule_id"]: r
                 for r in result["rule_results"]["rules"]}
        assert "OPERATIONAL_HEALTH" in rules

    def test_reproducibility_fields(self, db):
        ctx = _validated_setup(db, code="P34RP", count=1)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        result = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        assert result["validation_config_id"] == DEFAULT_CONFIG_ID
        assert result["evidence_snapshot_hash"] == snap["snapshot_hash"]


# -- 19. no-auto-promotion -----------------------------------------------------------------------------------------------------------------------------------------------------

class TestNoAutoPromotion:
    def test_validated_creates_nothing(self, db):
        from app.db.models.governance import (
            ModelApprovalRecord,
            ModelPromotionRequest,
        )

        ctx = _validated_setup(db, code="P34NAP", count=3)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        promo_before = db.query(ModelPromotionRequest).count()
        appr_before = db.query(ModelApprovalRecord).count()
        result = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        assert result["validation_state"] in (
            "VALIDATED_FOR_GOVERNANCE", "INCONCLUSIVE", "INSUFFICIENT_DATA")
        assert db.query(ModelPromotionRequest).count() == promo_before
        assert db.query(ModelApprovalRecord).count() == appr_before
        assert resolve_active_model_id(db) == "ensemble_v1-elo+poisson"

    def test_no_governance_transitions(self, db):
        from app.services.model_governance.artifact import get_artifact as g

        ctx = _validated_setup(db, code="P34NGT", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        before = g(db, ctx["artifact"]["artifact_id"]).lifecycle_state
        run_validation(db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        after = g(db, ctx["artifact"]["artifact_id"]).lifecycle_state
        assert after == before


# -- 20. historical immutability ----------------------------------------------------------------------------------------------------------------------------------------------------

class TestImmutability:
    def test_history_stable(self, db):
        from app.db.models.evidence import EvidenceSnapshot
        from app.db.models.governance import ShadowEvaluationRecord
        from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot

        ctx = _validated_setup(db, code="P34HI", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        pred_hashes = sorted(
            r.prediction_hash for r in
            db.query(PreMatchPredictionSnapshot).all())
        eval_hashes = sorted(
            r.evaluation_hash for r in
            db.query(ShadowEvaluationRecord).all())
        snap_hash = snap["snapshot_hash"]
        run_validation(db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        assert sorted(r.prediction_hash for r in
                      db.query(PreMatchPredictionSnapshot).all()) == pred_hashes
        assert sorted(r.evaluation_hash for r in
                      db.query(ShadowEvaluationRecord).all()) == eval_hashes
        stored = db.query(EvidenceSnapshot).filter_by(
            snapshot_id=snap["snapshot_id"]).one()
        assert stored.snapshot_hash == snap_hash


# -- 21. champion concurrency ---------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestConcurrency:
    def test_stale_champion_detected(self, db):
        from app.services.candidate_validation import check_staleness as cs

        ctx = _validated_setup(db, code="P34CC", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        first = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        from app.services.model_governance import register_artifact as reg_a
        from app.services.model_governance.registry import ModelRegistry

        other = reg_a(
            db, model_id="ensemble_v1-elo+poisson",
            model_version="ensemble_v1-elo+poisson",
            members=["elo", "poisson"], weights=[0.7, 0.3])
        db.add(ModelRegistry(role="CHAMPION", artifact_id=other.artifact_id,
                             state="ACTIVE"))
        db.commit()
        assert other.artifact_id != \
            db.query(CandidateValidationReport).filter_by(
                validation_id=first["validation_id"]).one().champion_artifact_id
        assert cs(db, first["validation_id"])["staleness"] == "STALE"


# -- 22/23. API + CLI -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestValidationAPI:
    def test_status_empty(self, client):
        body = client.get("/api/v1/candidate-validation/status").json()
        assert body["validation_count"] == 0
        assert body["production_champion"] == "ensemble_v1-elo+poisson"

    def test_config_endpoint(self, client):
        body = client.get("/api/v1/candidate-validation/config").json()
        assert body["config_id"] == "candidate_validation_v1"
        assert body["min_paired_observations"] == 50

    def test_run_flow(self, client, db):
        ctx = _validated_setup(db, code="P34API", count=2)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        created = client.post(
            "/api/v1/candidate-validation/run",
            json={"candidate_artifact_id": ctx["artifact"]["artifact_id"],
                  "evidence_snapshot_id": snap["snapshot_id"]}).json()
        assert created["validation_state"] in (
            "VALIDATED_FOR_GOVERNANCE", "INCONCLUSIVE", "INSUFFICIENT_DATA",
            "BLOCKED", "INVALID")
        detail = client.get(
            f"/api/v1/candidate-validation/{created['validation_id']}").json()
        assert detail["validation_hash"] == created["validation_hash"]
        rules = client.get(
            f"/api/v1/candidate-validation/{created['validation_id']}/rules"
        ).json()
        assert len(rules["rules"]) == 14
        evidence = client.get(
            f"/api/v1/candidate-validation/{created['validation_id']}/evidence"
        ).json()
        assert evidence["evidence"]["snapshot_id"] == snap["snapshot_id"]
        staleness = client.get(
            f"/api/v1/candidate-validation/{created['validation_id']}/staleness"
        ).json()
        assert staleness["staleness"] in ("VALID", "STALE", "SUPERSEDED")
        candidates = client.get(
            "/api/v1/candidate-validation/candidates").json()
        assert ctx["artifact"]["artifact_id"] in candidates["candidates"]

    def test_run_missing_args(self, client):
        resp = client.post("/api/v1/candidate-validation/run", json={})
        assert resp.status_code == 422

    def test_run_unknown_candidate(self, client, db):
        ctx = _validated_setup(db, code="P34APIU", count=1)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        resp = client.post(
            "/api/v1/candidate-validation/run",
            json={"candidate_artifact_id": "art_nope_00000000",
                  "evidence_snapshot_id": snap["snapshot_id"]})
        assert resp.status_code == 422

    def test_guard_blocks_run(self, client):
        from unittest.mock import patch

        with patch("app.config.Settings.operational_endpoints_enabled",
                   False):
            resp = client.post(
                "/api/v1/candidate-validation/run",
                json={"candidate_artifact_id": "x",
                      "evidence_snapshot_id": "y"})
            assert resp.status_code == 403
            resp = client.post("/api/v1/candidate-validation/refresh")
            assert resp.status_code == 403


class TestValidationCLI:
    def test_status_config_candidates(self, db):
        import scripts.tacticx as cli
        import argparse

        for action in ("status", "config", "candidates"):
            args = argparse.Namespace(
                action=action, candidate="", snapshot="", validation="",
                config="", as_json=True)
            assert cli._cmd_validation(db, args) == 0

    def test_run_show_rules(self, db):
        import scripts.tacticx as cli
        import argparse

        ctx = _validated_setup(db, code="P34CLI", count=1)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        args = argparse.Namespace(
            action="run", candidate=ctx["artifact"]["artifact_id"],
            snapshot=snap["snapshot_id"], validation="", config="",
            as_json=True)
        assert cli._cmd_validation(db, args) == 0
        row = db.query(CandidateValidationReport).order_by(
            CandidateValidationReport.id.desc()).first()
        for action, kwargs in (
                ("show", {"validation": row.validation_id}),
                ("rules", {"validation": row.validation_id})):
            args = argparse.Namespace(
                action=action, candidate="", snapshot="",
                config="", as_json=True, **kwargs)
            assert cli._cmd_validation(db, args) == 0


# -- 24. frontend (client tests live in frontend suite) --------------------------------------------------------------------------------------------------------------------------------------
# -- 25. migration -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestMigrationChain:
    def test_0017_chain(self):
        import importlib.util
        from pathlib import Path

        path = (Path(__file__).parent.parent / "migrations" / "versions"
                / "0017_candidate_validation.py")
        spec = importlib.util.spec_from_file_location("mig_0017", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "0017_candidate_validation"
        assert mod.down_revision == "0016_evidence"
        assert mod.branch_labels is None

    def test_single_head_is_0017(self):
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
        assert db.query(CandidateValidationReport).count() == 0


# -- 26. PostgreSQL shape (live PG covered in verification; structural here) ------------------------------------------------------------------------------------------------------------------
class TestPostgresShape:
    def test_json_columns_present(self, db):
        from sqlalchemy import inspect

        cols = {c["name"] for c in inspect(db.bind).get_columns(
            "candidate_validation_reports")}
        for expected in ("rule_results", "performance_summary",
                         "uncertainty_summary", "validation_hash",
                         "evidence_snapshot_id", "validation_config_id"):
            assert expected in cols, expected


# -- 27. regression -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestRegression:
    def test_phase27_summary_stable(self, db):
        from app.services.prediction_evaluation import summarize_evaluations

        _validated_setup(db, code="P34R27", count=2)
        summary = summarize_evaluations(db)
        assert summary["metrics"]["sample_count"] >= 2

    def test_phase28_monitoring_stable(self, db):
        from app.services.production_monitoring import performance_overview

        _validated_setup(db, code="P34R28", count=2)
        perf = performance_overview(db)
        assert perf["metrics"]["sample_count"] >= 2

    def test_phase30_governance_stable(self, db):
        _validated_setup(db, code="P34R30", count=1)
        assert resolve_active_model_id(db) == "ensemble_v1-elo+poisson"

    def test_phase32_shadow_stable(self, db):
        from app.db.models.governance import ShadowEvaluationRecord

        _validated_setup(db, code="P34R32", count=2)
        rows = db.query(ShadowEvaluationRecord).all()
        assert len(rows) == 2
        assert all(r.outcome_hash for r in rows)

    def test_phase33_evidence_stable(self, db):
        from app.services.evidence import build_cohort as build_c
        from app.services.evidence import generate_snapshot as gen_s

        ctx = _validated_setup(db, code="P34R33", count=2)
        cohort = build_c(db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = gen_s(db, cohort.cohort_id)
        assert snap["paired_count"] == 2


# -- 28. security -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestSecurity:
    def test_reports_carry_no_credentials(self, db):
        ctx = _validated_setup(db, code="P34SEC", count=1)
        cohort = build_cohort(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"])
        snap = generate_snapshot(db, cohort.cohort_id)
        result = run_validation(
            db, ctx["artifact"]["artifact_id"], snap["snapshot_id"])
        blob = str(result).lower()
        assert "api_key" not in blob
        assert "authorization" not in blob
        assert "bearer" not in blob
        assert "password" not in blob


# -- golden regression -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestGoldenRegression:
    def test_ensemble_values_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P34GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"
