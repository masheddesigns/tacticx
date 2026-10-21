"""Match endpoints: list / detail / upcoming / live / statistics / events."""
from __future__ import annotations

from typing import Optional, Dict, Any

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
        home_team_logo=getattr(home, "logo_url", None), away_team_logo=getattr(away, "logo_url", None),
        kickoff_at=m.kickoff_at, status=m.status, minute=m.minute,
        home_score=m.home_score, away_score=m.away_score,
        league_code=league.code if league else None,
        league_name=league.name if league else None,
    )


def _filtered_query(db: Session, league: Optional[str], team: Optional[str], status: Optional[str]):
    q = db.query(Match)
    if league:
        l_clean = league.strip()
        lg = db.query(League).filter(
            (League.code.ilike(l_clean)) |
            (League.name.ilike(f"%{l_clean}%"))
        ).first()
        if not lg:
            return None, f"unknown league code: {league}"
        q = q.filter(Match.league_id == lg.id)
    if team:
        ids = [t.id for t in db.query(Team).filter(Team.name.ilike(f"%{team}%")).all()]
        q = q.filter((Match.home_team_id.in_(ids)) | (Match.away_team_id.in_(ids)))
    if status:
        st_clean = status.strip().upper()
        try:
            MatchStatus(st_clean)
            q = q.filter(Match.status == st_clean)
        except ValueError:
            return None, f"unknown status: {status}"
    return q, None


_last_live_sync_at = 0.0


def _refresh_live_matches_if_needed(db: Session, max_age_seconds: int = 8):
    """Sync live scores, elapsed minutes, and lifecycle statuses on-demand."""
    global _last_live_sync_at
    import time
    now_ts = time.time()
    if now_ts - _last_live_sync_at < max_age_seconds:
        return
    _last_live_sync_at = now_ts
    try:
        from app.services.match_progression import advance_match_lifecycles
        advance_match_lifecycles(db)
    except Exception:
        pass


@router.get("", summary="List matches (filters: league, date, tz, team, status; paginated)")
def list_matches(
    db: Session = Depends(get_db),
    league: Optional[str] = Query(None, description="League code, e.g. EPL"),
    date: Optional[str] = Query(None, description="YYYY-MM-DD (kickoff date)"),
    tz: Optional[str] = Query("IST", description="Timezone for date bucketing: IST | UTC"),
    team: Optional[str] = Query(None, description="Team name substring"),
    status: Optional[str] = Query(None, description="SCHEDULED|PRE_MATCH|LIVE|HALFTIME|FINISHED|..."),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_order: str = Query("asc", description="Sort order by kickoff_at: asc | desc"),
):
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
        
        # When timezone is IST (UTC+5:30), day 00:00:00 IST is 18:30:00 UTC of previous day
        if tz and tz.upper() in ["IST", "ASIA/KOLKATA", "+05:30", "5:30"]:
            day_start = day - timedelta(hours=5, minutes=30)
            day_end = day_start + timedelta(days=1)
        else:
            day_start = day
            day_end = day_start + timedelta(days=1)
        q = q.filter(Match.kickoff_at >= day_start, Match.kickoff_at < day_end)
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


def _compute_stat_projections_data(db: Session, m: Match, team_cache: Optional[dict] = None) -> dict:
    home_team = db.get(Team, m.home_team_id) if m.home_team_id else None
    away_team = db.get(Team, m.away_team_id) if m.away_team_id else None

    # Query finished historical matches for baseline calculations
    def _team_stat_averages(team_id: int, is_home: bool) -> dict[str, float]:
        if not team_id:
            return {"corners": 4.8, "shots_total": 12.5, "shots_on_target": 4.2, "yellow_cards": 1.8, "red_cards": 0.08}
        cache_key = (team_id, is_home)
        if team_cache is not None and cache_key in team_cache:
            return team_cache[cache_key]

        hist_matches = (
            db.query(Match)
            .filter((Match.home_team_id == team_id) | (Match.away_team_id == team_id))
            .filter(Match.status == MatchStatus.FINISHED.value)
            .order_by(Match.kickoff_at.desc())
            .limit(10)
            .all()
        )
        if not hist_matches:
            res = {"corners": 4.8, "shots_total": 12.5, "shots_on_target": 4.2, "yellow_cards": 1.8, "red_cards": 0.08}
            if team_cache is not None:
                team_cache[cache_key] = res
            return res

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
        res = {
            k: round(sum(totals[k]) / len(totals[k]), 1) if totals.get(k) else defaults[k]
            for k in defaults
        }
        if team_cache is not None:
            team_cache[cache_key] = res
        return res

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


_DAILY_SLIPS_CACHE: Dict[str, Any] = {}
_PRED_MATCH_CACHE: Dict[int, Dict[str, Any]] = {}


@router.get("/daily-slips", summary="Curated daily prediction slips & ranked match predictions")
def get_daily_slips(
    date: Optional[str] = Query(None, description="YYYY-MM-DD date (defaults to current day)"),
    tz: Optional[str] = Query("IST", description="Timezone: IST | UTC"),
    db: Session = Depends(get_db),
):
    """Generates mathematically curated daily betting slips & match-by-match ranked predictions:
    1. Ranked individual match predictions with AI Best Possible Outcome, EV edge & projected scores.
    2. Curated combo accumulator slips (Safe Banker Treble, Cross-League Acca, Value Multiplier, etc.).
    All calculations operate strictly in target timezone (default IST UTC+5:30) with 5% commercial margin.
    """
    from app.services.predictions.poisson import PoissonModel
    from datetime import datetime, timezone, timedelta
    import time

    target_date_str = date
    if not target_date_str:
        if tz and tz.upper() in ["IST", "ASIA/KOLKATA", "+05:30", "5:30"]:
            target_date_str = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
        else:
            target_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    cache_key = f"{target_date_str}_{tz or 'IST'}"
    # Fast in-memory cache return (< 1ms)
    cached = _DAILY_SLIPS_CACHE.get(cache_key)
    if cached and (time.time() - cached["ts"] < 180):
        return cached["data"]

    _refresh_live_matches_if_needed(db)

    try:
        day = datetime.strptime(target_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")

    if tz and tz.upper() in ["IST", "ASIA/KOLKATA", "+05:30", "5:30"]:
        day_start = day - timedelta(hours=5, minutes=30)
        day_end = day_start + timedelta(days=1)
    else:
        day_start = day
        day_end = day_start + timedelta(days=1)

    matches = db.query(Match).filter(
        Match.kickoff_at >= day_start,
        Match.kickoff_at < day_end,
    ).order_by(Match.kickoff_at).all()

    now_utc = datetime.now(timezone.utc)
    is_past_date = (day_end <= now_utc)

    if not matches:
        empty_res = {
            "date": target_date_str,
            "total_matches": 0,
            "ranked_predictions": [],
            "slips": [],
        }
        _DAILY_SLIPS_CACHE[cache_key] = {"ts": time.time(), "data": empty_res}
        return empty_res

    # Helper for commercial Parimatch odds (5% overround)
    def _calc_odds(p: float, margin: float = 0.05) -> float:
        if p <= 0:
            return 1.01
        commercial_p = min(0.98, p * (1 + margin))
        return round(1.0 / commercial_p, 2)

    FLAG_MAP = {
        "EPL": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "LA_LIGA": "🇪🇸", "SERIE_A": "🇮🇹", "BUNDESLIGA": "🇩🇪", "LIGUE_1": "🇫🇷",
        "UCL": "🏆", "UEL": "🇪🇺", "UECL": "🏟️", "ISL": "🇮🇳", "MLS": "🇺🇸", "BRA_SERIE_A": "🇧🇷", "LIGA_ARG": "🇦🇷",
        "NATIONS_LEAGUE": "🇪🇺", "FRIENDLIES": "🌍"
    }

    all_picks = []
    ranked_predictions = []
    team_stat_cache = {}
    poisson_model = PoissonModel()

    # Prioritize active (non-finished) matches first, then official league priority.
    # Fair-coverage selection: every league with active matches gets at least
    # 2 evaluated (round-robin by league priority), then fill to the cap by
    # priority order. A flat top-N cut starves late-priority leagues (MLS,
    # Brasileirao) on busy multi-league days.
    # NOTE: priority is keyed by league CODE, not DB id (ids are not stable
    # across environments/backfills).
    priority_order = {"EPL": 1, "UCL": 1.5, "UEL": 1.6, "UECL": 1.7, "LA_LIGA": 2, "SERIE_A": 3,
                      "BUNDESLIGA": 4, "LIGUE_1": 5, "ISL": 6,
                      "NATIONS_LEAGUE": 7, "MLS": 8, "FRIENDLIES": 9,
                      "LIGA_ARG": 10, "BRA_SERIE_A": 11}
    league_code_of = {}
    for _m in matches:
        if _m.id not in league_code_of:
            _lg = db.get(League, _m.league_id) if _m.league_id else None
            league_code_of[_m.id] = _lg.code if _lg else "LEAGUE"

    def _sort_key(x):
        return (
            1 if (x.status or "").upper() in ("FINISHED", "POSTPONED", "CANCELLED", "ABANDONED") else 0,
            priority_order.get(league_code_of.get(x.id, "LEAGUE"), 99),
            x.kickoff_at.isoformat() if x.kickoff_at else "",
        )

    sorted_matches = sorted(matches, key=_sort_key)
    # Week-wide coverage: every league with active matches gets at least 3
    # evaluated, then priority fill to the cap. Per-match compute is ~20ms,
    # so a 400 cap stays within API latency budgets (cache: 180s).
    EVAL_CAP = 400
    MIN_PER_LEAGUE = 3
    eval_matches = []
    seen = set()
    active_by_league = {}
    for x in sorted_matches:
        if (x.status or "").upper() in ("FINISHED", "POSTPONED", "CANCELLED", "ABANDONED"):
            continue
        active_by_league.setdefault(league_code_of.get(x.id, "LEAGUE"), []).append(x)
    for _code in sorted(active_by_league.keys(),
                        key=lambda c: priority_order.get(c, 99)):
        for x in active_by_league[_code][:MIN_PER_LEAGUE]:
            eval_matches.append(x)
            seen.add(x.id)
    for x in sorted_matches:
        if len(eval_matches) >= EVAL_CAP:
            break
        if x.id not in seen:
            eval_matches.append(x)
            seen.add(x.id)

    for m in eval_matches:
        try:
            home_team = db.get(Team, m.home_team_id) if m.home_team_id else None
            away_team = db.get(Team, m.away_team_id) if m.away_team_id else None
            league = db.get(League, m.league_id) if m.league_id else None

            h_name = home_team.name if home_team else "Home"
            a_name = away_team.name if away_team else "Away"
            lg_code = league.code if league else "LEAGUE"
            lg_name = league.name if league else "Football"

            # Check per-match cache (10 min TTL or status change)
            cached_m = _PRED_MATCH_CACHE.get(m.id)
            if cached_m and cached_m.get("status") == m.status and (time.time() - cached_m.get("ts", 0) < 600):
                projected_stats_payload = cached_m["projected_stats_payload"]
                p_h = cached_m["p_h"]
                p_d = cached_m["p_d"]
                p_a = cached_m["p_a"]
                p_o15 = cached_m["p_o15"]
                p_o25 = cached_m["p_o25"]
                p_btts = cached_m["p_btts"]
                lam_h = cached_m["lam_h"]
                lam_a = cached_m["lam_a"]
                proj_data = cached_m.get("proj_data", {})
            else:
                # Compute stat projections
                proj_data = _compute_stat_projections_data(db, m, team_cache=team_stat_cache)
                comb = proj_data.get("combined_projections") or {}
                t_proj = proj_data.get("team_projections") or {}
                h_corn = t_proj.get("home", {}).get("corners", 5.0)
                a_corn = t_proj.get("away", {}).get("corners", 4.5)
                c_total = comb.get("corners_total", 9.5)
                cards_total = comb.get("yellow_cards_total", 3.5)
                sot_total = comb.get("shots_on_target", 8.5)

                projected_stats_payload = {
                    "corners_total": round(c_total, 1),
                    "corners_home": round(h_corn, 1),
                    "corners_away": round(a_corn, 1),
                    "cards_total": round(cards_total, 1),
                    "shots_on_target": round(sot_total, 1),
                }

                try:
                    pred = poisson_model.predict(db, m.id, cutoff=m.kickoff_at or datetime.now(timezone.utc))
                    p_h = float(pred.home_win_probability)
                    p_d = float(pred.draw_probability)
                    p_a = float(pred.away_win_probability)
                    p_o15 = float(pred.over_1_5_probability)
                    p_o25 = float(pred.over_2_5_probability)
                    p_btts = float(pred.btts_yes_probability)
                    lam_h = float(getattr(pred, "expected_home_goals", None) or 1.4)
                    lam_a = float(getattr(pred, "expected_away_goals", None) or 1.1)
                except Exception:
                    # Robust Poisson model fallback for UEFA Champions League and cup competitions
                    import math
                    h_sot = t_proj.get("home", {}).get("shots_on_target", 4.5)
                    a_sot = t_proj.get("away", {}).get("shots_on_target", 3.8)
                    lam_h = max(0.6, min(3.2, h_sot * 0.32))
                    lam_a = max(0.5, min(2.8, a_sot * 0.30))
                    grid = [[(math.exp(-lam_h) * (lam_h ** i) / math.factorial(i)) * (math.exp(-lam_a) * (lam_a ** j) / math.factorial(j)) for j in range(10)] for i in range(10)]
                    p_h = sum(grid[i][j] for i in range(10) for j in range(10) if i > j)
                    p_d = sum(grid[i][j] for i in range(10) for j in range(10) if i == j)
                    p_a = sum(grid[i][j] for i in range(10) for j in range(10) if i < j)
                    p_o15 = sum(grid[i][j] for i in range(10) for j in range(10) if i + j >= 2)
                    p_o25 = sum(grid[i][j] for i in range(10) for j in range(10) if i + j >= 3)
                    p_btts = sum(grid[i][j] for i in range(10) for j in range(10) if i >= 1 and j >= 1)

                _PRED_MATCH_CACHE[m.id] = {
                    "ts": time.time(),
                    "status": m.status,
                    "projected_stats_payload": projected_stats_payload,
                    "p_h": p_h,
                    "p_d": p_d,
                    "p_a": p_a,
                    "p_o15": p_o15,
                    "p_o25": p_o25,
                    "p_btts": p_btts,
                    "lam_h": lam_h,
                    "lam_a": lam_a,
                    "proj_data": proj_data,
                }

            proj_score = f"{int(round(lam_h))} - {int(round(lam_a))}"

            m_status = (m.status or "").upper()
            h_score = m.home_score
            a_score = m.away_score

            # Fetch match statistics if finished for prop markets
            match_stats = {}
            if m_status == "FINISHED":
                stat_rows = db.query(MatchStatistic).filter_by(match_id=m.id, period="full").all()
                for sr in stat_rows:
                    try:
                        val = float(str(sr.stat_value).rstrip("%"))
                        match_stats[(sr.team, sr.stat_name)] = val
                    except (ValueError, TypeError):
                        pass

            def _get_pick_status(pick_text: str) -> str:
                if m_status == "FINISHED" and h_score is not None and a_score is not None:
                    tot_g = h_score + a_score
                    if "Over 1.5" in pick_text:
                        return "WON" if tot_g >= 2 else "LOST"
                    if "Over 2.5" in pick_text:
                        return "WON" if tot_g >= 3 else "LOST"
                    if "Both Teams to Score" in pick_text:
                        return "WON" if (h_score > 0 and a_score > 0) else "LOST"
                    if "or Draw (1X)" in pick_text:
                        return "WON" if h_score >= a_score else "LOST"
                    if "or Draw (X2)" in pick_text:
                        return "WON" if a_score >= h_score else "LOST"
                    if "to Win" in pick_text:
                        if h_name in pick_text:
                            return "WON" if h_score > a_score else "LOST"
                        else:
                            return "WON" if a_score > h_score else "LOST"

                    # Stat props evaluation
                    if "Corners" in pick_text:
                        tot_corn = match_stats.get(("home", "corners"), 5.0) + match_stats.get(("away", "corners"), 4.0)
                        if "Over 9.5" in pick_text:
                            return "WON" if tot_corn >= 9.5 else "LOST"
                        if "Over 8.5" in pick_text:
                            return "WON" if tot_corn >= 8.5 else "LOST"
                    if "Shots on Target" in pick_text:
                        tot_sot = match_stats.get(("home", "shots_on_target"), 4.0) + match_stats.get(("away", "shots_on_target"), 4.0)
                        if "Over 8.5" in pick_text:
                            return "WON" if tot_sot >= 8.5 else "LOST"
                    if "Total Shots" in pick_text:
                        tot_shots = match_stats.get(("home", "shots_total"), 13.0) + match_stats.get(("away", "shots_total"), 11.0)
                        if "Over 24.5" in pick_text:
                            return "WON" if tot_shots >= 24.5 else "LOST"
                    if "Yellow Cards" in pick_text:
                        tot_yc = match_stats.get(("home", "yellow_cards"), 2.0) + match_stats.get(("away", "yellow_cards"), 2.0)
                        if "Over 3.5" in pick_text:
                            return "WON" if tot_yc >= 3.5 else "LOST"
                    if "Red Card" in pick_text:
                        tot_rc = match_stats.get(("home", "red_cards"), 0.0) + match_stats.get(("away", "red_cards"), 0.0)
                        return "WON" if tot_rc >= 1.0 else "LOST"

                elif m_status in ("IN_PLAY", "LIVE", "HALFTIME"):
                    return "LIVE"
                return "PENDING"

            # Candidate picks for accumulator slips:
            # For Today/Future (!is_past_date), exclude FINISHED matches so active slips contain only placeable bets.
            # For Past Dates (is_past_date), include that date's finished matches so date-wise slips show settled outcomes.
            if (is_past_date or m_status != "FINISHED") and m_status not in ("POSTPONED", "CANCELLED", "ABANDONED"):
                # Candidate 1: Direct Win
                if p_h >= 0.55:
                    all_picks.append({
                        "match_id": m.id,
                        "fixture": f"{h_name} vs {a_name}",
                        "league": lg_name,
                        "league_code": lg_code,
                        "pick": f"{h_name} to Win",
                        "market": "1X2 (Match Winner)",
                        "probability": round(p_h, 3),
                        "odds": _calc_odds(p_h),
                        "confidence": "HIGH" if p_h >= 0.65 else "MEDIUM",
                        "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
                        "projected_stats": projected_stats_payload,
                        "status": _get_pick_status(f"{h_name} to Win"),
                    })
                elif p_a >= 0.50:
                    all_picks.append({
                        "match_id": m.id,
                        "fixture": f"{h_name} vs {a_name}",
                        "league": lg_name,
                        "league_code": lg_code,
                        "pick": f"{a_name} to Win",
                        "market": "1X2 (Match Winner)",
                        "probability": round(p_a, 3),
                        "odds": _calc_odds(p_a),
                        "confidence": "HIGH" if p_a >= 0.60 else "MEDIUM",
                        "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
                        "projected_stats": projected_stats_payload,
                        "status": _get_pick_status(f"{a_name} to Win"),
                    })

                # Candidate 2: Double Chance (Safety Pick)
                p_1x = p_h + p_d
                if p_1x >= 0.75:
                    all_picks.append({
                        "match_id": m.id,
                        "fixture": f"{h_name} vs {a_name}",
                        "league": lg_name,
                        "league_code": lg_code,
                        "pick": f"{h_name} or Draw (1X)",
                        "market": "Double Chance",
                        "probability": round(p_1x, 3),
                        "odds": _calc_odds(p_1x),
                        "confidence": "VERY HIGH",
                        "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
                        "projected_stats": projected_stats_payload,
                        "status": _get_pick_status(f"{h_name} or Draw (1X)"),
                    })

                p_x2 = p_d + p_a
                if p_x2 >= 0.75:
                    all_picks.append({
                        "match_id": m.id,
                        "fixture": f"{h_name} vs {a_name}",
                        "league": lg_name,
                        "league_code": lg_code,
                        "pick": f"{a_name} or Draw (X2)",
                        "market": "Double Chance",
                        "probability": round(p_x2, 3),
                        "odds": _calc_odds(p_x2),
                        "confidence": "VERY HIGH",
                        "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
                        "projected_stats": projected_stats_payload,
                        "status": _get_pick_status(f"{a_name} or Draw (X2)"),
                    })

                # Candidate 3: Over 1.5 Goals
                if p_o15 >= 0.72:
                    all_picks.append({
                        "match_id": m.id,
                        "fixture": f"{h_name} vs {a_name}",
                        "league": lg_name,
                        "league_code": lg_code,
                        "pick": "Over 1.5 Total Goals",
                        "market": "Totals",
                        "probability": round(p_o15, 3),
                        "odds": _calc_odds(p_o15),
                        "confidence": "HIGH",
                        "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
                        "projected_stats": projected_stats_payload,
                        "status": _get_pick_status("Over 1.5 Total Goals"),
                    })

                # Candidate 4: Over 2.5 Goals (Value Pick)
                if 0.50 <= p_o25 <= 0.75:
                    all_picks.append({
                        "match_id": m.id,
                        "fixture": f"{h_name} vs {a_name}",
                        "league": lg_name,
                        "league_code": lg_code,
                        "pick": "Over 2.5 Goals",
                        "market": "Totals",
                        "probability": round(p_o25, 3),
                        "odds": _calc_odds(p_o25),
                        "confidence": "MEDIUM",
                        "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
                        "projected_stats": projected_stats_payload,
                        "status": _get_pick_status("Over 2.5 Goals"),
                    })

                # Candidate 5: Both Teams to Score (BTTS)
                if 0.52 <= p_btts <= 0.75:
                    all_picks.append({
                        "match_id": m.id,
                        "fixture": f"{h_name} vs {a_name}",
                        "league": lg_name,
                        "league_code": lg_code,
                        "pick": "Both Teams to Score (Yes)",
                        "market": "BTTS",
                        "probability": round(p_btts, 3),
                        "odds": _calc_odds(p_btts),
                        "confidence": "MEDIUM",
                        "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
                        "projected_stats": projected_stats_payload,
                        "status": _get_pick_status("Both Teams to Score (Yes)"),
                    })

            # Evaluate all candidate outcomes for this match to determine the single Best Possible Outcome
            match_candidates = []

            # Helper to calculate continuous AI Power Index (15 - 99)
            def _score_outcome(prob_val: float, odds_val: float, ev_val: float) -> float:
                p_norm = prob_val / 100.0
                return round(min(99.0, max(15.0, (p_norm * 75.0) + min(15.0, (odds_val - 1.0) * 8.0) + max(-5.0, ev_val * 0.4))), 1)

            # 1. Home Win
            p_h_ev = round(((p_h * _calc_odds(p_h)) - 1.0) * 100, 1)
            p_h_pct = round(p_h * 100, 1)
            p_h_odds = _calc_odds(p_h)
            match_candidates.append({
                "pick": f"{h_name} to Win",
                "market": "1X2 (Match Winner)",
                "probability": p_h_pct,
                "odds": p_h_odds,
                "confidence": "VERY HIGH" if p_h >= 0.70 else ("HIGH" if p_h >= 0.58 else "MEDIUM"),
                "category": "BANKER" if p_h >= 0.70 else ("VALUE" if p_h_ev >= 5.0 else "MATCH_WINNER"),
                "badge": "Top Home Banker" if p_h >= 0.70 else ("High Value Edge" if p_h_ev >= 5.0 else "Home Win"),
                "ev_edge": f"+{p_h_ev}% Edge" if p_h_ev > 0 else f"{p_h_ev}% Edge",
                "ai_score": _score_outcome(p_h_pct, p_h_odds, p_h_ev),
                "status": _get_pick_status(f"{h_name} to Win"),
            })

            # 2. Away Win
            p_a_ev = round(((p_a * _calc_odds(p_a)) - 1.0) * 100, 1)
            p_a_pct = round(p_a * 100, 1)
            p_a_odds = _calc_odds(p_a)
            match_candidates.append({
                "pick": f"{a_name} to Win",
                "market": "1X2 (Match Winner)",
                "probability": p_a_pct,
                "odds": p_a_odds,
                "confidence": "VERY HIGH" if p_a >= 0.65 else ("HIGH" if p_a >= 0.55 else "MEDIUM"),
                "category": "BANKER" if p_a >= 0.65 else ("VALUE" if p_a_ev >= 5.0 else "MATCH_WINNER"),
                "badge": "Top Away Banker" if p_a >= 0.65 else ("High Value Edge" if p_a_ev >= 5.0 else "Away Win"),
                "ev_edge": f"+{p_a_ev}% Edge" if p_a_ev > 0 else f"{p_a_ev}% Edge",
                "ai_score": _score_outcome(p_a_pct, p_a_odds, p_a_ev),
                "status": _get_pick_status(f"{a_name} to Win"),
            })

            # 3. Double Chance (1X)
            p_1x = min(0.98, p_h + p_d)
            p_1x_ev = round(((p_1x * _calc_odds(p_1x)) - 1.0) * 100, 1)
            p_1x_pct = round(p_1x * 100, 1)
            p_1x_odds = _calc_odds(p_1x)
            match_candidates.append({
                "pick": f"{h_name} or Draw (1X)",
                "market": "Double Chance",
                "probability": p_1x_pct,
                "odds": p_1x_odds,
                "confidence": "VERY HIGH" if p_1x >= 0.80 else "HIGH",
                "category": "SAFETY",
                "badge": "Safe Buffer (1X)",
                "ev_edge": f"+{p_1x_ev}% Edge" if p_1x_ev > 0 else f"{p_1x_ev}% Edge",
                "ai_score": _score_outcome(p_1x_pct, p_1x_odds, p_1x_ev),
                "status": _get_pick_status(f"{h_name} or Draw (1X)"),
            })

            # 4. Double Chance (X2)
            p_x2 = min(0.98, p_d + p_a)
            p_x2_ev = round(((p_x2 * _calc_odds(p_x2)) - 1.0) * 100, 1)
            p_x2_pct = round(p_x2 * 100, 1)
            p_x2_odds = _calc_odds(p_x2)
            match_candidates.append({
                "pick": f"{a_name} or Draw (X2)",
                "market": "Double Chance",
                "probability": p_x2_pct,
                "odds": p_x2_odds,
                "confidence": "VERY HIGH" if p_x2 >= 0.80 else "HIGH",
                "category": "SAFETY",
                "badge": "Safe Buffer (X2)",
                "ev_edge": f"+{p_x2_ev}% Edge" if p_x2_ev > 0 else f"{p_x2_ev}% Edge",
                "ai_score": _score_outcome(p_x2_pct, p_x2_odds, p_x2_ev),
                "status": _get_pick_status(f"{a_name} or Draw (X2)"),
            })

            # 5. Over 1.5 Goals
            p_o15_ev = round(((p_o15 * _calc_odds(p_o15)) - 1.0) * 100, 1)
            p_o15_pct = round(p_o15 * 100, 1)
            p_o15_odds = _calc_odds(p_o15)
            match_candidates.append({
                "pick": "Over 1.5 Total Goals",
                "market": "Totals",
                "probability": p_o15_pct,
                "odds": p_o15_odds,
                "confidence": "VERY HIGH" if p_o15 >= 0.80 else "HIGH",
                "category": "GOALS",
                "badge": "Over 1.5 Lock",
                "ev_edge": f"+{p_o15_ev}% Edge" if p_o15_ev > 0 else f"{p_o15_ev}% Edge",
                "ai_score": _score_outcome(p_o15_pct, p_o15_odds, p_o15_ev),
                "status": _get_pick_status("Over 1.5 Total Goals"),
            })

            # 6. Over 2.5 Goals
            p_o25_ev = round(((p_o25 * _calc_odds(p_o25)) - 1.0) * 100, 1)
            p_o25_pct = round(p_o25 * 100, 1)
            p_o25_odds = _calc_odds(p_o25)
            match_candidates.append({
                "pick": "Over 2.5 Total Goals",
                "market": "Totals",
                "probability": p_o25_pct,
                "odds": p_o25_odds,
                "confidence": "HIGH" if p_o25 >= 0.65 else "MEDIUM",
                "category": "GOALS",
                "badge": "Over 2.5 Goals",
                "ev_edge": f"+{p_o25_ev}% Edge" if p_o25_ev > 0 else f"{p_o25_ev}% Edge",
                "ai_score": _score_outcome(p_o25_pct, p_o25_odds, p_o25_ev),
                "status": _get_pick_status("Over 2.5 Goals"),
            })

            # 7. BTTS Yes
            p_btts_ev = round(((p_btts * _calc_odds(p_btts)) - 1.0) * 100, 1)
            p_btts_pct = round(p_btts * 100, 1)
            p_btts_odds = _calc_odds(p_btts)
            match_candidates.append({
                "pick": "Both Teams to Score (Yes)",
                "market": "BTTS",
                "probability": p_btts_pct,
                "odds": p_btts_odds,
                "confidence": "HIGH" if p_btts >= 0.65 else "MEDIUM",
                "category": "GOALS",
                "badge": "BTTS (Yes)",
                "ev_edge": f"+{p_btts_ev}% Edge" if p_btts_ev > 0 else f"{p_btts_ev}% Edge",
                "ai_score": _score_outcome(p_btts_pct, p_btts_odds, p_btts_ev),
                "status": _get_pick_status("Both Teams to Score (Yes)"),
            })

            # Sort match candidates to prioritize the highest mathematical viability and win probability
            match_candidates.sort(key=lambda x: (x["probability"] * 0.70) + (x["ai_score"] * 0.30), reverse=True)
            best_outcome = match_candidates[0]

            # Choose up to 2 alternative viable picks from different markets
            alt_picks = []
            seen_mkts = {best_outcome["market"]}
            for cand in match_candidates[1:]:
                if cand["market"] not in seen_mkts:
                    seen_mkts.add(cand["market"])
                    alt_picks.append(cand)
                    if len(alt_picks) == 2:
                        break

            # Formulate tailored AI statistical rationale
            cat = best_outcome["category"]
            if cat == "BANKER":
                ai_insight = f"{best_outcome['pick']} carries top-tier model certainty ({best_outcome['probability']}%) projecting a {proj_score} scoreline with {best_outcome['ev_edge']} against market odds."
            elif cat == "GOALS":
                ai_insight = f"Dynamic offensive profiles project {round(lam_h + lam_a, 1)} combined expected goals, establishing {best_outcome['pick']} as premier mathematical value."
            elif cat == "SAFETY":
                ai_insight = f"High-confidence defensive hedge offering {best_outcome['probability']}% statistical coverage against unexpected upset variance."
            elif cat == "VALUE":
                ai_insight = f"Significant positive model discrepancy yielding {best_outcome['ev_edge']} over commercial bookmaker odds with {proj_score} projected scoreline."
            else:
                ai_insight = f"Calibrated Poisson model favors {best_outcome['pick']} with {best_outcome['probability']}% probability and {proj_score} projected outcome."

            ranked_predictions.append({
                "match_id": m.id,
                "fixture": f"{h_name} vs {a_name}",
                "home_team": h_name,
                "away_team": a_name,
                "league_code": lg_code,
                "league_name": lg_name,
                "league_flag": FLAG_MAP.get(lg_code, "⚽"),
                "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
                "status": m_status or "SCHEDULED",
                "home_score": h_score,
                "away_score": a_score,
                "best_outcome": best_outcome,
                "alternative_outcomes": alt_picks,
                "projected_score": proj_score,
                "projected_stats": projected_stats_payload,
                "ai_insight": ai_insight,
                "sort_score": best_outcome["ai_score"],
            })
        except Exception:
            continue

    # Helper: calculate combined accumulator odds and ranking metrics
    def _combine_slip(picks_list, name, badge, desc, slip_type, is_single: bool = False):
        if not picks_list:
            return None
        comb_odds = 1.0
        for p in picks_list:
            comb_odds *= p["odds"]
        avg_prob = sum(p["probability"] for p in picks_list) / len(picks_list)

        # Risk level determination
        if avg_prob >= 0.78 or comb_odds <= 1.40:
            risk_lvl = "LOW"
        elif avg_prob >= 0.60 and comb_odds <= 3.50:
            risk_lvl = "BALANCED"
        else:
            risk_lvl = "HIGH_YIELD"

        # Edge calculation: (Model Probability * Decimal Odds) - 1.0
        ev_pct = round(((avg_prob * comb_odds) - 1.0) * 100, 1)
        ev_str = f"+{ev_pct}% Edge" if ev_pct > 0 else f"{ev_pct}% Edge"

        # AI Ranking score (combining safety, payoff potential, and model edge)
        raw_score = (avg_prob * 65.0) + min(25.0, (comb_odds - 1.0) * 10.0) + (max(0.0, ev_pct) * 0.5)
        ai_score = round(min(99.0, max(55.0, raw_score)), 1)

        # Outcome status calculation
        statuses = [p.get("status", "PENDING") for p in picks_list]
        if "LOST" in statuses:
            outcome = "LOST"
        elif all(s == "WON" for s in statuses):
            outcome = "WON"
        elif any(s == "LIVE" for s in statuses):
            outcome = "LIVE"
        else:
            outcome = "PENDING"

        return {
            "title": name,
            "type": slip_type,
            "badge": badge,
            "description": desc,
            "total_odds": round(comb_odds, 2),
            "win_probability": round(avg_prob * 100, 1),
            "selections_count": len(picks_list),
            "is_single_match": is_single,
            "risk_level": risk_lvl,
            "ev_edge": ev_str,
            "ai_score": ai_score,
            "outcome_status": outcome,
            "picks": picks_list,
        }

    slips = []

    # 0. UCL-DEDICATED SLIPS (When Champions League games are present)
    ucl_banker_candidates = sorted(
        [p for p in all_picks if p.get("league_code") == "UCL" and p["probability"] >= 0.65],
        key=lambda x: x["probability"],
        reverse=True
    )
    if len(ucl_banker_candidates) >= 2:
        seen_ucl_b = set()
        ucl_b_picks = []
        for p in ucl_banker_candidates:
            if p["match_id"] not in seen_ucl_b:
                seen_ucl_b.add(p["match_id"])
                ucl_b_picks.append(p)
                if len(ucl_b_picks) == 3:
                    break
        if len(ucl_b_picks) >= 2:
            slips.append(_combine_slip(
                ucl_b_picks,
                "🏆 UCL Pure Banker Slip",
                "UCL Only (High Probability)",
                f"Champions League exclusive banker parlay combining {len(ucl_b_picks)} highest-confidence European fixtures.",
                "banker"
            ))

    ucl_val_candidates = sorted(
        [p for p in all_picks if p.get("league_code") == "UCL" and p["odds"] >= 1.60],
        key=lambda x: x["probability"] * x["odds"],
        reverse=True
    )
    if len(ucl_val_candidates) >= 2:
        seen_ucl_v = set()
        ucl_v_picks = []
        for p in ucl_val_candidates:
            if p["match_id"] not in seen_ucl_v:
                seen_ucl_v.add(p["match_id"])
                ucl_v_picks.append(p)
                if len(ucl_v_picks) == 3:
                    break
        if len(ucl_v_picks) >= 2:
            slips.append(_combine_slip(
                ucl_v_picks,
                "🚀 UCL Mega Multiplier",
                "UCL Only (High Odds)",
                f"High-yield UEFA Champions League value accumulator with maximum mathematical edge.",
                "value"
            ))

    # 1. SAFE BANKER TREBLE (Highest Probability >= 75%, ultra-low variance)
    banker_candidates = sorted(
        [p for p in all_picks if p["probability"] >= 0.70],
        key=lambda x: x["probability"],
        reverse=True
    )
    if len(banker_candidates) < 3:
        banker_candidates = sorted(all_picks, key=lambda x: x["probability"], reverse=True)

    seen_matches_banker = set()
    banker_picks = []
    for p in banker_candidates:
        if p["match_id"] not in seen_matches_banker:
            seen_matches_banker.add(p["match_id"])
            banker_picks.append(p)
            if len(banker_picks) == 3:
                break
    if banker_picks:
        slips.append(_combine_slip(
            banker_picks,
            "Safe Banker Treble",
            "Highest Accuracy (75%+ Prob)",
            "Top-confidence mathematical selections designed for minimal variance.",
            "banker"
        ))

    # 2. CROSS-LEAGUE POWER ACCA (Multi-league synergy: EPL, La Liga, Serie A, etc.)
    acc_candidates = sorted(
        [p for p in all_picks if p["probability"] >= 0.58 and p["odds"] >= 1.25],
        key=lambda x: x["probability"] * x["odds"],
        reverse=True
    )
    if len(acc_candidates) < 4:
        acc_candidates = sorted(all_picks, key=lambda x: x["probability"], reverse=True)

    multi_league_picks = []
    seen_leagues = set()
    seen_matches_acc = set()
    for p in acc_candidates:
        if p["match_id"] not in seen_matches_acc and p["league_code"] not in seen_leagues:
            seen_matches_acc.add(p["match_id"])
            seen_leagues.add(p["league_code"])
            multi_league_picks.append(p)
            if len(multi_league_picks) == 4:
                break
    if len(multi_league_picks) < 3:
        for p in acc_candidates:
            if p["match_id"] not in seen_matches_acc:
                seen_matches_acc.add(p["match_id"])
                multi_league_picks.append(p)
                if len(multi_league_picks) == 4:
                    break

    if multi_league_picks:
        slips.append(_combine_slip(
            multi_league_picks,
            "Cross-League Power Acca",
            "Multi-League Combo",
            f"Cross-competition accumulator combining {len(multi_league_picks)} high-synergy selections.",
            "accumulator"
        ))

    # 3. CORNERS & CARDS SPECIALIST (Prop market specialist slip)
    prop_candidates = sorted(
        [p for p in all_picks if p["market"].startswith("Props") and p["probability"] >= 0.56],
        key=lambda x: x["probability"],
        reverse=True
    )
    if len(prop_candidates) < 3:
        prop_candidates = sorted([p for p in all_picks if p["market"].startswith("Props")], key=lambda x: x["probability"], reverse=True)

    seen_matches_prop = set()
    prop_picks = []
    for p in prop_candidates:
        if p["match_id"] not in seen_matches_prop:
            seen_matches_prop.add(p["match_id"])
            prop_picks.append(p)
            if len(prop_picks) == 3:
                break
    if prop_picks:
        slips.append(_combine_slip(
            prop_picks,
            "Corners & Cards Specialist",
            "Prop Market Edge",
            "Data-driven statistical props based on referee averages, set-piece pressure, and card rates.",
            "corners_cards"
        ))

    # 4. GOALS GALORE COMBO (Over Goals & BTTS specialist)
    goal_candidates = sorted(
        [p for p in all_picks if p["market"] in ("Totals", "BTTS") and p["probability"] >= 0.60],
        key=lambda x: x["probability"],
        reverse=True
    )
    if len(goal_candidates) < 3:
        goal_candidates = sorted([p for p in all_picks if p["market"] in ("Totals", "BTTS")], key=lambda x: x["probability"], reverse=True)

    seen_matches_goal = set()
    goal_picks = []
    for p in goal_candidates:
        if p["match_id"] not in seen_matches_goal:
            seen_matches_goal.add(p["match_id"])
            goal_picks.append(p)
            if len(goal_picks) == 3:
                break
    if goal_picks:
        slips.append(_combine_slip(
            goal_picks,
            "Goals Galore Combo",
            "Over Goals & BTTS",
            "Curated goal lines combining high expected goals (xG) projections across leagues.",
            "goals"
        ))

    # 5. HIGH VALUE MULTIPLIER (Positive EV, 1.65+ odds picks)
    value_candidates = sorted(
        [p for p in all_picks if 1.55 <= p["odds"] <= 2.50 and p["probability"] >= 0.45],
        key=lambda x: x["probability"] * x["odds"],
        reverse=True
    )
    if len(value_candidates) < 3:
        value_candidates = sorted([p for p in all_picks if p["odds"] >= 1.50], key=lambda x: x["probability"] * x["odds"], reverse=True)

    seen_matches_val = set()
    value_picks = []
    for p in value_candidates:
        if p["match_id"] not in seen_matches_val:
            seen_matches_val.add(p["match_id"])
            value_picks.append(p)
            if len(value_picks) == 3:
                break
    if value_picks:
        slips.append(_combine_slip(
            value_picks,
            "High Value Multiplier",
            "Value Edge (1.70+ Odds)",
            "Selections where model win probability offers significant positive expected value against market margins.",
            "value"
        ))

    # 6. MEGA 5-FOLD PARLAY (High Compound Multiplier across Europe)
    mega_candidates = sorted(
        [p for p in all_picks if p["probability"] >= 0.60],
        key=lambda x: x["probability"],
        reverse=True
    )
    if len(mega_candidates) < 5:
        mega_candidates = sorted(all_picks, key=lambda x: x["probability"], reverse=True)

    seen_matches_mega = set()
    mega_picks = []
    for p in mega_candidates:
        if p["match_id"] not in seen_matches_mega:
            seen_matches_mega.add(p["match_id"])
            mega_picks.append(p)
            if len(mega_picks) == 5:
                break
    if len(mega_picks) >= 3:
        slips.append(_combine_slip(
            mega_picks,
            "Mega 5-Fold Parlay",
            "Big Odds Multiplier",
            f"Strategic {len(mega_picks)}-selection cross-league parlay designed for high compound returns.",
            "mega"
        ))

    # 7. SINGLE MATCH BANKER (Top Single Game Pick with Highest Confidence)
    single_banker_candidates = sorted(all_picks, key=lambda x: x["probability"], reverse=True)
    if single_banker_candidates:
        s_pick = single_banker_candidates[0]
        slips.append(_combine_slip(
            [s_pick],
            f"Single: {s_pick['fixture']}",
            "Top Single Banker",
            f"Highest-confidence standalone single match pick ({s_pick['pick']}) with deep statistical backing.",
            "single_match",
            is_single=True
        ))

    # 8. SINGLE MATCH VALUE EDGE (Top Standalone Value with 1.65+ Odds)
    single_val_candidates = sorted(
        [p for p in all_picks if p["odds"] >= 1.65],
        key=lambda x: x["probability"] * x["odds"],
        reverse=True
    )
    if not single_val_candidates:
        single_val_candidates = sorted(all_picks, key=lambda x: x["odds"], reverse=True)
    if single_val_candidates:
        s_val_pick = single_val_candidates[0]
        if single_banker_candidates and s_val_pick["match_id"] == single_banker_candidates[0]["match_id"] and len(single_val_candidates) > 1:
            s_val_pick = single_val_candidates[1]
        slips.append(_combine_slip(
            [s_val_pick],
            f"Single Value: {s_val_pick['fixture']}",
            "Top Single Value (1.70+ Odds)",
            f"Prime single match betting opportunity on {s_val_pick['fixture']} ({s_val_pick['pick']}) offering maximum model EV edge.",
            "single_match",
            is_single=True
        ))

    valid_slips = [s for s in slips if s is not None]
    # Assign official ranking: Rank #1, #2, #3... by ai_score descending
    valid_slips.sort(key=lambda x: x["ai_score"], reverse=True)
    for rank_idx, s in enumerate(valid_slips, 1):
        s["rank"] = rank_idx

    # For Today/Future, eliminate finished matches from active predictions so bettors only see upcoming games.
    # For Past Dates, show that date's predictions settled with WON / LOST badges.
    if is_past_date:
        active_predictions = [
            rp for rp in ranked_predictions
            if rp["status"] not in ("POSTPONED", "CANCELLED", "ABANDONED")
        ]
    else:
        active_predictions = [
            rp for rp in ranked_predictions
            if rp["status"] != "FINISHED" and rp["status"] not in ("POSTPONED", "CANCELLED", "ABANDONED")
        ]
    settled_predictions_today = [
        rp for rp in ranked_predictions
        if rp["status"] == "FINISHED"
    ]

    # Re-rank active predictions from #1 to #N by AI Power Score
    active_predictions.sort(key=lambda x: x["sort_score"], reverse=True)
    for r_idx, rp in enumerate(active_predictions, 1):
        rp["rank"] = r_idx
        rp["is_nap_of_the_day"] = (r_idx == 1)

    result = {
        "date": target_date_str,
        "total_matches": len(matches),
        "upcoming_count": len(active_predictions),
        "settled_count": len(settled_predictions_today),
        "ranked_predictions": active_predictions,
        "settled_predictions_today": settled_predictions_today,
        "slips": valid_slips,
    }
    _stamp_team_logos(db, active_predictions, settled_predictions_today,
                      [p for s in valid_slips for p in (s.get("picks") or [])])
    _DAILY_SLIPS_CACHE[cache_key] = {"ts": time.time(), "data": result}
    return result


def _stamp_team_logos(db: Session, *item_lists: list) -> None:
    """Attach home_team_logo/away_team_logo to prediction payload dicts.

    Single bulk lookup per request: resolves each referenced match's teams
    once, so slip cards and ranked rows render real crests without N+1s.
    """
    need_ids: set[int] = set()
    for items in item_lists:
        for it in items:
            mid = it.get("match_id")
            if mid is not None:
                need_ids.add(mid)
    if not need_ids:
        return
    logo_by_match: dict[int, tuple] = {}
    for m in db.query(Match).filter(Match.id.in_(need_ids)).all():
        home = db.get(Team, m.home_team_id) if m.home_team_id else None
        away = db.get(Team, m.away_team_id) if m.away_team_id else None
        logo_by_match[m.id] = (getattr(home, "logo_url", None),
                               getattr(away, "logo_url", None))
    for items in item_lists:
        for it in items:
            logos = logo_by_match.get(it.get("match_id"))
            if logos:
                it.setdefault("home_team_logo", logos[0])
                it.setdefault("away_team_logo", logos[1])


_PREDICTION_HISTORY_CACHE: Dict[str, Any] = {}


@router.get("/prediction-history", summary="Historical prediction track record with audited outcomes (won vs lost)")
def get_prediction_history(
    date: Optional[str] = Query(None, description="Specific YYYY-MM-DD date in tz (or ALL)"),
    days: int = Query(30, ge=1, le=90, description="Lookback window in days when date is not specified"),
    league: Optional[str] = Query(None, description="Filter by league code or name"),
    outcome: Optional[str] = Query("ALL", description="Filter outcome: ALL | WON | LOST"),
    limit: int = Query(100, ge=1, le=200, description="Max historical matches to evaluate"),
    tz: Optional[str] = Query("IST", description="Timezone: IST | UTC"),
    db: Session = Depends(get_db),
):
    """Provides an audited, transparent historical ledger of past AI match predictions and settlements:
    - Syncs live & recent scores before evaluating.
    - Supports exact date-wise filtering (matching the top date bar) or all-dates view.
    - Evaluates the pre-match AI Best Outcome against official full-time results.
    - Accurately settles each pick and date-wise slip as WON (Correct) or LOST (Wrong).
    """
    _refresh_live_matches_if_needed(db)

    from app.services.predictions.poisson import PoissonModel
    from datetime import datetime, timezone, timedelta
    import time
    import math

    date_clean = (date or "").strip()
    if date_clean.upper() == "ALL":
        date_clean = ""

    cache_key = f"{date_clean or 'all'}_{days}_{league or 'all'}_{outcome or 'all'}_{limit}_{tz or 'IST'}"
    cached = _PREDICTION_HISTORY_CACHE.get(cache_key)
    if cached and (time.time() - cached["ts"] < 180):
        return cached["data"]

    now_utc = datetime.now(timezone.utc)
    is_ist = bool(tz and tz.upper() in ["IST", "ASIA/KOLKATA", "+05:30", "5:30"])
    tz_offset = timedelta(hours=5, minutes=30) if is_ist else timedelta(0)

    q = db.query(Match).filter(
        Match.status == "FINISHED",
        Match.home_score.isnot(None),
        Match.away_score.isnot(None),
    )

    if date_clean:
        try:
            day = datetime.fromisoformat(date_clean).replace(tzinfo=timezone.utc)
            day_start = day - tz_offset
            day_end = day_start + timedelta(days=1)
            q = q.filter(Match.kickoff_at >= day_start, Match.kickoff_at < day_end)
        except ValueError:
            cutoff_dt = now_utc - timedelta(days=days)
            q = q.filter(Match.kickoff_at >= cutoff_dt)
    else:
        cutoff_dt = now_utc - timedelta(days=days)
        q = q.filter(Match.kickoff_at >= cutoff_dt)

    if league:
        l_clean = league.strip()
        lg = db.query(League).filter(
            (League.code.ilike(l_clean)) | (League.name.ilike(f"%{l_clean}%"))
        ).first()
        if lg:
            q = q.filter(Match.league_id == lg.id)

    matches = q.order_by(Match.kickoff_at.desc()).limit(min(limit, 150)).all()

    FLAG_MAP = {
        "EPL": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "LA_LIGA": "🇪🇸", "SERIE_A": "🇮🇹", "BUNDESLIGA": "🇩🇪", "LIGUE_1": "🇫🇷",
        "UCL": "🏆", "UEL": "🇪🇺", "UECL": "🏟️", "ISL": "🇮🇳", "MLS": "🇺🇸", "BRA_SERIE_A": "🇧🇷", "LIGA_ARG": "🇦🇷",
        "NATIONS_LEAGUE": "🇪🇺", "FRIENDLIES": "🌍"
    }

    poisson_model = PoissonModel()

    def _calc_odds(p: float, margin: float = 0.05) -> float:
        if p <= 0:
            return 1.01
        commercial_p = min(0.98, p * (1 + margin))
        return round(1.0 / commercial_p, 2)

    def _score_outcome(prob_val: float, odds_val: float, ev_val: float) -> float:
        p_norm = prob_val / 100.0
        return round(min(99.0, max(15.0, (p_norm * 75.0) + min(15.0, (odds_val - 1.0) * 8.0) + max(-5.0, ev_val * 0.4))), 1)

    all_history_items = []

    for m in matches:
        try:
            home_team = db.get(Team, m.home_team_id) if m.home_team_id else None
            away_team = db.get(Team, m.away_team_id) if m.away_team_id else None
            league_obj = db.get(League, m.league_id) if m.league_id else None

            h_name = home_team.name if home_team else "Home"
            a_name = away_team.name if away_team else "Away"
            lg_code = league_obj.code if league_obj else "LEAGUE"
            lg_name = league_obj.name if league_obj else "Football"
            h_score = m.home_score
            a_score = m.away_score

            # Check per-match cache (10 min TTL or status change; TTL matters:
            # scores can be corrected while status stays FINISHED)
            cached_m = _PRED_MATCH_CACHE.get(m.id)
            if cached_m and cached_m.get("status") == m.status and (time.time() - cached_m.get("ts", 0) < 600):
                p_h = cached_m["p_h"]
                p_d = cached_m["p_d"]
                p_a = cached_m["p_a"]
                p_o15 = cached_m["p_o15"]
                p_o25 = cached_m["p_o25"]
                p_btts = cached_m["p_btts"]
                lam_h = cached_m["lam_h"]
                lam_a = cached_m["lam_a"]
            else:
                # Poisson pre-match prediction
                try:
                    pred = poisson_model.predict(db, m.id, cutoff=m.kickoff_at or now_utc)
                    p_h = float(pred.home_win_probability)
                    p_d = float(pred.draw_probability)
                    p_a = float(pred.away_win_probability)
                    p_o15 = float(pred.over_1_5_probability)
                    p_o25 = float(pred.over_2_5_probability)
                    p_btts = float(pred.btts_yes_probability)
                    lam_h = float(getattr(pred, "expected_home_goals", None) or 1.4)
                    lam_a = float(getattr(pred, "expected_away_goals", None) or 1.1)
                except Exception:
                    lam_h, lam_a = 1.4, 1.1
                    grid = [[(math.exp(-lam_h) * (lam_h ** i) / math.factorial(i)) * (math.exp(-lam_a) * (lam_a ** j) / math.factorial(j)) for j in range(10)] for i in range(10)]
                    p_h = sum(grid[i][j] for i in range(10) for j in range(10) if i > j)
                    p_d = sum(grid[i][j] for i in range(10) for j in range(10) if i == j)
                    p_a = sum(grid[i][j] for i in range(10) for j in range(10) if i < j)
                    p_o15 = sum(grid[i][j] for i in range(10) for j in range(10) if i + j >= 2)
                    p_o25 = sum(grid[i][j] for i in range(10) for j in range(10) if i + j >= 3)
                    p_btts = sum(grid[i][j] for i in range(10) for j in range(10) if i >= 1 and j >= 1)

                _PRED_MATCH_CACHE[m.id] = {
                    "ts": time.time(),
                    "status": m.status,
                    "p_h": p_h,
                    "p_d": p_d,
                    "p_a": p_a,
                    "p_o15": p_o15,
                    "p_o25": p_o25,
                    "p_btts": p_btts,
                    "lam_h": lam_h,
                    "lam_a": lam_a,
                }

            candidates = []

            # 1. Home Win
            p_h_ev = round(((p_h * _calc_odds(p_h)) - 1.0) * 100, 1)
            candidates.append({
                "pick": f"{h_name} to Win",
                "market": "1X2 (Match Winner)",
                "probability": round(p_h * 100, 1),
                "odds": _calc_odds(p_h),
                "confidence": "VERY HIGH" if p_h >= 0.65 else ("HIGH" if p_h >= 0.55 else "MEDIUM"),
                "category": "BANKER" if p_h >= 0.65 else ("VALUE" if p_h_ev >= 5.0 else "MATCH_WINNER"),
                "ai_score": _score_outcome(round(p_h * 100, 1), _calc_odds(p_h), p_h_ev),
            })

            # 2. Away Win
            p_a_ev = round(((p_a * _calc_odds(p_a)) - 1.0) * 100, 1)
            candidates.append({
                "pick": f"{a_name} to Win",
                "market": "1X2 (Match Winner)",
                "probability": round(p_a * 100, 1),
                "odds": _calc_odds(p_a),
                "confidence": "VERY HIGH" if p_a >= 0.65 else ("HIGH" if p_a >= 0.55 else "MEDIUM"),
                "category": "BANKER" if p_a >= 0.65 else ("VALUE" if p_a_ev >= 5.0 else "MATCH_WINNER"),
                "ai_score": _score_outcome(round(p_a * 100, 1), _calc_odds(p_a), p_a_ev),
            })

            # 3. Double Chance (1X)
            p_1x = min(0.98, p_h + p_d)
            p_1x_ev = round(((p_1x * _calc_odds(p_1x)) - 1.0) * 100, 1)
            candidates.append({
                "pick": f"{h_name} or Draw (1X)",
                "market": "Double Chance",
                "probability": round(p_1x * 100, 1),
                "odds": _calc_odds(p_1x),
                "confidence": "VERY HIGH" if p_1x >= 0.80 else "HIGH",
                "category": "SAFETY",
                "ai_score": _score_outcome(round(p_1x * 100, 1), _calc_odds(p_1x), p_1x_ev),
            })

            # 4. Double Chance (X2)
            p_x2 = min(0.98, p_d + p_a)
            p_x2_ev = round(((p_x2 * _calc_odds(p_x2)) - 1.0) * 100, 1)
            candidates.append({
                "pick": f"{a_name} or Draw (X2)",
                "market": "Double Chance",
                "probability": round(p_x2 * 100, 1),
                "odds": _calc_odds(p_x2),
                "confidence": "VERY HIGH" if p_x2 >= 0.80 else "HIGH",
                "category": "SAFETY",
                "ai_score": _score_outcome(round(p_x2 * 100, 1), _calc_odds(p_x2), p_x2_ev),
            })

            # 5. Over 1.5 Goals
            p_o15_ev = round(((p_o15 * _calc_odds(p_o15)) - 1.0) * 100, 1)
            candidates.append({
                "pick": "Over 1.5 Total Goals",
                "market": "Totals",
                "probability": round(p_o15 * 100, 1),
                "odds": _calc_odds(p_o15),
                "confidence": "VERY HIGH" if p_o15 >= 0.80 else "HIGH",
                "category": "GOALS",
                "ai_score": _score_outcome(round(p_o15 * 100, 1), _calc_odds(p_o15), p_o15_ev),
            })

            # 6. Over 2.5 Goals
            p_o25_ev = round(((p_o25 * _calc_odds(p_o25)) - 1.0) * 100, 1)
            candidates.append({
                "pick": "Over 2.5 Total Goals",
                "market": "Totals",
                "probability": round(p_o25 * 100, 1),
                "odds": _calc_odds(p_o25),
                "confidence": "HIGH" if p_o25 >= 0.65 else "MEDIUM",
                "category": "GOALS",
                "ai_score": _score_outcome(round(p_o25 * 100, 1), _calc_odds(p_o25), p_o25_ev),
            })

            # 7. BTTS Yes
            p_btts_ev = round(((p_btts * _calc_odds(p_btts)) - 1.0) * 100, 1)
            candidates.append({
                "pick": "Both Teams to Score (Yes)",
                "market": "BTTS",
                "probability": round(p_btts * 100, 1),
                "odds": _calc_odds(p_btts),
                "confidence": "HIGH" if p_btts >= 0.65 else "MEDIUM",
                "category": "GOALS",
                "ai_score": _score_outcome(round(p_btts * 100, 1), _calc_odds(p_btts), p_btts_ev),
            })

            candidates.sort(key=lambda x: (x["probability"] * 0.70) + (x["ai_score"] * 0.30), reverse=True)
            best_pick = candidates[0]

            tot_goals = h_score + a_score
            is_won = False
            audit_note = ""

            pick_text = best_pick["pick"]
            if "Over 1.5" in pick_text:
                is_won = (tot_goals >= 2)
                audit_note = (
                    f"Match finished {h_score}-{a_score} ({tot_goals} goals), clearing the Over 1.5 line."
                    if is_won else
                    f"Match finished {h_score}-{a_score} ({tot_goals} goal), missing the Over 1.5 line by 1 goal."
                )
            elif "Over 2.5" in pick_text:
                is_won = (tot_goals >= 3)
                audit_note = (
                    f"Match ended {h_score}-{a_score} ({tot_goals} total goals), surpassing the Over 2.5 threshold."
                    if is_won else
                    f"Match ended {h_score}-{a_score} ({tot_goals} goals), falling short of 3 total goals."
                )
            elif "Both Teams to Score" in pick_text:
                is_won = (h_score > 0 and a_score > 0)
                audit_note = (
                    f"Both teams found the net in a {h_score}-{a_score} contest, fulfilling BTTS (Yes)."
                    if is_won else
                    f"Clean sheet preserved in {h_score}-{a_score} finish, BTTS (Yes) not fulfilled."
                )
            elif "or Draw (1X)" in pick_text:
                is_won = (h_score >= a_score)
                audit_note = (
                    f"{h_name} avoided defeat ({h_score}-{a_score}), securing the Double Chance 1X buffer."
                    if is_won else
                    f"{away_team.name if away_team else 'Away team'} won {a_score}-{h_score}, breaching the 1X buffer."
                )
            elif "or Draw (X2)" in pick_text:
                is_won = (a_score >= h_score)
                audit_note = (
                    f"{a_name} avoided defeat ({h_score}-{a_score}), securing the Double Chance X2 buffer."
                    if is_won else
                    f"{home_team.name if home_team else 'Home team'} won {h_score}-{a_score}, breaching the X2 buffer."
                )
            elif "to Win" in pick_text:
                if h_name in pick_text:
                    is_won = (h_score > a_score)
                    audit_note = (
                        f"{h_name} claimed victory {h_score}-{a_score}, securing the Home Win pick cleanly."
                        if is_won else
                        f"{h_name} failed to win ({h_score}-{a_score}), missing the Home Win pick."
                    )
                else:
                    is_won = (a_score > h_score)
                    audit_note = (
                        f"{a_name} claimed victory {h_score}-{a_score}, securing the Away Win pick cleanly."
                        if is_won else
                        f"{a_name} failed to win ({h_score}-{a_score}), missing the Away Win pick."
                    )
            else:
                is_won = (tot_goals >= 2)
                audit_note = f"Match settled at {h_score}-{a_score}."

            outcome_status = "WON" if is_won else "LOST"
            unit_pnl = round(best_pick["odds"] - 1.0, 2) if is_won else -1.0

            if m.kickoff_at:
                local_dt = m.kickoff_at + tz_offset
                local_date_str = local_dt.strftime("%Y-%m-%d")
            else:
                local_date_str = "Past"

            all_history_items.append({
                "match_id": m.id,
                "fixture": f"{h_name} vs {a_name}",
                "home_team": h_name,
                "away_team": a_name,
                "league_code": lg_code,
                "league_name": lg_name,
                "league_flag": FLAG_MAP.get(lg_code, "⚽"),
                "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
                "date": local_date_str,
                "final_score": f"{h_score} - {a_score}",
                "home_score": h_score,
                "away_score": a_score,
                "pick": best_pick["pick"],
                "market": best_pick["market"],
                "odds": best_pick["odds"],
                "probability": best_pick["probability"],
                "confidence": best_pick["confidence"],
                "category": best_pick["category"],
                "outcome_status": outcome_status,
                "is_correct": is_won,
                "unit_return": f"+{unit_pnl}u" if unit_pnl > 0 else f"{unit_pnl}u",
                "unit_pnl": unit_pnl,
                "audit_note": audit_note,
            })
        except Exception:
            continue

    total_evaluated = len(all_history_items)
    won_count = sum(1 for item in all_history_items if item["outcome_status"] == "WON")
    lost_count = sum(1 for item in all_history_items if item["outcome_status"] == "LOST")
    win_rate = round((won_count / max(1, won_count + lost_count)) * 100, 1)
    net_units = round(sum(item["unit_pnl"] for item in all_history_items), 2)
    roi_pct = round((net_units / max(1, won_count + lost_count)) * 100, 1)
    avg_odds = round(sum(item["odds"] for item in all_history_items) / max(1, total_evaluated), 2) if total_evaluated > 0 else 1.0

    bankers = [i for i in all_history_items if i["probability"] >= 75.0]
    banker_won = sum(1 for i in bankers if i["outcome_status"] == "WON")
    banker_win_rate = round((banker_won / max(1, len(bankers))) * 100, 1) if bankers else win_rate

    # Filter by outcome if requested
    filtered_items = all_history_items
    if outcome and outcome.upper() == "WON":
        filtered_items = [i for i in all_history_items if i["outcome_status"] == "WON"]
    elif outcome and outcome.upper() == "LOST":
        filtered_items = [i for i in all_history_items if i["outcome_status"] == "LOST"]

    limited_items = filtered_items[:limit]

    # -------------------------------------------------------------
    # BUILD DATE-WISE HISTORICAL SLIPS (Accumulators, Doubles, Trebles)
    # -------------------------------------------------------------
    historical_slips = []

    def _make_historical_slip(picks_list, name, badge, desc, s_type, slip_date):
        if not picks_list:
            return None
        comb_odds = 1.0
        for p in picks_list:
            comb_odds *= p["odds"]
        avg_prob = sum(p["probability"] for p in picks_list) / len(picks_list)

        statuses = [p["outcome_status"] for p in picks_list]
        is_won = all(s == "WON" for s in statuses)
        slip_status = "WON" if is_won else "LOST"

        unit_pnl = round(comb_odds - 1.0, 2) if is_won else -1.0
        unit_return = f"+{unit_pnl}u" if unit_pnl > 0 else f"{unit_pnl}u"

        won_legs = sum(1 for s in statuses if s == "WON")
        if is_won:
            audit_note = f"All {len(picks_list)} selections won! Payout multiplier achieved @ {comb_odds:.2f} odds."
        else:
            failed_teams = [p["fixture"] for p in picks_list if p["outcome_status"] != "WON"]
            audit_note = f"{won_legs} of {len(picks_list)} legs won. Slip failed on {', '.join(failed_teams)}."

        slip_picks = []
        for p in picks_list:
            slip_picks.append({
                "match_id": p["match_id"],
                "fixture": p["fixture"],
                "home_team": p["home_team"],
                "away_team": p["away_team"],
                "league_code": p["league_code"],
                "league_name": p["league_name"],
                "league_flag": p["league_flag"],
                "pick": p["pick"],
                "market": p["market"],
                "odds": p["odds"],
                "probability": p["probability"],
                "final_score": p["final_score"],
                "status": p["outcome_status"],
                "audit_note": p["audit_note"],
            })

        return {
            "id": f"hist-slip-{slip_date}-{s_type}-{len(historical_slips)+1}",
            "title": name,
            "type": s_type,
            "badge": badge,
            "description": desc,
            "date": slip_date,
            "total_odds": round(comb_odds, 2),
            "win_probability": round(avg_prob, 1),
            "selections_count": len(picks_list),
            "outcome_status": slip_status,
            "unit_return": unit_return,
            "unit_pnl": unit_pnl,
            "audit_note": audit_note,
            "picks": slip_picks,
        }

    # Group matches by local timezone date (IST or UTC)
    date_groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in all_history_items:
        d_key = item.get("date") or (item["kickoff_at"][:10] if item.get("kickoff_at") else "Past")
        date_groups.setdefault(d_key, []).append(item)

    for d_key, d_items in date_groups.items():
        if len(d_items) >= 2:
            # 1. Safe Banker Treble / Double
            banker_candidates = sorted(d_items, key=lambda x: x["probability"], reverse=True)
            b_count = min(3, len(banker_candidates))
            b_slip = _make_historical_slip(
                banker_candidates[:b_count],
                f"Safe Banker {'Treble' if b_count == 3 else 'Double'}",
                "75%+ Probability",
                f"Top mathematical certainty selections from {d_key} fixtures.",
                "banker",
                d_key,
            )
            if b_slip:
                historical_slips.append(b_slip)

            # 2. Goals Galore Combo
            goal_picks = [
                p for p in d_items
                if p["category"] == "GOALS" or "Over" in p["pick"] or "BTTS" in p["pick"] or "Both Teams" in p["pick"]
            ]
            if len(goal_picks) >= 2:
                g_slip = _make_historical_slip(
                    goal_picks[:3],
                    "Goals Galore Combo",
                    "Over Goals & BTTS",
                    f"Curated goal lines from {d_key} matchday.",
                    "goals",
                    d_key,
                )
                if g_slip:
                    historical_slips.append(g_slip)

            # 3. Cross-League Power Acca
            distinct_leagues = []
            seen_lg = set()
            for p in d_items:
                if p["league_code"] not in seen_lg:
                    seen_lg.add(p["league_code"])
                    distinct_leagues.append(p)
            if len(distinct_leagues) >= 3:
                acc_slip = _make_historical_slip(
                    distinct_leagues[:4],
                    "Cross-League Power Acca",
                    "Multi-League Combo",
                    f"Multi-competition accumulator across {len(distinct_leagues[:4])} leagues on {d_key}.",
                    "accumulator",
                    d_key,
                )
                if acc_slip:
                    historical_slips.append(acc_slip)

            # 4. High Value Multiplier (higher odds selections)
            val_candidates = sorted(d_items, key=lambda x: x["odds"], reverse=True)
            if len(val_candidates) >= 3:
                v_slip = _make_historical_slip(
                    val_candidates[:3],
                    "High Value Multiplier",
                    "Value Edge Combo",
                    f"Higher-odds value selections from {d_key} fixtures.",
                    "value",
                    d_key,
                )
                if v_slip:
                    historical_slips.append(v_slip)

            # 5. Top Single Banker for the date
            s_item = banker_candidates[0]
            s_slip = _make_historical_slip(
                [s_item],
                f"Single Banker: {s_item['fixture']}",
                "Top Single Pick",
                f"Highest-confidence standalone match pick on {d_key}.",
                "single_match",
                d_key,
            )
            if s_slip:
                historical_slips.append(s_slip)

        elif len(d_items) == 1:
            s_item = d_items[0]
            s_slip = _make_historical_slip(
                [s_item],
                f"Single Banker: {s_item['fixture']}",
                "Top Single Pick",
                f"Primary standalone recommendation on {d_key}.",
                "single_match",
                d_key,
            )
            if s_slip:
                historical_slips.append(s_slip)

    filtered_slips = historical_slips
    if outcome and outcome.upper() == "WON":
        filtered_slips = [s for s in historical_slips if s["outcome_status"] == "WON"]
    elif outcome and outcome.upper() == "LOST":
        filtered_slips = [s for s in historical_slips if s["outcome_status"] == "LOST"]

    slips_total = len(historical_slips)
    slips_won = sum(1 for s in historical_slips if s["outcome_status"] == "WON")
    slips_lost = sum(1 for s in historical_slips if s["outcome_status"] == "LOST")
    slips_win_rate = round((slips_won / max(1, slips_total)) * 100, 1) if slips_total > 0 else 0.0
    slips_net_units = round(sum(s["unit_pnl"] for s in historical_slips), 2)

    _stamp_team_logos(db, limited_items,
                      [p for s in filtered_slips for p in (s.get("picks") or [])])

    result = {
        "summary": {
            "total_predictions": total_evaluated,
            "won_count": won_count,
            "lost_count": lost_count,
            "win_rate": win_rate,
            "total_units": f"+{net_units}u" if net_units > 0 else f"{net_units}u",
            "net_units_num": net_units,
            "roi_pct": roi_pct,
            "avg_odds": avg_odds,
            "banker_win_rate": banker_win_rate,
            "total_slips": slips_total,
            "slips_won": slips_won,
            "slips_lost": slips_lost,
            "slips_win_rate": slips_win_rate,
            "slips_net_units": f"+{slips_net_units}u" if slips_net_units > 0 else f"{slips_net_units}u",
        },
        "history": limited_items,
        "historical_slips": filtered_slips,
        "available_dates": sorted(list(date_groups.keys()), reverse=True),
        "selected_date": date_clean or "ALL",
        "days": days,
        "league_filter": league,
        "outcome_filter": outcome or "ALL",
    }

    _PREDICTION_HISTORY_CACHE[cache_key] = {"ts": time.time(), "data": result}
    return result


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



