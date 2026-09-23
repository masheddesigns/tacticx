"""Phase 26 — pre-match prediction execution layer tests.

Covers: readiness gating, temporal enforcement, config validation, output
validation, immutability, idempotency, hashing, API, golden regression,
adversarial leakage, scheduler integration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.core import League, Lineup, Match, MatchEvent, Team
from app.db.models.odds import OddsSnapshot
from app.db.models.prediction_snapshots import (
    PredictionFeatureSnapshot,
    PreMatchPredictionSnapshot,
)
from app.services.acquisition.readiness_gate import (
    generate_readiness_certificate,
)
from app.services.prediction_execution import (
    PredictionBlocked,
    describe_match_predictions,
    execute_pre_match_prediction,
    get_prediction,
)
from app.services.prediction_execution.contracts import (
    canonical_hash,
    execution_key,
)
from app.services.prediction_execution.validation import (
    validate_prediction_output,
)

MODEL_ID = "ensemble_v1-elo+poisson"


def _league(db, code):
    lg = League(code=code, name=f"{code} league", provider="t",
                provider_league_id=f"p26-{code}", season="2024")
    db.add(lg)
    db.commit()
    return lg


def _teams(db, league, code):
    home = Team(league_id=league.id, name="Home", provider="t",
                provider_team_id=f"p26-{code}-h")
    away = Team(league_id=league.id, name="Away", provider="t",
                provider_team_id=f"p26-{code}-a")
    db.add_all([home, away])
    db.commit()
    return home, away


def _finished(db, league, home_id, away_id, kickoff, hs=2, aw=0, tag="h"):
    db.add(Match(
        league_id=league.id, home_team_id=home_id, away_team_id=away_id,
        kickoff_at=kickoff, status="FINISHED", home_score=hs, away_score=aw,
        provider="t", provider_match_id=f"p26-{tag}-{kickoff.isoformat()}"))
    db.commit()


def _ready_fixture(db, code="P26R", with_optionals=False):
    """Target + 3 finished matches per team, kickoff 5h out. Returns target."""
    league = _league(db, code)
    home, away = _teams(db, league, code)
    now = datetime.now(timezone.utc)
    for i in range(3):
        _finished(db, league, home.id, away.id,
                  now - timedelta(days=21 - i * 7), hs=2, aw=0, tag=f"{code}a{i}")
        _finished(db, league, away.id, home.id,
                  now - timedelta(days=20 - i * 7), hs=1, aw=1, tag=f"{code}b{i}")
    target = Match(
        league_id=league.id, home_team_id=home.id, away_team_id=away.id,
        kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
        provider="t", provider_match_id=f"p26-{code}-target")
    db.add(target)
    db.commit()
    db.refresh(target)
    cutoff = now + timedelta(hours=1)
    if with_optionals:
        db.add(Lineup(match_id=target.id, team_id=home.id, team="home",
                      player_name="Starter One"))
        db.add(OddsSnapshot(match_id=target.id, market_type="1x2",
                            timestamp=now - timedelta(hours=1)))
        db.commit()
    return target, cutoff


def _execute(db, target, cutoff, **kwargs):
    cert = generate_readiness_certificate(db, target.id, cutoff=cutoff)
    result = execute_pre_match_prediction(db, target.id, cutoff, **kwargs)
    return cert, result


# -- readiness -------------------------------------------------------------------------------------

class TestReadinessGating:
    def test_degraded_executes_with_flag(self, db):
        target, cutoff = _ready_fixture(db, code="P26D")
        cert, result = _execute(db, target, cutoff)
        assert cert.readiness_state == "READY_DEGRADED"
        assert result["readiness_state"] == "READY_DEGRADED"
        assert result["cache_hit"] is False
        assert result["prediction_id"].startswith("pred_")

    def test_ready_executes(self, db):
        target, cutoff = _ready_fixture(db, code="P26OK", with_optionals=True)
        cert, result = _execute(db, target, cutoff)
        assert cert.readiness_state == "PREDICTION_READY"
        assert result["readiness_state"] == "PREDICTION_READY"

    def test_blocked_refuses(self, db):
        league = _league(db, "P26B")
        home, away = _teams(db, league, "P26B")
        now = datetime.now(timezone.utc)
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p26-P26B-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        cutoff = now + timedelta(hours=1)
        cert = generate_readiness_certificate(db, target.id, cutoff=cutoff)
        assert cert.readiness_state == "BLOCKED"
        with pytest.raises(PredictionBlocked) as exc:
            execute_pre_match_prediction(db, target.id, cutoff)
        assert exc.value.code == "READINESS_BLOCKED"

    def test_missing_certificate_refuses(self, db):
        target, cutoff = _ready_fixture(db, code="P26NC")
        with pytest.raises(PredictionBlocked) as exc:
            execute_pre_match_prediction(db, target.id, cutoff)
        assert exc.value.code == "CERTIFICATE_MISSING"

    def test_superseded_certificate_refuses(self, db):
        target, cutoff = _ready_fixture(db, code="P26SUP")
        old = generate_readiness_certificate(db, target.id, cutoff=cutoff)
        new = generate_readiness_certificate(db, target.id, cutoff=cutoff)
        assert old.certificate_id != new.certificate_id
        with pytest.raises(PredictionBlocked) as exc:
            execute_pre_match_prediction(
                db, target.id, cutoff, certificate_id=old.certificate_id)
        assert exc.value.code == "CERTIFICATE_SUPERSEDED"

    def test_certificate_cutoff_mismatch_refuses(self, db):
        target, cutoff = _ready_fixture(db, code="P26MM")
        other_cutoff = cutoff + timedelta(minutes=30)
        generate_readiness_certificate(db, target.id, cutoff=other_cutoff)
        with pytest.raises(PredictionBlocked) as exc:
            execute_pre_match_prediction(db, target.id, cutoff)
        assert exc.value.code == "CERTIFICATE_CUTOFF_MISMATCH"

    def test_certificate_wrong_match_refuses(self, db):
        t1, c1 = _ready_fixture(db, code="P26W1")
        t2, _ = _ready_fixture(db, code="P26W2")
        cert = generate_readiness_certificate(db, t1.id, cutoff=c1)
        with pytest.raises(PredictionBlocked) as exc:
            execute_pre_match_prediction(
                db, t2.id, c1, certificate_id=cert.certificate_id)
        assert exc.value.code == "CERTIFICATE_MATCH_MISMATCH"

    def test_unknown_certificate_refuses(self, db):
        target, cutoff = _ready_fixture(db, code="P26UC")
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        with pytest.raises(PredictionBlocked) as exc:
            execute_pre_match_prediction(
                db, target.id, cutoff, certificate_id="cert_nope_123")
        assert exc.value.code == "CERTIFICATE_NOT_FOUND"

    def test_explicit_certificate_id_executes(self, db):
        target, cutoff = _ready_fixture(db, code="P26EC")
        cert = generate_readiness_certificate(db, target.id, cutoff=cutoff)
        result = execute_pre_match_prediction(
            db, target.id, cutoff, certificate_id=cert.certificate_id)
        assert result["readiness_certificate_id"] == cert.certificate_id


# -- temporal --------------------------------------------------------------------------------------

class TestTemporalEnforcement:
    def test_cutoff_at_kickoff_refuses(self, db):
        target, _ = _ready_fixture(db, code="P26CK")
        db.refresh(target)
        with pytest.raises(PredictionBlocked) as exc:
            execute_pre_match_prediction(db, target.id, target.kickoff_at)
        assert exc.value.code == "CUTOFF_AT_OR_AFTER_KICKOFF"

    def test_cutoff_after_kickoff_refuses(self, db):
        target, _ = _ready_fixture(db, code="P26CA")
        db.refresh(target)
        with pytest.raises(PredictionBlocked) as exc:
            execute_pre_match_prediction(
                db, target.id, target.kickoff_at + timedelta(minutes=1))
        assert exc.value.code == "CUTOFF_AT_OR_AFTER_KICKOFF"

    def test_unknown_match_refuses(self, db):
        with pytest.raises(PredictionBlocked) as exc:
            execute_pre_match_prediction(
                db, 999999, datetime.now(timezone.utc))
        assert exc.value.code == "UNKNOWN_MATCH"


# -- config ----------------------------------------------------------------------------------------

class TestConfigValidation:
    def test_invalid_model_refuses(self, db):
        target, cutoff = _ready_fixture(db, code="P26IM")
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        with pytest.raises(PredictionBlocked) as exc:
            execute_pre_match_prediction(db, target.id, cutoff,
                                         model_id="nope_v9")
        assert exc.value.code == "UNSUPPORTED_MODEL"


# -- validation ------------------------------------------------------------------------------------

def _valid_payload():
    return {
        "status": "valid",
        "home_win_probability": 0.6,
        "draw_probability": 0.25,
        "away_win_probability": 0.15,
        "expected_home_goals": 1.7,
        "expected_away_goals": 0.9,
        "expected_total_goals": 2.6,
        "over_2_5_probability": 0.55,
        "under_2_5_probability": 0.45,
        "btts_yes_probability": 0.5,
        "btts_no_probability": 0.5,
        "score_probabilities": {"1-0": 0.12, "2-1": 0.09},
    }


class TestOutputValidation:
    def test_valid_payload_passes(self):
        assert validate_prediction_output(_valid_payload()) == []

    def test_non_valid_status_rejected(self):
        p = _valid_payload()
        p["status"] = "insufficient_data"
        assert validate_prediction_output(p) != []

    def test_probability_out_of_range(self):
        p = _valid_payload()
        p["home_win_probability"] = 1.5
        assert validate_prediction_output(p) != []

    def test_probability_sum_rejected(self):
        p = _valid_payload()
        p["away_win_probability"] = 0.5
        assert validate_prediction_output(p) != []

    def test_negative_lambda_rejected(self):
        p = _valid_payload()
        p["expected_home_goals"] = -0.3
        assert validate_prediction_output(p) != []

    def test_nan_rejected(self):
        p = _valid_payload()
        p["draw_probability"] = float("nan")
        assert validate_prediction_output(p) != []

    def test_infinity_rejected(self):
        p = _valid_payload()
        p["expected_away_goals"] = float("inf")
        violations = validate_prediction_output(p)
        assert violations != []

    def test_inconsistent_markets_rejected(self):
        p = _valid_payload()
        p["under_2_5_probability"] = 0.9
        assert validate_prediction_output(p) != []

    def test_bad_score_grid_rejected(self):
        p = _valid_payload()
        p["score_probabilities"] = {"1-0": float("nan")}
        assert validate_prediction_output(p) != []


# -- immutability + idempotency + hashing ------------------------------------------------------------

class TestImmutabilityIdempotencyHashing:
    def test_repeated_execution_reuses_snapshot(self, db):
        target, cutoff = _ready_fixture(db, code="P26ID")
        _, first = _execute(db, target, cutoff)
        second = execute_pre_match_prediction(db, target.id, cutoff)
        assert second["cache_hit"] is True
        assert second["prediction_id"] == first["prediction_id"]
        count = db.query(PreMatchPredictionSnapshot).filter_by(
            match_id=target.id).count()
        assert count == 1

    def test_changed_cutoff_creates_new_snapshot(self, db):
        target, cutoff = _ready_fixture(db, code="P26CC")
        _, first = _execute(db, target, cutoff)
        new_cutoff = cutoff + timedelta(minutes=15)
        generate_readiness_certificate(db, target.id, cutoff=new_cutoff)
        second = execute_pre_match_prediction(db, target.id, new_cutoff)
        assert second["prediction_id"] != first["prediction_id"]
        assert second["prediction_version"] == first["prediction_version"] + 1
        # Previous snapshot byte-identical in DB.
        again = get_prediction(db, first["prediction_id"])
        assert again["prediction_hash"] == first["prediction_hash"]
        assert again["prediction_payload"] == first["prediction_payload"]

    def test_execution_key_deterministic(self):
        k1 = execution_key(7, "2024-09-01T12:00:00", MODEL_ID, MODEL_ID, "abc")
        k2 = execution_key(7, "2024-09-01T12:00:00", MODEL_ID, MODEL_ID, "abc")
        assert k1 == k2
        assert execution_key(8, "2024-09-01T12:00:00", MODEL_ID, MODEL_ID, "abc") != k1
        assert execution_key(7, "2024-09-01T12:05:00", MODEL_ID, MODEL_ID, "abc") != k1
        assert execution_key(7, "2024-09-01T12:00:00", MODEL_ID, MODEL_ID, "abd") != k1

    def test_prediction_hash_sensitivity(self, db):
        target, cutoff = _ready_fixture(db, code="P26HS")
        _, first = _execute(db, target, cutoff)
        altered = dict(first["prediction_payload"])
        altered["prediction"]["home_win_probability"] = 0.12345
        assert canonical_hash(altered) != first["prediction_hash"]

    def test_feature_snapshot_reused(self, db):
        target, cutoff = _ready_fixture(db, code="P26FS")
        _, first = _execute(db, target, cutoff)
        execute_pre_match_prediction(db, target.id, cutoff)
        count = db.query(PredictionFeatureSnapshot).filter_by(
            match_id=target.id).count()
        assert count == 1
        assert first["feature_snapshot_hash"]

    def test_readiness_binding_recorded(self, db):
        target, cutoff = _ready_fixture(db, code="P26RB")
        cert, result = _execute(db, target, cutoff)
        assert result["readiness_certificate_id"] == cert.certificate_id
        assert result["readiness_certificate_hash"] == cert.payload_hash


# -- API --------------------------------------------------------------------------------------------

class TestPredictionAPI:
    def test_post_success(self, client, db):
        target, cutoff = _ready_fixture(db, code="P26API")
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        resp = client.post(
            f"/api/v1/matches/{target.id}/predictions",
            json={"cutoff": cutoff.isoformat()})
        assert resp.status_code == 200
        body = resp.json()
        assert body["blocked"] is False
        assert body["prediction_id"].startswith("pred_")

    def test_post_duplicate_returns_same(self, client, db):
        target, cutoff = _ready_fixture(db, code="P26APID")
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        payload = {"cutoff": cutoff.isoformat()}
        first = client.post(
            f"/api/v1/matches/{target.id}/predictions", json=payload).json()
        second = client.post(
            f"/api/v1/matches/{target.id}/predictions", json=payload).json()
        assert second["prediction_id"] == first["prediction_id"]
        assert second["cache_hit"] is True

    def test_post_blocked_match(self, client, db):
        league = _league(db, "P26APIB")
        home, away = _teams(db, league, "P26APIB")
        now = datetime.now(timezone.utc)
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p26-P26APIB-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        cutoff = now + timedelta(hours=1)
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        resp = client.post(
            f"/api/v1/matches/{target.id}/predictions",
            json={"cutoff": cutoff.isoformat()})
        assert resp.status_code == 200
        assert resp.json()["blocked"] is True

    def test_post_invalid_match(self, client):
        resp = client.post(
            "/api/v1/matches/999999/predictions",
            json={"cutoff": datetime.now(timezone.utc).isoformat()})
        assert resp.status_code == 200
        assert resp.json()["code"] == "UNKNOWN_MATCH"

    def test_post_missing_cutoff(self, client, db):
        target, _ = _ready_fixture(db, code="P26APIM")
        resp = client.post(f"/api/v1/matches/{target.id}/predictions",
                           json={})
        assert resp.status_code == 422

    def test_get_status_and_detail(self, client, db):
        target, cutoff = _ready_fixture(db, code="P26APIG")
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        created = client.post(
            f"/api/v1/matches/{target.id}/predictions",
            json={"cutoff": cutoff.isoformat()}).json()
        status = client.get(
            f"/api/v1/matches/{target.id}/prediction-snapshots").json()
        assert status["prediction_count"] == 1
        assert status["status"] in ("GENERATED", "DEGRADED")
        detail = client.get(
            f"/api/v1/prediction-snapshots/{created['prediction_id']}").json()
        assert detail["prediction_id"] == created["prediction_id"]

    def test_get_unknown_prediction_404(self, client):
        resp = client.get("/api/v1/prediction-snapshots/pred_nope_123")
        assert resp.status_code == 404

    def test_describe_statuses(self, db):
        target, cutoff = _ready_fixture(db, code="P26DSC")
        assert describe_match_predictions(db, target.id)["status"] in (
            "NOT_GENERATED", "BLOCKED")
        _, result = _execute(db, target, cutoff)
        status = describe_match_predictions(db, target.id)
        assert status["status"] in ("GENERATED", "DEGRADED")
        assert status["latest"]["prediction_id"] == result["prediction_id"]


# -- migration chain -------------------------------------------------------------------------------------------

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

    def test_0011_exists_with_correct_chain(self):
        mod = self._load("0011_prediction_snapshots")
        assert mod.revision == "0011_prediction_snapshots"
        assert mod.down_revision == "0010_prematch_readiness"
        assert mod.branch_labels is None

    def test_0011_links_into_chain(self):
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
        # 0011 must chain 0010 -> 0011; head ownership belongs to the
        # latest phase test (no branch divergence).
        assert revisions["0011_prediction_snapshots"] == \
            "0010_prematch_readiness"
        down_revs = {v for v in revisions.values() if v is not None}
        heads = [r for r in revisions if r not in down_revs]
        assert len(heads) == 1

    def test_snapshot_tables_created(self, db):
        from app.db.models.prediction_snapshots import (
            PredictionFeatureSnapshot,
            PreMatchPredictionSnapshot,
        )

        assert db.query(PredictionFeatureSnapshot).count() == 0
        assert db.query(PreMatchPredictionSnapshot).count() == 0


# -- golden regression -------------------------------------------------------------------------------

class TestGoldenRegression:
    def test_ensemble_values_unchanged(self, db):
        from tests.test_phase17b_match_intelligence import _build
        from tests.test_phase17b_match_intelligence import (
            _history as _gold_history,
        )

        _, _, target = _gold_history(db, code="P26GOLD")
        doc = _build(db, target)
        core = doc["core_prediction"]
        xg = doc["expected_goals"]
        assert core["home"] == pytest.approx(0.60605, rel=1e-3)
        assert core["draw"] == pytest.approx(0.22233, rel=1e-3)
        assert core["away"] == pytest.approx(0.17161, rel=1e-3)
        assert xg["home_lambda"] == pytest.approx(1.7442, rel=1e-3)
        assert xg["away_lambda"] == pytest.approx(0.1713, rel=1e-3)
        assert core["model_version"] == "ensemble_v1-elo+poisson"


# -- adversarial leakage ------------------------------------------------------------------------------

class TestAdversarialLeakage:
    def _leakage_pair(self, db, code, add_post_cutoff):
        target, cutoff = _ready_fixture(db, code=code)
        _, before = _execute(db, target, cutoff)
        add_post_cutoff(db, target, cutoff)
        after = execute_pre_match_prediction(db, target.id, cutoff)
        return before, after

    def test_post_cutoff_result_ignored(self, db):
        def add(db, target, cutoff):
            lg_id = target.league_id
            extra = Match(
                league_id=lg_id, home_team_id=target.home_team_id,
                away_team_id=target.away_team_id,
                kickoff_at=cutoff + timedelta(minutes=5),
                status="FINISHED", home_score=5, away_score=0,
                provider="t", provider_match_id="p26-leak-result")
            db.add(extra)
            db.commit()

        before, after = self._leakage_pair(db, "P26LKR", add)
        assert after["cache_hit"] is True
        assert after["prediction_hash"] == before["prediction_hash"]

    def test_post_cutoff_odds_ignored(self, db):
        def add(db, target, cutoff):
            db.add(OddsSnapshot(
                match_id=target.id, market_type="1x2",
                timestamp=cutoff + timedelta(minutes=5)))
            db.commit()

        before, after = self._leakage_pair(db, "P26LKO", add)
        assert after["prediction_hash"] == before["prediction_hash"]

    def test_post_cutoff_event_ignored(self, db):
        def add(db, target, cutoff):
            db.add(MatchEvent(
                match_id=target.id, team="home",
                event_type="goal", minute=90))
            db.commit()

        before, after = self._leakage_pair(db, "P26LKE", add)
        assert after["prediction_hash"] == before["prediction_hash"]

    def test_post_cutoff_lineup_ignored(self, db):
        def add(db, target, cutoff):
            db.add(Lineup(match_id=target.id, team_id=target.home_team_id,
                          team="home", player_name="Late Sub",
                          recorded_at=cutoff + timedelta(minutes=5),
                          effective_at=cutoff + timedelta(minutes=5)))
            db.commit()

        before, after = self._leakage_pair(db, "P26LKL", add)
        assert after["prediction_hash"] == before["prediction_hash"]


# -- scheduler -----------------------------------------------------------------------------------------

class TestSchedulerIntegration:
    def test_job_type_registered(self):
        from app.services.scheduler import ALL_JOB_TYPES, get_job_config
        from app.services.scheduler.config import JOB_PRE_MATCH_PREDICTION
        from app.services.scheduler.executors import get_executor

        assert JOB_PRE_MATCH_PREDICTION in ALL_JOB_TYPES
        cfg = get_job_config(JOB_PRE_MATCH_PREDICTION)
        assert cfg["enabled"] is True
        assert get_executor(JOB_PRE_MATCH_PREDICTION).__name__ == \
            "execute_pre_match_prediction"

    def test_executor_dry_run(self, db):
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import JOB_PRE_MATCH_PREDICTION
        from app.services.scheduler.executors import get_executor

        target, cutoff = _ready_fixture(db, code="P26SCH")
        generate_readiness_certificate(db, target.id, cutoff=cutoff)
        cfg = get_job_config(JOB_PRE_MATCH_PREDICTION)
        cfg["competitions"] = ["P26SCH"]
        result = get_executor(JOB_PRE_MATCH_PREDICTION)(
            db, cfg, dry_run=True)
        assert result["status"] == "dry_run"
        assert target.id in result["due_match_ids"]

    def test_executor_skips_blocked(self, db):
        from app.services.scheduler import get_job_config
        from app.services.scheduler.config import JOB_PRE_MATCH_PREDICTION
        from app.services.scheduler.executors import get_executor

        league = _league(db, "P26SCHB")
        home, away = _teams(db, league, "P26SCHB")
        now = datetime.now(timezone.utc)
        target = Match(
            league_id=league.id, home_team_id=home.id, away_team_id=away.id,
            kickoff_at=now + timedelta(hours=5), status="SCHEDULED",
            provider="t", provider_match_id="p26-P26SCHB-target")
        db.add(target)
        db.commit()
        db.refresh(target)
        generate_readiness_certificate(
            db, target.id, cutoff=now + timedelta(hours=1))
        cfg = get_job_config(JOB_PRE_MATCH_PREDICTION)
        cfg["competitions"] = ["P26SCHB"]
        result = get_executor(JOB_PRE_MATCH_PREDICTION)(
            db, cfg, dry_run=True)
        assert target.id in result["skipped_blocked"]
        assert target.id not in result["due_match_ids"]
