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
        ap.error(f"unknown command: {args.command}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
