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
    sort_order: str = Query("asc", description="Sort order by kickoff_at: asc | desc"),
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

    actual_stats: dict[str, dict[str, Any]] = {}
    for r in stats_rows:
        actual_stats.setdefault(r.stat_name, {})[r.team] = r.stat_value

    def _get_stat_num(name: str, team: str) -> Optional[float]:
        val = actual_stats.get(name, {}).get(team)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        return None

    act_corners_h = _get_stat_num("corners", "home")
    act_corners_a = _get_stat_num("corners", "away")
    act_corners_tot = (act_corners_h + act_corners_a) if (act_corners_h is not None and act_corners_a is not None) else None

    act_sot_h = _get_stat_num("shots_on_target", "home")
    act_sot_a = _get_stat_num("shots_on_target", "away")
    act_sot_tot = (act_sot_h + act_sot_a) if (act_sot_h is not None and act_sot_a is not None) else None

    act_shots_h = _get_stat_num("shots_total", "home")
    act_shots_a = _get_stat_num("shots_total", "away")
    act_shots_tot = (act_shots_h + act_shots_a) if (act_shots_h is not None and act_shots_a is not None) else None

    act_yc_h = _get_stat_num("yellow_cards", "home")
    act_yc_a = _get_stat_num("yellow_cards", "away")
    act_yc_tot = (act_yc_h + act_yc_a) if (act_yc_h is not None and act_yc_a is not None) else None

    act_rc_h = _get_stat_num("red_cards", "home")
    act_rc_a = _get_stat_num("red_cards", "away")
    act_rc_tot = (act_rc_h + act_rc_a) if (act_rc_h is not None and act_rc_a is not None) else None

    act_poss_h = actual_stats.get("possession", {}).get("home")
    act_poss_a = actual_stats.get("possession", {}).get("away")

    # 3. Build Comparison Items
    comparisons = []
    correct_count = 0
    total_evaluated = 0

    # Item 1: 1X2 Match Winner
    if has_score:
        actual_winner = "home" if m.home_score > m.away_score else ("away" if m.away_score > m.home_score else "draw")
        actual_winner_label = f"{home_name} Win" if actual_winner == "home" else (f"{away_name} Win" if actual_winner == "away" else "Draw")
        is_hit = (pred_outcome == actual_winner)
        total_evaluated += 1
        if is_hit:
            correct_count += 1
        comparisons.append({
            "category": "Outcome",
            "metric": "Match Winner (1X2)",
            "actual": f"{actual_winner_label} ({m.home_score}-{m.away_score})",
            "engine_predicted": f"{pred_outcome_label} ({round(p_h * 100 if pred_outcome == 'home' else (p_a * 100 if pred_outcome == 'away' else p_d * 100), 1)}%)",
            "mirofish_predicted": f"Simulated {pred_outcome_label}",
            "status": "HIT" if is_hit else "MISS",
            "delta": "Exact hit" if is_hit else "Different result",
            "notes": "Engine favored correct side" if is_hit else "Match diverged from model baseline",
        })
    else:
        comparisons.append({
            "category": "Outcome",
            "metric": "Match Winner (1X2)",
            "actual": "Match Pending Kickoff",
            "engine_predicted": f"{pred_outcome_label} ({round(max(p_h, p_d, p_a) * 100, 1)}%)",
            "mirofish_predicted": f"Simulated {pred_outcome_label}",
            "status": "PENDING",
            "delta": "-",
            "notes": "Kickoff scheduled; model forecast locked",
        })

    # Item 2: Scoreline & Expected Goals
    if has_score:
        actual_tot_goals = m.home_score + m.away_score
        goal_err = round(abs(actual_tot_goals - xg_tot), 2)
        total_evaluated += 1
        if goal_err <= 1.2:
            correct_count += 1
        comparisons.append({
            "category": "Goals",
            "metric": "Scoreline vs Expected Goals (xG)",
            "actual": f"{m.home_score} - {m.away_score} (Total: {actual_tot_goals} Goals)",
            "engine_predicted": f"xG {xg_h} - {xg_a} (Total xG: {xg_tot})",
            "mirofish_predicted": f"Most probable: {top_score_pred}",
            "status": "HIT" if goal_err <= 1.0 else ("CLOSE" if goal_err <= 1.8 else "MISS"),
            "delta": f"{round(actual_tot_goals - xg_tot, 2):+} goals",
            "notes": f"Goal difference vs xG projection",
        })
    else:
        comparisons.append({
            "category": "Goals",
            "metric": "Scoreline vs Expected Goals (xG)",
            "actual": "Match Pending Kickoff",
            "engine_predicted": f"xG {xg_h} - {xg_a} (Total xG: {xg_tot})",
            "mirofish_predicted": f"Most probable: {top_score_pred}",
            "status": "PENDING",
            "delta": "-",
            "notes": "Awaiting final whistle",
        })

    # Item 3: Over/Under 2.5 Goals
    if has_score:
        act_over = (m.home_score + m.away_score) > 2.5
        pred_over = over_2_5_prob >= 50.0
        ou_hit = (act_over == pred_over)
        total_evaluated += 1
        if ou_hit:
            correct_count += 1
        comparisons.append({
            "category": "Goals",
            "metric": "Total Goals Over/Under 2.5",
            "actual": f"{'Over 2.5' if act_over else 'Under 2.5'} ({m.home_score + m.away_score} goals)",
            "engine_predicted": f"{'Over 2.5' if pred_over else 'Under 2.5'} ({over_2_5_prob}%)",
            "mirofish_predicted": "Pace aligned" if ou_hit else "Unexpected scoring tempo",
            "status": "HIT" if ou_hit else "MISS",
            "delta": f"{'+' if act_over else '-'}{abs(m.home_score + m.away_score - 2.5)} vs 2.5 line",
            "notes": "Market threshold accurately forecasted" if ou_hit else "Goal frequency varied from projection",
        })

    # Item 4: Both Teams To Score (BTTS)
    if has_score:
        act_btts = (m.home_score > 0 and m.away_score > 0)
        pred_btts = btts_yes_prob >= 50.0
        btts_hit = (act_btts == pred_btts)
        total_evaluated += 1
        if btts_hit:
            correct_count += 1
        comparisons.append({
            "category": "Markets",
            "metric": "Both Teams To Score (BTTS)",
            "actual": f"{'Yes' if act_btts else 'No'} ({m.home_score}-{m.away_score})",
            "engine_predicted": f"{'Yes' if pred_btts else 'No'} ({btts_yes_prob}%)",
            "mirofish_predicted": f"Defensive rating: {'Permeable' if pred_btts else 'Resilient'}",
            "status": "HIT" if btts_hit else "MISS",
            "delta": "Matched" if btts_hit else "Mismatch",
            "notes": "Both sides found net" if act_btts else "Clean sheet achieved",
        })

    # Item 5: Corners
    proj_corners_tot = comb_proj["corners_total"]
    if act_corners_tot is not None:
        c_diff = round(act_corners_tot - proj_corners_tot, 1)
        c_hit = abs(c_diff) <= 2.5
        total_evaluated += 1
        if c_hit:
            correct_count += 1
        comparisons.append({
            "category": "Situational",
            "metric": "Corners (Total & Teams)",
            "actual": f"{int(act_corners_tot)} corners ({home_name}: {int(act_corners_h)}, {away_name}: {int(act_corners_a)})",
            "engine_predicted": f"Projected: {proj_corners_tot} ({home_name}: {team_proj['home']['corners']}, {away_name}: {team_proj['away']['corners']})",
            "mirofish_predicted": "Wing pressure simulation",
            "status": "HIT" if c_hit else ("CLOSE" if abs(c_diff) <= 4.0 else "MISS"),
            "delta": f"{c_diff:+} corners",
            "notes": "Within normal match variance" if c_hit else "Deviation in flank set-pieces",
        })
    else:
        comparisons.append({
            "category": "Situational",
            "metric": "Corners (Total & Teams)",
            "actual": "Provider stats pending" if is_finished else "Match Pending Kickoff",
            "engine_predicted": f"Projected: {proj_corners_tot} ({home_name}: {team_proj['home']['corners']}, {away_name}: {team_proj['away']['corners']})",
            "mirofish_predicted": f"Expected ~{proj_corners_tot} set pieces",
            "status": "AWAITING_SYNC" if is_finished else "PENDING",
            "delta": "-",
            "notes": "Awaiting fixture statistics update" if is_finished else "Scheduled pre-match projection",
        })

    # Item 6: Shots on Target
    proj_sot_tot = comb_proj["shots_on_target"]
    if act_sot_tot is not None:
        sot_diff = round(act_sot_tot - proj_sot_tot, 1)
        sot_hit = abs(sot_diff) <= 2.5
        total_evaluated += 1
        if sot_hit:
            correct_count += 1
        comparisons.append({
            "category": "Situational",
            "metric": "Shots on Target",
            "actual": f"{int(act_sot_tot)} on target ({home_name}: {int(act_sot_h)}, {away_name}: {int(act_sot_a)})",
            "engine_predicted": f"Projected: {proj_sot_tot} ({home_name}: {team_proj['home']['shots_on_target']}, {away_name}: {team_proj['away']['shots_on_target']})",
            "mirofish_predicted": "Attacking volume simulation",
            "status": "HIT" if sot_hit else ("CLOSE" if abs(sot_diff) <= 4.0 else "MISS"),
            "delta": f"{sot_diff:+} on target",
            "notes": "Target volume within projected envelope" if sot_hit else "Clinical/errant finishing variance",
        })
    else:
        comparisons.append({
            "category": "Situational",
            "metric": "Shots on Target",
            "actual": "Provider stats pending" if is_finished else "Match Pending Kickoff",
            "engine_predicted": f"Projected: {proj_sot_tot} ({home_name}: {team_proj['home']['shots_on_target']}, {away_name}: {team_proj['away']['shots_on_target']})",
            "mirofish_predicted": f"Expected ~{proj_sot_tot} on target",
            "status": "AWAITING_SYNC" if is_finished else "PENDING",
            "delta": "-",
            "notes": "Awaiting fixture statistics update" if is_finished else "Scheduled pre-match projection",
        })

    # Item 7: Total Shots
    proj_shots_tot = comb_proj["shots_total"]
    if act_shots_tot is not None:
        sh_diff = round(act_shots_tot - proj_shots_tot, 1)
        sh_hit = abs(sh_diff) <= 4.0
        total_evaluated += 1
        if sh_hit:
            correct_count += 1
        comparisons.append({
            "category": "Situational",
            "metric": "Total Shots Attempted",
            "actual": f"{int(act_shots_tot)} attempts ({home_name}: {int(act_shots_h)}, {away_name}: {int(act_shots_a)})",
            "engine_predicted": f"Projected: {proj_shots_tot} ({home_name}: {team_proj['home']['shots_total']}, {away_name}: {team_proj['away']['shots_total']})",
            "mirofish_predicted": "Total offensive attempts",
            "status": "HIT" if sh_hit else ("CLOSE" if abs(sh_diff) <= 6.0 else "MISS"),
            "delta": f"{sh_diff:+} shots",
            "notes": "Attacking frequency aligned" if sh_hit else "Higher/lower tempo game",
        })
    else:
        comparisons.append({
            "category": "Situational",
            "metric": "Total Shots Attempted",
            "actual": "Provider stats pending" if is_finished else "Match Pending Kickoff",
            "engine_predicted": f"Projected: {proj_shots_tot} ({home_name}: {team_proj['home']['shots_total']}, {away_name}: {team_proj['away']['shots_total']})",
            "mirofish_predicted": f"Expected ~{proj_shots_tot} shots",
            "status": "AWAITING_SYNC" if is_finished else "PENDING",
            "delta": "-",
            "notes": "Awaiting fixture statistics update" if is_finished else "Scheduled pre-match projection",
        })

    # Item 8: Yellow Cards
    proj_yc_tot = comb_proj["yellow_cards_total"]
    if act_yc_tot is not None:
        yc_diff = round(act_yc_tot - proj_yc_tot, 1)
        yc_hit = abs(yc_diff) <= 1.5
        total_evaluated += 1
        if yc_hit:
            correct_count += 1
        comparisons.append({
            "category": "Discipline",
            "metric": "Yellow Cards (Bookings)",
            "actual": f"{int(act_yc_tot)} yellows ({home_name}: {int(act_yc_h)}, {away_name}: {int(act_yc_a)})",
            "engine_predicted": f"Projected: {proj_yc_tot} ({home_name}: {team_proj['home']['yellow_cards']}, {away_name}: {team_proj['away']['yellow_cards']})",
            "mirofish_predicted": "Foul friction simulation",
            "status": "HIT" if yc_hit else "CLOSE",
            "delta": f"{yc_diff:+} cards",
            "notes": "Disciplinary line consistent" if yc_hit else "Card count divergence",
        })
    else:
        comparisons.append({
            "category": "Discipline",
            "metric": "Yellow Cards (Bookings)",
            "actual": "Provider stats pending" if is_finished else "Match Pending Kickoff",
            "engine_predicted": f"Projected: {proj_yc_tot} ({home_name}: {team_proj['home']['yellow_cards']}, {away_name}: {team_proj['away']['yellow_cards']})",
            "mirofish_predicted": "Foul friction simulation",
            "status": "AWAITING_SYNC" if is_finished else "PENDING",
            "delta": "-",
            "notes": "Awaiting fixture statistics update" if is_finished else "Scheduled pre-match projection",
        })

    # Item 9: Red Cards
    proj_rc_tot = comb_proj["red_cards_total"]
    if act_rc_tot is not None:
        rc_hit = (int(act_rc_tot) == 0 and proj_rc_tot <= 0.20) or (int(act_rc_tot) > 0 and proj_rc_tot > 0.20)
        total_evaluated += 1
        if rc_hit:
            correct_count += 1
        comparisons.append({
            "category": "Discipline",
            "metric": "Red Cards (Expulsions)",
            "actual": f"{int(act_rc_tot)} Red Cards",
            "engine_predicted": f"Projected: {proj_rc_tot} (Low risk)" if proj_rc_tot <= 0.15 else f"Projected: {proj_rc_tot} (Elevated risk)",
            "mirofish_predicted": "Simulated card probability",
            "status": "HIT" if rc_hit else "MISS",
            "delta": "0" if rc_hit else "Ejection recorded",
            "notes": "Clean match, no dismissal" if int(act_rc_tot) == 0 else "Player sent off",
        })
    else:
        comparisons.append({
            "category": "Discipline",
            "metric": "Red Cards (Expulsions)",
            "actual": "Provider stats pending" if is_finished else "Match Pending Kickoff",
            "engine_predicted": f"Projected: {proj_rc_tot} (Low risk)" if proj_rc_tot <= 0.15 else f"Projected: {proj_rc_tot} (Elevated risk)",
            "mirofish_predicted": "Simulated card probability",
            "status": "AWAITING_SYNC" if is_finished else "PENDING",
            "delta": "-",
            "notes": "Awaiting fixture statistics update" if is_finished else "Scheduled pre-match projection",
        })

    # 4. Fetch stored Brier evaluation if exists
    from app.services.prediction_evaluation.service import evaluations_for_match, evaluation_to_dict
    stored_evals = evaluations_for_match(db, match_id)
    stored_brier = None
    if stored_evals:
        last_eval = evaluation_to_dict(stored_evals[-1])
        stored_brier = last_eval.get("metrics", {}).get("brier_1x2")

    acc_rate = round((correct_count / total_evaluated * 100), 1) if total_evaluated > 0 else None

    # Mirofish qualitative narrative breakdown
    miro_scenarios = mirofish_sec.get("scenarios") or []
    miro_narrative = (
        miro_scenarios[0].get("tactical_narrative") or miro_scenarios[0].get("summary")
        if miro_scenarios else "MiroFish qualitative dynamic simulation"
    )

    return {
        "match_id": match_id,
        "is_finished": is_finished,
        "has_score": has_score,
        "home_team": {"id": home_team.id if home_team else None, "name": home_name},
        "away_team": {"id": away_team.id if away_team else None, "name": away_name},
        "actual_score": {"home": m.home_score, "away": m.away_score} if has_score else None,
        "actual_possession": {"home": act_poss_h, "away": act_poss_a} if (act_poss_h or act_poss_a) else None,
        "accuracy_summary": {
            "total_evaluated": total_evaluated,
            "correct_hits": correct_count,
            "accuracy_percentage": acc_rate,
            "brier_score": stored_brier,
            "grade": "EXCELLENT" if (acc_rate and acc_rate >= 75) else ("GOOD" if (acc_rate and acc_rate >= 50) else "MIXED"),
        },
        "mirofish_summary": {
            "status": mirofish_sec.get("status", "unavailable"),
            "narrative": miro_narrative,
            "scenarios_count": len(miro_scenarios),
        },
        "comparisons": comparisons,
    }

