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
    return MatchOut(
        id=m.id, league_id=m.league_id, home_team_id=m.home_team_id, away_team_id=m.away_team_id,
        home_team_name=home.name if home else None, away_team_name=away.name if away else None,
        kickoff_at=m.kickoff_at, status=m.status, minute=m.minute,
        home_score=m.home_score, away_score=m.away_score,
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


@router.get("/{match_id}/events", summary="Match events")
def get_events(match_id: int, db: Session = Depends(get_db)):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    rows = db.query(MatchEvent).filter_by(match_id=match_id).order_by(MatchEvent.minute).all()
    return {"data": [EventOut(minute=r.minute, event_type=r.event_type, detail=r.detail,
                              team=r.team, player_name=r.player_name) for r in rows]}
