"""Prediction lifecycle: versions, refresh, diff, kickoff lock (Phase 7).

Rules: history is immutable (v1 is never overwritten); new information
creates a new version; cutoff is the absolute information boundary;
post-kickoff input cannot modify pre-match predictions; diffs use neutral
wording ("probability shifted", never improving/worsening).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.enums import MatchStatus
from app.db.models.lifecycle import PredictionDiff, PredictionVersion
from app.db.models.predictions import Prediction
from app.services.backtesting.service import store_full_prediction
from app.services.features.temporal import TemporalMode, as_naive_utc

STATE_GENERATED, STATE_REFRESHED = "generated", "refreshed"
STATE_SUPERSEDED, STATE_LOCKED, STATE_EVALUATED = "superseded", "locked", "evaluated"
ACTIVE_STATES = (STATE_GENERATED, STATE_REFRESHED)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ref(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def readiness_gate(db: Session, match_id: int, cutoff: datetime,
                   mode: TemporalMode = TemporalMode.STRICT_PREMATCH) -> Dict:
    """ready | partial | insufficient_data with explicit reasons.

    ready: historical team data sufficient for the core model.
    partial: sufficient, but xG (or secondary inputs) unavailable.
    insufficient: a team lacks usable historical data — the engine must not
    silently substitute arbitrary defaults.
    """
    from app.services.features.availability import assess_availability

    match = db.get(Match, match_id)
    if match is None:
        return {"readiness": "insufficient_data",
                "reasons": ["match missing"]}
    availability = assess_availability(db, match_id, cutoff, mode)
    reasons = list(availability.notes)
    if not availability.goals:
        return {"readiness": "insufficient_data", "reasons": reasons,
                "availability": availability.as_dict()}
    if not availability.xg:
        reasons.append("xG unavailable: goals-only pathway")
        return {"readiness": "partial", "reasons": reasons,
                "availability": availability.as_dict()}
    return {"readiness": "ready", "reasons": reasons,
            "availability": availability.as_dict()}


def _assert_consistent(composed) -> None:
    """Reject malformed predictions (spec: 1X2, grids, BTTS, totals,
    double chance, lambdas, version, cutoff)."""
    from app.services.intelligence import derived

    probs = composed.probabilities or {}
    check = derived.validate_1x2(probs.get("home", -1), probs.get("draw", -1),
                                 probs.get("away", -1))
    if not check["valid"]:
        raise ValueError(f"malformed 1X2 rejected: {check['errors']}")
    goals = composed.goals or {}
    for key in ("home_lambda", "away_lambda"):
        value = goals.get(key)
        if value is not None and (not isinstance(value, (int, float)) or value <= 0):
            raise ValueError(f"malformed lambda rejected: {key}={value!r}")
    markets = composed.markets
    totals = (markets.totals or {}).get("probabilities", {}) if markets else {}
    for line in ("0_5", "1_5", "2_5", "3_5"):
        over, under = totals.get(f"over_{line}"), totals.get(f"under_{line}")
        if over is not None and under is not None and abs(over + under - 1.0) > 1e-6:
            raise ValueError(f"malformed totals rejected at {line}")
    btts = (markets.btts or {}) if markets else {}
    if "yes" in btts and "no" in btts and abs(btts["yes"] + btts["no"] - 1.0) > 1e-6:
        raise ValueError("malformed BTTS rejected")
    if not (composed.model or {}).get("version"):
        raise ValueError("malformed prediction rejected: version missing")
    if not composed.cutoff:
        raise ValueError("malformed prediction rejected: cutoff missing")


def _market_ref(composed) -> Dict:
    market = composed.market
    consensus = (getattr(market, "consensus", None) or {})
    return {
        "status": getattr(market, "status", "unavailable"),
        "timestamp": getattr(market, "timestamp", None),
        "bookmakers": sorted(getattr(market, "bookmakers", []) or []),
        "values": (consensus.get("values") if isinstance(consensus, dict) else None),
    }


def version_input_reference(match_id: int, cutoff: datetime, model_version: str,
                            feature_version: str, market_ref: Dict,
                            seed: Optional[int] = None) -> str:
    canonical = json.dumps({
        "match_id": match_id, "cutoff": str(as_naive_utc(cutoff)),
        "model_version": model_version, "feature_version": feature_version,
        "market": market_ref, "seed": seed}, sort_keys=True, default=str)
    return f"pred_{_ref(canonical)}"


def find_cached_version(db: Session, input_reference: str) -> Optional[PredictionVersion]:
    return db.query(PredictionVersion).filter_by(
        input_reference=input_reference).order_by(
            PredictionVersion.version_number.desc()).first()


def latest_version(db: Session, match_id: int,
                   states: Optional[tuple] = None) -> Optional[PredictionVersion]:
    query = db.query(PredictionVersion).filter_by(match_id=match_id)
    if states is not None:
        query = query.filter(PredictionVersion.state.in_(states))
    return query.order_by(PredictionVersion.version_number.desc()).first()


def history(db: Session, match_id: int) -> List[PredictionVersion]:
    return db.query(PredictionVersion).filter_by(match_id=match_id).order_by(
        PredictionVersion.version_number.asc()).all()


def generate_version(db: Session, match_id: int, cutoff: datetime,
                     mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                     model: Optional[str] = None, seed: Optional[int] = None,
                     state: str = STATE_GENERATED) -> Dict:
    """Build one immutable version: readiness gate -> composer -> persistence.

    Idempotent on (match, cutoff, model, feature, market snapshot): an
    identical request returns the existing version instead of recomputing.
    """
    from app.services.intelligence.composer import PredictionComposer

    match = db.get(Match, match_id)
    if match is None:
        raise ValueError(f"unknown match: {match_id}")
    naive_cutoff = as_naive_utc(cutoff)
    if naive_cutoff is None:
        raise ValueError("cutoff is required")
    if match.kickoff_at is not None and naive_cutoff >= as_naive_utc(match.kickoff_at):
        raise ValueError("cutoff at/after kickoff: pre-match generation refused")
    gate = readiness_gate(db, match_id, cutoff, mode)
    if gate["readiness"] == "insufficient_data":
        raise ValueError(f"prediction refused: {'; '.join(gate['reasons'])}")
    composed = PredictionComposer().compose(db, match_id, cutoff, mode,
                                            model=model, seed=seed)
    _assert_consistent(composed)
    from app.services.predictions.outputs import FullPrediction

    core = composed.core_prediction or {}
    # Single model run: the stored row is reconstructed from the composer's
    # core output (never a second, potentially divergent prediction call).
    full = FullPrediction(**{k: v for k, v in core.items() if k in FullPrediction.model_fields})
    market_ref = _market_ref(composed)
    reference = version_input_reference(
        match_id, cutoff, core.get("model_version", ""),
        composed.model.get("feature_version", "features_v1"), market_ref, seed)
    cached = find_cached_version(db, reference)
    if cached is not None:
        return {"version": _version_out(cached), "cached": True,
                "readiness": gate["readiness"]}
    stored = store_full_prediction(db, match_id, full,
                                   model_config=composed.model.get("selection"))
    previous = latest_version(db, match_id)
    number = (previous.version_number + 1) if previous else 1
    row = PredictionVersion(
        prediction_id=stored.id, match_id=match_id, version_number=number,
        state=state, model_version=core.get("model_version", ""),
        feature_version=composed.model.get("feature_version", "features_v1"),
        cutoff=naive_cutoff, market_snapshot_ids=market_ref,
        feature_snapshot_ref=_ref(json.dumps(core.get("feature_availability", {}),
                                             sort_keys=True, default=str)),
        input_reference=reference, status=composed.status or "ok")
    db.add(row)
    db.commit()
    return {"version": _version_out(row), "cached": False,
            "readiness": gate["readiness"], "prediction_id": stored.id,
            "composed": composed.model_dump()}


def refresh_prediction(db: Session, match_id: int,
                       mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                       model: Optional[str] = None,
                       seed: Optional[int] = None) -> Dict:
    """New cutoff (now) -> new immutable version + diff + supersede.

    Refuses when kickoff has passed (locks instead). Never mutates v1.
    """
    match = db.get(Match, match_id)
    if match is None:
        raise ValueError(f"unknown match: {match_id}")
    now = _now_utc()
    now_naive = as_naive_utc(now)
    if match.kickoff_at is not None and now_naive is not None \
            and now_naive >= as_naive_utc(match.kickoff_at):
        locked = lock_due_predictions(db, match_id)
        raise ValueError("kickoff passed: pre-match refresh refused "
                         f"(locked={locked})")
    previous = latest_version(db, match_id, states=(*ACTIVE_STATES, STATE_LOCKED))
    created = generate_version(db, match_id, now, mode, model=model, seed=seed,
                               state=STATE_REFRESHED)
    current = db.get(PredictionVersion, created["version"]["id"])
    diff_payload: Optional[Dict] = None
    if previous is not None and previous.id != current.id and not created["cached"]:
        diff_payload = compute_diff(db, previous.id, current.id)
        if previous.state in ACTIVE_STATES:
            previous.state = STATE_SUPERSEDED
            db.commit()
    created["diff"] = diff_payload
    created["version"] = _version_out(current)
    return created


def compute_diff(db: Session, from_version_id: int, to_version_id: int) -> Dict:
    """Neutral probability/lambda/market/availability changes between versions."""
    old = db.get(PredictionVersion, from_version_id)
    new = db.get(PredictionVersion, to_version_id)
    if old is None or new is None:
        raise ValueError("unknown version id")
    old_pred = db.get(Prediction, old.prediction_id)
    new_pred = db.get(Prediction, new.prediction_id)
    if old_pred is None or new_pred is None:
        raise ValueError("version references missing prediction")
    old_probs = old_pred.probabilities or {}
    new_probs = new_pred.probabilities or {}
    prob_changes = {}
    for key in ("home_win", "draw", "away_win"):
        before, after = old_probs.get(key), new_probs.get(key)
        if before is None or after is None:
            continue
        absolute = after - before
        prob_changes[key] = {
            "before": round(before, 6), "after": round(after, 6),
            "absolute_change": round(absolute, 6),
            "relative_change": round(absolute / before, 6) if before else None,
            "wording": "probability shifted",
        }
    lambda_changes = {}
    for key in ("expected_home_goals", "expected_away_goals", "expected_total_goals"):
        before, after = old_probs.get(key), new_probs.get(key)
        if before is None or after is None:
            continue
        lambda_changes[key] = {"before": round(before, 4), "after": round(after, 4),
                               "absolute_change": round(after - before, 4)}
    old_avail = (old_pred.feature_availability or {})
    new_avail = (new_pred.feature_availability or {})
    availability_changes = feature_changes(old_avail, new_avail)
    old_market = (old.market_snapshot_ids or {})
    new_market = (new.market_snapshot_ids or {})
    market_changed = old_market.get("values") != new_market.get("values")
    payload = {
        "from_version": old.version_number, "to_version": new.version_number,
        "probability_changes": prob_changes,
        "goal_lambda_changes": lambda_changes,
        "market_changed": market_changed,
        "market_before": old_market.get("values"),
        "market_after": new_market.get("values"),
        "feature_changes": availability_changes,
        "cutoff_before": str(old.cutoff), "cutoff_after": str(new.cutoff),
    }
    row = PredictionDiff(match_id=new.match_id, from_version_id=old.id,
                         to_version_id=new.id, payload=payload)
    db.add(row)
    db.commit()
    payload["diff_id"] = row.id
    return payload


def feature_changes(before: Dict, after: Dict) -> Dict:
    """Newly available / lost / value-changed features from availability records."""
    out = {"became_available": [], "became_unavailable": [], "changed": []}
    flag_keys = ("goals", "shots", "corners", "cards", "xg", "events", "lineups")
    for key in flag_keys:
        if before.get(key) != after.get(key):
            if after.get(key):
                out["became_available"].append(key)
            else:
                out["became_unavailable"].append(key)
    for key in ("home_history", "away_history", "home_xg_history", "away_xg_history"):
        if before.get(key) != after.get(key):
            out["changed"].append({key: {"before": before.get(key),
                                         "after": after.get(key)}})
    return out


def lock_due_predictions(db: Session, match_id: Optional[int] = None) -> int:
    """Mark latest active versions locked once kickoff has passed."""
    now = _now_utc()
    query = db.query(PredictionVersion).filter(
        PredictionVersion.state.in_(list(ACTIVE_STATES)))
    if match_id is not None:
        query = query.filter_by(match_id=match_id)
    locked = 0
    now_naive = as_naive_utc(now)
    for version in query.all():
        match = db.get(Match, version.match_id)
        if match is None or match.kickoff_at is None:
            continue
        if now_naive is not None and now_naive >= as_naive_utc(match.kickoff_at):
            version.state = STATE_LOCKED
            locked += 1
    if locked:
        db.commit()
    return locked


def _version_out(row: PredictionVersion) -> Dict:
    out = {"id": row.id, "prediction_id": row.prediction_id,
           "match_id": row.match_id, "version_number": row.version_number,
           "state": row.state, "model_version": row.model_version,
           "feature_version": row.feature_version,
           "calibration_version": row.calibration_version,
           "scenario_version": row.scenario_version,
           "derived_market_version": row.derived_market_version,
           "cutoff": str(row.cutoff), "input_reference": row.input_reference,
           "status": row.status, "created_at": str(row.created_at)}
    return out


def version_detail(db: Session, row: PredictionVersion) -> Dict:
    """Version row + stored probabilities + market state + data quality."""
    out = _version_out(row)
    pred = db.get(Prediction, row.prediction_id)
    if pred is not None:
        out["probabilities"] = pred.probabilities
        out["market_state"] = (row.market_snapshot_ids or {})
        out["data_quality"] = pred.feature_availability
        out["model_config"] = pred.model_config
    return out
