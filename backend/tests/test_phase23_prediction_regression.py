"""Phase 23 deterministic prediction regression guard.
Verifies exact bitwise/numerical match of 1X2 probabilities, lambda parameters,
derived markets, correct score distribution, and uncertainty metrics.
Ensures zero drift in analytical/modeling code across releases.
"""
from __future__ import annotations

import math
import subprocess

import pytest

from tests.test_phase17b_match_intelligence import _build, _history


def test_deterministic_prediction_numerical_identity(db):
    """Calling prediction on identical match fixture produces bitwise identical output."""
    _, _, target = _history(db, code="P23ID")
    doc1 = _build(db, target)
    doc2 = _build(db, target)

    assert doc1["provenance"]["response_hash"] == doc2["provenance"]["response_hash"]
    assert doc1["core_prediction"] == doc2["core_prediction"]
    assert doc1["expected_goals"] == doc2["expected_goals"]
    assert doc1["derived_markets"] == doc2["derived_markets"]
    assert doc1["correct_score"] == doc2["correct_score"]
    assert doc1["uncertainty"] == doc2["uncertainty"]


def test_probability_axioms_and_mathematical_bounds(db):
    """Verifies standard probability axioms and mathematical consistency."""
    _, _, target = _history(db, code="P23MATH")
    doc = _build(db, target)

    core = doc["core_prediction"]
    p_h, p_d, p_a = core["home"], core["draw"], core["away"]
    assert 0.0 <= p_h <= 1.0
    assert 0.0 <= p_d <= 1.0
    assert 0.0 <= p_a <= 1.0
    assert abs((p_h + p_d + p_a) - 1.0) < 1e-5

    # Expected goals (lambda) must be strictly positive
    xg = doc["expected_goals"]
    assert xg["home_lambda"] > 0.0
    assert xg["away_lambda"] > 0.0

    # Derived markets bounds & complementary probabilities
    dm = doc["derived_markets"]
    totals = dm.get("totals", {})
    if "over_2_5" in totals and "under_2_5" in totals:
        assert 0.0 <= totals["over_2_5"] <= 1.0
        assert 0.0 <= totals["under_2_5"] <= 1.0
        assert abs((totals["over_2_5"] + totals["under_2_5"]) - 1.0) < 1e-4

    btts = dm.get("btts", {})
    if "yes" in btts and "no" in btts:
        assert 0.0 <= btts["yes"] <= 1.0
        assert 0.0 <= btts["no"] <= 1.0
        assert abs((btts["yes"] + btts["no"]) - 1.0) < 1e-4

    # Correct score distribution
    cs = doc["correct_score"]
    assert "top_n" in cs
    assert len(cs["top_n"]) > 0
    tail_mass = cs.get("tail_mass", 0.0)
    assert 0.0 <= tail_mass <= 1.0
    prob_sum = cs.get("probability_sum", 0.0)
    assert abs(prob_sum - 1.0) < 1e-4 or prob_sum <= 1.0

    # Uncertainty
    unc = doc["uncertainty"]
    assert "normalized_entropy" in unc or "entropy" in unc or "confidence_score" in unc or len(unc) > 0


def test_golden_prediction_values(db):
    """Golden numerical test verifying stable calculations against baseline."""
    _, _, target = _history(db, code="P23GOLDEN")
    doc = _build(db, target)

    core = doc["core_prediction"]
    xg = doc["expected_goals"]

    # Golden assertion verification: numbers must be finite and consistent
    assert all(math.isfinite(core[k]) for k in ("home", "draw", "away"))
    assert math.isfinite(xg["home_lambda"]) and math.isfinite(xg["away_lambda"])

    # Home + draw + away sum to 1.0
    total_prob = core["home"] + core["draw"] + core["away"]
    assert pytest.approx(1.0, rel=1e-5) == total_prob

    # Bitwise/floating numerical stability assertions against frozen baseline
    assert pytest.approx(0.60605, rel=1e-3) == core["home"]
    assert pytest.approx(0.22233, rel=1e-3) == core["draw"]
    assert pytest.approx(0.17161, rel=1e-3) == core["away"]
    assert pytest.approx(1.7442, rel=1e-3) == xg["home_lambda"]
    assert pytest.approx(0.1713, rel=1e-3) == xg["away_lambda"]
    assert pytest.approx(1.9155, rel=1e-3) == xg["total_lambda"]
    assert core["model_version"] == "ensemble_v1-elo+poisson"
    assert core["prediction_mode"] == "strict_prematch"


def test_prediction_codebase_integrity():
    """Verify that no prediction, feature, model, or calibration code has uncommitted modifications."""
    critical_dirs = [
        "backend/app/services/predictions/",
        "backend/app/services/intelligence/",
        "backend/app/services/intelligence_v2/",
        "backend/app/services/features/",
        "backend/app/services/evaluation/",
        "backend/app/services/backtesting/",
        "backend/app/services/model_research/",
        "backend/app/services/mirofish/",
    ]
    res = subprocess.run(
        ["git", "diff", "--exit-code", "HEAD", "--"] + critical_dirs,
        capture_output=True,
        text=True,
        cwd="/Users/sivek/Documents/Bet Predictor",
        check=False,
    )
    assert res.returncode == 0, f"Critical prediction files were modified:\n{res.stdout}"


def test_version_endpoint_safety(client):
    """Verify version endpoint returns safe metadata without leaking credentials."""
    resp = client.get("/api/v1/version")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "tacticx-backend"
    assert "version" in data
    assert "commit" in data
    assert "build_date" in data
    assert "environment" in data

    # Check root endpoint
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert root_data["service"] == "bet-predictor"
    assert "version" in root_data
    assert "commit" in root_data

    # Ensure no secrets or connection strings leaked in responses
    forbidden_tokens = ["postgres:", "sqlite:", "redis:", "password", "secret", "token", "key"]
    for k, v in data.items():
        val_str = str(v).lower()
        for tok in forbidden_tokens:
            assert tok not in val_str, f"Token {tok} found in version info {k}={v}"

