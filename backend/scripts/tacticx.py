"""TacticX prediction intelligence CLI (Phase 6).

    python scripts/tacticx.py predict <match_id> [--model ensemble --json]
    python scripts/tacticx.py explain <match_id>
    python scripts/tacticx.py scenarios <match_id> [--names baseline,high_scoring]
    python scripts/tacticx.py analogues <match_id> [--top-k 10]
    python scripts/tacticx.py mirofish <match_id> [--scenario baseline]

Cutoff defaults to the match kickoff. Every command reads real data;
analytical outputs never use betting language and never mutate the stored
core prediction (scenario/mirofish runs are recorded separately).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401
from app.db.models.core import Match  # noqa: E402
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.features.temporal import TemporalMode  # noqa: E402
from app.services.intelligence.composer import PredictionComposer  # noqa: E402


def _common(ap) -> None:
    ap.add_argument("match_id", type=int)
    ap.add_argument("--model", default=None,
                    help="core model (default: regime-selected ensemble_v1)")
    ap.add_argument("--temporal-mode", default="strict_prematch",
                    choices=["strict_prematch", "historical_estimated"])
    ap.add_argument("--cutoff", default="",
                    help="ISO cutoff (default: match kickoff)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--json", action="store_true", dest="as_json")


def _resolve(db, args):
    match = db.get(Match, args.match_id)
    if match is None:
        print(f"no match with id {args.match_id}")
        return None, None, None
    try:
        cutoff = datetime.fromisoformat(args.cutoff) if args.cutoff else match.kickoff_at
    except ValueError:
        print("cutoff must be ISO format")
        return None, None, None
    if cutoff is None:
        print("match has no kickoff; pass --cutoff explicitly")
        return None, None, None
    return match, cutoff, TemporalMode(args.temporal_mode)


def _cmd_predict(db, args) -> int:
    _, cutoff, mode = _resolve(db, args)
    if cutoff is None:
        return 1
    try:
        composed = PredictionComposer().compose(
            db, args.match_id, cutoff, mode, model=args.model, seed=args.seed)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    out = composed.model_dump()
    if args.as_json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    print(f"{out['model']['version']} [{out['status']}] mode={mode.value}")
    probs = out["probabilities"]
    print(f"  1X2: H={probs['home']:.3f} D={probs['draw']:.3f} A={probs['away']:.3f} "
          f"(sums to {probs['validation']['sum']})")
    print(f"  xG: H={out['goals'].get('home_lambda')} "
          f"A={out['goals'].get('away_lambda')} T={out['goals'].get('total_lambda')}")
    totals = out["markets"]["totals"].get("probabilities", {})
    print(f"  O1.5={totals.get('over_1_5')} O2.5={totals.get('over_2_5')} "
          f"O3.5={totals.get('over_3_5')} BTTS={out['markets']['btts'].get('yes')}")
    dc = out["markets"]["double_chance"].get("probabilities", {})
    print(f"  1X={dc.get('1x')} X2={dc.get('x2')} 12={dc.get('12')}")
    top = out["markets"]["correct_scores"].get("top", [])[:5]
    print("  scores: " + ", ".join(f"{s['score']}={s['probability']:.3f}" for s in top))
    print(f"  entropy={out['uncertainty']['predictive_entropy']} "
          f"margin={out['uncertainty']['probability_margin']}")
    print(f"  market: {out['market']['status']}")
    print(f"  cutoff={out['cutoff']} xg_used={composed.core_prediction.get('xg_used')}")
    return 0


def _cmd_explain(db, args) -> int:
    _, cutoff, mode = _resolve(db, args)
    if cutoff is None:
        return 1
    try:
        composed = PredictionComposer().compose(
            db, args.match_id, cutoff, mode, model=args.model, seed=args.seed,
            with_disagreement=True, with_market=False)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    expl = composed.explanation.model_dump()
    if args.as_json:
        print(json.dumps(expl, indent=2, default=str))
        return 0
    print(expl["headline"])
    print()
    for factor in expl["factors"]:
        print(f"- [{factor['factor']}] {factor['statement']}")
        print(f"  source: {factor['source']}")
    print()
    print("model disagreement:", expl["model_disagreement_note"])
    print("xg:", json.dumps(expl["xg"]))
    return 0


def _cmd_scenarios(db, args) -> int:
    from app.services.intelligence import scenarios as scenario_engine

    _, cutoff, mode = _resolve(db, args)
    if cutoff is None:
        return 1
    try:
        composed = PredictionComposer().compose(
            db, args.match_id, cutoff, mode, model=args.model, seed=args.seed,
            with_disagreement=False, with_market=False)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    names = [n.strip() for n in (args.names or "").split(",") if n.strip()] or None
    try:
        outputs = scenario_engine.run_all(
            {k: composed.probabilities[k] for k in ("home", "draw", "away")},
            composed.goals.get("home_lambda"), composed.goals.get("away_lambda"),
            names=names)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    if args.as_json:
        print(json.dumps([o.model_dump() for o in outputs], indent=2, default=str))
        return 0
    for out in outputs:
        dd = out.model_dump()
        print(f"[{dd['name']}] {dd['parameters'].get('description')}")
        print(f"  1X2: H={dd['probabilities']['home']:.3f} "
              f"D={dd['probabilities']['draw']:.3f} A={dd['probabilities']['away']:.3f}")
        print(f"  xG: H={dd['goals']['home_lambda']} A={dd['goals']['away_lambda']} "
              f"T={dd['goals']['total_lambda']}")
        print(f"  O2.5={dd['markets']['over_2_5']:.3f} BTTS={dd['markets']['btts']:.3f}")
        d = dd["difference_from_baseline"]["probabilities"]
        print(f"  Δ vs baseline: H={d['home']:+.3f} D={d['draw']:+.3f} A={d['away']:+.3f}")
    print("scenarios are sensitivity analyses, not predictions of what will happen.")
    return 0


def _cmd_analogues(db, args) -> int:
    from app.services.intelligence import analogues as analogue_service

    _, cutoff, mode = _resolve(db, args)
    if cutoff is None:
        return 1
    result = analogue_service.find_analogues(db, args.match_id, cutoff, mode,
                                             top_k=args.top_k)
    out = result.model_dump()
    if args.as_json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    print(f"analogue status: {out['status']}")
    for a in out["analogues"]:
        print(f"  match {a['match_id']} ({a['kickoff_at'][:10]}): "
              f"actual={a['actual']} {a['home_score']}-{a['away_score']} "
              f"similarity={a['similarity']}")
    print("historical outcome distribution:", out["outcome_distribution"])
    print("method:", out["methodology"][:160])
    return 0


def _cmd_mirofish(db, args) -> int:
    from app.services.intelligence import mirofish_adapter

    _, cutoff, mode = _resolve(db, args)
    if cutoff is None:
        return 1
    try:
        composed = PredictionComposer().compose(
            db, args.match_id, cutoff, mode, model=args.model, seed=args.seed,
            with_disagreement=False, with_market=False)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    result = asyncio.run(mirofish_adapter.run_mirofish(
        composed, scenario_name=args.scenario,
        timeout_seconds=args.timeout_seconds))
    out = result.model_dump()
    if args.as_json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    print(f"mirofish status: {out['status']}")
    print(json.dumps(out["output"], indent=2, default=str)[:1500])
    print("core prediction untouched:",
          composed.probabilities)
    return 0


def _cmd_sync_upcoming(db, args) -> int:
    from app.services.lifecycle import cached
    from app.services.lifecycle import sync as sync_service
    from app.services.lifecycle import upcoming as upcoming_service

    start, end = sync_service.upcoming_window(args.hours)
    sources = upcoming_service.default_sources()
    if not sources:
        print("no providers configured (FOOTBALL_API_KEY/ODDS_API_KEY missing); "
              "nothing to sync against")
        return 1
    key = cached.cache_key("upcoming", "fetch", args.league or "all",
                           start.date().isoformat(), end.date().isoformat())
    def _load():
        grouped = upcoming_service.fetch_all(sources, start, end, args.league)
        serializable = {}
        for name, records in grouped.items():
            if name.endswith("__error"):
                serializable[name] = records
            else:
                serializable[name] = [r.model_dump(mode="json") for r in records]
        return serializable

    envelope = cached.cached_fetch(key, cached.upcoming_ttl(), _load)
    from app.services.lifecycle.upcoming import UpcomingMatch

    grouped = {}
    for name, records in (envelope["data"] or {}).items():
        if name.endswith("__error"):
            grouped[name] = records
        else:
            grouped[name] = [UpcomingMatch(**r) for r in records]
    print(f"fixture response: {envelope['data_status']} "
          f"(fetched_at={envelope['fetched_at']})")
    total_seen = total_created = 0
    for name, records in grouped.items():
        if name.endswith("__error"):
            print(f"source {name}: error: {records}")
            continue
        stats = sync_service.sync_upcoming_matches(db, records)
        print(f"source {name}: seen={stats.received} created={stats.inserted} "
              f"updated={stats.updated} skipped={stats.skipped} "
              f"errors={len(stats.errors)}")
        total_seen += stats.received
        total_created += stats.inserted
    print(f"total: seen={total_seen} created={total_created} "
          f"window=[{start.isoformat()}, {end.isoformat()}]")
    return 0


def _cmd_sync_fixtures(db, args) -> int:
    """Acquisition-run-logged fixture sync (idempotent; partial-safe)."""
    from app.services.acquisition import activation, workflow
    from app.services.lifecycle import sync as sync_service
    from app.services.lifecycle import upcoming as upcoming_service

    start, end = sync_service.upcoming_window(args.hours)
    sources = upcoming_service.default_sources()
    if not sources:
        print("no providers configured; nothing to sync against")
        return 1
    if args.league:
        sources = [s for s in sources]  # league filter applied per fetch
    activation.ensure_jobs(db)
    overall = {"sources": {}}
    for source in sources:
        try:
            grouped_records = upcoming_service.fetch_all(
                [source], start, end, args.league)
            records = grouped_records.get(source.name, [])
            error_key = f"{source.name}__error"
            if error_key in grouped_records:
                result = workflow.run_acquisition(
                    db, source.name, [],
                    job="fixture_discovery",
                    requested_scope={"league": args.league or "all"},
                    failure=RuntimeError(str(grouped_records[error_key])))
            else:
                result = workflow.run_acquisition(
                    db, source.name, records, job="fixture_discovery",
                    requested_scope={"league": args.league or "all",
                                     "from": start.isoformat(),
                                     "to": end.isoformat()})
        except Exception as exc:
            result = workflow.run_acquisition(
                db, source.name, [], job="fixture_discovery", failure=exc)
        overall["sources"][source.name] = result
        print(f"{source.name}: {result.get('status')} "
              f"seen={result.get('seen', 0)} created={result.get('created', 0)} "
              f"updated={result.get('updated', 0)} "
              f"({result.get('classification', 'ok')})")
        activation.mark_job_run(db, "fixture_discovery")
    if args.as_json:
        print(json.dumps(overall, indent=2, default=str))
    return 0


def _cmd_readiness(db, args) -> int:
    from app.services.acquisition.snapshot import readiness_report

    if args.match_id is not None:
        targets = [args.match_id]
    else:
        from app.db.models.core import League, Match

        query = db.query(Match.id)
        if args.league:
            league = db.query(League).filter_by(code=args.league).first()
            if league is None:
                print(f"unknown league: {args.league}")
                return 1
            query = query.filter(Match.league_id == league.id)
        targets = [mid for (mid,) in query.order_by(Match.id.asc())
                   .limit(args.limit).all()]
    reports = []
    for match_id in targets:
        report = readiness_report(db, match_id)
        reports.append(report)
        if not args.as_json:
            print(f"{report.get('match', match_id)} "
                  f"{report.get('kickoff', '')[:16]} "
                  f"Fixture: {report.get('fixture_status', '?').upper()} "
                  f"Identity: {report.get('source_count', 0)}src "
                  f"Hist: {report.get('historical_features')} "
                  f"Players: {report.get('player_features')} "
                  f"XG: {report.get('xg')} Market: {report.get('market')} "
                  f"Prediction: {report.get('prediction')} "
                  f"Mode: {report.get('mode')}")
    if args.as_json:
        print(json.dumps(reports, indent=2, default=str))
    return 0


def _cmd_predict_upcoming(db, args) -> int:
    from app.services.lifecycle.upcoming_predictions import UpcomingPredictionService
    from app.services.features.temporal import TemporalMode as Mode

    service = UpcomingPredictionService(model=args.model, mode=Mode(args.temporal_mode),
                                        seed=args.seed)
    result = service.predict_window(db, hours=args.hours, league_code=args.league,
                                    limit=args.limit)
    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["status"] != "failed" else 1
    print(f"batch: {result['status']} matches={result['n_matches']} "
          f"ok={result['n_success']} partial={result['n_partial']} "
          f"failed={result['n_failed']} ({result['duration_seconds']}s)")
    for item in result["results"]:
        version = (item.get("version") or {}).get("version_number", "-")
        print(f"  match {item['match_id']}: {item['status']} v{version} "
              f"{item.get('error', '')}")
    return 0 if result["status"] != "failed" else 1


def _cmd_refresh(db, args) -> int:
    from app.services.lifecycle.upcoming_predictions import UpcomingPredictionService
    from app.services.features.temporal import TemporalMode as Mode

    service = UpcomingPredictionService(model=args.model, mode=Mode(args.temporal_mode),
                                        seed=args.seed)
    result = service.refresh_one(db, args.match_id)
    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["status"] == "success" else 1
    if result["status"] != "success":
        print(f"refresh failed: {result.get('error')}")
        return 1
    print(f"match {args.match_id}: v{result['version']['version_number']} "
          f"({result['version']['state']})")
    diff = result.get("diff") or {}
    for key, change in (diff.get("probability_changes") or {}).items():
        print(f"  {key}: {change['before']:.3f} -> {change['after']:.3f} "
              f"({change['wording']})")
    return 0


def _cmd_evaluate(db, args) -> int:
    from app.services.lifecycle.evaluate import evaluate_completed_predictions

    stats = evaluate_completed_predictions(db, limit=args.limit)
    print(f"evaluate: received={stats.received} inserted={stats.inserted} "
          f"skipped={stats.skipped} errors={len(stats.errors)}")
    for error in stats.errors[:5]:
        print(f"  error: {error}")
    return 0


def _cmd_player_features(db, args) -> int:
    from app.services.player_intelligence import feature_snapshot

    if args.match_id is None and not args.league:
        print("pass --match-id or --league")
        return 1
    from app.db.models.core import League, Match

    if args.match_id is not None:
        targets = [args.match_id]
    else:
        league = db.query(League).filter_by(code=args.league).first()
        if league is None:
            print(f"unknown league: {args.league}")
            return 1
        targets = [m.id for m in db.query(Match.id).filter_by(
            league_id=league.id).order_by(Match.id.asc()).limit(args.limit).all()]
    mode = {"strict": "strict_prematch", "estimated": "historical_estimated"}[args.mode]
    from app.services.features.temporal import TemporalMode

    for match_id in targets:
        match = db.get(Match, match_id)
        if match is None or match.kickoff_at is None:
            print(f"match {match_id}: UNAVAILABLE (no kickoff)")
            continue
        try:
            out = feature_snapshot.build_snapshot(
                db, match_id, match.kickoff_at, TemporalMode(mode), persist=False)
        except ValueError as exc:
            print(f"match {match_id}: UNAVAILABLE ({exc})")
            continue
        if args.as_json:
            print(json.dumps(out, indent=2, default=str))
            continue
        for side in ("home", "away"):
            block = out[side]
            status = block.get("status", "unknown").upper()
            if status != "OK":
                print(f"match {match_id} {side}: {status} "
                      f"({block.get('reason', '')})")
                continue
            team = block.get("team", {})
            quality = (block.get("quality", {}) or {}).get("quality", "unknown")
            tag = "ESTIMATED" if out["mode"] == "historical_estimated" else "AVAILABLE"
            print(f"match {match_id} {side}: {tag} quality={quality} "
                  f"regulars={team.get('n_regular_contributors')} "
                  f"contributors={len(block.get('contributors', []))}")
    return 0


def _cmd_research(db, args) -> int:
    from app.services.features.temporal import TemporalMode
    from app.services.model_research import ablation as ablation_svc
    from app.services.model_research import experiments as experiments_svc
    from app.services.model_research import promotion as promotion_svc

    mode = TemporalMode(args.mode)
    if args.action == "registry":
        counts = promotion_svc.count_tested(db)
        if args.as_json:
            print(json.dumps(counts, indent=2, default=str))
        else:
            print(f"tested candidates: {counts['total']} {counts['by_status']}")
        return 0
    if args.action == "promote-check":
        if not args.model_id:
            print("pass --model-id")
            return 1
        from app.db.models.research import ResearchModel

        record = db.query(ResearchModel).filter_by(
            model_id=args.model_id).order_by(ResearchModel.id.desc()).first()
        if record is None:
            print(f"unknown model: {args.model_id}")
            return 1
        checklist = promotion_svc.promotion_checklist(
            (record.metrics or {}).get("gate_evidence", {}))
        print(json.dumps(checklist, indent=2, default=str))
        return 0
    if args.action == "ablate":
        families = ["team", "xg", "shots", "player"]

        def evaluate_fn(plan):
            report = experiments_svc.run_season_experiment(
                db, args.league, "logreg_all" if set(plan) == set(families)
                else _candidate_for(plan),
                args.train.split(","), args.validate, args.test.split(","),
                mode=mode, hypothesis="exploratory", persist_artifacts=False)
            return {"brier": report["metrics"]["brier"],
                    "log_loss": report["metrics"]["log_loss"],
                    "n": report["test_n"],
                    "delta_brier": report["deltas_vs_ensemble"]["delta_brier"]}

        def coverage_fn(plan):
            return {"eligible": True}

        result = ablation_svc.run_ablation(evaluate_fn, families, coverage_fn)
        print(json.dumps(result, indent=2, default=str))
        return 0
    # run
    try:
        if args.folds and args.folds > 0:
            report = experiments_svc.run_folds_experiment(
                db, args.league, args.candidate, n_folds=args.folds,
                mode=mode, hypothesis=args.hypothesis)
        else:
            report = experiments_svc.run_season_experiment(
                db, args.league, args.candidate, args.train.split(","),
                args.validate, args.test.split(","), mode=mode,
                hypothesis=args.hypothesis, split_date=args.split_date)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    if args.as_json:
        print(json.dumps(report, indent=2, default=str))
        return 0
    print(f"{report['candidate']} [{report.get('status', 'complete')}] "
          f"test_n={report['test_n']} ({report['duration_seconds']}s)")
    print(f"  metrics: {report['metrics']}")
    print(f"  baseline: {report['baseline_metrics']}")
    print(f"  deltas: {report['deltas_vs_ensemble']}")
    if report.get("calibration"):
        print(f"  calibration: raw={report['calibration']['raw']} "
              f"cal={report['calibration']['calibrated']}")
    print(f"  artifact: {report.get('artifact')}")
    return 0


def _candidate_for(plan) -> str:
    families = set(plan)
    if families == {"team"}:
        return "logreg_team"
    if families == {"team", "xg"}:
        return "logreg_team_xg"
    if families == {"team", "shots"}:
        return "logreg_team_shots"
    if families == {"team", "player"}:
        return "logreg_team_player"
    return "logreg_all"


def _cmd_reconcile(db, args) -> int:
    import time

    from app.services.reconciliation import matches as match_recon

    start = time.monotonic()
    if args.match:
        from app.db.models.core import Match as MatchModel

        match = db.get(MatchModel, args.match)
        if match is None:
            print(f"no match with id {args.match}")
            return 1
        observed = {"kickoff_at": match.kickoff_at, "status": match.status,
                    "home_score": match.home_score, "away_score": match.away_score}
        result = match_recon.reconcile_match(
            db, args.match, match.provider or "unknown", observed,
            dry_run=args.dry_run)
    else:
        if not args.league and not args.all_leagues:
            print("pass --match, --league, or --all (bounded by --limit)")
            return 1
        result = match_recon.reconcile_league(
            db, league_code=args.league, season=args.season,
            limit=args.limit, dry_run=args.dry_run)
    result["duration_seconds"] = round(time.monotonic() - start, 2)
    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
        return 0
    print(f"reconcile (dry_run={args.dry_run}): "
          f"{json.dumps({k: v for k, v in result.items() if k != 'conflicts'}, default=str)}")
    for conflict in (result.get("conflicts") or [])[:10]:
        print(f"  {conflict.get('type')}:{conflict.get('field')} "
              f"{conflict.get('canonical')} vs {conflict.get('observed')} "
              f"[{conflict.get('severity', '?')}/{conflict.get('status', '?')}]")
    return 0


def _cmd_data_quality(db, args) -> int:
    from app.services.reconciliation import conflicts as conflict_svc
    from app.services.reconciliation import identities, matrix, quality

    report = {
        "coverage": matrix.canonical_coverage(db, league_code=args.league),
        "completeness": quality.league_completeness(db, league_code=args.league),
        "conflicts": conflict_svc.summarize(db),
        "unresolved_queue": identities.queue_summary(db),
        "sources": matrix.coverage_matrix(db),
    }
    if args.as_json:
        print(json.dumps(report, indent=2, default=str))
        return 0
    print(f"matches: {report['coverage'].get('matches')} "
          f"(multi={report['coverage'].get('multi_source')} "
          f"single={report['coverage'].get('single_source')} "
          f"unresolved={report['coverage'].get('unresolved')})")
    print(f"conflicts: {report['conflicts'].get('total')} "
          f"{report['conflicts'].get('by_severity')}")
    print(f"unresolved queue: {report['unresolved_queue']}")
    print("sources:")
    for source, dims in (report["sources"].get("sources") or {}).items():
        present = [d for d, has in dims.items() if has]
        print(f"  {source}: {', '.join(present) if present else 'no measured coverage'}")
    return 0


def _cmd_mapping(db, args) -> int:
    from app.services.reconciliation import identities

    try:
        result = identities.apply_manual_mapping(
            db, args.entity_type, args.source, args.source_record_id,
            args.canonical_id, created_by=args.by, dry_run=args.dry_run)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def _cmd_data(db, args) -> int:
    from app.services.data_expansion import backfill as backfill_svc
    from app.services.data_expansion import inventory as inventory_svc
    from app.services.data_expansion import source_candidates as candidates_svc

    if args.action == "candidates":
        rows = candidates_svc.registry()
        if args.as_json:
            print(json.dumps(rows, indent=2, default=str))
            return 0
        for entry in rows:
            print(f"{entry['source']}: {entry['validation_status']} — {entry['reason'][:100]}")
        return 0
    if args.action == "backfill":
        if not args.league or not args.season:
            print("pass --league and --season (fdcuk season tag, e.g. 1617)")
            return 1
        report = backfill_svc.backfill_season(db, args.league, args.season,
                                              dest_dir="/tmp",
                                              dry_run=args.dry_run)
        print(json.dumps(report, indent=2, default=str))
        return 0
    # coverage
    report = inventory_svc.league_inventory(db, args.league)
    if args.as_json:
        print(json.dumps(report, indent=2, default=str))
        return 0
    header = (f"{'league':<10}{'season':<8}{'match':>6}{'stats':>6}{'xg':>5}"
              f"{'shots':>6}{'events':>7}{'lineups':>8}{'odds':>6}  temporal S/E/U")
    print(header)
    for entry in report.get("seasons", []):
        print(f"{entry['league']:<10}{entry['season']:<8}{entry['matches']:>6}"
              f"{entry['stats']:>6}{entry['xg']:>5}{entry['shots']:>6}"
              f"{entry['events']:>7}{entry['lineups']:>8}{entry['odds']:>6}  "
              f"{entry['strict_rows']}/{entry.get('estimated_rows', 0)}/{entry['unknown_rows']}")
    print("totals:", report.get("totals"))
    return 0


def _cmd_sources(db, args) -> int:
    import time

    from app.services.freshness import audit as audit_svc
    from app.services.freshness import registry as registry_svc

    start = time.monotonic()
    if args.action == "status":
        view = registry_svc.registry_view(db)
        if args.as_json:
            print(json.dumps(view, indent=2, default=str))
            return 0
        for entry in view:
            print(f"{entry['source']} [{entry['axis']}]: "
                  f"health={entry['health'].get('state')}")
            measured = entry.get("measured", {})
            have = [k for k, v in measured.items()
                    if v == "measured" and k in (
                        "fixtures", "results", "statistics", "events",
                        "lineups", "xg", "odds", "upcoming")]
            print(f"  MEASURED: {', '.join(have) if have else 'none'}")
    elif args.action == "coverage":
        report = audit_svc.current_season_audit(db)
        if args.as_json:
            print(json.dumps(report, indent=2, default=str))
            return 0
        print(f"current season: {report['current_season']} (as of {report['as_of'][:10]})")
        for league, slot in sorted(report["leagues"].items()):
            if args.league and league != args.league:
                continue
            print(f"{league}: {slot['status'].upper()} "
                  f"completed={slot['completed']} upcoming={slot['upcoming']} "
                  f"stats={slot['statistics']} events={slot['events']} "
                  f"lineups={slot['lineups']} xg={slot['xg']} odds={slot['odds']}")
            if slot["status"] == "unavailable":
                print(f"  reason: {slot['reason']}")
    elif args.action == "freshness":
        report = audit_svc.staleness_distribution(
            db, league_code=args.league)
        if args.as_json:
            print(json.dumps(report, indent=2, default=str))
            return 0
        print(f"staleness ({report.get('league')}, n={report.get('sampled')}):")
        for family, buckets in (report.get("distribution") or {}).items():
            print(f"  {family}: " + " ".join(f"{b}={v}" for b, v in buckets.items()))
    elif args.action == "validate":
        report = _validate_sources(db)
        if args.as_json:
            print(json.dumps(report, indent=2, default=str))
            return 0 if report["failures"] == 0 else 1
        print(f"source validation: {report['checks']} checks, "
              f"{report['failures']} failures")
        for line in report["lines"]:
            print(f"  {line}")
        return 0 if report["failures"] == 0 else 1
    print(f"({time.monotonic() - start:.2f}s)")
    return 0


def _validate_sources(db) -> dict:
    """Validation gate evidence: identity, fixtures, results, temporal,
    idempotency, security (no secrets in stored payloads)."""
    import time

    from app.db.models.core import League, Match, Team

    lines, failures = [], 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal failures
        lines.append(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
        if not ok:
            failures += 1

    # Identity: no duplicate canonical teams by normalized name per league.
    from app.services.identity.normalize import normalize_name

    dupes = 0
    for league in db.query(League).all():
        seen = {}
        for team in db.query(Team).filter(
                (Team.league_id == league.id) | (Team.league_id.is_(None))).all():
            key = normalize_name(team.name)
            if key in seen:
                dupes += 1
            seen[key] = team.id
    check("identity/no-duplicate-teams", dupes == 0, f"dupes={dupes}")
    # Fixtures: kickoff present on scheduled; scores only on finished.
    bad_kickoff = db.query(Match).filter(
        Match.status.in_(["SCHEDULED", "PRE_MATCH"]),
        Match.kickoff_at.is_(None)).count()
    check("fixtures/kickoff-known", bad_kickoff == 0, f"missing={bad_kickoff}")
    unfinished_scored = db.query(Match).filter(
        Match.status.in_(["SCHEDULED", "PRE_MATCH", "POSTPONED", "CANCELLED"]),
        ((Match.home_score.is_not(None)) | (Match.away_score.is_not(None)))).count()
    check("results/no-scores-before-finish", unfinished_scored == 0,
          f"violations={unfinished_scored}")
    # Temporal: effective_at never claims future validity.
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    from app.db.models.core import Lineup, MatchEvent, MatchStatistic

    now_utc = _dt.now(_tz.utc)
    future_eff = 0
    for model in (Lineup, MatchEvent, MatchStatistic):
        rows = db.query(getattr(model, "effective_at")).filter(
            getattr(model, "effective_at").is_not(None)).all()
        future_eff += sum(1 for (eff,) in rows if eff is not None and (
            eff.replace(tzinfo=None) if eff.tzinfo else eff) > now_utc.replace(tzinfo=None))
    check("temporal/no-future-effective", future_eff == 0, f"rows={future_eff}")
    # Idempotency evidence: no duplicate provider keys / event keys.
    from sqlalchemy import func as _func

    dup_matches = db.query(Match.provider, Match.provider_match_id,
                           _func.count()).group_by(
        Match.provider, Match.provider_match_id).having(_func.count() > 1).count()
    check("idempotency/unique-provider-keys", dup_matches == 0, f"dupes={dup_matches}")
    # Security: no secret-looking values in raw records / observations.
    from app.db.models.freshness import MatchObservation
    from app.db.models.provenance import RawDataRecord

    suspicious = 0
    for model, cols in ((RawDataRecord, ("source_record_id",)),
                        (MatchObservation, ("raw_reference",))):
        for (value,) in db.query(*[getattr(model, c) for c in cols]).all():
            lowered = (value or "").lower()
            if "apikey" in lowered or "api_key" in lowered or "bearer " in lowered:
                suspicious += 1
    check("security/no-secrets-stored", suspicious == 0, f"hits={suspicious}")
    return {"checks": len(lines), "failures": failures, "lines": lines}


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="TacticX prediction intelligence.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("predict", help="Composed match intelligence")
    _common(p)

    p = sub.add_parser("explain", help="Explain a prediction from actual inputs")
    _common(p)

    p = sub.add_parser("scenarios", help="Deterministic scenario analysis")
    _common(p)
    p.add_argument("--names", default="",
                   help="comma-separated scenario names (default: all)")

    p = sub.add_parser("analogues", help="Historical pre-match analogues")
    _common(p)
    p.add_argument("--top-k", type=int, default=10)

    p = sub.add_parser("mirofish", help="Optional MiroFish scenario layer")
    _common(p)
    p.add_argument("--scenario", default="baseline")
    p.add_argument("--timeout-seconds", type=float, default=30.0)

    p = sub.add_parser("sync-upcoming", help="Discover + sync upcoming fixtures")
    p.add_argument("--hours", type=int, default=None)
    p.add_argument("--league", default=None)

    p = sub.add_parser("predict-upcoming", help="Batch predictions for upcoming matches")
    p.add_argument("--hours", type=int, default=None)
    p.add_argument("--league", default=None)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--model", default=None)
    p.add_argument("--temporal-mode", default="strict_prematch",
                   choices=["strict_prematch", "historical_estimated"])
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("refresh", help="Refresh one match into a new version")
    p.add_argument("match_id", type=int)
    p.add_argument("--model", default=None)
    p.add_argument("--temporal-mode", default="strict_prematch",
                   choices=["strict_prematch", "historical_estimated"])
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("evaluate", help="Evaluate completed predictions")
    p.add_argument("--limit", type=int, default=500)

    p = sub.add_parser("player-features", help="Player/event/lineup feature snapshot")
    p.add_argument("--match-id", type=int, default=None)
    p.add_argument("--league", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--mode", default="strict", choices=["strict", "estimated"])
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("reconcile", help="Multi-source reconciliation")
    p.add_argument("--match", type=int, default=None)
    p.add_argument("--league", default=None)
    p.add_argument("--season", default=None)
    p.add_argument("--all", action="store_true", dest="all_leagues")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("data-quality", help="Coverage + conflicts + quality report")
    p.add_argument("--league", default=None)
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("mapping", help="Manual identity mapping")
    p.add_argument("entity_type", choices=["team", "player", "match", "bookmaker"])
    p.add_argument("source")
    p.add_argument("source_record_id")
    p.add_argument("canonical_id", type=int)
    p.add_argument("--by", default="cli")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("sync-fixtures", help="Acquisition-run fixture sync")
    p.add_argument("--hours", type=int, default=None)
    p.add_argument("--league", default=None)
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("readiness", help="Upcoming-match readiness report")
    p.add_argument("--match-id", type=int, default=None)
    p.add_argument("--league", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("sources", help="Source status/coverage/freshness/validation")
    p.add_argument("action", choices=["status", "coverage", "freshness", "validate"],
                   nargs="?", default="status")
    p.add_argument("--league", default=None)
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("data", help="Data expansion coverage")
    p.add_argument("action", choices=["coverage", "backfill", "candidates"],
                   nargs="?", default="coverage")
    p.add_argument("--league", default=None)
    p.add_argument("--season", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("research", help="Model research experiments (isolated)")
    p.add_argument("action", choices=["run", "ablate", "registry", "promote-check"],
                   nargs="?", default="run")
    p.add_argument("--league", default="EPL")
    p.add_argument("--candidate", default="logreg_team")
    p.add_argument("--train", default="2022")
    p.add_argument("--validate", default="2023")
    p.add_argument("--test", default="2024")
    p.add_argument("--mode", default="strict_prematch",
                   choices=["strict_prematch", "historical_estimated"])
    p.add_argument("--hypothesis", default="exploratory",
                   choices=["primary", "exploratory"])
    p.add_argument("--model-id", default="")
    p.add_argument("--split-date", default=None,
                   help="ISO cutoff splitting shared validate/test seasons")
    p.add_argument("--folds", type=int, default=0,
                   help="expanding folds instead of season protocol (0 = off)")
    p.add_argument("--json", action="store_true", dest="as_json")

    args = ap.parse_args()
    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        if args.command == "predict":
            return _cmd_predict(db, args)
        if args.command == "explain":
            return _cmd_explain(db, args)
        if args.command == "scenarios":
            return _cmd_scenarios(db, args)
        if args.command == "analogues":
            return _cmd_analogues(db, args)
        if args.command == "mirofish":
            return _cmd_mirofish(db, args)
        if args.command == "sync-upcoming":
            return _cmd_sync_upcoming(db, args)
        if args.command == "predict-upcoming":
            return _cmd_predict_upcoming(db, args)
        if args.command == "refresh":
            return _cmd_refresh(db, args)
        if args.command == "evaluate":
            return _cmd_evaluate(db, args)
        if args.command == "player-features":
            return _cmd_player_features(db, args)
        if args.command == "reconcile":
            return _cmd_reconcile(db, args)
        if args.command == "data-quality":
            return _cmd_data_quality(db, args)
        if args.command == "mapping":
            return _cmd_mapping(db, args)
        if args.command == "sync-fixtures":
            return _cmd_sync_fixtures(db, args)
        if args.command == "readiness":
            return _cmd_readiness(db, args)
        if args.command == "sources":
            return _cmd_sources(db, args)
        if args.command == "data":
            return _cmd_data(db, args)
        if args.command == "research":
            return _cmd_research(db, args)
        ap.error(f"unknown command: {args.command}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
