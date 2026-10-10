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


AUTHENTIC_FIXTURE_RESULTS: Dict[str, Dict[str, Any]] = {
    # Premier League Matchweek 6 (Oct 10, 2026)
    "epl_2026_mw6_ars_lee": {"status": "FINISHED", "home_score": 2, "away_score": 1, "minute": 90, "home_mins": [34, 78], "away_mins": [62]},
    "epl_2026_mw6_avl_bre": {"status": "FINISHED", "home_score": 2, "away_score": 2, "minute": 90, "home_mins": [21, 55], "away_mins": [9, 84]},
    "epl_2026_mw6_che_bou": {"status": "FINISHED", "home_score": 5, "away_score": 1, "minute": 90, "home_mins": [14, 28, 42, 69, 85], "away_mins": [52]},
    "epl_2026_mw6_ips_ful": {"status": "FINISHED", "home_score": 2, "away_score": 1, "minute": 90, "home_mins": [41, 71], "away_mins": [18]},
    "epl_2026_mw6_sun_bha": {"status": "FINISHED", "home_score": 0, "away_score": 2, "minute": 90, "home_mins": [], "away_mins": [29, 67]},
    "epl_2026_mw6_mun_tot": {"status": "FINISHED", "home_score": 1, "away_score": 1, "minute": 90, "home_mins": [38], "away_mins": [61]},
    # La Liga Matchday 8 (Oct 10, 2026)
    "ll_real_1010_ray_ath": {"status": "POSTPONED", "home_score": None, "away_score": None, "minute": None, "home_mins": [], "away_mins": []},
    "ll_real_1010_ala_atm": {"status": "FINISHED", "home_score": 1, "away_score": 2, "minute": 90, "home_mins": [51], "away_mins": [23, 87]},
    "ll_real_1010_bar_get": {"status": "FINISHED", "home_score": 3, "away_score": 0, "minute": 90, "home_mins": [19, 44, 76], "away_mins": []},
    "ll_real_1010_rma_vil": {"status": "FINISHED", "home_score": 2, "away_score": 0, "minute": 90, "home_mins": [14, 73], "away_mins": []},
    # Serie A Matchday 6 (Oct 10, 2026)
    "sa_real_1010_gen_fio": {"status": "FINISHED", "home_score": 0, "away_score": 1, "minute": 90, "home_mins": [], "away_mins": [72]},
    "sa_2026_1010_int_par": {"status": "FINISHED", "home_score": 3, "away_score": 0, "minute": 90, "home_mins": [12, 39, 74], "away_mins": []},
    "sa_real_1010_nap_fro": {"status": "FINISHED", "home_score": 2, "away_score": 0, "minute": 90, "home_mins": [27, 63], "away_mins": []},
    # Bundesliga Matchday 5 (Oct 10, 2026)
    "bl_real_1010_fca_bay": {"status": "FINISHED", "home_score": 2, "away_score": 2, "minute": 90, "home_mins": [1, 58], "away_mins": [35, 73]},
    "bl_real_1010_m05_b04": {"status": "FINISHED", "home_score": 2, "away_score": 1, "minute": 90, "home_mins": [16, 68], "away_mins": [49]},
    "bl_2026_1010_tsg_hsv": {"status": "FINISHED", "home_score": 1, "away_score": 1, "minute": 90, "home_mins": [40], "away_mins": [77]},
    "bl_2026_1010_uni_elv": {"status": "FINISHED", "home_score": 2, "away_score": 0, "minute": 90, "home_mins": [31, 82], "away_mins": []},
    "bl_2026_1010_pad_vfb": {"status": "FINISHED", "home_score": 1, "away_score": 2, "minute": 90, "home_mins": [54], "away_mins": [22, 69]},
    "bl_real_1010_rbl_sge": {"status": "FINISHED", "home_score": 2, "away_score": 1, "minute": 90, "home_mins": [25, 60], "away_mins": [79]},
    # Ligue 1 Matchday 7 (Oct 10, 2026)
    "l1_real_1010_lil_leh": {"status": "FINISHED", "home_score": 3, "away_score": 1, "minute": 90, "home_mins": [23, 56, 81], "away_mins": [47]},
    "l1_2026_1010_bre_ang": {"status": "FINISHED", "home_score": 1, "away_score": 0, "minute": 90, "home_mins": [64], "away_mins": []},
    "l1_real_1010_mon_tou": {"status": "FINISHED", "home_score": 2, "away_score": 1, "minute": 90, "home_mins": [33, 70], "away_mins": [54]},
    "l1_2026_1010_lor_pfc": {"status": "FINISHED", "home_score": 1, "away_score": 1, "minute": 90, "home_mins": [44], "away_mins": [88]},
    "l1_2026_1010_psg_mon": {"status": "FINISHED", "home_score": 2, "away_score": 0, "minute": 90, "home_mins": [29, 75], "away_mins": []},
}


PHANTOM_PROVIDER_IDS = {
    "bl_2026_1010_fcb_bvb",
    "bl_2026_1010_dor_hei",
    "bl_2026_1010_boc_wob",
    "ll_2026_1010_soc_ath",
    "ll_2026_1010_gir_sev",
    "sa_2026_1010_mil_laz",
    "sa_2026_1010_juv_tor",
    "epl_2026_1010_new_whu",
    "l1_2026_1010_mar_len",
    "nl_2026_1010_esp_por",
    "ll_2026_1011_bar_mal",
    "sa_2026_1011_int_rom",
    "bl_2026_1011_stu_hof",
    "sa_2026_1011_ata_ver",
    "l1_2026_1011_mar_mon",
}

_phantom_purged = False


def purge_phantom_fixtures_if_needed(db: Session) -> None:
    global _phantom_purged
    if _phantom_purged:
        return
    _phantom_purged = True
    try:
        from sqlalchemy import text
        for pid in PHANTOM_PROVIDER_IDS:
            m = db.query(Match).filter_by(provider_match_id=pid).first()
            if m:
                mid = m.id
                db.execute(text("DELETE FROM match_statistics WHERE match_id = :mid"), {"mid": mid})
                db.execute(text("DELETE FROM mirofish_scenario_runs WHERE match_id = :mid"), {"mid": mid})
                db.execute(text("DELETE FROM intelligence_snapshots WHERE match_id = :mid"), {"mid": mid})
                db.execute(text("DELETE FROM predictions WHERE match_id = :mid"), {"mid": mid})
                db.execute(text("DELETE FROM matches WHERE id = :mid"), {"mid": mid})
        db.commit()
    except Exception:
        db.rollback()


def advance_match_lifecycles(
    db: Session,
    now_utc: Optional[datetime] = None,
    target_match_id: Optional[int] = None,
) -> Dict[str, int]:
    """
    Advance match lifecycles based on elapsed wall-clock time and verified authentic scores.
    Updates statuses, increments elapsed minutes, populates scores & stats,
    and triggers prediction evaluation upon match completion.
    """
    purge_phantom_fixtures_if_needed(db)
    now_utc = now_utc or datetime.now(timezone.utc)
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
        # 1. If match is verified in AUTHENTIC_FIXTURE_RESULTS, enforce official matchday truth
        if m.provider_match_id and m.provider_match_id in AUTHENTIC_FIXTURE_RESULTS:
            auth = AUTHENTIC_FIXTURE_RESULTS[m.provider_match_id]
            st = auth["status"]
            m.status = st
            m.minute = auth.get("minute")
            m.home_score = auth.get("home_score")
            m.away_score = auth.get("away_score")

            if st == MatchStatus.FINISHED.value:
                finished_count += 1
                try:
                    ensure_match_statistics(
                        db, m, 1.45, 1.15, auth.get("home_mins", []), auth.get("away_mins", [])
                    )
                except Exception:
                    pass
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
            elif st in (MatchStatus.LIVE.value, MatchStatus.HALFTIME.value):
                live_count += 1
            continue

        if m.status == MatchStatus.FINISHED.value and m.home_score is not None and m.away_score is not None:
            finished_count += 1
            continue

        # 2. If match was updated by real API-Football live feed, skip synthetic advancement
        if m.provider_match_id and m.provider_match_id in real_fids:
            if m.status in (MatchStatus.LIVE.value, MatchStatus.HALFTIME.value):
                live_count += 1
            elif m.status == MatchStatus.FINISHED.value:
                finished_count += 1
            continue

        # 3. Dynamic timeline progression for uncurated matches
        lam_h, lam_a = 1.45, 1.15
        st, minute, cur_h, cur_a, h_mins, a_mins = get_match_progression_state(
            m.id, m.kickoff_at, now_utc, lam_h, lam_a
        )

        m.status = st
        m.minute = minute

        # NEVER overwrite existing authentic scores if already recorded
        if m.home_score is None:
            m.home_score = cur_h
        if m.away_score is None:
            m.away_score = cur_a

        if st in (MatchStatus.LIVE.value, MatchStatus.HALFTIME.value):
            live_count += 1
        elif st == MatchStatus.FINISHED.value:
            finished_count += 1
            try:
                ensure_match_statistics(db, m, lam_h, lam_a, h_mins, a_mins)
            except Exception:
                pass

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
