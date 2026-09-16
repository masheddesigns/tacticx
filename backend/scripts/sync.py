"""Controlled real sync CLI (Phase 1.5).

Small, bounded, quota-friendly. Examples:

  python -m scripts.sync --leagues EPL --next 5
  python -m scripts.sync --leagues EPL --date 2026-09-16
  python -m scripts.sync --match-id 12345 --with-details
  python -m scripts.sync --live-only --max-matches 1 --with-details --with-odds
  python -m scripts.sync --leagues EPL --next 5 --check-idempotency

--check-idempotency runs the fixture pass twice and reports entity counts
before/after; the second pass must not create duplicates.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.db.models import Base  # noqa: F401
from app.db.models.core import League, Match, Player, Team
from app.db.models.logs import ProviderRequestLog
from app.db.session import get_engine, get_session_local
from app.logging_config import configure_logging, get_logger
from app.services import ingestion
from app.services.odds.odds_api import LEAGUE_SPORT_KEYS
from app.services.providers import get_football_provider, get_odds_provider

log = get_logger(__name__)


def _counts(db) -> dict:
    return {
        "leagues": db.query(League).count(),
        "teams": db.query(Team).count(),
        "matches": db.query(Match).count(),
        "players": db.query(Player).count(),
        "provider_requests": db.query(ProviderRequestLog).count(),
    }


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", default="", help="Comma-separated codes, default=all configured")
    ap.add_argument("--date", default="", help="YYYY-MM-DD: fixtures on that date only")
    ap.add_argument("--next", default="", help="N: next N fixtures per league (small!)")
    ap.add_argument("--match-id", default="", help="Single provider match id to refresh")
    ap.add_argument("--live-only", action="store_true", help="Only live matches, bounded by --max-matches")
    ap.add_argument("--max-matches", type=int, default=1)
    ap.add_argument("--fixtures-only", action="store_true")
    ap.add_argument("--with-details", action="store_true", help="Fetch statistics/events/lineups")
    ap.add_argument("--with-odds", action="store_true", help="Fetch odds snapshots (bounded)")
    ap.add_argument("--odds-sport", default="", help="Odds sport key, default per-league mapping")
    ap.add_argument("--check-idempotency", action="store_true", help="Run fixture pass twice, compare counts")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.is_football_configured and not args.with_odds:
        print("FAIL: FOOTBALL_API_KEY missing — nothing to sync against.")
        return 1
    if args.with_odds and not settings.is_odds_configured:
        print("FAIL: ODDS_API_KEY missing — cannot fetch odds.")
        return 1

    Base.metadata.create_all(get_engine())  # dev convenience; prod uses alembic
    db = get_session_local()()
    try:
        football = get_football_provider(db_session_factory=get_session_local)
        wanted = set(filter(None, args.leagues.split(",")))
        entries = [e for e in settings.supported_leagues_parsed()
                   if not wanted or e["code"] in wanted]

        if args.match_id or args.live_only:
            return _run_single_mode(db, football, args, settings)

        before = _counts(db)
        for entry in entries:
            lg, _ = ingestion.upsert_league(
                db, code=entry["code"], name=entry["code"], provider=football.provider_name,
                provider_league_id=entry["provider_id"], season=entry["season"])
            fixtures = _fetch_fixtures(football, entry, args)
            stats = ingestion.sync_fixtures(db, fixtures, league_code=entry["code"], league_id=lg.id)
            log.info("league=%s received=%d inserted=%d updated=%d errors=%s",
                     entry["code"], stats.received, stats.inserted, stats.updated, stats.errors)
            if args.with_details and not args.fixtures_only:
                _sync_details(db, football, entry["code"], args)
            if args.with_odds:
                _sync_odds(db, args, entry["code"], settings)
        after = _counts(db)

        report = {"before": before, "after": after}
        if args.check_idempotency:
            # Second identical pass — must not create duplicates.
            for entry in entries:
                lg = db.query(League).filter_by(code=entry["code"]).first()
                fixtures = _fetch_fixtures(football, entry, args)
                ingestion.sync_fixtures(db, fixtures, league_code=entry["code"],
                                        league_id=lg.id if lg else None)
            twice = _counts(db)
            report["after_second_pass"] = twice
            dupes = {k: twice[k] - after[k] for k in ("leagues", "teams", "matches", "players")}
            report["idempotency"] = ("PASS" if all(v == 0 for v in dupes.values())
                                     else f"FAIL: deltas={dupes}")
        print(json.dumps(report, indent=2))
        return 0
    finally:
        db.close()


def _fetch_fixtures(football, entry: dict, args) -> list:
    if args.next:
        data = asyncio.run(football._get(
            "/fixtures",
            {"league": entry["provider_id"], "season": entry["season"], "next": int(args.next)},
            ttl=300,
        ))
        rows = data.get("response", []) if isinstance(data, dict) else []
        return [football._parse_fixture(r) for r in rows if isinstance(r, dict)]
    if args.date:
        # Single-day from/to range: identical to ?date= semantically, and works
        # on plans where the ?date= shortcut is restricted to near-today.
        data = asyncio.run(football._get(
            "/fixtures",
            {"league": entry["provider_id"], "season": entry["season"],
             "from": args.date, "to": args.date},
            ttl=300,
        ))
        rows = data.get("response", []) if isinstance(data, dict) else []
        return [football._parse_fixture(r) for r in rows if isinstance(r, dict)]
    return asyncio.run(football.get_fixtures(entry["provider_id"], entry["season"]))


def _sync_details(db, football, league_code: str, args) -> None:
    matches = db.query(Match).join(League, Match.league_id == League.id).filter(
        League.code == league_code).order_by(Match.kickoff_at.desc()).limit(args.max_matches * 5).all()
    for m in matches[: max(1, args.max_matches)]:
        stats = asyncio.run(ingestion._async_sync_details(db, m, football))
        log.info("details match=%s received=%d inserted=%d errors=%s",
                 m.provider_match_id, stats.received, stats.inserted, stats.errors)


def _sync_odds(db, args, league_code: str, settings) -> None:
    odds = get_odds_provider(db_session_factory=get_session_local)
    sport = args.odds_sport or LEAGUE_SPORT_KEYS.get(league_code, "soccer_epl")
    snaps = asyncio.run(odds.get_odds(sport_key=sport))
    matched, unmatched = 0, 0
    for snap in snaps:
        m = ingestion.find_match_for_odds_event(db, snap.home_team, snap.away_team, snap.commence_time)
        if m is None:
            unmatched += 1
            continue
        ingestion.store_odds_snapshots(db, m.id, [snap], odds.provider_name, is_live=False)
        matched += 1
    log.info("odds sport=%s snapshots=%d matched=%d unmatched(no match, skipped)=%d",
             sport, len(snaps), matched, unmatched)


def _run_single_mode(db, football, args, settings) -> int:
    """ONE match only: refresh metadata + optionally details/odds."""
    if args.match_id:
        fx = asyncio.run(football.get_match(args.match_id))
        fixtures = [fx] if fx else []
    else:
        data = asyncio.run(football._get("/fixtures", {"live": "all"}, ttl=30))
        fixtures = [football._parse_fixture(r) for r in data.get("response", [])][: args.max_matches]
    if not fixtures:
        print(json.dumps({"mode": "single", "result": "no matches returned (none live?)"}))
        return 0
    stats = ingestion.sync_fixtures(db, fixtures, league_code="SINGLE")
    for fx in fixtures:
        m = db.query(Match).filter_by(
            provider=fx.provider, provider_match_id=fx.provider_match_id).first()
        if m and args.with_details:
            d = asyncio.run(ingestion._async_sync_details(db, m, football))
            log.info("details received=%d inserted=%d errors=%s", d.received, d.inserted, d.errors)
        if m and args.with_odds:
            odds = get_odds_provider(db_session_factory=get_session_local)
            snaps = asyncio.run(odds.get_live_odds())
            mine = []
            for s in snaps:
                linked = ingestion.find_match_for_odds_event(
                    db, s.home_team, s.away_team, s.commence_time)
                if linked is not None and linked.id == m.id:
                    mine.append(s)
            if mine:
                ingestion.store_odds_snapshots(db, m.id, mine, odds.provider_name, is_live=True)
            log.info("live odds stored=%d (of %d fetched)", len(mine), len(snaps))
    print(json.dumps({"mode": "single", "received": stats.received,
                      "inserted": stats.inserted, "updated": stats.updated,
                      "counts": _counts(db)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
