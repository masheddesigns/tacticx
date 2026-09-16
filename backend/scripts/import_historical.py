"""Historical dataset importer (Phase 1.6).

    python scripts/import_historical.py --file data/epl_2020_2025.csv --league EPL

Validates schema, normalizes teams/dates/competitions, resolves identities,
detects duplicates, preserves source + record IDs, upserts idempotently, and
reports exactly what happened. Malformed rows are listed AND written to a
.rejected.jsonl file — never silently discarded. Re-running is safe (resumable).
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging, get_logger  # noqa: E402
from app.services.sources.registry import get_historical_registry  # noqa: E402

log = get_logger(__name__)


def _season_range(season: str, from_season: str, to_season: str) -> list[str]:
    """Single season or inclusive range. Raises ValueError on bad input."""
    if from_season or to_season:
        start, end = int(from_season or to_season), int(to_season or from_season)
        if end < start:
            raise ValueError("to-season before from-season")
        if end - start > 40:
            raise ValueError("season range too wide (>40)")
        return [str(y) for y in range(start, end + 1)]
    if not season:
        raise ValueError("pass --season or --from-season/--to-season")
    return [season]


def print_report(report: dict) -> None:
    print(f"Records read:       {report.get('records_read', 0):>8}")
    print(f"Valid:              {report.get('valid', 0):>8}")
    print(f"Inserted:           {report.get('inserted', 0):>8}")
    print(f"Updated:            {report.get('updated', 0):>8}")
    print(f"Duplicates skipped: {report.get('duplicates_skipped', 0):>8}")
    print(f"Invalid:            {report.get('invalid', 0):>8}")
    if report.get("filtered"):
        print(f"Filtered (scope):   {report.get('filtered', 0):>8}")
    for err in (report.get("errors") or [])[:10]:
        print(f"  error: {err}")
    if report.get("_rejected_path"):
        print(f"Rejected rows: {report['_rejected_path']}")


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Import historical CSV/JSON/Parquet datasets.")
    ap.add_argument("--file", default="", help="Dataset path (.csv/.json/.jsonl/.parquet; required for csv source; supports {season} template for ranges)")
    ap.add_argument("--league", required=True, help="Our league code, e.g. EPL")
    ap.add_argument("--season", default="", help="Season label, e.g. 2024")
    ap.add_argument("--from-season", dest="from_season", default="", help="First season for range imports, e.g. 2020")
    ap.add_argument("--to-season", dest="to_season", default="", help="Last season for range imports, e.g. 2024")
    ap.add_argument("--refresh", action="store_true", help="Re-download remote datasets even when locally cached")
    ap.add_argument("--with-details", action="store_true", help="Also import lineups/events (sources that offer them), bounded by --max-matches")
    ap.add_argument("--max-matches", type=int, default=10, help="Bound for detail fetching per season")
    ap.add_argument("--source", default="", help="Historical source name (default: HISTORICAL_SOURCE)")
    ap.add_argument("--from", dest="date_from", default="", help="Start date YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", default="", help="End date YYYY-MM-DD")
    ap.add_argument("--column-map", default="", help="JSON object mapping canonical->file columns")
    ap.add_argument("--dry-run", action="store_true", help="Parse + validate only, persist nothing")
    ap.add_argument("--no-create-teams", action="store_true", help="Strict mode: unresolved teams stay unresolved")
    ap.add_argument("--rejected-file", default="", help="Where to write rejected rows (default: <file>.rejected.jsonl)")
    args = ap.parse_args()

    settings = get_settings()
    column_map = json.loads(args.column_map) if args.column_map else None
    rejected_path = args.rejected_file or f"{args.file}.rejected.jsonl"

    Base.metadata.create_all(get_engine())
    registry = get_historical_registry()
    name = args.source or settings.HISTORICAL_SOURCE

    if args.dry_run:
        # Scratch in-memory DB: identical resolution behavior, zero side effects.
        from sqlalchemy import create_engine as _mk
        from sqlalchemy.orm import sessionmaker as _sm

        scratch = _mk("sqlite://")
        Base.metadata.create_all(scratch)
        db = _sm(bind=scratch)()
    else:
        db = get_session_local()()
    try:
        seasons = _season_range(args.season, args.from_season, args.to_season)
        aggregate = {"records_read": 0, "valid": 0, "filtered": 0, "inserted": 0,
                     "updated": 0, "duplicates_skipped": 0, "invalid": 0, "errors": []}
        all_rejected: list = []
        for season in seasons:
            ctor_kwargs: dict = {"db": db}
            if name == "csv":
                template = args.file
                if not template:
                    print("IMPORT FAILED: --file is required for the csv source")
                    return 1
                ctor_kwargs["file_path"] = template.format(season=season)
                if column_map:
                    ctor_kwargs["column_map"] = column_map
            # Remote dataset sources (e.g. football_data_co_uk) ignore --file/--column-map.
            source = registry.resolve(name, **ctor_kwargs)
            report = source.import_history(
                args.league, season, args.date_from or None, args.date_to or None,
                create_teams=not args.no_create_teams,
                refresh=args.refresh,
                include_details=args.with_details,
                max_detail_matches=args.max_matches if args.with_details else 0)
            all_rejected.extend(report.pop("_rejected", []))
            for key in ("records_read", "valid", "filtered", "inserted", "updated",
                        "duplicates_skipped", "invalid"):
                aggregate[key] += report.get(key, 0)
            aggregate["errors"].extend(report.get("errors", []))
            aggregate["detail_matches"] = aggregate.get("detail_matches", 0) + report.get(
                "detail_matches", 0)
            print(f"--- season {season}: read={report.get('records_read', 0)} "
                  f"inserted={report.get('inserted', 0)} "
                  f"dupes={report.get('duplicates_skipped', 0)} "
                  f"invalid={report.get('invalid', 0)}")
        rejected = all_rejected
        report = aggregate
        rejected = report.pop("_rejected", [])
        if rejected and not args.dry_run:
            with open(rejected_path, "w", encoding="utf-8") as fh:
                for item in rejected:
                    fh.write(json.dumps(item, default=str) + "\n")
            report["_rejected_path"] = rejected_path
        elif rejected:
            report["_rejected_path"] = f"{len(rejected)} rows (dry-run: not written)"
        print_report(report)
        return 0
    except (ValueError, FileNotFoundError) as exc:
        print(f"IMPORT FAILED: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
