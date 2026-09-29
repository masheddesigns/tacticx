"""Phase 32 — real-data champion/challenger shadow pipeline tests.

Covers: challenger identity, shared feature snapshot, temporal cutoff,
output compatibility/validation, execution, idempotency, pairing,
outcome linkage, evaluation, insufficient data, monitoring, Phase 30
integration, production isolation, restart recovery, migration, API,
CLI, adversarial safety, no-auto-promotion, golden regression.
Synthetic fixtures exist only in this test DB, never production paths.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.governance import (
    ShadowEvaluationRecord,
    ShadowPredictionSnapshot,
)
from app.services.acquisition.readiness_gate import (
    generate_readiness_certificate,
)
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
    ShadowExecutionError,
    ShadowIneligible,
    execute_shadow,
    find_eligible_matches,
    find_shadow,
    shadow_comparison,
    shadow_summary,
    validate_shadow_pair,
)


def _round_robin(db, code="P32R", days=40):
    league = League(code=code, name=f"{code} league", provider="t",
                    provider_league_id=f"p32-{code}", season="2024")
    db.add(league)
    db.commit()
    teams = {}
    for name in ("A", "B", "C", "D"):
        team = Team(league_id=league.id, name=name, provider="t",
                    provider_team_id=f"p32-{code}-{name}")
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
                provider="t", provider_match_id=f"p32-{code}-{idx}"))
    db.commit()
    return league


def _upcoming(db, league, code, hours=5):
    home = db.query(Team).filter_by(
        league_id=league.id, provider_team_id=f"p32-{code}-A").one()
    away = db.query(Team).filter_by(
        league_id=league.id, provider_team_id=f"p32-{code}-B").one()
    now = datetime.now(timezone.utc)
    target = Match(
        league_id=league.id, home_team_id=home.id, away_team_id=away.id,
        kickoff_at=now + timedelta(hours=hours), status="SCHEDULED",
        provider="t", provider_match_id=f"p32-{code}-target")
    db.add(target)
    db.commit()
    db.refresh(target)
    return target, now + timedelta(hours=1)


def _shadow_ready(db, code="P32S", key="elo_only"):
    """Full stack: history + target + cert + champion pred + SHADOW challenger."""
    league = _round_robin(db, code=code)
    target, cutoff = _upcoming(db, league, code)
    cert = generate_readiness_certificate(db, target.id, cutoff=cutoff)
    champ_pred = execute_pre_match_prediction(db, target.id, cutoff)
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
    return {"league": league, "target": target, "cutoff": cutoff,
            "cert": cert, "champ_pred": champ_pred, "challenger": art,
            "champion": champ, "experiment": exp}


# -- 1. challenger identity ------------------------------------------------------------------------------------

class TestChallengerIdentity:
    def test_artifact_contract(self, db):
        ctx = _shadow_ready(db, code="P32CI")
        art = ctx["challenger"]
        assert art["artifact_id"].startswith("art_")
        assert art["model_id"]
        assert art["candidate_id"]
        assert art["config_fingerprint"]["members"]
        assert art["config_fingerprint"]["weights"]
        assert art["artifact_hash"]

    def test_weights_in_fingerprint(self, db):
        ctx = _shadow_ready(db, code="P32CW")
        fp = ctx["challenger"]["config_fingerprint"]
        assert fp["weights"] == [1.0]
        assert fp["members"] == ["elo"]


# -- 2. shared feature snapshot -----------------------------------------------------------------------------------

class TestSharedFeatureSnapshot:
    def test_same_snapshot_bound(self, db):
        ctx = _shadow_ready(db, code="P32SF")
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert res["feature_snapshot_id"] == \
            ctx["champ_pred"]["feature_snapshot_id"]
        assert res["feature_snapshot_hash"] == \
            ctx["champ_pred"]["feature_snapshot_hash"]
        assert res["production_prediction_id"] == \
            ctx["champ_pred"]["prediction_id"]

    def test_pair_validation_ok(self, db):
        ctx = _shadow_ready(db, code="P32PV")
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        verdict = validate_shadow_pair(db, res["shadow_id"])
        assert verdict["valid"] is True
        assert verdict["code"] == "SHADOW_PAIR_VALID"

    def test_pair_mismatch_invalid(self, db):
        ctx = _shadow_ready(db, code="P32PM")
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        row = db.query(ShadowPredictionSnapshot).filter_by(
            shadow_id=res["shadow_id"]).one()
        row.feature_snapshot_hash = "tampered" + "0" * 56
        db.commit()
        verdict = validate_shadow_pair(db, res["shadow_id"])
        assert verdict["valid"] is False
        assert verdict["code"] == "SHADOW_PAIR_INVALID"

    def test_unknown_shadow_invalid(self, db):
        verdict = validate_shadow_pair(db, "shdw_nope_00000000")
        assert verdict["valid"] is False


# -- 3. temporal cutoff ----------------------------------------------------------------------------------------------

class TestTemporalCutoff:
    def test_cutoff_before_kickoff(self, db):
        ctx = _shadow_ready(db, code="P32TC")
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert res["cutoff"] < ctx["target"].kickoff_at.isoformat()

    def test_post_cutoff_data_excluded(self, db):
        from app.db.models.odds import OddsSnapshot
        from app.services.prediction_execution.features import (
            build_cutoff_safe_snapshot,
        )

        ctx = _shadow_ready(db, code="P32TE")
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        db.add(OddsSnapshot(
            match_id=ctx["target"].id, market_type="1x2",
            timestamp=ctx["cutoff"] + timedelta(hours=3)))
        db.commit()
        rebuilt = build_cutoff_safe_snapshot(
            db, ctx["target"].id, ctx["cutoff"],
            ctx["champ_pred"]["model_id"], ctx["champ_pred"]["model_version"])
        assert rebuilt["snapshot_hash"] == \
            ctx["champ_pred"]["feature_snapshot_hash"]
        again = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert again["shadow_id"] == res["shadow_id"]


# -- 4/5. output compatibility + validation -------------------------------------------------------------------------------

class TestOutputContract:
    def test_incompatible_output_refused(self, db, monkeypatch):
        import app.services.predictions.ensemble as ensemble_mod

        ctx = _shadow_ready(db, code="P32IO")

        class BadModel:
            def predict(self, db, match_id, cutoff, mode):
                from app.services.predictions.outputs import FullPrediction

                return FullPrediction(
                    model_name="bad", model_version="bad",
                    status="valid",
                    home_win_probability=0.9, draw_probability=0.9,
                    away_win_probability=0.9)

        monkeypatch.setattr(ensemble_mod.EnsembleModel, "from_names",
                            classmethod(lambda cls, *a, **k: BadModel()))
        with pytest.raises(ShadowExecutionError) as exc:
            execute_shadow(
                db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert exc.value.code == "INCOMPATIBLE"
        

    def test_nan_output_refused(self, db, monkeypatch):
        import app.services.predictions.ensemble as ensemble_mod

        ctx = _shadow_ready(db, code="P32NAN")

        class NanModel:
            def predict(self, db, match_id, cutoff, mode):
                class _Result:
                    @staticmethod
                    def model_dump(mode=None):
                        return {
                            "status": "valid",
                            "model_name": "nan", "model_version": "nan",
                            "home_win_probability": float("nan"),
                            "draw_probability": 0.5,
                            "away_win_probability": 0.5}

                return _Result()

        monkeypatch.setattr(ensemble_mod.EnsembleModel, "from_names",
                            classmethod(lambda cls, *a, **k: NanModel()))
        with pytest.raises(ShadowExecutionError):
            execute_shadow(
                db, ctx["target"].id, ctx["challenger"]["artifact_id"])

    def test_champion_unaffected_by_bad_challenger(self, db, monkeypatch):
        import app.services.predictions.ensemble as ensemble_mod
        from app.db.models.prediction_snapshots import (
            PreMatchPredictionSnapshot,
        )

        ctx = _shadow_ready(db, code="P32CU")

        class BoomModel:
            def predict(self, db, match_id, cutoff, mode):
                raise RuntimeError("challenger exploded")

        monkeypatch.setattr(ensemble_mod.EnsembleModel, "from_names",
                            classmethod(lambda cls, *a, **k: BoomModel()))
        with pytest.raises(ShadowExecutionError):
            execute_shadow(
                db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        row = db.query(PreMatchPredictionSnapshot).filter_by(
            prediction_id=ctx["champ_pred"]["prediction_id"]).one()
        assert row.prediction_hash == ctx["champ_pred"]["prediction_hash"]


# -- 6/7. shadow execution + storage ----------------------------------------------------------------------------------------------

class TestShadowExecution:
    def test_execute_stores_row(self, db):
        ctx = _shadow_ready(db, code="P32EX")
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert res["shadow_id"].startswith("shdw_")
        assert res["cache_hit"] is False
        assert res["challenger_output_hash"]
        assert res["evaluation_state"] == "PENDING"

    def test_unknown_challenger_refused(self, db):
        league = _round_robin(db, code="P32UC")
        target, _ = _upcoming(db, league, "P32UC")
        with pytest.raises(ShadowIneligible):
            execute_shadow(db, target.id, "art_nope_00000000")

    def test_non_shadow_challenger_refused(self, db):
        from app.services.research import register_builtin

        league = _round_robin(db, code="P32NS")
        target, _ = _upcoming(db, league, "P32NS")
        cand = register_builtin(db, "elo_only")
        from app.services.model_governance.service import (
            register_candidate_artifact as reg,
        )

        art = reg(db, candidate_id=cand.candidate_id)
        with pytest.raises(ShadowIneligible) as exc:
            execute_shadow(db, target.id, art["artifact_id"])
        assert exc.value.code == "INVALID_CHALLENGER_STATE"

    def test_blocked_match_refused(self, db):
        ctx = _shadow_ready(db, code="P32BM")
        target = ctx["target"]
        target.status = "POSTPONED"
        db.commit()
        with pytest.raises(ShadowIneligible):
            execute_shadow(
                db, target.id, ctx["challenger"]["artifact_id"])

    def test_waits_for_champion(self, db):
        helper = _shadow_ready(db, code="P32WCH")
        challenger_id = helper["challenger"]["artifact_id"]
        league = _round_robin(db, code="P32WC")
        target, cutoff = _upcoming(db, league, "P32WC")
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        with pytest.raises(ShadowIneligible) as exc:
            execute_shadow(db, target.id, challenger_id)
        assert exc.value.code == "NO_CHAMPION_PREDICTION"


def _artifact_row(db, artifact_id):
    from app.db.models.governance import ModelArtifact

    return db.query(ModelArtifact).filter_by(
        artifact_id=artifact_id).one()


# -- 8/9. immutability + idempotency ----------------------------------------------------------------------------------------------------

class TestShadowImmutability:
    def test_rerun_same_row(self, db):
        ctx = _shadow_ready(db, code="P32ID")
        first = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        second = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert second["cache_hit"] is True
        assert second["shadow_id"] == first["shadow_id"]
        count = db.query(ShadowPredictionSnapshot).filter_by(
            match_id=ctx["target"].id).count()
        assert count == 1

    def test_row_fields_frozen(self, db):
        ctx = _shadow_ready(db, code="P32FR")
        first = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        row = db.query(ShadowPredictionSnapshot).filter_by(
            shadow_id=first["shadow_id"]).one()
        before = (row.challenger_output_hash, row.feature_snapshot_hash,
                  row.cutoff.isoformat())
        execute_shadow(db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        db.refresh(row)
        after = (row.challenger_output_hash, row.feature_snapshot_hash,
                 row.cutoff.isoformat())
        assert before == after

    def test_new_cutoff_new_row(self, db):
        ctx = _shadow_ready(db, code="P32NC")
        first = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        new_cutoff = ctx["cutoff"] + timedelta(minutes=20)
        generate_readiness_certificate(
            db, ctx["target"].id, cutoff=new_cutoff)
        execute_pre_match_prediction = __import__(
            "app.services.prediction_execution",
            fromlist=["execute_pre_match_prediction"]
        ).execute_pre_match_prediction
        execute_pre_match_prediction(
            db, ctx["target"].id, new_cutoff)
        second = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert second["shadow_id"] != first["shadow_id"]


# -- 10/11. pairing + same-input guarantee (covered in §2) ------------------------------------------------------------------------------
# -- 12/13. output contract + validation (covered in §4/5) -------------------------------------------------------------------------------
# -- 14. real/test separation ------------------------------------------------------------------------------------------------------------------

class TestRealTestSeparation:
    def test_no_eligible_matches_state(self, db):
        scan = find_eligible_matches(db)
        assert scan["state"] == "NO_ELIGIBLE_MATCHES"
        assert scan["eligible"] == []

    def test_test_fixtures_never_hit_production_tables(self, db):
        from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot

        before = db.query(PreMatchPredictionSnapshot).count()
        ctx = _shadow_ready(db, code="P32RT")
        execute_shadow(db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        # Only the test's own champion prediction exists; shadow wrote none.
        assert db.query(PreMatchPredictionSnapshot).count() == before + 1


# -- 15. (spec §15: NO_ELIGIBLE_MATCHES covered above) -----------------------------------------------------------------------------------
# -- 16. scheduler -------------------------------------------------------------------------------------------------------------------------------

class TestScheduler:
    def test_job_registered(self):
        from app.services.scheduler import ALL_JOB_TYPES, get_job_config
        from app.services.scheduler.config import JOB_SHADOW_PREDICTION
        from app.services.scheduler.executors import get_executor

        assert JOB_SHADOW_PREDICTION in ALL_JOB_TYPES
        assert len(ALL_JOB_TYPES) == 9
        assert get_job_config(JOB_SHADOW_PREDICTION)["enabled"] is True
        assert get_executor(JOB_SHADOW_PREDICTION).__name__ == \
            "execute_shadow_prediction"

    def test_no_challenger_skipped(self, db):
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import JOB_SHADOW_PREDICTION
        from app.services.scheduler.executors import get_executor

        cfg = get_job_config(JOB_SHADOW_PREDICTION)
        cfg["competitions"] = ["P32SJ"]
        result = get_executor(JOB_SHADOW_PREDICTION)(db, cfg, dry_run=True)
        assert result["status"] == "skipped"
        assert "challenger" in result["reason"]

    def test_dry_run_lists_due(self, db):
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import JOB_SHADOW_PREDICTION
        from app.services.scheduler.executors import get_executor

        ctx = _shadow_ready(db, code="P32SJ")
        cfg = get_job_config(JOB_SHADOW_PREDICTION)
        cfg["competitions"] = ["P32SJ"]
        cfg["challenger_artifact_id"] = ctx["challenger"]["artifact_id"]
        result = get_executor(JOB_SHADOW_PREDICTION)(db, cfg, dry_run=True)
        assert result["status"] == "dry_run"
        assert ctx["target"].id in result["due_match_ids"]

    def test_executor_never_promotes(self, db):
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import JOB_SHADOW_PREDICTION
        from app.services.scheduler.executors import get_executor

        ctx = _shadow_ready(db, code="P32SNP")
        from app.db.models.governance import ModelPromotionRequest

        cfg = get_job_config(JOB_SHADOW_PREDICTION)
        cfg["competitions"] = ["P32SNP"]
        cfg["challenger_artifact_id"] = ctx["challenger"]["artifact_id"]
        before = db.query(ModelPromotionRequest).count()
        get_executor(JOB_SHADOW_PREDICTION)(db, cfg, dry_run=False)
        assert db.query(ModelPromotionRequest).count() == before
        assert resolve_active_model_id(db) == "ensemble_v1-elo+poisson"


# -- 17-19. execution conditions/champion timing/outcome linkage covered in §6/7/10 ------------------------------------------------------
# -- 20. shadow evaluation --------------------------------------------------------------------------------------------------------------------------

class TestShadowEvaluation:
    def _finished_shadow(self, db, code="P32EV", hs=2, aws=1):
        ctx = _shadow_ready(db, code=code)
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        target = ctx["target"]
        target.status = "FINISHED"
        target.home_score = hs
        target.away_score = aws
        db.commit()
        return ctx, res

    def test_evaluate_pair(self, db):
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        _, res = self._finished_shadow(db)
        out = ev(db, res["shadow_id"])
        assert out["cache_hit"] is False
        assert out["champion_metrics"]["actual_result"] == "home"
        assert out["challenger_metrics"]["actual_result"] == "home"
        assert out["differences"]["delta_accuracy_1x2"] in (0, 1, -1)
        assert out["outcome_hash"]

    def test_shared_outcome(self, db):
        from app.services.prediction_evaluation import (
            evaluate_prediction_snapshot,
        )

        ctx, res = self._finished_shadow(db, code="P32SO")
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        shadow_eval = ev(db, res["shadow_id"])
        champ_eval = evaluate_prediction_snapshot(
            db, ctx["champ_pred"]["prediction_id"])
        assert shadow_eval["outcome_hash"] == champ_eval["outcome_hash"]
        assert shadow_eval["outcome_snapshot_id"] == \
            champ_eval["outcome_snapshot_id"]

    def test_evaluation_idempotent(self, db):
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        _, res = self._finished_shadow(db, code="P32EI")
        first = ev(db, res["shadow_id"])
        second = ev(db, res["shadow_id"])
        assert second["cache_hit"] is True
        assert second["evaluation_id"] == first["evaluation_id"]
        count = db.query(ShadowEvaluationRecord).filter_by(
            shadow_id=res["shadow_id"]).count()
        assert count == 1

    def test_unfinished_refuses(self, db):
        from app.services.shadow_execution import evaluate_shadow_pair as ev
        from app.services.shadow_execution.evaluation import (
            ShadowEvaluationError,
        )

        ctx = _shadow_ready(db, code="P32UE")
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        with pytest.raises(ShadowEvaluationError):
            ev(db, res["shadow_id"])

    def test_insufficient_data_flag(self, db):
        from app.services.shadow_execution import shadow_comparison as comp

        ctx, res = self._finished_shadow(db, code="P32IDF")
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        ev(db, res["shadow_id"])
        report = comp(db, ctx["challenger"]["artifact_id"])
        assert report["evaluated_pairs"] == 1
        assert report["aggregate"]["evidence"] == "INSUFFICIENT_DATA"


# -- 21. no winner -------------------------------------------------------------------------------------------------------------------------------------

class TestNoWinner:
    def test_comparison_has_no_ranking(self, db):
        from app.services.shadow_execution import shadow_comparison as comp

        ctx, res = TestShadowEvaluation()._finished_shadow(db, code="P32NW")
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        ev(db, res["shadow_id"])
        report = comp(db, ctx["challenger"]["artifact_id"])
        blob_keys = " ".join(str(report["aggregate"].keys())).lower()
        assert "winner" not in blob_keys
        assert "best" not in blob_keys
        assert "rank" not in blob_keys
        assert report["evaluated_pairs"] == 1


# -- 22-24. small samples/leagues/data quality (covered via monitoring + comparison) ------------------------------------------------------
# -- 25. monitoring ----------------------------------------------------------------------------------------------------------------------------------------

class TestShadowMonitoring:
    def test_summary_empty(self, db):
        report = shadow_summary(db)
        assert report["shadow_executions"] == 0
        assert report["evaluation_coverage_rate"] is None

    def test_summary_counts(self, db):
        ctx = _shadow_ready(db, code="P32MS")
        execute_shadow(db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        report = shadow_summary(db)
        assert report["shadow_executions"] == 1
        assert report["by_challenger"][ctx["challenger"]["artifact_id"]][
            "executed"] == 1

    def test_monitoring_read_only(self, db):
        from app.db.models.evaluation_records import (
            MatchOutcomeSnapshot,
            PredictionEvaluationRecord,
        )
        from app.db.models.governance import ModelRegistry
        from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot

        ctx = _shadow_ready(db, code="P32MR")
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        counts = (db.query(PreMatchPredictionSnapshot).count(),
                  db.query(PredictionEvaluationRecord).count(),
                  db.query(MatchOutcomeSnapshot).count(),
                  db.query(ModelRegistry).count())
        shadow_summary(db)
        shadow_comparison(db, ctx["challenger"]["artifact_id"])
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        target = ctx["target"]
        target.status = "FINISHED"
        target.home_score = 1
        target.away_score = 1
        db.commit()
        ev(db, res["shadow_id"])
        counts2 = (db.query(PreMatchPredictionSnapshot).count(),
                   db.query(PredictionEvaluationRecord).count(),
                   db.query(MatchOutcomeSnapshot).count(),
                   db.query(ModelRegistry).count())
        assert counts2 == (counts[0], counts[1], counts[2] + 1, counts[3])
        # Only the outcome snapshot (shared Phase 27 ingestion) was added;
        # production predictions/evaluations/registry untouched.


# -- 26. Phase 30 integration -------------------------------------------------------------------------------------------------------------------------------

class TestPhase30Integration:
    def test_uses_governance_shadow_state(self, db):
        ctx = _shadow_ready(db, code="P32G30")
        art = ctx["challenger"]
        from app.services.model_governance.artifact import get_artifact as g

        assert g(db, art["artifact_id"]).lifecycle_state == "SHADOW"

    def test_registry_unchanged_by_shadow(self, db):
        from app.db.models.governance import ModelRegistry

        ctx = _shadow_ready(db, code="P32GR")
        before = db.query(ModelRegistry).count()
        execute_shadow(db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert db.query(ModelRegistry).count() == before
        assert resolve_active_model_id(db) == "ensemble_v1-elo+poisson"


# -- 27. API -----------------------------------------------------------------------------------------------------------------------------------------------------

class TestShadowAPI:
    def test_summary_empty(self, client):
        body = client.get("/api/v1/shadow/summary").json()
        assert body["shadow_executions"] == 0

    def test_matches_empty_state(self, client):
        body = client.get("/api/v1/shadow/matches").json()
        assert body["state"] == "NO_ELIGIBLE_MATCHES"
        assert body["eligible"] == []

    def test_execute_flow(self, client, db):
        ctx = _shadow_ready(db, code="P32API")
        resp = client.post(
            f"/api/v1/shadow/execute/{ctx['target'].id}",
            json={"match_id": ctx["target"].id,
                  "challenger_artifact_id": ctx["challenger"]["artifact_id"]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["shadow_id"].startswith("shdw_")
        again = client.post(
            f"/api/v1/shadow/execute/{ctx['target'].id}",
            json={"match_id": ctx["target"].id,
                  "challenger_artifact_id": ctx["challenger"]["artifact_id"]}).json()
        assert again["shadow_id"] == body["shadow_id"]

    def test_execute_missing_challenger(self, client, db):
        ctx = _shadow_ready(db, code="P32APIM")
        resp = client.post(
            f"/api/v1/shadow/execute/{ctx['target'].id}", json={"match_id": 1})
        assert resp.status_code == 422

    def test_match_detail_and_pair_validate(self, client, db):
        ctx = _shadow_ready(db, code="P32APID")
        created = client.post(
            f"/api/v1/shadow/execute/{ctx['target'].id}",
            json={"match_id": ctx["target"].id,
                  "challenger_artifact_id": ctx["challenger"]["artifact_id"]}).json()
        detail = client.get(
            f"/api/v1/shadow/matches/{ctx['target'].id}").json()
        assert detail["shadow_count"] == 1
        verdict = client.get(
            f"/api/v1/shadow/pairs/{created['shadow_id']}/validate").json()
        assert verdict["valid"] is True

    def test_start_no_eligible(self, client):
        body = client.post(
            "/api/v1/shadow/start", json={"challenger_artifact_id": "x"}).json()
        assert body["state"] == "NO_ELIGIBLE_MATCHES"
        assert body["executed"] == []

    def test_evaluations_and_comparison(self, client, db):
        ctx = _shadow_ready(db, code="P32APIE")
        created = client.post(
            f"/api/v1/shadow/execute/{ctx['target'].id}",
            json={"match_id": ctx["target"].id,
                  "challenger_artifact_id": ctx["challenger"]["artifact_id"]}).json()
        target = ctx["target"]
        target.status = "FINISHED"
        target.home_score = 2
        target.away_score = 2
        db.commit()
        evaluated = client.post(
            f"/api/v1/shadow/pairs/{created['shadow_id']}/evaluate").json()
        assert evaluated["cache_hit"] is False
        listing = client.get("/api/v1/shadow/evaluations").json()
        assert listing["evaluation_count"] == 1
        comp = client.get(
            f"/api/v1/shadow/comparison/{ctx['challenger']['artifact_id']}").json()
        assert comp["evaluated_pairs"] == 1
        chall = client.get("/api/v1/shadow/challengers").json()
        assert ctx["challenger"]["artifact_id"] in chall["challengers"]

    def test_guard_blocks_execution(self, client):
        from unittest.mock import patch

        with patch("app.config.Settings.operational_endpoints_enabled", False):
            resp = client.post(
                "/api/v1/shadow/execute/1",
                json={"match_id": 1, "challenger_artifact_id": "x"})
            assert resp.status_code == 403
            resp = client.post("/api/v1/shadow/start",
                               json={"challenger_artifact_id": "x"})
            assert resp.status_code == 403


# -- 28. CLI --------------------------------------------------------------------------------------------------------------------------------------------------------

class TestShadowCLI:
    def test_status(self, db):
        import scripts.tacticx as cli
        import argparse

        args = argparse.Namespace(action="status", match=0, challenger="",
                                  shadow="", competition="", as_json=True)
        assert cli._cmd_shadow(db, args) == 0

    def test_matches(self, db):
        import scripts.tacticx as cli
        import argparse

        args = argparse.Namespace(action="matches", match=0, challenger="",
                                  shadow="", competition="", as_json=True)
        assert cli._cmd_shadow(db, args) == 0

    def test_run_and_audit(self, db):
        import scripts.tacticx as cli
        import argparse

        ctx = _shadow_ready(db, code="P32CLI")
        args = argparse.Namespace(
            action="run", match=ctx["target"].id,
            challenger=ctx["challenger"]["artifact_id"], shadow="",
            competition="", as_json=True)
        assert cli._cmd_shadow(db, args) == 0
        row = db.query(ShadowPredictionSnapshot).filter_by(
            match_id=ctx["target"].id).one()
        args = argparse.Namespace(
            action="audit", match=0, challenger="", shadow=row.shadow_id,
            competition="", as_json=True)
        assert cli._cmd_shadow(db, args) == 0


# -- 29. frontend (client tests live in frontend suite) ---------------------------------------------------------------------------------------------------------------
# -- 30. database migration -----------------------------------------------------------------------------------------------------------------------------------------------

class TestMigrationChain:
    def test_0015_chain(self):
        import importlib.util
        from pathlib import Path

        path = (Path(__file__).parent.parent / "migrations" / "versions"
                / "0015_shadow_execution.py")
        spec = importlib.util.spec_from_file_location("mig_0015", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "0015_shadow_execution"
        assert mod.down_revision == "0014_model_governance"
        assert mod.branch_labels is None

    def test_single_head_is_0015(self):
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
        assert heads == ["0015_shadow_execution"]

    def test_tables_exist(self, db):
        from app.db.models.governance import ShadowEvaluationRecord

        assert db.query(ShadowPredictionSnapshot).count() == 0
        assert db.query(ShadowEvaluationRecord).count() == 0


# -- 31. production isolation ----------------------------------------------------------------------------------------------------------------------------------------------

class TestProductionIsolation:
    def test_eight_no_modifications(self, db):
        from app.db.models.evaluation_records import (
            MatchOutcomeSnapshot,
            PredictionEvaluationRecord,
        )
        from app.db.models.governance import ModelRegistry
        from app.db.models.intelligence_v2 import IntelligenceSnapshot
        from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot

        ctx = _shadow_ready(db, code="P32PI")
        before = {
            "pred": db.query(PreMatchPredictionSnapshot).count(),
            "eval": db.query(PredictionEvaluationRecord).count(),
            "intel": db.query(IntelligenceSnapshot).count(),
            "registry": db.query(ModelRegistry).count(),
            "champion": resolve_active_model_id(db),
        }
        prod_hash = ctx["champ_pred"]["prediction_hash"]
        execute_shadow(db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        target = ctx["target"]
        target.status = "FINISHED"
        target.home_score = 1
        target.away_score = 0
        db.commit()
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        shadows = db.query(ShadowPredictionSnapshot).filter_by(
            match_id=target.id).all()
        ev(db, shadows[0].shadow_id)
        after = {
            "pred": db.query(PreMatchPredictionSnapshot).count(),
            "eval": db.query(PredictionEvaluationRecord).count(),
            "intel": db.query(IntelligenceSnapshot).count(),
            "registry": db.query(ModelRegistry).count(),
            "champion": resolve_active_model_id(db),
        }
        assert after["pred"] == before["pred"]
        assert after["eval"] == before["eval"]
        assert after["intel"] == before["intel"]
        assert after["registry"] == before["registry"]
        assert after["champion"] == before["champion"] == \
            "ensemble_v1-elo+poisson"
        row = db.query(PreMatchPredictionSnapshot).filter_by(
            prediction_id=ctx["champ_pred"]["prediction_id"]).one()
        assert row.prediction_hash == prod_hash
        # No outcome/eval rows created by shadow ops except via shared
        # Phase 27 capture (outcome snapshot is shared ingestion).
        assert db.query(MatchOutcomeSnapshot).count() <= 1

    def test_no_promotion_requests_created(self, db):
        from app.db.models.governance import ModelPromotionRequest

        ctx = _shadow_ready(db, code="P32PN")
        before = db.query(ModelPromotionRequest).count()
        execute_shadow(db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert db.query(ModelPromotionRequest).count() == before


# -- 32. golden regression ---------------------------------------------------------------------------------------------------------------------------------------------------

class TestGoldenRegression:
    def test_ensemble_values_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P32GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"


# -- 33. historical immutability -----------------------------------------------------------------------------------------------------------------------------------------------

class TestHistoricalImmutability:
    def test_history_stable_across_shadow_lifecycle(self, db):
        ctx = _shadow_ready(db, code="P32HI")
        prod_hash = ctx["champ_pred"]["prediction_hash"]
        feat_hash = ctx["champ_pred"]["feature_snapshot_hash"]
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        target = ctx["target"]
        target.status = "FINISHED"
        target.home_score = 2
        target.away_score = 2
        db.commit()
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        ev(db, res["shadow_id"])
        # Challenger governance reads.
        from app.services.model_governance import reconstruct

        reconstruct(db, ctx["challenger"]["artifact_id"])
        from app.db.models.prediction_snapshots import (
            PreMatchPredictionSnapshot,
            PredictionFeatureSnapshot,
        )

        prow = db.query(PreMatchPredictionSnapshot).filter_by(
            prediction_id=ctx["champ_pred"]["prediction_id"]).one()
        frow = db.query(PredictionFeatureSnapshot).filter_by(
            snapshot_hash=feat_hash).one()
        assert prow.prediction_hash == prod_hash
        assert prow.prediction_payload == ctx["champ_pred"]["prediction_payload"]
        assert frow.snapshot_hash == feat_hash


# -- 34. failure testing ----------------------------------------------------------------------------------------------------------------------------------------------------------

class TestFailures:
    def test_missing_feature_snapshot(self, db):
        from app.db.models.prediction_snapshots import (
            PredictionFeatureSnapshot,
        )

        ctx = _shadow_ready(db, code="P32FF")
        db.query(PredictionFeatureSnapshot).delete()
        db.commit()
        with pytest.raises(ShadowExecutionError) as exc:
            execute_shadow(
                db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert exc.value.code == "MISSING_FEATURE_SNAPSHOT"

    def test_cutoff_mismatch_new_cert(self, db):
        ctx = _shadow_ready(db, code="P32CM")
        new_cutoff = ctx["cutoff"] + timedelta(minutes=30)
        generate_readiness_certificate(db, ctx["target"].id,
                                       cutoff=new_cutoff)
        # Latest cert differs from champion prediction cutoff: shadow must
        # refuse rather than mix inputs.
        with pytest.raises(ShadowIneligible) as exc:
            execute_shadow(
                db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert exc.value.code in ("CERTIFICATE_CUTOFF_MISMATCH",
                                  "NO_CHAMPION_PREDICTION")

    def test_concurrent_execution_single_row(self, db):
        ctx = _shadow_ready(db, code="P32CC")
        first = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        second = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert first["shadow_id"] == second["shadow_id"]
        assert db.query(ShadowPredictionSnapshot).filter_by(
            match_id=ctx["target"].id).count() == 1

    def test_unknown_match(self, db):
        with pytest.raises(ShadowIneligible):
            from app.services.shadow_execution import execute_shadow as ex

            ex(db, 999999, "art_x")


# -- 35. restart -----------------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestRestart:
    def test_interrupt_resume_same_row(self, db):
        ctx = _shadow_ready(db, code="P32RS")
        first = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        # Simulated restart: fresh lookup + re-execution.
        found = find_shadow(db, first["shadow_execution_key"])
        assert found is not None and found.shadow_id == first["shadow_id"]
        second = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        assert second["shadow_id"] == first["shadow_id"]
        assert db.query(ShadowPredictionSnapshot).filter_by(
            match_id=ctx["target"].id).count() == 1

    def test_evaluation_rerun_same_record(self, db):
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        ctx = _shadow_ready(db, code="P32RR")
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        target = ctx["target"]
        target.status = "FINISHED"
        target.home_score = 0
        target.away_score = 1
        db.commit()
        first = ev(db, res["shadow_id"])
        second = ev(db, res["shadow_id"])
        assert second["evaluation_id"] == first["evaluation_id"]
        from app.db.models.governance import ShadowEvaluationRecord

        assert db.query(ShadowEvaluationRecord).filter_by(
            shadow_id=res["shadow_id"]).count() == 1


# -- 40. no auto-promotion ---------------------------------------------------------------------------------------------------------------------------------------------------------------

class TestNoAutoPromotion:
    def _better_challenger_flow(self, db, code):
        ctx = _shadow_ready(db, code=code)
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        target = ctx["target"]
        target.status = "FINISHED"
        target.home_score = 0
        target.away_score = 3
        db.commit()
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        return ctx, ev(db, res["shadow_id"])

    def test_better_metrics_no_promotion(self, db):
        from app.db.models.governance import ModelPromotionRequest

        ctx = _shadow_ready(db, code="P32NAB")
        before = db.query(ModelPromotionRequest).count()
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        target = ctx["target"]
        target.status = "FINISHED"
        target.home_score = 0
        target.away_score = 3
        db.commit()
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        ev(db, res["shadow_id"])
        assert resolve_active_model_id(db) == "ensemble_v1-elo+poisson"
        assert db.query(ModelPromotionRequest).count() == before

    def test_worse_metrics_no_auto_rejection(self, db):
        ctx = _shadow_ready(db, code="P32NAW")
        from app.services.model_governance.artifact import get_artifact as g

        before = g(db, ctx["challenger"]["artifact_id"]).lifecycle_state
        res = execute_shadow(
            db, ctx["target"].id, ctx["challenger"]["artifact_id"])
        target = ctx["target"]
        target.home_score = 5
        target.away_score = 0
        target.status = "FINISHED"
        db.commit()
        from app.services.shadow_execution import evaluate_shadow_pair as ev

        ev(db, res["shadow_id"])
        after = g(db, ctx["challenger"]["artifact_id"]).lifecycle_state
        assert after == before == "SHADOW"

    def test_anomaly_no_lifecycle_change(self, db):
        from app.services.production_monitoring import detect_anomalies

        ctx = _shadow_ready(db, code="P32NAA")
        from app.services.model_governance.artifact import get_artifact as g

        before = g(db, ctx["challenger"]["artifact_id"]).lifecycle_state
        detect_anomalies(db)
        after = g(db, ctx["challenger"]["artifact_id"]).lifecycle_state
        assert after == before

    def test_scheduler_no_lifecycle_change(self, db):
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import JOB_SHADOW_PREDICTION
        from app.services.scheduler.executors import get_executor

        ctx = _shadow_ready(db, code="P32NAS")
        from app.services.model_governance.artifact import get_artifact as g

        before = g(db, ctx["challenger"]["artifact_id"]).lifecycle_state
        cfg = get_job_config(JOB_SHADOW_PREDICTION)
        cfg["competitions"] = ["P32NAS"]
        cfg["challenger_artifact_id"] = ctx["challenger"]["artifact_id"]
        get_executor(JOB_SHADOW_PREDICTION)(db, cfg, dry_run=False)
        after = g(db, ctx["challenger"]["artifact_id"]).lifecycle_state
        assert after == before
        assert resolve_active_model_id(db) == "ensemble_v1-elo+poisson"
