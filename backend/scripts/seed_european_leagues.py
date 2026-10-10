"""
Populate October 2026 fixtures across European Top Leagues:
- La Liga (League ID 2)
- Serie A (League ID 3)
- Bundesliga (League ID 4)
- Ligue 1 (League ID 5)
- UEFA Champions League (League ID 6, Oct 20-21)
Includes Today (Oct 10), Tomorrow (Oct 11), and upcoming October matchdays.
"""
import psycopg2

conn = psycopg2.connect("postgresql://bet:bet@tacticx-postgres:5432/betpredictor")
cur = conn.cursor()

# Get max match ID
cur.execute("SELECT coalesce(max(id), 2785) FROM matches;")
current_id = cur.fetchone()[0]

european_fixtures = [
    # =========================================================================
    # TODAY: SATURDAY, OCTOBER 10, 2026
    # =========================================================================
    # --- LA LIGA (League 2) ---
    {
        "date": "2026-10-10 12:00:00+00", "league": 2,
        "home": 38, "away": 33, # Villarreal (38) vs Mallorca (33)
        "p_id": "ll_2026_1010_vil_mal"
    },
    {
        "date": "2026-10-10 14:15:00+00", "league": 2,
        "home": 44, "away": 37, # Atletico Madrid (44) vs Osasuna (37)
        "p_id": "ll_2026_1010_atm_osa"
    },
    {
        "date": "2026-10-10 16:30:00+00", "league": 2,
        "home": 35, "away": 28, # Real Madrid (35) vs Sevilla (28)
        "p_id": "ll_2026_1010_rma_sev"
    },
    {
        "date": "2026-10-10 19:00:00+00", "league": 2,
        "home": 30, "away": 34, # Real Sociedad (30) vs Athletic Bilbao (34) - Basque Derby
        "p_id": "ll_2026_1010_soc_ath"
    },

    # --- SERIE A (League 3) ---
    {
        "date": "2026-10-10 13:00:00+00", "league": 3,
        "home": 64, "away": 58, # Bologna (64) vs Lecce (58)
        "p_id": "sa_2026_1010_bol_lec"
    },
    {
        "date": "2026-10-10 16:00:00+00", "league": 3,
        "home": 61, "away": 50, # Juventus (61) vs Genoa (50)
        "p_id": "sa_2026_1010_juv_gen"
    },
    {
        "date": "2026-10-10 18:45:00+00", "league": 3,
        "home": 65, "away": 59, # AC Milan (65) vs Lazio (59)
        "p_id": "sa_2026_1010_mil_laz"
    },

    # --- BUNDESLIGA (League 4) ---
    {
        "date": "2026-10-10 13:30:00+00", "league": 4,
        "home": 74, "away": 76, # Stuttgart (74) vs Wolfsburg (76)
        "p_id": "bl_2026_1010_stu_wol"
    },
    {
        "date": "2026-10-10 13:30:00+00", "league": 4,
        "home": 73, "away": 71, # RB Leipzig (73) vs Freiburg (71)
        "p_id": "bl_2026_1010_rbl_fre"
    },
    {
        "date": "2026-10-10 13:30:00+00", "league": 4,
        "home": 82, "away": 70, # Eintracht Frankfurt (82) vs Hoffenheim (70)
        "p_id": "bl_2026_1010_sge_tsg"
    },
    {
        "date": "2026-10-10 16:30:00+00", "league": 4,
        "home": 67, "away": 78, # Bayern Munich (67) vs Borussia Dortmund (78) - Der Klassiker
        "p_id": "bl_2026_1010_bay_bvb"
    },

    # --- LIGUE 1 (League 5) ---
    {
        "date": "2026-10-10 15:00:00+00", "league": 5,
        "home": 93, "away": 85, # Monaco (93) vs Lille (85)
        "p_id": "l1_2026_1010_mon_lil"
    },
    {
        "date": "2026-10-10 19:00:00+00", "league": 5,
        "home": 88, "away": 91, # Paris Saint-Germain (88) vs Lens (91)
        "p_id": "l1_2026_1010_psg_len"
    },

    # =========================================================================
    # TOMORROW: SUNDAY, OCTOBER 11, 2026
    # =========================================================================
    # --- LA LIGA ---
    {
        "date": "2026-10-11 12:00:00+00", "league": 2,
        "home": 40, "away": 36, # Getafe (40) vs Celta Vigo (36)
        "p_id": "ll_2026_1011_get_cel"
    },
    {
        "date": "2026-10-11 14:15:00+00", "league": 2,
        "home": 31, "away": 29, # Girona (31) vs Valencia (29)
        "p_id": "ll_2026_1011_gir_val"
    },
    {
        "date": "2026-10-11 16:30:00+00", "league": 2,
        "home": 39, "away": 27, # Real Betis (39) vs Rayo Vallecano (27)
        "p_id": "ll_2026_1011_bet_ray"
    },
    {
        "date": "2026-10-11 19:00:00+00", "league": 2,
        "home": 41, "away": 43, # Barcelona (41) vs Alaves (43)
        "p_id": "ll_2026_1011_bar_ala"
    },

    # --- SERIE A ---
    {
        "date": "2026-10-11 10:30:00+00", "league": 3,
        "home": 51, "away": 46, # Fiorentina (51) vs Empoli (46)
        "p_id": "sa_2026_1011_fio_emp"
    },
    {
        "date": "2026-10-11 13:00:00+00", "league": 3,
        "home": 49, "away": 62, # Napoli (49) vs Torino (62)
        "p_id": "sa_2026_1011_nap_tor"
    },
    {
        "date": "2026-10-11 16:00:00+00", "league": 3,
        "home": 57, "away": 53, # Atalanta (57) vs Monza (53)
        "p_id": "sa_2026_1011_ata_mon"
    },
    {
        "date": "2026-10-11 18:45:00+00", "league": 3,
        "home": 54, "away": 52, # Roma (54) vs Inter Milan (52) - Headline Clash
        "p_id": "sa_2026_1011_rom_int"
    },

    # --- BUNDESLIGA ---
    {
        "date": "2026-10-11 13:30:00+00", "league": 4,
        "home": 80, "away": 81, # Union Berlin (80) vs Mainz (81)
        "p_id": "bl_2026_1011_uni_fsv"
    },
    {
        "date": "2026-10-11 15:30:00+00", "league": 4,
        "home": 72, "away": 69, # Bayer Leverkusen (72) vs Gladbach (69)
        "p_id": "bl_2026_1011_b04_bmg"
    },
    {
        "date": "2026-10-11 17:30:00+00", "league": 4,
        "home": 68, "away": 66, # Augsburg (68) vs Werder Bremen (66)
        "p_id": "bl_2026_1011_fca_svw"
    },

    # --- LIGUE 1 ---
    {
        "date": "2026-10-11 13:00:00+00", "league": 5,
        "home": 98, "away": 96, # Rennes (98) vs Nantes (96) - Derby Breton
        "p_id": "l1_2026_1011_ren_nan"
    },
    {
        "date": "2026-10-11 15:05:00+00", "league": 5,
        "home": 84, "away": 87, # Nice (84) vs Reims (87)
        "p_id": "l1_2026_1011_nic_rei"
    },
    {
        "date": "2026-10-11 18:45:00+00", "league": 5,
        "home": 86, "away": 101, # Marseille (86) vs Lyon (101) - Choc des Olympiques
        "p_id": "l1_2026_1011_om_ol"
    },

    # =========================================================================
    # UEFA CHAMPIONS LEAGUE MATCHDAY 3 (OCTOBER 20 - 21, 2026)
    # =========================================================================
    {
        "date": "2026-10-20 19:00:00+00", "league": 6,
        "home": 41, "away": 67, # Barcelona (41) vs Bayern Munich (67)
        "p_id": "ucl_2026_1020_bar_bay"
    },
    {
        "date": "2026-10-20 19:00:00+00", "league": 6,
        "home": 35, "away": 78, # Real Madrid (35) vs Borussia Dortmund (78)
        "p_id": "ucl_2026_1020_rma_bvb"
    },
    {
        "date": "2026-10-20 19:00:00+00", "league": 6,
        "home": 17, "away": 65, # Chelsea (17) vs AC Milan (65)
        "p_id": "ucl_2026_1020_che_mil"
    },
    {
        "date": "2026-10-21 19:00:00+00", "league": 6,
        "home": 88, "away": 44, # Paris Saint-Germain (88) vs Atletico Madrid (44)
        "p_id": "ucl_2026_1021_psg_atm"
    },
    {
        "date": "2026-10-21 19:00:00+00", "league": 6,
        "home": 52, "away": 13, # Inter Milan (52) vs Newcastle (13)
        "p_id": "ucl_2026_1021_int_new"
    },
    {
        "date": "2026-10-21 19:00:00+00", "league": 6,
        "home": 73, "away": 18, # RB Leipzig (73) vs Liverpool (18)
        "p_id": "ucl_2026_1021_rbl_liv"
    },
]

inserted = 0
for f in european_fixtures:
    cur.execute("SELECT id FROM matches WHERE provider_match_id = %s;", (f["p_id"],))
    exists = cur.fetchone()
    if exists:
        continue
    current_id += 1
    cur.execute("""
        INSERT INTO matches (id, league_id, home_team_id, away_team_id, kickoff_at, status, minute, home_score, away_score, provider, provider_match_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, 'SCHEDULED', NULL, NULL, NULL, 'euro_official', %s, now());
    """, (current_id, f["league"], f["home"], f["away"], f["date"], f["p_id"]))
    inserted += 1

conn.commit()
print(f"Successfully inserted {inserted} European league matches for October 2026!")

# Update sequence
cur.execute("SELECT setval('matches_id_seq', (SELECT max(id) FROM matches));")
conn.commit()
cur.close()
conn.close()
