"""Collect odds snapshots via the source registry (append-only).

Only markets the source actually provides are persisted:

    python scripts/collect_odds.py --league EPL --season 2024
    python scripts/collect_odds.py --league EPL --season 2024 --live --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.sources.pipeline import Pipeline  # noqa: E402
from scripts.collect_lib import (  # noqa: E402
    attempt,
    common_args,
    configured_leagues,
    odds_chain,
    open_db,
    run_async,
)


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Collect odds snapshots (append-only).")
    common_args(ap)
    ap.add_argument("--live", action="store_true", help="Live odds where the source offers them")
    args = ap.parse_args()

    skwargs = {"file_path": args.file} if args.file else {}
    summary: dict = {"operation": "collect_odds", "leagues": {}}
    db = None if args.dry_run else open_db()
    try:
        for entry in configured_leagues(args.league):
            def op(source, _e=entry):
                return run_async(lambda: source.get_odds_snapshots(
                    _e["code"], args.season or _e["season"], live=args.live))

            try:
                served_by, snaps = attempt(odds_chain(args.source, **skwargs), op)
            except RuntimeError as exc:
                summary["leagues"][entry["code"]] = {"error": str(exc)}
                continue
            markets = sorted({s.market for s in snaps if s.market})
            league_out: dict = {"source": served_by, "snapshots": len(snaps),
                                "markets": markets}
            if not args.dry_run:
                assert db is not None
                pipe = Pipeline(db, served_by)
                for snap in snaps:
                    pipe.ingest_odds(snap, parser_version="collect_odds_v1")
                stats = pipe.finish("collect_odds", league=entry["code"])
                league_out.update({"inserted": stats.inserted,
                                   "duplicates": stats.duplicates,
                                   "quarantined": stats.quarantined,
                                   "unresolved": stats.unresolved})
            summary["leagues"][entry["code"]] = league_out
        print(json.dumps(summary, indent=2, default=str))
        return 0
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
