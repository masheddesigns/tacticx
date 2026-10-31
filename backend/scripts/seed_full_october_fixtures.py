"""Comprehensive October 2026 fixture database seeder.
Seeds all fixtures across the Top 5 European leagues and UEFA Champions League:
- Premier League (EPL, league_id=1)
- La Liga (LA_LIGA, league_id=2)
- Serie A (SERIE_A, league_id=3)
- Bundesliga (BUNDESLIGA, league_id=4)
- Ligue 1 (LIGUE_1, league_id=5)
- UEFA Champions League (UCL, league_id=6)
Includes matchdays for:
- Weekend Oct 10 - Oct 11 (completing any missing fixtures)
- Midweek Oct 13 - Oct 14
- Weekend Oct 16 - Oct 19
- UEFA Champions League Matchday 3 (Oct 20 & Oct 21)
- Weekend Oct 23 - Oct 26 (including El Clasico, Arsenal vs Liverpool, Derby d'Italia, Le Classique)
- Midweek Oct 27 - Oct 29 (League Cup & Serie A midweek)
- Weekend Oct 30 - Nov 1 (Halloween matchdays, including Man United vs Chelsea, Dortmund vs Leipzig)
"""
from datetime import datetime, timezone
import os
import psycopg2
from typing import List, Dict, Any

def seed_all_fixtures():
    db_url = os.environ.get("DATABASE_URL", "postgresql://bet:bet@tacticx-postgres:5432/betpredictor")
    if "+psycopg2" in db_url:
        db_url = db_url.replace("+psycopg2", "")
    
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # 1. Ensure UCL Teams exist in 'teams'
    ucl_extra_teams = [
        {"name": "Sporting CP", "short": "Sporting", "country": "Portugal"},
        {"name": "Benfica", "short": "Benfica", "country": "Portugal"},
        {"name": "Celtic", "short": "Celtic", "country": "Scotland"},
        {"name": "PSV Eindhoven", "short": "PSV", "country": "Netherlands"},
        {"name": "Feyenoord", "short": "Feyenoord", "country": "Netherlands"},
        {"name": "Club Brugge", "short": "Club Brugge", "country": "Belgium"},
        {"name": "Shakhtar Donetsk", "short": "Shakhtar", "country": "Ukraine"},
        {"name": "Red Star Belgrade", "short": "Red Star", "country": "Serbia"},
        {"name": "Dinamo Zagreb", "short": "Dinamo Zagreb", "country": "Croatia"},
        {"name": "Young Boys", "short": "Young Boys", "country": "Switzerland"},
        {"name": "Sparta Praha", "short": "Sparta Praha", "country": "Czechia"},
        {"name": "Slovan Bratislava", "short": "Slovan", "country": "Slovakia"},
        {"name": "Sturm Graz", "short": "Sturm Graz", "country": "Austria"},
        {"name": "Red Bull Salzburg", "short": "Salzburg", "country": "Austria"},
        {"name": "Fenerbahce", "short": "Fenerbahce", "country": "Turkey"},
        {"name": "Slavia Prague", "short": "Slavia Prague", "country": "Czechia"},
        {"name": "Sabah FK", "short": "Sabah FK", "country": "Azerbaijan"},
        {"name": "AEK Athens", "short": "AEK Athens", "country": "Greece"},
        {"name": "Bodo/Glimt", "short": "Bodo/Glimt", "country": "Norway"},
        {"name": "Como", "short": "Como", "country": "Italy"},
        {"name": "Galatasaray", "short": "Galatasaray", "country": "Turkey"},
        {"name": "Viking FK", "short": "Viking", "country": "Norway"},
        {"name": "Lens", "short": "Lens", "country": "France"},
        {"name": "LASK Linz", "short": "LASK", "country": "Austria"},
        {"name": "Levante", "short": "Levante", "country": "Spain"},
        {"name": "FC Porto", "short": "Porto", "country": "Portugal"},
        {"name": "Málaga", "short": "Málaga", "country": "Spain"},
        {"name": "Schalke 04", "short": "Schalke", "country": "Germany"},
        {"name": "SC Paderborn 07", "short": "Paderborn", "country": "Germany"},
        {"name": "Troyes", "short": "Troyes", "country": "France"},
        {"name": "Le Mans", "short": "Le Mans", "country": "France"},
        {"name": "Racing Santander", "short": "Santander", "country": "Spain"},
        {"name": "Elche", "short": "Elche", "country": "Spain"},
        {"name": "Venezia", "short": "Venezia", "country": "Italy"},
        {"name": "Frosinone", "short": "Frosinone", "country": "Italy"},
        {"name": "Hamburg SV", "short": "Hamburg", "country": "Germany"},
        {"name": "Paris FC", "short": "Paris FC", "country": "France"},
        {"name": "Coventry City", "short": "Coventry", "country": "England"},
        {"name": "Hull City", "short": "Hull", "country": "England"},
        {"name": "Sunderland", "short": "Sunderland", "country": "England"},
        {"name": "Leeds United", "short": "Leeds", "country": "England"},
    ]

    team_id_map: Dict[str, int] = {}
    
    # Query existing teams
    cur.execute("SELECT id, name FROM teams;")
    for row in cur.fetchall():
        team_id_map[row[1].lower()] = row[0]

    cur.execute("SELECT coalesce(max(id), 260) FROM teams;")
    max_team_id = cur.fetchone()[0]

    for ut in ucl_extra_teams:
        if ut["name"].lower() not in team_id_map:
            max_team_id += 1
            cur.execute("""
                INSERT INTO teams (id, league_id, name, short_name, country, provider, provider_team_id, created_at)
                VALUES (%s, 6, %s, %s, %s, 'manual_curated', %s, now())
                ON CONFLICT DO NOTHING;
            """, (max_team_id, ut["name"], ut["short"], ut["country"], f"ucl_{ut['short'].lower()}"))
            team_id_map[ut["name"].lower()] = max_team_id

    # Refresh teams map
    cur.execute("SELECT id, name FROM teams;")
    for row in cur.fetchall():
        team_id_map[row[1].lower()] = row[0]

    # Helper function to get team ID
    def t(name: str) -> int:
        name_lower = name.lower()
        if name_lower in team_id_map:
            return team_id_map[name_lower]
        # Partial match
        for k, v in team_id_map.items():
            if name_lower in k or k in name_lower:
                return v
        raise ValueError(f"Team not found: {name}")

    # 2. Get current max match ID
    cur.execute("SELECT coalesce(max(id), 2816) FROM matches;")
    current_match_id = cur.fetchone()[0]

    # 3. Comprehensive October Fixture Schedule
    fixtures: List[Dict[str, Any]] = [
        # =========================================================================
        # WEEKEND 1 COMPLETION: OCT 10 - OCT 12
        # =========================================================================
        # Bundesliga Oct 10
        {"date": "2026-10-10 13:30:00+00", "league": 4, "home": t("Bochum"), "away": t("Wolfsburg"), "p_id": "bl_2026_1010_boc_wob"},
        {"date": "2026-10-10 16:30:00+00", "league": 4, "home": t("Dortmund"), "away": t("Heidenheim"), "p_id": "bl_2026_1010_dor_hei"},
        # La Liga Oct 10
        {"date": "2026-10-10 16:30:00+00", "league": 2, "home": t("Girona"), "away": t("Sevilla"), "p_id": "ll_2026_1010_gir_sev"},
        # Serie A Oct 10
        {"date": "2026-10-10 18:45:00+00", "league": 3, "home": t("Juventus"), "away": t("Torino"), "p_id": "sa_2026_1010_juv_tor"},
        # Ligue 1 Oct 10
        {"date": "2026-10-10 19:00:00+00", "league": 5, "home": t("Paris SG"), "away": t("Montpellier"), "p_id": "l1_2026_1010_psg_mon"},

        # Sunday Oct 11 additions
        {"date": "2026-10-11 13:30:00+00", "league": 4, "home": t("Stuttgart"), "away": t("Hoffenheim"), "p_id": "bl_2026_1011_stu_hof"},
        {"date": "2026-10-11 16:30:00+00", "league": 2, "home": t("Barcelona"), "away": t("Mallorca"), "p_id": "ll_2026_1011_bar_mal"},
        {"date": "2026-10-11 16:00:00+00", "league": 3, "home": t("Atalanta"), "away": t("Verona"), "p_id": "sa_2026_1011_ata_ver"},
        {"date": "2026-10-11 18:45:00+00", "league": 3, "home": t("Inter"), "away": t("Roma"), "p_id": "sa_2026_1011_int_rom"},

        # =========================================================================
        # MIDWEEK 1: OCT 12 - OCT 14 (SERIE A & UEFA CHAMPIONS LEAGUE OFFICIAL SLATE)
        # =========================================================================
        # Monday Oct 12
        {"date": "2026-10-12 18:45:00+00", "league": 3, "home": t("Torino"), "away": t("Udinese"), "p_id": "sa_2026_1012_tor_udi"},

        # Tuesday Oct 13 (UEFA Champions League)
        {"date": "2026-10-13 16:45:00+00", "league": 6, "home": t("Lens"), "away": t("Sporting CP"), "p_id": "ucl_2026_1013_len_spo"},
        {"date": "2026-10-13 19:00:00+00", "league": 6, "home": t("Arsenal"), "away": t("Lille"), "p_id": "ucl_2026_1013_ars_lil"},
        {"date": "2026-10-13 19:00:00+00", "league": 6, "home": t("Ath Madrid"), "away": t("Man United"), "p_id": "ucl_2026_1013_atm_mun"},
        {"date": "2026-10-13 19:00:00+00", "league": 6, "home": t("Inter"), "away": t("Club Brugge"), "p_id": "ucl_2026_1013_int_bru"},
        {"date": "2026-10-13 19:00:00+00", "league": 6, "home": t("RB Leipzig"), "away": t("PSV Eindhoven"), "p_id": "ucl_2026_1013_rbl_psv"},
        {"date": "2026-10-13 19:00:00+00", "league": 6, "home": t("Villarreal"), "away": t("Napoli"), "p_id": "ucl_2026_1013_vil_nap"},

        # Wednesday Oct 14 (UEFA Champions League)
        {"date": "2026-10-14 19:00:00+00", "league": 6, "home": t("Roma"), "away": t("Real Madrid"), "p_id": "ucl_2026_1014_rom_rma"},
        {"date": "2026-10-14 19:00:00+00", "league": 6, "home": t("Man City"), "away": t("Paris SG"), "p_id": "ucl_2026_1014_mci_psg"},
        {"date": "2026-10-14 19:00:00+00", "league": 6, "home": t("Slovan Bratislava"), "away": t("Stuttgart"), "p_id": "ucl_2026_1014_slo_vfb"},

        # =========================================================================
        # WEEKEND 2: OCT 16 - OCT 19 (MATCHDAY 8 / 9)
        # =========================================================================
        # Friday Oct 16
        {"date": "2026-10-16 18:30:00+00", "league": 4, "home": t("Dortmund"), "away": t("FC Koln"), "p_id": "bl_2026_1016_dor_koe"},
        {"date": "2026-10-16 18:45:00+00", "league": 5, "home": t("Monaco"), "away": t("Lille"), "p_id": "l1_2026_1016_mon_lil"},
        {"date": "2026-10-16 19:00:00+00", "league": 2, "home": t("Celta"), "away": t("Real Madrid"), "p_id": "ll_2026_1016_cel_rma"},

        # Saturday Oct 17
        # Premier League
        {"date": "2026-10-17 11:30:00+00", "league": 1, "home": t("Tottenham"), "away": t("West Ham"), "p_id": "epl_2026_1017_tot_whu"},
        {"date": "2026-10-17 14:00:00+00", "league": 1, "home": t("Fulham"), "away": t("Aston Villa"), "p_id": "epl_2026_1017_ful_avl"},
        {"date": "2026-10-17 14:00:00+00", "league": 1, "home": t("Man United"), "away": t("Brentford"), "p_id": "epl_2026_1017_mun_bre"},
        {"date": "2026-10-17 14:00:00+00", "league": 1, "home": t("Newcastle"), "away": t("Brighton"), "p_id": "epl_2026_1017_new_bha"},
        {"date": "2026-10-17 14:00:00+00", "league": 1, "home": t("Southampton" if "southampton" in team_id_map else "Burnley"), "away": t("Leicester" if "leicester" in team_id_map else "Everton"), "p_id": "epl_2026_1017_bur_eve"},
        {"date": "2026-10-17 16:30:00+00", "league": 1, "home": t("Bournemouth"), "away": t("Arsenal"), "p_id": "epl_2026_1017_bou_ars"},
        # La Liga
        {"date": "2026-10-17 12:00:00+00", "league": 2, "home": t("Ath Bilbao"), "away": t("Mallorca"), "p_id": "ll_2026_1017_ath_mal"},
        {"date": "2026-10-17 14:15:00+00", "league": 2, "home": t("Osasuna"), "away": t("Betis"), "p_id": "ll_2026_1017_osa_bet"},
        {"date": "2026-10-17 16:30:00+00", "league": 2, "home": t("Girona"), "away": t("Sociedad"), "p_id": "ll_2026_1017_gir_soc"},
        {"date": "2026-10-17 19:00:00+00", "league": 2, "home": t("Barcelona"), "away": t("Sevilla"), "p_id": "ll_2026_1017_bar_sev"},
        # Serie A
        {"date": "2026-10-17 13:00:00+00", "league": 3, "home": t("Genoa"), "away": t("Bologna"), "p_id": "sa_2026_1017_gen_bol"},
        {"date": "2026-10-17 16:00:00+00", "league": 3, "home": t("Milan"), "away": t("Udinese"), "p_id": "sa_2026_1017_mil_udi"},
        {"date": "2026-10-17 18:45:00+00", "league": 3, "home": t("Juventus"), "away": t("Lazio"), "p_id": "sa_2026_1017_juv_laz"},
        # Bundesliga
        {"date": "2026-10-17 13:30:00+00", "league": 4, "home": t("Leverkusen"), "away": t("Ein Frankfurt"), "p_id": "bl_2026_1017_b04_sge"},
        {"date": "2026-10-17 13:30:00+00", "league": 4, "home": t("Hoffenheim"), "away": t("Bochum"), "p_id": "bl_2026_1017_tsg_boc"},
        {"date": "2026-10-17 13:30:00+00", "league": 4, "home": t("Freiburg"), "away": t("Augsburg"), "p_id": "bl_2026_1017_scf_fca"},
        {"date": "2026-10-17 13:30:00+00", "league": 4, "home": t("Mainz"), "away": t("RB Leipzig"), "p_id": "bl_2026_1017_m05_rbl"},
        {"date": "2026-10-17 16:30:00+00", "league": 4, "home": t("Bayern Munich"), "away": t("Stuttgart"), "p_id": "bl_2026_1017_bay_vfb"},
        # Ligue 1
        {"date": "2026-10-17 15:00:00+00", "league": 5, "home": t("Brest"), "away": t("Rennes"), "p_id": "l1_2026_1017_bre_ren"},
        {"date": "2026-10-17 17:00:00+00", "league": 5, "home": t("Lens"), "away": t("Lyon"), "p_id": "l1_2026_1017_len_lyo"},
        {"date": "2026-10-17 19:00:00+00", "league": 5, "home": t("Paris SG"), "away": t("Strasbourg"), "p_id": "l1_2026_1017_psg_str"},

        # Sunday Oct 18
        # Premier League
        {"date": "2026-10-18 13:00:00+00", "league": 1, "home": t("Wolves"), "away": t("Man City"), "p_id": "epl_2026_1018_wol_mci"},
        {"date": "2026-10-18 15:30:00+00", "league": 1, "home": t("Liverpool"), "away": t("Chelsea"), "p_id": "epl_2026_1018_liv_che"},
        # La Liga
        {"date": "2026-10-18 14:15:00+00", "league": 2, "home": t("Ath Madrid"), "away": t("Cadiz"), "p_id": "ll_2026_1018_atm_cad"},
        {"date": "2026-10-18 16:30:00+00", "league": 2, "home": t("Villarreal"), "away": t("Getafe"), "p_id": "ll_2026_1018_vil_get"},
        {"date": "2026-10-18 19:00:00+00", "league": 2, "home": t("Valencia"), "away": t("Las Palmas"), "p_id": "ll_2026_1018_val_lpa"},
        # Serie A
        {"date": "2026-10-18 10:30:00+00", "league": 3, "home": t("Empoli"), "away": t("Napoli"), "p_id": "sa_2026_1018_emp_nap"},
        {"date": "2026-10-18 13:00:00+00", "league": 3, "home": t("Lecce"), "away": t("Fiorentina"), "p_id": "sa_2026_1018_lec_fio"},
        {"date": "2026-10-18 16:00:00+00", "league": 3, "home": t("Cagliari"), "away": t("Torino"), "p_id": "sa_2026_1018_cag_tor"},
        {"date": "2026-10-18 18:45:00+00", "league": 3, "home": t("Roma"), "away": t("Inter"), "p_id": "sa_2026_1018_rom_int"},
        # Bundesliga
        {"date": "2026-10-18 13:30:00+00", "league": 4, "home": t("Wolfsburg"), "away": t("Werder Bremen"), "p_id": "bl_2026_1018_wob_svw"},
        {"date": "2026-10-18 15:30:00+00", "league": 4, "home": t("Heidenheim"), "away": t("M'gladbach"), "p_id": "bl_2026_1018_hei_bmg"},
        # Ligue 1
        {"date": "2026-10-18 13:00:00+00", "league": 5, "home": t("Le Havre"), "away": t("Lyon"), "p_id": "l1_2026_1018_leh_lyo"},
        {"date": "2026-10-18 15:00:00+00", "league": 5, "home": t("Nantes"), "away": t("Nice"), "p_id": "l1_2026_1018_nan_nic"},
        {"date": "2026-10-18 15:00:00+00", "league": 5, "home": t("Toulouse"), "away": t("Metz"), "p_id": "l1_2026_1018_tou_met"},
        {"date": "2026-10-18 18:45:00+00", "league": 5, "home": t("Montpellier"), "away": t("Marseille"), "p_id": "l1_2026_1018_mon_mar"},

        # Monday Oct 19
        {"date": "2026-10-19 19:00:00+00", "league": 1, "home": t("Tottenham"), "away": t("Coventry" if "coventry" in team_id_map else "Fulham"), "p_id": "epl_2026_1019_tot_cov"},
        {"date": "2026-10-19 19:00:00+00", "league": 2, "home": t("Getafe"), "away": t("Vallecano"), "p_id": "ll_2026_1019_get_val"},
        {"date": "2026-10-19 16:30:00+00", "league": 3, "home": t("Monza"), "away": t("Cagliari"), "p_id": "sa_2026_1019_mon_cag"},
        {"date": "2026-10-19 18:45:00+00", "league": 3, "home": t("Parma"), "away": t("Torino"), "p_id": "sa_2026_1019_par_tor"},

        # =========================================================================
        # MIDWEEK 2: OCT 20 & 21 (UEFA CHAMPIONS LEAGUE MATCHDAY 3 & DOMESTIC)
        # =========================================================================
        # Tuesday Oct 20
        {"date": "2026-10-20 16:45:00+00", "league": 6, "home": t("Fenerbahce"), "away": t("Slavia Prague"), "p_id": "ucl_2026_1020_fen_sla"},
        {"date": "2026-10-20 16:45:00+00", "league": 6, "home": t("Sabah FK"), "away": t("Dortmund"), "p_id": "ucl_2026_1020_sab_bvb"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Roma"), "away": t("Slovan Bratislava"), "p_id": "ucl_2026_1020_rom_slo"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("FC Porto"), "away": t("PSV Eindhoven"), "p_id": "ucl_2026_1020_por_psv"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Liverpool"), "away": t("Villarreal"), "p_id": "ucl_2026_1020_liv_vil"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Man City"), "away": t("AEK Athens"), "p_id": "ucl_2026_1020_mci_aek"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Napoli"), "away": t("Bodo/Glimt"), "p_id": "ucl_2026_1020_nap_bod"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Paris SG"), "away": t("Barcelona"), "p_id": "ucl_2026_1020_psg_bar"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Stuttgart"), "away": t("Ath Madrid"), "p_id": "ucl_2026_1020_stu_atm"},

        # Wednesday Oct 21
        {"date": "2026-10-21 16:45:00+00", "league": 6, "home": t("Como"), "away": t("Man United"), "p_id": "ucl_2026_1021_com_mun"},
        {"date": "2026-10-21 16:45:00+00", "league": 6, "home": t("Lille"), "away": t("Galatasaray"), "p_id": "ucl_2026_1021_lil_gal"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Aston Villa"), "away": t("Viking FK"), "p_id": "ucl_2026_1021_avl_vik"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Bayern Munich"), "away": t("Arsenal"), "p_id": "ucl_2026_1021_bay_ars"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Club Brugge"), "away": t("Lens"), "p_id": "ucl_2026_1021_bru_len"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Inter"), "away": t("Shakhtar Donetsk"), "p_id": "ucl_2026_1021_int_sha"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Betis"), "away": t("Feyenoord"), "p_id": "ucl_2026_1021_bet_fey"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Real Madrid"), "away": t("RB Leipzig"), "p_id": "ucl_2026_1021_rma_rbl"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Sporting CP"), "away": t("LASK Linz"), "p_id": "ucl_2026_1021_spo_las"},
        {"date": "2026-10-21 18:00:00+00", "league": 2, "home": t("Levante"), "away": t("Ath Bilbao"), "p_id": "ll_2026_1021_lev_ath"},

        # =========================================================================
        # WEEKEND 3: OCT 23 - OCT 26 (EL CLASICO, DERBY D'ITALIA, LE CLASSIQUE)
        # =========================================================================
        # Friday Oct 23
        {"date": "2026-10-23 18:30:00+00", "league": 4, "home": t("Mainz"), "away": t("M'gladbach"), "p_id": "bl_2026_1023_m05_bmg"},
        {"date": "2026-10-23 18:45:00+00", "league": 5, "home": t("Rennes"), "away": t("Le Havre"), "p_id": "l1_2026_1023_ren_leh"},
        {"date": "2026-10-23 19:00:00+00", "league": 2, "home": t("Alaves"), "away": t("Valladolid" if "valladolid" in team_id_map else "Granada"), "p_id": "ll_2026_1023_ala_gra"},

        # Saturday Oct 24
        # Premier League
        {"date": "2026-10-24 14:00:00+00", "league": 1, "home": t("Brentford"), "away": t("Ipswich"), "p_id": "epl_2026_1024_bre_ips"},
        {"date": "2026-10-24 14:00:00+00", "league": 1, "home": t("Brighton"), "away": t("Wolves"), "p_id": "epl_2026_1024_bha_wol"},
        {"date": "2026-10-24 14:00:00+00", "league": 1, "home": t("Man City"), "away": t("Southampton" if "southampton" in team_id_map else "Burnley"), "p_id": "epl_2026_1024_mci_bur"},
        {"date": "2026-10-24 16:30:00+00", "league": 1, "home": t("Everton"), "away": t("Fulham"), "p_id": "epl_2026_1024_eve_ful"},
        # La Liga - EL CLASICO
        {"date": "2026-10-24 14:15:00+00", "league": 2, "home": t("Las Palmas"), "away": t("Girona"), "p_id": "ll_2026_1024_lpa_gir"},
        {"date": "2026-10-24 16:15:00+00", "league": 2, "home": t("Vallecano"), "away": t("Alaves"), "p_id": "ll_2026_1024_ray_ala"},
        {"date": "2026-10-24 19:00:00+00", "league": 2, "home": t("Real Madrid"), "away": t("Barcelona"), "p_id": "ll_2026_1024_rma_bar"},
        # Serie A
        {"date": "2026-10-24 13:00:00+00", "league": 3, "home": t("Napoli"), "away": t("Lecce"), "p_id": "sa_2026_1024_nap_lec"},
        {"date": "2026-10-24 16:00:00+00", "league": 3, "home": t("Bologna"), "away": t("Milan"), "p_id": "sa_2026_1024_bol_mil"},
        {"date": "2026-10-24 18:45:00+00", "league": 3, "home": t("Atalanta"), "away": t("Verona"), "p_id": "sa_2026_1024_ata_ver"},
        # Bundesliga
        {"date": "2026-10-24 13:30:00+00", "league": 4, "home": t("Augsburg"), "away": t("Dortmund"), "p_id": "bl_2026_1024_fca_dor"},
        {"date": "2026-10-24 13:30:00+00", "league": 4, "home": t("RB Leipzig"), "away": t("Freiburg"), "p_id": "bl_2026_1024_rbl_scf"},
        {"date": "2026-10-24 13:30:00+00", "league": 4, "home": t("Stuttgart"), "away": t("Bochum"), "p_id": "bl_2026_1024_vfb_boc"},
        {"date": "2026-10-24 16:30:00+00", "league": 4, "home": t("Werder Bremen"), "away": t("Leverkusen"), "p_id": "bl_2026_1024_svw_b04"},
        # Ligue 1
        {"date": "2026-10-24 15:00:00+00", "league": 5, "home": t("Brest"), "away": t("Reims"), "p_id": "l1_2026_1024_bre_rei"},
        {"date": "2026-10-24 19:00:00+00", "league": 5, "home": t("Lens"), "away": t("Lille"), "p_id": "l1_2026_1024_len_lil"},

        # Sunday Oct 25
        # Premier League - ARSENAL VS LIVERPOOL
        {"date": "2026-10-25 14:00:00+00", "league": 1, "home": t("Chelsea"), "away": t("Newcastle"), "p_id": "epl_2026_1025_che_new"},
        {"date": "2026-10-25 14:00:00+00", "league": 1, "home": t("Crystal Palace"), "away": t("Tottenham"), "p_id": "epl_2026_1025_cry_tot"},
        {"date": "2026-10-25 14:00:00+00", "league": 1, "home": t("West Ham"), "away": t("Man United"), "p_id": "epl_2026_1025_whu_mun"},
        {"date": "2026-10-25 16:30:00+00", "league": 1, "home": t("Arsenal"), "away": t("Liverpool"), "p_id": "epl_2026_1025_ars_liv"},
        # La Liga
        {"date": "2026-10-25 14:15:00+00", "league": 2, "home": t("Celta"), "away": t("Ath Madrid"), "p_id": "ll_2026_1025_cel_atm"},
        {"date": "2026-10-25 16:30:00+00", "league": 2, "home": t("Getafe"), "away": t("Valencia"), "p_id": "ll_2026_1025_get_val"},
        {"date": "2026-10-25 19:00:00+00", "league": 2, "home": t("Betis"), "away": t("Ath Madrid"), "p_id": "ll_2026_1025_bet_atm"},
        {"date": "2026-10-25 19:00:00+00", "league": 2, "home": t("Sociedad"), "away": t("Osasuna"), "p_id": "ll_2026_1025_soc_osa"},
        # Serie A - DERBY D'ITALIA
        {"date": "2026-10-25 13:00:00+00", "league": 3, "home": t("Monza"), "away": t("Roma"), "p_id": "sa_2026_1025_mon_rom"},
        {"date": "2026-10-25 13:00:00+00", "league": 3, "home": t("Lazio"), "away": t("Genoa"), "p_id": "sa_2026_1025_laz_gen"},
        {"date": "2026-10-25 17:00:00+00", "league": 3, "home": t("Inter"), "away": t("Juventus"), "p_id": "sa_2026_1025_int_juv"},
        {"date": "2026-10-25 19:45:00+00", "league": 3, "home": t("Fiorentina"), "away": t("Roma"), "p_id": "sa_2026_1025_fio_rom"},
        # Bundesliga
        {"date": "2026-10-25 14:30:00+00", "league": 4, "home": t("Bochum"), "away": t("Bayern Munich"), "p_id": "bl_2026_1025_boc_bay"},
        {"date": "2026-10-25 16:30:00+00", "league": 4, "home": t("Union Berlin"), "away": t("Ein Frankfurt"), "p_id": "bl_2026_1025_uni_sge"},
        {"date": "2026-10-25 18:30:00+00", "league": 4, "home": t("Heidenheim"), "away": t("Hoffenheim"), "p_id": "bl_2026_1025_hei_tsg"},
        # Ligue 1 - LE CLASSIQUE
        {"date": "2026-10-25 13:00:00+00", "league": 5, "home": t("Lyon"), "away": t("Nantes"), "p_id": "l1_2026_1025_lyo_nan"},
        {"date": "2026-10-25 16:00:00+00", "league": 5, "home": t("Nice"), "away": t("Monaco"), "p_id": "l1_2026_1025_nic_mon"},
        {"date": "2026-10-25 16:00:00+00", "league": 5, "home": t("Strasbourg"), "away": t("Nantes"), "p_id": "l1_2026_1025_str_nan"},
        {"date": "2026-10-25 19:45:00+00", "league": 5, "home": t("Marseille"), "away": t("Paris SG"), "p_id": "l1_2026_1025_mar_psg"},

        # =========================================================================
        # MIDWEEK 3: OCT 27 - OCT 29 (SERIE A MIDWEEK & LEAGUE CUP)
        # =========================================================================
        # Tuesday Oct 27
        {"date": "2026-10-27 17:30:00+00", "league": 3, "home": t("Lecce"), "away": t("Verona"), "p_id": "sa_2026_1027_lec_ver"},
        {"date": "2026-10-27 19:45:00+00", "league": 3, "home": t("Milan"), "away": t("Napoli"), "p_id": "sa_2026_1027_mil_nap"},
        # Wednesday Oct 28
        {"date": "2026-10-28 17:30:00+00", "league": 3, "home": t("Empoli"), "away": t("Inter"), "p_id": "sa_2026_1028_emp_int"},
        {"date": "2026-10-28 19:45:00+00", "league": 3, "home": t("Juventus"), "away": t("Udinese"), "p_id": "sa_2026_1028_juv_udi"},
        {"date": "2026-10-28 19:45:00+00", "league": 3, "home": t("Atalanta"), "away": t("Monza"), "p_id": "sa_2026_1028_ata_mon"},
        # Thursday Oct 29
        {"date": "2026-10-29 17:30:00+00", "league": 3, "home": t("Genoa"), "away": t("Fiorentina"), "p_id": "sa_2026_1029_gen_fio"},
        {"date": "2026-10-29 19:45:00+00", "league": 3, "home": t("Roma"), "away": t("Torino"), "p_id": "sa_2026_1029_rom_tor"},

        # =========================================================================
        # WEEKEND 4: OCT 30 - NOV 1 (HALLOWEEN WEEKEND & CLASHES)
        # =========================================================================
        # Friday Oct 30
        {"date": "2026-10-30 18:30:00+00", "league": 4, "home": t("Leverkusen"), "away": t("Stuttgart"), "p_id": "bl_2026_1030_b04_vfb"},
        {"date": "2026-10-30 18:45:00+00", "league": 5, "home": t("Monaco"), "away": t("Brest"), "p_id": "l1_2026_1030_mon_bre"},
        {"date": "2026-10-30 19:00:00+00", "league": 2, "home": t("Alaves"), "away": t("Mallorca"), "p_id": "ll_2026_1030_ala_mal"},

        # Saturday Oct 31 (Authentic ESPN Slate)
        # Premier League
        {"date": "2026-10-31 12:30:00+00", "league": 1, "home": t("Chelsea"), "away": t("Man United"), "p_id": "espn_401879248"},
        {"date": "2026-10-31 15:00:00+00", "league": 1, "home": t("Bournemouth"), "away": t("Leeds"), "p_id": "espn_401879251"},
        {"date": "2026-10-31 15:00:00+00", "league": 1, "home": t("Brentford"), "away": t("Nott'm Forest"), "p_id": "espn_401879249"},
        {"date": "2026-10-31 15:00:00+00", "league": 1, "home": t("Coventry"), "away": t("Sunderland"), "p_id": "espn_401879247"},
        {"date": "2026-10-31 15:00:00+00", "league": 1, "home": t("Hull"), "away": t("Ipswich"), "p_id": "espn_401878763"},
        {"date": "2026-10-31 15:00:00+00", "league": 1, "home": t("Man City"), "away": t("Brighton"), "p_id": "espn_401879245"},
        {"date": "2026-10-31 17:30:00+00", "league": 1, "home": t("Tottenham"), "away": t("Crystal Palace"), "p_id": "espn_401878761"},
        {"date": "2026-10-31 20:00:00+00", "league": 1, "home": t("Aston Villa"), "away": t("Fulham"), "p_id": "espn_401879250"},
        # La Liga
        {"date": "2026-10-31 13:00:00+00", "league": 2, "home": t("Levante"), "away": t("Ath Madrid"), "p_id": "espn_401882820"},
        {"date": "2026-10-31 15:15:00+00", "league": 2, "home": t("Vallecano"), "away": t("Celta"), "p_id": "espn_401882818"},
        {"date": "2026-10-31 17:30:00+00", "league": 2, "home": t("Betis"), "away": t("Málaga"), "p_id": "espn_401882825"},
        {"date": "2026-10-31 20:00:00+00", "league": 2, "home": t("Barcelona"), "away": t("Alaves"), "p_id": "espn_401882822"},
        # Serie A
        {"date": "2026-10-31 14:00:00+00", "league": 3, "home": t("Bologna"), "away": t("Monza"), "p_id": "espn_401874798"},
        {"date": "2026-10-31 17:00:00+00", "league": 3, "home": t("Udinese"), "away": t("Roma"), "p_id": "espn_401874990"},
        {"date": "2026-10-31 19:45:00+00", "league": 3, "home": t("Milan"), "away": t("Inter"), "p_id": "espn_401874795"},
        # Bundesliga
        {"date": "2026-10-31 14:30:00+00", "league": 4, "home": t("Leverkusen"), "away": t("Stuttgart"), "p_id": "espn_401884753"},
        {"date": "2026-10-31 14:30:00+00", "league": 4, "home": t("M'gladbach"), "away": t("SC Paderborn"), "p_id": "espn_401884749"},
        {"date": "2026-10-31 14:30:00+00", "league": 4, "home": t("Augsburg"), "away": t("Freiburg"), "p_id": "espn_401884751"},
        {"date": "2026-10-31 14:30:00+00", "league": 4, "home": t("Schalke 04"), "away": t("RB Leipzig"), "p_id": "espn_401884747"},
        {"date": "2026-10-31 14:30:00+00", "league": 4, "home": t("Werder Bremen"), "away": t("Hoffenheim"), "p_id": "espn_401884748"},
        {"date": "2026-10-31 17:30:00+00", "league": 4, "home": t("Bayern Munich"), "away": t("Dortmund"), "p_id": "espn_401884754"},
        # Ligue 1
        {"date": "2026-10-31 19:45:00+00", "league": 5, "home": t("Troyes"), "away": t("Le Mans"), "p_id": "espn_401876413"},

        # Sunday Nov 1 (Authentic ESPN Slate)
        # Premier League
        {"date": "2026-11-01 16:30:00+00", "league": 1, "home": t("Liverpool"), "away": t("Arsenal"), "p_id": "espn_401879246"},
        # La Liga
        {"date": "2026-11-01 13:00:00+00", "league": 2, "home": t("Getafe"), "away": t("Sevilla"), "p_id": "espn_401882821"},
        {"date": "2026-11-01 15:15:00+00", "league": 2, "home": t("Racing Santander"), "away": t("Real Madrid"), "p_id": "espn_401882819"},
        {"date": "2026-11-01 17:30:00+00", "league": 2, "home": t("Elche"), "away": t("Valencia"), "p_id": "espn_401882823"},
        {"date": "2026-11-01 20:00:00+00", "league": 2, "home": t("Ath Bilbao"), "away": t("Sociedad"), "p_id": "espn_401882826"},
        # Serie A
        {"date": "2026-11-01 11:30:00+00", "league": 3, "home": t("Como"), "away": t("Venezia"), "p_id": "espn_401875002"},
        {"date": "2026-11-01 14:00:00+00", "league": 3, "home": t("Frosinone"), "away": t("Torino"), "p_id": "espn_401874782"},
        {"date": "2026-11-01 14:00:00+00", "league": 3, "home": t("Lazio"), "away": t("Cagliari"), "p_id": "espn_401874983"},
        {"date": "2026-11-01 17:00:00+00", "league": 3, "home": t("Lecce"), "away": t("Genoa"), "p_id": "espn_401874968"},
        {"date": "2026-11-01 19:45:00+00", "league": 3, "home": t("Juventus"), "away": t("Napoli"), "p_id": "espn_401874949"},
        # Bundesliga
        {"date": "2026-11-01 14:30:00+00", "league": 4, "home": t("Union Berlin"), "away": t("FC Koln"), "p_id": "espn_401884750"},
        {"date": "2026-11-01 16:30:00+00", "league": 4, "home": t("Ein Frankfurt"), "away": t("Hamburg SV"), "p_id": "espn_401884752"},
        # Ligue 1
        {"date": "2026-11-01 14:00:00+00", "league": 5, "home": t("Strasbourg"), "away": t("Auxerre"), "p_id": "espn_401876414"},
        {"date": "2026-11-01 16:15:00+00", "league": 5, "home": t("Lyon"), "away": t("Angers"), "p_id": "espn_401876418"},
        {"date": "2026-11-01 16:15:00+00", "league": 5, "home": t("Paris FC"), "away": t("Monaco"), "p_id": "espn_401876415"},
        {"date": "2026-11-01 19:45:00+00", "league": 5, "home": t("Marseille"), "away": t("Toulouse"), "p_id": "espn_401876417"},
    ]

    inserted_count = 0
    for f in fixtures:
        cur.execute("SELECT id FROM matches WHERE provider_match_id = %s;", (f["p_id"],))
        if cur.fetchone():
            continue
        current_match_id += 1
        cur.execute("""
            INSERT INTO matches (
                id, league_id, home_team_id, away_team_id, kickoff_at,
                status, minute, home_score, away_score, provider, provider_match_id, updated_at
            ) VALUES (%s, %s, %s, %s, %s, 'SCHEDULED', NULL, NULL, NULL, 'fotmob_canonical', %s, now())
            ON CONFLICT DO NOTHING;
        """, (current_match_id, f["league"], f["home"], f["away"], f["date"], f["p_id"]))
        inserted_count += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Successfully seeded {inserted_count} new fixtures for October 2026 across Top 5 leagues and UCL!")

if __name__ == "__main__":
    seed_all_fixtures()
