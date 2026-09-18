"""Historical backfill orchestrator (Phase 13).

Season CSV → polite download → validation → proven import_rows path
(identity, reconciliation, idempotency inside the pipeline) → temporal
check → quality gate → coverage measurement. Uses existing canonical
resolution; no parallel data model; no model code touched.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.data_expansion import acquisition as acquisition_svc
from app.services.data_expansion import validation as validation_svc


def backfill_season(db: Session, league_code: str, season_tag: str,
                    dest_dir: str = "/tmp", dry_run: bool = False) -> Dict:
    """Backfill one (league, season). Dry-run downloads + validates + counts
    without persisting."""
    from app.services.sources.historical.csv_source import import_rows, read_dataset

    started = time.monotonic()
    probe = acquisition_svc.probe(league_code, season_tag)
    if not probe.get("exists"):
        return {"league": league_code, "season": season_tag, "status": "unavailable",
                "reason": probe.get("error", "HEAD probe failed"),
                "duration_seconds": round(time.monotonic() - started, 2)}
    fetched = acquisition_svc.download(league_code, season_tag, dest_dir)
    if not fetched.get("path"):
        return {"league": league_code, "season": season_tag, "status": "failed",
                "reason": fetched.get("error", "download failed"),
                "duration_seconds": round(time.monotonic() - started, 2)}
    rows, _ = read_dataset(fetched["path"])
    sanity = validation_svc.validate_rows(rows)
    if dry_run:
        return {"league": league_code, "season": season_tag, "status": "dry_run",
                "bytes": fetched["bytes"], "sha256_16": fetched["sha256_16"],
                "row_sanity": sanity,
                "duration_seconds": round(time.monotonic() - started, 2)}
    rejected: list = []
    rid_prefix = f"fdcuk-{league_code}-{season_tag}-"
    report = import_rows(db, "football_data_co_uk", rows, league_code, season_tag,
                         rejected_sink=rejected,
                         rid_prefix=rid_prefix,
                         source_url=fetched["url"])
    report["rejected_rows"] = len(rejected)
    temporal = _temporal_check(db, league_code)
    season_check = _season_window_check(db, league_code, season_tag, rid_prefix)
    report.update({
        "league": league_code, "season": season_tag, "status": "imported",
        "bytes": fetched["bytes"], "sha256_16": fetched["sha256_16"],
        "row_sanity": sanity, "temporal": temporal,
        "season_window": season_check,
        "duration_seconds": round(time.monotonic() - started, 2)})
    if not season_check.get("ok", False):
        report["status"] = "imported_with_warning"
    return report


def _season_window_check(db: Session, league_code: str, season_tag: str,
                         rid_prefix: str) -> Dict:
    """Defense-in-depth: created rows must kick off inside the season window.
    Catches cross-league rid reuse and mislabeled files before they spread."""
    from app.db.models.core import Match

    try:
        start_year = int(season_tag[:2])
        start_year += 2000 if start_year < 50 else 1900
    except (TypeError, ValueError):
        return {"ok": False, "reason": f"unparseable season_tag {season_tag!r}"}
    rows = db.query(Match).filter(
        Match.provider_match_id.like(f"{rid_prefix}%")).all()
    if not rows:
        return {"ok": False, "reason": "no rows created under this rid prefix"}
    in_window = 0
    for match in rows:
        if match.kickoff_at is None:
            continue
        kickoff = match.kickoff_at
        # Season Aug(Y)-Jul(Y+1): kickoff year Y with month>=8, or Y+1.
        if (kickoff.year == start_year and kickoff.month >= 8) or \
           (kickoff.year == start_year + 1 and kickoff.month < 8):
            in_window += 1
    ratio = in_window / len(rows)
    return {"ok": ratio >= 0.9, "in_window": in_window, "rows": len(rows),
            "ratio": round(ratio, 4)}


def _temporal_check(db: Session, league_code: str) -> Dict:
    """Post-import temporal honesty: effective_at presence on new stat rows."""
    from app.db.models.core import League, Lineup, Match, MatchEvent, MatchStatistic

    league = db.query(League).filter_by(code=league_code).first()
    if league is None:
        return {"error": "league missing"}
    match_ids = [m.id for m in db.query(Match.id).filter_by(league_id=league.id).all()]
    eff = unknown = 0
    if match_ids:
        for model in (Lineup, MatchEvent, MatchStatistic):
            rows = db.query(model).filter(
                getattr(model, "match_id").in_(match_ids)).all()
            for row in rows:
                if getattr(row, "effective_at", None) is not None:
                    eff += 1
                else:
                    unknown += 1
    return {"strict_rows": eff, "unknown_rows": unknown,
            "note": "unknown timing stays unknown (no retroactive stamping)"}
