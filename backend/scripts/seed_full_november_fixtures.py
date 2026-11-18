"""Comprehensive November 2026 fixture database seeder.
Seeds authentic official fixtures across all supported competitions:
- Premier League (EPL, league_id=1)
- La Liga (LA_LIGA, league_id=2)
- Serie A (SERIE_A, league_id=3)
- Bundesliga (BUNDESLIGA, league_id=4)
- Ligue 1 (LIGUE_1, league_id=5)
- UEFA Champions League (UCL, league_id=6)
- UEFA Europa League (UEL, league_id=13)
- UEFA Conference League (UECL, league_id=14)
- Indian Super League (ISL, league_id=12)
- Major League Soccer (MLS, league_id=9)
- Brasileirão Série A (BRA_SERIE_A, league_id=11)
- Liga Profesional Argentina (LIGA_ARG, league_id=10)
"""
from datetime import datetime, timezone
import os
import psycopg2
from typing import List, Dict, Any

def seed_november_fixtures():
    db_url = os.environ.get("DATABASE_URL", "postgresql://bet:bet@tacticx-postgres:5432/betpredictor")
    if "+psycopg2" in db_url:
        db_url = db_url.replace("+psycopg2", "")
    
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # 1. Query existing leagues and teams
    cur.execute("SELECT id, code FROM leagues;")
    leagues_map = {row[1]: row[0] for row in cur.fetchall()}
    if "UEL" not in leagues_map:
        cur.execute("INSERT INTO leagues (id, code, name, country, season) VALUES (13, 'UEL', 'UEFA Europa League', 'Europe', '2026') ON CONFLICT DO NOTHING;")
        leagues_map["UEL"] = 13
    if "UECL" not in leagues_map:
        cur.execute("INSERT INTO leagues (id, code, name, country, season) VALUES (14, 'UECL', 'UEFA Conference League', 'Europe', '2026') ON CONFLICT DO NOTHING;")
        leagues_map["UECL"] = 14
    if "UNL" not in leagues_map:
        cur.execute("INSERT INTO leagues (id, code, name, country, season) VALUES (15, 'UNL', 'UEFA Nations League', 'Europe', '2026') ON CONFLICT DO NOTHING;")
        leagues_map["UNL"] = 15

    cur.execute("SELECT id, name FROM teams;")
    team_id_map = {row[1].lower(): row[0] for row in cur.fetchall()}
    cur.execute("SELECT coalesce(max(id), 500) FROM teams;")
    max_tid = cur.fetchone()[0]

    def get_or_create_team(t_name: str, lg_id: int) -> int:
        nonlocal max_tid
        tn_low = t_name.lower()
        if tn_low in team_id_map:
            return team_id_map[tn_low]
        for k, v in team_id_map.items():
            if tn_low in k or k in tn_low:
                return v
        max_tid += 1
        cur.execute("""
            INSERT INTO teams (id, league_id, name, short_name, provider, created_at)
            VALUES (%s, %s, %s, %s, 'manual_curated', now())
            ON CONFLICT DO NOTHING;
        """, (max_tid, lg_id, t_name, t_name[:32]))
        team_id_map[tn_low] = max_tid
        return max_tid

    cur.execute("SELECT coalesce(max(id), 3800) FROM matches;")
    current_mid = cur.fetchone()[0]

    fixtures = [
        {"date": "2026-11-03T00:15:00Z", "league": 10, "home": "Atlético Tucumán", "away": "Argentinos Juniors", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3615"},
        {"date": "2026-11-03T00:15:00Z", "league": 10, "home": "Independiente Rivadavia", "away": "Banfield", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3616"},
        {"date": "2026-11-04T15:30:00Z", "league": 13, "home": "Rennes", "away": "Olympiacos", "status": "FINISHED", "home_score": 0, "away_score": 0, "p_id": "espn_nov_3632"},
        {"date": "2026-11-04T17:45:00Z", "league": 6, "home": "AEK Athens", "away": "Real Madrid", "status": "FINISHED", "home_score": 2, "away_score": 3, "p_id": "espn_nov_3633"},
        {"date": "2026-11-04T17:45:00Z", "league": 6, "home": "Fenerbahce", "away": "Liverpool", "status": "FINISHED", "home_score": 3, "away_score": 2, "p_id": "espn_nov_3634"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "Dortmund", "away": "Betis", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3635"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "FC Porto", "away": "Napoli", "status": "FINISHED", "home_score": 4, "away_score": 1, "p_id": "espn_nov_3636"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "Lens", "away": "Como", "status": "FINISHED", "home_score": 1, "away_score": 9, "p_id": "espn_nov_3637"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "PSV Eindhoven", "away": "Club Brugge", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3638"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "RB Leipzig", "away": "Man City", "status": "FINISHED", "home_score": 2, "away_score": 3, "p_id": "espn_nov_3639"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "Slavia Prague", "away": "Arsenal", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3640"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "Viking FK", "away": "Sabah FK", "status": "FINISHED", "home_score": 4, "away_score": 1, "p_id": "espn_nov_3641"},
        {"date": "2026-11-04T22:30:00Z", "league": 11, "home": "Athletico Paranaense", "away": "Vasco da Gama", "status": "FINISHED", "home_score": 1, "away_score": 3, "p_id": "espn_nov_3628"},
        {"date": "2026-11-04T22:30:00Z", "league": 11, "home": "Flamengo", "away": "Grêmio", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3629"},
        {"date": "2026-11-05T00:30:00Z", "league": 11, "home": "Botafogo", "away": "Atlético Mineiro", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3630"},
        {"date": "2026-11-05T00:30:00Z", "league": 11, "home": "São Paulo", "away": "Corinthians", "status": "FINISHED", "home_score": 0, "away_score": 0, "p_id": "espn_nov_3631"},
        {"date": "2026-11-05T11:30:00Z", "league": 12, "home": "Churchill Brothers SC", "away": "NorthEast United FC", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3642"},
        {"date": "2026-11-05T14:00:00Z", "league": 12, "home": "Mohun Bagan Super Giant", "away": "Odisha FC", "status": "FINISHED", "home_score": 3, "away_score": 2, "p_id": "espn_nov_3643"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Anderlecht", "away": "Red Bull Salzburg", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3667"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Crystal Palace", "away": "Hoffenheim", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3668"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Levski Sofia", "away": "Jagiellonia Bialystok", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3669"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Lille", "away": "Viktoria Plzen", "status": "FINISHED", "home_score": 0, "away_score": 1, "p_id": "espn_nov_3670"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Milan", "away": "Ferencvaros", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3666"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "NEC Nijmegen", "away": "Omonia Nicosia", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3671"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Sociedad", "away": "Lyon", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3672"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Sparta Praha", "away": "Bournemouth", "status": "FINISHED", "home_score": 1, "away_score": 3, "p_id": "espn_nov_3673"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "AGF", "away": "Red Bull Bragantino", "status": "FINISHED", "home_score": 0, "away_score": 0, "p_id": "espn_nov_3648"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "Atalanta", "away": "Kairat Almaty", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3649"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "FC Midtjylland", "away": "Ajax Amsterdam", "status": "FINISHED", "home_score": 1, "away_score": 6, "p_id": "espn_nov_3650"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "FC Thun", "away": "Heart of Midlothian", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3651"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "KuPS Kuopio", "away": "KAA Gent", "status": "FINISHED", "home_score": 0, "away_score": 0, "p_id": "espn_nov_3652"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "Lincoln Red Imps", "away": "Hajduk Split", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3653"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "Mjällby AIF", "away": "Borac Banja Luka", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3654"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "Red Star Belgrade", "away": "Inter", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3655"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "Trabzonspor", "away": "Freiburg", "status": "FINISHED", "home_score": 0, "away_score": 1, "p_id": "espn_nov_3656"},
        {"date": "2026-11-05T18:00:00Z", "league": 10, "home": "Aldosivi", "away": "River Plate", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3644"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "AZ Alkmaar", "away": "Juventus", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3674"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Benfica", "away": "Lech Poznan", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3676"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Celta", "away": "Unión (Santa Fe)", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3677"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Celtic", "away": "Besiktas", "status": "FINISHED", "home_score": 3, "away_score": 2, "p_id": "espn_nov_3678"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Hapoel Be'er", "away": "OFI Crete", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3679"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Leverkusen", "away": "Marseille", "status": "FINISHED", "home_score": 0, "away_score": 1, "p_id": "espn_nov_3675"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Sturm Graz", "away": "NK Celje", "status": "FINISHED", "home_score": 2, "away_score": 3, "p_id": "espn_nov_3680"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Sunderland", "away": "Dinamo Zagreb", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3681"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Torreense", "away": "Armenia", "status": "FINISHED", "home_score": 3, "away_score": 2, "p_id": "espn_nov_3682"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "CSU Craiova", "away": "Egnatia", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3658"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "F.C. København", "away": "Iberia 1999", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3659"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "FC Lugano", "away": "Kauno Zalgiris", "status": "FINISHED", "home_score": 3, "away_score": 0, "p_id": "espn_nov_3660"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "FC Twente", "away": "Pafos", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3661"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "Getafe", "away": "Brighton", "status": "FINISHED", "home_score": 0, "away_score": 1, "p_id": "espn_nov_3662"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "Monaco", "away": "FC Nordsjælland", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3657"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "Panathinaikos", "away": "CSKA Sofia", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3663"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "Riga FC", "away": "Jablonec", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3664"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "Sint-Truidense", "away": "SK Brann", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3665"},
        {"date": "2026-11-05T22:15:00Z", "league": 10, "home": "Gimnasia La Plata", "away": "Belgrano", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3645"},
        {"date": "2026-11-05T22:30:00Z", "league": 11, "home": "Palmeiras", "away": "Remo", "status": "FINISHED", "home_score": 6, "away_score": 1, "p_id": "espn_nov_3646"},
        {"date": "2026-11-06T00:30:00Z", "league": 11, "home": "Cruzeiro", "away": "Bahia", "status": "FINISHED", "home_score": 3, "away_score": 2, "p_id": "espn_nov_3647"},
        {"date": "2026-11-06T14:00:00Z", "league": 12, "home": "FC Goa", "away": "Bengaluru FC", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3685"},
        {"date": "2026-11-06T18:00:00Z", "league": 10, "home": "Barracas Central", "away": "Racing Club", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3690"},
        {"date": "2026-11-06T19:30:00Z", "league": 4, "home": "Hamburg SV", "away": "M'gladbach", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3686"},
        {"date": "2026-11-06T19:45:00Z", "league": 3, "home": "Venezia", "away": "Udinese", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3688"},
        {"date": "2026-11-06T19:45:00Z", "league": 5, "home": "Toulouse", "away": "Strasbourg", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3687"},
        {"date": "2026-11-06T20:00:00Z", "league": 1, "home": "Everton", "away": "Coventry", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3684"},
        {"date": "2026-11-06T20:00:00Z", "league": 2, "home": "Sevilla", "away": "Alaves", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3683"},
        {"date": "2026-11-06T22:15:00Z", "league": 10, "home": "Independiente Rivadavia", "away": "Deportivo Riestra", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3691"},
        {"date": "2026-11-06T22:15:00Z", "league": 10, "home": "San Lorenzo", "away": "Platense", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3692"},
        {"date": "2026-11-06T22:15:00Z", "league": 10, "home": "Unión (Santa Fe)", "away": "Vélez Sarsfield", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3693"},
        {"date": "2026-11-06T23:00:00Z", "league": 11, "home": "Vitória", "away": "Fluminense", "status": "FINISHED", "home_score": 0, "away_score": 3, "p_id": "espn_nov_3689"},
        {"date": "2026-11-07T01:00:00Z", "league": 10, "home": "Banfield", "away": "Atlético Tucumán", "status": "FINISHED", "home_score": 2, "away_score": 2, "p_id": "espn_nov_3694"},
        {"date": "2026-11-07T01:00:00Z", "league": 10, "home": "Tigre", "away": "Sarmiento (Junín)", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3695"},
        {"date": "2026-11-07T11:30:00Z", "league": 12, "home": "Inter Kashi", "away": "Sporting Club Delhi", "status": "FINISHED", "home_score": 0, "away_score": 3, "p_id": "espn_nov_3711"},
        {"date": "2026-11-07T12:30:00Z", "league": 1, "home": "Leeds United", "away": "Tottenham", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3696"},
        {"date": "2026-11-07T13:00:00Z", "league": 2, "home": "Málaga", "away": "Racing Santander", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3700"},
        {"date": "2026-11-07T14:00:00Z", "league": 3, "home": "Cagliari", "away": "Frosinone", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3734"},
        {"date": "2026-11-07T14:00:00Z", "league": 3, "home": "Torino", "away": "Lecce", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3735"},
        {"date": "2026-11-07T14:00:00Z", "league": 12, "home": "Chennaiyin FC", "away": "East Bengal FC", "status": "FINISHED", "home_score": 5, "away_score": 3, "p_id": "espn_nov_3712"},
        {"date": "2026-11-07T14:30:00Z", "league": 4, "home": "Dortmund", "away": "SV Elversberg", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3704"},
        {"date": "2026-11-07T14:30:00Z", "league": 4, "home": "Mainz", "away": "Bayern Munich", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3705"},
        {"date": "2026-11-07T14:30:00Z", "league": 4, "home": "RB Leipzig", "away": "Augsburg", "status": "FINISHED", "home_score": 5, "away_score": 2, "p_id": "espn_nov_3706"},
        {"date": "2026-11-07T14:30:00Z", "league": 4, "home": "SC Paderborn 07", "away": "Ein Frankfurt", "status": "FINISHED", "home_score": 2, "away_score": 2, "p_id": "espn_nov_3707"},
        {"date": "2026-11-07T15:00:00Z", "league": 1, "home": "Arsenal", "away": "Hull", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3697"},
        {"date": "2026-11-07T15:00:00Z", "league": 1, "home": "Fulham", "away": "Newcastle", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3698"},
        {"date": "2026-11-07T15:15:00Z", "league": 2, "home": "Espanyol", "away": "Deportivo La Coruna", "status": "FINISHED", "home_score": 0, "away_score": 0, "p_id": "espn_nov_3701"},
        {"date": "2026-11-07T17:00:00Z", "league": 3, "home": "Parma", "away": "Bologna", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3736"},
        {"date": "2026-11-07T17:30:00Z", "league": 1, "home": "Nott'm Forest", "away": "Man City", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3699"},
        {"date": "2026-11-07T17:30:00Z", "league": 2, "home": "Osasuna", "away": "Ath Bilbao", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3702"},
        {"date": "2026-11-07T17:30:00Z", "league": 4, "home": "Stuttgart", "away": "Werder Bremen", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3708"},
        {"date": "2026-11-07T18:00:00Z", "league": 5, "home": "Auxerre", "away": "Paris FC", "status": "FINISHED", "home_score": 0, "away_score": 1, "p_id": "espn_nov_3709"},
        {"date": "2026-11-07T18:00:00Z", "league": 10, "home": "Gimnasia La Plata", "away": "Independiente Rivadavia", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3728"},
        {"date": "2026-11-07T18:00:00Z", "league": 10, "home": "Talleres", "away": "Estudiantes Río Cuarto", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3729"},
        {"date": "2026-11-07T19:45:00Z", "league": 3, "home": "Roma", "away": "Sassuolo", "status": "FINISHED", "home_score": 3, "away_score": 0, "p_id": "espn_nov_3737"},
        {"date": "2026-11-07T20:00:00Z", "league": 2, "home": "Valencia", "away": "Real Madrid", "status": "FINISHED", "home_score": 0, "away_score": 3, "p_id": "espn_nov_3703"},
        {"date": "2026-11-07T20:05:00Z", "league": 5, "home": "Paris SG", "away": "Troyes", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3710"},
        {"date": "2026-11-07T20:30:00Z", "league": 10, "home": "Argentinos Juniors", "away": "Huracán", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3730"},
        {"date": "2026-11-07T20:30:00Z", "league": 10, "home": "Boca Juniors", "away": "Defensa y Justicia", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3731"},
        {"date": "2026-11-07T20:30:00Z", "league": 10, "home": "Rosario Central", "away": "Estudiantes Río Cuarto", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3732"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "CF Montréal", "away": "Vancouver Whitecaps", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3713"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "Chicago Fire", "away": "Columbus Crew", "status": "FINISHED", "home_score": 3, "away_score": 4, "p_id": "espn_nov_3714"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "D.C. United", "away": "New York City FC", "status": "FINISHED", "home_score": 0, "away_score": 1, "p_id": "espn_nov_3715"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "FC Cincinnati", "away": "Nashville SC", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3716"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "Inter", "away": "Charlotte FC", "status": "FINISHED", "home_score": 3, "away_score": 3, "p_id": "espn_nov_3717"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "New York Red Bulls", "away": "Atlanta United", "status": "FINISHED", "home_score": 3, "away_score": 0, "p_id": "espn_nov_3720"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "Orlando City SC", "away": "England U17", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3718"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "Philadelphia Union", "away": "Toronto FC", "status": "FINISHED", "home_score": 4, "away_score": 1, "p_id": "espn_nov_3719"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "Austin FC", "away": "Portland Timbers", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3721"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "FC Dallas", "away": "Colorado Rapids", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3722"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "Houston Dynamo", "away": "St. Louis CITY SC", "status": "FINISHED", "home_score": 0, "away_score": 1, "p_id": "espn_nov_3723"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "Minnesota United", "away": "San Jose Earthquakes", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3724"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "Real Salt Lake", "away": "LA Galaxy", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3725"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "San Diego FC", "away": "Sporting Kansas City", "status": "FINISHED", "home_score": 0, "away_score": 1, "p_id": "espn_nov_3726"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "Seattle Sounders", "away": "Los Angeles FC", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3727"},
        {"date": "2026-11-08T01:00:00Z", "league": 10, "home": "Instituto (Córdoba)", "away": "Newell's Old Boys", "status": "FINISHED", "home_score": 2, "away_score": 2, "p_id": "espn_nov_3733"},
        {"date": "2026-11-08T11:30:00Z", "league": 3, "home": "Napoli", "away": "Lazio", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3739"},
        {"date": "2026-11-08T13:00:00Z", "league": 2, "home": "Elche", "away": "Betis", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3758"},
        {"date": "2026-11-08T14:00:00Z", "league": 1, "home": "Brighton", "away": "Brentford", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3744"},
        {"date": "2026-11-08T14:00:00Z", "league": 1, "home": "Crystal Palace", "away": "Liverpool", "status": "FINISHED", "home_score": 1, "away_score": 3, "p_id": "espn_nov_3745"},
        {"date": "2026-11-08T14:00:00Z", "league": 1, "home": "Ipswich", "away": "Bournemouth", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3746"},
        {"date": "2026-11-08T14:00:00Z", "league": 1, "home": "Sunderland", "away": "Chelsea", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3747"},
        {"date": "2026-11-08T14:00:00Z", "league": 3, "home": "Genoa", "away": "Milan", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3740"},
        {"date": "2026-11-08T14:00:00Z", "league": 3, "home": "Monza", "away": "Atalanta", "status": "FINISHED", "home_score": 0, "away_score": 1, "p_id": "espn_nov_3741"},
        {"date": "2026-11-08T14:00:00Z", "league": 5, "home": "Rennes", "away": "Lille", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3749"},
        {"date": "2026-11-08T14:30:00Z", "league": 4, "home": "FC Koln", "away": "Leverkusen", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3755"},
        {"date": "2026-11-08T15:15:00Z", "league": 2, "home": "Sociedad", "away": "Vallecano", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3759"},
        {"date": "2026-11-08T16:15:00Z", "league": 5, "home": "Angers", "away": "Nice", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3750"},
        {"date": "2026-11-08T16:15:00Z", "league": 5, "home": "Brest", "away": "Lyon", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3751"},
        {"date": "2026-11-08T16:15:00Z", "league": 5, "home": "Le Havre", "away": "Lorient", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3752"},
        {"date": "2026-11-08T16:15:00Z", "league": 5, "home": "Le Mans", "away": "Monaco", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3753"},
        {"date": "2026-11-08T16:30:00Z", "league": 1, "home": "Man United", "away": "Aston Villa", "status": "FINISHED", "home_score": 4, "away_score": 4, "p_id": "espn_nov_3748"},
        {"date": "2026-11-08T16:30:00Z", "league": 4, "home": "Freiburg", "away": "Union Berlin", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3756"},
        {"date": "2026-11-08T17:00:00Z", "league": 3, "home": "Inter", "away": "Como", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3742"},
        {"date": "2026-11-08T17:30:00Z", "league": 2, "home": "Celta", "away": "Levante", "status": "FINISHED", "home_score": 0, "away_score": 0, "p_id": "espn_nov_3760"},
        {"date": "2026-11-08T17:30:00Z", "league": 2, "home": "Villarreal", "away": "Getafe", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_nov_3761"},
        {"date": "2026-11-08T18:30:00Z", "league": 4, "home": "Hoffenheim", "away": "Schalke 04", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3757"},
        {"date": "2026-11-08T19:45:00Z", "league": 3, "home": "Fiorentina", "away": "Juventus", "status": "FINISHED", "home_score": 2, "away_score": 2, "p_id": "espn_nov_3743"},
        {"date": "2026-11-08T19:45:00Z", "league": 5, "home": "Lens", "away": "Marseille", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3754"},
        {"date": "2026-11-08T20:00:00Z", "league": 2, "home": "Ath Madrid", "away": "Barcelona", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3762"},
        {"date": "2026-11-08T22:30:00Z", "league": 10, "home": "Central Córdoba (Santiago del Estero)", "away": "Lanús", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_nov_3738"},
        {"date": "2026-11-12T17:00Z", "league": 15, "home": "Armenia", "away": "Cyprus", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_401861146"},
        {"date": "2026-11-12T17:00Z", "league": 15, "home": "Türkiye", "away": "Belgium", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_401861145"},
        {"date": "2026-11-12T19:45Z", "league": 15, "home": "Albania", "away": "Finland", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_401861147"},
        {"date": "2026-11-12T19:45Z", "league": 15, "home": "Czechia", "away": "Spain", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_401861148"},
        {"date": "2026-11-12T19:45Z", "league": 15, "home": "England", "away": "Croatia", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_401861150"},
        {"date": "2026-11-12T19:45Z", "league": 15, "home": "Italy", "away": "France", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_401861151"},
        {"date": "2026-11-12T19:45Z", "league": 15, "home": "Montenegro", "away": "Latvia", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_401861152"},
        {"date": "2026-11-12T19:45Z", "league": 15, "home": "San Marino", "away": "Belarus", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_401861149"},
        {"date": "2026-11-13T17:00Z", "league": 15, "home": "Moldova", "away": "Kazakhstan", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_401861162"},
        {"date": "2026-11-13T19:45Z", "league": 15, "home": "Andorra", "away": "Gibraltar", "status": "FINISHED", "home_score": 2, "away_score": 0, "p_id": "espn_401861155"},
        {"date": "2026-11-13T19:45Z", "league": 15, "home": "Bulgaria", "away": "Iceland", "status": "FINISHED", "home_score": 0, "away_score": 5, "p_id": "espn_401861157"},
        {"date": "2026-11-13T19:45Z", "league": 15, "home": "Liechtenstein", "away": "Azerbaijan", "status": "FINISHED", "home_score": 0, "away_score": 1, "p_id": "espn_401861153"},
        {"date": "2026-11-13T19:45Z", "league": 15, "home": "Luxembourg", "away": "Estonia", "status": "FINISHED", "home_score": 0, "away_score": 1, "p_id": "espn_401861154"},
        {"date": "2026-11-13T19:45Z", "league": 15, "home": "Netherlands", "away": "Greece", "status": "FINISHED", "home_score": 7, "away_score": 0, "p_id": "espn_401861159"},
        {"date": "2026-11-13T19:45Z", "league": 15, "home": "Scotland", "away": "North Macedonia", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_401861161"},
        {"date": "2026-11-13T19:45Z", "league": 15, "home": "Serbia", "away": "Germany", "status": "FINISHED", "home_score": 1, "away_score": 3, "p_id": "espn_401861158"},
        {"date": "2026-11-13T19:45Z", "league": 15, "home": "Slovakia", "away": "Faroe Islands", "status": "FINISHED", "home_score": 2, "away_score": 2, "p_id": "espn_401861160"},
        {"date": "2026-11-13T19:45Z", "league": 15, "home": "Slovenia", "away": "Switzerland", "status": "FINISHED", "home_score": 0, "away_score": 0, "p_id": "espn_401861156"},
        {"date": "2026-11-14T14:00Z", "league": 15, "home": "Kosovo", "away": "Israel", "status": "FINISHED", "home_score": 0, "away_score": 0, "p_id": "espn_401861163"},
        {"date": "2026-11-14T17:00Z", "league": 15, "home": "Georgia", "away": "Hungary", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_401861164"},
        {"date": "2026-11-14T17:00Z", "league": 15, "home": "Norway", "away": "Wales", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_401861165"},
        {"date": "2026-11-14T19:45Z", "league": 15, "home": "Austria", "away": "Republic of Ireland", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_401861170"},
        {"date": "2026-11-14T19:45Z", "league": 15, "home": "Northern Ireland", "away": "Ukraine", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_401861169"},
        {"date": "2026-11-14T19:45Z", "league": 15, "home": "Portugal", "away": "Denmark", "status": "FINISHED", "home_score": 1, "away_score": 4, "p_id": "espn_401861167"},
        {"date": "2026-11-14T19:45Z", "league": 15, "home": "Romania", "away": "Poland", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_401861168"},
        {"date": "2026-11-14T19:45Z", "league": 15, "home": "Sweden", "away": "Bosnia-Herzegovina", "status": "FINISHED", "home_score": 3, "away_score": 2, "p_id": "espn_401861166"},
        {"date": "2026-11-14T21:30Z", "league": 11, "home": "Mirassol", "away": "Atlético-MG", "status": "FINISHED", "home_score": 0, "away_score": 0, "p_id": "espn_401841311"},
        {"date": "2026-11-14T23:30Z", "league": 11, "home": "Chapecoense", "away": "Vasco da Gama", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_401841175"},
        {"date": "2026-11-15T14:00Z", "league": 15, "home": "Cyprus", "away": "Montenegro", "status": "FINISHED", "home_score": 1, "away_score": 4, "p_id": "espn_401861172"},
        {"date": "2026-11-15T14:00Z", "league": 15, "home": "Latvia", "away": "Armenia", "status": "FINISHED", "home_score": 0, "away_score": 0, "p_id": "espn_401861171"},
        {"date": "2026-11-15T17:00Z", "league": 15, "home": "Belarus", "away": "Albania", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_401861173"},
        {"date": "2026-11-15T17:00Z", "league": 15, "home": "Finland", "away": "San Marino", "status": "FINISHED", "home_score": 7, "away_score": 2, "p_id": "espn_401861174"},
        {"date": "2026-11-15T19:45Z", "league": 15, "home": "Belgium", "away": "Italy", "status": "FINISHED", "home_score": 4, "away_score": 1, "p_id": "espn_401861176"},
        {"date": "2026-11-15T19:45Z", "league": 15, "home": "Croatia", "away": "Czechia", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_401861178"},
        {"date": "2026-11-15T19:45Z", "league": 15, "home": "France", "away": "Türkiye", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_401861177"},
        {"date": "2026-11-15T19:45Z", "league": 15, "home": "Spain", "away": "England", "status": "FINISHED", "home_score": 2, "away_score": 3, "p_id": "espn_401861175"},
        {"date": "2026-11-16T15:00Z", "league": 15, "home": "Faroe Islands", "away": "Moldova", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_401861180"},
        {"date": "2026-11-16T15:00Z", "league": 15, "home": "Kazakhstan", "away": "Slovakia", "status": "FINISHED", "home_score": 2, "away_score": 2, "p_id": "espn_401861181"},
        {"date": "2026-11-16T17:00Z", "league": 15, "home": "Estonia", "away": "Bulgaria", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_401861183"},
        {"date": "2026-11-16T17:00Z", "league": 15, "home": "Iceland", "away": "Luxembourg", "status": "FINISHED", "home_score": 3, "away_score": 0, "p_id": "espn_401861182"},
        {"date": "2026-11-16T17:00Z", "league": 15, "home": "Lithuania", "away": "Liechtenstein", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_401861184"},
        {"date": "2026-11-16T19:45Z", "league": 15, "home": "Germany", "away": "Netherlands", "status": "FINISHED", "home_score": 5, "away_score": 0, "p_id": "espn_401861185"},
        {"date": "2026-11-16T19:45Z", "league": 15, "home": "Gibraltar", "away": "Malta", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_401861179"},
        {"date": "2026-11-16T19:45Z", "league": 15, "home": "Greece", "away": "Serbia", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_401861188"},
        {"date": "2026-11-16T19:45Z", "league": 15, "home": "North Macedonia", "away": "Slovenia", "status": "FINISHED", "home_score": 0, "away_score": 3, "p_id": "espn_401861187"},
        {"date": "2026-11-16T19:45Z", "league": 15, "home": "Switzerland", "away": "Scotland", "status": "FINISHED", "home_score": 4, "away_score": 0, "p_id": "espn_401861186"},
        {"date": "2026-11-17T19:45Z", "league": 15, "home": "Bosnia-Herzegovina", "away": "Romania", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_401861196"},
        {"date": "2026-11-17T19:45Z", "league": 15, "home": "Denmark", "away": "Norway", "status": "FINISHED", "home_score": 2, "away_score": 3, "p_id": "espn_401861194"},
        {"date": "2026-11-17T19:45Z", "league": 15, "home": "Hungary", "away": "Northern Ireland", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_401861191"},
        {"date": "2026-11-17T19:45Z", "league": 15, "home": "Israel", "away": "Austria", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_401861193"},
        {"date": "2026-11-17T19:45Z", "league": 15, "home": "Poland", "away": "Sweden", "status": "FINISHED", "home_score": 1, "away_score": 1, "p_id": "espn_401861195"},
        {"date": "2026-11-17T19:45Z", "league": 15, "home": "Republic of Ireland", "away": "Kosovo", "status": "FINISHED", "home_score": 3, "away_score": 0, "p_id": "espn_401861192"},
        {"date": "2026-11-17T19:45Z", "league": 15, "home": "Ukraine", "away": "Georgia", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_401861190"},
        {"date": "2026-11-17T19:45Z", "league": 15, "home": "Wales", "away": "Portugal", "status": "FINISHED", "home_score": 2, "away_score": 3, "p_id": "espn_401861189"},
        {"date": "2026-11-18T22:30Z", "league": 11, "home": "Coritiba", "away": "Santos", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841315"},
        {"date": "2026-11-18T23:00Z", "league": 11, "home": "Remo", "away": "Chapecoense", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841310"},
        {"date": "2026-11-18T23:30Z", "league": 11, "home": "Cruzeiro", "away": "Palmeiras", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841314"},
        {"date": "2026-11-18T23:30Z", "league": 11, "home": "Flamengo", "away": "Athletico-PR", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841313"},
        {"date": "2026-11-19T00:30Z", "league": 11, "home": "Corinthians", "away": "Botafogo", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841316"},
        {"date": "2026-11-19T00:30Z", "league": 11, "home": "Grêmio", "away": "Bahia", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841312"},
        {"date": "2026-11-19T22:30Z", "league": 11, "home": "Vasco da Gama", "away": "Internacional", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841308"},
        {"date": "2026-11-19T22:30Z", "league": 11, "home": "Vitória", "away": "Red Bull Bragantino", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841317"},
        {"date": "2026-11-20T00:30Z", "league": 9, "home": "Orlando City SC", "away": "FC Cincinnati", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933535"},
        {"date": "2026-11-20T00:30Z", "league": 11, "home": "São Paulo", "away": "Fluminense", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841309"},
        {"date": "2026-11-20T03:00Z", "league": 9, "home": "Seattle Sounders FC", "away": "Real Salt Lake", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933555"},
        {"date": "2026-11-20T11:30Z", "league": 12, "home": "East Bengal FC", "away": "Sporting Club Delhi", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401925412"},
        {"date": "2026-11-20T14:00Z", "league": 12, "home": "Bengaluru FC", "away": "Mumbai City FC", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401925411"},
        {"date": "2026-11-20T19:45Z", "league": 5, "home": "Troyes", "away": "Le Havre AC", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401876395"},
        {"date": "2026-11-20T20:00Z", "league": 2, "home": "Athletic Club", "away": "Espanyol", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401882805"},
        {"date": "2026-11-20T23:00Z", "league": 10, "home": "Vélez Sarsfield", "away": "Belgrano (Córdoba)", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933760"},
        {"date": "2026-11-21T11:30Z", "league": 12, "home": "Chennaiyin FC", "away": "Punjab FC", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401925410"},
        {"date": "2026-11-21T12:30Z", "league": 1, "home": "Manchester City", "away": "Fulham", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401879233"},
        {"date": "2026-11-21T13:00Z", "league": 2, "home": "Alavés", "away": "Deportivo", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401882806"},
        {"date": "2026-11-21T14:00Z", "league": 3, "home": "Como", "away": "Cagliari", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401875056"},
        {"date": "2026-11-21T14:00Z", "league": 3, "home": "Lazio", "away": "Lecce", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401874981"},
        {"date": "2026-11-21T14:00Z", "league": 12, "home": "NorthEast United FC", "away": "FC GOA", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401925409"},
        {"date": "2026-11-21T14:30Z", "league": 4, "home": "1. FC Union Berlin", "away": "RB Leipzig", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401884732"},
        {"date": "2026-11-21T14:30Z", "league": 4, "home": "Bayer Leverkusen", "away": "SC Paderborn 07", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401884735"},
        {"date": "2026-11-21T14:30Z", "league": 4, "home": "Borussia Mönchengladbach", "away": "Borussia Dortmund", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401884731"},
        {"date": "2026-11-21T14:30Z", "league": 4, "home": "Eintracht Frankfurt", "away": "TSG Hoffenheim", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401884734"},
        {"date": "2026-11-21T14:30Z", "league": 4, "home": "SV Elversberg", "away": "SC Freiburg", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401884728"},
        {"date": "2026-11-21T15:00Z", "league": 1, "home": "AFC Bournemouth", "away": "Nottingham Forest", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401879238"},
        {"date": "2026-11-21T15:00Z", "league": 1, "home": "Aston Villa", "away": "Sunderland", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401878756"},
        {"date": "2026-11-21T15:00Z", "league": 1, "home": "Chelsea", "away": "Leeds United", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401879236"},
        {"date": "2026-11-21T15:00Z", "league": 1, "home": "Coventry City", "away": "Crystal Palace", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401879235"},
        {"date": "2026-11-21T15:00Z", "league": 1, "home": "Tottenham Hotspur", "away": "Ipswich Town", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401878754"},
        {"date": "2026-11-21T15:15Z", "league": 2, "home": "Rayo Vallecano", "away": "Valencia", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401882799"},
        {"date": "2026-11-21T16:15Z", "league": 5, "home": "Nice", "away": "Paris Saint-Germain", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401876398"},
        {"date": "2026-11-21T17:00Z", "league": 3, "home": "Parma", "away": "AS Roma", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401874967"},
        {"date": "2026-11-21T17:30Z", "league": 1, "home": "Newcastle United", "away": "Arsenal", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401879232"},
        {"date": "2026-11-21T17:30Z", "league": 2, "home": "Sevilla", "away": "Real Betis", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401882797"},
        {"date": "2026-11-21T17:30Z", "league": 4, "home": "Schalke 04", "away": "VfB Stuttgart", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401884729"},
        {"date": "2026-11-21T18:00Z", "league": 10, "home": "Defensa y Justicia", "away": "Barracas Central", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933758"},
        {"date": "2026-11-21T19:00Z", "league": 9, "home": "New England Revolution", "away": "Philadelphia Union", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933733"},
        {"date": "2026-11-21T19:30Z", "league": 11, "home": "Palmeiras", "away": "Flamengo", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841322"},
        {"date": "2026-11-21T19:45Z", "league": 3, "home": "Napoli", "away": "Torino", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401875067"},
        {"date": "2026-11-21T19:45Z", "league": 5, "home": "AS Monaco", "away": "AJ Auxerre", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401876399"},
        {"date": "2026-11-21T19:45Z", "league": 5, "home": "Lens", "away": "Toulouse", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401876403"},
        {"date": "2026-11-21T19:45Z", "league": 5, "home": "Lille", "away": "Lyon", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401876402"},
        {"date": "2026-11-21T19:45Z", "league": 5, "home": "Strasbourg", "away": "Brest", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401876396"},
        {"date": "2026-11-21T20:00Z", "league": 2, "home": "Real Madrid", "away": "Celta Vigo", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401882798"},
        {"date": "2026-11-21T20:00Z", "league": 10, "home": "Argentinos Juniors", "away": "Independiente", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933755"},
        {"date": "2026-11-21T20:30Z", "league": 11, "home": "Bahia", "away": "Coritiba", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841327"},
        {"date": "2026-11-21T21:00Z", "league": 9, "home": "FC Dallas", "away": "Portland Timbers", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933732"},
        {"date": "2026-11-21T23:00Z", "league": 9, "home": "Inter Miami CF", "away": "Columbus Crew", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933739"},
        {"date": "2026-11-22T00:00Z", "league": 11, "home": "Chapecoense", "away": "Cruzeiro", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841325"},
        {"date": "2026-11-22T11:30Z", "league": 3, "home": "Juventus", "away": "Venezia", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401875008"},
        {"date": "2026-11-22T13:00Z", "league": 2, "home": "Barcelona", "away": "Villarreal", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401882804"},
        {"date": "2026-11-22T14:00Z", "league": 1, "home": "Hull City", "away": "Brighton & Hove Albion", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401879234"},
        {"date": "2026-11-22T14:00Z", "league": 3, "home": "Bologna", "away": "Udinese", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401875047"},
        {"date": "2026-11-22T14:00Z", "league": 3, "home": "Sassuolo", "away": "Genoa", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401874960"},
        {"date": "2026-11-22T14:00Z", "league": 5, "home": "Paris FC", "away": "Angers", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401876397"},
        {"date": "2026-11-22T14:00Z", "league": 12, "home": "Churchill Brothers", "away": "Mohun Bagan Super Giant", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401925408"},
        {"date": "2026-11-22T14:30Z", "league": 4, "home": "FC Augsburg", "away": "Mainz", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401884733"},
        {"date": "2026-11-22T15:15Z", "league": 2, "home": "Racing Santander", "away": "Real Sociedad", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401882800"},
        {"date": "2026-11-22T16:15Z", "league": 5, "home": "Lorient", "away": "Stade Rennais", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401876401"},
        {"date": "2026-11-22T16:30Z", "league": 1, "home": "Liverpool", "away": "Manchester United", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401878755"},
        {"date": "2026-11-22T16:30Z", "league": 4, "home": "Werder Bremen", "away": "Hamburg SV", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401884730"},
        {"date": "2026-11-22T17:00Z", "league": 3, "home": "AC Milan", "away": "Frosinone", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401874989"},
        {"date": "2026-11-22T17:30Z", "league": 2, "home": "Osasuna", "away": "Málaga", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401882801"},
        {"date": "2026-11-22T19:00Z", "league": 10, "home": "Rosario Central", "away": "Gimnasia (Mendoza)", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933759"},
        {"date": "2026-11-22T19:00Z", "league": 11, "home": "Athletico-PR", "away": "Remo", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841318"},
        {"date": "2026-11-22T19:45Z", "league": 3, "home": "Atalanta", "away": "Internazionale", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401875001"},
        {"date": "2026-11-22T19:45Z", "league": 5, "home": "Marseille", "away": "Le Mans", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401876400"},
        {"date": "2026-11-22T20:00Z", "league": 2, "home": "Getafe", "away": "Atlético Madrid", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401882803"},
        {"date": "2026-11-22T21:00Z", "league": 9, "home": "Nashville SC", "away": "TBD Away", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933731"},
        {"date": "2026-11-22T21:30Z", "league": 11, "home": "Fluminense", "away": "Mirassol", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841324"},
        {"date": "2026-11-22T22:00Z", "league": 10, "home": "River Plate", "away": "Lanús", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933761"},
        {"date": "2026-11-22T22:30Z", "league": 11, "home": "Red Bull Bragantino", "away": "Vasco da Gama", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841321"},
        {"date": "2026-11-22T23:30Z", "league": 9, "home": "Chicago Fire FC", "away": "Charlotte FC", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933730"},
        {"date": "2026-11-23T01:00Z", "league": 10, "home": "Instituto (Córdoba)", "away": "Huracán", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933762"},
        {"date": "2026-11-23T01:30Z", "league": 9, "home": "Vancouver Whitecaps", "away": "TBD Away", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933729"},
        {"date": "2026-11-23T19:45Z", "league": 3, "home": "Monza", "away": "Fiorentina", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401875009"},
        {"date": "2026-11-23T20:00Z", "league": 1, "home": "Brentford", "away": "Everton", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401879237"},
        {"date": "2026-11-23T20:00Z", "league": 2, "home": "Levante", "away": "Elche", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401882802"},
        {"date": "2026-11-23T20:00Z", "league": 10, "home": "Gimnasia La Plata", "away": "Newell's Old Boys", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933756"},
        {"date": "2026-11-23T22:30Z", "league": 11, "home": "Internacional", "away": "Vitória", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841323"},
        {"date": "2026-11-23T23:00Z", "league": 11, "home": "Botafogo", "away": "São Paulo", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841326"},
        {"date": "2026-11-24T00:00Z", "league": 11, "home": "Santos", "away": "Grêmio", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841320"},
        {"date": "2026-11-24T01:00Z", "league": 9, "home": "St. Louis CITY SC", "away": "LAFC", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933728"},
        {"date": "2026-11-24T14:00Z", "league": 12, "home": "NorthEast United FC", "away": "Sporting Club Delhi", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401925407"},
        {"date": "2026-11-24T17:45Z", "league": 6, "home": "Bodo/Glimt", "away": "LASK Linz", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915380"},
        {"date": "2026-11-24T17:45Z", "league": 6, "home": "Galatasaray", "away": "Aston Villa", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915300"},
        {"date": "2026-11-24T20:00Z", "league": 6, "home": "Arsenal", "away": "Borussia Dortmund", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915295"},
        {"date": "2026-11-24T20:00Z", "league": 6, "home": "Como", "away": "AEK Athens", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915296"},
        {"date": "2026-11-24T20:00Z", "league": 6, "home": "Feyenoord Rotterdam", "away": "FC Porto", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915294"},
        {"date": "2026-11-24T20:00Z", "league": 6, "home": "Manchester City", "away": "Napoli", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915379"},
        {"date": "2026-11-24T20:00Z", "league": 6, "home": "RB Leipzig", "away": "Lens", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915299"},
        {"date": "2026-11-24T20:00Z", "league": 6, "home": "Real Madrid", "away": "PSV Eindhoven", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915298"},
        {"date": "2026-11-24T20:00Z", "league": 6, "home": "Slovan Bratislava", "away": "Real Betis", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915297"},
        {"date": "2026-11-24T21:00Z", "league": 11, "home": "Chapecoense", "away": "Palmeiras", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841335"},
        {"date": "2026-11-25T03:00Z", "league": 9, "home": "San Jose Earthquakes", "away": "Houston Dynamo FC", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933738"},
        {"date": "2026-11-25T17:45Z", "league": 6, "home": "Sabah FK", "away": "Barcelona", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915378"},
        {"date": "2026-11-25T17:45Z", "league": 6, "home": "Slavia Prague", "away": "Villarreal", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915293"},
        {"date": "2026-11-25T20:00Z", "league": 6, "home": "Atlético Madrid", "away": "Viking FK", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915291"},
        {"date": "2026-11-25T20:00Z", "league": 6, "home": "Club Brugge", "away": "Liverpool", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915292"},
        {"date": "2026-11-25T20:00Z", "league": 6, "home": "Internazionale", "away": "VfB Stuttgart", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915376"},
        {"date": "2026-11-25T20:00Z", "league": 6, "home": "Lille", "away": "Bayern Munich", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915377"},
        {"date": "2026-11-25T20:00Z", "league": 6, "home": "Paris Saint-Germain", "away": "AS Roma", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915374"},
        {"date": "2026-11-25T20:00Z", "league": 6, "home": "Shakhtar Donetsk", "away": "Fenerbahce", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915375"},
        {"date": "2026-11-25T20:00Z", "league": 6, "home": "Sporting CP", "away": "Manchester United", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401915373"},
        {"date": "2026-11-25T23:00Z", "league": 11, "home": "Atlético-MG", "away": "Corinthians", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401841319"},
        {"date": "2026-11-26T00:00Z", "league": 10, "home": "Boca Juniors", "away": "Independiente Rivadavia", "status": "SCHEDULED", "home_score": 0, "away_score": 0, "p_id": "espn_401933757"},
    ]

    inserted = 0
    for f in fixtures:
        cur.execute("SELECT id FROM matches WHERE provider_match_id = %s;", (f["p_id"],))
        if cur.fetchone():
            continue
        ht_id = get_or_create_team(f["home"], f["league"])
        at_id = get_or_create_team(f["away"], f["league"])
        current_mid += 1
        cur.execute("""
            INSERT INTO matches (
                id, league_id, home_team_id, away_team_id, kickoff_at,
                status, minute, home_score, away_score, provider, provider_match_id, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 90 if %s == 'FINISHED' else None, %s, %s, 'espn', %s, now())
            ON CONFLICT DO NOTHING;
        """, (current_mid, f["league"], ht_id, at_id, f["date"], f["status"], f["status"], f["home_score"], f["away_score"], f["p_id"]))
        inserted += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Seeded {inserted} November fixtures!")

if __name__ == "__main__":
    seed_november_fixtures()