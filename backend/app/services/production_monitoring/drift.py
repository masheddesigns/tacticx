"""Phase 28 drift analysis with documented STABLE/WATCH/INSUFFICIENT_DATA.

Rules (observational, documented here and in docs):
- INSUFFICIENT_DATA when the recent window has fewer than MIN_DRIFT_SAMPLE
  evaluations.
- WATCH when any watch band is exceeded with sufficient samples:
  |Δbrier| > 0.05, |Δaccuracy| > 0.10, |Δlogloss| > 0.20.
- STABLE otherwise.
No model verdict is ever emitted; WATCH means "measured movement worth a
look", not degradation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.services.prediction_evaluation.drift import drift_report as _base_drift

from .contracts import (
    MIN_DRIFT_SAMPLE,
    MONITORING_CONTRACT_VERSION,
    STATE_INSUFFICIENT_DATA,
    STATE_STABLE,
    STATE_WATCH,
    WATCH_ACCURACY_DELTA,
    WATCH_BRIER_DELTA,
    WATCH_LOGLOSS_DELTA,
)


def _relative(current: Optional[float],
              baseline: Optional[float]) -> Optional[float]:
    if current is None or baseline is None:
        return None
    if baseline == 0:
        return None
    return round((current - baseline) / abs(baseline), 4)


def drift_analysis(
    db: Session,
    *,
    recent_n: int = 50,
    model_id: Optional[str] = None,
    model_version: Optional[str] = None,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Recent-window vs baseline with state + relative differences."""
    base = _base_drift(
        db, recent_n=recent_n, model_id=model_id,
        model_version=model_version, competition=competition,
        season=season, prediction_mode=prediction_mode)
    diffs = base.get("differences_recent_minus_baseline", {})

    if base.get("recent_sample", 0) < MIN_DRIFT_SAMPLE:
        state = STATE_INSUFFICIENT_DATA
    elif (abs(diffs.get("brier_1x2") or 0.0) > WATCH_BRIER_DELTA
          or abs(diffs.get("accuracy_1x2") or 0.0) > WATCH_ACCURACY_DELTA
          or abs(diffs.get("log_loss_1x2") or 0.0) > WATCH_LOGLOSS_DELTA):
        state = STATE_WATCH
    else:
        state = STATE_STABLE

    relative = {k: _relative(base["recent_means"].get(k),
                             base["baseline_means"].get(k))
                for k in diffs}
    base.update({
        "contract": MONITORING_CONTRACT_VERSION,
        "state": state,
        "state_rules": {
            "INSUFFICIENT_DATA": f"recent_sample < {MIN_DRIFT_SAMPLE}",
            "WATCH": f"|Δbrier| > {WATCH_BRIER_DELTA} or "
                     f"|Δaccuracy| > {WATCH_ACCURACY_DELTA} or "
                     f"|Δlogloss| > {WATCH_LOGLOSS_DELTA} "
                     "(measured movement, not a degradation verdict)",
            "STABLE": "otherwise",
        },
        "relative_differences": relative,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })
    return base
