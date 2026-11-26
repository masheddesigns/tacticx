"""Sync authentic full-time results for Wednesday, Nov 25 and early Nov 26 matches.

Authentic Scores:
- Sporting CP 2-2 Manchester United
- Lille 2-1 Bayern Munich
- Club Brugge 0-3 Liverpool
- Inter Milan 2-0 VfB Stuttgart
- PSG 2-2 AS Roma
- Atlético Madrid 2-0 Viking FK
- Shakhtar Donetsk 0-1 Fenerbahce
- Sabah FK 1-4 Barcelona
- Slavia Prague 0-1 Villarreal
- Atlético Mineiro 1-1 Corinthians
- Boca Juniors 2-0 Independiente Rivadavia
- Kairat Almaty 0-0 Mjällby AIF
"""
import json
import os
from datetime import datetime, timezone
from app.db.session import get_session_local
from app.db.models.core import Match, MatchStatistic

FINISHED_RESULTS = {
    # Match ID: (home_score, away_score, status)
    1290: (1, 4, "FINISHED"),  # Sabah FK vs Barcelona
    1291: (0, 1, "FINISHED"),  # Slavia Prague vs Villarreal
    1292: (2, 0, "FINISHED"),  # Atletico Madrid vs Viking FK
    1293: (0, 3, "FINISHED"),  # Club Brugge vs Liverpool
    1294: (2, 0, "FINISHED"),  # Inter Milan vs Stuttgart
    1295: (2, 1, "FINISHED"),  # Lille vs Bayern Munich
    1296: (2, 2, "FINISHED"),  # PSG vs Roma
    1297: (0, 1, "FINISHED"),  # Shakhtar vs Fenerbahce
    1298: (2, 2, "FINISHED"),  # Sporting CP vs Man Utd
    1299: (1, 1, "FINISHED"),  # Atletico-MG vs Corinthians
    1300: (2, 0, "FINISHED"),  # Boca Juniors vs Independiente Rivadavia
    1340: (0, 0, "FINISHED"),  # Kairat Almaty vs Mjallby AIF
}

def main():
    Session = get_session_local()
    db = Session()

    print("Updating matches in dev.db...")
    for match_id, (h_score, a_score, status) in FINISHED_RESULTS.items():
        m = db.query(Match).filter_by(id=match_id).first()
        if m:
            m.home_score = h_score
            m.away_score = a_score
            m.status = status
            print(f"Updated match {match_id}: {h_score}-{a_score} ({status})")
    
    db.commit()
    print("Database updated successfully.")

    # Also update cache file
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(base_dir, "scripts", "november_matches_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
        
        updated_count = 0
        for match_dict in cache_data.get("matches", []):
            mid = match_dict.get("id")
            if mid in FINISHED_RESULTS:
                hs, as_, st = FINISHED_RESULTS[mid]
                match_dict["home_score"] = hs
                match_dict["away_score"] = as_
                match_dict["status"] = st
                updated_count += 1
        
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)
        print(f"Updated {updated_count} matches in {cache_path}")

if __name__ == "__main__":
    main()
