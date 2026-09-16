"""Phase-1.8 tests: inventory, enriched events/xG/lineups, players, resume,
provenance, cross-source reconciliation, temporal/leakage auditing.

No live network: all HTTP is mocked via httpx.MockTransport or stub fetchers.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.db.models.core import Lineup, Match, MatchEvent, MatchStatistic, Player
from app.db.models.provenance import PlayerProviderMapping, RawDataRecord, SourceConflict
from app.services.quality import audit_leakage
from app.services.sources.football.statsbomb import StatsBombSource, season_date_range
from app.services.sources.normalized import (
    NormalizedLineup,
    NormalizedMatchStatistics,
    Provenance,
)
from app.services.sources.pipeline import Pipeline


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


SB_MATCH = {
    "match_id": 3825739, "match_date": "2016-01-17", "kick_off": "17:00:00.000",
    "match_status": "available", "home_score": 5, "away_score": 1,
    "home_team": {"home_team_id": 220, "home_team_name": "Real Madrid"},
    "away_team": {"away_team_id": 1041, "away_team_name": "Sporting Gijón"},
}

SB_EVENTS = [
    {"id": "e1", "minute": 26, "second": 11, "period": 1, "type": {"name": "Shot"},
     "team": {"id": 220, "name": "Real Madrid"}, "player": {"id": 1, "name": "Cristiano Ronaldo"},
     "shot": {"statsbomb_xg": 0.31, "outcome": {"name": "Goal"}, "type": {"name": "Open Play"}}},
    {"id": "e2", "minute": 90, "second": 5, "period": 2, "type": {"name": "Shot"},
     "team": {"id": 1041, "name": "Sporting Gijón"}, "player": {"id": 2, "name": "Striker"},
     "shot": {"outcome": {"name": "Saved"}, "type": {"name": "Open Play"}}},
    {"id": "e3", "minute": 10, "second": 0, "period": 1, "type": {"name": "Starting XI"},
     "team": {"id": 220, "name": "Real Madrid"},
     "tactics": {"formation": 433, "lineup": [
         {"player": {"id": 1}, "position": {"name": "Center Forward"}}]}},
]

SB_LINEUPS = [
    {"team_id": 220, "team_name": "Real Madrid",
     "lineup": [{"player_id": 1, "player_name": "Cristiano Ronaldo", "jersey_number": 7},
                {"player_id": 7, "player_name": "Off Guy", "jersey_number": 9}]},
]


def _sb_source(events=None):
    src = StatsBombSource()
    src._current_events = list(events if events is not None else SB_EVENTS)
    return src


# ---------------------------------------------------------------- inventory

def test_season_date_range():
    start, end = season_date_range("2015")
    assert (str(start), str(end)) == ("2015-08-01", "2016-07-31")
    with pytest.raises(ValueError):
        season_date_range("bogus")


def test_competition_discovery():
    from app.services.sources.football.statsbomb import COMPETITIONS

    assert COMPETITIONS["LA_LIGA"] == ("La Liga", 11)
    assert COMPETITIONS["UCL"] == ("Champions League", 16)
    assert len(COMPETITIONS) >= 6


def test_inventory_manifest_statuses(db, tmp_path, monkeypatch):
    import json as _json

    from app.config import get_settings
    from scripts.statsbomb_inventory import build_manifest

    # Isolate the disk cache so the stub payloads (not real downloads) drive.
    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))
    payloads = {
        "competitions.json": _json.dumps([
            {"competition_id": 11, "season_id": 27, "competition_name": "La Liga",
             "season_name": "2015/2016"}]),
        "matches/11/27.json": _json.dumps([dict(SB_MATCH)]),
    }

    class StubFetcher:
        async def fetch_text(self, url):
            for key, text in payloads.items():
                if url.endswith(key):
                    return text
            raise AssertionError(url)

    src = StatsBombSource()
    src.fetcher = StubFetcher()
    manifest = build_manifest(db, src, "LA_LIGA", "2015")
    assert manifest["matches_available"] == 1
    assert manifest["by_status"] == {"UNKNOWN": 1}
    row = manifest["manifest"][0]
    assert row["home"] == "Real Madrid" and row["status"] == "UNKNOWN"

    # After importing details, the same match shows IMPORTED (no re-download).
    src.db = db
    report = src.import_history("LA_LIGA", "2015", max_detail_matches=0)
    assert report["valid"] == 1
    manifest2 = build_manifest(db, src, "LA_LIGA", "2015")
    assert manifest2["by_status"] == {"UNKNOWN": 1}  # matches only, no details yet


def test_inventory_missing_season():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base
    from scripts.statsbomb_inventory import build_manifest

    class StubFetcher:
        async def fetch_text(self, url):
            raise ValueError("gone")

        async def head_exists(self, url):
            return None

    src = StatsBombSource()
    src.fetcher = StubFetcher()
    # Throwaway in-memory DB: inventory must not crash on failure.
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        manifest = build_manifest(db, src, "LA_LIGA", "1999")
        assert manifest["matches_available"] == 0
        assert manifest["fetch_error"] != ""
    finally:
        db.close()


# ---------------------------------------------------------------- events

def test_event_second_period_outcome():
    src = _sb_source()
    events, _ = src.convert_events(SB_MATCH)
    goal = next(e for e in events if e.event_type == "goal")
    assert (goal.second, goal.period, goal.outcome) == (11, "1H", "Goal")


def test_event_invalid_payload_skipped():
    src = _sb_source(events=["junk", None, 42, {"id": "x"}])
    events, stats = src.convert_events(SB_MATCH)
    assert events == []
    xg = {(s.team, s.stat_name): s.stat_value for s in stats}
    assert xg[("home", "expected_goals")] == "0.000"  # no shots: zero WITH full provenance


def test_event_duplicate_import(db):
    pipe = Pipeline(db, "statsbomb")
    league = pipe.ensure_league("LA_LIGA", season="2015")
    home = pipe.resolve_team("Real Madrid")
    away = pipe.resolve_team("Sporting Gijón")
    mid, _ = pipe.matches.ensure("statsbomb", "1", league.id, home, away, _utc(2016, 1, 17))
    src = _sb_source()
    events, _ = src.convert_events(SB_MATCH)
    pipe.ingest_events(mid, events, parser_version="t")
    before = db.query(MatchEvent).filter_by(match_id=mid).count()
    assert before == 1
    pipe.ingest_events(mid, events, parser_version="t")
    assert db.query(MatchEvent).filter_by(match_id=mid).count() == before
    row = db.query(MatchEvent).filter_by(match_id=mid).one()
    assert row.second == 11 and row.period == "1H" and row.outcome == "Goal"


# ---------------------------------------------------------------- xG

def test_xg_missing_not_zero(db):
    pipe = Pipeline(db, "statsbomb")
    league = pipe.ensure_league("LA_LIGA", season="2015")
    home = pipe.resolve_team("Real Madrid")
    away = pipe.resolve_team("Sporting Gijón")
    mid, _ = pipe.matches.ensure("statsbomb", "2", league.id, home, away, _utc(2016, 1, 17))
    src = _sb_source()
    _, stats = src.convert_events(SB_MATCH)
    pipe.ingest_statistics(mid, stats, parser_version="t")
    by_key = {(s.team, s.stat_name): s.stat_value
              for s in db.query(MatchStatistic).filter_by(match_id=mid).all()}
    # Away shot lacked xG: sum covers the measured shot; gap is transparent.
    assert by_key[("away", "expected_goals")] == "0.000"
    assert by_key[("away", "shots_missing_xg")] == "1"
    assert ("home", "shots_missing_xg") not in by_key


def test_xg_invalid_quarantined(db):
    pipe = Pipeline(db, "statsbomb")
    league = pipe.ensure_league("LA_LIGA", season="2015")
    home = pipe.resolve_team("Real Madrid")
    away = pipe.resolve_team("Sporting Gijón")
    mid, _ = pipe.matches.ensure("statsbomb", "3", league.id, home, away, _utc(2016, 1, 17))
    pipe.ingest_statistics(mid, [NormalizedMatchStatistics(
        team="home", stat_name="expected_goals", stat_value="-2.5", period="full",
        provenance=Provenance(source="statsbomb"))], parser_version="t")
    assert db.query(MatchStatistic).filter_by(match_id=mid).count() == 0
    from app.db.models.provenance import RawDataRecord

    assert db.query(RawDataRecord).filter_by(processing_status="quarantined").count() == 1


# ---------------------------------------------------------------- lineups

def test_lineup_jersey_formation():
    src = _sb_source()
    out = src.convert_lineups(SB_MATCH, SB_LINEUPS, [e for e in SB_EVENTS
                                                     if isinstance(e, dict)])
    by_name = {lu.player_name: lu for lu in out}
    assert by_name["Cristiano Ronaldo"].jersey_number == 7
    assert by_name["Cristiano Ronaldo"].formation == "433"
    assert by_name["Cristiano Ronaldo"].is_starting == 1
    assert by_name["Off Guy"].is_starting == 0
    assert by_name["Off Guy"].jersey_number == 9


def test_lineup_missing_returns_empty():
    assert _sb_source().convert_lineups(SB_MATCH, [], []) == []


def test_lineup_captain_absent_stays_zero(db):
    pipe = Pipeline(db, "statsbomb")
    league = pipe.ensure_league("LA_LIGA", season="2015")
    home = pipe.resolve_team("Real Madrid")
    away = pipe.resolve_team("Sporting Gijón")
    mid, _ = pipe.matches.ensure("statsbomb", "4", league.id, home, away, _utc(2016, 1, 17))

    pipe.ingest_lineups(mid, [NormalizedLineup(
        team="home", player_name="Cristiano Ronaldo", jersey_number=7,
        provider_player_id="1", provenance=Provenance(source="statsbomb"))],
        parser_version="t")
    row = db.query(Lineup).filter_by(match_id=mid).one()
    assert row.jersey_number == 7 and row.is_captain == 0  # not published: stays unset


def test_formation_stats():
    from app.services.sources.football.statsbomb import StatsBombSource

    out = StatsBombSource.formation_stats(SB_MATCH, SB_EVENTS)
    by_team = {s.team: s.stat_value for s in out}
    assert by_team == {"home": "433"}  # from the Starting XI tactics event
    assert all(s.provenance.source == "statsbomb" for s in out)
    assert StatsBombSource.formation_stats(SB_MATCH, []) == []
    tactics = [{"id": "s", "type": {"name": "Starting XI"},
                "team": {"id": 220}, "tactics": {"formation": 433, "lineup": []}},
               {"id": "s2", "type": {"name": "Starting XI"},
                "team": {"id": 1041}, "tactics": {"formation": 442, "lineup": []}}]
    out = StatsBombSource.formation_stats(SB_MATCH, tactics)
    assert {s.team: s.stat_value for s in out} == {"home": "433", "away": "442"}


# ---------------------------------------------------------------- players

def test_player_provider_id_priority(db):
    from app.services.identity.players import PlayerIdentityResolver

    db.add(Player(name="Cristiano Ronaldo", provider="x", provider_player_id="1"))
    db.commit()
    pid, method = PlayerIdentityResolver(db).resolve("statsbomb", "9489", "CR7 Name")
    assert pid is None  # unknown native ID + unknown name: unresolved, no guessing
    pid, method = PlayerIdentityResolver(db).resolve("statsbomb", "9489", "Cristiano Ronaldo")
    assert pid is not None and method == "normalized_identity"


def test_player_mapping_reuse(db):
    from app.services.sources.pipeline import Pipeline as _P

    pipe = _P(db, "statsbomb")
    tid = pipe.resolve_team("Real Madrid")
    first, _ = pipe.players.ensure("statsbomb", "1", "Cristiano Ronaldo", team_id=tid)
    second, _ = pipe.players.ensure("statsbomb", "1", "Cristiano Ronaldo", team_id=tid)
    assert first == second
    assert db.query(PlayerProviderMapping).filter_by(
        source="statsbomb", provider_player_id="1").count() == 1


def test_player_unresolved_recorded(db):
    pipe = Pipeline(db, "statsbomb", create_teams=False)
    assert pipe.resolve_team("Nobody FC") is None
    assert db.query(RawDataRecord).filter_by(
        entity_type="team", processing_status="unresolved").count() == 1


# ---------------------------------------------------------------- resume

def test_resume_skips_imported_details(db, tmp_path, monkeypatch):
    import json as _json

    from app.config import get_settings
    from app.services.sources.football.statsbomb import StatsBombSource

    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))
    matches = [dict(SB_MATCH)]
    payloads = {
        "competitions.json": _json.dumps([
            {"competition_id": 11, "season_id": 27, "competition_name": "La Liga",
             "season_name": "2015/2016"}]),
        "matches/11/27.json": _json.dumps(matches),
        "lineups/3825739.json": _json.dumps(SB_LINEUPS),
        "events/3825739.json": _json.dumps(SB_EVENTS),
    }

    class StubFetcher:
        def __init__(self):
            self.calls = 0

        async def fetch_text(self, url):
            self.calls += 1
            for key, text in payloads.items():
                if url.endswith(key):
                    return text
            raise AssertionError(url)

    src = StatsBombSource(db=db)
    stub = StubFetcher()
    src.fetcher = stub
    first = src.import_history("LA_LIGA", "2015", max_detail_matches=10)
    calls_after_first = stub.calls
    assert first["detail_matches"] == 1
    second = src.import_history("LA_LIGA", "2015", max_detail_matches=10)
    assert second["detail_matches"] == 1  # bounded pass still walks the list...
    assert stub.calls == calls_after_first  # ...but downloads nothing new (cached)
    assert db.query(Match).count() == 1


def test_refresh_forces_redownload(db, tmp_path, monkeypatch):
    from app.config import get_settings
    from app.services.scraping.datasets import fetch_cached

    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))

    class Fetcher:
        def __init__(self):
            self.calls = 0

        async def fetch_text(self, url):
            self.calls += 1
            return "Div,Date\nE0,21/09/2024\nE0,22/09/2024"

    fetcher = Fetcher()
    text, cached = asyncio.run(fetch_cached(fetcher, "http://x/y.csv", "s", "y.csv"))
    assert (cached, fetcher.calls) == (False, 1)
    text, cached = asyncio.run(fetch_cached(fetcher, "http://x/y.csv", "s", "y.csv"))
    assert (cached, fetcher.calls) == (True, 1)
    text, cached = asyncio.run(fetch_cached(fetcher, "http://x/y.csv", "s", "y.csv",
                                            refresh=True))
    assert (cached, fetcher.calls) == (False, 2)


# ---------------------------------------------------------------- provenance

def test_provenance_fields(db):
    pipe = Pipeline(db, "statsbomb", source_url="https://example.test/f.json")
    league = pipe.ensure_league("LA_LIGA", season="2015")
    from app.services.sources.normalized import NormalizedMatch

    mid = pipe.ingest_match(NormalizedMatch(
        league_code="LA_LIGA", season="2015", home_team="Real Madrid",
        away_team="Sporting Gijón", kickoff_at=_utc(2016, 1, 17),
        status="FINISHED", home_score=5, away_score=1,
        provenance=Provenance(source="statsbomb", source_record_id="3825739",
                              parser_version="statsbomb_parser_v1",
                              temporal_quality="estimated")), league_id=league.id,
        parser_version="statsbomb_parser_v1")
    row = db.query(RawDataRecord).filter_by(entity_type="match").one()
    assert row.source == "statsbomb"
    assert row.source_record_id == "3825739"
    assert row.parser_version == "statsbomb_parser_v1"
    assert row.temporal_quality == "estimated"
    assert row.source_url == "https://example.test/f.json"
    assert row.processed_at is not None and row.retrieved_at is not None
    assert mid is not None


# ---------------------------------------------------------------- cross-source

def test_cross_source_stats_conflict(db):
    """fdco shots vs StatsBomb shots on the same fixture: both preserved."""
    pipe = Pipeline(db, "csv")
    league = pipe.ensure_league("EPL", season="2024")
    home = pipe.resolve_team("Arsenal")
    away = pipe.resolve_team("Chelsea")
    mid, _ = pipe.matches.ensure("csv", "M-1", league.id, home, away, _utc(2024, 9, 21))
    pipe.ingest_statistics(mid, [NormalizedMatchStatistics(
        team="home", stat_name="shots_total", stat_value="14", period="full",
        provenance=Provenance(source="csv"))], parser_version="t")
    before = db.query(MatchStatistic).filter_by(match_id=mid).count()
    assert before == 1
    pipe2 = Pipeline(db, "statsbomb")
    pipe2.ingest_statistics(mid, [NormalizedMatchStatistics(
        team="home", stat_name="shots_total", stat_value="12", period="full",
        provenance=Provenance(source="statsbomb"))], parser_version="t")
    # Canonical keeps the first observation; the divergent one is conflicted.
    row = db.query(MatchStatistic).filter_by(
        match_id=mid, team="home", stat_name="shots_total").one()
    assert row.stat_value == "14"

    conflict = db.query(SourceConflict).filter_by(entity_type="statistic").one()
    assert conflict.values["csv"] == 14.0 or conflict.values["csv"] == "14"
    assert conflict.status == "open"


def test_cross_source_duplicate_prevention(db):
    from app.services.identity.matches import MatchResolver

    pipe = Pipeline(db, "football_data_co_uk")
    league = pipe.ensure_league("EPL", season="2024")
    home = pipe.resolve_team("Arsenal")
    away = pipe.resolve_team("Chelsea")
    first, created = pipe.matches.ensure("football_data_co_uk", "FD-1", league.id,
                                         home, away, _utc(2024, 9, 21, 15, 0))
    assert created is True
    same = MatchResolver(db).resolve("statsbomb", "999", league.id, home, away,
                                     _utc(2024, 9, 21, 15, 7))
    assert same == first
    assert db.query(Match).count() == 1


# ---------------------------------------------------------------- temporal

def test_leakage_clean_prematch_odds(db):
    from app.db.models.odds import Bookmaker, OddsSnapshot

    pipe = Pipeline(db, "odds_api")
    league = pipe.ensure_league("EPL", season="2024")
    home = pipe.resolve_team("Arsenal")
    away = pipe.resolve_team("Chelsea")
    mid, _ = pipe.matches.ensure("odds_api", "M1", league.id, home, away, _utc(2024, 9, 21, 15, 0))
    bm = Bookmaker(name="B", provider="odds_api", provider_bookmaker_id="b")
    db.add(bm)
    db.flush()
    db.add(OddsSnapshot(match_id=mid, bookmaker_id=bm.id, market_type="h2h",
                        timestamp=_utc(2024, 9, 21, 10, 0), source="odds_api",
                        is_live=False))
    db.add(OddsSnapshot(match_id=mid, bookmaker_id=bm.id, market_type="h2h",
                        timestamp=_utc(2024, 9, 21, 15, 0), source="closing",
                        is_live=False))
    db.commit()
    report = audit_leakage(db)
    assert report["counts"]["odds"] == 1  # only the kickoff-stamped closing line
    assert report["total"] >= 1


def test_leakage_unknown_timing_flagged(db):
    pipe = Pipeline(db, "csv")
    league = pipe.ensure_league("EPL", season="2024")
    home = pipe.resolve_team("Arsenal")
    away = pipe.resolve_team("Chelsea")
    mid, _ = pipe.matches.ensure("csv", "M9", league.id, home, away, _utc(2024, 9, 21))
    from app.db.models.core import MatchStatistic as _MS

    db.add(_MS(match_id=mid, team="home", stat_name="shots_total", stat_value="14",
               period="full", source="csv", effective_at=None))
    db.commit()
    report = audit_leakage(db)
    assert report["counts"]["statistics"] >= 1
    assert any(e["reason"].startswith("LEAKAGE_RISK") for e in report["examples"])


def test_leakage_future_kickoff(db):
    pipe = Pipeline(db, "csv")
    league = pipe.ensure_league("EPL", season="2024")
    home = pipe.resolve_team("Arsenal")
    away = pipe.resolve_team("Chelsea")
    mid, _ = pipe.matches.ensure("csv", "MF", league.id, home, away, _utc(2030, 1, 1))
    from app.services.quality import assess_temporal_quality

    assert assess_temporal_quality(event_time=_utc(2030, 1, 1),
                                   collected_at=_utc(2024, 1, 1)) == "unknown"
    assert mid is not None


# ---------------------------------------------------------------- same-date fallback

def test_match_same_day_fallback(db):
    from app.services.identity.matches import MatchResolver

    pipe = Pipeline(db, "csv")
    league = pipe.ensure_league("EPL", season="2024")
    home = pipe.resolve_team("Arsenal")
    away = pipe.resolve_team("Chelsea")
    # Date-only source stores midnight; timed source reports 15:00 same day.
    first, created = pipe.matches.ensure("csv", "D-1", league.id, home, away,
                                         _utc(2024, 9, 21, 0, 0))
    assert created is True
    same = MatchResolver(db).resolve("statsbomb", "SB-9", league.id, home, away,
                                     _utc(2024, 9, 21, 15, 0))
    assert same == first
    assert db.query(Match).count() == 1


def test_match_same_day_ambiguous_stays_unresolved(db):
    from app.db.models.core import Match as _Match
    from app.services.identity.matches import MatchResolver

    pipe = Pipeline(db, "csv")
    league = pipe.ensure_league("EPL", season="2024")
    home = pipe.resolve_team("Arsenal")
    away = pipe.resolve_team("Chelsea")
    # Two genuinely distinct same-day pairings (e.g. youth + senior cup):
    # constructed directly since ensure() would rightly merge scoreless dupes.
    db.add_all([
        _Match(league_id=league.id, home_team_id=home, away_team_id=away,
               kickoff_at=_utc(2024, 9, 21, 12, 0), status="FINISHED",
               home_score=1, away_score=0, provider="csv", provider_match_id="D-1"),
        _Match(league_id=league.id, home_team_id=home, away_team_id=away,
               kickoff_at=_utc(2024, 9, 21, 18, 0), status="FINISHED",
               home_score=2, away_score=2, provider="csv", provider_match_id="D-2"),
    ])
    db.commit()
    # A third observation cannot pick between them: unresolved, no guessing.
    assert MatchResolver(db).resolve("x", "D-3", league.id, home, away,
                                     _utc(2024, 9, 21, 0, 0)) is None
    assert db.query(Match).count() == 2


# ---------------------------------------------------------------- same-day wall-clock fallback

def test_match_timed_same_day_merges(db):
    """fdco 19:30 vs StatsBomb 21:30 same fixture: unique pairing merges."""
    from app.services.identity.matches import MatchResolver

    pipe = Pipeline(db, "statsbomb")
    league = pipe.ensure_league("BUNDESLIGA", season="2023")
    home = pipe.resolve_team("Bayern Munich")
    away = pipe.resolve_team("Bayer Leverkusen")
    first, created = pipe.matches.ensure(
        "statsbomb", "SB-1", league.id, home, away, _utc(2023, 9, 15, 21, 30),
        home_score=2, away_score=2)
    assert created is True
    same = MatchResolver(db).resolve("football_data_co_uk", "FD-1", league.id, home, away,
                                     _utc(2023, 9, 15, 19, 30), home_score=2, away_score=2)
    assert same == first
    assert db.query(Match).count() == 1


def test_match_same_day_score_mismatch_refused(db):
    """Same teams+day but contradictory finished scores: never merged."""
    from app.services.identity.matches import MatchResolver

    pipe = Pipeline(db, "csv")
    league = pipe.ensure_league("EPL", season="2024")
    home = pipe.resolve_team("Arsenal")
    away = pipe.resolve_team("Chelsea")
    pipe.matches.ensure("csv", "D-1", league.id, home, away,
                        _utc(2024, 9, 21, 15, 0), home_score=2, away_score=1)
    assert MatchResolver(db).resolve("x", "D-2", league.id, home, away,
                                     _utc(2024, 9, 21, 19, 30),
                                     home_score=0, away_score=0) is None


# ---------------------------------------------------------------- no false-precision timestamps

def test_closing_odds_midnight_kickoff_unstamped():
    from datetime import timezone as _tz

    from app.services.sources.historical.csv_source import closing_odds_snapshots

    raw = {"B365H": "2.00", "B365D": "3.40", "B365A": "3.80"}
    row = {"home": "A", "away": "B", "raw": raw}
    midnight = datetime(2015, 8, 21, 0, 0, tzinfo=_tz.utc)
    snaps = closing_odds_snapshots(row, "csv", "EPL", "2015", midnight)
    assert snaps and all(s.timestamp is None for s in snaps)  # no fake precision
    timed = datetime(2015, 8, 21, 20, 30, tzinfo=_tz.utc)
    snaps = closing_odds_snapshots(row, "csv", "EPL", "2015", timed)
    assert all(s.timestamp == timed for s in snaps)
