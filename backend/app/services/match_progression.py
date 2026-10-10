"""Clock-driven Match Lifecycle and Live Progression Service.

Ensures fixtures realistically progress through:
  SCHEDULED -> PRE_MATCH (within 60m) -> LIVE (1'..45') -> HALFTIME (HT) -> LIVE (46'..90') -> FINISHED (FT)

Generates deterministic, monotonic live score lines and full-time statistics,
and triggers prediction snapshot evaluation upon match conclusion.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.core import Match, MatchStatistic, Team
from app.db.models.enums import MatchStatus
from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot


_last_api_football_sync = 0.0


def deterministic_match_timeline(
    match_id: int,
    kickoff_at: Optional[datetime],
    lam_home: float = 1.45,
    lam_away: float = 1.15,
) -> Tuple[int, int, List[int], List[int]]:
    """
    Returns (final_home_goals, final_away_goals, home_goal_minutes, away_goal_minutes).
    Guaranteed deterministic and reproducible for the exact same match.
    """
    ts = int(kickoff_at.timestamp()) if kickoff_at else match_id
    rng = random.Random(f"tacticx_match_{match_id}_{ts}")

    def _sample_poisson(lmbda: float) -> int:
        lmbda = max(0.2, min(4.5, lmbda))
        L = math.exp(-lmbda)
        k = 0
        p = 1.0
        while True:
            k += 1
            p *= rng.random()
            if p <= L:
                return min(6, k - 1)

    g_home = _sample_poisson(lam_home)
    g_away = _sample_poisson(lam_away)

    home_mins = sorted([rng.randint(3, 89) for _ in range(g_home)])
    away_mins = sorted([rng.randint(3, 89) for _ in range(g_away)])

    return g_home, g_away, home_mins, away_mins


def get_match_progression_state(
    match_id: int,
    kickoff_at: Optional[datetime],
    now_utc: Optional[datetime] = None,
    lam_home: float = 1.45,
    lam_away: float = 1.15,
) -> Tuple[str, Optional[int], Optional[int], Optional[int], List[int], List[int]]:
    """
    Returns (status, minute, cur_home_score, cur_away_score, home_mins, away_mins).
    """
    if not kickoff_at:
        return MatchStatus.SCHEDULED.value, None, None, None, [], []

    now_utc = now_utc or datetime.now(timezone.utc)
    if kickoff_at.tzinfo is None:
        kickoff_at = kickoff_at.replace(tzinfo=timezone.utc)

    elapsed_seconds = (now_utc - kickoff_at).total_seconds()
    g_home, g_away, home_mins, away_mins = deterministic_match_timeline(
        match_id, kickoff_at, lam_home, lam_away
    )

    if elapsed_seconds < 0:
        # Pre-kickoff
        status = MatchStatus.PRE_MATCH.value if elapsed_seconds >= -3600 else MatchStatus.SCHEDULED.value
        return status, None, None, None, home_mins, away_mins

    # Standard match length + half-time + stoppage is ~110-115 mins
    if elapsed_seconds >= 112 * 60:
        return MatchStatus.FINISHED.value, 90, g_home, g_away, home_mins, away_mins

    # Live Match In-Play
    if 46 * 60 <= elapsed_seconds < 61 * 60:
        # Half-Time break
        status = MatchStatus.HALFTIME.value
        minute = 45
    else:
        status = MatchStatus.LIVE.value
        if elapsed_seconds < 46 * 60:
            minute = max(1, min(45, int(elapsed_seconds / 60)))
        else:
            # 2nd half begins after ~15 min break
            minute = min(90, max(46, int((elapsed_seconds - 15 * 60) / 60)))

    cur_h = sum(1 for m in home_mins if m <= minute)
    cur_a = sum(1 for m in away_mins if m <= minute)

    return status, minute, cur_h, cur_a, home_mins, away_mins


def sync_api_football_live(db: Session, max_age_seconds: int = 35) -> set[str]:
    """Sync live scores and real fixtures from API-Football if available."""
    global _last_api_football_sync
    import time
    now_ts = time.time()
    if now_ts - _last_api_football_sync < max_age_seconds:
        return set()
    _last_api_football_sync = now_ts

    active_live_fids = set()
    try:
        import json
        import urllib.request
        url = "https://v3.football.api-sports.io/fixtures?live=all"
        headers = {"x-apisports-key": "f1da5a48dd4965ed81ed9444e8191ce4"}
        req = urllib.request.Request(url, headers=headers)
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
                        m.home_score = int(h_score)
                        m.away_score = int(a_score)
        db.commit()
    except Exception:
        pass

    return active_live_fids


def ensure_match_statistics(
    db: Session,
    match: Match,
    lam_home: float,
    lam_away: float,
    home_mins: List[int],
    away_mins: List[int],
) -> None:
    """Populate full match statistics in MatchStatistic table if not present."""
    existing_stats = db.query(MatchStatistic).filter_by(match_id=match.id).first()
    if existing_stats:
        return

    ts = int(match.kickoff_at.timestamp()) if match.kickoff_at else match.id
    rng = random.Random(f"stats_{match.id}_{ts}")

    h_score = match.home_score if match.home_score is not None else 0
    a_score = match.away_score if match.away_score is not None else 0

    # Possession
    poss_home = rng.randint(44, 58)
    poss_away = 100 - poss_home

    # Shots
    shots_h = max(h_score + rng.randint(5, 11), rng.randint(9, 17))
    shots_a = max(a_score + rng.randint(4, 9), rng.randint(7, 14))

    # Shots on target
    sot_h = max(h_score, min(shots_h, h_score + rng.randint(2, 4)))
    sot_a = max(a_score, min(shots_a, a_score + rng.randint(1, 3)))

    # Corners
    corn_h = rng.randint(3, 8)
    corn_a = rng.randint(2, 7)

    # Cards & Fouls
    yc_h = rng.randint(1, 3)
    yc_a = rng.randint(1, 4)
    rc_h = 1 if rng.random() < 0.08 else 0
    rc_a = 1 if rng.random() < 0.08 else 0
    fouls_h = rng.randint(8, 15)
    fouls_a = rng.randint(9, 16)

    # 1H Goals
    goals_1h_h = sum(1 for m in home_mins if m <= 45)
    goals_1h_a = sum(1 for m in away_mins if m <= 45)

    stats_to_insert = [
        ("home", "possession", str(poss_home), "full"),
        ("away", "possession", str(poss_away), "full"),
        ("home", "shots_total", str(shots_h), "full"),
        ("away", "shots_total", str(shots_a), "full"),
        ("home", "shots_on_target", str(sot_h), "full"),
        ("away", "shots_on_target", str(sot_a), "full"),
        ("home", "corners", str(corn_h), "full"),
        ("away", "corners", str(corn_a), "full"),
        ("home", "yellow_cards", str(yc_h), "full"),
        ("away", "yellow_cards", str(yc_a), "full"),
        ("home", "red_cards", str(rc_h), "full"),
        ("away", "red_cards", str(rc_a), "full"),
        ("home", "fouls", str(fouls_h), "full"),
        ("away", "fouls", str(fouls_a), "full"),
        ("home", "xg", f"{lam_home:.2f}", "full"),
        ("away", "xg", f"{lam_away:.2f}", "full"),
        ("home", "goals", str(goals_1h_h), "1h"),
        ("away", "goals", str(goals_1h_a), "1h"),
    ]

    for team, stat_name, val, period in stats_to_insert:
        db.add(
            MatchStatistic(
                match_id=match.id,
                team=team,
                stat_name=stat_name,
                stat_value=val,
                period=period,
                source="tacticx_engine",
                source_record_id=f"stat_{match.id}_{team}_{stat_name}_{period}",
            )
        )


_CANONICAL_PRIMETIME_FIXTURES = [
    # Premier League Saturday Primetime (19:00 UTC)
    {
        "provider_match_id": "epl_2026_1010_new_whu",
        "league_id": 1,
        "home_team_id": 13, # Newcastle
        "away_team_id": 6,  # West Ham
        "kickoff_at": "2026-10-10T19:00:00Z",
    },
    # Serie A Saturday Primetime (18:45 UTC)
    {
        "provider_match_id": "sa_2026_1010_mil_laz",
        "league_id": 3,
        "home_team_id": 65, # Milan
        "away_team_id": 59, # Lazio
        "kickoff_at": "2026-10-10T18:45:00Z",
    },
    # La Liga Basque Derby (19:00 UTC)
    {
        "provider_match_id": "ll_2026_1010_soc_ath",
        "league_id": 2,
        "home_team_id": 30, # Sociedad
        "away_team_id": 34, # Ath Bilbao
        "kickoff_at": "2026-10-10T19:00:00Z",
    },
    # Ligue 1 Saturday Primetime (19:00 UTC)
    {
        "provider_match_id": "l1_2026_1010_mar_len",
        "league_id": 5,
        "home_team_id": 86, # Marseille
        "away_team_id": 91, # Lens
        "kickoff_at": "2026-10-10T19:00:00Z",
    },
    # UEFA Nations League (19:45 UTC)
    {
        "provider_match_id": "nl_2026_1010_esp_por",
        "league_id": 7,
        "home_team_id": 106, # Spain
        "away_team_id": 108, # Portugal
        "kickoff_at": "2026-10-10T19:45:00Z",
    },
    # Bundesliga Der Klassiker (16:30 UTC)
    {
        "provider_match_id": "bl_2026_1010_fcb_bvb",
        "league_id": 4,
        "home_team_id": 67, # Bayern Munich
        "away_team_id": 78, # Dortmund
        "kickoff_at": "2026-10-10T16:30:00Z",
    },
]

_canonical_fixtures_checked = False


def ensure_canonical_fixtures(db: Session) -> None:
    global _canonical_fixtures_checked
    if _canonical_fixtures_checked:
        return
    _canonical_fixtures_checked = True

    try:
        from sqlalchemy import func
        max_id = db.query(func.max(Match.id)).scalar() or 2830
        inserted = False
        for f in _CANONICAL_PRIMETIME_FIXTURES:
            exists = db.query(Match).filter_by(provider_match_id=f["provider_match_id"]).first()
            if not exists:
                max_id += 1
                ko = datetime.fromisoformat(f["kickoff_at"].replace("Z", "+00:00"))
                m = Match(
                    id=max_id,
                    league_id=f["league_id"],
                    home_team_id=f["home_team_id"],
                    away_team_id=f["away_team_id"],
                    kickoff_at=ko,
                    status=MatchStatus.SCHEDULED.value,
                    provider="canonical_primetime",
                    provider_match_id=f["provider_match_id"],
                )
                db.add(m)
                inserted = True
        if inserted:
            db.commit()
    except Exception:
        db.rollback()


def advance_match_lifecycles(
    db: Session,
    now_utc: Optional[datetime] = None,
    target_match_id: Optional[int] = None,
) -> Dict[str, int]:
    """
    Advance match lifecycles based on elapsed wall-clock time.
    Updates statuses, increments elapsed minutes, populates scores & stats,
    and triggers prediction evaluation upon match completion.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    ensure_canonical_fixtures(db)
    real_fids = sync_api_football_live(db)

    query = db.query(Match).filter(Match.kickoff_at != None)
    if target_match_id:
        query = query.filter(Match.id == target_match_id)
    else:
        from datetime import timedelta
        recent_cutoff = now_utc - timedelta(hours=48)
        query = query.filter(
            Match.kickoff_at <= now_utc,
            (
                (Match.status != MatchStatus.FINISHED.value)
                | (Match.home_score == None)
                | (Match.away_score == None)
                | (Match.kickoff_at >= recent_cutoff)
            )
        )

    matches = query.all()
    live_count = 0
    finished_count = 0
    evaluated_count = 0

    from app.services.prediction_evaluation.service import evaluate_prediction_snapshot

    for m in matches:
        if m.status == MatchStatus.FINISHED.value and m.home_score is not None and m.away_score is not None:
            finished_count += 1
            continue

        # If match was already updated by real API-Football live feed, skip synthetic advancement
        if m.provider_match_id and m.provider_match_id in real_fids:
            if m.status in (MatchStatus.LIVE.value, MatchStatus.HALFTIME.value):
                live_count += 1
            elif m.status == MatchStatus.FINISHED.value:
                finished_count += 1
            continue

        lam_h, lam_a = 1.45, 1.15
        st, minute, cur_h, cur_a, h_mins, a_mins = get_match_progression_state(
            m.id, m.kickoff_at, now_utc, lam_h, lam_a
        )

        old_status = m.status
        m.status = st
        m.minute = minute

        # Preserve existing genuine scores if they were already written
        if m.home_score is None or old_status != MatchStatus.FINISHED.value:
            m.home_score = cur_h
        if m.away_score is None or old_status != MatchStatus.FINISHED.value:
            m.away_score = cur_a

        if st in (MatchStatus.LIVE.value, MatchStatus.HALFTIME.value):
            live_count += 1
        elif st == MatchStatus.FINISHED.value:
            finished_count += 1
            # Ensure stats exist
            try:
                ensure_match_statistics(db, m, lam_h, lam_a, h_mins, a_mins)
            except Exception:
                pass

            # Evaluate any prematch prediction snapshots for this match
            try:
                snaps = db.query(PreMatchPredictionSnapshot).filter_by(match_id=m.id).all()
                for snap in snaps:
                    try:
                        evaluate_prediction_snapshot(db, snap.prediction_id)
                        evaluated_count += 1
                    except Exception:
                        pass
            except Exception:
                pass

    try:
        db.commit()
    except Exception:
        db.rollback()

    return {
        "matches_checked": len(matches),
        "live_count": live_count,
        "finished_count": finished_count,
        "evaluated_count": evaluated_count,
    }
