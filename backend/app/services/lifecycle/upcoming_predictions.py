"""Upcoming prediction pipeline (Phase 7).

upcoming match -> canonical resolution (already stored) -> historical
feature snapshot -> current eligible market -> prediction composer ->
immutable persistence. No model training during generation.

Batch failures are per-match isolated: one failure never corrupts others,
and every outcome (success/partial/failed) is reported explicitly.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.enums import MatchStatus
from app.services.features.temporal import TemporalMode
from app.services.lifecycle import versions


def match_data_quality(composed_dump: Dict) -> Dict:
    """Defined calculation (no invented percentages):

    feature_completeness = available leaves / total leaves (snapshot count);
    market_completeness = composer market status; temporal_quality =
    verified when cutoff < kickoff else broken.
    """
    data_quality = composed_dump.get("data_quality", {}) or {}
    total = (data_quality.get("available_feature_count", 0)
             + data_quality.get("missing_feature_count", 0))
    available = data_quality.get("available_feature_count", 0)
    market = composed_dump.get("market", {}) or {}
    cutoff = composed_dump.get("cutoff", "")
    kickoff = (composed_dump.get("match", {}) or {}).get("kickoff_at", "")
    temporal_quality = "verified" if cutoff and kickoff and cutoff < kickoff else (
        "broken" if cutoff and kickoff else "unknown")
    return {
        "feature_completeness": round(available / total, 4) if total else None,
        "feature_available": available, "feature_total": total,
        "market_completeness": market.get("status", "unavailable"),
        "temporal_quality": temporal_quality,
        "readiness": None,
    }


class UpcomingPredictionService:
    """Generate + refresh upcoming-match predictions with lifecycle state."""

    def __init__(self, model: Optional[str] = None,
                 mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                 seed: Optional[int] = None):
        self.model = model
        self.mode = mode
        self.seed = seed

    def predict_one(self, db: Session, match_id: int,
                    cutoff: Optional[datetime] = None) -> Dict:
        match = db.get(Match, match_id)
        if match is None:
            return {"match_id": match_id, "status": "failed",
                    "error": "match not found"}
        if match.status not in (MatchStatus.SCHEDULED.value,
                                MatchStatus.PRE_MATCH.value):
            return {"match_id": match_id, "status": "failed",
                    "error": f"match status {match.status}: not predictable pre-match"}
        at = cutoff or datetime.now(timezone.utc)
        try:
            created = versions.generate_version(db, match_id, at, self.mode,
                                                model=self.model, seed=self.seed)
        except ValueError as exc:
            return {"match_id": match_id, "status": "failed", "error": str(exc)}
        except Exception as exc:
            return {"match_id": match_id, "status": "failed",
                    "error": f"prediction failed: {str(exc)[:200]}"}
        quality = match_data_quality(created.get("composed", {}) or {})
        quality["readiness"] = created.get("readiness")
        status = "success" if created.get("readiness") == "ready" else "partial"
        return {"match_id": match_id, "status": status,
                "cached": created.get("cached", False),
                "version": created["version"], "quality": quality}

    def predict_window(self, db: Session, hours: Optional[int] = None,
                       league_code: Optional[str] = None,
                       limit: int = 100) -> Dict:
        """Batch predictions for upcoming matches. Per-match isolation."""
        from app.db.models.core import League

        now = datetime.now(timezone.utc)
        from datetime import timedelta

        from app.config import get_settings

        span = hours if hours is not None else get_settings().NEXT_MATCH_LOOKAHEAD_HOURS
        query = db.query(Match).filter(
            Match.status.in_([MatchStatus.SCHEDULED.value,
                              MatchStatus.PRE_MATCH.value]),
            Match.kickoff_at.is_not(None),
            Match.kickoff_at > now,
            Match.kickoff_at <= now + timedelta(hours=max(1, span)))
        if league_code:
            league = db.query(League).filter_by(code=league_code).first()
            if league is None:
                return {"status": "failed", "error": f"unknown league: {league_code}",
                        "results": []}
            query = query.filter(Match.league_id == league.id)
        matches = query.order_by(Match.kickoff_at.asc()).limit(max(1, limit)).all()
        results, start = [], time.monotonic()
        for match in matches:
            try:
                results.append(self.predict_one(db, match.id))
            except Exception as exc:
                db.rollback()
                results.append({"match_id": match.id, "status": "failed",
                                "error": str(exc)[:200]})
        ok = sum(1 for r in results if r["status"] == "success")
        partial = sum(1 for r in results if r["status"] == "partial")
        failed = sum(1 for r in results if r["status"] == "failed")
        overall = "success" if failed == 0 else ("partial" if ok + partial > 0 else "failed")
        return {"status": overall, "window_hours": span, "league": league_code or "",
                "n_matches": len(results), "n_success": ok, "n_partial": partial,
                "n_failed": failed, "duration_seconds": round(time.monotonic() - start, 2),
                "results": results}

    def refresh_one(self, db: Session, match_id: int) -> Dict:
        try:
            created = versions.refresh_prediction(db, match_id, self.mode,
                                                  model=self.model, seed=self.seed)
        except ValueError as exc:
            return {"match_id": match_id, "status": "failed", "error": str(exc)}
        except Exception as exc:
            return {"match_id": match_id, "status": "failed",
                    "error": f"refresh failed: {str(exc)[:200]}"}
        return {"match_id": match_id, "status": "success",
                "cached": created.get("cached", False),
                "version": created["version"], "diff": created.get("diff")}
