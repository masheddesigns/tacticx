"""API-Football smoke test — minimal real requests, summary output only.

1. GET /status           -> auth check + account/quota info (free on most plans)
2. GET /fixtures?league&season&next=1 -> exactly ONE upcoming fixture

Prints HTTP status, provider response status, fixtures received, quota info.
Exit 0 on success, non-zero on any failure. Never prints the API key.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.logging_config import configure_logging, get_logger  # noqa: E402
from app.services.football.api_football import ApiFootballProvider  # noqa: E402
from app.services.http_client import ProviderHTTPError  # noqa: E402

log = get_logger(__name__)


async def _run() -> dict:
    s = get_settings()
    out: dict = {"provider": "api_football", "checks": {}}
    if not s.FOOTBALL_API_KEY.strip():
        out["checks"]["config"] = "FAIL: FOOTBALL_API_KEY missing"
        return out
    out["checks"]["config"] = "OK: FOOTBALL_API_KEY configured"

    provider = ApiFootballProvider()
    # 1. Auth + quota via /status (tiny, usually quota-free).
    try:
        status = await provider._get("/status", ttl=60)
    except ProviderHTTPError as exc:
        out["checks"]["auth"] = f"FAIL: /status -> {exc} (status={exc.status_code})"
        return out
    resp = status.get("response", {}) if isinstance(status, dict) else {}
    out["checks"]["auth"] = "OK"
    out["account"] = {k: resp.get(k) for k in ("name", "firstname", "lastname", "country")}
    out["quota"] = resp.get("requests") or resp.get("subscription") or "not reported"
    out["http_status"] = 200

    # 2. Exactly one upcoming fixture (smallest useful football payload).
    leagues = s.supported_leagues_parsed()
    first = leagues[0] if leagues else {"provider_id": "39", "season": "2024", "code": "EPL"}
    try:
        data = await provider._get(
            "/fixtures",
            {"league": first["provider_id"], "season": first["season"], "next": 1},
            ttl=300,
        )
    except ProviderHTTPError as exc:
        out["checks"]["fixtures"] = f"FAIL: {exc} (status={exc.status_code})"
        return out
    rows = data.get("response", []) if isinstance(data, dict) else []
    out["checks"]["fixtures"] = "OK"
    out["fixtures_received"] = len(rows)
    out["provider_status"] = (data.get("status") if isinstance(data, dict) else None) or "ok"
    if rows:
        fx = rows[0].get("fixture", {})
        out["sample"] = {
            "id": fx.get("id"),
            "date": fx.get("date"),
            "status": fx.get("status"),
            "teams": {k: v.get("name") for k, v in rows[0].get("teams", {}).items()},
        }
    else:
        out["sample"] = None
    out["today"] = date.today().isoformat()
    return out


def main() -> int:
    configure_logging("INFO")
    try:
        out = asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 — smoke test must report, not traceback
        print(json.dumps({"provider": "api_football", "checks": {"fatal": f"FAIL: {exc}"}}, indent=2))
        return 1
    print(json.dumps(out, indent=2, default=str))
    failed = any(str(v).startswith("FAIL") for v in out.get("checks", {}).values())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
