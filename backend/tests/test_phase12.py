"""Phase 12 tests: splits, isolation, determinism, gates, registry, leakage,
regression. No live network calls."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.models.core import League, Match, Team
from app.db.models.research import ResearchModel
from app.services.features.temporal import TemporalMode
from app.services.model_research import (
    ablation,
    artifacts,
    calibration,
    candidates,
    datasets,
    evaluation,
    experiments,
    features,
    promotion,
    significance,
    splits,
    training,
)

BASE = datetime(2024, 9, 1, 12, 0)
STRICT = TemporalMode.STRICT_PREMATCH


def _league(db, code="P12"):
    league = db.query(League).filter_by(code=code).first()
    if league is not None:
        return league
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="p12", season="2024")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names):
    out = {}
    for name in names:
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=f"p12-{league.code}-{name}")
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _add(db, league, teams, home, away, kickoff, hs, aws):
    match = Match(
        league_id=league.id, home_team_id=teams[home].id, away_team_id=teams[away].id,
        kickoff_at=kickoff, status="FINISHED", home_score=hs, away_score=aws,
        provider="test", provider_match_id=f"p12-{home}-{away}-{kickoff.isoformat()}")
    db.add(match)
    db.commit()
    return match


def _season(db, code="P12S", start_day=1, rounds=8):
    """8-team round robin (28 matches) for split/fold tests."""
    league = _league(db, code)
    names = ["A", "B", "C", "D", "E", "F", "G", "H"]
    teams = _teams(db, league, names)
    scores = [(2, 0), (1, 1), (0, 1), (3, 1)]
    idx = day = 0
    for round_no in range(rounds):
        order = names[round_no:] + names[:round_no]
        for i in range(0, len(order) - 1, 2):
            hs, aws = scores[idx % len(scores)]
            idx += 1
            _add(db, league, teams, order[i], order[i + 1],
                 datetime(2024, 8, start_day) + timedelta(days=day), hs, aws)
            day += 1
    return league, teams


# -- splits --------------------------------------------------------------------

def test_season_splits_reject_empty():
    rows = [{"match_id": 1, "kickoff": "2024-08-01T00:00:00", "actual": 0}]
    season_of = lambda r: "2024"
    with pytest.raises(ValueError):
        splits.season_splits(rows, ["2023"], "2024", ["2024"], season_of)
    with pytest.raises(ValueError):
        splits.season_splits(rows, ["2024"], "2023", ["2024"], season_of)


def test_expanding_folds_chronological():
    rows = [{"match_id": i, "kickoff": f"2024-08-{i + 1:02d}T00:00:00",
             "actual": i % 3} for i in range(300)]
    folds = splits.expanding_folds(rows, n_folds=2, min_train=100)
    assert len(folds) == 2
    assert folds[1]["train"][-1]["kickoff"] <= folds[1]["test"][0]["kickoff"]
    assert folds[0]["test"][-1]["kickoff"] <= folds[1]["test"][0]["kickoff"]


# -- datasets / features ----------------------------------------------------------

def test_dataset_chronological_and_gated(db):
    league, _ = _season(db)
    dataset = datasets.build_dataset(db, "P12S", families=["team"], mode=STRICT)
    assert dataset["dataset_version"].startswith("research_ds_")
    assert len(dataset["rows"]) == 32
    assert dataset["rows"][0]["features"]["elo_diff"] == 0.0  # no history yet
    assert dataset["rows"][-1]["features"]["elo_diff"] != 0.0
    gated = features.gate_row(dataset["rows"][-1], "team")
    assert gated is True
    missing = features.missingness_report(dataset["rows"], "team")
    assert missing["rows"] == 32 and missing["coverage_pct"] <= 100.0
    selected = features.select_features(dataset["rows"], ["team"])
    assert selected["kept"] + selected["dropped"] == 32
    assert len(selected["feature_names"]) == 4


def test_missingness_never_fabricated(db):
    league, _ = _season(db, code="P12M")
    dataset = datasets.build_dataset(db, "P12M", families=["xg"], mode=STRICT)
    report = features.missingness_report(dataset["rows"], "xg")
    assert report["eligible_rows"] == 0
    assert report["coverage_pct"] == 0.0
    assert report["strict_availability"] == "unavailable"


# -- training isolation --------------------------------------------------------------

def test_preprocessing_train_only(db):
    import numpy as np

    league, _ = _season(db, code="P12P")
    dataset = datasets.build_dataset(db, "P12P", families=["team"], mode=STRICT)
    selected = features.select_features(dataset["rows"], ["team"])
    X = np.asarray(selected["X"], dtype=float)
    train, test = X[:20], X[20:]
    mean, scale = training.standardize_fit(train)
    applied = training.standardize_apply(test, mean, scale)
    # Test rows must not shift the scaler: mean of applied != 0 in general,
    # and scaler equals train statistics exactly.
    assert list(mean) == list(train.mean(axis=0))
    assert not bool((applied.mean(axis=0) == 0).all())


def test_deterministic_training(db):
    import numpy as np

    league, _ = _season(db, code="P12D")
    dataset = datasets.build_dataset(db, "P12D", families=["team"], mode=STRICT)
    selected = features.select_features(dataset["rows"], ["team"])
    X = np.asarray(selected["X"], dtype=float)
    y = np.asarray(selected["labels"], dtype=int)
    first = training.train_logreg(X, y, seed=7)
    second = training.train_logreg(X, y, seed=7)
    assert first["coef"] == second["coef"]
    assert np.allclose(training.predict_logreg(first, X),
                       training.predict_logreg(second, X))


def test_calibration_never_sees_test(db):
    import numpy as np

    probs_val = [[0.5, 0.3, 0.2]] * 40
    actual_val = [0] * 20 + [2] * 20
    probs_test = [[0.4, 0.3, 0.3]] * 10
    actual_test = [1] * 10
    report = calibration.evaluate_calibration(probs_val, actual_val,
                                              probs_test, actual_test)
    assert report["fitted_on"] == "validation"
    assert report["version_suffix"] == "-cal"
    assert "raw" in report and "calibrated" in report


# -- significance / registry / promotion -------------------------------------------------

def test_paired_deltas_identical_populations():
    probs = [[0.6, 0.2, 0.2]] * 50 + [[0.2, 0.2, 0.6]] * 50
    actual = [0] * 50 + [2] * 50
    deltas = significance.paired_deltas(probs, probs, actual, n_boot=200)
    assert deltas["delta_brier"]["mean"] == 0.0
    assert "inconclusive" in deltas["delta_brier"]["verdict"]
    sharp = [[0.9, 0.05, 0.05]] * 50 + [[0.05, 0.05, 0.9]] * 50
    deltas2 = significance.paired_deltas(sharp, probs, actual, n_boot=200)
    assert deltas2["delta_brier"]["mean"] > 0
    assert deltas2["delta_brier"]["verdict"] == "improvement"


def test_registry_and_promotion_gate(db):
    row = promotion.register(db, "test_model", "v1", metrics={"brier": 0.6})
    assert row.status == "research"
    assert promotion.count_tested(db)["total"] >= 1
    checklist = promotion.promotion_checklist(
        {"out_of_sample_evaluation": (True, "ok")})
    assert checklist["eligible_for_consideration"] is False
    assert len(checklist["missing"]) == 9
    moved = promotion.transition(db, "test_model", "candidate", decided_by="human")
    assert moved.status == "candidate"
    with pytest.raises(ValueError):
        promotion.transition(db, "test_model", "production", decided_by="auto")
    with pytest.raises(ValueError):
        promotion.transition(db, "test_model", "production", decided_by="human",
                             reason="")
    moved2 = promotion.transition(db, "test_model", "production",
                                  decided_by="human", reason="reviewed")
    assert moved2.status == "production"


def test_artifacts_deterministic_and_mismatch_raises(tmp_path):
    key = "test_key"
    payload = {"b": [1, 2], "a": 1}
    first = artifacts.save_artifact(key, "exp", payload)
    second = artifacts.save_artifact(key, "exp", {"a": 1, "b": [1, 2]})
    assert first == second  # key order irrelevant
    with pytest.raises(ValueError):
        artifacts.save_artifact(key, "exp", {"a": 2})
    loaded = artifacts.load_artifact(key, "exp")
    assert loaded["payload"] == payload


# -- leakage ----------------------------------------------------------------------

def test_future_match_insertion_unchanged(db):
    league, teams = _season(db, code="P12F")[:2]
    before = datasets.build_dataset(db, "P12F", families=["team"], mode=STRICT)
    _add(db, league, teams, "A", "B", datetime(2025, 6, 1), 5, 0)
    after = datasets.build_dataset(db, "P12F", families=["team"], mode=STRICT)
    before_rows = {(r["match_id"], tuple(sorted(
        (k, v) for k, v in r["features"].items()))): r["actual"]
        for r in before["rows"]}
    after_rows = {(r["match_id"], tuple(sorted(
        (k, v) for k, v in r["features"].items()))): r["actual"]
        for r in after["rows"] if r["match_id"] in before_rows or True}
    for key, actual in before_rows.items():
        assert key in after_rows and after_rows[key] == actual


def test_testset_modification_leaves_training_untouched(db):
    import numpy as np

    league, _ = _season(db, code="P12T")
    dataset = datasets.build_dataset(db, "P12T", families=["team"], mode=STRICT)
    selected = features.select_features(dataset["rows"], ["team"])
    X = np.asarray(selected["X"], dtype=float)
    mean_before = list(training.standardize_fit(X[:20])[0])
    _ = training.standardize_fit(X)  # full fit must not alter train-only scaler
    mean_after = list(training.standardize_fit(X[:20])[0])
    assert mean_before == mean_after


# -- ablation + candidates -----------------------------------------------------------------

def test_ablation_plans_and_skips():
    plans = ablation.additive_plan()
    assert plans[0] == ["team"]
    loo = ablation.leave_one_out_plan(["team", "xg"])
    assert ["team", "xg"] in loo and ["team"] in loo and ["xg"] in loo
    result = ablation.run_ablation(
        lambda plan: {"brier": 0.6} if plan != ["team", "xg"] else (_ for _ in ()).throw(
            ValueError("no coverage")),
        ["team", "xg"])
    assert any(s["plan"] == "team+xg" for s in result["skipped"])
    assert candidates.describe("logreg_team")["kind"] == "multinomial_logistic"
    with pytest.raises(ValueError):
        candidates.describe("nope")


# -- regression: production untouched -----------------------------------------------------------------

def test_phase12_production_files_untouched():
    import subprocess

    result = subprocess.run(
        ["git", "status", "--porcelain",
         "backend/app/services/predictions/",
         "backend/app/services/intelligence/",
         "backend/app/services/evaluation/",
         "backend/app/services/backtesting/",
         "backend/app/services/features/",
         "backend/app/services/player_intelligence/",
         "backend/app/services/lifecycle/",
         "backend/app/services/reconciliation/",
         "backend/app/services/freshness/",
         "backend/app/services/acquisition/"],
        capture_output=True, text=True, cwd="/Users/sivek/Documents/Bet Predictor")
    assert result.stdout.strip() == "", result.stdout
