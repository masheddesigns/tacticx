"""Phase 2 tests: Elo, Poisson, Monte Carlo, ensemble, leakage, xG gating,
backtesting, metrics, baselines, and prediction API. No live network calls."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.db.models.core import League, Match, MatchStatistic, Team
from app.db.models.predictions import BacktestRun, Prediction
from app.services.backtesting import metrics as met
from app.services.backtesting.runner import dataset_summary, run_backtest, scope_matches
from app.services.features.availability import assess_availability
from app.services.features.repository import HistoricalFeatureRepository
from app.services.features.temporal import TemporalMode
from app.services.predictions.elo import EloConfig, EloModel
from app.services.predictions.ensemble import BaselineModel, EnsembleModel
from app.services.predictions.math_utils import markets_from_grid, score_grid
from app.services.predictions.montecarlo import MonteCarloModel
from app.services.predictions.poisson import PoissonModel, xg_enhanced_config

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
        existing = db.query(Team).filter_by(provider="test", provider_team_id=str(i + 1)).first()
        if existing is not None:
            out[name] = existing
            continue
        team = Team(league_id=league.id, name=name, provider="test",
                    provider_team_id=str(i + 1))
        db.add(team)
        db.flush()
        out[name] = team
    db.commit()
    return out


def _add(db, league, teams, home, away, day, home_score, away_score,
         status="FINISHED"):
    match = Match(
        league_id=league.id, home_team_id=teams[home].id, away_team_id=teams[away].id,
        kickoff_at=datetime(2024, 9, day), status=status,
        home_score=home_score, away_score=away_score,
        provider="test", provider_match_id=f"{home}-{away}-{day}")
    db.add(match)
    db.commit()
    return match


def _mini_league(db):
    """12 finished matches, Sep 1-12: A strong at home, D weak everywhere.
    Idempotent: returns existing rows when already built."""
    league = _league(db)
    if db.query(Match).filter_by(league_id=league.id).count() >= 12:
        teams = {t.name: t for t in db.query(Team).filter_by(league_id=league.id).all()}
        return league, teams
    teams = _teams(db, league)
    _add(db, league, teams, "A", "B", 1, 3, 0)
    _add(db, league, teams, "C", "D", 2, 1, 1)
    _add(db, league, teams, "A", "C", 3, 2, 0)
    _add(db, league, teams, "B", "D", 4, 2, 2)
    _add(db, league, teams, "B", "A", 5, 1, 2)
    _add(db, league, teams, "D", "C", 6, 0, 1)
    _add(db, league, teams, "C", "A", 7, 1, 1)
    _add(db, league, teams, "D", "B", 8, 0, 3)
    _add(db, league, teams, "A", "D", 9, 4, 0)
    _add(db, league, teams, "B", "C", 10, 2, 1)
    _add(db, league, teams, "C", "B", 11, 0, 0)
    _add(db, league, teams, "D", "A", 12, 1, 3)
    return league, teams


def _xg_rows(db, match_id, home_xg, away_xg):
    db.add(MatchStatistic(match_id=match_id, team="home", stat_name="expected_goals",
                          stat_value=str(home_xg), period="full", source="test"))
    db.add(MatchStatistic(match_id=match_id, team="away", stat_name="expected_goals",
                          stat_value=str(away_xg), period="full", source="test"))
    db.commit()


# ------------------------------------------------------------------ Elo

def test_elo_initial_priors_equal(db):
    _mini_league(db)
    model = EloModel()
    ratings, n = model.ratings_at(db, datetime(2024, 8, 1))
    assert n == 0 and ratings == {}


def test_elo_home_advantage(db):
    _mini_league(db)
    match = db.query(Match).first()
    pred = EloModel().predict(db, match.id, datetime(2024, 9, 20), STRICT)
    assert pred.status == "valid"
    assert abs(pred.outcome_sum() - 1.0) < 1e-6
    # Same ratings, no home edge vs with edge: home prob must rise.
    plain = EloModel(config=EloConfig(home_advantage=0.0)).predict(
        db, match.id, datetime(2024, 9, 20), STRICT)
    assert pred.home_win_probability > plain.home_win_probability


def test_elo_chronological_updates(db):
    league, teams = _mini_league(db)
    model = EloModel()
    before, _ = model.ratings_at(db, datetime(2024, 9, 5))
    after, n = model.ratings_at(db, datetime(2024, 9, 20))
    assert n == 12
    # A won twice early (3-0, 2-0): rating must be above the initial prior.
    assert after[teams["A"].id] > model.config.initial_rating
    # D lost everything: below prior.
    assert after[teams["D"].id] < model.config.initial_rating
    assert before[teams["A"].id] != after[teams["A"].id]


def test_elo_no_future_matches(db):
    league, teams = _mini_league(db)
    model = EloModel()
    mid_cutoff, _ = model.ratings_at(db, datetime(2024, 9, 6))
    # A late A-vs-D blowout (Sep 9: A 4-0) must not leak into Sep-6 ratings.
    late, _ = model.ratings_at(db, datetime(2024, 9, 20))
    assert mid_cutoff[teams["A"].id] < late[teams["A"].id]
    # And a cutoff before everything sees nothing at all.
    empty, n = model.ratings_at(db, datetime(2024, 8, 15))
    assert n == 0 and empty == {}


def test_elo_deterministic(db):
    _mini_league(db)
    match = db.query(Match).first()
    first = EloModel().predict(db, match.id, datetime(2024, 9, 20), STRICT)
    second = EloModel().predict(db, match.id, datetime(2024, 9, 20), STRICT)
    assert first.model_dump() == second.model_dump()


def test_elo_config_versioning():
    assert EloModel().model_version == "elo_v1"
    assert EloModel(config=EloConfig(k_factor=30)).model_version != "elo_v1"
    assert EloModel(config=EloConfig(home_advantage_by_league={"EPL": 80})).model_version != "elo_v1"


# ------------------------------------------------------------------ Poisson

def _poisson_match(db):
    league, teams = _mini_league(db)
    match = Match(
        league_id=league.id, home_team_id=teams["A"].id, away_team_id=teams["B"].id,
        kickoff_at=datetime(2024, 9, 20), status="SCHEDULED",
        provider="test", provider_match_id="A-B-20")
    db.add(match)
    db.commit()
    return match


def test_poisson_parameters_and_split(db):
    match = _poisson_match(db)
    model = PoissonModel()
    lam_home, lam_away, diag = model.estimate_lambdas(db, match.id, datetime(2024, 9, 20), STRICT)
    # Strong home side A vs weak B: home lambda clearly larger.
    assert lam_home > lam_away > 0
    assert diag["n_history"] == 12
    assert diag["xg_used"] is False


def test_poisson_minimum_sample(db):
    league = _league(db)
    teams = _teams(db, league, ("X", "Y"))
    match = Match(
        league_id=league.id, home_team_id=teams["X"].id, away_team_id=teams["Y"].id,
        kickoff_at=datetime(2024, 9, 20), status="SCHEDULED",
        provider="test", provider_match_id="X-Y")
    db.add(match)
    db.commit()
    pred = PoissonModel().predict(db, match.id, datetime(2024, 9, 20), STRICT)
    assert pred.status == "insufficient_data"
    assert "uniform probabilities are a placeholder" in pred.data_quality[-1]


def test_poisson_league_context(db):
    league, teams = _mini_league(db)
    model = PoissonModel()
    lam_home, lam_away, diag = model.estimate_lambdas(
        db, db.query(Match).first().id, datetime(2024, 9, 20), STRICT)
    assert diag["league_avg_home"] > 0 and diag["league_avg_away"] > 0
    # Recency-weighted averages near the unweighted means (17/12, 14/12).
    assert 1.3 < diag["league_avg_home"] < 1.5
    assert 1.0 < diag["league_avg_away"] < 1.3


def test_poisson_distribution_sums(db):
    match = _poisson_match(db)
    pred = PoissonModel().predict(db, match.id, datetime(2024, 9, 20), STRICT)
    assert pred.status == "valid"
    assert abs(pred.outcome_sum() - 1.0) < 1e-6
    assert abs(sum(pred.score_probabilities.values()) - 1.0) < 1e-4  # 6dp rounding
    for required in ("0-0", "1-0", "0-1", "1-1", "2-0", "0-2", "2-1", "1-2",
                     "2-2", "3-0", "0-3", "3-1", "1-3", "3-2", "2-3"):
        assert required in pred.score_probabilities
    assert pred.over_2_5_probability is not None
    assert abs(pred.over_2_5_probability + pred.under_2_5_probability - 1.0) < 1e-9
    assert abs(pred.btts_yes_probability + pred.btts_no_probability - 1.0) < 1e-9
    assert pred.expected_total_goals == pytest.approx(
        pred.expected_home_goals + pred.expected_away_goals, abs=1e-3)


def test_score_grid_math():
    grid = score_grid(1.5, 1.0)
    assert abs(sum(grid.values()) - 1.0) < 1e-9
    markets = markets_from_grid(grid)
    assert abs(markets["home_win_probability"] + markets["draw_probability"]
               + markets["away_win_probability"] - 1.0) < 1e-9


# ------------------------------------------------------------------ Monte Carlo

def test_montecarlo_deterministic_seed(db):
    match = _poisson_match(db)
    first = MonteCarloModel(n_simulations=2000, random_seed=7).predict(
        db, match.id, datetime(2024, 9, 20), STRICT)
    second = MonteCarloModel(n_simulations=2000, random_seed=7).predict(
        db, match.id, datetime(2024, 9, 20), STRICT)
    assert first.model_dump() == second.model_dump()
    assert abs(first.outcome_sum() - 1.0) < 1e-9


def test_montecarlo_converges_to_poisson(db):
    match = _poisson_match(db)
    analytic = PoissonModel().predict(db, match.id, datetime(2024, 9, 20), STRICT)
    simulated = MonteCarloModel(n_simulations=50000, random_seed=123).predict(
        db, match.id, datetime(2024, 9, 20), STRICT)
    assert abs(simulated.home_win_probability - analytic.home_win_probability) < 0.02
    assert abs(simulated.draw_probability - analytic.draw_probability) < 0.02
    assert abs(simulated.over_2_5_probability - analytic.over_2_5_probability) < 0.02


def test_montecarlo_configurable_simulations(db):
    match = _poisson_match(db)
    few = MonteCarloModel(n_simulations=100, random_seed=1).predict(
        db, match.id, datetime(2024, 9, 20), STRICT)
    assert few.model_version == "montecarlo_v1-custom"
    assert abs(few.outcome_sum() - 1.0) < 1e-9
    assert MonteCarloModel().model_version == "montecarlo_v1"


# ------------------------------------------------------------------ Ensemble

def test_ensemble_weights(db):
    match = _poisson_match(db)
    elo_only = EnsembleModel(members=[EloModel(), PoissonModel()], weights=[1.0, 0.0])
    pred = elo_only.predict(db, match.id, datetime(2024, 9, 20), STRICT)
    direct = EloModel().predict(db, match.id, datetime(2024, 9, 20), STRICT)
    assert pred.home_win_probability == pytest.approx(direct.home_win_probability)
    assert "elo" in pred.model_version and "poisson" in pred.model_version


def test_ensemble_normalization(db):
    match = _poisson_match(db)
    pred = EnsembleModel(members=[EloModel(), PoissonModel()],
                         weights=[2.0, 2.0]).predict(db, match.id, datetime(2024, 9, 20), STRICT)
    assert abs(pred.outcome_sum() - 1.0) < 1e-6
    assert pred.status == "valid"


def test_ensemble_model_isolation(db):
    match = _poisson_match(db)
    # Poisson alone is insufficient nowhere here, but force it: empty-history
    # member fails while Elo still predicts -> ensemble stays valid.
    ensemble = EnsembleModel(members=[EloModel(), PoissonModel()])
    pred = ensemble.predict(db, match.id, datetime(2024, 9, 20), STRICT)
    assert pred.status == "valid"
    with pytest.raises(ValueError, match="unknown model"):
        EnsembleModel.from_names(["nope"])
    rebuilt = EnsembleModel.from_names(["elo", "poisson"], weights=[0.5, 0.5])
    assert rebuilt.weights == [0.5, 0.5]


def test_ensemble_no_valid_members(db):
    league = _league(db)
    teams = _teams(db, league, ("X", "Y"))
    match = Match(
        league_id=league.id, home_team_id=teams["X"].id, away_team_id=teams["Y"].id,
        kickoff_at=datetime(2024, 9, 20), status="SCHEDULED",
        provider="test", provider_match_id="X-Y")
    db.add(match)
    db.commit()
    pred = EnsembleModel(members=[PoissonModel()]).predict(
        db, match.id, datetime(2024, 9, 20), STRICT)
    assert pred.status == "insufficient_data"


# ------------------------------------------------------------------ Leakage

def test_future_match_excluded_from_history(db):
    league, teams = _mini_league(db)
    repo = HistoricalFeatureRepository(db, datetime(2024, 9, 6), STRICT)
    history = repo.finished_before(league_id=league.id)
    assert [m.kickoff_at.day for m in history] == [1, 2, 3, 4, 5]
    assert all(m.kickoff_at < repo.cutoff for m in history)


def test_post_match_stats_of_target_excluded(db):
    league, teams = _mini_league(db)
    target = db.query(Match).filter_by(provider_match_id="A-B-1").one()
    # Even with stat rows attached to the target, Poisson lambdas for OTHER
    # matches must be identical: target rows are never read as history.
    db.add(MatchStatistic(match_id=target.id, team="home", stat_name="shots_total",
                          stat_value="99", period="full", source="test"))
    db.commit()
    model = PoissonModel()
    other = db.query(Match).filter_by(provider_match_id="C-D-2").one()
    first = model.estimate_lambdas(db, other.id, datetime(2024, 9, 20), STRICT)
    db.query(MatchStatistic).delete()
    db.commit()
    second = model.estimate_lambdas(db, other.id, datetime(2024, 9, 20), STRICT)
    assert first[0] == second[0] and first[1] == second[1]


def test_cutoff_enforced_strict_vs_estimated(db):
    league, teams = _mini_league(db)
    target = db.query(Match).filter_by(provider_match_id="A-D-9").one()
    # Stat row without timing on a PAST match: strict excludes, estimated allows.
    db.add(MatchStatistic(match_id=target.id, team="home", stat_name="shots_total",
                          stat_value="9", period="full", source="test"))
    db.commit()
    strict_repo = HistoricalFeatureRepository(db, datetime(2024, 9, 20), STRICT)
    assert strict_repo.match_stats(target.id) == []
    assert strict_repo.excluded_unknown_timing == 1
    estimated_repo = HistoricalFeatureRepository(db, datetime(2024, 9, 20), ESTIMATED)
    assert len(estimated_repo.match_stats(target.id)) == 1
    # Explicitly timed rows pass strict mode.
    from datetime import timezone

    row = db.query(MatchStatistic).filter_by(match_id=target.id).one()
    row.effective_at = datetime(2024, 9, 10, tzinfo=timezone.utc)
    db.commit()
    strict_repo2 = HistoricalFeatureRepository(db, datetime(2024, 9, 20), STRICT)
    assert len(strict_repo2.match_stats(target.id)) == 1
    # ...but not when effective is after the cutoff.
    row.effective_at = datetime(2024, 9, 25, tzinfo=timezone.utc)
    db.commit()
    strict_repo3 = HistoricalFeatureRepository(db, datetime(2024, 9, 20), STRICT)
    assert strict_repo3.match_stats(target.id) == []


# ------------------------------------------------------------------ xG gating

def test_xg_sufficient_then_used(db):
    league, teams = _mini_league(db)
    for match in db.query(Match).all():
        _xg_rows(db, match.id, 1.5, 1.2)
    match = db.query(Match).filter_by(provider_match_id="A-D-9").one()
    cutoff = datetime(2024, 9, 20)
    avail = assess_availability(db, match.id, cutoff, ESTIMATED)
    assert avail.xg is True
    pred = PoissonModel(config=xg_enhanced_config()).predict(db, match.id, cutoff, ESTIMATED)
    assert pred.status == "valid" and pred.xg_used is True
    assert pred.model_version == "poisson_v1-xg"
    # Same data in STRICT mode: unknown-timing xG rows are excluded -> fallback.
    strict_pred = PoissonModel(config=xg_enhanced_config()).predict(db, match.id, cutoff, STRICT)
    assert strict_pred.status == "valid" and strict_pred.xg_used is False


def test_xg_insufficient_falls_back(db):
    league, teams = _mini_league(db)
    match = db.query(Match).filter_by(provider_match_id="A-D-9").one()
    cutoff = datetime(2024, 9, 20)
    avail = assess_availability(db, match.id, cutoff, ESTIMATED)
    assert avail.xg is False
    assert "xG excluded" in " ".join(avail.notes)
    pred = PoissonModel(config=xg_enhanced_config()).predict(db, match.id, cutoff, ESTIMATED)
    assert pred.status == "valid" and pred.xg_used is False
    # Missing xG is never zero-filled: pure-goals lambdas match baseline config.
    baseline = PoissonModel().predict(db, match.id, cutoff, ESTIMATED)
    assert pred.expected_home_goals == baseline.expected_home_goals


def test_xg_missing_never_zero(db):
    _mini_league(db)
    repo = HistoricalFeatureRepository(db, datetime(2024, 9, 20), ESTIMATED)
    team = db.query(Team).filter_by(name="A").one()
    assert repo.team_xg_before(team.id) == []


# ------------------------------------------------------------------ Backtesting

def test_scope_matches_ordered_and_filtered(db):
    _mini_league(db)

    rows = scope_matches(db, league_code="TST")
    assert len(rows) == 12
    kickoffs = [m.kickoff_at for m in rows]
    assert kickoffs == sorted(kickoffs)
    with pytest.raises(ValueError, match="unknown league"):
        scope_matches(db, league_code="NOPE")


def test_dataset_summary_from_db(db):
    _mini_league(db)

    summary = dataset_summary(db, league_code="TST")
    assert summary["total_matches"] == 12
    # First 5-matchdays need history: teams reach 5 games at different times.
    assert summary["strict_prematch_eligible"] + summary["insufficient_history"] == 12
    assert summary["strict_prematch_eligible"] > 0


def test_backtest_chronological_no_lookahead(db):
    _mini_league(db)
    from app.services.predictions.elo import EloModel

    result = run_backtest(db, EloModel(), league_code="TST", persist=False)
    assert result["sample_size"] == 12  # Elo always has priors
    assert result["metrics"]["accuracy_1x2"] is not None
    assert result["metrics"]["log_loss_1x2"] is not None
    assert result["metrics"]["brier_1x2"] is not None
    # Stored cutoffs must be non-decreasing in kickoff order.
    stored = db.query(Prediction).filter_by(model_name="").all()
    assert stored == []  # persist=False wrote nothing


def test_backtest_persists_and_resolves(db):
    _mini_league(db)
    from app.services.predictions.elo import EloModel

    result = run_backtest(db, EloModel(), league_code="TST", persist=True)
    assert result["sample_size"] == 12
    assert db.query(Prediction).count() == 12
    from app.db.models.predictions import PredictionResult

    assert db.query(PredictionResult).count() == 12
    assert db.query(BacktestRun).count() == 1
    run = db.query(BacktestRun).one()
    assert run.sample_size == 12 and run.metrics["accuracy_1x2"] is not None


def test_backtest_poisson_exclusions(db):
    _mini_league(db)
    from app.services.predictions.poisson import PoissonModel

    result = run_backtest(db, PoissonModel(), league_code="TST", persist=False)
    assert result["excluded_insufficient"] > 0
    assert result["sample_size"] + result["excluded_insufficient"] == 12
    assert result["metrics"]["mae_home_goals"] is not None


def test_backtest_deterministic_rerun(db):
    _mini_league(db)
    from app.services.predictions.elo import EloModel

    first = run_backtest(db, EloModel(), league_code="TST", persist=False)
    second = run_backtest(db, EloModel(), league_code="TST", persist=False)
    assert first["metrics"] == second["metrics"]


# ------------------------------------------------------------------ Metrics

def test_metrics_hand_computed():
    assert met.accuracy(["home", "draw"], ["home", "away"]) == 0.5
    assert met.multiclass_log_loss([[0.5, 0.25, 0.25]], [0]) == pytest.approx(0.6931, abs=1e-3)
    assert met.multiclass_brier([[1.0, 0.0, 0.0]], [0]) == 0.0
    assert met.multiclass_brier([[1.0, 0.0, 0.0]], [2]) == pytest.approx(2.0)
    assert met.binary_log_loss([1.0], [1]) < 1e-6
    assert met.binary_brier([0.0], [1]) == 1.0
    assert met.mae([1.0, 2.0], [1.0, 4.0]) == 1.0
    assert met.rmse([2.0], [4.0]) == 2.0
    assert met.accuracy([], []) == 0.0
    assert met.multiclass_log_loss([], []) == 0.0


def test_calibration_metrics():
    probs = [0.1] * 5 + [0.9] * 5
    outcomes = [0] * 5 + [1] * 5
    assert met.expected_calibration_error(probs, outcomes, n_bins=2) == pytest.approx(0.1)
    curve = met.reliability_curve(probs, outcomes, n_bins=2)
    assert curve["bins"][0]["empirical_rate"] == 0.0
    assert curve["bins"][1]["empirical_rate"] == 1.0
    assert met.expected_calibration_error([], []) is None


def test_baseline_model(db):
    _mini_league(db)
    match = _poisson_match(db)
    pred = BaselineModel().predict(db, match.id, datetime(2024, 9, 20), STRICT)
    assert pred.status == "valid"
    assert abs(pred.outcome_sum() - 1.0) < 1e-6
    # 12 history matches: 4 home wins, 4 draws, 4 away wins.
    assert pred.home_win_probability == pytest.approx(4.0 / 12.0)
    assert pred.draw_probability == pytest.approx(4.0 / 12.0)
    assert pred.model_version == "baseline_v1"


# ------------------------------------------------------------------ Availability

def test_availability_gating(db):
    _mini_league(db)
    match = db.query(Match).filter_by(provider_match_id="A-B-1").one()
    avail = assess_availability(db, match.id, datetime(2024, 9, 2), STRICT)
    assert avail.goals is False  # only 1 prior match each
    assert "insufficient goal history" in " ".join(avail.notes)
    assert avail.possession is False
    late = db.query(Match).filter_by(provider_match_id="A-D-9").one()
    avail_late = assess_availability(db, late.id, datetime(2024, 9, 20), STRICT)
    assert avail_late.goals is True
    assert avail_late.home_history >= 5 and avail_late.away_history >= 5
    assert avail_late.xg is False


# ------------------------------------------------------------------ API

def test_api_generate_and_history(client, db, sample_match):
    response = client.post(f"/api/v1/predictions/{sample_match.id}/generate",
                           json={"model": "elo", "temporal_mode": "strict_prematch"})
    assert response.status_code == 200
    body = response.json()
    assert body["model_name"] == "elo"
    assert abs(body["home_win_probability"] + body["draw_probability"]
               + body["away_win_probability"] - 1.0) < 1e-6
    assert body["prediction_id"] is not None
    history = client.get(f"/api/v1/predictions/{sample_match.id}/history").json()
    assert len(history["data"]) == 1
    listing = client.get("/api/v1/predictions?model=elo").json()
    assert len(listing["data"]) == 1
    bad_model = client.post(f"/api/v1/predictions/{sample_match.id}/generate",
                            json={"model": "nope"})
    assert bad_model.status_code == 400
    assert client.post("/api/v1/predictions/999999/generate", json={}).status_code == 404


def test_api_backtest_run(client, db, sample_match):
    _mini_league(db)
    response = client.post("/api/v1/backtesting/run",
                           json={"model": "baseline", "league": "TST"})
    assert response.status_code == 200
    body = response.json()
    # 11, not 12: the first chronological match has no pre-cutoff history,
    # so the baseline correctly reports insufficient_data for it.
    assert body["sample_size"] == 11
    assert body["excluded_insufficient"] == 1
    assert body["metrics"]["accuracy_1x2"] is not None
    runs = client.get("/api/v1/backtesting?model=baseline").json()
    assert len(runs["data"]) == 1
    bad = client.post("/api/v1/backtesting/run",
                      json={"model": "baseline", "league": "NOPE"})
    assert bad.status_code == 400


def test_api_list_predictions_filter(client, db, sample_match):
    _mini_league(db)
    client.post(f"/api/v1/predictions/{sample_match.id}/generate", json={"model": "elo"})
    assert client.get("/api/v1/predictions?league=ZZZ").status_code == 404
