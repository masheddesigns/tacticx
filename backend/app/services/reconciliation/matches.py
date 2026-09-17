"""Match reconciliation across sources (Phase 8).

For each source match: resolve league/season/teams/kickoff/status against
canonical records using existing deterministic matching (MatchResolver with
kickoff tolerance, same-day fallback). Field-by-field comparison emits typed
conflicts; low-risk differences auto-resolve, score/kickoff conflicts stay
visible. No new fuzzy matching without tests.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.core import League, Match
from app.services.reconciliation import conflicts as conflict_svc


def _same_score(match: Match, home: Optional[int], away: Optional[int]) -> Optional[bool]:
    if home is None or away is None:
        return None
    if match.home_score is None or match.away_score is None:
        return None
    return (match.home_score, match.away_score) == (home, away)


def reconcile_match(db: Session, canonical_id: int, source: str,
                    observed: Dict, dry_run: bool = False) -> Dict:
    """Compare one source observation against the canonical match.

    observed keys: league_code, home_team_id, away_team_id, kickoff_at,
    status, home_score, away_score, source_match_id.
    Returns {agreements, conflicts, auto_resolved}. In dry-run nothing is
    persisted.
    """
    match = db.get(Match, canonical_id)
    if match is None:
        return {"error": "canonical match missing", "agreements": [], "conflicts": []}
    tolerance_minutes = get_settings().MATCH_KICKOFF_TOLERANCE_MINUTES
    agreements, found = [], []

    def emit(conflict_type: str, field: str, value_a, value_b,
             classification: Optional[str] = None):
        entry = {"type": conflict_type, "field": field,
                 "canonical": value_a, "observed": value_b}
        auto = conflict_svc.auto_resolvable(conflict_type, value_a, value_b)
        if auto is not None:
            entry["auto_resolution"] = auto
        if not dry_run:
            row = conflict_svc.record_conflict(
                db, "match", canonical_id, conflict_type, field,
                "canonical", source, value_a, value_b,
                classification=classification,
                resolution_status=auto or conflict_svc.STATUS_UNRESOLVED,
                resolved_by="auto:low-risk" if auto else "")
            entry["conflict_id"] = row.id
            entry["severity"] = row.severity
            entry["status"] = row.resolution_status
        found.append(entry)
        return entry

    # League / season.
    if observed.get("league_code"):
        league = db.get(League, match.league_id) if match.league_id else None
        if league is not None and league.code != observed["league_code"]:
            emit("league_mismatch", "league", league.code, observed["league_code"])
        else:
            agreements.append("league")
    # Teams.
    for side, attr in (("home_team_id", "home_team_id"), ("away_team_id", "away_team_id")):
        if observed.get(side) is not None and getattr(match, attr) != observed[side]:
            emit("team_mismatch", attr, getattr(match, attr), observed[side])
        elif observed.get(side) is not None:
            agreements.append(attr)
    # Kickoff with configurable tolerance; 6h+ never silently merges.
    if observed.get("kickoff_at") is not None and match.kickoff_at is not None:
        try:
            delta_min = abs((match.kickoff_at.replace(tzinfo=None)
                             - observed["kickoff_at"].replace(tzinfo=None)
                             ).total_seconds()) / 60.0
        except Exception:
            delta_min = None
        if delta_min is None or delta_min > tolerance_minutes:
            emit("kickoff_mismatch", "kickoff_at", str(match.kickoff_at),
                 str(observed["kickoff_at"]))
            if delta_min is not None and delta_min > 360:
                found[-1]["note"] = (f"{delta_min / 60:.1f}h apart: never merged, "
                                     "conflict stays open")
        else:
            agreements.append("kickoff")
    # Status.
    if observed.get("status") and match.status != observed["status"]:
        emit("status_mismatch", "status", match.status, observed["status"])
    elif observed.get("status"):
        agreements.append("status")
    # Score (critical).
    same = _same_score(match, observed.get("home_score"), observed.get("away_score"))
    if same is False:
        emit("score_mismatch", "score",
             f"{match.home_score}-{match.away_score}",
             f"{observed.get('home_score')}-{observed.get('away_score')}")
    elif same is True:
        agreements.append("score")
    return {"canonical_id": canonical_id, "source": source,
            "agreements": agreements, "conflicts": found,
            "dry_run": dry_run}


def reconcile_league(db: Session, league_code: Optional[str] = None,
                     season: Optional[str] = None, limit: int = 500,
                     dry_run: bool = False) -> Dict:
    """Bounded batch: group canonical matches by (league, home, away) and
    compare near-duplicate rows pairwise (separate rows per source ingestion).
    Groups are small; candidate generation uses team/league filters, never
    O(n^2) over the table. Scores/kickoffs/status across rows become typed
    conflicts instead of silent duplicates."""
    from collections import defaultdict

    tolerance_minutes = get_settings().MATCH_KICKOFF_TOLERANCE_MINUTES
    query = db.query(Match).filter(Match.home_team_id.is_not(None),
                                   Match.away_team_id.is_not(None))
    if league_code:
        league = db.query(League).filter_by(code=league_code).first()
        if league is None:
            return {"error": f"unknown league: {league_code}"}
        query = query.filter(Match.league_id == league.id)
    rows = query.order_by(Match.id.asc()).limit(max(1, limit)).all()
    groups: Dict[tuple, list] = defaultdict(list)
    for match in rows:
        groups[(match.league_id, match.home_team_id, match.away_team_id,
                _season_label(match.kickoff_at))].append(match)
    summary = {"matches": len(rows), "groups": len(groups),
               "multi_row_groups": 0, "agreements": 0, "conflicts": 0,
               "dry_run": dry_run}
    for key, members in groups.items():
        if len(members) < 2:
            continue
        summary["multi_row_groups"] += 1
        members.sort(key=lambda m: (m.kickoff_at is None, m.kickoff_at, m.id))
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                result = _compare_rows(db, members[i], members[j],
                                       tolerance_minutes, dry_run=dry_run)
                summary["agreements"] += len(result.get("agreements", []))
                summary["conflicts"] += len(result.get("conflicts", []))
    return summary


def _season_label(kickoff_at) -> str:
    """Season bucket (Aug-Jul) so cross-season same-fixture rows never
    compare as duplicates. Unknown kickoff -> 'unknown' (compared only
    with each other, never merged silently)."""
    try:
        naive = kickoff_at.replace(tzinfo=None) if kickoff_at.tzinfo else kickoff_at
        return str(naive.year if naive.month >= 8 else naive.year - 1)
    except Exception:
        return "unknown"


def _compare_rows(db: Session, a: Match, b: Match, tolerance_minutes: int,
                  dry_run: bool = False) -> Dict:
    """Pairwise comparison of two same-fixture rows from different sources."""
    primary, secondary = (a, b) if a.id < b.id else (b, a)
    observed = {
        "league_code": None,
        "home_team_id": secondary.home_team_id,
        "away_team_id": secondary.away_team_id,
        "kickoff_at": secondary.kickoff_at,
        "status": secondary.status,
        "home_score": secondary.home_score,
        "away_score": secondary.away_score,
        "source_match_id": secondary.provider_match_id,
    }
    result = reconcile_match(db, primary.id, secondary.provider or "unknown",
                             observed, dry_run=dry_run)
    if (primary.provider or "") != (secondary.provider or ""):
        result.setdefault("sources", [primary.provider, secondary.provider])
    else:
        # Same provider, two rows: duplicate source record.
        if not dry_run:
            row = conflict_svc.record_conflict(
                db, "match", primary.id, "duplicate_source_match",
                "provider_match_id", primary.provider or "",
                secondary.provider or "",
                primary.provider_match_id, secondary.provider_match_id)
            result["conflicts"].append({"type": "duplicate_source_match",
                                        "conflict_id": row.id,
                                        "severity": row.severity})
        else:
            result["conflicts"].append({"type": "duplicate_source_match",
                                        "severity": "medium"})
    return result
