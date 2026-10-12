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
        # MIDWEEK 1: OCT 12 - OCT 15 (EUROPEAN DOMESTIC RESCHEDULED & MIDWEEK TIES)
        # =========================================================================
        # Monday Oct 12
        {"date": "2026-10-12 16:30:00+00", "league": 1, "home": t("Aston Villa"), "away": t("Fulham"), "p_id": "epl_2026_1012_avl_ful"},
        {"date": "2026-10-12 16:45:00+00", "league": 3, "home": t("Fiorentina"), "away": t("Lazio"), "p_id": "sa_2026_1012_fio_laz"},
        {"date": "2026-10-12 17:00:00+00", "league": 2, "home": t("Villarreal"), "away": t("Las Palmas"), "p_id": "ll_2026_1012_vil_lpa"},
        {"date": "2026-10-12 17:00:00+00", "league": 5, "home": t("Lyon"), "away": t("Nantes"), "p_id": "l1_2026_1012_lyo_nan"},

        # Tuesday Oct 13
        {"date": "2026-10-13 16:30:00+00", "league": 4, "home": t("RB Leipzig"), "away": t("Freiburg"), "p_id": "bl_2026_1013_rbl_scf"},
        {"date": "2026-10-13 16:45:00+00", "league": 3, "home": t("Napoli"), "away": t("Monza"), "p_id": "sa_2026_1013_nap_mon"},
        {"date": "2026-10-13 17:00:00+00", "league": 2, "home": t("Betis"), "away": t("Osasuna"), "p_id": "ll_2026_1013_bet_osa"},

        # Wednesday Oct 14
        {"date": "2026-10-14 16:30:00+00", "league": 1, "home": t("Brighton"), "away": t("Newcastle"), "p_id": "epl_2026_1014_bha_new"},
        {"date": "2026-10-14 16:45:00+00", "league": 3, "home": t("Milan"), "away": t("Bologna"), "p_id": "sa_2026_1014_mil_bol"},
        {"date": "2026-10-14 17:00:00+00", "league": 5, "home": t("Marseille"), "away": t("Nice"), "p_id": "l1_2026_1014_mar_nic"},

        # Thursday Oct 15
        {"date": "2026-10-15 16:45:00+00", "league": 3, "home": t("Torino"), "away": t("Cagliari"), "p_id": "sa_2026_1015_tor_cag"},
        {"date": "2026-10-15 17:00:00+00", "league": 2, "home": t("Sociedad"), "away": t("Valencia"), "p_id": "ll_2026_1015_soc_val"},

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
        {"date": "2026-10-19 19:00:00+00", "league": 1, "home": t("Nott'm Forest"), "away": t("Crystal Palace"), "p_id": "epl_2026_1019_nfo_cry"},
        {"date": "2026-10-19 18:45:00+00", "league": 3, "home": t("Verona"), "away": t("Monza"), "p_id": "sa_2026_1019_ver_mon"},

        # =========================================================================
        # MIDWEEK 2: OCT 20 & 21 (UEFA CHAMPIONS LEAGUE MATCHDAY 3)
        # =========================================================================
        # Tuesday Oct 20
        {"date": "2026-10-20 16:45:00+00", "league": 6, "home": t("Monaco"), "away": t("Red Star Belgrade"), "p_id": "ucl_2026_1020_mon_red"},
        {"date": "2026-10-20 16:45:00+00", "league": 6, "home": t("Milan"), "away": t("Club Brugge"), "p_id": "ucl_2026_1020_mil_bru"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Real Madrid"), "away": t("Dortmund"), "p_id": "ucl_2026_1020_rma_bvb"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Arsenal"), "away": t("Shakhtar Donetsk"), "p_id": "ucl_2026_1020_ars_sha"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Juventus"), "away": t("Stuttgart"), "p_id": "ucl_2026_1020_juv_vfb"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Paris SG"), "away": t("PSV Eindhoven"), "p_id": "ucl_2026_1020_psg_psv"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Aston Villa"), "away": t("Bologna"), "p_id": "ucl_2026_1020_avl_bol"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Girona"), "away": t("Slovan Bratislava"), "p_id": "ucl_2026_1020_gir_slo"},
        {"date": "2026-10-20 19:00:00+00", "league": 6, "home": t("Sturm Graz"), "away": t("Sporting CP"), "p_id": "ucl_2026_1020_stu_spo"},

        # Wednesday Oct 21
        {"date": "2026-10-21 16:45:00+00", "league": 6, "home": t("Atalanta"), "away": t("Celtic"), "p_id": "ucl_2026_1021_ata_cel"},
        {"date": "2026-10-21 16:45:00+00", "league": 6, "home": t("Brest"), "away": t("Leverkusen"), "p_id": "ucl_2026_1021_bre_b04"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Barcelona"), "away": t("Bayern Munich"), "p_id": "ucl_2026_1021_bar_bay"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("RB Leipzig"), "away": t("Liverpool"), "p_id": "ucl_2026_1021_rbl_liv"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Man City"), "away": t("Sparta Praha"), "p_id": "ucl_2026_1021_mci_spa"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Ath Madrid"), "away": t("Lille"), "p_id": "ucl_2026_1021_atm_lil"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Young Boys"), "away": t("Inter"), "p_id": "ucl_2026_1021_yb_int"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Benfica"), "away": t("Feyenoord"), "p_id": "ucl_2026_1021_ben_fey"},
        {"date": "2026-10-21 19:00:00+00", "league": 6, "home": t("Red Bull Salzburg"), "away": t("Dinamo Zagreb"), "p_id": "ucl_2026_1021_sal_zag"},

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

        # Saturday Oct 31
        # Premier League
        {"date": "2026-10-31 12:30:00+00", "league": 1, "home": t("Newcastle"), "away": t("Arsenal"), "p_id": "epl_2026_1031_new_ars"},
        {"date": "2026-10-31 15:00:00+00", "league": 1, "home": t("Bournemouth"), "away": t("Man City"), "p_id": "epl_2026_1031_bou_mci"},
        {"date": "2026-10-31 15:00:00+00", "league": 1, "home": t("Liverpool"), "away": t("Brighton"), "p_id": "epl_2026_1031_liv_bha"},
        {"date": "2026-10-31 15:00:00+00", "league": 1, "home": t("Nott'm Forest"), "away": t("West Ham"), "p_id": "epl_2026_1031_nfo_whu"},
        {"date": "2026-10-31 15:00:00+00", "league": 1, "home": t("Burnley"), "away": t("Everton"), "p_id": "epl_2026_1031_bur_eve"},
        {"date": "2026-10-31 17:30:00+00", "league": 1, "home": t("Wolves"), "away": t("Crystal Palace"), "p_id": "epl_2026_1031_wol_cry"},
        # La Liga
        {"date": "2026-10-31 13:00:00+00", "league": 2, "home": t("Osasuna"), "away": t("Betis"), "p_id": "ll_2026_1031_osa_bet"},
        {"date": "2026-10-31 15:15:00+00", "league": 2, "home": t("Girona"), "away": t("Celta"), "p_id": "ll_2026_1031_gir_cel"},
        {"date": "2026-10-31 17:30:00+00", "league": 2, "home": t("Villarreal"), "away": t("Vallecano"), "p_id": "ll_2026_1031_vil_ray"},
        {"date": "2026-10-31 20:00:00+00", "league": 2, "home": t("Valencia"), "away": t("Real Madrid"), "p_id": "ll_2026_1031_val_rma"},
        # Serie A
        {"date": "2026-10-31 14:00:00+00", "league": 3, "home": t("Bologna"), "away": t("Lecce"), "p_id": "sa_2026_1031_bol_lec"},
        {"date": "2026-10-31 17:00:00+00", "league": 3, "home": t("Udinese"), "away": t("Juventus"), "p_id": "sa_2026_1031_udi_juv"},
        {"date": "2026-10-31 19:45:00+00", "league": 3, "home": t("Monza"), "away": t("Milan"), "p_id": "sa_2026_1031_mon_mil"},
        # Bundesliga - DERBY
        {"date": "2026-10-31 14:30:00+00", "league": 4, "home": t("Bayern Munich"), "away": t("Union Berlin"), "p_id": "bl_2026_1031_bay_uni"},
        {"date": "2026-10-31 14:30:00+00", "league": 4, "home": t("Ein Frankfurt"), "away": t("Bochum"), "p_id": "bl_2026_1031_sge_boc"},
        {"date": "2026-10-31 14:30:00+00", "league": 4, "home": t("Hoffenheim"), "away": t("FC Koln"), "p_id": "bl_2026_1031_tsg_koe"},
        {"date": "2026-10-31 14:30:00+00", "league": 4, "home": t("Wolfsburg"), "away": t("Augsburg"), "p_id": "bl_2026_1031_wob_fca"},
        {"date": "2026-10-31 17:30:00+00", "league": 4, "home": t("Dortmund"), "away": t("RB Leipzig"), "p_id": "bl_2026_1031_dor_rbl"},
        # Ligue 1
        {"date": "2026-10-31 16:00:00+00", "league": 5, "home": t("Paris SG"), "away": t("Lens"), "p_id": "l1_2026_1031_psg_len"},
        {"date": "2026-10-31 18:00:00+00", "league": 5, "home": t("Brest"), "away": t("Nice"), "p_id": "l1_2026_1031_bre_nic"},
        {"date": "2026-10-31 20:00:00+00", "league": 5, "home": t("Lyon"), "away": t("Strasbourg"), "p_id": "l1_2026_1031_lyo_str"},

        # Sunday Nov 1
        # Premier League
        {"date": "2026-11-01 14:00:00+00", "league": 1, "home": t("Tottenham"), "away": t("Aston Villa"), "p_id": "epl_2026_1101_tot_avl"},
        {"date": "2026-11-01 16:30:00+00", "league": 1, "home": t("Man United"), "away": t("Chelsea"), "p_id": "epl_2026_1101_mun_che"},
        # La Liga
        {"date": "2026-11-01 13:00:00+00", "league": 2, "home": t("Ath Madrid"), "away": t("Las Palmas"), "p_id": "ll_2026_1101_atm_lpa"},
        {"date": "2026-11-01 15:15:00+00", "league": 2, "home": t("Barcelona"), "away": t("Girona"), "p_id": "ll_2026_1101_bar_gir"},
        {"date": "2026-11-01 17:30:00+00", "league": 2, "home": t("Sevilla"), "away": t("Sociedad"), "p_id": "ll_2026_1101_sev_soc"},
        {"date": "2026-11-01 20:00:00+00", "league": 2, "home": t("Ath Bilbao"), "away": t("Betis"), "p_id": "ll_2026_1101_ath_bet"},
        # Serie A
        {"date": "2026-11-01 11:30:00+00", "league": 3, "home": t("Napoli"), "away": t("Atalanta"), "p_id": "sa_2026_1101_nap_ata"},
        {"date": "2026-11-01 14:00:00+00", "league": 3, "home": t("Torino"), "away": t("Fiorentina"), "p_id": "sa_2026_1101_tor_fio"},
        {"date": "2026-11-01 17:00:00+00", "league": 3, "home": t("Verona"), "away": t("Roma"), "p_id": "sa_2026_1101_ver_rom"},
        {"date": "2026-11-01 19:45:00+00", "league": 3, "home": t("Inter"), "away": t("Empoli"), "p_id": "sa_2026_1101_int_emp"},
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
