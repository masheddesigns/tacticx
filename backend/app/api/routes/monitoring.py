"""Production monitoring API routes (Phase 28, strictly read-only).

No endpoint here creates or modifies predictions, evaluations, outcomes,
model configuration, or provider activation.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.services.production_monitoring import (
    breakdown,
    calibration_detail,
    coverage_funnel,
    data_quality_report,
    detect_anomalies,
    drift_analysis,
    performance_overview,
    provider_report,
    temporal_windows,
)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _parse_dt(value: Optional[str], name: str) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"{name} must be ISO-8601")


def _scope(model_id: Optional[str] = None,
           model_version: Optional[str] = None,
           competition: Optional[str] = None,
           season: Optional[str] = None,
           prediction_mode: Optional[str] = None) -> dict:
    return {"model_id": model_id, "model_version": model_version,
            "competition": competition, "season": season,
            "prediction_mode": prediction_mode}


@router.get("/overview")
def monitoring_overview(
    model_id: Optional[str] = Query(None),
    model_version: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    perf = performance_overview(
        db, model_id=model_id, model_version=model_version,
        competition=competition, season=season)
    cov = coverage_funnel(db, competition=competition, season=season,
                          model_id=model_id, model_version=model_version)
    drift = drift_analysis(
        db, model_id=model_id, model_version=model_version,
        competition=competition, season=season)
    quality = data_quality_report(db)
    metrics = perf.get("metrics", {})
    return {
        "evaluation_count": metrics.get("sample_count", 0),
        "eligible_count": cov["eligible_count"],
        "ready_count": cov["ready_count"],
        "prediction_count": cov["predicted_count"],
        "prediction_coverage_rate": cov["prediction_coverage_rate"],
        "evaluation_coverage_rate": cov["evaluation_coverage_rate"],
        "accuracy": metrics.get("accuracy_1x2"),
        "log_loss": metrics.get("log_loss_1x2"),
        "brier_score": metrics.get("brier_1x2"),
        "goal_mae": metrics.get("goal_mae"),
        "calibration_state": "INSUFFICIENT_DATA"
        if metrics.get("sample_count", 0) < 20 else "AVAILABLE",
        "drift_state": drift.get("state"),
        "data_quality_state": quality.get("state"),
        "evaluation_period": perf.get("evaluation_period"),
    }


@router.get("/performance")
def monitoring_performance(
    model_id: Optional[str] = Query(None),
    model_version: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    prediction_mode: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    window: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    date_from = _parse_dt(start_date, "start_date")
    date_to = _parse_dt(end_date, "end_date")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=422, detail="start_date must not exceed end_date")
    windows = [20, 50, 100]
    if window is not None:
        try:
            windows = [int(window)]
        except ValueError:
            raise HTTPException(
                status_code=422, detail="window must be an integer")
    result = temporal_windows(
        db, windows=windows, model_id=model_id,
        model_version=model_version, competition=competition,
        season=season, prediction_mode=prediction_mode,
        date_from=date_from, date_to=date_to)
    result["breakdown"] = breakdown(
        db, by="competition_season", model_id=model_id,
        model_version=model_version)
    return result


@router.get("/calibration")
def monitoring_calibration(
    model_id: Optional[str] = Query(None),
    model_version: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    n_bins: int = Query(10, ge=2, le=50),
    db: Session = Depends(get_db),
):
    return calibration_detail(
        db, model_id=model_id, model_version=model_version,
        competition=competition, season=season, n_bins=n_bins)


@router.get("/drift")
def monitoring_drift(
    model_id: Optional[str] = Query(None),
    model_version: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    prediction_mode: Optional[str] = Query(None),
    window: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return drift_analysis(
        db, recent_n=window, model_id=model_id,
        model_version=model_version, competition=competition,
        season=season, prediction_mode=prediction_mode)


@router.get("/data-quality")
def monitoring_data_quality(db: Session = Depends(get_db)):
    return data_quality_report(db)


@router.get("/coverage")
def monitoring_coverage(
    model_id: Optional[str] = Query(None),
    model_version: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    date_from = _parse_dt(start_date, "start_date")
    date_to = _parse_dt(end_date, "end_date")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=422, detail="start_date must not exceed end_date")
    return coverage_funnel(
        db, competition=competition, season=season,
        date_from=date_from, date_to=date_to,
        model_id=model_id, model_version=model_version)


@router.get("/providers")
def monitoring_providers(
    provider: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return provider_report(
        db, provider=provider, competition=competition, season=season)


@router.get("/anomalies")
def monitoring_anomalies(
    severity: Optional[str] = Query(None),
    anomaly_type: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    result = detect_anomalies(
        db, scope={"provider": provider, "competition": competition,
                   "season": season})
    items = result["anomalies"]
    if severity:
        items = [a for a in items if a["severity"] == severity]
    if anomaly_type:
        items = [a for a in items if a["anomaly_type"] == anomaly_type]
    result["anomalies"] = items
    result["anomaly_count"] = len(items)
    result["filters"] = {"severity": severity, "anomaly_type": anomaly_type,
                         "provider": provider, "competition": competition,
                         "season": season}
    return result
