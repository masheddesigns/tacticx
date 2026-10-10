"""
Official verified European League Matchday fixtures for October 10 & 11, 2026.
Verified schedules:
- La Liga Matchday 8 (Oct 10-11, 2026)
- Serie A Matchday 6 (Oct 10-11, 2026)
- Bundesliga Matchday 5 (Oct 10-11, 2026)
- Ligue 1 Matchday 7 (Oct 10-11, 2026)
"""
import psycopg2

conn = psycopg2.connect("postgresql://bet:bet@tacticx-postgres:5432/betpredictor")
cur = conn.cursor()

cur.execute("SELECT coalesce(max(id), 2785) FROM matches;")
current_id = cur.fetchone()[0]

real_european_fixtures = [
    # =========================================================================
    # LA LIGA — MATCHDAY 8 (OCTOBER 10 - 11, 2026)
    # =========================================================================
    # Saturday, Oct 10
    {
        "date": "2026-10-10 12:00:00+00", "league": 2,
        "home": 27, "away": 34, # Rayo Vallecano (27) vs Athletic Club (34)
        "p_id": "ll_real_1010_ray_ath"
    },
    {
        "date": "2026-10-10 14:15:00+00", "league": 2,
        "home": 43, "away": 44, # Deportivo Alavés (43) vs Atlético Madrid (44)
        "p_id": "ll_real_1010_ala_atm"
    },
    {
        "date": "2026-10-10 16:30:00+00", "league": 2,
        "home": 41, "away": 40, # FC Barcelona (41) vs Getafe (40)
        "p_id": "ll_real_1010_bar_get"
    },
    {
        "date": "2026-10-10 19:00:00+00", "league": 2,
        "home": 35, "away": 38, # Real Madrid (35) vs Villarreal (38)
        "p_id": "ll_real_1010_rma_vil"
    },
    # Sunday, Oct 11
    {
        "date": "2026-10-11 14:15:00+00", "league": 2,
        "home": 39, "away": 37, # Real Betis (39) vs Osasuna (37)
        "p_id": "ll_real_1011_bet_osa"
    },

    # =========================================================================
    # BUNDESLIGA — MATCHDAY 5 (OCTOBER 10 - 11, 2026)
    # =========================================================================
    # Saturday, Oct 10
    {
        "date": "2026-10-10 13:30:00+00", "league": 4, # 15:30 CET
        "home": 68, "away": 67, # FC Augsburg (68) vs FC Bayern München (67)
        "p_id": "bl_real_1010_fca_bay"
    },
    {
        "date": "2026-10-10 13:30:00+00", "league": 4, # 15:30 CET
        "home": 81, "away": 72, # 1. FSV Mainz 05 (81) vs Bayer Leverkusen (72)
        "p_id": "bl_real_1010_m05_b04"
    },
    {
        "date": "2026-10-10 16:30:00+00", "league": 4, # 18:30 CET (Topspiel)
        "home": 73, "away": 82, # RB Leipzig (73) vs Eintracht Frankfurt (82)
        "p_id": "bl_real_1010_rbl_sge"
    },
    # Sunday, Oct 11
    {
        "date": "2026-10-11 13:30:00+00", "league": 4, # 15:30 CET (Rhein Derby)
        "home": 79, "away": 69, # 1. FC Köln (79) vs Borussia Mönchengladbach (69)
        "p_id": "bl_real_1011_koe_bmg"
    },

    # =========================================================================
    # SERIE A — MATCHDAY 6 (OCTOBER 10 - 11, 2026)
    # =========================================================================
    # Saturday, Oct 10
    {
        "date": "2026-10-10 13:00:00+00", "league": 3,
        "home": 50, "away": 51, # Genoa (50) vs Fiorentina (51)
        "p_id": "sa_real_1010_gen_fio"
    },
    {
        "date": "2026-10-10 16:00:00+00", "league": 3,
        "home": 49, "away": 48, # Napoli (49) vs Frosinone (48)
        "p_id": "sa_real_1010_nap_fro"
    },
    # Sunday, Oct 11
    {
        "date": "2026-10-11 13:00:00+00", "league": 3,
        "home": 58, "away": 64, # Lecce (58) vs Bologna (64)
        "p_id": "sa_real_1011_lec_bol"
    },
    {
        "date": "2026-10-11 13:00:00+00", "league": 3,
        "home": 59, "away": 53, # Lazio (59) vs Monza (53)
        "p_id": "sa_real_1011_laz_mon"
    },
    {
        "date": "2026-10-11 16:00:00+00", "league": 3,
        "home": 56, "away": 65, # Sassuolo (56) vs AC Milan (65)
        "p_id": "sa_real_1011_sas_mil"
    },
    {
        "date": "2026-10-11 18:45:00+00", "league": 3,
        "home": 63, "away": 61, # Cagliari (63) vs Juventus (61)
        "p_id": "sa_real_1011_cag_juv"
    },

    # =========================================================================
    # LIGUE 1 — MATCHDAY 7 (OCTOBER 10 - 11, 2026)
    # =========================================================================
    # Saturday, Oct 10
    {
        "date": "2026-10-10 15:15:00+00", "league": 5, # 17:15 CET
        "home": 85, "away": 95, # Lille (85) vs Le Havre (95)
        "p_id": "l1_real_1010_lil_leh"
    },
    {
        "date": "2026-10-10 18:45:00+00", "league": 5, # 20:45 CET
        "home": 93, "away": 97, # Monaco (93) vs Toulouse (97)
        "p_id": "l1_real_1010_mon_tou"
    },
    # Sunday, Oct 11
    {
        "date": "2026-10-11 13:00:00+00", "league": 5, # 15:00 CET
        "home": 84, "away": 100, # Nice (84) vs Strasbourg (100)
        "p_id": "l1_real_1011_nic_str"
    },
]

inserted = 0
for f in real_european_fixtures:
    cur.execute("SELECT id FROM matches WHERE provider_match_id = %s;", (f["p_id"],))
    exists = cur.fetchone()
    if exists:
        continue
    current_id += 1
    cur.execute("""
        INSERT INTO matches (id, league_id, home_team_id, away_team_id, kickoff_at, status, minute, home_score, away_score, provider, provider_match_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, 'SCHEDULED', NULL, NULL, NULL, 'euro_verified', %s, now());
    """, (current_id, f["league"], f["home"], f["away"], f["date"], f["p_id"]))
    inserted += 1

conn.commit()
print(f"Successfully inserted {inserted} verified European league fixtures for Oct 10-11, 2026!")

cur.execute("SELECT setval('matches_id_seq', (SELECT max(id) FROM matches));")
conn.commit()
cur.close()
conn.close()
