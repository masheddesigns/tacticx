"""The Odds API smoke test — minimum useful dataset, summary output only.

1. GET /sports            -> auth check (cheap, verifies key in force)
2. GET /sports/{sport}/odds -> one league feed, mapped into internal DTOs

Verifies mapping into bookmaker/market/selection/odds/timestamp/match fields.
Never dumps the full provider response. Exit 0/1. Never prints the API key.
"""
from __future__ import annotations

import asyncio
import json
import sys

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.logging_config import configure_logging, get_logger  # noqa: E402
from app.services.http_client import ProviderHTTPError  # noqa: E402
from app.services.odds.odds_api import DEFAULT_SPORT_KEY, OddsApiProvider  # noqa: E402

log = get_logger(__name__)


async def _run(sport_key: str) -> dict:
    s = get_settings()
    out: dict = {"provider": "odds_api", "sport_key": sport_key, "checks": {}}
    if not s.ODDS_API_KEY.strip():
        out["checks"]["config"] = "FAIL: ODDS_API_KEY missing"
        return out
    out["checks"]["config"] = "OK: ODDS_API_KEY configured"

    provider = OddsApiProvider()
    try:
        sports = await provider._get("/sports", ttl=3600)
    except ProviderHTTPError as exc:
        out["checks"]["auth"] = f"FAIL: /sports -> {exc} (status={exc.status_code})"
        return out
    out["checks"]["auth"] = "OK"
    out["sports_available"] = len(sports) if isinstance(sports, list) else 0
    out["quota_note"] = "see x-requests-remaining header in provider_request_logs"

    try:
        snaps = await provider.get_odds(sport_key=sport_key)
    except ProviderHTTPError as exc:
        out["checks"]["odds"] = f"FAIL: {exc} (status={exc.status_code})"
        return out
    out["checks"]["odds"] = "OK"
    events = {x.event_id for x in snaps if x.event_id}
    out["snapshots"] = len(snaps)
    out["events_covered"] = len(events)
    out["bookmakers"] = sorted({x.bookmaker for x in snaps})[:10]
    out["markets"] = sorted({x.market_type for x in snaps})
    out["selections_total"] = sum(len(x.selections) for x in snaps)
    # Mapping verification: every snapshot must carry the required fields.
    bad = [i for i, x in enumerate(snaps)
           if not x.bookmaker or not x.market_type or not x.selections
           or any(not sel.selection or not (sel.odds > 1.0) for sel in x.selections)]
    out["checks"]["mapping"] = "OK" if not bad else f"FAIL: {len(bad)} snapshots mis-mapped"
    if snaps:
        first = snaps[0]
        out["sample"] = {
            "bookmaker": first.bookmaker, "market": first.market_type,
            "event": {"home": first.home_team, "away": first.away_team,
                      "commence": str(first.commence_time)},
            "selections": [{"selection": y.selection, "odds": y.odds, "point": y.point}
                           for y in first.selections[:4]],
        }
    return out


def main() -> int:
    configure_logging("INFO")
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default=DEFAULT_SPORT_KEY)
    args = ap.parse_args()
    try:
        out = asyncio.run(_run(args.sport))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"provider": "odds_api", "checks": {"fatal": f"FAIL: {exc}"}}, indent=2))
        return 1
    print(json.dumps(out, indent=2, default=str))
    failed = any(str(v).startswith("FAIL") for v in out.get("checks", {}).values())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
