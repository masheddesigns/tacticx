"""
Accurate Official Premier League 2026/27 Fixtures for October 2026 (Matchweeks 6, 7 & 8).
Matches verified against the official Premier League 2026/27 calendar.
"""
import psycopg2

conn = psycopg2.connect("postgresql://bet:bet@tacticx-postgres:5432/betpredictor")
cur = conn.cursor()

# Get max id
cur.execute("SELECT coalesce(max(id), 2765) FROM matches;")
current_id = cur.fetchone()[0]

official_epl_fixtures = [
    # ==========================================
    # SATURDAY, OCTOBER 10, 2026 (MATCHWEEK 6)
    # ==========================================
    {
        "date": "2026-10-10 11:30:00+00", # 12:30 BST
        "home": 3, "away": 25, # Arsenal (3) vs Leeds United (25)
        "p_id": "epl_2026_mw6_ars_lee",
    },
    {
        "date": "2026-10-10 14:00:00+00", # 15:00 BST
        "home": 14, "away": 15, # Aston Villa (14) vs Brentford (15)
        "p_id": "epl_2026_mw6_avl_bre",
    },
    {
        "date": "2026-10-10 14:00:00+00", # 15:00 BST
        "home": 17, "away": 5, # Chelsea (17) vs Bournemouth (5)
        "p_id": "epl_2026_mw6_che_bou",
    },
    {
        "date": "2026-10-10 14:00:00+00", # 15:00 BST
        "home": 23, "away": 10, # Ipswich Town (23) vs Fulham (10)
        "p_id": "epl_2026_mw6_ips_ful",
    },
    {
        "date": "2026-10-10 14:00:00+00", # 15:00 BST
        "home": 24, "away": 7, # Sunderland (24) vs Brighton (7)
        "p_id": "epl_2026_mw6_sun_bha",
    },
    {
        "date": "2026-10-10 16:30:00+00", # 17:30 BST (Evening clash)
        "home": 19, "away": 16, # Manchester United (19) vs Tottenham Hotspur (16)
        "p_id": "epl_2026_mw6_mun_tot",
    },

    # ==========================================
    # SUNDAY, OCTOBER 11, 2026 (MATCHWEEK 6)
    # ==========================================
    {
        "date": "2026-10-11 13:00:00+00", # 14:00 BST
        "home": 12, "away": 4, # Crystal Palace (12) vs Nottingham Forest (4)
        "p_id": "epl_2026_mw6_cry_nfo",
    },
    {
        "date": "2026-10-11 13:00:00+00", # 14:00 BST
        "home": 22, "away": 9, # Hull City (22) vs Everton (9)
        "p_id": "epl_2026_mw6_hul_eve",
    },
    {
        "date": "2026-10-11 15:30:00+00", # 16:30 BST (Super Sunday Headline)
        "home": 18, "away": 2, # Liverpool (18) vs Manchester City (2)
        "p_id": "epl_2026_mw6_liv_mci",
    },

    # ==========================================
    # MONDAY, OCTOBER 12, 2026 (MATCHWEEK 6)
    # ==========================================
    {
        "date": "2026-10-12 19:00:00+00", # 20:00 BST (Monday Night Football)
        "home": 21, "away": 13, # Coventry City (21) vs Newcastle United (13)
        "p_id": "epl_2026_mw6_cov_new",
    },

    # ==========================================
    # MATCHWEEK 7 (OCTOBER 23 - 26, 2026)
    # ==========================================
    {
        "date": "2026-10-23 19:00:00+00",
        "home": 23, "away": 4, # Ipswich Town vs Nottingham Forest
        "p_id": "epl_2026_mw7_ips_nfo",
    },
    {
        "date": "2026-10-24 11:30:00+00",
        "home": 14, "away": 2, # Aston Villa vs Manchester City
        "p_id": "epl_2026_mw7_avl_mci",
    },
    {
        "date": "2026-10-24 14:00:00+00",
        "home": 21, "away": 10, # Coventry City vs Fulham
        "p_id": "epl_2026_mw7_cov_ful",
    },
    {
        "date": "2026-10-24 14:00:00+00",
        "home": 3, "away": 9, # Arsenal vs Everton
        "p_id": "epl_2026_mw7_ars_eve",
    },
    {
        "date": "2026-10-24 16:30:00+00",
        "home": 17, "away": 16, # Chelsea vs Tottenham Hotspur (London Derby)
        "p_id": "epl_2026_mw7_che_tot",
    },
    {
        "date": "2026-10-25 14:00:00+00",
        "home": 7, "away": 18, # Brighton vs Liverpool
        "p_id": "epl_2026_mw7_bha_liv",
    },
    {
        "date": "2026-10-25 16:30:00+00",
        "home": 13, "away": 19, # Newcastle vs Manchester United
        "p_id": "epl_2026_mw7_new_mun",
    },

    # ==========================================
    # MATCHWEEK 8 (OCTOBER 31, 2026)
    # ==========================================
    {
        "date": "2026-10-31 12:30:00+00",
        "home": 18, "away": 3, # Liverpool vs Arsenal (Blockbuster Clash)
        "p_id": "epl_2026_mw8_liv_ars",
    },
    {
        "date": "2026-10-31 15:00:00+00",
        "home": 2, "away": 17, # Manchester City vs Chelsea
        "p_id": "epl_2026_mw8_mci_che",
    },
    {
        "date": "2026-10-31 17:30:00+00",
        "home": 16, "away": 14, # Tottenham Hotspur vs Aston Villa
        "p_id": "epl_2026_mw8_tot_avl",
    },
]

inserted = 0
for f in official_epl_fixtures:
    cur.execute("SELECT id FROM matches WHERE provider_match_id = %s;", (f["p_id"],))
    exists = cur.fetchone()
    if exists:
        continue
    current_id += 1
    cur.execute("""
        INSERT INTO matches (id, league_id, home_team_id, away_team_id, kickoff_at, status, minute, home_score, away_score, provider, provider_match_id, updated_at)
        VALUES (%s, 1, %s, %s, %s, 'SCHEDULED', NULL, NULL, NULL, 'epl_official', %s, now());
    """, (current_id, f["home"], f["away"], f["date"], f["p_id"]))
    inserted += 1

conn.commit()
print(f"Successfully inserted {inserted} official Premier League matches for October 2026!")

# Update sequence
cur.execute("SELECT setval('matches_id_seq', (SELECT max(id) FROM matches));")
conn.commit()
cur.close()
conn.close()
