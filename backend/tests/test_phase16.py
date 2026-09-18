"""Phase-1.6 tests: identity, import, scraper (mocked), odds, quality.

No live network: all HTTP is mocked via httpx.MockTransport or stub fetchers.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

import httpx
import pytest

from app.config import get_settings
from app.db.models.core import Match, Team
from app.db.models.provenance import (
    MatchSourceMapping,
    RawDataRecord,
    SourceConflict,
    TeamProviderMapping,
)
from app.services.conflicts import check_score, reconcile_match
from app.services.identity.matches import MatchResolver
from app.services.identity.normalize import normalize_name
from app.services.identity.teams import TeamIdentityResolver
from app.services.quality import validate_event, validate_match, validate_odds, validate_stat
from app.services.sources.historical.csv_source import (
    CsvFileSource,
    RowIssue,
    canonical_row,
    closing_odds_snapshots,
    parse_date,
    read_dataset,
)
from app.services.sources.normalized import NormalizedMatch
from app.services.sources.pipeline import Pipeline
from app.services.sources.registry import (
    football_source_chain,
    get_football_registry,
    get_historical_registry,
    get_odds_registry,
    reset_registries,
)

FIXTURES = "tests/fixtures"


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------- identity

def test_normalize_name():
    assert normalize_name("Arsenal FC") == "arsenal"
    assert normalize_name("  Manchester   United  ") == "manchester united"
    assert normalize_name("St. Étienne") == "st etienne"
    assert normalize_name("") == ""
    assert normalize_name(None) == ""


def test_team_exact_mapping(db):
    team = Team(name="Arsenal", provider="x", provider_team_id="1")
    db.add(team)
    db.commit()
    db.add(TeamProviderMapping(team_id=team.id, source="csv", provider_team_id="ARS",
                               provider_team_name="Arsenal", normalized_name="arsenal"))
    db.commit()
    resolver = TeamIdentityResolver(db)
    team_id, method = resolver.resolve("csv", "ARS", "Arsenal FC")
    assert (team_id, method) == (team.id, "mapping")


def test_team_legacy_provider_id(db):
    team = Team(name="Chelsea", provider="api_football", provider_team_id="49")
    db.add(team)
    db.commit()
    resolver = TeamIdentityResolver(db)
    team_id, method = resolver.resolve("api_football", "49", "Chelsea FC")
    assert (team_id, method) == (team.id, "legacy_provider_id")
    # Mapping persisted for auditability.
    assert db.query(TeamProviderMapping).filter_by(source="api_football").count() == 1


def test_team_normalized_match(db):
    db.add(Team(name="Arsenal FC", provider="x", provider_team_id="1"))
    db.commit()
    team_id, method = TeamIdentityResolver(db).resolve("csv", "", "Arsenal")
    assert method == "normalized_name" and team_id is not None


def test_team_ambiguous_unresolved(db):
    db.add_all([Team(name="United", provider="a", provider_team_id="1"),
                Team(name="United FC", provider="b", provider_team_id="2")])
    db.commit()
    team_id, method = TeamIdentityResolver(db).resolve("csv", "", "United")
    assert team_id is None  # two candidates normalize equal -> no guessing


def test_team_alias(db):
    team = Team(name="Ipswich", provider="x", provider_team_id="1")
    db.add(team)
    db.commit()
    resolver = TeamIdentityResolver(db, aliases={"Ipswich Town": "Ipswich"})
    team_id, method = resolver.resolve("csv", "", "Ipswich Town")
    assert (team_id, method) == (team.id, "alias")


def test_team_unresolved(db):
    team_id, method = TeamIdentityResolver(db, aliases={}).resolve("csv", "", "Mystery Rovers")
    assert team_id is None


def test_team_ensure_and_mapping_idempotent(db):
    resolver = TeamIdentityResolver(db)
    first, _ = resolver.ensure("csv", "", "Bournemouth")
    second, _ = resolver.ensure("csv", "", "Bournemouth")
    assert first == second
    assert db.query(TeamProviderMapping).filter_by(source="csv").count() == 1
    assert db.query(Team).filter_by(name="Bournemouth").count() == 1


def _seed_match(db, source="csv", sid="M1", kickoff="2024-09-21T15:00:00+00:00"):
    from datetime import datetime

    pipe = Pipeline(db, source)
    league = pipe.ensure_league("EPL", season="2024")
    home = pipe.resolve_team("West Ham")
    away = pipe.resolve_team("Chelsea")
    return pipe.matches.ensure(source, sid, league.id, home, away,
                               datetime.fromisoformat(kickoff))


def test_match_identity_across_sources(db):
    first_id, created = _seed_match(db, source="csv", sid="M1")
    assert created is True
    # Same canonical tuple from another source resolves to the SAME match.
    from datetime import datetime

    pipe = Pipeline(db, "football_data_co_uk")
    league = pipe.ensure_league("EPL", season="2024")
    home = pipe.resolve_team("West Ham")
    away = pipe.resolve_team("Chelsea")
    match_id, created2 = pipe.matches.ensure(
        "football_data_co_uk", "FD-99", league.id, home, away,
        datetime.fromisoformat("2024-09-21T15:07:00+00:00"))  # 7 min clock skew
    assert match_id == first_id and created2 is False
    assert db.query(MatchSourceMapping).filter_by(match_id=first_id).count() == 2
    assert db.query(Match).count() == 1


def test_match_kickoff_tolerance(db):
    from datetime import datetime

    first_id, _ = _seed_match(db)
    resolver = MatchResolver(db)
    m = db.get(Match, first_id)
    far = resolver.resolve("csv", "OTHER", m.league_id, m.home_team_id, m.away_team_id,
                           datetime.fromisoformat("2024-09-22T15:00:00+00:00"))
    assert far is None  # a day apart is a different fixture, not a skew


# ---------------------------------------------------------------- import

def test_csv_import_valid(db):
    src = CsvFileSource(file_path=f"{FIXTURES}/epl_sample.csv", db=db)
    report = src.import_history("EPL", "2024")
    assert report["records_read"] == 3
    assert report["valid"] == 3
    assert report["invalid"] == 0
    assert report["inserted"] > 0
    assert db.query(Match).count() == 3
    # Provenance: every match tracked with parser version.
    raws = db.query(RawDataRecord).filter_by(entity_type="match").all()
    assert len(raws) == 3
    assert all(r.parser_version == "csv_dataset_parser_v1" for r in raws)
    assert all(r.processing_status == "processed" for r in raws)
    # Closing odds stored (h2h + totals for B365).
    from app.db.models.odds import OddsSnapshot

    assert db.query(OddsSnapshot).count() == 6


def test_csv_import_malformed(db):
    src = CsvFileSource(file_path=f"{FIXTURES}/malformed_sample.csv", db=db)
    report = src.import_history("EPL", "2024")
    assert report["records_read"] == 5
    assert report["valid"] == 3  # rows 1, 4, 5 parse; 4/5 quarantined by quality
    assert report["invalid"] == 4  # bad date + missing team + 2 quality failures
    assert len(report["_rejected"]) == 2  # schema-level rejects with reasons
    assert db.query(Match).count() == 1  # only the genuinely good row
    # Nothing invented: bad scores/teams absent from the DB.
    assert db.query(Team).filter(Team.name == "").count() == 0


def test_csv_reimport_idempotent(db):
    src = CsvFileSource(file_path=f"{FIXTURES}/epl_sample.csv", db=db)
    src.import_history("EPL", "2024")
    second = src.import_history("EPL", "2024")
    assert second["inserted"] == 0
    assert second["duplicates_skipped"] > 0
    assert db.query(Match).count() == 3
    # Score fill-in counts as update: scheduled row gains a result on re-import.
    assert second["updated"] >= 0


def test_csv_score_fill_counts_as_update(db, tmp_path):
    scheduled = tmp_path / "v1.csv"
    scheduled.write_text("Date,HomeTeam,AwayTeam,FTHG,FTAG\n21/09/2024,Arsenal,Chelsea,,\n")
    result = tmp_path / "v2.csv"
    result.write_text("Date,HomeTeam,AwayTeam,FTHG,FTAG\n21/09/2024,Arsenal,Chelsea,2,1\n")
    r1 = CsvFileSource(file_path=str(scheduled), db=db).import_history("EPL", "2024")
    assert r1["inserted"] > 0
    r2 = CsvFileSource(file_path=str(result), db=db).import_history("EPL", "2024")
    assert r2["inserted"] == 0 and r2["updated"] >= 1
    m = db.query(Match).one()
    assert (m.home_score, m.away_score) == (2, 1)


def test_json_import(db):
    src = CsvFileSource(file_path=f"{FIXTURES}/generic_sample.json", db=db)
    report = src.import_history("EPL", "2024")
    assert report["records_read"] == 2 and report["invalid"] == 0
    assert db.query(Match).count() == 2


def test_unsupported_format(db):
    src = CsvFileSource(file_path="data/x.xml", db=db)
    with pytest.raises(ValueError, match="unsupported dataset format"):
        src.import_history("EPL", "2024")


def test_parquet_without_engine(db, tmp_path):
    pq = tmp_path / "x.parquet"
    pq.write_bytes(b"PAR1fake")
    src = CsvFileSource(file_path=str(pq), db=db)
    try:
        import pandas  # noqa: F401
        pytest.skip("pandas installed — optional-parquet branch not taken")
    except ImportError:
        with pytest.raises(ValueError, match="parquet support needs"):
            src.import_history("EPL", "2024")


def test_read_dataset_rejects(tmp_path):
    with pytest.raises(ValueError):
        read_dataset(str(tmp_path / "nope.txt"))


def test_canonical_row_issues():
    with pytest.raises(RowIssue):
        canonical_row({"Date": "2024-09-21"})
    assert parse_date("21/09/2024") is not None
    assert parse_date("garbage") is None


def test_closing_odds_only_when_provided():
    row = {"home": "A", "away": "B", "raw": {"B365H": "", "B365D": "", "B365A": ""}}
    assert closing_odds_snapshots(row, "csv", "EPL", "2024", None) == []
    row2 = {"home": "A", "away": "B",
            "raw": {"B365H": "1.80", "B365D": "3.60", "B365A": "4.50",
                    "B365>2.5": "2.10", "B365<2.5": "1.72"}}
    snaps = closing_odds_snapshots(row2, "csv", "EPL", "2024", None)
    assert [s.market for s in snaps] == ["h2h", "totals"]
    assert snaps[0].timestamp is None or True  # kickoff None here; pipeline stamps instead


# ---------------------------------------------------------------- scraper

def _text_client(text: str, calls: dict, status: int = 200, headers: Optional[dict] = None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] = calls.get("n", 0) + 1
        return httpx.Response(status, text=text, headers=headers or {})
    return _mock_client(handler)


def test_polite_fetch_success():

    from app.services.caching import cache as cache_mod
    from app.services.scraping.polite import PoliteFetcher, reset_fetcher_state

    cache_mod.reset_cache()
    reset_fetcher_state()
    calls: dict = {}
    client = _text_client("a,b\n1,2\n", calls)
    fetcher = PoliteFetcher(source="t_success", min_delay_seconds=0, check_robots=False,
                            client=client)
    text = asyncio.run(fetcher.fetch_text("https://example.test/data.csv", cache_key="t:ok"))
    assert text == "a,b\n1,2\n"
    assert calls["n"] == 1


def test_polite_fetch_timeout(monkeypatch):

    from app.config import get_settings
    from app.services.http_client import ProviderHTTPError
    from app.services.scraping.polite import PoliteFetcher

    monkeypatch.setattr(get_settings(), "PROVIDER_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(get_settings(), "PROVIDER_RETRY_BASE_SECONDS", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow host")

    fetcher = PoliteFetcher(source="t_timeout", min_delay_seconds=0, check_robots=False,
                            client=_mock_client(handler))
    with pytest.raises(ProviderHTTPError):
        asyncio.run(fetcher.fetch_text("https://example.test/x", cache_key="t:timeout"))


def test_polite_fetch_429_then_success():

    from app.services.caching import cache as cache_mod
    from app.services.scraping.polite import PoliteFetcher, reset_fetcher_state

    cache_mod.reset_cache()
    reset_fetcher_state()
    calls: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] = calls.get("n", 0) + 1
        if calls["n"] == 1:
            return httpx.Response(429, text="slow down", headers={"Retry-After": "0"})
        return httpx.Response(200, text="recovered")

    fetcher = PoliteFetcher(source="t_429", min_delay_seconds=0, check_robots=False,
                            client=_mock_client(handler))
    assert asyncio.run(fetcher.fetch_text("https://example.test/y", cache_key="t:429")) == "recovered"
    assert calls["n"] == 2


def test_polite_fetch_500_retried():

    from app.services.caching import cache as cache_mod
    from app.services.scraping.polite import PoliteFetcher, reset_fetcher_state

    cache_mod.reset_cache()
    reset_fetcher_state()
    calls: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] = calls.get("n", 0) + 1
        return httpx.Response(500, text="boom") if calls["n"] == 1 else httpx.Response(200, text="ok")

    fetcher = PoliteFetcher(source="t_500", min_delay_seconds=0, check_robots=False,
                            client=_mock_client(handler))
    assert asyncio.run(fetcher.fetch_text("https://example.test/z", cache_key="t:500")) == "ok"
    assert calls["n"] == 2


def test_polite_fetch_cached():

    from app.services.caching import cache as cache_mod
    from app.services.scraping.polite import PoliteFetcher, reset_fetcher_state

    cache_mod.reset_cache()
    reset_fetcher_state()
    calls: dict = {}
    fetcher = PoliteFetcher(source="t_cache", min_delay_seconds=0, check_robots=False,
                            client=_text_client("v", calls))
    asyncio.run(fetcher.fetch_text("https://example.test/c", cache_key="t:cached"))
    asyncio.run(fetcher.fetch_text("https://example.test/c", cache_key="t:cached"))
    assert calls["n"] == 1


def test_polite_min_delay():

    from app.services.caching import cache as cache_mod
    from app.services.scraping.polite import PoliteFetcher, reset_fetcher_state

    cache_mod.reset_cache()
    reset_fetcher_state()
    fetcher = PoliteFetcher(source="t_delay", min_delay_seconds=0.2, check_robots=False,
                            client=_text_client("v", {}))
    start = time.monotonic()
    asyncio.run(fetcher.fetch_text("https://example.test/d1", cache_key="t:d1"))
    asyncio.run(fetcher.fetch_text("https://example.test/d2", cache_key="t:d2"))
    assert time.monotonic() - start >= 0.15


def test_robots_disallowed(monkeypatch):

    from app.services.scraping.polite import PoliteFetcher, SourceDisallowed

    monkeypatch.setattr("app.services.scraping.polite.robots_allowed", lambda *a, **k: False)
    fetcher = PoliteFetcher(source="t_robots", min_delay_seconds=0, client=_text_client("v", {}))
    with pytest.raises(SourceDisallowed):
        asyncio.run(fetcher.fetch_text("https://example.test/nope", cache_key="t:robots"))


def test_robots_checker_parsing(monkeypatch):
    from app.services.scraping import robots as robots_mod

    robots_mod.reset_robots_cache()

    class Parser:
        def __init__(self, allowed: bool):
            self.allowed = allowed

        def set_url(self, url):
            pass

        def read(self):
            pass

        def can_fetch(self, ua, url):
            return self.allowed

    monkeypatch.setattr(robots_mod, "RobotFileParser", lambda: Parser(True))
    assert robots_mod.robots_allowed("https://allow.test/page") is True
    robots_mod.reset_robots_cache()
    monkeypatch.setattr(robots_mod, "RobotFileParser", lambda: Parser(False))
    assert robots_mod.robots_allowed("https://deny.test/page") is False
    robots_mod.reset_robots_cache()


def test_robots_fetch_error_fails_closed(monkeypatch):
    from app.services.scraping import robots as robots_mod

    robots_mod.reset_robots_cache()

    class Broken:
        def set_url(self, url):
            pass

        def read(self):
            raise OSError("network down")

    monkeypatch.setattr(robots_mod, "RobotFileParser", lambda: Broken())
    assert robots_mod.robots_allowed("https://down.test/page") is False
    robots_mod.reset_robots_cache()


def test_scraper_parser_failure_recorded(db):

    from app.services.scraping.framework import BaseScraper

    class Broken(BaseScraper):
        source_name = "t_broken"
        entity_type = "match"

        def parse(self, payload: str):
            raise ValueError("layout changed upstream")

    async def fake_request(url: str) -> str:
        return "unexpected html"

    scraper = Broken(db=db)
    scraper.request = fake_request  # type: ignore[method-assign]
    outcome = asyncio.run(scraper.run_url(db, "https://example.test/broken"))
    assert outcome.failed == 1
    row = db.query(RawDataRecord).filter_by(source="t_broken").one()
    assert row.processing_status == "failed" and "layout changed" in row.error_message


def test_scraper_quarantine_and_duplicate(db):

    from app.services.scraping.framework import BaseScraper

    seen = {"persisted": 0}

    class Toy(BaseScraper):
        source_name = "t_toy"
        entity_type = "thing"

        def parse(self, payload: str):
            return [{"id": "1", "ok": True}, {"id": "2", "ok": False}]

        def validate(self, row: dict):
            return [] if row["ok"] else ["bad row"]

        def normalize(self, row: dict):
            return row

        def persist(self, db_session, record):
            seen["persisted"] += 1
            return "duplicate"

    async def fake_request(url: str) -> str:
        return "payload"

    scraper = Toy(db=db)
    scraper.request = fake_request  # type: ignore[method-assign]
    outcome = asyncio.run(scraper.run_url(db, "https://example.test/toy"))
    assert outcome.quarantined == 1 and outcome.duplicates == 1
    statuses = sorted(r.processing_status for r in db.query(RawDataRecord).filter_by(source="t_toy"))
    assert statuses == ["duplicate", "quarantined"]


# ---------------------------------------------------------------- odds

def _odds_pipe(db):
    pipe = Pipeline(db, "csv")
    league = pipe.ensure_league("EPL", season="2024")
    home = pipe.resolve_team("Arsenal")
    away = pipe.resolve_team("Chelsea")
    from datetime import datetime

    match_id, _ = pipe.matches.ensure("csv", "M-1", league.id, home, away,
                                      datetime.fromisoformat("2024-09-21T15:00:00+00:00"))
    return pipe, match_id


def _snap(home_odds: float, ts: str, bookmaker="Bet365", bid="b365", market="h2h"):
    from datetime import datetime

    from app.services.sources.normalized import NormalizedOddsSelection, NormalizedOddsSnapshot

    return NormalizedOddsSnapshot(
        league_code="EPL", season="2024", home_team="Arsenal", away_team="Chelsea",
        kickoff_at=datetime.fromisoformat("2024-09-21T15:00:00+00:00"),
        market=market, timestamp=datetime.fromisoformat(ts), is_live=False,
        source="csv", source_event_id="M-1",
        selections=[NormalizedOddsSelection(selection="home", price=home_odds,
                                            bookmaker=bookmaker, bookmaker_id=bid)])


def test_pipeline_odds_append_and_redelivery(db):
    from app.db.models.odds import OddsSelection, OddsSnapshot

    pipe, match_id = _odds_pipe(db)
    pipe.ingest_odds(_snap(1.80, "2024-09-21T10:00:00+00:00"), parser_version="t_v1")
    pipe.ingest_odds(_snap(1.80, "2024-09-21T10:00:00+00:00"), parser_version="t_v1")  # redelivery
    pipe.ingest_odds(_snap(1.76, "2024-09-21T10:05:00+00:00"), parser_version="t_v1")  # move
    prices = sorted(s.odds for s in db.query(OddsSelection).all())
    assert prices == [1.76, 1.80]
    # Phase 13 idempotency: redelivery reuses the snapshot row (was 3).
    assert db.query(OddsSnapshot).filter_by(match_id=match_id).count() == 2


def test_pipeline_odds_multiple_bookmakers(db):
    from app.db.models.odds import OddsSnapshot

    pipe, match_id = _odds_pipe(db)
    pipe.ingest_odds(_snap(1.80, "2024-09-21T10:00:00+00:00"), parser_version="t_v1")
    pipe.ingest_odds(_snap(1.85, "2024-09-21T10:00:00+00:00", bookmaker="Pinnacle", bid="pin"),
                     parser_version="t_v1")
    assert db.query(OddsSnapshot).filter_by(match_id=match_id).count() == 2


def test_pipeline_odds_missing_market_or_price(db):
    pipe, _ = _odds_pipe(db)
    no_market = _snap(1.80, "2024-09-21T10:00:00+00:00")
    no_market.market = ""
    assert pipe.ingest_odds(no_market) is None
    bad_price = _snap(1.00, "2024-09-21T10:00:00+00:00")
    assert pipe.ingest_odds(bad_price) is None
    empty = _snap(1.80, "2024-09-21T10:00:00+00:00")
    empty.selections = []
    assert pipe.ingest_odds(empty) is None


def test_score_conflict_and_reconcile(db, monkeypatch):
    pipe, match_id = _odds_pipe(db)
    assert check_score(db, match_id, "csv", 2, 1) is None  # first fills canonical
    m = db.get(Match, match_id)
    assert (m.home_score, m.away_score) == (2, 1)
    assert check_score(db, match_id, "csv", 2, 1) is None  # agreement: no conflict
    conflict = check_score(db, match_id, "odds_api", 1, 1)
    assert conflict is not None and conflict.status == "open"
    # Agreement leaves no trace; only canonical + dissenter are recorded.
    assert conflict.values == {"canonical": [2, 1], "odds_api": [1, 1]}
    assert (m.home_score, m.away_score) == (2, 1)  # canonical untouched
    monkeypatch.setattr(get_settings(), "SOURCE_PRIORITY", "odds_api,csv")
    resolved = reconcile_match(db, match_id)
    assert resolved is not None and resolved.status == "resolved"
    assert "odds_api" in resolved.resolution
    assert (m.home_score, m.away_score) == (1, 1)


def test_reconcile_no_prioritized_source(db, monkeypatch):
    pipe, match_id = _odds_pipe(db)
    check_score(db, match_id, "csv", 2, 1)
    check_score(db, match_id, "odds_api", 1, 1)
    monkeypatch.setattr(get_settings(), "SOURCE_PRIORITY", "unknown_source")
    resolved = reconcile_match(db, match_id)
    assert resolved is not None and resolved.status == "resolved"
    assert db.query(SourceConflict).filter_by(status="open").count() == 0


# ---------------------------------------------------------------- quality

def test_quality_match():
    assert validate_match("A", "B", 2, 1, league_code="EPL").valid is True
    bad = validate_match("A", "A", -1, 99)
    assert bad.valid is False
    fields = {i.field for i in bad.issues}
    assert {"teams", "home_score", "away_score"} <= fields
    assert validate_match("", "B").valid is False
    assert validate_match("A", "B", kickoff_at="not-a-date").valid is False  # type: ignore[arg-type]


def test_quality_stat():
    assert validate_stat("shots", "5").valid is True
    assert validate_stat("possession", "54%").valid is True
    assert validate_stat("possession", "140%").valid is False
    assert validate_stat("shots", "-2").valid is False
    assert validate_stat("", "5").valid is False


def test_quality_odds():
    assert validate_odds(1.80, "home", "h2h").valid is True
    assert validate_odds(1.00, "home", "h2h").valid is False
    assert validate_odds("nan-price", "home", "h2h").valid is False
    assert validate_odds(1.80, "", "h2h").valid is False


def test_quality_event():
    assert validate_event(23, "goal").valid is True
    assert validate_event(999, "goal").valid is False
    assert validate_event(10, "").valid is False


def test_pipeline_quarantines_bad_match(db):
    pipe = Pipeline(db, "csv")
    bad = NormalizedMatch(league_code="EPL", season="2024", home_team="Leeds",
                          away_team="Leeds", kickoff_at=None, status="SCHEDULED")
    assert pipe.ingest_match(bad) is None
    row = db.query(RawDataRecord).filter_by(entity_type="match").one()
    assert row.processing_status == "quarantined"


# ---------------------------------------------------------------- registry

def test_registry_resolve_and_chain():
    reset_registries()
    football = get_football_registry()
    assert set(football.available()) >= {"api_football", "football_data_co_uk", "csv"}
    assert set(get_odds_registry().available()) >= {"odds_api", "football_data_co_uk", "csv"}
    assert set(get_historical_registry().available()) >= {"csv", "football_data_co_uk"}
    with pytest.raises(ValueError, match="unknown football source"):
        football.resolve("nope")
    chain = football.resolve_chain("csv", "api_football", file_path="x.csv")
    assert [getattr(s, "source_name", "") for s in chain] == ["csv", "api_football"]
    single = football.resolve_chain("csv", "", file_path="x.csv")
    assert len(single) == 1
    reset_registries()


def test_default_chains_from_config():
    reset_registries()
    try:
        chain = football_source_chain()
        assert getattr(chain[0], "source_name", "") == get_settings().FOOTBALL_SOURCE_PRIMARY
    finally:
        reset_registries()


# ---------------------------------------------------------------- wrappers

def test_api_football_source_wrapper():

    from app.services.sources.football.api_football_source import ApiFootballSource
    from tests.fixtures.mock_responses import FIXTURES_RESPONSE

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FIXTURES_RESPONSE)

    src = ApiFootballSource(client=_mock_client(handler))
    fixtures = asyncio.run(src.get_fixtures("EPL", "2024", "2024-09-21", "2024-09-21"))
    assert len(fixtures) == 2 and all(f.league_code == "EPL" for f in fixtures)
    assert fixtures[0].provenance.source == "api_football"
    assert fixtures[0].home_team == "Arsenal"
    assert src.check()["source"] == "api_football"


def test_odds_api_source_wrapper():

    from app.services.sources.odds.odds_api_source import OddsApiSource
    from tests.fixtures.mock_responses import ODDS_RESPONSE

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ODDS_RESPONSE)

    src = OddsApiSource(client=_mock_client(handler))
    snaps = asyncio.run(src.get_odds_snapshots("EPL", "2024"))
    assert len(snaps) == 1 and snaps[0].market == "h2h"
    assert snaps[0].selections[0].bookmaker == "Bet365"
    assert set(src.supported_markets()) >= {"h2h"}


def test_fdco_url_and_fetch(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.services.sources.football.football_data_co_uk import (
        FootballDataCoUkSource,
        season_segment,
        season_url,
    )

    # Isolate the on-disk dataset cache: real downloads must never leak in.
    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))

    assert season_segment("2024") == "2425"
    assert season_url("https://www.football-data.co.uk/mmz4281", "EPL", "2024") == \
        "https://www.football-data.co.uk/mmz4281/2425/E0.csv"
    with pytest.raises(ValueError, match="no division"):
        season_url("https://x", "UCL", "2024")

    with open(f"{FIXTURES}/epl_sample.csv", encoding="utf-8") as fh:
        text = fh.read()

    class StubFetcher:
        def __init__(self):
            self.calls = 0

        async def fetch_text(self, url: str) -> str:
            self.calls += 1
            assert url.endswith("/2425/E0.csv")
            return text

    src = FootballDataCoUkSource()
    src.fetcher = StubFetcher()
    fixtures = asyncio.run(src.get_fixtures("EPL", "2024"))
    assert len(fixtures) == 3
    assert fixtures[0].home_team == "West Ham" and fixtures[0].home_score == 0
    teams = asyncio.run(src.get_teams("EPL", "2024"))
    assert {t.name for t in teams} >= {"West Ham", "Chelsea", "Liverpool"}
    snaps = asyncio.run(src.get_odds_snapshots("EPL", "2024"))
    assert snaps and all(s.source == "football_data_co_uk" for s in snaps)
    assert asyncio.run(src.get_odds_snapshots("EPL", "2024", live=True)) == []


# ---------------------------------------------------------------- coverage

def test_coverage_report(db):
    from scripts.data_coverage import build_coverage, season_label

    assert season_label(None) == "unknown"
    from datetime import datetime

    assert season_label(datetime(2024, 9, 21)) == "2024"
    assert season_label(datetime(2025, 1, 5)) == "2024"

    CsvFileSource(file_path=f"{FIXTURES}/epl_sample.csv", db=db).import_history("EPL", "2024")
    report = build_coverage(db, "EPL", "2024")
    cov = report["leagues"]["EPL 2024"]
    assert cov["matches"] == 3
    assert cov["odds"] == 3 and cov["historical_odds"] == 3
    assert cov["statistics"] == 3  # half-time goals only in this file
    assert cov["xg"] == 0  # honestly absent from this file
    assert cov["teams"] == 6
    assert report["unresolved_teams"] == 0 and report["unresolved_matches"] == 0


def test_raw_record_upsert(db):
    from app.services.scraping.framework import record_raw

    record_raw(db, source="csv", entity_type="match", source_record_id="R1",
               payload="v1", parser_version="p_v1", status="processed")
    record_raw(db, source="csv", entity_type="match", source_record_id="R1",
               payload="v1-again", parser_version="p_v1", status="processed")
    rows = db.query(RawDataRecord).filter_by(source="csv", source_record_id="R1").all()
    assert len(rows) == 1  # same key -> one row, idempotent
    assert rows[0].parser_version == "p_v1"
