"""Chronological backtest runner (Phase 2).

Walk-forward evaluation only — never a random split:

    TRAIN: every finished match with kickoff < cutoff
    TEST:  the next match(es), then move the cutoff forward

For each in-scope finished match, in kickoff order: set cutoff = kickoff,
check sufficiency, predict, persist the prediction (point-in-time record),
resolve against the actual result, and accumulate metrics. Exclusions
(insufficient history, temporal risk) are counted and reported, never hidden.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.db.models.enums import MatchStatus
from app.db.models.predictions import BacktestRun
from app.services.backtesting import metrics as met
from app.services.backtesting.service import resolve_predictions, store_full_prediction
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.predictions.outputs import FullPrediction

INDEX = {"home": 0, "draw": 1, "away": 2}


def actual_outcome(match: Match) -> Optional[str]:
    if match.home_score is None or match.away_score is None:
        return None
    if match.home_score > match.away_score:
        return "home"
    if match.home_score < match.away_score:
        return "away"
    return "draw"


def scope_matches(db: Session, league_code: Optional[str] = None,
                  season: Optional[str] = None,
                  date_from: Optional[datetime] = None,
                  date_to: Optional[datetime] = None) -> List[Match]:
    """In-scope finished, scored matches ordered by kickoff (then id)."""
    q = db.query(Match).filter(
        Match.status == MatchStatus.FINISHED.value,
        Match.home_score.is_not(None),
        Match.away_score.is_not(None),
        Match.kickoff_at.is_not(None),
        Match.home_team_id.is_not(None),
        Match.away_team_id.is_not(None),
    )
    if league_code:
        league = db.query(League).filter_by(code=league_code).first()
        if league is None:
            raise ValueError(f"unknown league: {league_code}")
        q = q.filter(Match.league_id == league.id)
    if date_from is not None:
        q = q.filter(Match.kickoff_at >= as_naive_utc(date_from))
    if date_to is not None:
        q = q.filter(Match.kickoff_at <= as_naive_utc(date_to))
    rows = q.order_by(Match.kickoff_at.asc(), Match.id.asc()).all()
    if season:
        rows = [m for m in rows if _season_label(m.kickoff_at) == season]
    return rows


def _season_label(kickoff) -> str:
    naive = as_naive_utc(kickoff)
    if naive is None:
        return "unknown"
    return str(naive.year if naive.month >= 8 else naive.year - 1)


def dataset_summary(db: Session, league_code: Optional[str] = None,
                    season: Optional[str] = None,
                    date_from: Optional[datetime] = None,
                    date_to: Optional[datetime] = None,
                    minimum_team_matches: int = 5) -> Dict:
    """Dataset counts straight from the database — never fabricated."""
    matches = scope_matches(db, league_code, season, date_from, date_to)
    from app.services.features.repository import HistoricalFeatureRepository

    strict_eligible = 0
    insufficient = 0
    for match in matches:
        cutoff = as_naive_utc(match.kickoff_at)
        repo = HistoricalFeatureRepository(db, cutoff, TemporalMode.STRICT_PREMATCH)
        home_n = len(repo.team_matches_before(match.home_team_id))
        away_n = len(repo.team_matches_before(match.away_team_id))
        if home_n >= minimum_team_matches and away_n >= minimum_team_matches:
            strict_eligible += 1
        else:
            insufficient += 1
    return {
        "total_matches": len(matches),
        "strict_prematch_eligible": strict_eligible,
        "insufficient_history": insufficient,
        "excluded_temporal": 0,
        "date_range": [str(as_naive_utc(date_from)), str(as_naive_utc(date_to))],
    }


def run_backtest(db: Session, model, league_code: Optional[str] = None,
                 season: Optional[str] = None,
                 date_from: Optional[datetime] = None,
                 date_to: Optional[datetime] = None,
                 mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                 persist: bool = True, seed: Optional[int] = None,
                 return_details: bool = False) -> Dict:
    """Execute a walk-forward backtest for one model. Returns metrics + counts.
    With return_details=True, per-match (match_id, probs, actual) rows are
    included for CIs and calibration analysis (not persisted)."""
    matches = scope_matches(db, league_code, season, date_from, date_to)
    model_name = getattr(model, "model_name", "?")
    model_version = getattr(model, "model_version", "?")
    config = _model_config(model)

    outcome_probs: List[List[float]] = []
    outcome_actual: List[int] = []
    outcome_predicted: List[int] = []
    over25_probs: List[float] = []
    over25_actual: List[int] = []
    btts_probs: List[float] = []
    btts_actual: List[int] = []
    exp_home: List[float] = []
    exp_away: List[float] = []
    act_home: List[float] = []
    act_away: List[float] = []
    home_win_probs: List[float] = []
    home_win_actual: List[int] = []
    detail_rows: List[Dict] = []
    sample = 0
    excluded_insufficient = 0
    excluded_temporal = 0

    for match in matches:
        cutoff = as_naive_utc(match.kickoff_at)
        try:
            if hasattr(model, "predict"):
                import inspect

                params = inspect.signature(model.predict).parameters
                if "seed" in params:
                    pred = model.predict(db, match.id, cutoff, mode, seed=seed)
                else:
                    pred = model.predict(db, match.id, cutoff, mode)
            else:
                continue
        except Exception:
            excluded_temporal += 1
            continue
        if not isinstance(pred, FullPrediction):
            excluded_temporal += 1
            continue
        if pred.status == "temporal_risk":
            excluded_temporal += 1
            continue
        if pred.status != "valid":
            excluded_insufficient += 1
            continue
        actual = actual_outcome(match)
        if actual is None:
            continue
        if persist:
            stored = store_full_prediction(db, match.id, pred, model_config=config)
            resolve_predictions(db, stored.match_id)
        sample += 1
        outcome_probs.append([pred.home_win_probability, pred.draw_probability,
                              pred.away_win_probability])
        outcome_actual.append(INDEX[actual])
        outcome_predicted.append(met.argmax_labels([outcome_probs[-1]])[0])
        total_goals = (match.home_score or 0) + (match.away_score or 0)
        if pred.over_2_5_probability is not None:
            over25_probs.append(pred.over_2_5_probability)
            over25_actual.append(1 if total_goals > 2.5 else 0)
        if pred.btts_yes_probability is not None:
            btts_probs.append(pred.btts_yes_probability)
            btts_actual.append(1 if (match.home_score or 0) > 0 and (match.away_score or 0) > 0 else 0)
        if pred.expected_home_goals is not None and pred.expected_away_goals is not None:
            exp_home.append(pred.expected_home_goals)
            exp_away.append(pred.expected_away_goals)
            act_home.append(float(match.home_score or 0))
            act_away.append(float(match.away_score or 0))
        home_win_probs.append(pred.home_win_probability)
        home_win_actual.append(1 if actual == "home" else 0)
        if return_details:
            detail_rows.append({"match_id": match.id,
                                "probs": [pred.home_win_probability, pred.draw_probability,
                                          pred.away_win_probability],
                                "actual": INDEX[actual]})

    result = {
        "model": model_name,
        "model_version": model_version,
        "temporal_mode": mode.value,
        "sample_size": sample,
        "excluded_insufficient": excluded_insufficient,
        "excluded_temporal": excluded_temporal,
        "metrics": _compute_metrics(
            outcome_probs, outcome_actual, outcome_predicted,
            over25_probs, over25_actual, btts_probs, btts_actual,
            exp_home, exp_away, act_home, act_away,
            home_win_probs, home_win_actual),
    }
    if return_details:
        result["details"] = detail_rows
    if persist:
        db.add(BacktestRun(
            model_name=model_name, model_version=model_version,
            league=league_code or "", season=season or "",
            temporal_mode=mode.value,
            date_from=as_naive_utc(date_from), date_to=as_naive_utc(date_to),
            sample_size=sample, excluded_insufficient=excluded_insufficient,
            excluded_temporal=excluded_temporal,
            metrics=result["metrics"], model_config=config))
        db.commit()
    return result


def _model_config(model) -> Optional[Dict]:
    for attr in ("config_dict",):
        if hasattr(model, attr):
            try:
                return getattr(model, attr)()
            except Exception:
                pass
    config = getattr(model, "config", None)
    if config is not None and hasattr(config, "as_dict"):
        try:
            return config.as_dict()
        except Exception:
            pass
    return None


def _compute_metrics(outcome_probs, outcome_actual, outcome_predicted,
                     over25_probs, over25_actual, btts_probs, btts_actual,
                     exp_home, exp_away, act_home, act_away,
                     home_win_probs, home_win_actual) -> Dict:
    metrics: Dict = {}
    metrics["accuracy_1x2"] = round(met.accuracy(outcome_predicted, outcome_actual), 4) \
        if outcome_actual else None
    metrics["log_loss_1x2"] = round(met.multiclass_log_loss(outcome_probs, outcome_actual), 4) \
        if outcome_actual else None
    metrics["brier_1x2"] = round(met.multiclass_brier(outcome_probs, outcome_actual), 4) \
        if outcome_actual else None
    metrics["ece_home_win"] = met.expected_calibration_error(home_win_probs, home_win_actual) \
        if home_win_actual else None
    metrics["reliability_home_win"] = met.reliability_curve(home_win_probs, home_win_actual) \
        if home_win_actual else None
    if over25_actual:
        over_pred = ["over" if p >= 0.5 else "under" for p in over25_probs]
        over_act = ["over" if a else "under" for a in over25_actual]
        metrics["accuracy_over25"] = round(met.accuracy(over_pred, over_act), 4)
        metrics["log_loss_over25"] = round(met.binary_log_loss(over25_probs, over25_actual), 4)
        metrics["brier_over25"] = round(met.binary_brier(over25_probs, over25_actual), 4)
    else:
        metrics["accuracy_over25"] = metrics["log_loss_over25"] = metrics["brier_over25"] = None
    if btts_actual:
        btts_pred = ["yes" if p >= 0.5 else "no" for p in btts_probs]
        btts_act = ["yes" if a else "no" for a in btts_actual]
        metrics["accuracy_btts"] = round(met.accuracy(btts_pred, btts_act), 4)
        metrics["log_loss_btts"] = round(met.binary_log_loss(btts_probs, btts_actual), 4)
        metrics["brier_btts"] = round(met.binary_brier(btts_probs, btts_actual), 4)
    else:
        metrics["accuracy_btts"] = metrics["log_loss_btts"] = metrics["brier_btts"] = None
    if act_home:
        metrics["mae_home_goals"] = round(met.mae(exp_home, act_home), 4)
        metrics["rmse_home_goals"] = round(met.rmse(exp_home, act_home), 4)
        metrics["mae_away_goals"] = round(met.mae(exp_away, act_away), 4)
        metrics["rmse_away_goals"] = round(met.rmse(exp_away, act_away), 4)
    else:
        metrics["mae_home_goals"] = metrics["rmse_home_goals"] = None
        metrics["mae_away_goals"] = metrics["rmse_away_goals"] = None
    return metrics
