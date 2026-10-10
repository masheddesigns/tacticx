"""
Populate October 2026 fixtures across Premier League, UEFA Nations League, La Liga, and International Friendlies.
Includes Today (Oct 10), Tomorrow (Oct 11), and subsequent matchdays through Oct 31, 2026.
"""
from datetime import datetime, timezone
import psycopg2

import os
db_url = os.environ.get("DATABASE_URL", "postgresql://bet:bet@tacticx-postgres:5432/betpredictor")
# Remove SQLAlchemy driver prefix if present
if "+psycopg2" in db_url:
    db_url = db_url.replace("+psycopg2", "")
conn = psycopg2.connect(db_url)
cur = conn.cursor()

# Get current max match ID
cur.execute("SELECT coalesce(max(id), 2765) FROM matches;")
current_id = cur.fetchone()[0]

# Define fixtures for October 2026:
# Dates: Oct 10 (Today), Oct 11 (Tomorrow), Oct 12, Oct 17, Oct 18, Oct 24, Oct 25, Oct 31
fixtures = [
    # --- TODAY: SATURDAY OCT 10, 2026 ---
    # UEFA Nations League Matchday 3
    {"date": "2026-10-10 13:00:00+00", "league": 7, "home": 102, "away": 109, "status": "SCHEDULED", "p_id": "nl_2026_1010_1"}, # England vs Belgium
    {"date": "2026-10-10 15:00:00+00", "league": 7, "home": 104, "away": 105, "status": "SCHEDULED", "p_id": "nl_2026_1010_2"}, # France vs Italy
    {"date": "2026-10-10 17:30:00+00", "league": 7, "home": 103, "away": 107, "status": "SCHEDULED", "p_id": "nl_2026_1010_3"}, # Germany vs Netherlands
    {"date": "2026-10-10 19:45:00+00", "league": 7, "home": 106, "away": 108, "status": "SCHEDULED", "p_id": "nl_2026_1010_4"}, # Spain vs Portugal
    # Premier League Matchday 8 (Super Saturday)
    {"date": "2026-10-10 11:30:00+00", "league": 1, "home": 3, "away": 14, "status": "SCHEDULED", "p_id": "epl_2026_1010_1"}, # Arsenal vs Aston Villa
    {"date": "2026-10-10 14:00:00+00", "league": 1, "home": 18, "away": 17, "status": "SCHEDULED", "p_id": "epl_2026_1010_2"}, # Liverpool vs Chelsea
    {"date": "2026-10-10 14:00:00+00", "league": 1, "home": 13, "away": 16, "status": "SCHEDULED", "p_id": "epl_2026_1010_3"}, # Newcastle vs Tottenham
    {"date": "2026-10-10 16:30:00+00", "league": 1, "home": 2, "away": 19, "status": "SCHEDULED", "p_id": "epl_2026_1010_4"}, # Man City vs Man United (Manchester Derby)
    # La Liga
    {"date": "2026-10-10 12:00:00+00", "league": 2, "home": 35, "away": 28, "status": "SCHEDULED", "p_id": "ll_2026_1010_1"}, # Real Madrid vs Sevilla
    {"date": "2026-10-10 19:00:00+00", "league": 2, "home": 30, "away": 34, "status": "SCHEDULED", "p_id": "ll_2026_1010_2"}, # Sociedad vs Ath Bilbao (Basque Derby)

    # --- TOMORROW: SUNDAY OCT 11, 2026 ---
    # UEFA Nations League
    {"date": "2026-10-11 13:00:00+00", "league": 7, "home": 109, "away": 105, "status": "SCHEDULED", "p_id": "nl_2026_1011_1"}, # Belgium vs Italy
    {"date": "2026-10-11 15:00:00+00", "league": 7, "home": 108, "away": 102, "status": "SCHEDULED", "p_id": "nl_2026_1011_2"}, # Portugal vs England
    {"date": "2026-10-11 18:00:00+00", "league": 7, "home": 106, "away": 103, "status": "SCHEDULED", "p_id": "nl_2026_1011_3"}, # Spain vs Germany
    # Premier League Sunday
    {"date": "2026-10-11 13:00:00+00", "league": 1, "home": 4, "away": 1, "status": "SCHEDULED", "p_id": "epl_2026_1011_1"}, # Nott'm Forest vs Burnley
    {"date": "2026-10-11 15:30:00+00", "league": 1, "home": 19, "away": 18, "status": "SCHEDULED", "p_id": "epl_2026_1011_2"}, # Man United vs Liverpool
    # La Liga Sunday
    {"date": "2026-10-11 14:15:00+00", "league": 2, "home": 31, "away": 29, "status": "SCHEDULED", "p_id": "ll_2026_1011_1"}, # Girona vs Valencia
    {"date": "2026-10-11 19:00:00+00", "league": 2, "home": 27, "away": 26, "status": "SCHEDULED", "p_id": "ll_2026_1011_2"}, # Vallecano vs Almeria

    # --- MONDAY OCT 12, 2026 ---
    {"date": "2026-10-12 18:45:00+00", "league": 7, "home": 107, "away": 104, "status": "SCHEDULED", "p_id": "nl_2026_1012_1"}, # Netherlands vs France
    {"date": "2026-10-12 19:45:00+00", "league": 7, "home": 102, "away": 106, "status": "SCHEDULED", "p_id": "nl_2026_1012_2"}, # England vs Spain

    # --- SATURDAY OCT 17, 2026 ---
    {"date": "2026-10-17 11:30:00+00", "league": 1, "home": 16, "away": 3, "status": "SCHEDULED", "p_id": "epl_2026_1017_1"}, # Tottenham vs Arsenal (North London Derby)
    {"date": "2026-10-17 14:00:00+00", "league": 1, "home": 14, "away": 2, "status": "SCHEDULED", "p_id": "epl_2026_1017_2"}, # Aston Villa vs Man City
    {"date": "2026-10-17 14:00:00+00", "league": 1, "home": 17, "away": 13, "status": "SCHEDULED", "p_id": "epl_2026_1017_3"}, # Chelsea vs Newcastle
    {"date": "2026-10-17 16:30:00+00", "league": 1, "home": 18, "away": 4, "status": "SCHEDULED", "p_id": "epl_2026_1017_4"}, # Liverpool vs Nott'm Forest
    {"date": "2026-10-17 19:00:00+00", "league": 2, "home": 35, "away": 30, "status": "SCHEDULED", "p_id": "ll_2026_1017_1"}, # Real Madrid vs Sociedad

    # --- SUNDAY OCT 18, 2026 ---
    {"date": "2026-10-18 13:00:00+00", "league": 1, "home": 1, "away": 19, "status": "SCHEDULED", "p_id": "epl_2026_1018_1"}, # Burnley vs Man United
    {"date": "2026-10-18 15:30:00+00", "league": 1, "home": 2, "away": 18, "status": "SCHEDULED", "p_id": "epl_2026_1018_2"}, # Man City vs Liverpool
    {"date": "2026-10-18 19:00:00+00", "league": 2, "home": 28, "away": 31, "status": "SCHEDULED", "p_id": "ll_2026_1018_1"}, # Sevilla vs Girona

    # --- SATURDAY OCT 24, 2026 ---
    {"date": "2026-10-24 11:30:00+00", "league": 1, "home": 19, "away": 16, "status": "SCHEDULED", "p_id": "epl_2026_1024_1"}, # Man United vs Tottenham
    {"date": "2026-10-24 14:00:00+00", "league": 1, "home": 3, "away": 18, "status": "SCHEDULED", "p_id": "epl_2026_1024_2"}, # Arsenal vs Liverpool
    {"date": "2026-10-24 16:30:00+00", "league": 1, "home": 13, "away": 2, "status": "SCHEDULED", "p_id": "epl_2026_1024_3"}, # Newcastle vs Man City
    {"date": "2026-10-24 19:00:00+00", "league": 2, "home": 34, "away": 35, "status": "SCHEDULED", "p_id": "ll_2026_1024_1"}, # Ath Bilbao vs Real Madrid

    # --- SUNDAY OCT 25, 2026 ---
    {"date": "2026-10-25 13:00:00+00", "league": 1, "home": 17, "away": 14, "status": "SCHEDULED", "p_id": "epl_2026_1025_1"}, # Chelsea vs Aston Villa
    {"date": "2026-10-25 15:30:00+00", "league": 1, "home": 4, "away": 19, "status": "SCHEDULED", "p_id": "epl_2026_1025_2"}, # Nott'm Forest vs Man United

    # --- SATURDAY OCT 31, 2026 (HALLOWEEN MATCHDAY) ---
    {"date": "2026-10-31 11:30:00+00", "league": 1, "home": 2, "away": 3, "status": "SCHEDULED", "p_id": "epl_2026_1031_1"}, # Man City vs Arsenal (Title Clash)
    {"date": "2026-10-31 14:00:00+00", "league": 1, "home": 18, "away": 16, "status": "SCHEDULED", "p_id": "epl_2026_1031_2"}, # Liverpool vs Tottenham
    {"date": "2026-10-31 14:00:00+00", "league": 1, "home": 14, "away": 19, "status": "SCHEDULED", "p_id": "epl_2026_1031_3"}, # Aston Villa vs Man United
    {"date": "2026-10-31 16:30:00+00", "league": 1, "home": 13, "away": 17, "status": "SCHEDULED", "p_id": "epl_2026_1031_4"}, # Newcastle vs Chelsea
    {"date": "2026-10-31 19:00:00+00", "league": 2, "home": 35, "away": 29, "status": "SCHEDULED", "p_id": "ll_2026_1031_1"}, # Real Madrid vs Valencia
]

inserted = 0
for f in fixtures:
    # Check if provider_match_id exists
    cur.execute("SELECT id FROM matches WHERE provider_match_id = %s;", (f["p_id"],))
    exists = cur.fetchone()
    if exists:
        continue
    current_id += 1
    cur.execute("""
        INSERT INTO matches (id, league_id, home_team_id, away_team_id, kickoff_at, status, minute, home_score, away_score, provider, provider_match_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, NULL, 'manual_curated', %s, now());
    """, (current_id, f["league"], f["home"], f["away"], f["date"], f["status"], f["p_id"]))
    inserted += 1

conn.commit()
print(f"Successfully inserted {inserted} fixtures for October 2026!")

# Update sequence
cur.execute("SELECT setval('matches_id_seq', (SELECT max(id) FROM matches));")
conn.commit()
cur.close()
conn.close()
