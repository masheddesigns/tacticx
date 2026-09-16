"""Phase-1.7 tests: stats schema, xG, events, lineups, players, provenance,
temporal quality, stat conflicts, dataset cache, season ranges, prune.

No live network: all HTTP is mocked via httpx.MockTransport or stub fetchers.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.config import get_settings
from app.db.models.core import Lineup, Match, MatchEvent, MatchStatistic, Player, Team
from app.db.models.provenance import (
    PlayerProviderMapping,
    RawDataRecord,
    SourceConflict,
)
from app.services.conflicts import check_stat_observation
from app.services.identity.players import PlayerIdentityResolver
from app.services.quality import (
    assess_temporal_quality,
    validate_minute,
    validate_xg,
)
from app.services.sources.historical.csv_source import (
    canonical_row,
    closing_odds_snapshots,
    match_stats_from_row,
)
from app.services.sources.normalized import (
    NormalizedEvent,
    NormalizedLineup,
    NormalizedMatchStatistics,
    Provenance,
)
from app.services.sources.pipeline import Pipeline
from app.services.sources.stats_schema import normalize_stat_name

FIXTURES = "tests/fixtures"


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# ---------------------------------------------------------------- stat schema

def test_normalize_stat_name():
    assert normalize_stat_name("HS") == "shots_total"
    assert normalize_stat_name("HST") == "shots_on_target"
    assert normalize_stat_name("Shots on Goal") == "shots_on_target"
    assert normalize_stat_name("Ball Possession") == "possession"
    assert normalize_stat_name("Corner Kicks") == "corners"
    assert normalize_stat_name("Expected Goals") == "expected_goals"
    assert normalize_stat_name("xg") == "expected_goals"
    assert normalize_stat_name("Some Weird Metric") == "some_weird_metric"  # passthrough
    assert normalize_stat_name("") == ""


def test_fdco_stats_extraction():
    raw = {"Div": "E0", "Date": "21/09/2024", "HomeTeam": "West Ham", "AwayTeam": "Chelsea",
           "FTHG": "0", "FTAG": "3", "HTHG": "0", "HTAG": "0",
           "HS": "14", "AS": "10", "HST": "5", "AST": "2",
           "HC": "7", "AC": "8", "HF": "12", "AF": "10",
           "HY": "2", "AY": "3", "HR": "0", "AR": "0"}
    row = canonical_row(raw)
    home = row["stats"]["home"]
    assert home[("shots_total", "full")] == "14"
    assert home[("shots_on_target", "full")] == "5"
    assert home[("corners", "full")] == "7"
    assert home[("fouls", "full")] == "12"
    assert home[("yellow_cards", "full")] == "2"
    assert home[("red_cards", "full")] == "0"
    assert home[("goals", "1h")] == "0"
    assert row["stats"]["away"][("shots_total", "full")] == "10"
    stats = match_stats_from_row(row, "csv", "p_v1")
    assert len(stats) == 14  # 6 full-time + HT goals, x2 sides
    by_key = {(s.team, s.stat_name, s.period): s.stat_value for s in stats}
    assert by_key[("home", "shots_total", "full")] == "14"
    assert by_key[("away", "goals", "1h")] == "0"
    assert all(s.provenance.parser_version == "p_v1" for s in stats)


def test_fdco_stats_missing_cells_skipped():
    raw = {"Div": "E0", "Date": "21/09/2024", "HomeTeam": "A", "AwayTeam": "B",
           "FTHG": "1", "FTAG": "0", "HS": "", "HST": "3"}
    row = canonical_row(raw)
    stats = match_stats_from_row(row, "csv", "p_v1")
    names = {(s.team, s.stat_name) for s in stats}
    assert ("home", "shots_total") not in names  # empty cell -> absent, never zero-filled
    assert ("home", "shots_on_target") in names
    # Nothing derived: off-target is NOT computed.
    assert not any("off_target" in s.stat_name for s in stats)


def test_closing_and_asian_handicap():
    raw = {"Div": "E0", "Date": "21/09/2024", "HomeTeam": "A", "AwayTeam": "B",
           "FTHG": "1", "FTAG": "0",
           "B365H": "2.00", "B365D": "3.40", "B365A": "3.80",
           "B365CH": "1.90", "B365CD": "3.60", "B365CA": "4.00",
           "AHh": "-0.5", "B365AHH": "1.95", "B365AHA": "1.90"}
    row = {"home": "A", "away": "B", "raw": raw}
    snaps = closing_odds_snapshots(row, "csv", "EPL", "2024", None)
    by_market = {(s.source_market_id, s.market) for s in snaps}
    assert ("B365:h2h", "h2h") in by_market
    assert ("B365C:h2h", "h2h") in by_market  # closing kept separate
    ah = [s for s in snaps if s.market == "asian_handicap"]
    assert len(ah) == 1 and ah[0].selections[0].point == -0.5
    assert all(s.provenance.temporal_quality == "estimated" for s in snaps)


# ---------------------------------------------------------------- xG quality

def test_validate_xg():
    assert validate_xg(1.72).valid is True
    assert validate_xg("0.84").valid is True
    assert validate_xg(0.0).valid is True
    assert validate_xg(-0.1).valid is False
    assert validate_xg("n/a").valid is False
    assert validate_xg(float("nan")).valid is False
    assert validate_xg(99.0).valid is False


def test_validate_minute():
    assert validate_minute(45, 2).valid is True
    assert validate_minute(90, None).valid is True
    assert validate_minute(200, None).valid is False
    assert validate_minute(45, 99).valid is False


def test_stat_conflict_tolerance(db):
    from app.services.sources.pipeline import Pipeline as _P

    pipe = _P(db, "statsbomb")
    league = pipe.ensure_league("EPL", season="2015")
    home = pipe.resolve_team("Leicester")
    away = pipe.resolve_team("Chelsea")
    mid, _ = pipe.matches.ensure("statsbomb", "SB-1", league.id, home, away,
                                 _utc(2016, 5, 1))
    pipe.ingest_statistics(mid, [NormalizedMatchStatistics(
        team="home", stat_name="expected_goals", stat_value="1.720", period="full",
        provenance=Provenance(source="statsbomb"))], parser_version="t")
    # Same value, other source -> agreement, no conflict.
    assert check_stat_observation(db, mid, "home", "expected_goals", 1.72, "csv") is None
    assert db.query(SourceConflict).count() == 0
    # Within tolerance -> no conflict.
    assert check_stat_observation(db, mid, "home", "expected_goals", 1.723, "csv") is None
    assert db.query(SourceConflict).count() == 0
    # Genuine divergence -> conflict preserving both observations.
    conflict = check_stat_observation(db, mid, "home", "expected_goals", 1.68, "csv")
    assert conflict is not None and conflict.status == "open"
    assert conflict.values["statsbomb"] == 1.72
    assert conflict.values["csv"] == 1.68
    # Canonical untouched.
    row = db.query(MatchStatistic).filter_by(match_id=mid, stat_name="expected_goals").one()
    assert row.stat_value == "1.720"


def test_pipeline_stat_cross_source_keeps_canonical(db):
    pipe = Pipeline(db, "statsbomb")
    league = pipe.ensure_league("EPL", season="2015")
    home = pipe.resolve_team("Leicester")
    away = pipe.resolve_team("Chelsea")
    mid, _ = pipe.matches.ensure("statsbomb", "SB-2", league.id, home, away, _utc(2016, 5, 2))
    pipe.ingest_statistics(mid, [NormalizedMatchStatistics(
        team="home", stat_name="shots_total", stat_value="14", period="full",
        provenance=Provenance(source="statsbomb"))], parser_version="t")
    pipe2 = Pipeline(db, "csv")
    pipe2.ingest_statistics(mid, [NormalizedMatchStatistics(
        team="home", stat_name="shots_total", stat_value="19", period="full",
        provenance=Provenance(source="csv"))], parser_version="t")
    row = db.query(MatchStatistic).filter_by(match_id=mid, stat_name="shots_total").one()
    assert row.stat_value == "14"  # first wins; csv observation preserved in conflict
    assert db.query(SourceConflict).filter_by(entity_type="statistic").count() == 1


# ---------------------------------------------------------------- events

SB_MATCH = {
    "match_id": 3825739, "match_date": "2016-01-17", "kick_off": "17:00:00.000",
    "match_status": "available", "home_score": 5, "away_score": 1,
    "home_team": {"home_team_id": 220, "home_team_name": "Real Madrid"},
    "away_team": {"away_team_id": 1041, "away_team_name": "Sporting Gijón"},
}

SB_EVENTS = [
    {"id": "e1", "minute": 26, "second": 11, "type": {"name": "Shot"},
     "team": {"id": 220, "name": "Real Madrid"}, "player": {"id": 1, "name": "Cristiano Ronaldo"},
     "shot": {"statsbomb_xg": 0.31, "outcome": {"name": "Goal"}, "type": {"name": "Open Play"}}},
    {"id": "e2", "minute": 45, "second": 1, "type": {"name": "Shot"},
     "team": {"id": 1041, "name": "Sporting Gijón"}, "player": {"id": 2, "name": "Striker"},
     "shot": {"statsbomb_xg": 0.76, "outcome": {"name": "Goal"}, "type": {"name": "Penalty"}}},
    {"id": "e3", "minute": 60, "second": 0, "type": {"name": "Shot"},
     "team": {"id": 220, "name": "Real Madrid"}, "player": {"id": 3, "name": "Bale"},
     "shot": {"statsbomb_xg": 0.05, "outcome": {"name": "Off T"}, "type": {"name": "Penalty"}}},
    {"id": "e4", "minute": 70, "second": 0, "type": {"name": "Own Goal For"},
     "team": {"id": 1041, "name": "Sporting Gijón"}, "player": {"id": 4, "name": "Defender"}},
    {"id": "e5", "minute": 20, "second": 0, "type": {"name": "Foul Committed"},
     "team": {"id": 220, "name": "Real Madrid"}, "player": {"id": 5, "name": "Ramos"},
     "foul_committed": {"card": {"name": "Yellow Card"}}},
    {"id": "e6", "minute": 80, "second": 0, "type": {"name": "Bad Behaviour"},
     "team": {"id": 1041, "name": "Sporting Gijón"}, "player": {"id": 6, "name": "Hothead"},
     "bad_behaviour": {"card": {"name": "Second Yellow"}}},
    {"id": "e7", "minute": 65, "second": 0, "type": {"name": "Substitution"},
     "team": {"id": 220, "name": "Real Madrid"}, "player": {"id": 7, "name": "Off Guy"},
     "substitution": {"replacement": {"id": 8, "name": "On Guy"}}},
    {"id": "e8", "minute": 10, "second": 0, "type": {"name": "Foul Committed"},
     "team": {"id": 220, "name": "Real Madrid"}, "player": {"id": 9, "name": "Clean"}},
    {"id": "e9", "minute": 5, "second": 0, "type": {"name": "Pass"},
     "team": {"id": 220, "name": "Real Madrid"}, "player": {"id": 10, "name": "Passer"}},
    {"id": "e10", "minute": 30, "second": 0, "type": {"name": "Shot"},
     "team": {"id": 999, "name": "Unknown FC"}, "player": {"id": 11, "name": "Ghost"},
     "shot": {"statsbomb_xg": 0.5, "outcome": {"name": "Goal"}, "type": {"name": "Open Play"}}},
    "not-a-dict",
]


def _sb_source():
    from app.services.sources.football.statsbomb import StatsBombSource

    src = StatsBombSource()
    src._current_events = list(SB_EVENTS)
    return src


def test_statsbomb_event_mapping():
    src = _sb_source()
    events, stats = src.convert_events(SB_MATCH)
    by_minute = {e.minute: e.event_type for e in events}
    assert by_minute[26] == "goal"
    assert by_minute[45] == "penalty"  # scored penalty keeps its own type
    assert by_minute[60] == "missed_penalty"
    assert by_minute[70] == "own_goal"
    assert by_minute[20] == "yellow_card"
    assert by_minute[65] == "substitution"
    kinds = {e.event_type for e in events}
    assert "second_yellow" in kinds
    assert len(events) == 7  # card-less foul, pass, unknown team, junk skipped
    assert all(e.provider_player_id for e in events)
    xg = {(s.team, s.stat_name): s.stat_value for s in stats}
    assert xg[("home", "expected_goals")] == "0.360"
    assert xg[("away", "expected_goals")] == "0.760"
    assert xg[("home", "shots_total")] == "2"      # 2 home shots (ghost team excluded)
    assert xg[("away", "shots_total")] == "1"
    assert xg[("away", "shots_on_target")] == "1"  # Saved counts; woodwork would not


def test_statsbomb_lineup_mapping():
    from app.services.sources.football.statsbomb import StatsBombSource

    src = StatsBombSource()
    lineups = [
        {"team_id": 220, "team_name": "Real Madrid",
         "lineup": [{"player_id": 1, "player_name": "Cristiano Ronaldo"},
                    {"player_id": 7, "player_name": "Off Guy"},
                    {"player_id": 8, "player_name": "On Guy"}]},
        {"team_id": 1041, "team_name": "Sporting Gijón",
         "lineup": [{"player_id": 2, "player_name": "Striker"}]},
    ]
    starting = [{"id": "s1", "type": {"name": "Starting XI"},
                 "team": {"id": 220},
                 "tactics": {"formation": 433, "lineup": [
                     {"player": {"id": 1}, "position": {"name": "Center Forward"}},
                     {"player": {"id": 7}, "position": {"name": "Left Midfield"}}]}}]
    out = src.convert_lineups(SB_MATCH, lineups, starting)
    by_name = {lu.player_name: lu for lu in out}
    assert by_name["Cristiano Ronaldo"].is_starting == 1
    assert by_name["Cristiano Ronaldo"].position == "Center Forward"
    assert by_name["Cristiano Ronaldo"].formation == "433"
    assert by_name["Cristiano Ronaldo"].provider_player_id == "1"
    assert by_name["On Guy"].is_starting == 0  # bench/sub, not distinguished
    assert by_name["Striker"].team == "away"
    assert len(out) == 4


def test_pipeline_events_and_lineups_detail(db):
    pipe = Pipeline(db, "statsbomb")
    league = pipe.ensure_league("LA_LIGA", season="2015")
    home = pipe.resolve_team("Real Madrid")
    away = pipe.resolve_team("Sporting Gijón")
    mid, _ = pipe.matches.ensure("statsbomb", "3825739", league.id, home, away,
                                 _utc(2016, 1, 17))
    src = _sb_source()
    events, _ = src.convert_events(SB_MATCH)
    pipe.ingest_events(mid, events, parser_version="t")
    assert db.query(MatchEvent).filter_by(match_id=mid).count() == 7
    row = db.query(MatchEvent).filter_by(match_id=mid, event_type="goal").first()
    assert row is not None and row.source == "statsbomb"
    bad = [NormalizedEvent(minute=999, event_type="goal", team="home", player_name="X",
                           provenance=Provenance(source="statsbomb"))]
    pipe.ingest_events(mid, bad, parser_version="t")
    assert db.query(MatchEvent).filter_by(match_id=mid).count() == 7  # quarantined, not stored


def test_pipeline_lineup_players_resolved(db):
    pipe = Pipeline(db, "statsbomb")
    league = pipe.ensure_league("LA_LIGA", season="2015")
    home = pipe.resolve_team("Real Madrid")
    away = pipe.resolve_team("Sporting Gijón")
    mid, _ = pipe.matches.ensure("statsbomb", "3825739", league.id, home, away,
                                 _utc(2016, 1, 17))

    pipe.ingest_lineups(mid, [NormalizedLineup(
        team="home", player_name="Cristiano Ronaldo", position="Center Forward",
        is_starting=1, formation="433", is_captain=1, provider_player_id="1",
        provenance=Provenance(source="statsbomb"))],
        parser_version="t")
    row = db.query(Lineup).filter_by(match_id=mid).one()
    assert row.formation == "433" and row.is_captain == 1 and row.player_provider_id == "1"
    player = db.query(Player).filter_by(name="Cristiano Ronaldo").one()
    assert player.team_id == home  # scoped to the right team

    assert db.query(PlayerProviderMapping).filter_by(source="statsbomb").count() == 1


# ---------------------------------------------------------------- players

def test_player_exact_mapping(db):
    player = Player(name="Cristiano Ronaldo", provider="x", provider_player_id="1")
    db.add(player)
    db.commit()
    from app.db.models.provenance import PlayerProviderMapping as _M

    db.add(_M(player_id=player.id, source="statsbomb", provider_player_id="9489",
              provider_player_name="Cristiano Ronaldo", normalized_name="cristiano ronaldo"))
    db.commit()
    pid, method = PlayerIdentityResolver(db).resolve("statsbomb", "9489", "CR7")
    assert (pid, method) == (player.id, "mapping")


def test_player_legacy_and_created(db):
    db.add(Player(name="Bale", provider="statsbomb", provider_player_id="777"))
    db.commit()
    pid, method = PlayerIdentityResolver(db).resolve("statsbomb", "777", "Gareth Bale")
    assert method == "legacy_provider_id"
    created, method2 = PlayerIdentityResolver(db).ensure("statsbomb", "778", "Brand Newbie")
    assert method2 == "created"
    assert db.query(Player).filter_by(name="Brand Newbie").count() == 1


def test_player_ambiguous_unresolved(db):
    h = Team(name="Real Madrid", provider="x", provider_team_id="1")
    db.add(h)
    db.flush()
    db.add_all([Player(name="Silva", team_id=h.id, provider="a", provider_player_id="1"),
                Player(name="Silva", team_id=None, provider="b", provider_player_id="2")])
    db.commit()
    # Scoped to the team -> resolves; global -> ambiguous.
    pid, _ = PlayerIdentityResolver(db).resolve("statsbomb", "", "Silva", team_id=h.id)
    assert pid is not None
    pid2, _ = PlayerIdentityResolver(db).resolve("statsbomb", "", "Silva")
    assert pid2 is None


def test_player_alias(db):
    db.add(Player(name="David Beckham", provider="x", provider_player_id="1"))
    db.commit()
    pid, method = PlayerIdentityResolver(db, aliases={"Becks": "David Beckham"}).resolve(
        "statsbomb", "", "Becks")
    assert method == "alias" and pid is not None


# ---------------------------------------------------------------- provenance

def test_raw_temporal_and_url(db):
    from app.services.sources.pipeline import track_raw

    track_raw(db, "csv", "match", "R1", "payload", "p_v1", "processed",
              temporal_quality="estimated", source_url="data/x.csv")
    row = db.query(RawDataRecord).filter_by(source_record_id="R1").one()
    assert row.temporal_quality == "estimated"
    assert row.source_url == "data/x.csv"
    track_raw(db, "csv", "match", "R1", "payload", "p_v1", "processed",
              temporal_quality="bogus")
    row = db.query(RawDataRecord).filter_by(source_record_id="R1").one()
    assert row.temporal_quality == "unknown"  # invalid values fall back


def test_assess_temporal_quality():
    now = _utc(2024, 9, 1)
    kickoff = _utc(2024, 8, 1)
    assert assess_temporal_quality() == "unknown"
    assert assess_temporal_quality(event_time=kickoff) == "estimated"
    assert assess_temporal_quality(event_time=kickoff, collected_at=_utc(2024, 8, 2)) == "estimated"
    assert assess_temporal_quality(event_time=kickoff, published_at=_utc(2024, 8, 1),
                                   collected_at=_utc(2024, 8, 2)) == "verified"
    assert assess_temporal_quality(event_time=_utc(2024, 9, 5),
                                   collected_at=_utc(2024, 9, 1)) == "unknown"  # future event
    assert assess_temporal_quality(collected_at=_utc(2025, 1, 1), now=now) == "unknown"  # clock skew


# ---------------------------------------------------------------- registry/sources

def test_statsbomb_registered():
    from app.services.sources.registry import get_football_registry, get_historical_registry

    assert "statsbomb" in get_football_registry().available()
    assert "statsbomb" in get_historical_registry().available()


def test_statsbomb_helpers():
    from app.services.sources.football.football_data_co_uk import season_segment
    from app.services.sources.football.statsbomb import sb_season_name

    assert sb_season_name("2023") == "2023/2024"
    assert season_segment("2024") == "2425"
    with pytest.raises(ValueError):
        sb_season_name("not-a-season")


def test_collect_attempt_fallback():
    from scripts.collect_lib import attempt

    calls = []

    class Bad:
        source_name = "bad"

    class Good:
        source_name = "good"

    def fail(source):
        calls.append(source.source_name)
        raise RuntimeError("boom")

    def ok(source):
        calls.append(source.source_name)
        return [1, 2]

    name, result = attempt([Bad(), Good()], lambda s: fail(s) if s.source_name == "bad" else ok(s))
    assert (name, result) == ("good", [1, 2])
    with pytest.raises(RuntimeError, match="all sources failed"):
        attempt([Bad()], fail)


# ---------------------------------------------------------------- scraping cache

def test_dataset_cache_roundtrip(tmp_path, monkeypatch):

    from app.services.scraping import datasets as _d

    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))
    assert _d.read_cached("s", "f.csv") is None
    _d.write_cached("s", "f.csv", "a,b\n1,2\n")
    assert _d.read_cached("s", "f.csv") == "a,b\n1,2\n"

    calls = {"n": 0}

    class Fetcher:
        async def fetch_text(self, url):
            calls["n"] += 1
            return "fresh"

    text, cached = asyncio.run(_d.fetch_cached(Fetcher(), "http://x/y.csv", "s", "g.csv"))
    assert (text, cached) == ("fresh", False)
    text, cached = asyncio.run(_d.fetch_cached(Fetcher(), "http://x/y.csv", "s", "g.csv"))
    assert (text, cached) == ("fresh", True) and calls["n"] == 1
    text, cached = asyncio.run(_d.fetch_cached(Fetcher(), "http://x/y.csv", "s", "g.csv",
                                               refresh=True))
    assert cached is False and calls["n"] == 2


# ---------------------------------------------------------------- season ranges

def test_season_range_parsing():
    from scripts.import_historical import _season_range

    assert _season_range("2024", "", "") == ["2024"]
    assert _season_range("", "2020", "2022") == ["2020", "2021", "2022"]
    assert _season_range("", "", "2022") == ["2022"]
    with pytest.raises(ValueError):
        _season_range("", "2022", "2020")
    with pytest.raises(ValueError):
        _season_range("", "", "")


# ---------------------------------------------------------------- api extensions

def test_api_events_extra_assist_formation():

    from app.services.football.api_football import ApiFootballProvider

    payload = {"response": [{
        "time": {"elapsed": 45, "extra": 2}, "type": "Goal", "detail": "Normal Goal",
        "team": {"id": 1, "name": "Arsenal"}, "player": {"id": 10, "name": "Saka"},
        "assist": {"id": 11, "name": "Odegaard"}}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = ApiFootballProvider(api_key="x", client=_mock_client(handler))
    events = asyncio.run(provider.get_match_events("1"))
    assert events[0].minute_added == 2
    assert events[0].assist_player == "Odegaard"
    assert events[0].provider_player_id == "10"

    lineup_payload = {"response": [{
        "formation": "4-3-3",
        "startXI": [{"player": {"id": 1, "name": "Raya", "pos": "G"}}],
        "substitutes": []}]}
    provider2 = ApiFootballProvider(
        api_key="x", client=_mock_client(
            lambda request: httpx.Response(200, json=lineup_payload)))
    lineup = asyncio.run(provider2.get_lineups("1"))
    assert lineup[0].formation == "4-3-3"
    assert lineup[0].provider_player_id == "1"


# ---------------------------------------------------------------- cross-source

def test_cross_source_same_fixture(db):
    """fdco row + statsbomb observation resolve to ONE canonical match."""
    from app.services.identity.matches import MatchResolver
    from app.services.sources.historical.csv_source import CsvFileSource

    CsvFileSource(file_path=f"{FIXTURES}/epl_sample.csv", db=db).import_history("EPL", "2024")
    assert db.query(Match).count() == 3
    existing = db.query(Match).filter_by(provider="csv").first()
    assert existing is not None
    # Same canonical tuple from statsbomb (different native id) -> same row.
    same = MatchResolver(db).resolve(
        "statsbomb", "3825739", existing.league_id, existing.home_team_id,
        existing.away_team_id, existing.kickoff_at)
    assert same == existing.id
    assert db.query(Match).count() == 3
    # ...while a genuinely different kickoff creates a new canonical row.
    other, created = MatchResolver(db).ensure(
        "statsbomb", "3825740", existing.league_id, existing.home_team_id,
        existing.away_team_id, _utc(2024, 9, 22, 15, 0))
    assert created is True and other != existing.id


def test_prune_raw_dry_run(db, monkeypatch, capsys):
    import scripts.prune_raw as _prune
    from app.db.models.provenance import RawDataRecord as _Raw

    old = _Raw(source="csv", entity_type="match", source_record_id="OLD",
               retrieved_at=_utc(2020, 1, 1), payload_hash="x", parser_version="v",
               processing_status="processed")
    new = _Raw(source="csv", entity_type="match", source_record_id="NEW",
               retrieved_at=_utc(2026, 9, 1), payload_hash="y", parser_version="v",
               processing_status="processed")
    db.add_all([old, new])
    db.commit()
    # Point the CLI at the test database.
    monkeypatch.setattr(_prune, "get_session_local", lambda: (lambda: db))
    monkeypatch.setattr(_prune, "get_engine", lambda: None)
    monkeypatch.setattr(_prune, "Base", type("B", (), {"metadata": type(
        "M", (), {"create_all": staticmethod(lambda *a, **k: None)})()}))
    monkeypatch.setattr("sys.argv", ["prune_raw.py", "--dry-run", "--days", "90"])
    assert _prune.main() == 0
    out = capsys.readouterr().out
    assert '"eligible": 1' in out and '"deleted": 0' in out
    assert db.query(_Raw).count() == 2  # dry-run deletes nothing
    monkeypatch.setattr("sys.argv", ["prune_raw.py", "--apply", "--days", "90"])
    assert _prune.main() == 0
    assert db.query(_Raw).count() == 1


# ---------------------------------------------------------------- order-independent aliases

def test_alias_order_independent(db):
    from app.services.identity.teams import TeamIdentityResolver

    aliases = {"Dortmund": "Borussia Dortmund"}
    # Variant stored first, canonical arrives later -> still unifies.
    r1 = TeamIdentityResolver(db, aliases=aliases)
    first, _ = r1.ensure("csv", "", "Dortmund")
    r2 = TeamIdentityResolver(db, aliases=aliases)
    team_id, method = r2.resolve("statsbomb", " SG1 ", "Borussia Dortmund")
    assert team_id == first
    # And the reverse order works too.
    assert TeamIdentityResolver(db, aliases=aliases).resolve("x", "", "Dortmund")[0] == first
    assert db.query(Team).filter(Team.name.in_(["Dortmund", "Borussia Dortmund"])).count() == 1


def test_default_aliases_cover_known_variants():
    aliases = get_settings().team_aliases
    for variant, canonical in {
        "Man United": "Manchester United",
        "Ein Frankfurt": "Eintracht Frankfurt",
        "M'gladbach": "Borussia Mönchengladbach",
        "Ath Madrid": "Atlético Madrid",
        "Celta": "Celta Vigo",
        "Sp Gijon": "Sporting Gijón",
        "Espanol": "Espanyol",
        "Levante": "Levante UD",
    }.items():
        assert aliases.get(variant) == canonical


# ---------------------------------------------------------------- fdco detail path

FDCO_ROW = ("E0,21/09/2024,15:00,Arsenal,Chelsea,2,0,H,1,0,H,"
            "14,10,5,2,7,8,12,10,2,3,0,0,1.80,3.60,4.50\n")
FDCO_CSV = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,"
    "HS,AS,HST,AST,HC,AC,HF,AF,HY,AY,HR,AR,B365H,B365D,B365A\n"
    + FDCO_ROW * 60  # realistic season-file size (cache validator needs bulk)
)


def _fdco_source(csv_text, tmp_path, monkeypatch):
    from app.services.sources.football.football_data_co_uk import FootballDataCoUkSource

    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))

    class StubFetcher:
        def __init__(self):
            self.calls = 0

        async def fetch_text(self, url):
            self.calls += 1
            return csv_text

    src = FootballDataCoUkSource()
    stub = StubFetcher()
    src.fetcher = stub
    return src, stub


def test_fdco_match_statistics_via_sid(tmp_path, monkeypatch):

    src, stub = _fdco_source(FDCO_CSV, tmp_path, monkeypatch)
    stats = asyncio.run(src.get_match_statistics("E0|Arsenal|Chelsea|2024-09-21"))
    by_key = {(s.team, s.stat_name, s.period): s.stat_value for s in stats}
    assert by_key[("home", "shots_total", "full")] == "14"
    assert by_key[("away", "shots_on_target", "full")] == "2"
    assert by_key[("home", "goals", "1h")] == "1"
    assert by_key[("away", "yellow_cards", "full")] == "3"
    assert stub.calls == 1  # season file fetched once (then cached)
    stats2 = asyncio.run(src.get_match_statistics("E0|Arsenal|Chelsea|2024-09-21"))
    assert len(stats2) == len(stats) and stub.calls == 1
    assert asyncio.run(src.get_match_statistics("bogus")) == []
    assert asyncio.run(src.get_match_statistics("E0|Nope|Nothing|2024-09-21")) == []


def test_csv_match_statistics_via_row_sid(db):

    from app.services.sources.historical.csv_source import CsvFileSource

    src = CsvFileSource(file_path=f"{FIXTURES}/epl_sample.csv", db=db)
    stats = asyncio.run(src.get_match_statistics("row:0"))
    by_key = {(s.team, s.stat_name) for s in stats}
    assert ("home", "goals") in by_key  # HT goals present in fixture
    assert asyncio.run(src.get_match_statistics("row:99")) == []
    assert asyncio.run(src.get_match_statistics("junk")) == []


# ---------------------------------------------------------------- statsbomb import (mocked)

SB_MATCHES = [
    {"match_id": 1, "match_date": "2016-01-17", "kick_off": "17:00:00.000",
     "match_status": "available", "home_score": 5, "away_score": 1,
     "home_team": {"home_team_id": 220, "home_team_name": "Real Madrid"},
     "away_team": {"away_team_id": 1041, "away_team_name": "Sporting Gijón"}},
    {"match_id": 2, "match_date": "2016-01-18", "kick_off": "20:00:00.000",
     "match_status": "available", "home_score": 0, "away_score": 0,
     "home_team": {"home_team_id": 221, "home_team_name": "Levante UD"},
     "away_team": {"away_team_id": 322, "away_team_name": "Eibar"}},
]

SB_LINEUPS = [
    {"team_id": 220, "team_name": "Real Madrid",
     "lineup": [{"player_id": 1, "player_name": "Cristiano Ronaldo"},
                {"player_id": 7, "player_name": "Off Guy"}]},
    {"team_id": 1041, "team_name": "Sporting Gijón",
     "lineup": [{"player_id": 2, "player_name": "Striker"}]},
]

SB_COMPETITIONS = [
    {"competition_id": 11, "season_id": 27, "competition_name": "La Liga",
     "season_name": "2015/2016"},
]


def _sb_import_source(tmp_path, monkeypatch):
    import json as _json

    from app.services.sources.football.statsbomb import StatsBombSource

    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))
    payloads = {
        "competitions.json": _json.dumps(SB_COMPETITIONS),
        "matches/11/27.json": _json.dumps(SB_MATCHES),
        "lineups/1.json": _json.dumps(SB_LINEUPS),
        "events/1.json": _json.dumps(SB_EVENTS),
        "lineups/2.json": _json.dumps([]),
        "events/2.json": _json.dumps([]),
    }

    class StubFetcher:
        def __init__(self):
            self.calls = 0

        async def fetch_text(self, url):
            self.calls += 1
            for key, text in payloads.items():
                if url.endswith(key):
                    return text
            raise AssertionError(f"unexpected url {url}")

    src = StatsBombSource()
    stub = StubFetcher()
    src.fetcher = stub
    return src, stub


def test_statsbomb_import_mocked(db, tmp_path, monkeypatch):
    src, stub = _sb_import_source(tmp_path, monkeypatch)
    src.db = db
    report = src.import_history("LA_LIGA", "2015", max_detail_matches=1)
    assert report["records_read"] == 2 and report["valid"] == 2
    assert db.query(Match).count() == 2
    assert report["detail_matches"] == 1
    assert db.query(MatchEvent).count() == 7
    assert db.query(Lineup).count() == 3
    xg = {r.team: r.stat_value for r in db.query(MatchStatistic)
          .filter(MatchStatistic.stat_name == "expected_goals").all()}
    assert xg == {"home": "0.360", "away": "0.760"}
    # Resumable: second run adds nothing new.
    report2 = src.import_history("LA_LIGA", "2015", max_detail_matches=1)
    assert report2["inserted"] == 0
    # Provenance carries parser version + estimated quality.
    raws = db.query(RawDataRecord).filter_by(source="statsbomb").all()
    assert raws and all(r.parser_version == "statsbomb_parser_v1" for r in raws)
    assert {r.temporal_quality for r in raws} == {"estimated"}
    assert stub.calls > 0


def test_statsbomb_unknown_league():

    from app.services.sources.football.statsbomb import StatsBombSource

    src = StatsBombSource()
    with pytest.raises(ValueError, match="no mapping"):
        asyncio.run(src.fetch_season_matches("NOPE", "2024"))
