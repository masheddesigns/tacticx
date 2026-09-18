"""Intelligence orchestrator: read-only assembly + invariant checks (Phase 15).

Wraps the Phase 6 composer/analogues/scenarios without mutating anything:
no prediction, model, snapshot, odds or history writes occur here (except
the intelligence snapshot row itself when persist=True). Invalid
probabilities fail loudly instead of rendering.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.intelligence_v2 import IntelligenceSnapshot
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.intelligence import derived
from app.services.intelligence.composer import PredictionComposer
from app.services.intelligence_v2 import market_labels, warnings


def _hash(payload: Dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     default=str).encode()).hexdigest()


def check_invariants(composed: Dict) -> List[str]:
    """Mathematical invariants; non-empty return means invalid output."""
    errors = []
    probs = composed.get("probabilities", {}) or {}
    check = derived.validate_1x2(probs.get("home", -1), probs.get("draw", -1),
                                 probs.get("away", -1))
    if not check["valid"]:
        errors.extend(f"1x2: {e}" for e in check["errors"])
    markets = composed.get("markets", {}) or {}
    totals = (markets.get("totals") or {}).get("probabilities", {}) or {}
    for line in ("0_5", "1_5", "2_5", "3_5"):
        over, under = totals.get(f"over_{line}"), totals.get(f"under_{line}")
        if over is not None and under is not None and abs(over + under - 1.0) > 1e-6:
            errors.append(f"totals {line}: over+under={over + under}")
    btts = markets.get("btts", {}) or {}
    if "yes" in btts and "no" in btts and abs(btts["yes"] + btts["no"] - 1.0) > 1e-6:
        errors.append("btts: yes+no != 1")
    dc = (markets.get("double_chance") or {}).get("probabilities", {}) or {}
    home, draw, away = probs.get("home"), probs.get("draw"), probs.get("away")
    if all(isinstance(v, (int, float)) for v in (home, draw, away)) and dc:
        if abs(dc.get("1x", 0) - (home + draw)) > 1e-6:
            errors.append("double chance 1x identity failed")
        if abs(dc.get("x2", 0) - (draw + away)) > 1e-6:
            errors.append("double chance x2 identity failed")
        if abs(dc.get("12", 0) - (home + away)) > 1e-6:
            errors.append("double chance 12 identity failed")
    grid = composed.get("score_distribution", {}) or {}
    if grid and abs(sum(grid.values()) - 1.0) > 1e-3:
        errors.append("score grid != 1")
    req16 = (markets.get("correct_scores") or {}).get("required_16_mass")
    tail = (markets.get("correct_scores") or {}).get("tail_mass", 0.0) or 0.0
    if req16 is not None and abs(req16 + tail - 1.0) > 1e-6:
        errors.append("required-16 + tail != 1")
    return errors


def build_intelligence(db: Session, match_id: int, cutoff: datetime,
                       mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                       model: Optional[str] = None, seed: Optional[int] = None,
                       with_analogues: bool = False,
                       with_scenarios: bool = False,
                       persist: bool = True) -> Dict:
    """Assemble the canonical intelligence response (§20 shape)."""
    from app.services.intelligence import analogues as analogue_svc
    from app.services.intelligence import scenarios as scenario_svc

    match = db.get(Match, match_id)
    if match is None:
        raise ValueError(f"unknown match: {match_id}")
    naive_cutoff = as_naive_utc(cutoff)
    if naive_cutoff is None:
        raise ValueError("cutoff is required")
    composed = PredictionComposer().compose(db, match_id, cutoff, mode,
                                            model=model, seed=seed)
    dump = composed.model_dump()
    errors = check_invariants(dump)
    if errors:
        raise ValueError(f"invalid probabilities rejected: {errors}")
    analogues_out: Dict = {"status": "not_requested", "analogues": []}
    if with_analogues:
        analogues_out = analogue_svc.find_analogues(
            db, match_id, cutoff, mode).model_dump()
    scenarios_out: List[Dict] = []
    if with_scenarios:
        lam_h = (dump.get("goals") or {}).get("home_lambda")
        lam_a = (dump.get("goals") or {}).get("away_lambda")
        if lam_h is not None and lam_a is not None:
            scenarios_out = [s.model_dump() for s in scenario_svc.run_all(
                {k: dump["probabilities"][k] for k in ("home", "draw", "away")},
                lam_h, lam_a)]
    market = dump.get("market", {}) or {}
    consensus = (market.get("consensus") or {}).get("values", {}) or {}
    labels = market_labels.categorize(
        {k: dump["probabilities"][k] for k in ("home", "draw", "away")},
        consensus) if consensus else {"status": "no_market_consensus"}
    response = {
        "prediction": {"home": dump["probabilities"]["home"],
                       "draw": dump["probabilities"]["draw"],
                       "away": dump["probabilities"]["away"]},
        "goals": dump.get("goals", {}),
        "markets": dump.get("markets", {}),
        "score_distribution": dump.get("score_distribution", {}),
        "uncertainty": dump.get("uncertainty", {}),
        "model_disagreement": dump.get("model_disagreement", {}),
        "data_quality": dump.get("data_quality", {}),
        "market_comparison": {"market": market, "interpretation": labels},
        "analogues": analogues_out,
        "scenarios": scenarios_out,
        "warnings": warnings.generate_warnings(dump),
        "explanation": dump.get("explanation", {}),
        "core_prediction": dump.get("core_prediction", {}),
        "provenance": {
            "match_id": match_id, "cutoff": str(naive_cutoff),
            "model": dump.get("model", {}),
            "temporal_mode": mode.value,
            "dataset_version": "canonical_store",
            "market_snapshot_version": "market_probability_v1",
        },
    }
    digest = _hash(response)
    response["provenance"]["hash"] = digest
    snapshot_id = None
    if persist:
        existing = db.query(IntelligenceSnapshot).filter_by(
            match_id=match_id, payload_hash=digest).first()
        if existing is not None:
            snapshot_id = existing.snapshot_id
        else:
            row = IntelligenceSnapshot(
                snapshot_id=f"intel_{digest[:16]}", match_id=match_id,
                prediction_id=(dump.get("core_prediction") or {}).get(
                    "prediction_id"),
                model_version=(dump.get("model") or {}).get("version", ""),
                cutoff=naive_cutoff, payload=response, payload_hash=digest)
            db.add(row)
            db.commit()
            snapshot_id = row.snapshot_id
    response["provenance"]["snapshot_id"] = snapshot_id
    return response


def load_snapshot(db: Session, snapshot_id: str) -> Dict:
    """Content-addressed read of a stored snapshot (immutable → always safe)."""
    row = db.query(IntelligenceSnapshot).filter_by(snapshot_id=snapshot_id).first()
    if row is None:
        raise ValueError(f"unknown snapshot: {snapshot_id}")
    return row.payload or {}
