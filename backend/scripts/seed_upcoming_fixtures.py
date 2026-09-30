"""Seed upcoming matchday fixtures for the current upcoming window.

Idempotently creates scheduled matches for top European leagues so the Match
Intelligence Dashboard and Explorer display active upcoming matches, predictions,
and operational readiness.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from app.db.models.core import League, Match, Team, MatchStatus
from app.db.session import get_session_local, get_engine


def seed_upcoming() -> None:
    db = get_session_local()()
    now = datetime.now(timezone.utc)
    base_saturday = now.replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=(5 - now.weekday()) % 7 or 7)
    base_sunday = base_saturday + timedelta(days=1)

    fixtures = [
        # Premier League (Saturday & Sunday)
        ("EPL", "Arsenal", "Chelsea", base_saturday.replace(hour=15, minute=0), "epl-2026-upcoming-01"),
        ("EPL", "Man City", "Tottenham", base_saturday.replace(hour=17, minute=30), "epl-2026-upcoming-02"),
        ("EPL", "Liverpool", "Newcastle", base_saturday.replace(hour=12, minute=30), "epl-2026-upcoming-03"),
        ("EPL", "Aston Villa", "Everton", base_sunday.replace(hour=14, minute=0), "epl-2026-upcoming-04"),
        ("EPL", "Man United", "Brighton", base_sunday.replace(hour=16, minute=30), "epl-2026-upcoming-05"),

        # La Liga
        ("LA_LIGA", "Real Madrid", "Barcelona", base_sunday.replace(hour=20, minute=0), "laliga-2026-upcoming-01"),
        ("LA_LIGA", "Ath Madrid", "Sevilla", base_saturday.replace(hour=19, minute=0), "laliga-2026-upcoming-02"),
        ("LA_LIGA", "Betis", "Ath Bilbao", base_saturday.replace(hour=16, minute=15), "laliga-2026-upcoming-03"),

        # Serie A
        ("SERIE_A", "Inter", "Juventus", base_sunday.replace(hour=19, minute=45), "seriea-2026-upcoming-01"),
        ("SERIE_A", "Milan", "Roma", base_saturday.replace(hour=19, minute=45), "seriea-2026-upcoming-02"),
        ("SERIE_A", "Napoli", "Atalanta", base_saturday.replace(hour=17, minute=0), "seriea-2026-upcoming-03"),

        # Bundesliga
        ("BUNDESLIGA", "Bayern Munich", "Dortmund", base_saturday.replace(hour=16, minute=30), "bunde-2026-upcoming-01"),
        ("BUNDESLIGA", "Leverkusen", "RB Leipzig", base_saturday.replace(hour=14, minute=30), "bunde-2026-upcoming-02"),

        # Ligue 1
        ("LIGUE_1", "Paris SG", "Marseille", base_sunday.replace(hour=19, minute=45), "ligue1-2026-upcoming-01"),
        ("LIGUE_1", "Monaco", "Lyon", base_saturday.replace(hour=20, minute=0), "ligue1-2026-upcoming-02"),
    ]

    inserted = 0
    skipped = 0

    for league_code, home_name, away_name, kickoff_at, provider_id in fixtures:
        league = db.query(League).filter_by(code=league_code).first()
        if not league:
            continue

        home = db.query(Team).filter(Team.name.ilike(f"%{home_name}%")).first()
        away = db.query(Team).filter(Team.name.ilike(f"%{away_name}%")).first()

        if not home or not away:
            print(f"Skipping {home_name} vs {away_name}: teams not found (home={bool(home)}, away={bool(away)})")
            continue

        existing = db.query(Match).filter_by(provider="seed_upcoming", provider_match_id=provider_id).first()
        if existing:
            existing.kickoff_at = kickoff_at
            existing.status = MatchStatus.SCHEDULED.value
            skipped += 1
            continue

        match = Match(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=kickoff_at,
            status=MatchStatus.SCHEDULED.value,
            provider="seed_upcoming",
            provider_match_id=provider_id,
        )
        db.add(match)
        inserted += 1

    db.commit()
    print(f"Upcoming fixtures seeded: {inserted} inserted, {skipped} updated/skipped.")
    db.close()


if __name__ == "__main__":
    seed_upcoming()
