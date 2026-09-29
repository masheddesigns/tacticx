"""Phase 30 — controlled model validation & promotion governance tests.

Covers: artifact identity, lifecycle transitions, validation, promotion,
approval, shadow, canary, activation, rollback, concurrency, adversarial
no-auto-promotion, production isolation end-to-end, API, migration chain,
golden regression.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.governance import (
    ModelArtifact,
    ModelGovernanceEvent,
)
from app.services.model_governance import (
    activate_production,
    current_champion,
    ensure_champion,
    get_artifact,
    mark_canary_eligible,
    reconstruct,
    register_artifact,
    register_candidate_artifact,
    request_promotion,
    resolve_active_model_id,
    rollback,
    run_shadow_pair,
    start_shadow,
    validate_candidate,
)
from app.services.model_governance.artifact import artifact_identity
from app.services.model_governance.contracts import (
    ALLOWED_TRANSITIONS,
    CHAMPION_MODEL_ID,
    canonical_hash,
)
from app.services.model_governance.lifecycle import (
    GovernanceError,
    allowed_transitions,
    transition,
)
from app.services.research import (
    build_dataset,
    register_builtin,
    run_experiment,
)


def _round_robin(db, code="P30R", days=40):
    league = League(code=code, name=f"{code} league", provider="t",
                    provider_league_id=f"p30-{code}", season="2024")
    db.add(league)
    db.commit()
    teams = {}
    for name in ("A", "B", "C", "D"):
        team = Team(league_id=league.id, name=name, provider="t",
                    provider_team_id=f"p30-{code}-{name}")
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
                provider="t", provider_match_id=f"p30-{code}-{idx}"))
    db.commit()
    return league


def _researched(db, code="P30E", key="elo_only"):
    """Phase 29 candidate + dataset + experiment. Returns dict."""
    _round_robin(db, code=code)
    ds = build_dataset(db, competitions=[code])
    cand = register_builtin(db, key)
    exp = run_experiment(db, cand.candidate_id, ds.dataset_id)
    return {"dataset": ds, "candidate": cand, "experiment": exp}


def _validated_artifact(db, code="P30V", key="elo_only", actor="reviewer"):
    ctx = _researched(db, code=code, key=key)
    art = register_candidate_artifact(
        db, candidate_id=ctx["candidate"].candidate_id,
        experiment_id=ctx["experiment"]["experiment_id"],
        dataset_id=ctx["dataset"].dataset_id,
        dataset_hash=ctx["dataset"].dataset_hash)
    report = validate_candidate(
        db, art["artifact_id"],
        experiment_id=ctx["experiment"]["experiment_id"], actor=actor)
    return {"artifact": art, "report": report, **ctx}


# -- artifact identity -------------------------------------------------------------------------------------

class TestArtifactIdentity:
    def test_deterministic_identity(self):
        first = artifact_identity(
            model_id="ensemble_v1-elo+poisson",
            model_version="ensemble_v1-elo+poisson",
            members=["elo", "poisson"], weights=[0.5, 0.5])
        second = artifact_identity(
            model_id="ensemble_v1-elo+poisson",
            model_version="ensemble_v1-elo+poisson",
            members=["elo", "poisson"], weights=[0.5, 0.5])
        assert canonical_hash(first) == canonical_hash(second)

    def test_weights_change_identity(self):
        base = artifact_identity(
            model_id="ensemble_v1-elo+poisson",
            model_version="ensemble_v1-elo+poisson",
            members=["elo", "poisson"], weights=[0.5, 0.5])
        other = artifact_identity(
            model_id="ensemble_v1-elo+poisson",
            model_version="ensemble_v1-elo+poisson",
            members=["elo", "poisson"], weights=[0.6, 0.4])
        assert canonical_hash(base) != canonical_hash(other)

    def test_register_reuses_hash(self, db):
        first = register_artifact(
            db, model_id="m", model_version="m",
            members=["elo"], weights=[1.0])
        second = register_artifact(
            db, model_id="m", model_version="m",
            members=["elo"], weights=[1.0])
        assert second.artifact_id == first.artifact_id

    def test_champion_seed(self, db):
        binding = ensure_champion(db)
        artifact = get_artifact(db, binding.artifact_id)
        assert artifact.model_id == CHAMPION_MODEL_ID
        assert artifact.lifecycle_state == "PRODUCTION_ACTIVE"
        assert resolve_active_model_id(db) == CHAMPION_MODEL_ID
        # Seeding twice returns the same binding.
        assert ensure_champion(db).id == binding.id


# -- lifecycle ----------------------------------------------------------------------------------------------------------------

class TestLifecycle:
    def test_allowed_map_is_closed(self):
        for targets in ALLOWED_TRANSITIONS.values():
            for target in targets:
                assert target in ALLOWED_TRANSITIONS, target
        assert ALLOWED_TRANSITIONS["RESEARCH_ONLY"] == (
            "VALIDATION_PENDING", "WITHDRAWN")
        assert ALLOWED_TRANSITIONS["REJECTED"] == ()

    def test_invalid_transition_rejected(self, db):
        art = register_artifact(
            db, model_id="m", model_version="m",
            members=["elo"], weights=[1.0])
        with pytest.raises(GovernanceError) as exc:
            transition(db, art, "PRODUCTION_ACTIVE", actor="x")
        assert exc.value.code == "INVALID_TRANSITION"
        assert art.lifecycle_state == "RESEARCH_ONLY"

    def test_valid_transition_logged(self, db):
        art = register_artifact(
            db, model_id="m", model_version="m",
            members=["elo"], weights=[1.0])
        transition(db, art, "VALIDATION_PENDING", actor="op", reason="r")
        assert art.lifecycle_state == "VALIDATION_PENDING"
        events = db.query(ModelGovernanceEvent).filter_by(
            artifact_id=art.artifact_id).all()
        assert any(e.to_state == "VALIDATION_PENDING" for e in events)

    def test_allowed_helper(self):
        assert "VALIDATION_PENDING" in allowed_transitions("RESEARCH_ONLY")
        assert allowed_transitions("REJECTED") == ()


# -- validation ---------------------------------------------------------------------------------------------------------------------

class TestValidation:
    def test_validate_neutral_evidence(self, db):
        ctx = _validated_artifact(db, code="P30VN")
        assert ctx["report"]["validation_result"] == "VALIDATED"
        art = get_artifact(db, ctx["artifact"]["artifact_id"])
        assert art.lifecycle_state == "VALIDATED"

    def test_validate_requires_research_state(self, db):
        ctx = _validated_artifact(db, code="P30VR")
        from app.services.model_governance.validation import ValidationError

        with pytest.raises(ValidationError):
            validate_candidate(db, ctx["artifact"]["artifact_id"])

    def test_leaking_experiment_invalid(self, db):
        from app.services.research import register_candidate

        _round_robin(db, code="P30VL")
        ds = build_dataset(db, competitions=["P30VL"])
        cand = register_candidate(
            db, name="Leaky", model_family="ensemble",
            members=["elo", "poisson"],
            declared_inputs={"tables": ["matches", "future_results"]})
        from app.services.model_governance.service import (
            register_candidate_artifact as reg,
        )

        art = reg(db, candidate_id=cand.candidate_id,
                  dataset_id=ds.dataset_id, dataset_hash=ds.dataset_hash)
        exp = run_experiment(db, cand.candidate_id, ds.dataset_id)
        report = validate_candidate(
            db, art["artifact_id"], experiment_id=exp["experiment_id"])
        assert report["validation_result"] == "INVALID"

    def test_compatibility_probe(self, db):
        from app.services.model_governance.validation import (
            check_compatibility,
        )

        good = check_compatibility({
            "home_win_probability": 0.6, "draw_probability": 0.25,
            "away_win_probability": 0.15,
            "expected_home_goals": 1.5, "expected_away_goals": 0.8})
        assert good["compatible"] is True
        bad = check_compatibility({
            "home_win_probability": 0.6, "draw_probability": 0.25,
            "away_win_probability": 0.5,
            "expected_home_goals": -1.0, "expected_away_goals": 0.8})
        assert bad["compatible"] is False


# -- promotion + approval -----------------------------------------------------------------------------------------------------------------

class TestPromotionApproval:
    def _requested(self, db, code="P30PA"):
        ctx = _validated_artifact(db, code=code)
        req = request_promotion(
            db, ctx["artifact"]["artifact_id"],
            validation_id=ctx["report"]["validation_id"],
            requester="requester", reason="test")
        return ctx, req

    def test_request_moves_state(self, db):
        ctx, req = self._requested(db)
        assert req["state"] == "OPEN"
        art = get_artifact(db, ctx["artifact"]["artifact_id"])
        assert art.lifecycle_state == "PROMOTION_REQUESTED"
        assert req["champion_artifact_id"]

    def test_request_requires_validation(self, db):
        _round_robin(db, code="P30PR")
        from app.services.research import register_builtin

        from app.services.model_governance.service import (
            register_candidate_artifact as reg,
        )
        from app.services.model_governance.promotion import PromotionError

        cand = register_builtin(db, "elo_only")
        art = reg(db, candidate_id=cand.candidate_id)
        with pytest.raises(PromotionError):
            request_promotion(
                db, art["artifact_id"], validation_id="val_nope_123",
                requester="r")

    def test_approval_activates_count(self, db):
        from app.services.model_governance import decide as decide_fn

        ctx, req = self._requested(db, code="P30PAP")
        out = decide_fn(db, req["request_id"], decision="APPROVE",
                        actor="human-1", reason="evidence reviewed")
        assert out["decision"] == "APPROVE"
        art = get_artifact(db, ctx["artifact"]["artifact_id"])
        assert art.lifecycle_state == "APPROVED"

    def test_rejection_closes(self, db):
        from app.services.model_governance import decide as decide_fn

        ctx, req = self._requested(db, code="P30PRJ")
        decide_fn(db, req["request_id"], decision="REJECT",
                  actor="human-1", reason="insufficient evidence")
        art = get_artifact(db, ctx["artifact"]["artifact_id"])
        assert art.lifecycle_state == "REJECTED"

    def test_missing_actor_refused(self, db):
        from app.services.model_governance import decide as decide_fn
        from app.services.model_governance.approval import ApprovalError

        _, req = self._requested(db, code="P30PMA")
        with pytest.raises(ApprovalError):
            decide_fn(db, req["request_id"], decision="APPROVE", actor="")


# -- shadow ------------------------------------------------------------------------------------------------------------------------------------

class TestShadow:
    def _shadow_ready(self, db, code="P30SH"):
        from app.services.model_governance import decide as decide_fn

        ctx = _validated_artifact(db, code=code)
        req = request_promotion(
            db, ctx["artifact"]["artifact_id"],
            validation_id=ctx["report"]["validation_id"],
            requester="r")
        decide_fn(db, req["request_id"], decision="APPROVE",
                  actor="human-1")
        champ = ensure_champion(db)
        start_shadow(db, ctx["artifact"]["artifact_id"],
                     champ.artifact_id, actor="human-1")
        return ctx, champ

    def test_shadow_requires_approval(self, db):
        ctx = _validated_artifact(db, code="P30SHR")
        champ = ensure_champion(db)
        from app.services.model_governance.shadow import ShadowError

        with pytest.raises(ShadowError):
            start_shadow(db, ctx["artifact"]["artifact_id"],
                         champ.artifact_id)

    def test_shadow_pair_isolated(self, db):
        from app.db.models.prediction_snapshots import (
            PreMatchPredictionSnapshot,
        )

        ctx, champ = self._shadow_ready(db, code="P30SPI")
        league = db.query(League).filter_by(code="P30SPI").one()
        target = db.query(Match).filter_by(
            league_id=league.id, status="FINISHED").order_by(
            Match.kickoff_at.desc()).first()
        before = db.query(PreMatchPredictionSnapshot).count()
        pair = run_shadow_pair(
            db, challenger_artifact_id=ctx["artifact"]["artifact_id"],
            champion_artifact_id=champ.artifact_id,
            match_id=target.id,
            cutoff=target.kickoff_at)
        assert pair["challenger_output_hash"] != pair["champion_output_hash"]
        assert db.query(PreMatchPredictionSnapshot).count() == before

    def test_shadow_evaluation_factual(self, db):
        from app.services.model_governance import evaluate_shadow as eval_sh

        ctx, champ = self._shadow_ready(db, code="P30SEV")
        league = db.query(League).filter_by(code="P30SEV").one()
        targets = db.query(Match).filter_by(
            league_id=league.id, status="FINISHED").order_by(
            Match.kickoff_at.desc()).limit(5).all()
        for target in targets:
            run_shadow_pair(
                db, challenger_artifact_id=ctx["artifact"]["artifact_id"],
                champion_artifact_id=champ.artifact_id,
                match_id=target.id, cutoff=target.kickoff_at)
        report = eval_sh(db, ctx["artifact"]["artifact_id"])
        assert report["scored_pairs"] == 5
        assert "winner" not in str(report["differences_challenger_minus_champion"])


# -- canary + activation + rollback ------------------------------------------------------------------------------------------------------------------

class TestCanaryActivationRollback:
    def _approved_shadowed(self, db, code, pairs=12):
        from app.services.model_governance import decide as decide_fn

        ctx = _validated_artifact(db, code=code)
        req = request_promotion(
            db, ctx["artifact"]["artifact_id"],
            validation_id=ctx["report"]["validation_id"],
            requester="r")
        decide_fn(db, req["request_id"], decision="APPROVE",
                  actor="human-1")
        champ = ensure_champion(db)
        start_shadow(db, ctx["artifact"]["artifact_id"],
                     champ.artifact_id, actor="human-1")
        league = db.query(League).filter_by(code=code).one()
        targets = db.query(Match).filter_by(
            league_id=league.id, status="FINISHED").order_by(
            Match.kickoff_at.desc()).limit(pairs).all()
        for target in targets:
            run_shadow_pair(
                db, challenger_artifact_id=ctx["artifact"]["artifact_id"],
                champion_artifact_id=champ.artifact_id,
                match_id=target.id, cutoff=target.kickoff_at)
        return ctx, champ, req

    def test_canary_needs_evidence(self, db):
        from app.services.model_governance import decide as decide_fn
        from app.services.model_governance.deployment import DeploymentError

        ctx = _validated_artifact(db, code="P30CNE")
        req = request_promotion(
            db, ctx["artifact"]["artifact_id"],
            validation_id=ctx["report"]["validation_id"],
            requester="r")
        decide_fn(db, req["request_id"], decision="APPROVE",
                  actor="human-1")
        champ = ensure_champion(db)
        start_shadow(db, ctx["artifact"]["artifact_id"],
                     champ.artifact_id, actor="human-1")
        with pytest.raises(DeploymentError):
            mark_canary_eligible(db, ctx["artifact"]["artifact_id"],
                                 actor="human-1")

    def test_canary_then_activate(self, db):
        ctx, champ, _ = self._approved_shadowed(db, "P30CNA")
        report = mark_canary_eligible(
            db, ctx["artifact"]["artifact_id"], actor="human-1")
        assert report["eligible"] is True
        art = get_artifact(db, ctx["artifact"]["artifact_id"])
        assert art.lifecycle_state == "CANARY_ELIGIBLE"
        activated = activate_production(
            db, ctx["artifact"]["artifact_id"], actor="human-1",
            expected_champion_artifact_id=champ.artifact_id,
            reason="test activation")
        assert activated["previous_champion_artifact_id"] == champ.artifact_id
        assert resolve_active_model_id(db) == \
            ctx["artifact"]["model_id"]
        current = current_champion(db)
        assert current.artifact_id == ctx["artifact"]["artifact_id"]

    def test_stale_champion_fails(self, db):
        from app.services.model_governance.deployment import DeploymentError

        ctx, champ, _ = self._approved_shadowed(db, "P30SCF")
        mark_canary_eligible(db, ctx["artifact"]["artifact_id"],
                             actor="human-1")
        with pytest.raises(DeploymentError) as exc:
            activate_production(
                db, ctx["artifact"]["artifact_id"], actor="human-1",
                expected_champion_artifact_id="art_stale_00000000")
        assert exc.value.code == "STALE_CHAMPION"
        assert current_champion(db).artifact_id == champ.artifact_id

    def test_duplicate_activation_refused(self, db):
        from app.services.model_governance.deployment import DeploymentError

        ctx, champ, _ = self._approved_shadowed(db, "P30DUP")
        mark_canary_eligible(db, ctx["artifact"]["artifact_id"],
                             actor="human-1")
        activate_production(
            db, ctx["artifact"]["artifact_id"], actor="human-1",
            expected_champion_artifact_id=champ.artifact_id)
        with pytest.raises(DeploymentError) as exc:
            activate_production(
                db, ctx["artifact"]["artifact_id"], actor="human-1",
                expected_champion_artifact_id=champ.artifact_id)
        assert exc.value.code in ("INVALID_ARTIFACT_STATE", "ALREADY_ACTIVE")

    def test_rollback_restores(self, db):
        ctx, champ, _ = self._approved_shadowed(db, "P30RBK")
        mark_canary_eligible(db, ctx["artifact"]["artifact_id"],
                             actor="human-1")
        activate_production(
            db, ctx["artifact"]["artifact_id"], actor="human-1",
            expected_champion_artifact_id=champ.artifact_id)
        out = rollback(db, actor="human-2",
                       target_artifact_id=champ.artifact_id,
                       reason="test rollback")
        assert out["artifact_id"] == champ.artifact_id
        assert current_champion(db).artifact_id == champ.artifact_id
        assert resolve_active_model_id(db) == CHAMPION_MODEL_ID
        rolled = get_artifact(db, ctx["artifact"]["artifact_id"])
        assert rolled.lifecycle_state == "ROLLED_BACK"

    def test_rollback_unknown_refused(self, db):
        from app.services.model_governance.lifecycle import GovernanceError

        ensure_champion(db)
        with pytest.raises(GovernanceError):
            rollback(db, actor="human-2",
                     target_artifact_id="art_nope_00000000")


# -- adversarial: no automatic promotion ----------------------------------------------------------------------------------------------------------------------

class TestNoAutoPromotion:
    def test_no_auto_promote_symbol(self, db):
        import app.services.model_governance as gov

        source_names = [n for n in dir(gov) if "auto" in n.lower()]
        assert source_names == []
        import inspect

        for name in ("deployment", "promotion", "approval", "scheduler"):
            try:
                module = __import__(
                    f"app.services.model_governance.{name}",
                    fromlist=["x"]) if name != "scheduler" else None
            except ImportError:
                module = None
            if module is not None:
                text = inspect.getsource(module)
                assert "auto_promot" not in text.lower()

    def test_validation_does_not_activate(self, db):
        ctx = _validated_artifact(db, code="P30NAP")
        assert resolve_active_model_id(db) == CHAMPION_MODEL_ID
        fresh = get_artifact(db, ctx["artifact"]["artifact_id"])
        assert fresh.lifecycle_state == "VALIDATED"

    def test_approval_without_request_impossible(self, db):
        from app.services.model_governance import decide as decide_fn
        from app.services.model_governance.approval import ApprovalError
        from app.services.model_governance.promotion import PromotionError

        _round_robin(db, code="P30NAR")
        with pytest.raises((ApprovalError, PromotionError)):
            decide_fn(db, "promo_nope_123", decision="APPROVE",
                      actor="human-1")

    def test_rejected_cannot_activate(self, db):
        from app.services.model_governance import decide as decide_fn
        from app.services.model_governance.deployment import DeploymentError

        ctx = _validated_artifact(db, code="P30NRJ")
        req = request_promotion(
            db, ctx["artifact"]["artifact_id"],
            validation_id=ctx["report"]["validation_id"],
            requester="r")
        decide_fn(db, req["request_id"], decision="REJECT",
                  actor="human-1")
        with pytest.raises(DeploymentError):
            activate_production(
                db, ctx["artifact"]["artifact_id"], actor="human-1",
                expected_champion_artifact_id="art_x")

    def test_research_only_cannot_activate(self, db):
        from app.services.model_governance.deployment import DeploymentError
        from app.services.model_governance.service import (
            register_candidate_artifact as reg,
        )
        from app.services.research import register_builtin

        _round_robin(db, code="P30NRA")
        cand = register_builtin(db, "elo_only")
        art = reg(db, candidate_id=cand.candidate_id)
        champ = ensure_champion(db)
        with pytest.raises(DeploymentError):
            activate_production(
                db, art["artifact_id"], actor="human-1",
                expected_champion_artifact_id=champ.artifact_id)

    def test_duplicate_promotion_guard(self, db):
        ctx = _validated_artifact(db, code="P30NDP")
        req = request_promotion(
            db, ctx["artifact"]["artifact_id"],
            validation_id=ctx["report"]["validation_id"],
            requester="r")
        from app.services.model_governance import decide as decide_fn

        decide_fn(db, req["request_id"], decision="APPROVE",
                  actor="human-1")
        # Second approval on a closed request is refused.
        from app.services.model_governance.approval import ApprovalError

        with pytest.raises(ApprovalError):
            decide_fn(db, req["request_id"], decision="APPROVE",
                      actor="human-2")

    def test_modified_artifact_hash_mismatch(self, db):
        ctx = _validated_artifact(db, code="P30NMH")
        row = db.query(ModelArtifact).filter_by(
            artifact_id=ctx["artifact"]["artifact_id"]).one()
        row.model_version = "tampered_v9"
        db.commit()
        from app.services.model_governance.artifact import artifact_identity
        from app.services.model_governance.contracts import canonical_hash

        identity = artifact_identity(
            model_id=row.model_id, model_version="tampered_v9",
            members=row.config_fingerprint.get("members", []),
            weights=row.config_fingerprint.get("weights", []),
            candidate_id=row.candidate_id,
            experiment_id=row.experiment_id,
            dataset_id=row.dataset_id, dataset_hash=row.dataset_hash,
            feature_contract=row.feature_contract,
            prediction_mode=row.prediction_mode,
            train_period=row.train_period,
            evaluation_period=row.evaluation_period,
            code_hash=row.code_hash)
        assert canonical_hash(identity) != row.artifact_hash

    def test_approval_record_immutable(self, db):
        from app.services.model_governance import decide as decide_fn

        ctx = _validated_artifact(db, code="P30NAI")
        req = request_promotion(
            db, ctx["artifact"]["artifact_id"],
            validation_id=ctx["report"]["validation_id"],
            requester="r")
        out = decide_fn(db, req["request_id"], decision="APPROVE",
                        actor="human-1", reason="original")
        from app.db.models.governance import ModelApprovalRecord

        stored = db.query(ModelApprovalRecord).filter_by(
            approval_id=out["approval_id"]).one()
        assert stored.decision == "APPROVE"
        assert stored.actor == "human-1"
        assert stored.reason == "original"


# -- production isolation end-to-end (§24) ----------------------------------------------------------------------------------------------------------------------------------

class TestProductionIsolationE2E:
    def test_full_lifecycle_preserves_production(self, db):
        from app.db.models.prediction_snapshots import (
            PreMatchPredictionSnapshot,
        )
        from app.services.prediction_execution import (
            execute_pre_match_prediction,
        )
        from app.services.acquisition.readiness_gate import (
            generate_readiness_certificate,
        )

        # 1. Confirm ensemble_v1 is champion.
        champ = ensure_champion(db)
        assert resolve_active_model_id(db) == CHAMPION_MODEL_ID

        # 2-3. Candidate + validation.
        ctx = _validated_artifact(db, code="P30E2E", key="elo_only")
        art_id = ctx["artifact"]["artifact_id"]

        # 4-5. Promotion request + approval.
        req = request_promotion(
            db, art_id, validation_id=ctx["report"]["validation_id"],
            requester="e2e-requester", reason="e2e")
        from app.services.model_governance import decide as decide_fn

        decide_fn(db, req["request_id"], decision="APPROVE",
                  actor="e2e-approver", reason="e2e reviewed")

        # 6-7. Shadow + challenger outputs (12 pairs for canary evidence).
        start_shadow(db, art_id, champ.artifact_id, actor="e2e-approver")
        league = db.query(League).filter_by(code="P30E2E").one()
        targets = db.query(Match).filter_by(
            league_id=league.id, status="FINISHED").order_by(
            Match.kickoff_at.desc()).limit(12).all()
        for target in targets:
            run_shadow_pair(
                db, challenger_artifact_id=art_id,
                champion_artifact_id=champ.artifact_id,
                match_id=target.id, cutoff=target.kickoff_at)

        # 8. Production predictions still use ensemble_v1.
        now = datetime.now(timezone.utc)
        sched = Match(
            league_id=league.id,
            home_team_id=target.home_team_id,
            away_team_id=target.away_team_id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p30-P30E2E-sched")
        db.add(sched)
        db.commit()
        db.refresh(sched)
        cert = generate_readiness_certificate(db, sched.id)
        prod = execute_pre_match_prediction(db, sched.id, cert.cutoff)
        assert prod["model_id"] == CHAMPION_MODEL_ID
        prod_hash = prod["prediction_hash"]

        # 9. Explicit activation only.
        mark_canary_eligible(db, art_id, actor="e2e-approver")
        activate_production(
            db, art_id, actor="e2e-approver",
            expected_champion_artifact_id=champ.artifact_id,
            reason="e2e activation")
        assert resolve_active_model_id(db) != CHAMPION_MODEL_ID

        # 10. New governed outputs use the new artifact; default path pinned.
        assert current_champion(db).artifact_id == art_id
        prod2 = execute_pre_match_prediction(db, sched.id, cert.cutoff)
        assert prod2["prediction_id"] == prod["prediction_id"]
        assert prod2["model_id"] == CHAMPION_MODEL_ID

        # 11. Old predictions retain ensemble_v1.
        row = db.query(PreMatchPredictionSnapshot).filter_by(
            prediction_id=prod["prediction_id"]).one()
        assert row.model_id == CHAMPION_MODEL_ID
        assert row.prediction_hash == prod_hash

        # 12-13. Roll back; registry restored.
        rollback(db, actor="e2e-approver",
                 target_artifact_id=champ.artifact_id,
                 reason="e2e rollback")
        assert resolve_active_model_id(db) == CHAMPION_MODEL_ID

        # 14. Historical hashes unchanged.
        row2 = db.query(PreMatchPredictionSnapshot).filter_by(
            prediction_id=prod["prediction_id"]).one()
        assert row2.prediction_hash == prod_hash

        # 15. Governance audit complete.
        trail = reconstruct(db, art_id)
        states = [e["to_state"] for e in trail["events"]]
        for expected in ("VALIDATED", "PROMOTION_REQUESTED", "APPROVED",
                         "SHADOW", "CANARY_ELIGIBLE", "PRODUCTION_ACTIVE"):
            assert expected in states, expected
        assert trail["approvals"][0]["actor"] == "e2e-approver"


# -- API ----------------------------------------------------------------------------------------------------------------------------------------------

class TestGovernanceAPI:
    def _setup(self, db, code="P30API"):
        return _validated_artifact(db, code=code)

    def test_registry_and_champion(self, client):
        reg = client.get("/api/v1/model-governance/registry").json()
        assert "bindings" in reg
        champ = client.get("/api/v1/model-governance/champion").json()
        assert champ["artifact"]["model_id"] == CHAMPION_MODEL_ID

    def test_artifact_lifecycle_api(self, client, db):
        ctx = self._setup(db, code="P30APIA")
        art_id = ctx["artifact"]["artifact_id"]
        detail = client.get(
            f"/api/v1/model-governance/artifacts/{art_id}").json()
        assert detail["lifecycle_state"] == "VALIDATED"
        status = client.get(
            f"/api/v1/model-governance/status/{art_id}").json()
        assert status["artifact"]["artifact_id"] == art_id
        assert "canary_eligibility" in status

    def test_promotion_approval_flow_api(self, client, db):
        ctx = self._setup(db, code="P30APIP")
        art_id = ctx["artifact"]["artifact_id"]
        req = client.post(
            "/api/v1/model-governance/promotion-requests",
            json={"artifact_id": art_id,
                  "validation_id": ctx["report"]["validation_id"],
                  "requester": "api-op", "reason": "api test"}).json()
        assert req["state"] == "OPEN"
        listed = client.get(
            "/api/v1/model-governance/promotion-requests").json()
        assert any(r["request_id"] == req["request_id"]
                   for r in listed["requests"])
        appr = client.post(
            "/api/v1/model-governance/approvals",
            json={"request_id": req["request_id"], "decision": "APPROVE",
                  "actor": "api-human", "reason": "reviewed"}).json()
        assert appr["decision"] == "APPROVE"

    def test_shadow_canary_activate_rollback_api(self, client, db):
        ctx = self._setup(db, code="P30APIS")
        art_id = ctx["artifact"]["artifact_id"]
        champ = client.get("/api/v1/model-governance/champion").json()
        champ_id = champ["artifact"]["artifact_id"]
        req = client.post(
            "/api/v1/model-governance/promotion-requests",
            json={"artifact_id": art_id,
                  "validation_id": ctx["report"]["validation_id"],
                  "requester": "api-op"}).json()
        client.post(
            "/api/v1/model-governance/approvals",
            json={"request_id": req["request_id"], "decision": "APPROVE",
                  "actor": "api-human"})
        started = client.post(
            "/api/v1/model-governance/shadow/start",
            json={"challenger_artifact_id": art_id,
                  "champion_artifact_id": champ_id,
                  "actor": "api-human"}).json()
        assert started["state"] == "SHADOW"
        league = db.query(League).filter_by(code="P30APIS").one()
        target = db.query(Match).filter_by(
            league_id=league.id, status="FINISHED").order_by(
            Match.kickoff_at.desc()).first()
        pair = client.post(
            "/api/v1/model-governance/shadow/pair",
            json={"challenger_artifact_id": art_id,
                  "champion_artifact_id": champ_id,
                  "match_id": target.id,
                  "cutoff": target.kickoff_at.isoformat()}).json()
        assert pair["shadow_id"].startswith("shdw_")
        shadow = client.get(
            f"/api/v1/model-governance/shadow/{art_id}").json()
        assert shadow["shadow_pairs"] >= 1

    def test_guard_blocks_mutations(self, client):
        from unittest.mock import patch

        with patch("app.config.Settings.operational_endpoints_enabled",
                   False):
            resp = client.post(
                "/api/v1/model-governance/promotion-requests",
                json={"artifact_id": "x", "validation_id": "y"})
            assert resp.status_code == 403
            resp = client.post(
                "/api/v1/model-governance/approvals",
                json={"request_id": "x", "decision": "APPROVE",
                      "actor": "h"})
            assert resp.status_code == 403

    def test_audit_endpoint(self, client, db):
        ctx = self._setup(db, code="P30APIA2")
        body = client.get(
            f"/api/v1/model-governance/audit?artifact_id="
            f"{ctx['artifact']['artifact_id']}").json()
        assert len(body["events"]) >= 1


# -- migration chain ----------------------------------------------------------------------------------------------------------------------------------------------

class TestMigrationChain:
    def test_0014_chain(self):
        import importlib.util
        from pathlib import Path

        path = (Path(__file__).parent.parent / "migrations" / "versions"
                / "0014_model_governance.py")
        spec = importlib.util.spec_from_file_location("mig_0014", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "0014_model_governance"
        assert mod.down_revision == "0013_research_registry"
        assert mod.branch_labels is None

    def test_0014_links_into_chain(self):
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
        # 0014 must chain 0013 -> 0014; head ownership belongs to the
        # latest phase test (no branch divergence).
        assert revisions["0014_model_governance"] == \
            "0013_research_registry"
        down_revs = {v for v in revisions.values() if v is not None}
        heads = [r for r in revisions if r not in down_revs]
        assert len(heads) == 1

    def test_tables_exist(self, db):
        from app.db.models.governance import (
            ModelArtifact,
            ModelRegistry,
            ShadowPredictionSnapshot,
        )

        assert db.query(ModelArtifact).count() == 0
        assert db.query(ModelRegistry).count() == 0
        assert db.query(ShadowPredictionSnapshot).count() == 0


# -- golden regression ----------------------------------------------------------------------------------------------------------------------------------------------

class TestGoldenRegression:
    def test_ensemble_values_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P30GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"
