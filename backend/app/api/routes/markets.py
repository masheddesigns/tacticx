"""Market intelligence endpoints (Phase 3).

Analytical transformations of observed bookmaker prices — not outcome
guarantees, not recommendations. No betting, staking, or execution exists
anywhere in these responses.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.config import get_settings
from app.db.models.core import Match
from app.db.models.odds import Bookmaker, OddsSelection
from app.db.models.predictions import Prediction
from app.services.backtesting.runner import actual_outcome
from app.services.market.compare import compare
from app.services.market.consensus import consensus, price_summary
from app.services.market.probabilities import (
    MARKET_PROBABILITY_V1,
    no_vig_probabilities,
)
from app.services.market.repository import closing_state, get_market_state, snapshots_before
from app.services.market.timeline import opening_status, timeline

router = APIRouter(tags=["markets"])

OUTCOMES = ("home", "draw", "away")


def _parse_cutoff(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "cutoff must be ISO format")


def _consensus_vectors(state: dict) -> Dict[str, Dict[str, float]]:
    vectors: Dict[str, Dict[str, float]] = {}
    for book in state.get("bookmakers", []):
        if book["completeness"] != "complete":
            continue
        prices = {sel: info["price"] for sel, info in book["selections"].items()}
        probs, _ = no_vig_probabilities(prices)
        if probs:
            vectors[book["bookmaker"] or f"book_{len(vectors)}"] = probs
    return vectors


def _series(db: Session, match_id: int, market: str) -> list:
    grouped: Dict[tuple, List[tuple]] = {}
    for snap in snapshots_before(db, match_id, datetime.max, market):
        for row in db.query(OddsSelection).filter_by(snapshot_id=snap.id).all():
            grouped.setdefault((snap.bookmaker_id, snap.market_type,
                                row.selection), []).append((snap.timestamp, row.odds))
    series = []
    for (bookmaker_id, market_type, selection), points in sorted(grouped.items()):
        bookmaker = db.get(Bookmaker, bookmaker_id) if bookmaker_id else None
        entry = timeline(points)
        entry.update({"bookmaker": bookmaker.name if bookmaker else "",
                      "market": market_type, "selection": selection,
                      "opening_status": opening_status(False, bool(points))})
        series.append(entry)
    return series


@router.get("/markets/{match_id}", summary="Current market state with consensus")
def market_state(match_id: int, db: Session = Depends(get_db),
                 market: str = "h2h", cutoff: Optional[str] = None,
                 model: Optional[str] = None):
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "match not found")
    cutoff_dt = _parse_cutoff(cutoff) or match.kickoff_at or datetime.now()
    state = get_market_state(db, match_id, cutoff_dt, market)
    response = dict(state)
    vectors = _consensus_vectors(state)
    response["consensus"] = consensus(vectors)
    # Best available prices among snapshots inside the configured window.
    window_minutes = get_settings().ODDS_CONSENSUS_TIME_WINDOW_MINUTES
    stamps = [b["timestamp"] for b in state.get("bookmakers", []) if b["timestamp"]]
    per_selection: Dict[str, List[float]] = {}
    if stamps:
        try:
            ref = datetime.fromisoformat(max(stamps))
        except ValueError:
            ref = None
        for book in state.get("bookmakers", []):
            if not book["timestamp"]:
                continue
            try:
                ts = datetime.fromisoformat(book["timestamp"])
            except ValueError:
                continue
            if ref is not None and abs((ref - ts).total_seconds()) / 60.0 <= window_minutes:
                for sel, info in book["selections"].items():
                    per_selection.setdefault(sel, []).append(info["price"])
    response["best_prices"] = {sel: price_summary(prices)
                               for sel, prices in per_selection.items()}
    if model:
        comparison = _compare_with_model(db, match_id, state, model)
        if comparison is not None:
            response["model_comparison"] = comparison
    return response


def _compare_with_model(db: Session, match_id: int, state: dict, model_name: str):
    rows = (db.query(Prediction)
            .filter(Prediction.match_id == match_id, Prediction.model_name == model_name,
                    Prediction.status == "valid")
            .order_by(Prediction.prediction_timestamp.desc()).all())
    if not rows or not rows[0].probabilities:
        return {"error": f"no stored {model_name} prediction for this match"}
    probs = rows[0].probabilities
    model_probs = {"home": probs.get("home_win"), "draw": probs.get("draw"),
                   "away": probs.get("away_win")}
    if any(v is None for v in model_probs.values()):
        return {"error": "stored prediction lacks 1X2 probabilities"}
    consensus_vals = consensus(_consensus_vectors(state))["values"]
    if not consensus_vals:
        return {"error": "no consensus available at this state"}
    result = compare(model_probs, consensus_vals)
    result["model"] = model_name
    result["model_version"] = rows[0].model_version
    return result


@router.get("/markets/{match_id}/history", summary="Chronological odds timeline")
def market_history(match_id: int, db: Session = Depends(get_db), market: str = "h2h"):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    return {"match_id": match_id, "market": market,
            "series": _series(db, match_id, market),
            "calculation_version": MARKET_PROBABILITY_V1}


@router.get("/markets/{match_id}/movement", summary="Opening/current/closing movement")
def market_movement(match_id: int, db: Session = Depends(get_db), market: str = "h2h"):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    closing = closing_state(db, match_id, market)
    closing_lookup = {}
    if closing.get("available"):
        for book in closing["bookmakers"]:
            for sel, info in book["selections"].items():
                closing_lookup[(book["bookmaker"], sel)] = info["price"]
    rows = []
    for entry in _series(db, match_id, market):
        key = (entry["bookmaker"], entry["selection"])
        rows.append({
            "bookmaker": entry["bookmaker"], "market": entry["market"],
            "selection": entry["selection"],
            "opening": entry["opening_price"], "current": entry["current_price"],
            "closing": closing_lookup.get(key),
            "absolute_change": entry["absolute_movement"],
            "percentage_change": entry["percentage_movement"],
            "direction": entry["direction"],
            "velocity_per_hour": entry["movement_velocity_per_hour"],
            "max_price": entry["max_price"], "min_price": entry["min_price"],
            "number_of_movements": entry["number_of_movements"],
        })
    return {"match_id": match_id, "market": market, "movements": rows,
            "calculation_version": MARKET_PROBABILITY_V1}


@router.get("/markets/{match_id}/consensus", summary="Market consensus only")
def market_consensus(match_id: int, db: Session = Depends(get_db),
                     market: str = "h2h", cutoff: Optional[str] = None):
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "match not found")
    cutoff_dt = _parse_cutoff(cutoff) or match.kickoff_at or datetime.now()
    state = get_market_state(db, match_id, cutoff_dt, market)
    return {"match_id": match_id, "market": market, "cutoff": state["cutoff"],
            "consensus": consensus(_consensus_vectors(state)),
            "market_completeness": state["market_completeness"],
            "calculation_version": MARKET_PROBABILITY_V1}


@router.get("/markets/{match_id}/comparison", summary="Model vs market comparison")
def market_comparison(match_id: int, db: Session = Depends(get_db),
                      market: str = "h2h", cutoff: Optional[str] = None,
                      model: str = "ensemble"):
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "match not found")
    cutoff_dt = _parse_cutoff(cutoff) or match.kickoff_at or datetime.now()
    state = get_market_state(db, match_id, cutoff_dt, market)
    comparison = _compare_with_model(db, match_id, state, model)
    actual = actual_outcome(match) if match.status == "FINISHED" else None
    return {"match_id": match_id, "market": market, "cutoff": state["cutoff"],
            "market_state": {k: v for k, v in state.items() if k != "bookmakers"},
            "comparison": comparison, "actual_outcome": actual,
            "calculation_version": MARKET_PROBABILITY_V1}
