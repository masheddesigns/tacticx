"""Shared runner for collect_* jobs (Phase 1.6).

Resolves the primary source with configured fallback, fetches normalized
records, validates/persists via the pipeline (or reports in --dry-run).
Resumable: re-runs only touch changed rows.
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Base  # noqa: F401
from app.db.session import get_engine, get_session_local
from app.logging_config import get_logger
from app.services.sources.registry import get_football_registry, get_odds_registry

log = get_logger(__name__)


def common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--league", default="", help="League code (default: all configured)")
    ap.add_argument("--season", default="", help="Season label, e.g. 2024")
    ap.add_argument("--from", dest="date_from", default="", help="Start date YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", default="", help="End date YYYY-MM-DD")
    ap.add_argument("--source", default="", help="Source name (default: configured primary->fallback)")
    ap.add_argument("--file", default="", help="Dataset path (for file-based sources like csv)")
    ap.add_argument("--dry-run", action="store_true", help="Fetch + validate only, persist nothing")
    ap.add_argument("--max-matches", type=int, default=20, help="Bound detail fetching per league")


def configured_leagues(wanted: str) -> list[dict]:
    entries = get_settings().supported_leagues_parsed()
    codes = {c.strip() for c in wanted.split(",") if c.strip()}
    return [e for e in entries if not codes or e["code"] in codes]


def resolve_pair(registry, primary: str, fallback: str, explicit: str, **kwargs) -> list:
    """Explicit --source, else configured primary->fallback chain."""
    if explicit:
        return [registry.resolve(explicit, **kwargs)]
    return registry.resolve_chain(primary, fallback, **kwargs)


def football_chain(explicit: str, **kwargs) -> list:
    s = get_settings()
    return resolve_pair(get_football_registry(), s.FOOTBALL_SOURCE_PRIMARY,
                        s.FOOTBALL_SOURCE_FALLBACK, explicit, **kwargs)


def odds_chain(explicit: str, **kwargs) -> list:
    s = get_settings()
    return resolve_pair(get_odds_registry(), s.ODDS_SOURCE_PRIMARY,
                        s.ODDS_SOURCE_FALLBACK, explicit, **kwargs)


def open_db() -> Session:
    Base.metadata.create_all(get_engine())
    return get_session_local()()


def attempt(chain: list, operation):
    """Try each source in order; fall through on failure. Returns (source_name, result)."""
    errors = []
    for source in chain:
        name = getattr(source, "source_name", "?")
        try:
            result = operation(source)
            return name, result
        except Exception as exc:  # noqa: BLE001 — fall back, report at the end
            log.warning("source %s failed (%s); trying next", name, exc)
            errors.append(f"{name}: {exc}"[:200])
    raise RuntimeError("all sources failed: " + "; ".join(errors))


def run_async(awaitable):
    """Run a coroutine (or zero-arg coroutine factory) to completion."""
    if asyncio.iscoroutine(awaitable):
        return asyncio.run(awaitable)
    return asyncio.run(awaitable())
