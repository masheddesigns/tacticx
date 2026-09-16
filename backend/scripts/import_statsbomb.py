"""StatsBomb detail collection (Phase 1.8).

    python scripts/import_statsbomb.py --competition "La Liga" --season 2015 --with-details
    python scripts/import_statsbomb.py --league LA_LIGA --season 2015 --with-details --max-matches 50
    python scripts/import_statsbomb.py --league LA_LIGA --season 2015 --with-details --resume
    python scripts/import_statsbomb.py --league LA_LIGA --season 2015 --dry-run

Resumable by default: matches that already have details (or recorded 404s)
are skipped; --no-resume forces reprocessing. --dry-run plans from cached
files + DB state without downloading details or writing.
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.sources.football.statsbomb import StatsBombSource  # noqa: E402
from scripts.statsbomb_inventory import CODE_BY_COMPETITION, build_manifest  # noqa: E402

CODE_BY_NAME = dict(CODE_BY_COMPETITION)


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="StatsBomb collection (resumable, bounded).")
    ap.add_argument("--competition", default="", help='e.g. "La Liga" (or --league CODE)')
    ap.add_argument("--league", default="", help="Our league code, e.g. LA_LIGA")
    ap.add_argument("--season", default="", help="Our season label, e.g. 2015")
    ap.add_argument("--with-details", action="store_true",
                    help="Import lineups + events/xG (bounded by --max-matches)")
    ap.add_argument("--max-matches", type=int, default=50)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--resume", dest="resume", action="store_true", default=True,
                    help="Skip imported/404 matches (default: on)")
    ap.add_argument("--no-resume", dest="resume", action="store_false",
                    help="Reprocess details even when present")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from", dest="date_from", default="")
    ap.add_argument("--to", dest="date_to", default="")
    args = ap.parse_args()

    code = args.league.upper()
    if args.competition and not code:
        code = CODE_BY_NAME.get(args.competition.strip().lower(), "")
        if not code:
            print(f"unknown competition: {args.competition}")
            return 1
    if not code or not args.season:
        print("pass --league/--competition and --season")
        return 1

    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        source = StatsBombSource(db=db, db_session_factory=get_session_local)
        if args.dry_run:
            manifest = build_manifest(db, source, code, args.season)
            missing = manifest["by_status"]
            print(json.dumps({
                "competition": manifest["competition"], "season": manifest["season"],
                "matches_available": manifest["matches_available"],
                "would_import_matches": manifest["matches_available"],
                "would_import_details": sum(1 for r in manifest["manifest"]
                                            if r["status"] in ("UNKNOWN", "AVAILABLE", "PARTIAL",
                                                               "FAILED")),
                "by_status": missing,
            }, indent=2))
            return 0
        report = source.import_history(
            code, args.season, args.date_from or None, args.date_to or None,
            max_detail_matches=args.max_matches if args.with_details else 0,
            refresh=args.refresh, resume=args.resume)
        print(json.dumps({k: v for k, v in report.items() if not k.startswith("_")},
                         indent=2, default=str))
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"IMPORT FAILED: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
