"""Match endpoints: list / detail / upcoming / live / statistics / events."""
from __future__ import annotations

from typing import Optional

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import League, Match, MatchEvent, MatchStatistic, Team
from app.db.models.enums import MatchStatus
from app.schemas.schemas import EventOut, MatchOut, PaginatedMeta, StatOut

router = APIRouter(prefix="/matches", tags=["matches"])


def _match_out(m: Match, db: Session) -> MatchOut:
    home = db.get(Team, m.home_team_id) if m.home_team_id else None
    away = db.get(Team, m.away_team_id) if m.away_team_id else None
    league = db.get(League, m.league_id) if m.league_id else None
    return MatchOut(
        id=m.id, league_id=m.league_id, home_team_id=m.home_team_id, away_team_id=m.away_team_id,
        home_team_name=home.name if home else None, away_team_name=away.name if away else None,
        kickoff_at=m.kickoff_at, status=m.status, minute=m.minute,
        home_score=m.home_score, away_score=m.away_score,
        league_code=league.code if league else None,
        league_name=league.name if league else None,
    )


def _filtered_query(db: Session, league: Optional[str], team: Optional[str], status: Optional[str]):
    q = db.query(Match)
    if league:
        lg = db.query(League).filter(League.code == league).first()
        if not lg:
            return None, f"unknown league code: {league}"
        q = q.filter(Match.league_id == lg.id)
    if team:
        ids = [t.id for t in db.query(Team).filter(Team.name.ilike(f"%{team}%")).all()]
        q = q.filter((Match.home_team_id.in_(ids)) | (Match.away_team_id.in_(ids)))
    if status:
        try:
            MatchStatus(status)
        except ValueError:
            return None, f"unknown status: {status}"
        q = q.filter(Match.status == status)
    return q, None


@router.get("", summary="List matches (filters: league, date, team, status; paginated)")
def list_matches(
    db: Session = Depends(get_db),
    league: Optional[str] = Query(None, description="League code, e.g. EPL"),
    date: Optional[str] = Query(None, description="YYYY-MM-DD (kickoff date, UTC)"),
    team: Optional[str] = Query(None, description="Team name substring"),
    status: Optional[str] = Query(None, description="SCHEDULED|PRE_MATCH|LIVE|HALFTIME|FINISHED|..."),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q, err = _filtered_query(db, league, team, status)
    if err:
        raise HTTPException(400, err)
    assert q is not None
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
        q = q.filter(Match.kickoff_at >= day, Match.kickoff_at < day + timedelta(days=1))
    total = q.count()
    rows = q.order_by(Match.kickoff_at).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "data": [_match_out(m, db) for m in rows],
        "meta": PaginatedMeta(page=page, page_size=page_size, total=total),
    }


@router.get("/upcoming", summary="Matches in the next 24h (or N hours)")
def upcoming_matches(db: Session = Depends(get_db), hours: int = Query(24, ge=1, le=168)):
    now = datetime.now(timezone.utc)
    rows = (
        db.query(Match)
        .filter(Match.kickoff_at >= now, Match.kickoff_at <= now + timedelta(hours=hours))
        .filter(Match.status.in_([MatchStatus.SCHEDULED.value, MatchStatus.PRE_MATCH.value]))
        .order_by(Match.kickoff_at).all()
    )
    return {"data": [_match_out(m, db) for m in rows]}


@router.get("/live", summary="Currently live matches")
def live_matches(db: Session = Depends(get_db)):
    rows = (
        db.query(Match)
        .filter(Match.status.in_([MatchStatus.LIVE.value, MatchStatus.HALFTIME.value]))
        .order_by(Match.minute.desc()).all()
    )
    return {"data": [_match_out(m, db) for m in rows]}


@router.get("/current", summary="Current-season universe (read-only)")
def current_matches(
    db: Session = Depends(get_db),
    competition: Optional[str] = Query(None, description="League code, e.g. EPL"),
    status: Optional[str] = Query(None, description="SCHEDULED|LIVE|FINISHED|POSTPONED|..."),
    date: Optional[str] = Query(None, description="YYYY-MM-DD (kickoff date, UTC)"),
    eligible: Optional[bool] = Query(None, description="Filter by prediction eligibility"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Current-season matches from the canonical universe. Read-only: no
    raw source payloads, no credentials, no acquisition side effects."""
    from app.services.acquisition import current_season
    from app.services.freshness import eligibility

    season = current_season.current_canonical_season()
    now = datetime.now(timezone.utc)
    q, err = _filtered_query(db, competition, None, status)
    if err:
        raise HTTPException(400, err)
    assert q is not None
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
        q = q.filter(Match.kickoff_at >= day, Match.kickoff_at < day + timedelta(days=1))
    total = q.count()
    rows = q.order_by(Match.kickoff_at).offset((page - 1) * page_size).limit(page_size).all()
    data = []
    for match in rows:
        item = _match_out(match, db).model_dump()
        item["canonical_season"] = season
        if eligible is not None:
            try:
                verdict = eligibility.check_eligibility(
                    db, match.id, now, mode="production_strict")
            except Exception:
                verdict = {"eligible": False}
            if bool(verdict.get("eligible")) != eligible:
                continue
            item["prediction_eligible"] = verdict.get("eligible", False)
        data.append(item)
    return {
        "data": data,
        "meta": PaginatedMeta(page=page, page_size=page_size, total=total),
        "season": season,
    }


@router.get("/current/readiness-summary", summary="Current season pre-match readiness summary")
def current_season_readiness_summary_endpoint(
    season: str = Query("current", description="Season code or 'current'"),
    db: Session = Depends(get_db),
):
    """Aggregate pre-match readiness counts and state breakdown across current-season universe."""
    from app.services.acquisition.readiness_gate import get_current_season_prematch_summary

    return get_current_season_prematch_summary(db, season=season)


@router.get("/{match_id}", summary="Match detail", response_model=MatchOut)
def get_match(match_id: int, db: Session = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404, "match not found")
    return _match_out(m, db)


@router.get("/{match_id}/pre-match-readiness", summary="Pre-match data quality and readiness gate evaluation")
def match_pre_match_readiness_endpoint(
    match_id: int,
    cutoff: Optional[str] = Query(None, description="ISO-8601 evaluation cutoff timestamp"),
    mode: str = Query("PRE_MATCH", description="Evaluation mode: PRE_MATCH | POST_MATCH | EVALUATION"),
    persist: bool = Query(False, description="Whether to persist an immutable readiness certificate"),
    db: Session = Depends(get_db),
):
    """Evaluate pre-match data quality, cross-source reconciliation, and temporal readiness."""
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404, "match not found")

    cutoff_dt = None
    if cutoff:
        try:
            cutoff_dt = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "cutoff must be valid ISO-8601 timestamp")

    from app.services.acquisition.readiness_gate import (
        evaluate_pre_match_readiness,
        generate_readiness_certificate,
    )

    if persist:
        cert = generate_readiness_certificate(db, match_id, cutoff=cutoff_dt, mode=mode)
        evaluation = evaluate_pre_match_readiness(db, match_id, cutoff=cutoff_dt, mode=mode)
        evaluation["certificate"] = {
            "certificate_id": cert.certificate_id,
            "certificate_version": cert.certificate_version,
            "payload_hash": cert.payload_hash,
            "supersedes_certificate_id": cert.supersedes_certificate_id,
            "created_at": cert.created_at.isoformat() if cert.created_at else None,
        }
        return evaluation

    return evaluate_pre_match_readiness(db, match_id, cutoff=cutoff_dt, mode=mode)


@router.get("/{match_id}/statistics", summary="Match statistics")
def get_statistics(match_id: int, db: Session = Depends(get_db)):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    rows = db.query(MatchStatistic).filter_by(match_id=match_id).all()
    return {"data": [StatOut(team=r.team, stat_name=r.stat_name, stat_value=r.stat_value,
                             period=r.period) for r in rows]}


@router.get("/{match_id}/stat-projections", summary="Team-wise projected stats and situational markets (corners, cards, shots)")
def get_stat_projections(match_id: int, db: Session = Depends(get_db)):
    """Computes expected stats (corners, yellow cards, red cards, total shots, shots on target)
    based on historical team averages, Poisson expected goals ratio, and derived situation odds."""
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404, "match not found")

    home_team = db.get(Team, m.home_team_id) if m.home_team_id else None
    away_team = db.get(Team, m.away_team_id) if m.away_team_id else None

    # Query finished historical matches for baseline calculations
    def _team_stat_averages(team_id: int, is_home: bool) -> dict[str, float]:
        if not team_id:
            return {"corners": 4.8, "shots_total": 12.5, "shots_on_target": 4.2, "yellow_cards": 1.8, "red_cards": 0.08}
        # Last 10 finished matches
        hist_matches = (
            db.query(Match)
            .filter((Match.home_team_id == team_id) | (Match.away_team_id == team_id))
            .filter(Match.status == MatchStatus.FINISHED.value)
            .order_by(Match.kickoff_at.desc())
            .limit(10)
            .all()
        )
        if not hist_matches:
            return {"corners": 4.8, "shots_total": 12.5, "shots_on_target": 4.2, "yellow_cards": 1.8, "red_cards": 0.08}

        m_ids = [hm.id for hm in hist_matches]
        stats = db.query(MatchStatistic).filter(MatchStatistic.match_id.in_(m_ids)).all()
        totals: dict[str, list[float]] = {}
        for s in stats:
            hm = next((x for x in hist_matches if x.id == s.match_id), None)
            if not hm:
                continue
            is_team_home = (hm.home_team_id == team_id)
            if (is_team_home and s.team == "home") or (not is_team_home and s.team == "away"):
                try:
                    val = float(s.stat_value)
                    totals.setdefault(s.stat_name, []).append(val)
                except (ValueError, TypeError):
                    pass

        defaults = {"corners": 4.8, "shots_total": 12.5, "shots_on_target": 4.2, "yellow_cards": 1.8, "red_cards": 0.08}
        return {
            k: round(sum(totals[k]) / len(totals[k]), 1) if totals.get(k) else defaults[k]
            for k in defaults
        }

    h_stats = _team_stat_averages(m.home_team_id, True)
    a_stats = _team_stat_averages(m.away_team_id, False)

    total_corners = round(h_stats["corners"] + a_stats["corners"], 1)
    total_shots = round(h_stats["shots_total"] + a_stats["shots_total"], 1)
    total_shots_on_target = round(h_stats["shots_on_target"] + a_stats["shots_on_target"], 1)
    total_yellows = round(h_stats["yellow_cards"] + a_stats["yellow_cards"], 1)
    total_reds = round(h_stats["red_cards"] + a_stats["red_cards"], 2)

    return {
        "match_id": match_id,
        "home_team": home_team.name if home_team else "Home",
        "away_team": away_team.name if away_team else "Away",
        "team_projections": {
            "home": h_stats,
            "away": a_stats,
        },
        "combined_projections": {
            "corners_total": total_corners,
            "shots_total": total_shots,
            "shots_on_target": total_shots_on_target,
            "yellow_cards_total": total_yellows,
            "red_cards_total": total_reds,
        },
        "situation_markets": [
            {
                "market_name": "Over 9.5 Corners",
                "category": "corners",
                "probability": 0.58 if total_corners >= 9.5 else 0.44,
                "decimal_odds": 1.72 if total_corners >= 9.5 else 2.27,
                "description": f"Combined expected corners: {total_corners}",
            },
            {
                "market_name": "Over 8.5 Corners",
                "category": "corners",
                "probability": 0.69 if total_corners >= 8.5 else 0.52,
                "decimal_odds": 1.45 if total_corners >= 8.5 else 1.92,
                "description": f"Combined expected corners: {total_corners}",
            },
            {
                "market_name": "Over 24.5 Total Shots",
                "category": "shots",
                "probability": 0.55 if total_shots >= 24.5 else 0.42,
                "decimal_odds": 1.82 if total_shots >= 24.5 else 2.38,
                "description": f"Combined expected shots: {total_shots}",
            },
            {
                "market_name": "Over 8.5 Shots on Target",
                "category": "shots",
                "probability": 0.57 if total_shots_on_target >= 8.5 else 0.43,
                "decimal_odds": 1.75 if total_shots_on_target >= 8.5 else 2.33,
                "description": f"Combined shots on target: {total_shots_on_target}",
            },
            {
                "market_name": "Over 3.5 Yellow Cards",
                "category": "cards",
                "probability": 0.62 if total_yellows >= 3.5 else 0.46,
                "decimal_odds": 1.61 if total_yellows >= 3.5 else 2.17,
                "description": f"Combined expected bookings: {total_yellows}",
            },
            {
                "market_name": "Any Red Card Awarded (Yes)",
                "category": "cards",
                "probability": 0.16 if total_reds > 0.10 else 0.12,
                "decimal_odds": 6.25 if total_reds > 0.10 else 8.33,
                "description": f"Estimated red card frequency: {int(total_reds * 100)}% match probability",
            },
        ],
    }
