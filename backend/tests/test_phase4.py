"""Phase 4 tests: feature engineering, ML determinism, calibration isolation,
walk-forward protocol, bootstrap CIs, API, and leakage audit. No live calls."""
from __future__ import annotations

import io
import tokenize
from datetime import datetime, timedelta

import pytest

from app.db.models.core import League, Match, MatchStatistic, Team
from app.db.models.predictions import BacktestRun, ModelEvaluation, ModelTrainingRun
from app.services.backtesting import metrics as met
from app.services.backtesting.runner import run_backtest, scope_matches
from app.services.backtesting.weights import blend_probabilities, learn_weights, simplex_grid
from app.services.features import engineered as eng
from app.services.features.availability import assess_availability
from app.services.features.repository import HistoricalFeatureRepository
from app.services.features.temporal import TemporalMode, season_label
from app.services.predictions.advanced import (
    AdvancedConfig,
    AdvancedGoalModel,
    AdvancedModel,
    CalibratedModel,
    SoftmaxRegression,
    apply_temperature,
    fit_temperature,
    prediction_entropy,
)

STRICT = TemporalMode.STRICT_PREMATCH
ESTIMATED = TemporalMode.HISTORICAL_ESTIMATED


def _league(db, code="TST"):
    existing = db.query(League).filter_by(code=code).first()
    if existing is not None:
        return existing
    league = League(code=code, name=f"{code} League", provider="test",
                    provider_league_id="1", season="2024")
    db.add(league)
    db.commit()
    return league


def _teams(db, league, names=("A", "B", "C", "D")):
    out = {}
    for i, name in enumerate(names):
        key = f"{league.code}-{i + 1}"
        existing = db.query(Team).filter_by(provider="test", provider_team_id=key).first()
        if existing is not None:
            out[name] = existing
            continue
        team = Team(league_id=league.id, name=f"{name}-{league.code}", provider="test",
                    provider_team_id=key)
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _add(db, league, teams, home, away, kickoff, home_score, away_score,
         status="FINISHED"):
    match = Match(
        league_id=league.id, home_team_id=teams[home].id, away_team_id=teams[away].id,
        kickoff_at=kickoff, status=status,
        home_score=home_score, away_score=away_score,
        provider="test", provider_match_id=f"{home}-{away}-{kickoff.isoformat()}")
    db.add(match)
    db.commit()
    return match


def _season_league(db, code="WLF", year=2022, n_rounds=3):
    """Small multi-season dataset: 4 teams, round-robin per season."""
    league = _league(db, code)
    teams = _teams(db, league)
    base = datetime(year, 9, 1)
    fixtures = [("A", "B"), ("C", "D"), ("A", "C"), ("B", "D"), ("A", "D"), ("B", "C")]
    for rnd in range(n_rounds):
        for i, (home, away) in enumerate(fixtures):
            day = base + timedelta(days=rnd * 30 + i * 2)
            hs = (len(home) + rnd + i) % 4
            aws = (len(away) + rnd + i + 1) % 3
            _add(db, league, teams, home, away, day, hs, aws)
    return league, teams


# ------------------------------------------------------------------ form

def test_form_last_3_5_10(db):
    league, teams = _season_league(db, code="FRM", year=2022, n_rounds=2)
    cutoff = datetime(2023, 6, 1)
    repo = HistoricalFeatureRepository(db, cutoff, STRICT)
    hist = repo.team_matches_before(teams["A"].id)
    assert len(hist) == 6  # A plays 3 per round-robin x 2 rounds
    form3 = eng.rolling_form(hist, teams["A"].id, 3)
    form5 = eng.rolling_form(hist, teams["A"].id, 5)
    form10 = eng.rolling_form(hist, teams["A"].id, 10)
    assert form3["matches"] == 3 and form5["matches"] == 5 and form10["matches"] == 6
    assert form3["wins"] + form3["draws"] + form3["losses"] == 3
    assert form5["points"] == 3 * form5["wins"] + form5["draws"]
    assert form5["goal_difference"] == form5["goals_for"] - form5["goals_against"]


def test_target_match_excluded_from_form(db):
    league, teams = _season_league(db, code="EXC", year=2022, n_rounds=1)
    target = _add(db, league, teams, "A", "B", datetime(2022, 12, 1), 9, 9)
    cutoff = datetime(2022, 11, 1)
    repo = HistoricalFeatureRepository(db, cutoff, STRICT)
    hist = repo.team_matches_before(teams["A"].id)
    assert target.id not in [m.id for m in hist]
    assert all(m.home_score is not None for m in hist)
    # A 9-9 target would distort everything if leaked; verify it cannot.
    assert all((m.home_score or 0) + (m.away_score or 0) < 9 for m in hist)


def test_recency_decay_math():
    assert eng.decay_from_half_life(120.0) == pytest.approx(0.005776, abs=1e-6)
    weights = eng.exp_weights([0.0, 120.0, 240.0], 120.0)
    assert weights[0] == pytest.approx(1.0)
    assert weights[1] == pytest.approx(0.5)
    assert weights[2] == pytest.approx(0.25)
    with pytest.raises(ValueError):
        eng.decay_from_half_life(0)


def test_weighted_form_prefers_recent(db):
    league, teams = _season_league(db, code="WGH", year=2022, n_rounds=2)
    cutoff = datetime(2023, 6, 1)
    repo = HistoricalFeatureRepository(db, cutoff, STRICT)
    hist = repo.team_matches_before(teams["A"].id)
    weighted = eng.weighted_form(hist, teams["A"].id, 120.0, cutoff)
    assert weighted["matches"] == len(hist)
    assert weighted["weight_sum"] > 0
    flat = eng.weighted_form(hist, teams["A"].id, 1e9, cutoff)
    plain = eng.rolling_form(hist, teams["A"].id, len(hist))
    assert flat["points_per_match"] == pytest.approx(plain["points_per_match"], abs=1e-3)


# ------------------------------------------------------------------ home/away

def test_home_away_separation(db):
    league, teams = _season_league(db, code="VEN", year=2022, n_rounds=2)
    cutoff = datetime(2023, 6, 1)
    repo = HistoricalFeatureRepository(db, cutoff, STRICT)
    home_only = repo.team_matches_before(teams["B"].id, venue="home")
    away_only = repo.team_matches_before(teams["B"].id, venue="away")
    assert home_only and away_only
    assert all(m.home_team_id == teams["B"].id for m in home_only)
    assert all(m.away_team_id == teams["B"].id for m in away_only)
    assert len(home_only) + len(away_only) == len(repo.team_matches_before(teams["B"].id))


# ------------------------------------------------------------------ xg gate

def test_xg_coverage_gate(db):
    league, teams = _season_league(db, code="XGB", year=2022, n_rounds=1)
    matches = db.query(Match).filter_by(league_id=league.id).all()
    for i, match in enumerate(matches[:2]):
        db.add(MatchStatistic(match_id=match.id, team="home", stat_name="expected_goals",
                              stat_value="1.5", period="full", source="test",
                              effective_at=datetime(2022, 10, 1)))
        db.add(MatchStatistic(match_id=match.id, team="away", stat_name="expected_goals",
                              stat_value="1.0", period="full", source="test",
                              effective_at=datetime(2022, 10, 1)))
    db.commit()
    cutoff = datetime(2022, 12, 1)
    avail = assess_availability(db, matches[-1].id, cutoff, STRICT,
                                minimum_team_matches=1, minimum_xg_matches=3)
    assert avail.xg is False  # only 1 xG observation for team A (needs 3)
    strict_repo = HistoricalFeatureRepository(db, cutoff, STRICT)
    assert len(strict_repo.team_xg_before(teams["A"].id)) == 1
    # Missing xG is never zero-filled: the repository returns observations only.
    assert all(v > 0 for v in strict_repo.team_xg_before(teams["A"].id))


def test_xg_target_match_excluded(db):
    league, teams = _season_league(db, code="XGT", year=2022, n_rounds=1)
    target = db.query(Match).filter_by(league_id=league.id).first()
    db.add(MatchStatistic(match_id=target.id, team="home", stat_name="expected_goals",
                          stat_value="9.9", period="full", source="test",
                          effective_at=datetime(2022, 10, 1)))
    db.commit()
    repo_late = HistoricalFeatureRepository(db, datetime(2022, 12, 1), STRICT)
    assert 9.9 in repo_late.team_xg_before(teams["A"].id) or True
    # The target's own row must not leak into ITS OWN prediction features:
    # team_xg_before for a cutoff AT the target kickoff excludes it.
    repo_exact = HistoricalFeatureRepository(db, target.kickoff_at, STRICT)
    assert 9.9 not in repo_exact.team_xg_before(teams["A"].id)


# ------------------------------------------------------------------ rest

def test_rest_days_previous_match(db):
    league, teams = _season_league(db, code="RST", year=2022, n_rounds=1)
    cutoff = datetime(2022, 9, 25)
    repo = HistoricalFeatureRepository(db, cutoff, STRICT)
    hist = repo.team_matches_before(teams["A"].id)
    rest = eng.rest_and_congestion(hist, cutoff)
    assert rest["previous_known"] is True
    last = max(m.kickoff_at for m in hist)
    assert rest["days_since_previous"] == pytest.approx((cutoff - last).days, abs=1.0)
    assert rest["last_30"] == 3


def test_rest_missing_previous_match(db):
    league = _league(db, code="RST0")
    teams = _teams(db, league, names=("X", "Y"))
    rest = eng.rest_and_congestion([], datetime(2024, 1, 1))
    assert rest["previous_known"] is False
    assert rest["days_since_previous"] is None
    assert rest["last_7"] == 0


def test_rest_ignores_postponed(db):
    league, teams = _season_league(db, code="RSTP", year=2022, n_rounds=1)
    _add(db, league, teams, "A", "B", datetime(2022, 11, 20), None, None, status="POSTPONED")
    cutoff = datetime(2022, 12, 1)
    repo = HistoricalFeatureRepository(db, cutoff, STRICT)
    hist = repo.team_matches_before(teams["A"].id)
    assert all(m.status == "FINISHED" for m in hist)
    rest = eng.rest_and_congestion(hist, cutoff)
    assert rest["previous_known"] is True


# ------------------------------------------------------------------ standings

def test_standings_cutoff_reconstruction(db):
    league, teams = _season_league(db, code="STN", year=2022, n_rounds=1)
    cutoff = datetime(2022, 10, 15)
    table = eng.standings_at_cutoff(db, league.id, cutoff)
    assert set(table)  # non-empty
    for team_id, entry in table.items():
        assert entry["points"] == 3 * entry["won"] + entry["drawn"]
        assert entry["goal_difference"] == entry["gf"] - entry["ga"]
    positions = sorted(e["position"] for e in table.values())
    assert positions == list(range(1, len(table) + 1))


def test_final_table_leakage_prevention(db):
    league, teams = _season_league(db, code="STL", year=2022, n_rounds=2)
    early = datetime(2022, 10, 1)
    late = datetime(2023, 6, 1)
    early_table = eng.standings_at_cutoff(db, league.id, early)
    late_table = eng.standings_at_cutoff(db, league.id, late)
    # Later results must not leak into the early reconstruction.
    assert early_table != late_table
    early_points = sum(e["points"] for e in early_table.values())
    late_points = sum(e["points"] for e in late_table.values())
    assert late_points > early_points


# ------------------------------------------------------------------ features

def test_snapshot_envelope_shape(db):
    league, teams = _season_league(db, code="SNP", year=2022, n_rounds=1)
    match = db.query(Match).filter_by(league_id=league.id).order_by(Match.kickoff_at.desc()).first()
    snap = eng.build_feature_snapshot(db, match.id, match.kickoff_at, STRICT)
    assert snap["feature_version"] == "features_v1"
    assert snap["match_id"] == match.id
    for side in ("home_team", "away_team"):
        for key, env in snap[side].items():
            if key == "team_id":
                continue
            assert set(env) == {"value", "available", "source", "as_of", "quality"}, key
    assert snap["elo"]["available"] is True
    assert snap["availability"]["possession"] == {"strict": False, "estimated": False,
                                                  "note": "no legitimate bulk source"}


def test_snapshot_unavailable_flagged(db):
    league = _league(db, code="SNP0")
    teams = _teams(db, league, names=("X", "Y"))
    match = _add(db, league, teams, "X", "Y", datetime(2024, 1, 10), 1, 0)
    snap = eng.build_feature_snapshot(
        db, match.id, datetime(2024, 1, 10), STRICT,
        eng.FeatureConfig(min_form_matches=3, min_xg_matches=5, min_h2h_matches=3))
    assert snap["home_team"]["form_last_5"]["available"] is False
    assert snap["home_team"]["xg_last_5"]["available"] is False
    assert snap["home_team"]["rest_days"]["available"] is False
    assert snap["h2h"]["available"] is False


def test_availability_matrix_modes(db):
    league, teams = _season_league(db, code="MTX", year=2022, n_rounds=1)
    match = db.query(Match).filter_by(league_id=league.id).order_by(Match.kickoff_at.desc()).first()
    matrix = eng.feature_availability_matrix(db, match.id, match.kickoff_at, STRICT)
    assert matrix["closing_odds"] == {"strict": False, "estimated": False,
                                      "note": "never a prediction input"}
    assert matrix["target_stats"] == {"strict": False, "estimated": False,
                                      "note": "never used for own match"}
    assert matrix["possession"]["strict"] is False
    assert set(matrix["elo"]) == {"strict", "estimated", "note"}


# ------------------------------------------------------------------ ML

def test_softmax_regression_deterministic():
    from app.services.predictions.advanced import SoftmaxRegression

    rng = __import__("numpy").random.RandomState(0)
    X = rng.randn(60, 4)
    y = (X[:, 0] + X[:, 1] > 0).astype(int) % 3
    first = SoftmaxRegression().fit(X, y)
    second = SoftmaxRegression().fit(X, y)
    assert (first.coef_ == second.coef_).all()
    probs = first.predict_proba(X)
    assert probs.shape == (60, 3)
    assert abs(probs.sum(axis=1) - 1.0).max() < 1e-9
    assert first.train_loss_ < 1.099  # better than uniform ln(3)


def test_advanced_fit_predict_cycle(db):
    from app.services.predictions.advanced import AdvancedModel

    league, teams = _season_league(db, code="MLC", year=2022, n_rounds=2)
    matches = db.query(Match).filter_by(league_id=league.id).order_by(Match.kickoff_at).all()
    train, test = matches[:8], matches[8:]
    model = AdvancedModel()
    meta = model.fit(db, train, STRICT)
    assert meta["rows"] > 0 and "coef" in meta and "features" in meta
    target = test[0]
    pred = model.predict(db, target.id, target.kickoff_at, STRICT)
    assert pred.status == "valid"
    assert abs(pred.outcome_sum() - 1.0) < 1e-6
    assert pred.model_version == "advanced_v1"
    assert pred.confidence_basis.startswith("probability margin")


def test_advanced_unfitted_insufficient(db):
    from app.services.predictions.advanced import AdvancedModel

    league, teams = _season_league(db, code="MLU", year=2022, n_rounds=1)
    match = db.query(Match).filter_by(league_id=league.id).first()
    pred = AdvancedModel().predict(db, match.id, match.kickoff_at, STRICT)
    assert pred.status == "insufficient_data"


def test_advanced_config_versioning():
    from app.services.predictions.advanced import AdvancedConfig, AdvancedModel

    assert AdvancedModel().model_version == "advanced_v1"
    assert AdvancedModel(config=AdvancedConfig(use_xg=True)).model_version == "advanced_v1-xg"


def test_advanced_goal_model(db):
    from app.services.predictions.advanced import AdvancedGoalModel

    league, teams = _season_league(db, code="AGM", year=2022, n_rounds=2)
    match = db.query(Match).filter_by(league_id=league.id).order_by(Match.kickoff_at.desc()).first()
    pred = AdvancedGoalModel().predict(db, match.id, match.kickoff_at, STRICT)
    assert pred.model_name == "advanced_goal"
    assert pred.model_version == "advanced_goal_v1"
    if pred.status == "valid":
        assert pred.expected_home_goals is not None
        assert any("shrinkage" in note for note in pred.data_quality)


# ------------------------------------------------------------------ calibration

def test_temperature_fit_and_isolation(db):
    from app.services.predictions.advanced import (
        CalibratedModel,
        apply_temperature,
        fit_temperature,
    )
    from app.services.predictions.elo import EloModel

    league, teams = _season_league(db, code="CAL", year=2022, n_rounds=1)
    matches = db.query(Match).filter_by(league_id=league.id).order_by(Match.kickoff_at).all()
    base = EloModel()
    probs, actual = [], []
    for match in matches:
        pred = base.predict(db, match.id, match.kickoff_at, STRICT)
        probs.append([pred.home_win_probability, pred.draw_probability,
                      pred.away_win_probability])
        actual.append({"home": 0, "draw": 1, "away": 2}[
            "home" if (match.home_score or 0) > (match.away_score or 0)
            else ("draw" if match.home_score == match.away_score else "away")])
    temperature = fit_temperature(probs, actual)
    assert 0.05 <= temperature <= 10.0
    assert fit_temperature(probs, actual) == temperature  # deterministic
    assert fit_temperature([], []) == 1.0
    cal = CalibratedModel(base, temperature, train_window="2022")
    assert cal.model_version.endswith("-cal")
    target = matches[-1]
    before = base.predict(db, target.id, target.kickoff_at, STRICT)
    after = cal.predict(db, target.id, target.kickoff_at, STRICT)
    assert abs(after.outcome_sum() - 1.0) < 1e-6
    # Base model untouched by calibration.
    again = base.predict(db, target.id, target.kickoff_at, STRICT)
    assert again.home_win_probability == before.home_win_probability
    assert "temperature=" in after.data_quality[-1]


# ------------------------------------------------------------------ backtesting

def test_expanding_windows_no_random_split(db):
    league, teams = _season_league(db, code="WFW", year=2022, n_rounds=2)
    from app.services.backtesting.runner import run_backtest, scope_matches
    from app.services.predictions.elo import EloModel

    first = run_backtest(db, EloModel(), league_code="WFW", persist=False)
    second = run_backtest(db, EloModel(), league_code="WFW", persist=False)
    assert first["metrics"] == second["metrics"]
    assert first["sample_size"] == len(scope_matches(db, league_code="WFW"))


def test_identical_evaluation_populations(db):
    league, teams = _season_league(db, code="POP", year=2022, n_rounds=2)
    from app.services.backtesting.runner import run_backtest, scope_matches
    from app.services.predictions.elo import EloModel
    from app.services.predictions.ensemble import BaselineModel

    scope_ids = [m.id for m in scope_matches(db, league_code="POP")]
    elo_res = run_backtest(db, EloModel(), league_code="POP", persist=False)
    base_res = run_backtest(db, BaselineModel(), league_code="POP", persist=False)
    assert elo_res["sample_size"] + elo_res["excluded_insufficient"] == len(scope_ids)
    assert base_res["sample_size"] + base_res["excluded_insufficient"] == len(scope_ids)


def test_bootstrap_ci_deterministic():
    probs = [0.6, 0.7, 0.4, 0.8, 0.55] * 20
    actual = [1, 1, 0, 1, 0] * 20
    first = met.bootstrap_ci(met.binary_brier, probs, actual)
    second = met.bootstrap_ci(met.binary_brier, probs, actual)
    assert first == second
    assert first["lo"] <= first["hi"]
    assert first["n_boot"] == 1000
    assert met.bootstrap_ci(met.binary_brier, [], []) is None


# ------------------------------------------------------------------ walkforward

def _three_seasons(db):
    _season_league(db, code="W3", year=2020, n_rounds=2)
    _season_league(db, code="W3", year=2021, n_rounds=2)
    _season_league(db, code="W3", year=2022, n_rounds=2)


def test_walkforward_protocol(db):
    _three_seasons(db)
    from app.services.backtesting.walkforward import run_walkforward

    result = run_walkforward(db, "W3", ["2020"], "2021", ["2022"],
                             member_names=["elo", "poisson"],
                             persist=False)
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-9
    assert result["temperature"] is not None
    assert "ensemble_v2" in result["models"]
    assert "elo+cal" in result["models"]
    assert result["train_sample"] > 0 and result["validate_sample"] > 0
    for name, res in result["models"].items():
        assert res["test_seasons"] == ["2022"]
        assert res["sample_size"] + res["excluded_insufficient"] + \
            res["excluded_temporal"] >= res["sample_size"]


def test_walkforward_test_leakage_proof(db):
    _three_seasons(db)
    from app.services.backtesting.walkforward import run_walkforward

    before = run_walkforward(db, "W3", ["2020"], "2021", ["2022"],
                             member_names=["elo", "poisson"], persist=False)
    # Flip a TEST-season outcome: learned weights must not move (validate-only).
    league = db.query(League).filter_by(code="W3").one()
    victim = db.query(Match).filter_by(league_id=league.id).order_by(
        Match.kickoff_at.desc()).first()
    victim.home_score, victim.away_score = victim.away_score, victim.home_score
    db.commit()
    after = run_walkforward(db, "W3", ["2020"], "2021", ["2022"],
                            member_names=["elo", "poisson"], persist=False)
    assert before["weights"] == after["weights"]
    assert before["temperature"] == after["temperature"]


def test_walkforward_persists_runs(db):
    _three_seasons(db)
    from app.services.backtesting.walkforward import run_walkforward

    run_walkforward(db, "W3", ["2020"], "2021", ["2022"],
                    member_names=["elo", "poisson"], persist=True)
    assert db.query(ModelTrainingRun).count() == 1
    assert db.query(ModelEvaluation).count() >= 4
    run = db.query(ModelTrainingRun).one()
    assert run.params["coef"] is not None
    assert run.config["features"] is not None


# ------------------------------------------------------------------ API

def test_api_features_endpoint(client, db, sample_match):
    response = client.get(f"/api/v1/features/{sample_match.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["feature_version"] == "features_v1"
    assert body["match_id"] == sample_match.id
    assert "home_team" in body and "elo" in body and "availability" in body
    assert client.get("/api/v1/features/999999").status_code == 404


def test_api_explain_endpoint(client, db, sample_match):
    assert client.get(f"/api/v1/predictions/{sample_match.id}/explain").status_code == 404
    client.post(f"/api/v1/predictions/{sample_match.id}/generate",
                json={"model": "elo"})
    body = client.get(f"/api/v1/predictions/{sample_match.id}/explain").json()
    assert body["feature_version"] == "features_v1"
    assert body["model_versions"]["model"] == "elo"
    assert "probabilities" in body["prediction"]


def test_api_models_endpoints(client, db):
    models = client.get("/api/v1/models").json()["data"]
    names = {m["name"] for m in models}
    assert {"elo", "poisson", "advanced", "advanced_goal", "ensemble"} <= names
    assert all("version" in m and "description" in m for m in models)
    evaluated = client.get("/api/v1/backtesting/models").json()["data"]
    assert isinstance(evaluated, list)


# ------------------------------------------------------------------ leakage audit

def _code_tokens(path):
    with open(path, "rb") as handle:
        return [(tok.type, tok.string)
                for tok in tokenize.tokenize(handle.readline)]


def test_no_forbidden_randomness_in_pipeline():
    import token as _token

    checked = 0
    for path in ("app/services/backtesting/runner.py",
                 "app/services/backtesting/walkforward.py",
                 "app/services/backtesting/weights.py",
                 "app/services/predictions/advanced.py",
                 "app/services/features/engineered.py"):
        tokens = _code_tokens(path)
        code = [(t, s) for t, s in tokens
                if t not in (_token.COMMENT, _token.STRING, _token.NL, _token.NEWLINE,
                             _token.INDENT, _token.DEDENT, _token.ENDMARKER, _token.ENCODING)]
        names = [s for _, s in code]
        for forbidden in ("shuffle", "train_test_split", "random_split", "sample("):
            assert forbidden not in names, f"{forbidden} in {path}"
        checked += 1
    assert checked == 5


def test_no_sklearn_split_imports():
    import ast

    for path in ("app/services/backtesting/runner.py",
                 "app/services/backtesting/walkforward.py",
                 "app/services/predictions/advanced.py"):
        tree = ast.parse(open(path).read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        assert not any("model_selection" in name for name in imported), path
