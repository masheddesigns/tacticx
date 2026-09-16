"""Collect per-match statistics/events/lineups via the source registry.

Bounded by --max-matches per league; sources without detail data return
empty lists (absent, never invented):

    python scripts/collect_statistics.py --league EPL --season 2024 --from 2024-08-01 --to 2024-08-31 --max-matches 10
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
    football_chain,
    open_db,
    run_async,
)


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Collect match details (bounded, resumable).")
    common_args(ap)
    args = ap.parse_args()

    skwargs = {"file_path": args.file} if args.file else {}
    summary: dict = {"operation": "collect_statistics", "leagues": {}}
    db = None if args.dry_run else open_db()
    try:
        for entry in configured_leagues(args.league):
            def op(source, _e=entry):
                return run_async(lambda: source.get_fixtures(
                    _e["code"], args.season or _e["season"],
                    args.date_from or None, args.date_to or None))

            try:
                served_by, fixtures = attempt(football_chain(args.source, **skwargs), op)
            except RuntimeError as exc:
                summary["leagues"][entry["code"]] = {"error": str(exc)}
                continue
            league_out: dict = {"source": served_by, "fixtures": len(fixtures)}
            if args.dry_run:
                league_out["detail_matches"] = min(len(fixtures), max(1, args.max_matches))
                summary["leagues"][entry["code"]] = league_out
                continue
            assert db is not None
            pipe = Pipeline(db, served_by)
            src = next(s for s in football_chain(args.source, **skwargs)
                       if getattr(s, "source_name", "") == served_by)
            for f in fixtures[: max(1, args.max_matches)]:
                match_id = pipe.ingest_match(f, parser_version=f.provenance.parser_version)
                if match_id is None:
                    continue
                sid = f.provenance.source_record_id
                detail_stats = run_async(src.get_match_statistics(sid))
                pipe.ingest_statistics(match_id, detail_stats,
                                       parser_version=f.provenance.parser_version)
                events = run_async(src.get_match_events(sid))
                pipe.ingest_events(match_id, events, parser_version=f.provenance.parser_version)
                lineups = run_async(src.get_lineups(sid))
                pipe.ingest_lineups(match_id, lineups, parser_version=f.provenance.parser_version)
            stats = pipe.finish("collect_statistics", league=entry["code"])
            league_out.update({"inserted": stats.inserted, "updated": stats.updated,
                               "duplicates": stats.duplicates,
                               "quarantined": stats.quarantined, "unresolved": stats.unresolved})
            summary["leagues"][entry["code"]] = league_out
        print(json.dumps(summary, indent=2, default=str))
        return 0
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
