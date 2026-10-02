"""Fetch genuine match statistics from API-Football for finished matches and persist to MatchStatistic table."""
from __future__ import annotations

import json
import time
import urllib.request
import sys

sys.path.insert(0, ".")

from app.db.models.core import Match, MatchStatistic
from app.db.session import get_session_local

STAT_MAP = {
    "Total Shots": "shots_total",
    "Shots on Goal": "shots_on_target",
    "Corner Kicks": "corners",
    "Ball Possession": "possession",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Fouls": "fouls",
    "expected_goals": "xg",
}


def fetch_stats(fixture_id: str) -> list[dict]:
    url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
    headers = {"x-apisports-key": "f1da5a48dd4965ed81ed9444e8191ce4"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", [])
    except Exception as e:
        print(f"Error fetching stats for fixture {fixture_id}: {e}")
        return []


def sync_finished_stats() -> None:
    SessionLocal = get_session_local()
    db = SessionLocal()

    matches = (
        db.query(Match)
        .filter(Match.status == "FINISHED")
        .filter(Match.provider_match_id != "")
        .filter(Match.provider_match_id != None)
        .order_by(Match.kickoff_at.desc())
        .limit(25)
        .all()
    )

    print(f"Checking statistics for {len(matches)} finished matches...")
    added_count = 0

    for m in matches:
        # Check if stats already exist
        existing = db.query(MatchStatistic).filter_by(match_id=m.id).first()
        if existing:
            print(f"Match {m.id} already has stats, skipping.")
            continue

        print(f"Fetching stats for Match {m.id} (provider_id: {m.provider_match_id})...")
        resp = fetch_stats(m.provider_match_id)
        if len(resp) < 2:
            print(f"  No stats returned for Match {m.id}")
            continue

        for idx, team_data in enumerate(resp):
            team_role = "home" if idx == 0 else "away"
            stats_list = team_data.get("statistics", [])
            for item in stats_list:
                st_type = item.get("type")
                raw_val = item.get("value")
                if st_type in STAT_MAP and raw_val is not None:
                    canonical_name = STAT_MAP[st_type]
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
                    added_count += 1

        db.commit()
        time.sleep(0.3)

    print(f"Successfully inserted {added_count} match statistics rows!")
    db.close()


if __name__ == "__main__":
    sync_finished_stats()
