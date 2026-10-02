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


_last_live_sync_at = 0.0


def _refresh_live_matches_if_needed(db: Session, max_age_seconds: int = 45):
    """Sync live scores, elapsed minute, and status on-demand from API-Football."""
    global _last_live_sync_at
    import time
    now_ts = time.time()
    if now_ts - _last_live_sync_at < max_age_seconds:
        return
    _last_live_sync_at = now_ts
    try:
        import urllib.request, json
        url = "https://v3.football.api-sports.io/fixtures?live=all"
        headers = {"x-apisports-key": "f1da5a48dd4965ed81ed9444e8191ce4"}
        req = urllib.request.Request(url, headers=headers)
        active_live_fids = set()
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            live_items = data.get("response", [])
            for it in live_items:
                fid = str(it.get("fixture", {}).get("id"))
                active_live_fids.add(fid)
                status_short = it.get("fixture", {}).get("status", {}).get("short")
                elapsed = it.get("fixture", {}).get("status", {}).get("elapsed")
                goals = it.get("goals", {})
                h_score = goals.get("home")
                a_score = goals.get("away")

                m = db.query(Match).filter_by(provider_match_id=fid).first()
                if m:
                    if status_short in ("FT", "AET", "PEN"):
                        m.status = MatchStatus.FINISHED.value
                        m.minute = 90
                    elif status_short == "HT":
                        m.status = MatchStatus.HALFTIME.value
                        m.minute = 45
                    elif status_short in ("1H", "2H", "ET", "LIVE"):
                        m.status = MatchStatus.LIVE.value
                        m.minute = elapsed
                    if h_score is not None and a_score is not None:
                        m.home_score = h_score
                        m.away_score = a_score

        # Detect finished matches that API-Football dropped from ?live=all
        now_utc = datetime.now(timezone.utc)
        stale_live = db.query(Match).filter(Match.status.in_((MatchStatus.LIVE.value, MatchStatus.HALFTIME.value))).all()
        for sm in stale_live:
            sm_fid = str(sm.provider_match_id) if sm.provider_match_id else None
            if sm_fid and sm_fid not in active_live_fids:
                try:
                    single_url = f"https://v3.football.api-sports.io/fixtures?id={sm_fid}"
                    s_req = urllib.request.Request(single_url, headers=headers)
                    with urllib.request.urlopen(s_req, timeout=3) as s_resp:
                        s_data = json.loads(s_resp.read().decode())
                        s_items = s_data.get("response", [])
                        if s_items:
                            s_it = s_items[0]
                            s_status = s_it.get("fixture", {}).get("status", {}).get("short")
                            s_goals = s_it.get("goals", {})
                            if s_status in ("FT", "AET", "PEN"):
                                sm.status = MatchStatus.FINISHED.value
                                sm.minute = 90
                            elif s_status in ("PST", "CANC", "ABD"):
                                sm.status = MatchStatus.POSTPONED.value
                            if s_goals.get("home") is not None and s_goals.get("away") is not None:
                                sm.home_score = s_goals.get("home")
                                sm.away_score = s_goals.get("away")
                        else:
                            if sm.kickoff_at and (now_utc - sm.kickoff_at).total_seconds() >= 105 * 60:
                                sm.status = MatchStatus.FINISHED.value
                                sm.minute = 90
                except Exception:
                    if sm.kickoff_at and (now_utc - sm.kickoff_at).total_seconds() >= 105 * 60:
                        sm.status = MatchStatus.FINISHED.value
                        sm.minute = 90
            elif sm.kickoff_at and (now_utc - sm.kickoff_at).total_seconds() >= 125 * 60:
                sm.status = MatchStatus.FINISHED.value
                sm.minute = 90

        db.commit()
    except Exception:
        pass


@router.get("", summary="List matches (filters: league, date, team, status; paginated)")
def list_matches(
    db: Session = Depends(get_db),
    league: Optional[str] = Query(None, description="League code, e.g. EPL"),
    date: Optional[str] = Query(None, description="YYYY-MM-DD (kickoff date, UTC)"),
    team: Optional[str] = Query(None, description="Team name substring"),
    status: Optional[str] = Query(None, description="SCHEDULED|PRE_MATCH|LIVE|HALFTIME|FINISHED|..."),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_order: str = Query("asc", description="Sort order by kickoff_at: asc | desc"),
):
    if not status or status.upper() in ("LIVE", "HALFTIME"):
        _refresh_live_matches_if_needed(db)

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
    order_clause = Match.kickoff_at.desc() if sort_order.lower() == "desc" else Match.kickoff_at.asc()
    rows = q.order_by(order_clause).offset((page - 1) * page_size).limit(page_size).all()
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
    _refresh_live_matches_if_needed(db)
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


def _compute_stat_projections_data(db: Session, m: Match) -> dict:
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
        "match_id": m.id,
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


@router.get("/{match_id}/stat-projections", summary="Team-wise projected stats and situational markets (corners, cards, shots)")
def get_stat_projections(match_id: int, db: Session = Depends(get_db)):
    """Computes expected stats (corners, yellow cards, red cards, total shots, shots on target)
    based on historical team averages, Poisson expected goals ratio, and derived situation odds."""
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404, "match not found")
    return _compute_stat_projections_data(db, m)


@router.get("/{match_id}/stat-comparison", summary="Side-by-side comparison of original match results vs engine & Mirofish prediction")
def get_match_stat_comparison(match_id: int, db: Session = Depends(get_db)):
    """Comprehensive side-by-side comparison between original match results/data and
    the predictive model engine & Mirofish qualitative AI simulation."""
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404, "match not found")

    home_team = db.get(Team, m.home_team_id) if m.home_team_id else None
    away_team = db.get(Team, m.away_team_id) if m.away_team_id else None
    home_name = home_team.name if home_team else "Home"
    away_name = away_team.name if away_team else "Away"

    is_finished = (m.status == MatchStatus.FINISHED.value)
    has_score = (m.home_score is not None and m.away_score is not None)

    # 1. Fetch Engine & Mirofish intelligence
    from app.services.match_intelligence.service import build_match_intelligence
    try:
        intel = build_match_intelligence(db, match_id)
    except Exception:
        intel = {}

    core_pred = intel.get("core_prediction") or {}
    exp_goals = intel.get("expected_goals") or {}
    derived = intel.get("derived_markets") or {}
    totals = derived.get("totals") or {}
    btts_dict = derived.get("btts") or {}
    correct_scores = (intel.get("correct_score") or {}).get("top_scores") or []
    mirofish_sec = intel.get("mirofish") or {}

    def _safe_float(val, default):
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    p_h = _safe_float(core_pred.get("home"), 0.33)
    p_d = _safe_float(core_pred.get("draw"), 0.33)
    p_a = _safe_float(core_pred.get("away"), 0.33)
    sum_p = p_h + p_d + p_a
    if sum_p > 0:
        p_h, p_d, p_a = p_h / sum_p, p_d / sum_p, p_a / sum_p

    pred_outcome = "home" if p_h >= max(p_d, p_a) else ("draw" if p_d >= p_a else "away")
    pred_outcome_label = f"{home_name} Win" if pred_outcome == "home" else (f"{away_name} Win" if pred_outcome == "away" else "Draw")

    xg_h = round(_safe_float(exp_goals.get("home_lambda"), 1.35), 2)
    xg_a = round(_safe_float(exp_goals.get("away_lambda"), 1.10), 2)
    xg_tot = round(xg_h + xg_a, 2)

    over_2_5_prob = round(_safe_float(totals.get("over_2_5"), 0.50) * 100, 1)
    btts_yes_prob = round(_safe_float(btts_dict.get("yes"), 0.50) * 100, 1)
    top_score_pred = correct_scores[0].get("score") if correct_scores else f"{round(xg_h)}-{round(xg_a)}"

    # Projections for situational stats
    proj_data = _compute_stat_projections_data(db, m)
    comb_proj = proj_data["combined_projections"]
    team_proj = proj_data["team_projections"]

    # 2. Fetch actual statistics from MatchStatistic table
    stats_rows = db.query(MatchStatistic).filter_by(match_id=match_id).all()
    if not stats_rows and is_finished and m.provider_match_id:
        try:
            import urllib.request, json
            url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={m.provider_match_id}"
            headers = {"x-apisports-key": "f1da5a48dd4965ed81ed9444e8191ce4"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                resp_data = data.get("response", [])
                if len(resp_data) >= 2:
                    stat_map = {
                        "Total Shots": "shots_total",
                        "Shots on Goal": "shots_on_target",
                        "Corner Kicks": "corners",
                        "Ball Possession": "possession",
                        "Yellow Cards": "yellow_cards",
                        "Red Cards": "red_cards",
                        "Fouls": "fouls",
                        "expected_goals": "xg",
                    }
                    for idx, team_data in enumerate(resp_data):
                        team_role = "home" if idx == 0 else "away"
                        for item in team_data.get("statistics", []):
                            st_type = item.get("type")
                            raw_val = item.get("value")
                            if st_type in stat_map and raw_val is not None:
                                canonical_name = stat_map[st_type]
                                val_str = str(raw_val).replace("%", "")
                                stat_obj = MatchStatistic(
                                    match_id=m.id,
                                    team=team_role,
                                    stat_name=canonical_name,
                                    stat_value=val_str,
                                    period="full",
                                    source="api_football",
                                    source_record_id=f"{m.provider_match_id}_{team_role}_{canonical_name}",
                                )
                                db.add(stat_obj)
                    db.commit()
                    stats_rows = db.query(MatchStatistic).filter_by(match_id=match_id).all()
        except Exception:
            pass

    # 3. Delegate to comprehensive 44+ market comparison generator
    from app.services.predictions.market_comparisons import generate_market_comparisons
    return generate_market_comparisons(
        db=db,
        m=m,
        home_name=home_name,
        away_name=away_name,
        intel=intel,
        proj_data=proj_data,
        stats_rows=stats_rows,
    )



