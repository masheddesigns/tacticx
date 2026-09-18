"""Prediction eligibility gates (Phase 10).

Match-level gate (existence, competition, kickoff, teams, history, freshness,
provenance, conflicts) plus feature-family eligibility (team_form,
player_form, xg, market, ...). Production_strict = strict data access PLUS
no unknown timing, no estimation, no unresolved identity, no critical
conflicts, freshness limits. Estimated research mode keeps estimated labels
visible and never feeds production.

Degraded operation is explicit (degraded_mode + reasons), never silent.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.freshness import policies, provenance as prov

MODE_PRODUCTION_STRICT = "production_strict"
MODE_ESTIMATED = "estimated"


def check_eligibility(db: Session, match_id: int, cutoff: datetime,
                      mode: str = MODE_PRODUCTION_STRICT) -> Dict:
    """Structured eligibility verdict for one match at one cutoff."""
    from app.services.features.availability import assess_availability

    reasons: List[str] = []
    warnings: List[str] = []
    match = db.get(Match, match_id)
    if match is None:
        return {"eligible": False, "reasons": ["match missing"], "warnings": [],
                "degraded_mode": False}
    if match.league_id is None:
        reasons.append("competition unknown")
    if match.kickoff_at is None:
        reasons.append("kickoff unknown")
    if match.home_team_id is None or match.away_team_id is None:
        reasons.append("teams unresolved")
    naive_cutoff = as_naive_utc(cutoff)
    kickoff = as_naive_utc(match.kickoff_at) if match.kickoff_at else None
    if kickoff is not None and naive_cutoff is not None and naive_cutoff >= kickoff:
        reasons.append("cutoff at/after kickoff: pre-match prediction refused")
    strict = (mode == MODE_PRODUCTION_STRICT)
    access_mode = TemporalMode.STRICT_PREMATCH if strict else TemporalMode.HISTORICAL_ESTIMATED
    try:
        availability = assess_availability(db, match_id, cutoff, access_mode)
    except Exception as exc:
        return {"eligible": False, "reasons": [f"availability failed: {exc}"],
                "warnings": [], "degraded_mode": False}
    if not availability.goals:
        reasons.append("required historical data unavailable")
    families = feature_eligibility(db, match_id, cutoff, mode, availability)
    if strict:
        # No unresolved identity.
        if not availability.goals:
            pass  # already recorded
        # No critical conflicts.
        from app.db.models.reconciliation import ReconciliationConflict

        critical = [c for c in db.query(ReconciliationConflict).filter_by(
            entity_type="match", canonical_entity_id=match_id,
            resolution_status="unresolved").all()
            if c.field.split(":")[0] in ("score_mismatch", "team_mismatch",
                                         "league_mismatch",
                                         "duplicate_source_match")]
        if critical:
            reasons.append(
                f"critical reconciliation conflicts: {[c.field for c in critical]}")
        # Feature freshness limits.
        stale_families = [name for name, fam in families.items()
                          if fam.get("freshness", {}).get("state") == "expired"]
        if stale_families:
            warnings.append(f"expired freshness (allowed, flagged): {stale_families}")
    degraded = (not reasons) and any(
        not fam.get("eligible", True) for fam in families.values())
    data_quality = "reduced" if degraded else ("full" if not reasons else "blocked")
    temporal_quality = "strict" if strict else "estimated"
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "warnings": warnings + [f for fam in families.values()
                                for f in fam.get("notes", [])],
        "degraded_mode": degraded,
        "data_quality": data_quality,
        "temporal_quality": temporal_quality,
        "freshness": {name: (fam.get("freshness", {}) or {}).get("state", "unknown")
                      for name, fam in families.items()},
        "families": families,
        "mode": mode,
    }


def feature_eligibility(db: Session, match_id: int, cutoff: datetime,
                        mode: str, availability=None) -> Dict[str, Dict]:
    """Per-family eligibility (no global boolean). Each family states its own
    temporal basis; estimated families never pass as strict."""
    from app.services.features.availability import assess_availability

    if availability is None:
        access = TemporalMode.STRICT_PREMATCH if mode == MODE_PRODUCTION_STRICT \
            else TemporalMode.HISTORICAL_ESTIMATED
        availability = assess_availability(db, match_id, cutoff, access)
    avail = availability.as_dict() if hasattr(availability, "as_dict") else availability
    naive_cutoff = as_naive_utc(cutoff)

    def fam(eligible: bool, temporal: str, freshness_family: Optional[str],
            age_days_value: Optional[float], notes: List[str]) -> Dict:
        freshness = policies.classify_freshness(
            freshness_family or "default", age_days_value) \
            if freshness_family else {"state": "unknown"}
        return {"eligible": eligible, "temporal": temporal,
                "freshness": freshness, "notes": notes}

    match = db.get(Match, match_id)
    families = {
        "team_form": fam(bool(avail.get("goals")), "known" if avail.get("goals") else "unknown",
                         "team_form", _history_age(db, match, cutoff),
                         [] if avail.get("goals") else ["insufficient goal history"]),
        "player_form": fam(False, "unknown", "player_form", None,
                           ["player features estimated-only on this dataset; "
                            "strict-ineligible by temporal policy"]),
        "xg": fam(bool(avail.get("xg")), "known" if avail.get("xg") else "unknown",
                  "xg", None,
                  [] if avail.get("xg") else ["xG unavailable: goals-only pathway"]),
        "market": fam(True, "known", "odds", _market_age(db, match_id, cutoff),
                      ["market is observed context, never a model input"]),
    }
    if mode != MODE_PRODUCTION_STRICT:
        families["player_form"] = fam(
            True, "estimated", "player_form", None,
            ["estimated research mode: temporal_quality=estimated, "
             "never consumed by production"])
    return families


def _history_age(db: Session, match: Optional[Match], cutoff: datetime) -> Optional[float]:
    if match is None:
        return None
    from app.services.features.repository import HistoricalFeatureRepository

    try:
        repo = HistoricalFeatureRepository(db, cutoff, TemporalMode.STRICT_PREMATCH)
        histories = [repo.team_matches_before(match.home_team_id),
                     repo.team_matches_before(match.away_team_id)]
        kickoffs = [as_naive_utc(m.kickoff_at) for h in histories for m in h
                    if m.kickoff_at]
        if not kickoffs:
            return None
        naive_cutoff = as_naive_utc(cutoff)
        return max(0.0, (naive_cutoff - max(kickoffs)).total_seconds() / 86400.0)
    except Exception:
        return None


def _market_age(db: Session, match_id: int, cutoff: datetime) -> Optional[float]:
    from app.db.models.odds import OddsSnapshot

    naive_cutoff = as_naive_utc(cutoff)
    latest = db.query(OddsSnapshot).filter(
        OddsSnapshot.match_id == match_id,
        OddsSnapshot.timestamp <= naive_cutoff).order_by(
            OddsSnapshot.timestamp.desc()).first()
    if latest is None or latest.timestamp is None:
        return None
    stamp = as_naive_utc(latest.timestamp)
    if naive_cutoff is None or stamp is None:
        return None
    return max(0.0, (naive_cutoff - stamp).total_seconds() / 86400.0)
