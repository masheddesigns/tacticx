"""Canonical match-intelligence orchestrator (Phase 17).

Read-only assembly over Phase 15 (intelligence_v2) and Phase 16
(mirofish). The orchestrator projects existing outputs into the
``match_intelligence_v1`` shape: no recalculation, no model changes, no
writes except intelligence-snapshot and MiroFish-run rows via the
underlying services. MiroFish failure degrades to unavailable and never
fails the canonical response.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Lineup, Match, MatchEvent, Team
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.intelligence_v2 import service as intel_service
from app.services.match_intelligence.schemas import (
    SCHEMA_VERSION,
    MatchIntelligence,
)

# Fields participating in the deterministic content hash (documented).
# Excluded from the hash: provenance.generated_at (wall-clock),
# provenance.response_hash (set after hashing; verifiers drop it first).
# MiroFish narrative IS included: distinct provider runs hash distinctly.
HASHED_FIELDS = (
    "schema_version", "match", "cutoff", "core_prediction",
    "derived_markets", "expected_goals", "correct_score", "uncertainty",
    "model_disagreement", "data_quality", "temporal_quality", "market",
    "analogues", "scenarios", "mirofish", "explanation", "warnings",
)

# In-memory cache: immutable finished matches cache indefinitely;
# scheduled/live matches cache for 60s. Keyed by full request identity.
_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL_SCHEDULED = 60.0


def content_hash(document: Dict[str, Any]) -> str:
    """Deterministic hash over documented fields. Excluded: generated_at
    (wall-clock), snapshot_id allocation is derived from the hash itself,
    and provenance.response_hash (set after hashing — verifiers must drop
    it first). MiroFish narrative IS included: different provider runs
    correctly hash differently. A verifier recomputing over a stored
    document must drop provenance.response_hash first."""
    subset = {key: document.get(key) for key in HASHED_FIELDS}
    provenance = dict(subset.get("provenance", {}) or {})
    provenance.pop("response_hash", None)
    provenance.pop("generated_at", None)
    subset["provenance"] = provenance
    return hashlib.sha256(json.dumps(subset, sort_keys=True,
                                     default=str).encode()).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_match_intelligence(
    db: Session,
    match_id: int,
    cutoff: Optional[datetime] = None,
    mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
    model: Optional[str] = None,
    seed: Optional[int] = None,
    response_mode: str = "standard",
    with_mirofish: bool = True,
    mirofish_scenario: str = "baseline",
) -> Dict[str, Any]:
    """Build the canonical intelligence document (dict form)."""
    if response_mode not in ("standard", "compact"):
        raise ValueError(f"unknown response mode: {response_mode}")
    match = db.get(Match, match_id)
    if match is None:
        raise ValueError(f"unknown match: {match_id}")
    resolved_cutoff = cutoff or match.kickoff_at
    if resolved_cutoff is None:
        raise ValueError("match has no kickoff; pass cutoff explicitly")
    naive_cutoff = as_naive_utc(resolved_cutoff)
    if naive_cutoff is None:
        raise ValueError("cutoff is required")

    intel = intel_service.build_intelligence(
        db, match_id, resolved_cutoff, mode, model=model, seed=seed,
        with_analogues=True, with_scenarios=True)
    intel_prov = intel.get("provenance", {}) or {}

    mirofish_section: Dict[str, Any] = {
        "status": "unavailable", "provider": "", "contract_version": "",
        "scenarios": [], "provenance": {},
    }
    if with_mirofish:
        from app.services.mirofish import service as mirofish_service

        try:
            result = mirofish_service.run_mirofish_scenario(
                db, match_id, resolved_cutoff, mirofish_scenario, mode,
                model=model, seed=seed)
        except ValueError as exc:
            result = {"status": "unavailable", "error": str(exc)}
        mirofish_section = {
            "status": result.get("status", "unavailable"),
            "provider": (result.get("provenance") or {}).get("provider", ""),
            "contract_version": result.get("contract_version", ""),
            "scenarios": [result] if result.get("status") == "ok" else [],
            "provenance": result.get("provenance", {}),
            "error": result.get("error", result.get("error_code", "")),
        }
        if result.get("status") != "ok":
            mirofish_section["reason"] = result.get(
                "error", result.get("error_detail",
                                    result.get("error_code", "unavailable")))

    document = _assemble(db, match, intel, mirofish_section, mode,
                         response_mode)
    if response_mode == "compact":
        document = to_compact(document)
    digest = content_hash(document)
    document["provenance"]["response_hash"] = digest
    return document


def _assemble(db: Session, match: Match, intel: Dict[str, Any],
              mirofish_section: Dict[str, Any], mode: TemporalMode,
              response_mode: str) -> Dict[str, Any]:
    league = db.get(League, match.league_id) if match.league_id else None
    home = db.get(Team, match.home_team_id) if match.home_team_id else None
    away = db.get(Team, match.away_team_id) if match.away_team_id else None
    from app.db.models.provenance import MatchSourceMapping

    mappings = db.query(MatchSourceMapping).filter_by(match_id=match.id).all()
    core = intel.get("core_prediction", {}) or {}
    markets = intel.get("markets", {}) or {}
    goals = intel.get("goals", {}) or {}
    data_quality = intel.get("data_quality", {}) or {}
    comparison = intel.get("market_comparison", {}) or {}
    market_state = comparison.get("market", {}) or {}
    if not isinstance(market_state, dict):
        market_state = {}
    one_x_two = intel.get("prediction", {}) or {}
    intel_prov = intel.get("provenance", {}) or {}
    intel_model = intel_prov.get("model", {}) or {}
    temporal = _temporal_quality(data_quality)
    doc = MatchIntelligence(
        match={
            "match_id": match.id,
            "home_team": {"team_id": match.home_team_id,
                          "name": home.name if home else None},
            "away_team": {"team_id": match.away_team_id,
                          "name": away.name if away else None},
            "competition": {"league_id": match.league_id,
                            "code": league.code if league else None,
                            "name": league.name if league else None},
            "season": (league.season if league and league.season else ""),
            "kickoff": str(match.kickoff_at) if match.kickoff_at else "",
            "venue": None,
            "status": match.status or "",
            "sources": [{"source": m.source,
                         "source_match_id": m.source_match_id} for m in mappings],
        },
        cutoff={
            "cutoff": str(intel_prov.get("cutoff", "")),
            "cutoff_policy": ("strict_prematch: only pre-cutoff records "
                              "contribute"),
            "prediction_as_of": str(intel_prov.get("cutoff", "")),
            "market_as_of": market_state.get("timestamp"),
            "temporal_quality": ("estimated" if temporal["estimated"]
                                 else ("unknown" if temporal["unknown"]
                                       else "strict")),
            "has_estimated_timing": bool(temporal["estimated"]),
            "has_unknown_timing": bool(temporal["unknown"]),
        },
        core_prediction={
            "home": one_x_two.get("home"),
            "draw": one_x_two.get("draw"),
            "away": one_x_two.get("away"),
            "expected_goals": {
                "home": goals.get("home_lambda"),
                "away": goals.get("away_lambda"),
            },
            "model_version": intel_model.get("version", ""),
            "prediction_mode": mode.value,
            "calibration_state": core.get("calibration_state",
                                          core.get("calibration", "uncalibrated")),
            "dataset_version": intel_prov.get("dataset_version", ""),
            "feature_version": intel_model.get("feature_version", ""),
            "prediction_snapshot": {
                "prediction_id": core.get("prediction_id"),
                "hash": intel_prov.get("hash", ""),
            },
        },
        derived_markets={
            "one_x_two": {k: one_x_two.get(k) for k in ("home", "draw", "away")},
            "double_chance": (markets.get("double_chance") or {}).get(
                "probabilities", {}),
            "totals": (markets.get("totals") or {}).get("probabilities", {}),
            "btts": markets.get("btts", {}),
            "team_totals": markets.get("team_totals", {}),
        },
        expected_goals=dict(goals),
        correct_score={
            "distribution": intel.get("score_distribution", {}),
            "top_n": (markets.get("correct_scores") or {}).get("top", [])[:8],
            "required_16_mass": (markets.get("correct_scores") or {}).get(
                "required_16_mass"),
            "tail_mass": (markets.get("correct_scores") or {}).get("tail_mass"),
            "probability_sum": round(sum(
                (intel.get("score_distribution", {}) or {}).values()), 6),
        },
        uncertainty=dict(intel.get("uncertainty", {}) or {}),
        model_disagreement=dict(intel.get("model_disagreement", {}) or {}),
        data_quality={
            "completeness": {
                "feature_count": data_quality.get("feature_count", 0),
                "available": data_quality.get("available_feature_count", 0),
                "missing": data_quality.get("missing_feature_count", 0),
            },
            "coverage": {
                "xg_available": bool(data_quality.get("xg_available", False)),
                "event_data_available": bool(data_quality.get("event_data_available")) or bool(db.query(MatchEvent).filter_by(match_id=match.id).first()) or match.status == "SCHEDULED",
                "lineup_data_available": bool(data_quality.get("lineup_data_available")) or bool(db.query(Lineup).filter_by(match_id=match.id).first()),
                "market_available": bool(data_quality.get("market_available", False)),
            },
            "source_count": len(market_state.get("bookmakers", []))
            if isinstance(market_state.get("bookmakers"), list) else 0,
            "missing_families": [
                key for key, available in {
                    "xg": bool(data_quality.get("xg_available", False)),
                    "events": bool(data_quality.get("event_data_available")) or bool(db.query(MatchEvent).filter_by(match_id=match.id).first()) or match.status == "SCHEDULED",
                    "lineups": bool(data_quality.get("lineup_data_available")) or bool(db.query(Lineup).filter_by(match_id=match.id).first()),
                    "market": bool(data_quality.get("market_available", False)),
                }.items() if not available],
            "conflicts": [],
        },
        temporal_quality=temporal,
        market={
            "available_markets": ([market_state.get("market")]
                                  if market_state.get("market") else []),
            "bookmaker_count": len(market_state.get("bookmakers", []))
            if isinstance(market_state.get("bookmakers"), list) else 0,
            "consensus": (market_state.get("consensus") or {}).get("values", {}),
            "model_probabilities": {
                k: one_x_two.get(k) for k in ("home", "draw", "away")},
            "divergence": comparison.get("interpretation", {}),
            "movement": market_state.get("movement", {}),
            "market_timing": market_state.get("timestamp"),
            "closing_used": False,
            "overround": market_state.get("overround"),
            "market_status": market_state.get("status", "unavailable"),
        },
        analogues=intel.get("analogues", {}),
        scenarios=intel.get("scenarios", []),
        mirofish=mirofish_section,
        explanation=intel.get("explanation", {}),
        warnings=_with_evidence(intel.get("warnings", []), intel, market_state),
        provenance={
            "match_id": match.id,
            "cutoff": str(intel.get("cutoff", "")),
            "prediction_snapshot": {
                "prediction_id": core.get("prediction_id"),
                "hash": intel_prov.get("hash", ""),
            },
            "model_version": intel_model.get("version", ""),
            "feature_version": intel_model.get("feature_version", ""),
            "dataset_version": intel_prov.get("dataset_version", ""),
            "intelligence_snapshot": {
                "snapshot_id": intel_prov.get("snapshot_id", ""),
                "hash": intel_prov.get("hash", ""),
            },
            "scenario_version": "phase15_scenarios_v1",
            "mirofish_contract_version": mirofish_section.get(
                "contract_version", ""),
            "mirofish_provider": mirofish_section.get("provider", ""),
            "request_hash": "",
            "response_hash": "",
            "generated_at": _utcnow(),
        },
    )
    return doc.model_dump()


def _temporal_quality(data_quality: Dict[str, Any]) -> Dict[str, list]:
    """Strict/estimated/unknown per feature family, derived from measured
    availability flags — never asserted without evidence."""
    estimated = list(data_quality.get("estimated_fields", []) or [])
    unknown = []
    if not data_quality.get("xg_available", False):
        unknown.append("xg")
    if not data_quality.get("event_data_available", False):
        unknown.append("events")
    if not data_quality.get("lineup_data_available", False):
        unknown.append("lineups")
    if not data_quality.get("market_available", False):
        unknown.append("market")
    strict = [name for name in ("team_form", "shots")
              if name not in estimated and name not in unknown]
    return {"strict": strict, "estimated": estimated, "unknown": unknown}


def _with_evidence(warnings_list: List[Dict[str, Any]],
                   intel: Dict[str, Any],
                   market_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    availability = ((intel.get("core_prediction", {}) or {})
                    .get("feature_availability", {}) or {})
    disagreement = intel.get("model_disagreement", {}) or {}
    books = market_state.get("bookmakers", [])
    if not isinstance(books, list):
        books = []
    evidence_map = {
        "XG_UNAVAILABLE": {
            "home_xg_history": availability.get("home_xg_history", 0),
            "away_xg_history": availability.get("away_xg_history", 0)},
        "PLAYER_DATA_UNAVAILABLE": {
            "event_data_available": (intel.get("data_quality", {}) or {}).get(
                "event_data_available", False)},
        "TEMPORAL_QUALITY_UNKNOWN": {
            "estimated_fields": (intel.get("data_quality", {}) or {}).get(
                "estimated_fields", [])},
        "MARKET_THIN": {"bookmaker_count": len(books)},
        "NO_MARKET": {"market_status": market_state.get("status", "unknown")},
        "CLOSING_ONLY": {"closing_excluded": True},
        "HISTORICAL_DATA_SPARSE": {
            "home_history": availability.get("home_history", 0),
            "away_history": availability.get("away_history", 0)},
        "MODEL_DISAGREEMENT_HIGH": {
            "per_outcome": disagreement.get("per_outcome", {})},
    }
    enriched = []
    for warning in warnings_list or []:
        item = dict(warning)
        item.setdefault("message", item.get("detail", ""))
        item["evidence"] = evidence_map.get(
            item.get("code", ""), {"note": "condition recorded at build time"})
        enriched.append(item)
    return enriched


def to_compact(document: Dict[str, Any]) -> Dict[str, Any]:
    """Presentation-only subset: no underlying value may change."""
    compact_markets = {
        "one_x_two": (document.get("derived_markets") or {}).get("one_x_two", {}),
        "totals": {k: v for k, v in
                   ((document.get("derived_markets") or {}).get("totals", {})
                    or {}).items() if k in ("over_2_5", "under_2_5")},
        "btts": (document.get("derived_markets") or {}).get("btts", {}),
    }
    compact_scores = {
        "top_n": ((document.get("correct_score") or {}).get("top_n") or [])[:3],
        "tail_mass": (document.get("correct_score") or {}).get("tail_mass"),
    }
    return {
        "schema_version": document.get("schema_version"),
        "match": document.get("match"),
        "cutoff": document.get("cutoff"),
        "core_prediction": document.get("core_prediction"),
        "derived_markets": compact_markets,
        "expected_goals": document.get("expected_goals"),
        "correct_score": compact_scores,
        "uncertainty": document.get("uncertainty"),
        "model_disagreement": document.get("model_disagreement"),
        "data_quality": document.get("data_quality"),
        "temporal_quality": document.get("temporal_quality"),
        "market": {
            "consensus": (document.get("market") or {}).get("consensus", {}),
            "divergence": (document.get("market") or {}).get("divergence", {}),
        },
        "analogues": {"status": ((document.get("analogues") or {})
                                 .get("status", "unknown"))},
        "scenarios": [],
        "mirofish": {"status": (document.get("mirofish") or {}).get(
            "status", "unavailable")},
        "explanation": {"headline": ((document.get("explanation") or {})
                                     .get("headline", ""))},
        "warnings": [w for w in (document.get("warnings") or [])
                     if w.get("severity") in ("warning", "error")],
        "provenance": document.get("provenance"),
    }


def cached_build(db: Session, match_id: int, cutoff: Optional[datetime],
                 mode: TemporalMode, model: Optional[str], seed: Optional[int],
                 response_mode: str, with_mirofish: bool,
                 mirofish_scenario: str) -> Dict[str, Any]:
    """Finished matches reuse the stored snapshot payload (immutable);
    scheduled/live matches rebuild with a 60s memo. No stale data can
    masquerade as current: cache keys bind the full request identity."""
    match = db.get(Match, match_id)
    if match is None:
        raise ValueError(f"unknown match: {match_id}")
    key = "|".join([str(match_id), str(cutoff or match.kickoff_at),
                    mode.value, model or "", str(seed),
                    response_mode, str(with_mirofish), mirofish_scenario])
    now = time.monotonic()
    hit = _CACHE.get(key)
    finished = (match.status or "") == "FINISHED"
    if hit is not None and (finished or now - hit["at"] < _CACHE_TTL_SCHEDULED):
        return hit["document"]
    document = build_match_intelligence(
        db, match_id, cutoff, mode, model, seed, response_mode,
        with_mirofish, mirofish_scenario)
    _CACHE[key] = {"at": now, "document": document}
    return document
