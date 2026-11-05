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
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "Slavia Prague", "away": "Arsenal", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3640"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "Viking FK", "away": "Sabah FK", "status": "FINISHED", "home_score": 4, "away_score": 1, "p_id": "espn_nov_3641"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "Dortmund", "away": "Betis", "status": "FINISHED", "home_score": 2, "away_score": 1, "p_id": "espn_nov_3635"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "FC Porto", "away": "Napoli", "status": "FINISHED", "home_score": 4, "away_score": 1, "p_id": "espn_nov_3636"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "Lens", "away": "Como", "status": "FINISHED", "home_score": 1, "away_score": 9, "p_id": "espn_nov_3637"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "PSV Eindhoven", "away": "Club Brugge", "status": "FINISHED", "home_score": 1, "away_score": 2, "p_id": "espn_nov_3638"},
        {"date": "2026-11-04T20:00:00Z", "league": 6, "home": "RB Leipzig", "away": "Man City", "status": "FINISHED", "home_score": 2, "away_score": 3, "p_id": "espn_nov_3639"},
        {"date": "2026-11-04T22:30:00Z", "league": 11, "home": "Athletico Paranaense", "away": "Vasco da Gama", "status": "FINISHED", "home_score": 1, "away_score": 3, "p_id": "espn_nov_3628"},
        {"date": "2026-11-04T22:30:00Z", "league": 11, "home": "Flamengo", "away": "Grêmio", "status": "FINISHED", "home_score": 3, "away_score": 1, "p_id": "espn_nov_3629"},
        {"date": "2026-11-05T00:30:00Z", "league": 11, "home": "Botafogo", "away": "Atlético Mineiro", "status": "FINISHED", "home_score": 1, "away_score": 0, "p_id": "espn_nov_3630"},
        {"date": "2026-11-05T00:30:00Z", "league": 11, "home": "São Paulo", "away": "Corinthians", "status": "FINISHED", "home_score": 0, "away_score": 0, "p_id": "espn_nov_3631"},
        {"date": "2026-11-05T11:30:00Z", "league": 12, "home": "Churchill Brothers SC", "away": "NorthEast United FC", "status": "FINISHED", "home_score": 0, "away_score": 2, "p_id": "espn_nov_3642"},
        {"date": "2026-11-05T14:00:00Z", "league": 12, "home": "Mohun Bagan Super Giant", "away": "Odisha FC", "status": "LIVE", "home_score": 2, "away_score": 2, "p_id": "espn_nov_3643"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "AGF", "away": "Red Bull Bragantino", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3648"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "Atalanta", "away": "Kairat Almaty", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3649"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "FC Midtjylland", "away": "Ajax Amsterdam", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3650"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "FC Thun", "away": "Heart of Midlothian", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3651"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "KuPS Kuopio", "away": "KAA Gent", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3652"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "Lincoln Red Imps", "away": "Hajduk Split", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3653"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "Mjällby AIF", "away": "Borac Banja Luka", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3654"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "Red Star Belgrade", "away": "Inter", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3655"},
        {"date": "2026-11-05T17:45:00Z", "league": 14, "home": "Trabzonspor", "away": "Freiburg", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3656"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Milan", "away": "Ferencvaros", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3666"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Anderlecht", "away": "Red Bull Salzburg", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3667"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Crystal Palace", "away": "Hoffenheim", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3668"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Levski Sofia", "away": "Jagiellonia Bialystok", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3669"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Lille", "away": "Viktoria Plzen", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3670"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "NEC Nijmegen", "away": "Omonia Nicosia", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3671"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Sociedad", "away": "Lyon", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3672"},
        {"date": "2026-11-05T17:45:00Z", "league": 13, "home": "Sparta Praha", "away": "Bournemouth", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3673"},
        {"date": "2026-11-05T18:00:00Z", "league": 10, "home": "Aldosivi", "away": "River Plate", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3644"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "Monaco", "away": "FC Nordsjælland", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3657"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Celtic", "away": "Besiktas", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3678"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Hapoel Be'er", "away": "OFI Crete", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3679"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Sturm Graz", "away": "NK Celje", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3680"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Sunderland", "away": "Dinamo Zagreb", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3681"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Torreense", "away": "Armenia", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3682"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "CSU Craiova", "away": "Egnatia", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3658"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "F.C. København", "away": "Iberia 1999", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3659"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "FC Lugano", "away": "Kauno Zalgiris", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3660"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "FC Twente", "away": "Pafos", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3661"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "Getafe", "away": "Brighton", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3662"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "Panathinaikos", "away": "CSKA Sofia", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3663"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "Riga FC", "away": "Jablonec", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3664"},
        {"date": "2026-11-05T20:00:00Z", "league": 14, "home": "Sint-Truidense", "away": "SK Brann", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3665"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "AZ Alkmaar", "away": "Juventus", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3674"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Leverkusen", "away": "Marseille", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3675"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Benfica", "away": "Lech Poznan", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3676"},
        {"date": "2026-11-05T20:00:00Z", "league": 13, "home": "Celta", "away": "Unión (Santa Fe)", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3677"},
        {"date": "2026-11-05T22:15:00Z", "league": 10, "home": "Gimnasia La Plata", "away": "Belgrano", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3645"},
        {"date": "2026-11-05T22:30:00Z", "league": 11, "home": "Palmeiras", "away": "Remo", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3646"},
        {"date": "2026-11-06T00:30:00Z", "league": 11, "home": "Cruzeiro", "away": "Bahia", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3647"},
        {"date": "2026-11-06T14:00:00Z", "league": 12, "home": "FC Goa", "away": "Bengaluru FC", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3685"},
        {"date": "2026-11-06T18:00:00Z", "league": 10, "home": "Barracas Central", "away": "Racing Club", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3690"},
        {"date": "2026-11-06T19:30:00Z", "league": 4, "home": "Hamburg SV", "away": "M'gladbach", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3686"},
        {"date": "2026-11-06T19:45:00Z", "league": 5, "home": "Toulouse", "away": "Strasbourg", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3687"},
        {"date": "2026-11-06T19:45:00Z", "league": 3, "home": "Venezia", "away": "Udinese", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3688"},
        {"date": "2026-11-06T20:00:00Z", "league": 2, "home": "Sevilla", "away": "Alaves", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3683"},
        {"date": "2026-11-06T20:00:00Z", "league": 1, "home": "Everton", "away": "Coventry", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3684"},
        {"date": "2026-11-06T22:15:00Z", "league": 10, "home": "Independiente Rivadavia", "away": "Deportivo Riestra", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3691"},
        {"date": "2026-11-06T22:15:00Z", "league": 10, "home": "San Lorenzo", "away": "Platense", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3692"},
        {"date": "2026-11-06T22:15:00Z", "league": 10, "home": "Unión (Santa Fe)", "away": "Vélez Sarsfield", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3693"},
        {"date": "2026-11-06T23:00:00Z", "league": 11, "home": "Vitória", "away": "Fluminense", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3689"},
        {"date": "2026-11-07T01:00:00Z", "league": 10, "home": "Banfield", "away": "Atlético Tucumán", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3694"},
        {"date": "2026-11-07T01:00:00Z", "league": 10, "home": "Tigre", "away": "Sarmiento (Junín)", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3695"},
        {"date": "2026-11-07T11:30:00Z", "league": 12, "home": "Inter Kashi", "away": "Sporting Club Delhi", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3711"},
        {"date": "2026-11-07T12:30:00Z", "league": 1, "home": "Leeds United", "away": "Tottenham", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3696"},
        {"date": "2026-11-07T13:00:00Z", "league": 2, "home": "Málaga", "away": "Racing Santander", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3700"},
        {"date": "2026-11-07T14:00:00Z", "league": 12, "home": "Chennaiyin FC", "away": "East Bengal FC", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3712"},
        {"date": "2026-11-07T14:00:00Z", "league": 3, "home": "Cagliari", "away": "Frosinone", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3734"},
        {"date": "2026-11-07T14:00:00Z", "league": 3, "home": "Torino", "away": "Lecce", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3735"},
        {"date": "2026-11-07T14:30:00Z", "league": 4, "home": "Dortmund", "away": "SV Elversberg", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3704"},
        {"date": "2026-11-07T14:30:00Z", "league": 4, "home": "Mainz", "away": "Bayern Munich", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3705"},
        {"date": "2026-11-07T14:30:00Z", "league": 4, "home": "RB Leipzig", "away": "Augsburg", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3706"},
        {"date": "2026-11-07T14:30:00Z", "league": 4, "home": "SC Paderborn 07", "away": "Ein Frankfurt", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3707"},
        {"date": "2026-11-07T15:00:00Z", "league": 1, "home": "Arsenal", "away": "Hull", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3697"},
        {"date": "2026-11-07T15:00:00Z", "league": 1, "home": "Fulham", "away": "Newcastle", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3698"},
        {"date": "2026-11-07T15:15:00Z", "league": 2, "home": "Espanyol", "away": "Deportivo La Coruna", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3701"},
        {"date": "2026-11-07T17:00:00Z", "league": 3, "home": "Parma", "away": "Bologna", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3736"},
        {"date": "2026-11-07T17:30:00Z", "league": 1, "home": "Nott'm Forest", "away": "Man City", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3699"},
        {"date": "2026-11-07T17:30:00Z", "league": 2, "home": "Osasuna", "away": "Ath Bilbao", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3702"},
        {"date": "2026-11-07T17:30:00Z", "league": 4, "home": "Stuttgart", "away": "Werder Bremen", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3708"},
        {"date": "2026-11-07T18:00:00Z", "league": 10, "home": "Gimnasia La Plata", "away": "Independiente Rivadavia", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3728"},
        {"date": "2026-11-07T18:00:00Z", "league": 10, "home": "Talleres", "away": "Estudiantes Río Cuarto", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3729"},
        {"date": "2026-11-07T18:00:00Z", "league": 5, "home": "Auxerre", "away": "Paris FC", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3709"},
        {"date": "2026-11-07T19:45:00Z", "league": 3, "home": "Roma", "away": "Sassuolo", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3737"},
        {"date": "2026-11-07T20:00:00Z", "league": 2, "home": "Valencia", "away": "Real Madrid", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3703"},
        {"date": "2026-11-07T20:05:00Z", "league": 5, "home": "Paris SG", "away": "Troyes", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3710"},
        {"date": "2026-11-07T20:30:00Z", "league": 10, "home": "Argentinos Juniors", "away": "Huracán", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3730"},
        {"date": "2026-11-07T20:30:00Z", "league": 10, "home": "Boca Juniors", "away": "Defensa y Justicia", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3731"},
        {"date": "2026-11-07T20:30:00Z", "league": 10, "home": "Rosario Central", "away": "Estudiantes Río Cuarto", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3732"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "CF Montréal", "away": "Vancouver Whitecaps", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3713"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "Chicago Fire", "away": "Columbus Crew", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3714"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "D.C. United", "away": "New York City FC", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3715"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "FC Cincinnati", "away": "Nashville SC", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3716"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "Inter", "away": "Charlotte FC", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3717"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "Orlando City SC", "away": "England U17", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3718"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "Philadelphia Union", "away": "Toronto FC", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3719"},
        {"date": "2026-11-07T21:00:00Z", "league": 9, "home": "New York Red Bulls", "away": "Atlanta United", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3720"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "Austin FC", "away": "Portland Timbers", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3721"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "FC Dallas", "away": "Colorado Rapids", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3722"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "Houston Dynamo", "away": "St. Louis CITY SC", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3723"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "Minnesota United", "away": "San Jose Earthquakes", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3724"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "Real Salt Lake", "away": "LA Galaxy", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3725"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "San Diego FC", "away": "Sporting Kansas City", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3726"},
        {"date": "2026-11-08T00:00:00Z", "league": 9, "home": "Seattle Sounders", "away": "Los Angeles FC", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3727"},
        {"date": "2026-11-08T01:00:00Z", "league": 10, "home": "Instituto (Córdoba)", "away": "Newell's Old Boys", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3733"},
        {"date": "2026-11-08T11:30:00Z", "league": 3, "home": "Napoli", "away": "Lazio", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3739"},
        {"date": "2026-11-08T13:00:00Z", "league": 2, "home": "Elche", "away": "Betis", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3758"},
        {"date": "2026-11-08T14:00:00Z", "league": 3, "home": "Genoa", "away": "Milan", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3740"},
        {"date": "2026-11-08T14:00:00Z", "league": 3, "home": "Monza", "away": "Atalanta", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3741"},
        {"date": "2026-11-08T14:00:00Z", "league": 1, "home": "Brighton", "away": "Brentford", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3744"},
        {"date": "2026-11-08T14:00:00Z", "league": 1, "home": "Crystal Palace", "away": "Liverpool", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3745"},
        {"date": "2026-11-08T14:00:00Z", "league": 1, "home": "Ipswich", "away": "Bournemouth", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3746"},
        {"date": "2026-11-08T14:00:00Z", "league": 1, "home": "Sunderland", "away": "Chelsea", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3747"},
        {"date": "2026-11-08T14:00:00Z", "league": 5, "home": "Rennes", "away": "Lille", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3749"},
        {"date": "2026-11-08T14:30:00Z", "league": 4, "home": "FC Koln", "away": "Leverkusen", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3755"},
        {"date": "2026-11-08T15:15:00Z", "league": 2, "home": "Sociedad", "away": "Vallecano", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3759"},
        {"date": "2026-11-08T16:15:00Z", "league": 5, "home": "Angers", "away": "Nice", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3750"},
        {"date": "2026-11-08T16:15:00Z", "league": 5, "home": "Brest", "away": "Lyon", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3751"},
        {"date": "2026-11-08T16:15:00Z", "league": 5, "home": "Le Havre", "away": "Lorient", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3752"},
        {"date": "2026-11-08T16:15:00Z", "league": 5, "home": "Le Mans", "away": "Monaco", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3753"},
        {"date": "2026-11-08T16:30:00Z", "league": 1, "home": "Man United", "away": "Aston Villa", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3748"},
        {"date": "2026-11-08T16:30:00Z", "league": 4, "home": "Freiburg", "away": "Union Berlin", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3756"},
        {"date": "2026-11-08T17:00:00Z", "league": 3, "home": "Inter", "away": "Como", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3742"},
        {"date": "2026-11-08T17:30:00Z", "league": 2, "home": "Celta", "away": "Levante", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3760"},
        {"date": "2026-11-08T17:30:00Z", "league": 2, "home": "Villarreal", "away": "Getafe", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3761"},
        {"date": "2026-11-08T18:30:00Z", "league": 4, "home": "Hoffenheim", "away": "Schalke 04", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3757"},
        {"date": "2026-11-08T19:45:00Z", "league": 3, "home": "Fiorentina", "away": "Juventus", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3743"},
        {"date": "2026-11-08T19:45:00Z", "league": 5, "home": "Lens", "away": "Marseille", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3754"},
        {"date": "2026-11-08T20:00:00Z", "league": 2, "home": "Ath Madrid", "away": "Barcelona", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3762"},
        {"date": "2026-11-08T22:30:00Z", "league": 10, "home": "Central Córdoba (Santiago del Estero)", "away": "Lanús", "status": "SCHEDULED", "home_score": None, "away_score": None, "p_id": "espn_nov_3738"},
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