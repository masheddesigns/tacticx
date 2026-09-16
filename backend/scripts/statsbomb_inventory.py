"""StatsBomb inventory + collection manifest (Phase 1.8).

Before downloading anything, see what exists where:

    python scripts/statsbomb_inventory.py --all
    python scripts/statsbomb_inventory.py --competition "La Liga" --season 2015
    python scripts/statsbomb_inventory.py --league EPL --season 2015 --manifest
    python scripts/statsbomb_inventory.py --league LA_LIGA --season 2015 --probe --max-probe 20

Manifest statuses per match: IMPORTED | PARTIAL | AVAILABLE | NOT_AVAILABLE |
FAILED | UNKNOWN. Availability without download is established from local
cache + DB state; --probe additionally HEAD-checks missing files (bounded,
polite). A file confirmed missing (404) is recorded and never retried blindly.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401
from app.db.models.core import Lineup, MatchEvent, MatchStatistic  # noqa: E402
from app.db.models.provenance import MatchSourceMapping, RawDataRecord  # noqa: E402
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging, get_logger  # noqa: E402
from app.services.scraping.datasets import cache_dir  # noqa: E402
from app.services.sources.football.statsbomb import (  # noqa: E402
    COMPETITIONS,
    StatsBombSource,
)

log = get_logger(__name__)

CODE_BY_COMPETITION = {name.lower(): code for code, (name, _cid) in COMPETITIONS.items()}


def _season_rows(adapter: StatsBombSource, league_code: str, season: str) -> tuple[list, str]:
    try:
        matches = asyncio.run(adapter.fetch_season_matches(league_code, season))
        return matches, ""
    except Exception as exc:  # noqa: BLE001 — inventory never crashes on a season
        return [], str(exc)[:200]


def _canonical_ids(db) -> dict[str, int]:
    """StatsBomb sid -> canonical match id (via source mappings)."""
    rows = db.query(MatchSourceMapping).filter_by(source="statsbomb").all()
    return {r.source_match_id: r.match_id for r in rows}


def build_manifest(db, adapter: StatsBombSource, league_code: str, season: str,
                   probe: bool = False, max_probe: int = 0) -> dict:
    """Per-match collection manifest (derived — no extra table needed).

    Availability evidence, strongest first: DB details > local cache >
    HEAD probe (opt-in, bounded) > UNKNOWN. 404s are sticky NOT_AVAILABLE.
    """
    comp_name, comp_id = adapter._comp(league_code)
    matches, error = _season_rows(adapter, league_code, season)
    try:
        season_id = asyncio.run(adapter._season_id(comp_name, comp_id, season))
    except Exception:
        season_id = None
    sid_of = {str(m.get("match_id", "")): adapter.sid_for(comp_id, season_id or 0,
                                                          str(m.get("match_id", "")))
              for m in matches}
    mapping = _canonical_ids(db)
    # Batch DB state for all mapped canonical matches.
    mapped_mids = sorted({mapping[s] for s in sid_of.values() if s in mapping})
    events_by_match: dict[int, int] = {}
    lineups_by_match: dict[int, int] = {}
    xg_by_match: dict[int, bool] = {}
    if mapped_mids:
        from sqlalchemy import func as _func

        for mid, n in db.query(MatchEvent.match_id, _func.count()).filter(
                MatchEvent.match_id.in_(mapped_mids),
                MatchEvent.source == "statsbomb").group_by(MatchEvent.match_id).all():
            events_by_match[mid] = n
        for mid, n in db.query(Lineup.match_id, _func.count()).filter(
                Lineup.match_id.in_(mapped_mids),
                Lineup.source == "statsbomb").group_by(Lineup.match_id).all():
            lineups_by_match[mid] = n
        for mid in db.query(MatchStatistic.match_id).filter(
                MatchStatistic.match_id.in_(mapped_mids),
                MatchStatistic.stat_name == "expected_goals",
                MatchStatistic.source == "statsbomb").distinct().all():
            xg_by_match[mid[0]] = True
    detail_raw = {(r.source_record_id): r for r in db.query(RawDataRecord).filter(
        RawDataRecord.source == "statsbomb",
        RawDataRecord.entity_type == "match_details").all()}
    try:
        cached = {p.name for p in cache_dir("statsbomb").glob("*.json")}
    except OSError:
        cached = set()

    manifest = []
    probes_used = 0
    for m in matches:
        mid = str(m.get("match_id", ""))
        sid = sid_of.get(mid, "")
        canonical = mapping.get(sid)
        ev_n = events_by_match.get(canonical or -1, 0) if canonical else 0
        lu_n = lineups_by_match.get(canonical or -1, 0) if canonical else 0
        has_xg = bool(canonical and xg_by_match.get(canonical))
        ev_cached = f"events_{mid}.json" in cached
        lu_cached = f"lineups_{mid}.json" in cached
        raw = detail_raw.get(mid)
        status = "UNKNOWN"
        if canonical and ev_n and lu_n:
            status = "IMPORTED"
        elif raw is not None and raw.processing_status == "failed" \
                and "404" in (raw.error_message or ""):
            status = "NOT_AVAILABLE"
        elif raw is not None and raw.processing_status == "failed":
            status = "FAILED"
        elif canonical and (ev_n or lu_n):
            status = "PARTIAL"
        elif ev_cached and lu_cached:
            status = "AVAILABLE"
        probed: dict[str, object] = {}
        if probe and status in ("UNKNOWN", "PARTIAL") and probes_used < max_probe:
            probed = asyncio.run(_probe_pair(adapter, mid))
            probes_used += 2
            if probed.get("events") is False and probed.get("lineups") is False:
                status = "NOT_AVAILABLE"
            elif probed.get("events") or probed.get("lineups"):
                status = "AVAILABLE"
        manifest.append({
            "match_id": mid,
            "canonical_match_id": canonical,
            "home": ((m.get("home_team") or {}).get("home_team_name", "")),
            "away": ((m.get("away_team") or {}).get("away_team_name", "")),
            "date": m.get("match_date", ""),
            "events": ev_n, "lineups": lu_n, "xg": has_xg,
            "events_cached": ev_cached, "lineups_cached": lu_cached,
            "last_attempt": raw.processed_at.isoformat() if raw and raw.processed_at else None,
            "detail_error": (raw.error_message or "")[:200] if raw else "",
            "probed": probed,
            "status": status,
        })
    by_status: dict[str, int] = {}
    for row in manifest:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    return {"competition": comp_name, "season": season, "fetch_error": error,
            "matches_available": len(matches), "by_status": by_status,
            "manifest": manifest}


async def _probe_pair(adapter: StatsBombSource, match_id: str) -> dict:
    base = adapter.base_url
    return {
        "events": await adapter.fetcher.head_exists(f"{base}/events/{match_id}.json"),
        "lineups": await adapter.fetcher.head_exists(f"{base}/lineups/{match_id}.json"),
    }


def build_inventory(db, league_code: str = "", season: str = "",
                    probe: bool = False, max_probe: int = 0,
                    include_manifest: bool = False) -> dict:
    adapter = StatsBombSource()
    targets: list[tuple[str, str]] = []
    if league_code:
        if season:
            targets.append((league_code.upper(), season))
        else:
            comp_name, _cid = adapter._comp(league_code.upper())
            targets.extend(_seasons_for_comp(adapter, comp_name))
    else:
        for code in sorted(COMPETITIONS):
            if season:
                targets.append((code, season))
            else:
                comp_name, _cid = adapter._comp(code)
                targets.extend(_seasons_for_comp(adapter, comp_name))
    report: dict = {"competitions": {}}
    for code, season_name in targets:
        key = f"{code} {season_name}"
        try:
            manifest = build_manifest(db, adapter, code, season_name,
                                      probe=probe, max_probe=max_probe)
        except Exception as exc:  # noqa: BLE001
            report["competitions"][key] = {"error": str(exc)[:200]}
            continue
        entry: dict = {
            "matches_available": manifest["matches_available"],
            "fetch_error": manifest["fetch_error"],
            "by_status": manifest["by_status"],
            "with_events": sum(1 for r in manifest["manifest"] if r["events"]),
            "with_lineups": sum(1 for r in manifest["manifest"] if r["lineups"]),
            "with_xg": sum(1 for r in manifest["manifest"] if r["xg"]),
            "missing_detail": sum(1 for r in manifest["manifest"]
                                  if r["status"] in ("UNKNOWN", "AVAILABLE", "PARTIAL", "FAILED")),
        }
        if include_manifest:
            entry["manifest"] = manifest["manifest"]
        report["competitions"][key] = entry
    return report


def _seasons_for_comp(adapter: StatsBombSource, comp_name: str) -> list[tuple[str, str]]:
    """All seasons listed for a competition in competitions.json."""
    import asyncio as _asyncio

    try:
        data = _asyncio.run(adapter._get_json("competitions.json", "competitions.json"))
    except Exception:
        return []
    code = CODE_BY_COMPETITION.get(comp_name.lower(), "")
    out = []
    for row in data if isinstance(data, list) else []:
        if isinstance(row, dict) and row.get("competition_name") == comp_name:
            season_name = str(row.get("season_name", ""))
            ours = season_name.split("/")[0] if "/" in season_name else season_name
            out.append((code, ours))
    return sorted(set(out))


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="StatsBomb inventory + manifest.")
    ap.add_argument("--competition", default="", help='e.g. "La Liga" (or --league CODE)')
    ap.add_argument("--league", default="", help="Our league code, e.g. LA_LIGA")
    ap.add_argument("--season", default="", help="Our season label, e.g. 2015")
    ap.add_argument("--all", action="store_true", dest="show_all")
    ap.add_argument("--manifest", action="store_true", help="Include per-match rows")
    ap.add_argument("--probe", action="store_true", help="HEAD-verify missing files (bounded)")
    ap.add_argument("--max-probe", type=int, default=20)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    code = args.league.upper()
    if args.competition and not code:
        code = CODE_BY_COMPETITION.get(args.competition.strip().lower(), "")
        if not code:
            print(f"unknown competition: {args.competition}")
            return 1

    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        report = build_inventory(db, code, args.season, probe=args.probe,
                                 max_probe=args.max_probe,
                                 include_manifest=args.manifest)
        if args.as_json:
            print(json.dumps(report, indent=2, default=str))
        else:
            for key, cov in report["competitions"].items():
                print(f"\n{key}")
                if cov.get("fetch_error"):
                    print(f"  fetch_error: {cov['fetch_error']}")
                    continue
                print(f"  Matches available: {cov['matches_available']:>6}")
                print(f"  With events:       {cov['with_events']:>6}")
                print(f"  With lineups:      {cov['with_lineups']:>6}")
                print(f"  With xG:           {cov['with_xg']:>6}")
                print(f"  Missing detail:    {cov['missing_detail']:>6}")
                print(f"  By status: {cov['by_status']}")
                if args.manifest:
                    for row in cov.get("manifest", []):
                        if row["status"] not in ("IMPORTED",):
                            print(f"    {row['date']} {row['home']} v {row['away']} "
                                  f"[{row['status']}] ev={row['events']} lu={row['lineups']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
