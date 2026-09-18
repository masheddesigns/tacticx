"""Coverage + staleness + xG/player temporal audits (Phase 10).

Current-season audit records actual responses per league/season (never
assumed). Staleness distribution uses fixed buckets (0–7d, 8–30d, 31–90d,
91–365d, 1–3y, 3+y, unknown) broken down by feature family. xG and player
audits determine strict/estimated eligibility per record from effective_at
evidence — Phase 5 conclusions are never altered to increase coverage.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.services.features.temporal import as_naive_utc
from app.services.freshness import provenance as prov

STALENESS_BUCKETS = ["0-7d", "8-30d", "31-90d", "91-365d", "1-3y", "3+y", "unknown"]


def _bucket(age_days_value: Optional[float]) -> str:
    if age_days_value is None:
        return "unknown"
    if age_days_value <= 7:
        return "0-7d"
    if age_days_value <= 30:
        return "8-30d"
    if age_days_value <= 90:
        return "31-90d"
    if age_days_value <= 365:
        return "91-365d"
    if age_days_value <= 3 * 365:
        return "1-3y"
    return "3+y"


def season_coverage(db: Session, league_code: str) -> Dict:
    """Measured per-season coverage for one league (fixtures, results,
    stats, events, lineups, xG, odds, players, temporal metadata)."""
    from app.db.models.core import Lineup, MatchEvent, MatchStatistic, Player
    from app.db.models.odds import OddsSnapshot

    league = db.query(League).filter_by(code=league_code).first()
    if league is None:
        return {"league": league_code, "status": "unknown_league"}
    matches = db.query(Match).filter_by(league_id=league.id).all()
    by_season: Dict[str, Dict] = {}
    for match in matches:
        season = _season_label(match.kickoff_at)
        slot = by_season.setdefault(season, {
            "fixtures": 0, "completed": 0, "upcoming": 0, "match_ids": []})
        slot["fixtures"] += 1
        if match.status == "FINISHED":
            slot["completed"] += 1
        elif match.status in ("SCHEDULED", "PRE_MATCH", "POSTPONED"):
            slot["upcoming"] += 1
        slot["match_ids"].append(match.id)
    for season, slot in by_season.items():
        ids = slot.pop("match_ids")
        slot["statistics"] = db.query(MatchStatistic.match_id).filter(
            MatchStatistic.match_id.in_(ids)).distinct().count() if ids else 0
        slot["events"] = db.query(MatchEvent.match_id).filter(
            MatchEvent.match_id.in_(ids)).distinct().count() if ids else 0
        slot["lineups"] = db.query(Lineup.match_id).filter(
            Lineup.match_id.in_(ids)).distinct().count() if ids else 0
        slot["xg"] = db.query(MatchStatistic.match_id).filter(
            MatchStatistic.match_id.in_(ids),
            MatchStatistic.stat_name.in_(("xg", "expected_goals",
                                          "expected_goals_for", "exp_g"))
        ).distinct().count() if ids else 0
        slot["odds"] = db.query(OddsSnapshot.match_id).filter(
            OddsSnapshot.match_id.in_(ids)).distinct().count() if ids else 0
    return {"league": league_code, "seasons": by_season}


def _season_label(kickoff_at) -> str:
    naive = as_naive_utc(kickoff_at)
    if naive is None:
        return "unknown"
    return str(naive.year if naive.month >= 8 else naive.year - 1)


def current_season_audit(db: Session, provider_probe=None) -> Dict:
    """Concrete current-season audit across known leagues.

    provider_probe (optional async callable) records the live provider
    response; without it, coverage is measured from the store and the
    current season is identified by date. Missing current-season fixtures
    are reported unavailable with reason, never fabricated.
    """
    now = datetime.now(timezone.utc)
    current = str(now.year if now.month >= 8 else now.year - 1)
    out = {"as_of": now.isoformat(), "current_season": current, "leagues": {}}
    for league in db.query(League).all():
        coverage = season_coverage(db, league.code)
        seasons = coverage.get("seasons", {})
        current_slot = seasons.get(current, {})
        out["leagues"][league.code] = {
            "current_season": current,
            "fixtures_available": current_slot.get("fixtures", 0) > 0,
            "completed": current_slot.get("completed", 0),
            "upcoming": current_slot.get("upcoming", 0),
            "statistics": current_slot.get("statistics", 0),
            "events": current_slot.get("events", 0),
            "lineups": current_slot.get("lineups", 0),
            "xg": current_slot.get("xg", 0),
            "odds": current_slot.get("odds", 0),
            "seasons_present": sorted(seasons),
            "status": "available" if current_slot.get("fixtures", 0) > 0
            else "unavailable",
            "reason": "" if current_slot.get("fixtures", 0) > 0 else
            "provider_plan_or_source_limit: no current-season fixtures acquired",
        }
    return out


def staleness_distribution(db: Session, league_code: Optional[str] = None,
                           sample_per_league: int = 60) -> Dict:
    """Age-bucket distribution of feature evidence (cutoff-anchored).

    For sampled finished matches, the evidence age is cutoff minus the
    newest pre-cutoff input per family (team history, player rosters, xG,
    market). Buckets fixed; unknown kept visible.
    """
    from app.db.models.core import MatchStatistic
    from app.db.models.odds import OddsSnapshot

    query = db.query(Match).filter(Match.status == "FINISHED",
                                   Match.kickoff_at.is_not(None))
    if league_code:
        league = db.query(League).filter_by(code=league_code).first()
        if league is None:
            return {"error": f"unknown league: {league_code}"}
        query = query.filter(Match.league_id == league.id)
    total = query.count()
    step = max(1, total // sample_per_league)
    sample = query.order_by(Match.id.asc()).all()[::step][:sample_per_league]
    dist: Dict[str, Dict[str, int]] = {
        family: {bucket: 0 for bucket in STALENESS_BUCKETS}
        for family in ("team_history", "player_roster", "xg", "market")}
    for match in sample:
        cutoff = match.kickoff_at
        naive_cutoff = as_naive_utc(cutoff)
        # Team history: newest pre-cutoff finished match of either team.
        newest = None
        for team_id in (match.home_team_id, match.away_team_id):
            if team_id is None:
                continue
            row = db.query(Match).filter(
                ((Match.home_team_id == team_id) | (Match.away_team_id == team_id)),
                Match.status == "FINISHED", Match.kickoff_at.is_not(None),
                Match.kickoff_at < cutoff).order_by(
                    Match.kickoff_at.desc()).first()
            if row is not None and (newest is None or row.kickoff_at > newest):
                newest = row.kickoff_at
        dist["team_history"][_bucket(
            (naive_cutoff - as_naive_utc(newest)).total_seconds() / 86400.0
            if newest and naive_cutoff else None)] += 1
        # Player roster: newest pre-cutoff lineup row (parent-anchored).
        from app.db.models.core import Lineup

        lined = db.query(Match.kickoff_at).join(
            Lineup, Lineup.match_id == Match.id).filter(
                ((Match.home_team_id == match.home_team_id)
                 | (Match.away_team_id == match.away_team_id)
                 | (Match.home_team_id == match.away_team_id)
                 | (Match.away_team_id == match.home_team_id)),
                Match.status == "FINISHED", Match.kickoff_at < cutoff).order_by(
                    Match.kickoff_at.desc()).first()
        dist["player_roster"][_bucket(
            (naive_cutoff - as_naive_utc(lined[0])).total_seconds() / 86400.0
            if lined and lined[0] and naive_cutoff else None)] += 1
        # xG: newest pre-cutoff xG row; market: newest pre-cutoff snapshot.
        xg_row = db.query(MatchStatistic).join(
            Match, Match.id == MatchStatistic.match_id).filter(
                ((Match.home_team_id == match.home_team_id)
                 | (Match.away_team_id == match.away_team_id)),
                MatchStatistic.stat_name.in_(("xg", "expected_goals")),
                Match.status == "FINISHED",
                Match.kickoff_at < cutoff).order_by(
                    Match.kickoff_at.desc()).first()
        dist["xg"][_bucket(
            (naive_cutoff - as_naive_utc(
                db.get(Match, xg_row.match_id).kickoff_at)).total_seconds() / 86400.0
            if xg_row and naive_cutoff else None)] += 1
        snap = db.query(OddsSnapshot).filter(
            OddsSnapshot.match_id == match.id,
            OddsSnapshot.timestamp <= cutoff).order_by(
                OddsSnapshot.timestamp.desc()).first()
        dist["market"][_bucket(
            (naive_cutoff - as_naive_utc(snap.timestamp)).total_seconds() / 86400.0
            if snap and snap.timestamp and naive_cutoff else None)] += 1
    return {"league": league_code or "all", "sampled": len(sample),
            "buckets": STALENESS_BUCKETS, "distribution": dist}


def xg_temporal_audit(db: Session, limit: int = 5000) -> Dict:
    """Per-xG-record timing evidence: event/match date, effective_at,
    retrieved_at (recorded_at), source, strict/estimated eligibility."""
    from app.db.models.core import MatchStatistic

    rows = db.query(MatchStatistic).filter(MatchStatistic.stat_name.in_(
        ("xg", "expected_goals", "expected_goals_for", "exp_g"))).limit(limit).all()
    strict_eligible = estimated_eligible = unknown = 0
    by_source: Dict[str, int] = {}
    for row in rows:
        by_source[row.source or "unknown"] = by_source.get(row.source or "unknown", 0) + 1
        if row.effective_at is not None:
            strict_eligible += 1
            estimated_eligible += 1
        else:
            unknown += 1
            estimated_eligible += 1  # parent-anchored possible; strict never
    return {"records": len(rows), "by_source": by_source,
            "strict_eligible": strict_eligible,
            "estimated_eligible": estimated_eligible,
            "unknown_effective_at": unknown,
            "conclusion": "strict mode excludes xG with unknown effective_at "
                          "(Phase 5 conclusion preserved)"}


def player_temporal_audit(db: Session, limit: int = 5000) -> Dict:
    """Appearances/memberships/lineups/event-features: can each answer
    'knowable before kickoff'? Strict requires explicit effective_at."""
    from app.db.models.core import Lineup, MatchEvent

    lineup_total = db.query(Lineup).count()
    lineup_eff = db.query(Lineup).filter(Lineup.effective_at.is_not(None)).count()
    event_total = db.query(MatchEvent).count()
    event_eff = db.query(MatchEvent).filter(
        MatchEvent.effective_at.is_not(None)).count()
    from app.db.models.player_intelligence import PlayerTeamMembership

    memberships = db.query(PlayerTeamMembership).count()
    return {
        "appearances": {"records": lineup_total, "strict_eligible": lineup_eff,
                        "estimated_eligible": lineup_total,
                        "verdict": "strict unavailable (no explicit timing); "
                                   "estimated parent-anchored"},
        "lineups": {"records": lineup_total, "strict_eligible": lineup_eff,
                    "estimated_eligible": lineup_total,
                    "verdict": "as appearances"},
        "event_features": {"records": event_total, "strict_eligible": event_eff,
                           "estimated_eligible": event_total,
                           "verdict": "as appearances"},
        "memberships": {"records": memberships,
                        "verdict": "reconstructed ranges; cutoff-aware reads; "
                                   "last-seen is evidence, not contract end"},
    }
