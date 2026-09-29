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


def _cmd_intelligence(db, args) -> int:
    from app.services.features.temporal import TemporalMode as Mode
    from app.services.intelligence_v2 import service as intel_service

    match = db.get(Match, args.match_id)
    if match is None:
        print(f"no match with id {args.match_id}")
        return 1
    try:
        cutoff = datetime.fromisoformat(args.cutoff) if args.cutoff else match.kickoff_at
    except ValueError:
        print("cutoff must be ISO format")
        return 1
    if cutoff is None:
        print("match has no kickoff; pass --cutoff explicitly")
        return 1
    try:
        out = intel_service.build_intelligence(
            db, args.match_id, cutoff, Mode(args.temporal_mode),
            model=args.model, seed=args.seed,
            with_analogues=args.analogues, with_scenarios=args.scenarios)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    if args.as_json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    probs = out["prediction"]
    print(f"1X2: H={probs['home']:.3f} D={probs['draw']:.3f} A={probs['away']:.3f} "
          f"(sums to {probs['home'] + probs['draw'] + probs['away']:.6f})")
    if args.match_intelligence:
        from app.services.match_intelligence import service as mi_service

        try:
            doc = mi_service.build_match_intelligence(
                db, args.match_id, cutoff, Mode(args.temporal_mode),
                model=args.model, seed=args.seed,
                response_mode="compact" if args.compact else "standard")
        except ValueError as exc:
            print(f"error: {exc}")
            return 1
        core = doc["core_prediction"]
        print(f"match_intelligence_v1 match={doc['match']['match_id']} "
              f"H={core['home']:.3f} D={core['draw']:.3f} A={core['away']:.3f}")
        print(f"  mirofish={doc['mirofish']['status']} "
              f"warnings={len(doc['warnings'])} "
              f"hash={doc['provenance']['response_hash'][:12]}")
        return 0
    print(f"goals: H={out['goals'].get('home_lambda')} "
          f"A={out['goals'].get('away_lambda')}")
    print(f"uncertainty: entropy={out['uncertainty'].get('predictive_entropy')} "
          f"margin={out['uncertainty'].get('probability_margin')}")
    print(f"market: {out['market_comparison'].get('interpretation', {}).get('overall', '?')}")
    for warning in out["warnings"]:
        print(f"warning [{warning['severity']}]: {warning['code']}: {warning['detail']}")
    print(f"analogues: {out['analogues'].get('status')} "
          f"scenarios: {len(out['scenarios'])} "
          f"snapshot: {out['provenance'].get('snapshot_id')}")
    print(f"cutoff={out['provenance'].get('cutoff')} "
          f"hash={str(out['provenance'].get('hash'))[:12]}")
    if args.mirofish:
        from app.services.features.temporal import TemporalMode as Mode2
        from app.services.mirofish import config as mirofish_config
        from app.services.mirofish import scenario_builder
        from app.services.mirofish import service as mirofish_service

        scenario_id = args.scenario or "baseline"
        if scenario_id not in scenario_builder.allowed_scenario_ids():
            print(f"error: unknown scenario: {scenario_id} "
                  f"(known: {scenario_builder.allowed_scenario_ids()})")
            return 1
        print(f"mirofish: {mirofish_config.diagnose()}")
        try:
            result = mirofish_service.run_mirofish_scenario(
                db, args.match_id, cutoff, scenario_id,
                Mode(args.temporal_mode), model=args.model, seed=args.seed)
        except ValueError as exc:
            print(f"error: {exc}")
            return 1
        print(f"mirofish status: {result.get('status')}")
        if result.get("status") == "ok":
            print(f"  observations: {len(result.get('structured_observations', []))}")
            print(f"  narrative: {result.get('narrative', '')[:300]}")
            print(f"  response: {str(result.get('response_hash'))[:12]}")
        else:
            print(f"  reason: {result.get('error_code')}: "
                  f"{result.get('error_detail', '')[:200]}")
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


def _cmd_acquire(db, args) -> int:
    from app.services.acquisition import current_season

    leagues = [args.competition] if args.competition else None
    sources = None
    if args.source:
        # Source-scoped run: resolve through the provider factory so only
        # real configured adapters can be selected (never arbitrary code).
        from app.services.lifecycle import upcoming as upcoming_service
        from app.services.providers import get_football_provider, get_odds_provider

        if args.source == "api_football":
            provider = get_football_provider()
            sources = [upcoming_service.ApiFootballUpcomingSource(
                provider=provider)]
        elif args.source == "odds_api":
            provider = get_odds_provider()
            sources = [upcoming_service.OddsApiUpcomingSource(
                provider=provider)]
        else:
            print(f"unknown source: {args.source} (api_football|odds_api)")
            return 1
    if args.season == "current":
        report = current_season.acquire_current_season(
            db, leagues=leagues, sources=sources)
    else:
        # Explicit historical season: same pipeline, labeled scope.
        report = current_season.acquire_current_season(
            db, leagues=leagues, season=args.season, sources=sources)
    if getattr(args, "explain", False):
        from app.services.provider_qualification import plans as plans_mod
        from app.services.provider_qualification import registry as qual_registry
        from app.services.provider_qualification import snapshots as snapshots_mod

        for league_code in (leagues or list(current_season.TARGET_LEAGUES)):
            states = {}
            for source_id in qual_registry.get_registry().describe():
                latest = snapshots_mod.latest_for(db, source_id, league_code)
                status = latest.get("status", "unqualified")
                # Canonical selection only: qualified->A, partial->B,
                # anything else->D (market role is separate, never promoted).
                states[source_id] = {"qualified": "A",
                                     "partially_qualified": "B"}.get(status, "D")
            plan = plans_mod.build_plan(league_code, report.get("season", ""),
                                        states)
            print(f"plan {league_code}: selected={plan.selected_source or 'none'} "
                  f"hash={plan.plan_hash}")
            print(f"  reason: {plan.reason}")
            print(f"  fallbacks={plan.fallback_sources} "
                  f"candidates={plan.candidate_sources}")
            readiness = (report.get("readiness", {}) or {}).get("leagues", {})
            league_ready = readiness.get(league_code, {})
            print(f"  coverage: fixtures={league_ready.get('fixtures', '?')} "
                  f"eligible={league_ready.get('prediction_eligible', '?')}")
    if args.as_json:
        print(json.dumps(report, indent=2, default=str))
        return 0 if report.get("status") != "failed" else 1
    print(f"acquire season={report.get('season')} status={report.get('status')}")
    for league_code, league_report in (report.get("leagues") or {}).items():
        created = sum(
            (s.get("created", 0) or 0)
            for s in (league_report.get("sources") or {}).values()
            if isinstance(s, dict))
        print(f"  {league_code}: {league_report.get('status')} "
              f"created={created}")
        for name, result in (league_report.get("sources") or {}).items():
            if isinstance(result, dict) and result.get("status") not in (
                    "success", "partial_success", "empty"):
                print(f"    {name}: {result.get('status')}: "
                      f"{result.get('error', result.get('classification', ''))}")
    return 0 if report.get("status") != "failed" else 1


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
    elif args.action == "list":
        from app.services.provider_qualification import registry as qual_registry

        view = qual_registry.get_registry().describe()
        if args.as_json:
            print(json.dumps(view, indent=2, default=str))
            return 0
        for source_id, entry in view.items():
            print(f"{source_id}: enabled={entry['enabled']} "
                  f"qualification={entry['qualification_status']} "
                  f"priority={entry['priority']}")
            print(f"  competitions={entry['supported_competitions']} "
                  f"seasons={entry['supported_seasons']}")
        return 0
    elif args.action == "qualify":
        from app.services.provider_qualification import health_ext
        from app.services.provider_qualification import qualification as qual_svc
        from app.services.provider_qualification import registry as qual_registry

        names = [args.source] if args.source else [
            entry for entry in qual_registry.get_registry().describe()]
        results = {}
        competition = getattr(args, "competition", None) or args.league
        for name in names:
            verdict = qual_svc.qualify_source(
                name, competition=competition, season=args.season,
                max_requests=5, db=db)
            results[name] = verdict
            health_ext.record_qualification(db, name, verdict["status"])
        if args.as_json:
            print(json.dumps(results, indent=2, default=str))
            return 0
        for name, verdict in results.items():
            print(f"{name}: {verdict['status']} "
                  f"[{', '.join(verdict['reason_codes'])}] "
                  f"requests={verdict['request_count']} "
                  f"fixtures={verdict['coverage']['fixtures']}")
        return 0
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


def _cmd_model(db, args) -> int:
    """Model governance operations (Phase 30). Explicit only; no auto-promotion."""
    from app.services import model_governance as gov

    def emit(payload):
        if args.as_json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(json.dumps(payload, indent=2, default=str))
        return 0

    action = args.action
    if action == "registry":
        return emit({"bindings": gov.list_bindings(db)})
    if action == "champion":
        return emit(gov.active_champion_view(db))
    if action == "validate":
        if not args.artifact:
            print("pass --artifact <artifact_id>")
            return 1
        try:
            return emit(gov.validate_candidate(
                db, args.artifact, experiment_id=args.experiment or None,
                actor=args.actor))
        except Exception as exc:
            print(f"validation failed: {exc}")
            return 1
    if action == "validation":
        from app.db.models.governance import ModelValidationReport

        row = db.query(ModelValidationReport).filter_by(
            validation_id=args.validation).first()
        if row is None:
            print(f"unknown validation: {args.validation}")
            return 1
        return emit(gov.validation_to_dict(row))
    if action == "promotion-request":
        if not args.artifact or not args.validation:
            print("pass --artifact <id> --validation <id>")
            return 1
        try:
            return emit(gov.request_promotion(
                db, args.artifact, validation_id=args.validation,
                deployment_mode=args.mode, requester=args.actor,
                reason=args.reason))
        except Exception as exc:
            print(f"promotion request failed: {exc}")
            return 1
    if action in ("approve", "reject"):
        if not args.request:
            print("pass --request <request_id>")
            return 1
        try:
            return emit(gov.decide(
                db, args.request,
                decision="APPROVE" if action == "approve" else "REJECT",
                actor=args.actor, reason=args.reason))
        except Exception as exc:
            print(f"decision failed: {exc}")
            return 1
    if action == "shadow-start":
        if not args.artifact or not args.champion:
            print("pass --artifact <challenger> --champion <champion>")
            return 1
        try:
            return emit(gov.start_shadow(
                db, args.artifact, args.champion, actor=args.actor))
        except Exception as exc:
            print(f"shadow start failed: {exc}")
            return 1
    if action == "canary-activate":
        if not args.artifact:
            print("pass --artifact <artifact_id>")
            return 1
        try:
            return emit(gov.mark_canary_eligible(
                db, args.artifact, actor=args.actor))
        except Exception as exc:
            print(f"canary eligibility failed: {exc}")
            return 1
    if action == "production-activate":
        if not args.artifact or not args.expected_champion:
            print("pass --artifact <id> --expected-champion <id> --actor <name>")
            return 1
        try:
            return emit(gov.activate_production(
                db, args.artifact, actor=args.actor,
                expected_champion_artifact_id=args.expected_champion,
                reason=args.reason))
        except Exception as exc:
            print(f"production activation failed: {exc}")
            return 1
    if action == "rollback":
        if not args.artifact or not args.actor:
            print("pass --artifact <target> --actor <name>")
            return 1
        try:
            return emit(gov.rollback(
                db, actor=args.actor, target_artifact_id=args.artifact,
                reason=args.reason))
        except Exception as exc:
            print(f"rollback failed: {exc}")
            return 1
    if action == "audit":
        return emit({"events": gov.audit_trail(
            db, artifact_id=args.artifact or None)})
    print(f"unknown model action: {action}")
    return 1


def _cmd_system(db, args) -> int:
    """Local production system status (read-only)."""
    from sqlalchemy import text

    from app.config import get_settings
    from app.db.session import get_engine

    settings = get_settings()
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            version = conn.execute(
                text("SELECT version_num FROM alembic_version")).fetchone()
        database = {"reachable": True,
                    "migration": version[0] if version else "unstamped"}
    except Exception as exc:  # noqa: BLE001
        database = {"reachable": False, "error": str(exc)[:200]}
    try:
        from app.services.caching.cache import backend_name

        cache = {"backend": backend_name()}
    except Exception as exc:  # noqa: BLE001
        cache = {"backend": f"error: {exc}"[:200]}
    from app.services.scheduler import scheduler_status

    try:
        sched = scheduler_status(db)
        scheduler = {"recent_runs": len(sched.get("recent_runs", [])),
                     "locks": sched.get("locks", {})}
    except Exception as exc:  # noqa: BLE001
        scheduler = {"error": str(exc)[:200]}
    view = {"tacticx_env": settings.deployment_flavor(),
            "scheduler_enabled": settings.SCHEDULER_ENABLED,
            "prediction_enabled": settings.PREDICTION_ENABLED,
            "evaluation_enabled": settings.EVALUATION_ENABLED,
            "database": database, "cache": cache, "scheduler": scheduler,
            "diagnose": settings.diagnose()}
    print(json.dumps(view, indent=2, default=str))
    return 0


def _cmd_providers(db, args) -> int:
    """Provider status/qualification (read-only, honest states)."""
    from app.services.acquisition.activation import get_activation_state
    from app.services.freshness import registry as registry_svc
    from app.services.provider_qualification import registry as qual_registry

    if args.action == "qualification":
        view = qual_registry.get_registry().describe()
        print(json.dumps(view, indent=2, default=str))
        return 0
    view = registry_svc.registry_view(db)
    competitions = [c.strip() for c in args.competition.split(",")
                    if c.strip()] or ["EPL", "LA_LIGA", "SERIE_A",
                                      "BUNDESLIGA", "LIGUE_1"]
    out = []
    for entry in view:
        source = entry.get("source", "?")
        item = {"source": source,
                "health": (entry.get("health") or {}).get("state"),
                "activation": {
                    comp: get_activation_state(db, source, comp, args.season or None)
                    for comp in competitions}}
        out.append(item)
        if not args.as_json:
            states = ", ".join(f"{c}={s}" for c, s in item["activation"].items())
            print(f"{source}: health={item['health']} | {states}")
    if args.as_json:
        print(json.dumps(out, indent=2, default=str))
    return 0


def _cmd_prediction(db, args) -> int:
    """Prediction execution status (read-only aggregates)."""
    from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot

    total = db.query(PreMatchPredictionSnapshot).count()
    by_state = {}
    for state, in db.query(
            PreMatchPredictionSnapshot.readiness_state).distinct().all():
        by_state[state or "unknown"] = db.query(
            PreMatchPredictionSnapshot).filter_by(
            readiness_state=state).count()
    latest = db.query(PreMatchPredictionSnapshot).order_by(
        PreMatchPredictionSnapshot.id.desc()).first()
    view = {"prediction_count": total, "by_readiness_state": by_state,
            "latest_prediction_id": latest.prediction_id if latest else None,
            "latest_created_at": str(latest.created_at) if latest else None}
    print(json.dumps(view, indent=2, default=str))
    return 0


def _cmd_evaluation(db, args) -> int:
    """Evaluation status (read-only aggregates)."""
    from app.db.models.evaluation_records import PredictionEvaluationRecord
    from app.services.production_monitoring.data_quality import outcome_gaps

    total = db.query(PredictionEvaluationRecord).count()
    gaps = outcome_gaps(db)
    view = {"evaluation_count": total,
            "finished_predicted": gaps["finished_predicted_count"],
            "missing_outcomes": gaps["missing_outcomes"],
            "evaluation_state": gaps["state"]}
    print(json.dumps(view, indent=2, default=str))
    return 0


def _cmd_monitoring(db, args) -> int:
    """Monitoring summary (read-only, same paths as the API)."""
    from app.services.production_monitoring import (
        coverage_funnel,
        data_quality_report,
        detect_anomalies,
        performance_overview,
    )

    perf = performance_overview(db)
    cov = coverage_funnel(db)
    quality = data_quality_report(db)
    anomalies = detect_anomalies(db)
    view = {"evaluation_count": perf["metrics"].get("sample_count", 0),
            "accuracy_1x2": perf["metrics"].get("accuracy_1x2"),
            "log_loss_1x2": perf["metrics"].get("log_loss_1x2"),
            "brier_1x2": perf["metrics"].get("brier_1x2"),
            "coverage": {
                "eligible": cov["eligible_count"],
                "ready": cov["ready_count"],
                "predicted": cov["predicted_count"],
                "completed": cov["completed_count"],
                "evaluated": cov["evaluated_count"]},
            "data_quality_state": quality.get("state"),
            "anomaly_count": anomalies.get("anomaly_count", 0)}
    print(json.dumps(view, indent=2, default=str))
    return 0


def _cmd_acquisition(db, args) -> int:
    """Acquisition status (read-only, same paths as scheduled jobs)."""
    from app.services.acquisition.readiness_gate import (
        get_current_season_prematch_summary,
    )
    from app.services.scheduler import scheduler_status

    summary = get_current_season_prematch_summary(db)
    sched = scheduler_status(db)
    view = {"season": summary.get("season"),
            "operational_mode": summary.get("operational_mode"),
            "provider_state": summary.get("provider_state"),
            "fixture_count": summary.get("fixture_count"),
            "prediction_ready_count": summary.get("prediction_ready_count"),
            "blocked_count": summary.get("blocked_count"),
            "recent_runs": len(sched.get("recent_runs", []))}
    print(json.dumps(view, indent=2, default=str))
    return 0


def _cmd_jobs(db, args) -> int:
    from app.services.scheduler import (
        ALL_JOB_TYPES, get_job_config, recent_records, find_due_jobs,
        run_job, run_job_manual, run_due, check_alerts, detect_anomalies,
        operational_summary, scheduler_status,
    )
    from app.services.scheduler.store import get_record, cleanup_expired_locks
    from app.services.scheduler.config import ALL_JOB_TYPES

    action = args.action
    as_json = args.as_json

    if action == "list":
        records = recent_records(db, limit=20)
        if as_json:
            print(json.dumps([{
                "job_id": r.job_id, "job_type": r.job_type,
                "competition": r.competition, "status": r.status,
                "trigger": r.trigger, "completed_at": str(r.completed_at),
            } for r in records], indent=2, default=str))
            return 0
        if not records:
            print("no job records")
            return 0
        print(f"{'job_id':<30} {'type':<20} {'comp':<12} {'status':<12} {'trigger':<10}")
        print("-" * 84)
        for r in records:
            print(f"{r.job_id:<30} {r.job_type:<20} {r.competition:<12} "
                  f"{r.status:<12} {r.trigger:<10}")
        return 0

    if action == "status":
        status = scheduler_status(db)
        if as_json:
            print(json.dumps(status, indent=2, default=str))
            return 0
        print(f"Scheduler status as of {status['as_of']}")
        print(f"\n--- Sources ---")
        for source, info in status.get("sources", {}).items():
            health = info.get("health", {})
            print(f"  {source}: qual={info['qualification']} "
                  f"health={health.get('state', '?')}")
        print(f"\n--- Jobs ---")
        for job_type, info in status.get("jobs", {}).items():
            last = info.get("last_run")
            last_str = f"last={last['status']}" if last else "last=never"
            print(f"  {job_type}: enabled={info['enabled']} "
                  f"interval={info['interval_seconds']}s {last_str}")
        print(f"\n--- Locks ---")
        locks = status.get("locks", {})
        print(f"  active={locks.get('active', 0)} stale={locks.get('stale', 0)}")
        return 0

    if action == "run":
        job_type = args.job_type
        if job_type is None:
            print("usage: tacticx jobs run <job_type> [--competition X] [--dry-run]")
            return 1
        if job_type not in ALL_JOB_TYPES:
            print(f"unknown job type: {job_type!r} (valid: {', '.join(ALL_JOB_TYPES)})")
            return 1
        result = run_job_manual(
            db, job_type,
            competition=args.competition or "",
            season=args.season or "",
            source=args.source or "",
            dry_run=args.dry_run)
        if as_json:
            print(json.dumps(result, indent=2, default=str))
            return 0
        status = result.get("status", "?")
        label = "dry-run" if args.dry_run else "executed"
        print(f"[{label}] {job_type} -> {status}")
        if result.get("error_message"):
            print(f"  error: {result['error_message']}")
        return 0 if status in ("succeeded", "partial", "dry_run", "skipped") else 1

    if action == "run-due":
        if getattr(args, "loop", False):
            import time

            from app.config import get_settings

            interval = getattr(args, "interval_seconds", 0) or \
                get_settings().SCHEDULER_LOOP_INTERVAL_SECONDS
            cycle = 0
            print(f"scheduler loop started (interval={interval}s) — Ctrl-C to stop")
            try:
                while True:
                    cycle += 1
                    results = run_due(db, dry_run=args.dry_run)
                    print(f"[cycle {cycle}] executed={len(results)}")
                    for r in results:
                        print(f"  {r.get('job_type', '?')} "
                              f"({r.get('competition', '')}) -> "
                              f"{r.get('status', '?')}")
                    time.sleep(interval)
            except KeyboardInterrupt:
                print(f"scheduler loop stopped after {cycle} cycles")
                return 0
        results = run_due(db, dry_run=args.dry_run)
        if as_json:
            print(json.dumps(results, indent=2, default=str))
            return 0
        if not results:
            print("no jobs due")
            return 0
        for r in results:
            label = "dry-run" if args.dry_run else "executed"
            print(f"[{label}] {r.get('job_type', '?')} "
                  f"({r.get('competition', '')}) -> {r.get('status', '?')}")
        return 0

    if action == "alerts":
        alerts = check_alerts(db)
        if as_json:
            print(json.dumps(alerts, indent=2, default=str))
            return 0
        if not alerts:
            print("no alerts")
            return 0
        for a in alerts:
            print(f"  [{a['severity']}] {a['condition']}: {a.get('detail', '')}")
        return 0

    if action == "anomalies":
        anomalies = detect_anomalies(db)
        if as_json:
            print(json.dumps(anomalies, indent=2, default=str))
            return 0
        if not anomalies:
            print("no anomalies detected")
            return 0
        for a in anomalies:
            print(f"  [{a['type']}] {a.get('detail', '')}")
        return 0

    if action == "dashboard":
        summary = operational_summary(db)
        if as_json:
            print(json.dumps(summary, indent=2, default=str))
            return 0
        print(f"Operational summary as of {summary['as_of']}")
        print(f"  alerts: {summary['alert_count']}")
        print(f"  anomalies: {summary['anomaly_count']}")
        print(f"  active locks: {summary['active_locks']}")
        return 0

    print(f"unknown action: {action}")
    return 1


def _cmd_current_season(db, args) -> int:
    from app.services.acquisition.activation import (
        activate_current_season,
        can_activate_current_season,
        get_activation_state,
    )
    from app.services.acquisition.current_season import (
        current_canonical_season,
        get_current_season_readiness_report,
    )

    action = args.action
    as_json = args.as_json
    season = args.season or current_canonical_season()

    if action == "readiness":
        report = get_current_season_readiness_report(db, season=season)
        if as_json:
            print(json.dumps(report, indent=2, default=str))
            return 0
        print(f"Current Season Readiness [{season}] (as of {report.get('as_of', '')})")
        print(f"{'Competition':<18} {'Provider':<16} {'Fixtures':<10} {'Qual Status':<14} {'Activation':<14} {'Eligible':<10} {'Blocking Reasons'}")
        print("-" * 105)
        for item in report.get("items", []):
            fix_str = str(item.get("fixture_count")) if item.get("fixture_count") is not None else "N/A"
            reasons = "; ".join(item.get("blocking_reasons", [])) or "-"
            print(f"{item.get('competition', ''):<18} "
                  f"{item.get('provider', ''):<16} "
                  f"{fix_str:<10} "
                  f"{item.get('qualification_level', ''):<14} "
                  f"{item.get('activation_status', ''):<14} "
                  f"{'YES' if item.get('eligible_for_activation') else 'NO':<10} "
                  f"{reasons}")
        summary = report.get("summary", {})
        print("-" * 105)
        print(f"Total: {summary.get('total_competitions', 0)} | "
              f"Active: {summary.get('active_competitions', 0)} | "
              f"Qualified: {summary.get('qualified_competitions', 0)} | "
              f"Unavailable: {summary.get('unavailable_competitions', 0)}")
        return 0

    if action == "can-activate":
        source = args.source or "api_football"
        competition = args.competition or "EPL"
        decision = can_activate_current_season(source, competition, season, db)
        if as_json:
            print(json.dumps(decision, indent=2, default=str))
            return 0 if decision.get("eligible") else 1
        print(f"Activation Eligibility Check: source={source} comp={competition} season={season}")
        print(f"  Eligible: {'YES' if decision.get('eligible') else 'NO'}")
        if decision.get("reasons"):
            print("  Blocking reasons:")
            for r in decision["reasons"]:
                print(f"    - {r}")
        if decision.get("warnings"):
            print("  Warnings:")
            for w in decision["warnings"]:
                print(f"    - {w}")
        return 0 if decision.get("eligible") else 1

    if action == "activate":
        source = args.source or "api_football"
        competition = args.competition or "EPL"
        result = activate_current_season(
            db,
            source=source,
            competition=competition,
            season=season,
            actor=args.actor or "cli_operator",
            reason=args.reason or "cli activation",
            force=args.force,
        )
        if as_json:
            print(json.dumps(result, indent=2, default=str))
            return 0 if result.get("success") else 1
        if result.get("success"):
            print(f"SUCCESS: Activated {source} for {competition} {season}")
            print(f"  Activation record ID: {result.get('activation_id')}")
            return 0
        else:
            print(f"FAILED: Cannot activate {source} for {competition} {season}")
            for r in result.get("reasons", []):
                print(f"  - {r}")
            return 1

    print(f"unknown action: {action}")
    return 1


def _cmd_evidence(db, args) -> int:
    """Real-world performance evidence (read-only + explicit snapshots)."""
    from app.services.evidence import (
        build_cohort,
        compute_evidence,
        generate_snapshot,
        get_snapshot,
        snapshot_to_dict,
    )

    action = args.action
    if action == "status":
        from app.db.models.evaluation_records import PredictionEvaluationRecord
        from app.db.models.governance import ShadowEvaluationRecord

        champion_evals = db.query(PredictionEvaluationRecord).count()
        challenger_evals = db.query(ShadowEvaluationRecord).count()
        if champion_evals == 0 and challenger_evals == 0:
            state = "NO_DATA"
        elif challenger_evals == 0:
            state = "INSUFFICIENT_REAL_DATA"
        else:
            state = "AVAILABLE"
        print(json.dumps({
            "state": state,
            "champion_evaluations": champion_evals,
            "challenger_evaluations": challenger_evals,
            "paired_observations": challenger_evals,
            "real_shadow_predictions": challenger_evals,
            "synthetic_observations": 0}, indent=2))
        return 0
    if action == "cohorts":
        from app.db.models.evidence import EvidenceCohort

        rows = db.query(EvidenceCohort).order_by(
            EvidenceCohort.id.desc()).limit(50).all()
        print(json.dumps(
            [{"cohort_id": r.cohort_id, "cohort_hash": r.cohort_hash}
             for r in rows], indent=2))
        return 0
    if action == "generate":
        row = build_cohort(
            db, challenger_artifact_id=args.challenger or None,
            competitions=args.competition.split(",")
            if args.competition else None)
        print(json.dumps(
            generate_snapshot(db, row.cohort_id), indent=2, default=str))
        return 0
    if action == "compare":
        if not args.challenger:
            print("pass --challenger <challenger_artifact_id>")
            return 1
        row = build_cohort(db, challenger_artifact_id=args.challenger,
                           persist=False)
        print(json.dumps(compute_evidence(db, row), indent=2, default=str))
        return 0
    if action == "breakdown":
        if not args.challenger:
            print("pass --challenger <challenger_artifact_id>")
            return 1
        from app.services.production_monitoring.breakdown import breakdown

        print(json.dumps(breakdown(db, by="competition_season"),
                         indent=2, default=str))
        return 0
    if action == "show":
        if not args.snapshot:
            print("pass --snapshot <snapshot_id>")
            return 1
        print(json.dumps(snapshot_to_dict(get_snapshot(db, args.snapshot)),
                         indent=2, default=str))
        return 0
    if action == "refresh":
        row = build_cohort(db, challenger_artifact_id=args.challenger or None)
        print(json.dumps(generate_snapshot(db, row.cohort_id),
                         indent=2, default=str))
        return 0
    print(f"unknown evidence action: {action}")
    return 1


def _cmd_shadow(db, args) -> int:
    """Champion/challenger shadow operations (read-only + explicit runs)."""
    from app.services.shadow_execution import (
        ShadowExecutionError,
        ShadowIneligible,
        evaluate_shadow_pair,
        execute_shadow,
        find_eligible_matches,
        shadow_comparison,
        shadow_summary,
        validate_shadow_pair,
    )
    from app.services.shadow_execution.evaluation import ShadowEvaluationError

    action = args.action
    if action == "status":
        print(json.dumps(shadow_summary(db), indent=2, default=str))
        return 0
    if action == "challengers":
        print(json.dumps(
            shadow_summary(db)["by_challenger"], indent=2, default=str))
        return 0
    if action == "matches":
        print(json.dumps(
            find_eligible_matches(db, competition=args.competition or None),
            indent=2, default=str))
        return 0
    if action == "evaluate":
        if not args.shadow:
            print("pass --shadow <shadow_id>")
            return 1
        try:
            print(json.dumps(
                evaluate_shadow_pair(db, args.shadow),
                indent=2, default=str))
            return 0
        except ShadowEvaluationError as exc:
            print(f"shadow evaluation failed: {exc.reason}")
            return 1
    if action == "compare":
        if not args.challenger:
            print("pass --challenger <challenger_artifact_id>")
            return 1
        print(json.dumps(
            shadow_comparison(db, args.challenger),
            indent=2, default=str))
        return 0
    if action == "run":
        if not args.match or not args.challenger:
            print("pass --match <match_id> --challenger <artifact_id>")
            return 1
        try:
            print(json.dumps(
                execute_shadow(db, args.match, args.challenger),
                indent=2, default=str))
            return 0
        except (ShadowExecutionError, ShadowIneligible) as exc:
            print(f"shadow execution failed: {exc.reason}")
            return 1
    if action == "audit":
        if not args.shadow:
            print("pass --shadow <shadow_id>")
            return 1
        print(json.dumps(
            validate_shadow_pair(db, args.shadow),
            indent=2, default=str))
        return 0
    print(f"unknown shadow action: {action}")
    return 1


def _cmd_pre_match(db, args) -> int:
    from app.services.acquisition.readiness_gate import (
        evaluate_pre_match_readiness,
        generate_readiness_certificate,
        get_current_season_prematch_summary,
    )

    action = args.action
    as_json = args.as_json

    if action == "audit":
        if args.match_id is None:
            print("error: match_id is required for audit action")
            return 1

        cutoff_dt = None
        if args.cutoff:
            try:
                cutoff_dt = datetime.fromisoformat(args.cutoff.replace("Z", "+00:00"))
            except ValueError:
                print("error: cutoff must be valid ISO-8601 timestamp")
                return 1

        mode = args.mode or "PRE_MATCH"
        if args.persist:
            cert = generate_readiness_certificate(db, args.match_id, cutoff=cutoff_dt, mode=mode)
            evaluation = evaluate_pre_match_readiness(db, args.match_id, cutoff=cutoff_dt, mode=mode)
            evaluation["certificate"] = {
                "certificate_id": cert.certificate_id,
                "certificate_version": cert.certificate_version,
                "payload_hash": cert.payload_hash,
                "supersedes_certificate_id": cert.supersedes_certificate_id,
                "created_at": cert.created_at.isoformat() if cert.created_at else None,
            }
        else:
            evaluation = evaluate_pre_match_readiness(db, args.match_id, cutoff=cutoff_dt, mode=mode)

        if as_json:
            print(json.dumps(evaluation, indent=2, default=str))
            return 0 if evaluation["eligible"] else 1

        print(f"Pre-Match Readiness Audit: match={evaluation['match_id']} [{evaluation['competition']}]")
        print(f"  Kickoff: {evaluation['kickoff_at']} | Cutoff: {evaluation['cutoff']} (mode={evaluation['mode']})")
        print(f"  State:   {evaluation['readiness_state']} (Eligible: {'YES' if evaluation['eligible'] else 'NO'})")
        gv = evaluation["gate_verdicts"]
        print(f"  Gate 1 (Structural):     {'PASS' if gv['gate1_structural']['passed'] else 'FAIL'}")
        print(f"  Gate 2 (Reconciliation): {'PASS' if gv['gate2_reconciliation']['passed'] else 'FAIL'}")
        print(f"  Gate 3 (Temporal):       {'PASS' if gv['gate3_temporal']['passed'] else 'FAIL'}")
        print(f"  Gate 4 (Features):       {gv['gate4_features']['status'].upper()}")
        if evaluation["blocking_reasons"]:
            print("  Blocking Reasons:")
            for br in evaluation["blocking_reasons"]:
                print(f"    - {br}")
        if evaluation["warnings"]:
            print("  Warnings:")
            for w in evaluation["warnings"]:
                print(f"    - {w}")
        if "certificate" in evaluation:
            c = evaluation["certificate"]
            print(f"  Certificate ID: {c['certificate_id']}")
            print(f"  Payload Hash:   {c['payload_hash']}")
            if c.get("supersedes_certificate_id"):
                print(f"  Supersedes:     {c['supersedes_certificate_id']}")

        return 0 if evaluation["eligible"] else 1

    if action == "summary":
        season = args.season or "current"
        summary = get_current_season_prematch_summary(db, season=season)
        if as_json:
            print(json.dumps(summary, indent=2, default=str))
            return 0

        print(f"Current Season Pre-Match Readiness Summary [{summary['season']}]")
        print(f"  Operational Mode:       {summary['operational_mode']}")
        print(f"  Provider State:         {summary['provider_state']}")
        print(f"  Total Fixtures:         {summary['fixture_count']}")
        print(f"  Reconciled Fixtures:    {summary['reconciled_count']}")
        print(f"  Temporally Valid:       {summary['temporally_valid_count']}")
        print(f"  Quality Passed:         {summary['quality_passed_count']}")
        print(f"  Prediction Ready:       {summary['prediction_ready_count']}")
        print(f"  Ready Degraded:         {summary['ready_degraded_count']}")
        print(f"  Blocked:                {summary['blocked_count']}")
        if summary.get("blocking_reasons"):
            print("  Blocking Reasons Breakdown:")
            for reason, count in summary["blocking_reasons"].items():
                print(f"    - {reason}: {count}")
        return 0

    print(f"unknown action: {action}")
    return 1


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

    p = sub.add_parser("intelligence", help="Prediction intelligence summary")
    _common(p)
    p.add_argument("--analogues", action="store_true")
    p.add_argument("--scenarios", action="store_true")
    p.add_argument("--mirofish", action="store_true",
                   help="also run the isolated MiroFish scenario layer")
    p.add_argument("--scenario", default="baseline",
                   help="whitelisted MiroFish scenario ID")
    p.add_argument("--match-intelligence", action="store_true",
                   help="emit the canonical match_intelligence_v1 document")
    p.add_argument("--compact", action="store_true",
                   help="compact presentation mode")

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

    p = sub.add_parser("acquire", help="Current-season acquisition job")
    p.add_argument("--season", default="current",
                   help="canonical season (e.g. 2026/27) or 'current'")
    p.add_argument("--competition", default=None,
                   help="league code (default: all five target leagues)")
    p.add_argument("--source", default=None,
                   help="source name (default: all configured sources)")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.add_argument("--explain", action="store_true",
                   help="show acquisition plan: source selection, qualification "
                        "reasons, coverage, freshness, identity results")

    p = sub.add_parser("sources", help="Source status/coverage/freshness/validation")
    p.add_argument("action", choices=["status", "coverage", "freshness", "validate",
                                      "list", "qualify"],
                   nargs="?", default="status")
    p.add_argument("--league", default=None)
    p.add_argument("--competition", default=None,
                   help="league code (defaults to --league when set)")
    p.add_argument("--source", default=None)
    p.add_argument("--season", default="current")
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

    p = sub.add_parser("model", help="Model governance (explicit, human-gated)")
    p.add_argument("action",
                   choices=["registry", "champion", "validate", "validation",
                            "promotion-request", "approve", "reject",
                            "shadow-start", "canary-activate",
                            "production-activate", "rollback", "audit"],
                   nargs="?", default="registry")
    p.add_argument("--artifact", default="")
    p.add_argument("--validation", default="")
    p.add_argument("--request", default="")
    p.add_argument("--experiment", default="")
    p.add_argument("--champion", default="")
    p.add_argument("--expected-champion", default="")
    p.add_argument("--mode", default="SHADOW",
                   choices=["SHADOW", "CANARY", "PRODUCTION"])
    p.add_argument("--actor", default="")
    p.add_argument("--reason", default="")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("jobs", help="Acquisition scheduler jobs")
    p.add_argument("action",
                   choices=["list", "status", "run", "run-due",
                            "alerts", "anomalies", "dashboard"],
                   nargs="?", default="status")
    p.add_argument("job_type", nargs="?", default=None,
                   help="job type for 'run' action")
    p.add_argument("--competition", default="")
    p.add_argument("--season", default="")
    p.add_argument("--source", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--loop", action="store_true",
                   help="run-due continuously until interrupted")
    p.add_argument("--interval-seconds", type=int, default=0,
                   help="loop interval override (0 = SCHEDULER_LOOP_INTERVAL_SECONDS)")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("current-season", help="Controlled current-season data activation")
    p.add_argument("action",
                   choices=["readiness", "can-activate", "activate"],
                   nargs="?", default="readiness")
    p.add_argument("--competition", default="", help="competition code (e.g. EPL)")
    p.add_argument("--season", default="", help="canonical season (e.g. 2026/27)")
    p.add_argument("--source", default="", help="provider name (e.g. api_football)")
    p.add_argument("--actor", default="", help="audit actor name")
    p.add_argument("--reason", default="", help="audit activation reason")
    p.add_argument("--force", action="store_true", help="force activation override")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("pre-match", help="Pre-match data quality & readiness gate")
    p.add_argument("action", choices=["audit", "summary"], nargs="?", default="summary")
    p.add_argument("match_id", type=int, nargs="?", default=None, help="match ID for audit")
    p.add_argument("--cutoff", default=None, help="ISO cutoff (default: now/kickoff)")
    p.add_argument("--mode", default="PRE_MATCH", choices=["PRE_MATCH", "POST_MATCH", "EVALUATION"])
    p.add_argument("--persist", action="store_true", help="persist immutable readiness certificate")
    p.add_argument("--season", default="current", help="season code or 'current'")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("system", help="Local production system status (read-only)")
    p.add_argument("action", choices=["status"], nargs="?", default="status")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("providers", help="Provider status & qualification (read-only)")
    p.add_argument("action", choices=["status", "qualification"],
                   nargs="?", default="status")
    p.add_argument("--competition", default="",
                   help="comma-separated competition codes (default: big five)")
    p.add_argument("--season", default="")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("prediction", help="Prediction execution status (read-only)")
    p.add_argument("action", choices=["status"], nargs="?", default="status")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("evaluation", help="Evaluation status (read-only)")
    p.add_argument("action", choices=["status"], nargs="?", default="status")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("monitoring", help="Monitoring summary (read-only)")
    p.add_argument("action", choices=["summary"], nargs="?", default="summary")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("acquisition", help="Acquisition status (read-only)")
    p.add_argument("action", choices=["status"], nargs="?", default="status")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("shadow", help="Champion/challenger shadow (read-only + explicit runs)")
    p.add_argument("action",
                   choices=["status", "challengers", "matches", "evaluate",
                            "compare", "run", "audit"],
                   nargs="?", default="status")
    p.add_argument("--match", type=int, default=0)
    p.add_argument("--challenger", default="")
    p.add_argument("--shadow", default="")
    p.add_argument("--competition", default="")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("evidence", help="Real-world performance evidence (read-only + explicit snapshots)")
    p.add_argument("action",
                   choices=["status", "cohorts", "generate", "compare",
                            "breakdown", "show", "refresh"],
                   nargs="?", default="status")
    p.add_argument("--challenger", default="")
    p.add_argument("--snapshot", default="")
    p.add_argument("--competition", default="")
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
        if args.command == "intelligence":
            return _cmd_intelligence(db, args)
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
        if args.command == "acquire":
            return _cmd_acquire(db, args)
        if args.command == "sources":
            return _cmd_sources(db, args)
        if args.command == "data":
            return _cmd_data(db, args)
        if args.command == "research":
            return _cmd_research(db, args)
        if args.command == "model":
            return _cmd_model(db, args)
        if args.command == "jobs":
            return _cmd_jobs(db, args)
        if args.command == "current-season":
            return _cmd_current_season(db, args)
        if args.command == "pre-match":
            return _cmd_pre_match(db, args)
        if args.command == "system":
            return _cmd_system(db, args)
        if args.command == "providers":
            return _cmd_providers(db, args)
        if args.command == "prediction":
            return _cmd_prediction(db, args)
        if args.command == "evaluation":
            return _cmd_evaluation(db, args)
        if args.command == "monitoring":
            return _cmd_monitoring(db, args)
        if args.command == "acquisition":
            return _cmd_acquisition(db, args)
        if args.command == "shadow":
            return _cmd_shadow(db, args)
        if args.command == "evidence":
            return _cmd_evidence(db, args)
        ap.error(f"unknown command: {args.command}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
