"""Phase 5 evaluation package tests: identical populations, paired diffs,
calibration, uncertainty, sensitivity, regimes, subgroups, artifacts.

Pure service-level tests (no live data, deterministic seeds). The full
backtest suite must stay green alongside these.
"""
from __future__ import annotations

import math
import random

from app.services.evaluation import (
    artifacts,
    calibration,
    compare,
    regimes,
    sensitivity,
    subgroups,
    uncertainty,
)


def _synthetic(n: int = 120, seed: int = 7):
    rng = random.Random(seed)
    sharp, flat = [], []
    for i in range(n):
        outcome = rng.choice([0, 1, 2])
        probs = [0.2, 0.2, 0.2]
        probs[outcome] = 0.6
        sharp.append({"match_id": i, "probs": probs, "actual": outcome})
        flat.append({"match_id": i, "probs": [1 / 3, 1 / 3, 1 / 3], "actual": outcome})
    return sharp, flat


def test_intersect_populations_keeps_only_shared_matches():
    a = [{"match_id": 1, "probs": [0.5, 0.25, 0.25], "actual": 0},
         {"match_id": 2, "probs": [0.5, 0.25, 0.25], "actual": 1}]
    b = [{"match_id": 2, "probs": [0.4, 0.3, 0.3], "actual": 1},
         {"match_id": 3, "probs": [0.4, 0.3, 0.3], "actual": 2}]
    out = compare.intersect_populations({"a": a, "b": b})
    assert out["_common_n"] == 1
    assert [r["match_id"] for r in out["a"]] == [2]
    assert [r["match_id"] for r in out["b"]] == [2]


def test_compare_pair_reports_n_and_paired_ci():
    sharp, flat = _synthetic()
    result = compare.compare_pair(sharp, flat, "sharp", "flat")
    assert result["n_a"] == result["n_b"] == result["n_common"] == 120
    # Sharp model is better: positive mean (B better... here A=sharp better
    # means metric(A) - metric(B) is negative).
    assert result["brier"]["mean"] < 0
    assert result["brier"]["ci"]["lo"] <= result["brier"]["mean"] <= result["brier"]["ci"]["hi"]
    assert result["brier"]["ci"]["n_boot"] == 2000


def test_compare_pair_no_shared_matches():
    a = [{"match_id": 1, "probs": [0.5, 0.25, 0.25], "actual": 0}]
    b = [{"match_id": 2, "probs": [0.5, 0.25, 0.25], "actual": 0}]
    result = compare.compare_pair(a, b)
    assert result["n_common"] == 0
    assert "cannot compare" in result["note"]


def test_calibration_per_class_structure_and_sparse_flags():
    sharp, _ = _synthetic()
    summary = calibration.calibration_summary(sharp, n_bins=5)
    assert set(summary["per_class"]) == {"home", "draw", "away"}
    assert summary["n"] == 120
    for name in ("home", "draw", "away"):
        for b in summary["curves"][name]["bins"]:
            assert "sparse" in b


def test_probability_margin_and_entropy_descriptive():
    row = {"match_id": 1, "probs": [0.6, 0.25, 0.15], "actual": 0}
    enriched = uncertainty.describe_details([row])
    assert enriched[0]["margin"] == round(0.6 - 0.25, 6)
    assert enriched[0]["top_class"] == 0
    assert 0 < enriched[0]["entropy"] < math.log(3) + 1e-9


def test_ensemble_disagreement_zero_for_identical_members():
    sharp, _ = _synthetic(n=30)
    result = uncertainty.ensemble_disagreement({"m1": sharp, "m2": list(sharp)})
    assert result["n_matches"] == 30
    assert result["aggregate"]["home"]["mean_std"] == 0.0


def test_poisson_tail_mass_sums_and_monotonic():
    inner_10 = sensitivity.poisson_tail_mass(1.5, 1.2, max_goals=10)
    inner_12 = sensitivity.poisson_tail_mass(1.5, 1.2, max_goals=12)
    assert 0 <= inner_10["outside_mass"] < 1e-4
    assert inner_12["outside_mass"] <= inner_10["outside_mass"]
    assert inner_10["inside_mass"] + inner_10["outside_mass"] == \
        round(inner_10["inside_mass"] + inner_10["outside_mass"], 8)


def test_truncation_audit_empty_and_shape():
    assert sensitivity.truncation_audit([])["n"] == 0
    out = sensitivity.truncation_audit([(1.5, 1.2), (5.7, 0.9)])
    assert out["n"] == 2
    assert out["max_outside_mass"] >= out["mean_outside_mass"]


def test_sensitivity_summary_deltas():
    base = {"accuracy_1x2": 0.5, "log_loss_1x2": 1.0, "brier_1x2": 0.6,
            "ece_home_win": 0.05}
    runs = [{"label": "x", "sample_size": 10,
             "metrics": {"accuracy_1x2": 0.51, "log_loss_1x2": 1.02,
                         "brier_1x2": 0.61, "ece_home_win": 0.04}}]
    out = sensitivity.summarize_sensitivity(base, runs)
    assert out["runs"][0]["delta"] == {"accuracy_1x2": 0.01, "log_loss_1x2": 0.02,
                                       "brier_1x2": 0.01, "ece_home_win": -0.01}


def test_mc_convergence_structure():
    sharp, _ = _synthetic(n=40)
    stats = sensitivity.mc_convergence_stats({1000: sharp, 10000: sharp})
    assert stats["counts"] == [1000, 10000]
    assert stats["comparisons"][0]["max_1x2_probability_difference"] == 0.0


def test_regime_policy_routes_on_availability_only():
    assert regimes.select_model({"goals": False})["model"] == "baseline_v1"
    assert regimes.select_model({"goals": True}, xg_eligible=True)["model"] == \
        "poisson_v1-xg"
    assert regimes.select_model({"goals": True})["model"] == "ensemble_v1"
    assert "elo_v1" in regimes.MODEL_STATUS_REGISTRY
    assert regimes.default_policy()["market_role"].startswith("independent")


def test_subgroup_min_n_gating():
    rows = [{"match_id": i, "probs": [0.5, 0.3, 0.2], "actual": 0} for i in range(10)]
    out = subgroups.bucketize(rows, lambda r: "only", label="t")
    assert out["groups"]["only"]["status"] == "insufficient_sample"


def test_extreme_audit_flags_small_buckets():
    sharp, _ = _synthetic()
    out = subgroups.extreme_probability_audit(sharp, thresholds=[0.9])
    assert out["buckets"]["0.9"]["status"] == "insufficient_sample"


def test_drift_diagnostics_rates():
    train = _synthetic(n=60, seed=7)[0]
    test = _synthetic(n=60, seed=8)[0]
    out = subgroups.drift_diagnostics(train, test)
    assert out["train_n"] == out["test_n"] == 60
    assert abs(sum(out["train_outcome_rates"].values()) - 1.0) < 1e-9


def test_run_id_deterministic_and_safe():
    first = artifacts.run_id("baseline", "abcdef123456", "EPL:2024/x")
    second = artifacts.run_id("baseline", "abcdef123456", "EPL:2024/x")
    assert first == second
    assert ":" not in first and "/" not in first
    assert first.startswith("phase5_baseline_")


def test_goal_and_score_audits_handle_empty():
    assert subgroups.goal_distribution_audit([])["status"] == "insufficient_sample"
    assert subgroups.score_distribution_audit([])["status"] == "insufficient_sample"


def test_validation_router_registered():
    from app.main import app as application

    paths = {r.path for r in application.routes}
    assert "/api/v1/validation/phase5/runs" in paths or any(
        "validation/phase5/runs" in p for p in paths)
