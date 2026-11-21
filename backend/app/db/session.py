"""DB engine/session helpers. SQLite is supported for tests; Postgres for prod, with resilient SQLite fallback."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def _seed_from_cache(db, cache_path: str):
    """Seed initial leagues, teams, and matches from cache if database is empty."""
    import json
    from app.db.models.core import League, Team, Match

    try:
        leagues = [
            (1, 'EPL', 'Premier League', 'England', '2026'),
            (2, 'LA_LIGA', 'La Liga', 'Spain', '2026'),
            (3, 'SERIE_A', 'Serie A', 'Italy', '2026'),
            (4, 'BUNDESLIGA', 'Bundesliga', 'Germany', '2026'),
            (5, 'LIGUE_1', 'Ligue 1', 'France', '2026'),
            (6, 'UCL', 'UEFA Champions League', 'Europe', '2026'),
            (9, 'MLS', 'Major League Soccer', 'USA', '2026'),
            (10, 'LIGA_ARG', 'Liga Profesional Argentina', 'Argentina', '2026'),
            (11, 'BRA_SERIE_A', 'Brasileirão Série A', 'Brazil', '2026'),
            (12, 'ISL', 'Indian Super League', 'India', '2026'),
            (13, 'UEL', 'UEFA Europa League', 'Europe', '2026'),
            (14, 'UECL', 'UEFA Conference League', 'Europe', '2026'),
            (15, 'UNL', 'UEFA Nations League', 'Europe', '2026')
        ]
        for lid, code, name, country, season in leagues:
            if not db.query(League).filter_by(id=lid).first():
                db.add(League(id=lid, code=code, name=name, country=country, season=season, provider='curated', provider_league_id=f'lg_{lid}'))
        db.commit()

        if not os.path.exists(cache_path):
            return

        with open(cache_path) as f:
            cache = json.load(f)

        teams_map = {}
        for t in db.query(Team).all():
            teams_map[t.name] = t.id

        cur_max_tid = max((t.id for t in db.query(Team).all()), default=0)
        cur_max_mid = max((m.id for m in db.query(Match).all()), default=1000)

        seen_pids = {m.provider_match_id for m in db.query(Match.provider_match_id).all() if m.provider_match_id}

        for dt, mlist in cache.items():
            for m in mlist:
                h_name = m['home']
                a_name = m['away']
                lid = m['league']
                p_id = m.get('p_id')

                if p_id and p_id in seen_pids:
                    continue

                if h_name not in teams_map:
                    cur_max_tid += 1
                    t = Team(
                        id=cur_max_tid, league_id=lid, name=h_name, short_name=h_name[:20],
                        provider='curated', provider_team_id=f'team_{cur_max_tid}',
                        logo_url=f'https://a.espncdn.com/i/teamlogos/soccer/500/{cur_max_tid}.png'
                    )
                    db.add(t)
                    teams_map[h_name] = cur_max_tid

                if a_name not in teams_map:
                    cur_max_tid += 1
                    t = Team(
                        id=cur_max_tid, league_id=lid, name=a_name, short_name=a_name[:20],
                        provider='curated', provider_team_id=f'team_{cur_max_tid}',
                        logo_url=f'https://a.espncdn.com/i/teamlogos/soccer/500/{cur_max_tid}.png'
                    )
                    db.add(t)
                    teams_map[a_name] = cur_max_tid

                ht_id = teams_map[h_name]
                at_id = teams_map[a_name]
                cur_max_mid += 1

                date_str = m['date']
                dt_clean = date_str.replace('Z', '+00:00')
                ko_dt = datetime.fromisoformat(dt_clean).replace(tzinfo=None)

                match_obj = Match(
                    id=cur_max_mid,
                    league_id=lid,
                    home_team_id=ht_id,
                    away_team_id=at_id,
                    kickoff_at=ko_dt,
                    status=m['status'],
                    minute=90 if m['status'] == 'FINISHED' else (45 if m['status'] == 'LIVE' else None),
                    home_score=m.get('home_score'),
                    away_score=m.get('away_score'),
                    provider='espn',
                    provider_match_id=p_id or f'espn_{cur_max_mid}'
                )
                db.add(match_obj)
                if p_id:
                    seen_pids.add(p_id)

        db.commit()
        logger.info("Resilient fallback database seeded successfully with %d teams and %d matches", len(teams_map), len(seen_pids))
    except Exception as ex:
        db.rollback()
        logger.warning("Error seeding fallback database: %s", ex)


def _ensure_sqlite_ready(engine):
    from app.db.base import Base
    from app.db.models.core import Match

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with session_factory() as db:
        try:
            if db.query(Match).count() == 0:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                cache_path = os.path.join(base_dir, "scripts", "november_matches_cache.json")
                _seed_from_cache(db, cache_path)
        except Exception as ex:
            logger.warning("Could not check/seed fallback database: %s", ex)


def get_engine():
    global _engine
    if _engine is None:
        url = get_settings().DATABASE_URL
        is_postgres = any(url.startswith(prefix) for prefix in ("postgresql", "postgres"))

        if is_postgres:
            # Normalize postgres:// to postgresql:// (common in Render/Heroku)
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            # Ensure driver compatibility
            if url.startswith("postgresql://"):
                try:
                    import psycopg  # noqa: F401
                except ImportError:
                    url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

            try:
                # Test connection to PostgreSQL with short timeout to prevent slow boots
                connect_args = {}
                if "psycopg" in url:
                    connect_args = {"connect_timeout": 3}
                test_engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
                with test_engine.connect():
                    pass
                _engine = test_engine
                logger.info("Connected successfully to PostgreSQL database.")
                return _engine
            except Exception as ex:
                logger.warning(
                    "PostgreSQL unreachable (%s); gracefully falling back to local SQLite database.",
                    ex,
                )
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                db_path = os.path.join(base_dir, "dev.db")
                url = f"sqlite:///{db_path}"

        kwargs = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs = {}
        _engine = create_engine(url, **kwargs)

        if url.startswith("sqlite"):
            _ensure_sqlite_ready(_engine)

    return _engine


def get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def reset_engine() -> None:
    """Test helper: drop cached engine/session so DATABASE_URL changes take effect."""
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None
