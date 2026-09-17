"""Monitoring: rolling metrics, drift alerts, data drift (Phase 7).

All outputs are descriptive diagnostics. Monitoring NEVER switches models,
retrains, or changes configuration — it reports `performance_status` and
`drift_status` for operators. Thresholds come from configuration and are
documented in the output.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.lifecycle import PredictionEvaluation

STATUS_NORMAL, STATUS_WATCH, STATUS_DEGRADED = "normal", "watch", "degraded"


def rolling_metrics(db: Session, windows: Optional[List[int]] = None,
                    league_id: Optional[int] = None,
                    model_version: Optional[str] = None) -> Dict:
    """Aggregate evaluation metrics over trailing windows (by evaluation id).

    Windows come from config (default 50/100). Windows larger than the
    available sample report `insufficient_sample` instead of a number.
    """
    from app.db.models.predictions import Prediction

    settings = get_settings()
    windows = windows or [int(w) for w in settings.MONITOR_ROLLING_WINDOWS.split(",")
                          if w.strip().isdigit()]
    query = db.query(PredictionEvaluation).order_by(PredictionEvaluation.id.desc())
    if league_id is not None:
        from app.db.models.core import Match

        query = query.join(Match, Match.id == PredictionEvaluation.match_id).filter(
            Match.league_id == league_id)
    if model_version is not None:
        query = query.join(Prediction,
                           Prediction.id == PredictionEvaluation.prediction_id).filter(
            Prediction.model_version == model_version)
    rows = query.limit(max(windows) if windows else 0).all()
    out = {"windows": {}, "total_available": len(rows)}
    for window in windows:
        if len(rows) < window:
            out["windows"][str(window)] = {"status": "insufficient_sample",
                                           "n": len(rows)}
            continue
        sample = rows[:window]
        out["windows"][str(window)] = {"status": "ok", "n": window,
                                       "metrics": _aggregate(sample)}
    return out


def _aggregate(rows: List[PredictionEvaluation]) -> Dict:
    keys = ("log_loss", "brier", "accuracy", "goal_mae", "goal_rmse")
    out: Dict = {}
    for key in keys:
        values = [(r.metrics or {}).get(key) for r in rows]
        values = [v for v in values if isinstance(v, (int, float))]
        if values:
            out[key] = round(sum(values) / len(values), 6)
            out[f"{key}_n"] = len(values)
        else:
            out[key] = None
            out[f"{key}_n"] = 0
    return out


def drift_status(db: Session, reference_brier: float,
                 window: int = 100) -> Dict:
    """Compare trailing-window Brier against a reference (e.g. Phase 5
    validation range). Bands are configurable; the result is a label plus
    the measured delta — never an action."""
    settings = get_settings()
    data = rolling_metrics(db, windows=[window])
    entry = data["windows"].get(str(window), {})
    if entry.get("status") != "ok" or entry["metrics"].get("brier") is None:
        return {"status": "insufficient_sample", "window": window,
                "n": entry.get("n", 0)}
    current = entry["metrics"]["brier"]
    delta = current - reference_brier
    if delta >= settings.DRIFT_DEGRADED_BRIER_DELTA:
        status = STATUS_DEGRADED
    elif delta >= settings.DRIFT_WATCH_BRIER_DELTA:
        status = STATUS_WATCH
    else:
        status = STATUS_NORMAL
    return {"performance_status": status, "window": window,
            "current_brier": current, "reference_brier": reference_brier,
            "delta": round(delta, 6),
            "bands": {"watch_at": settings.DRIFT_WATCH_BRIER_DELTA,
                      "degraded_at": settings.DRIFT_DEGRADED_BRIER_DELTA},
            "note": "Descriptive only: no model switch, no retraining."}


def data_drift(db: Session, league_id: Optional[int] = None,
               limit: int = 500) -> Dict:
    """Current outcome/score distributions vs the reference census.

    Distribution change is reported, never labeled model failure.
    """
    from app.db.models.core import Match
    from app.db.models.enums import MatchStatus

    query = db.query(Match).filter(Match.status == MatchStatus.FINISHED.value,
                                   Match.home_score.is_not(None),
                                   Match.away_score.is_not(None))
    if league_id is not None:
        query = query.filter(Match.league_id == league_id)
    rows = query.order_by(Match.kickoff_at.desc()).limit(limit).all()
    if len(rows) < 20:
        return {"status": "insufficient_sample", "n": len(rows)}
    home = sum(1 for m in rows if (m.home_score or 0) > (m.away_score or 0))
    draw = sum(1 for m in rows if m.home_score == m.away_score)
    total_goals = [(m.home_score or 0) + (m.away_score or 0) for m in rows]
    n = len(rows)
    return {
        "status": "ok", "n": n,
        "outcome_rates": {"home": round(home / n, 4), "draw": round(draw / n, 4),
                          "away": round((n - home - draw) / n, 4)},
        "mean_total_goals": round(sum(total_goals) / n, 4),
        "note": "Shift is diagnostic context, not model failure.",
    }
