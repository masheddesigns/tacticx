"""Prediction composer (Phase 6).

Turns a core statistical prediction into complete, explainable, auditable
match intelligence. The composer never trains models and never mutates
source data: it reads a feature snapshot, runs the selected core model,
derives markets from the model's own distribution, and attaches separately
labeled diagnostic layers (uncertainty, disagreement, market context,
explanation, scenarios, analogues, MiroFish).

Default core model is ensemble_v1 (Phase 5 validated default). Selection
follows the Phase 5 availability-based regime policy; any override is
explicit and recorded in provenance.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.services.evaluation.regimes import select_model
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.intelligence import derived
from app.services.intelligence.schemas import (
    CALCULATION_VERSION,
    ComposedPrediction,
    DataQuality,
    DerivedMarkets,
    LayerProvenance,
    MarketContext,
    ModelDisagreement,
    UncertaintySummary,
)
from app.services.predictions.math_utils import MAX_GRID_GOALS
from app.services.predictions.outputs import FullPrediction

DEFAULT_MODEL = "ensemble"
FEATURE_VERSION = "features_v1"
DISAGREEMENT_MEMBERS = ("elo", "poisson", "advanced", "ensemble")


def build_core_model(name: str, seed=None, simulations: int = 10000):
    """Core model factory (mirrors scripts/predict.py; default ensemble_v1)."""
    from app.services.predictions.advanced import AdvancedGoalModel, AdvancedModel
    from app.services.predictions.elo import EloModel
    from app.services.predictions.ensemble import BaselineModel, EnsembleModel
    from app.services.predictions.montecarlo import MonteCarloModel
    from app.services.predictions.poisson import PoissonModel, xg_enhanced_config

    if name == "elo":
        return EloModel()
    if name == "poisson":
        return PoissonModel()
    if name == "poisson-xg":
        return PoissonModel(config=xg_enhanced_config())
    if name == "montecarlo":
        return MonteCarloModel(n_simulations=simulations, random_seed=seed)
    if name == "ensemble":
        return EnsembleModel()
    if name == "baseline":
        return BaselineModel()
    if name == "advanced":
        return AdvancedModel()
    if name == "advanced_goal":
        return AdvancedGoalModel()
    raise ValueError(f"unknown model: {name}")


class PredictionComposer:
    """Compose full match intelligence around an untouched statistical core."""

    def __init__(self, default_model: str = DEFAULT_MODEL,
                 simulations: int = 10000):
        self.default_model = default_model
        self.simulations = simulations

    def _select_model(self, availability: Dict, requested: Optional[str],
                      xg_eligible: bool = False,
                      advanced_fitted: bool = False) -> Dict:
        if requested:
            try:
                build_core_model(requested)
            except ValueError as exc:
                raise ValueError(str(exc))
            return {"model": requested, "reason": "explicit caller request",
                    "policy": False}
        decision = select_model(availability, xg_eligible=xg_eligible,
                                advanced_fitted=advanced_fitted)
        return {"model": {"baseline_v1": "baseline", "poisson_v1-xg": "poisson-xg",
                          "advanced_v1": "advanced",
                          "ensemble_v1": "ensemble"}.get(decision["model"], "ensemble"),
                "reason": decision["reason"], "policy": True}

    def compose(self, db: Session, match_id: int, cutoff: datetime,
                mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                model: Optional[str] = None, seed: Optional[int] = None,
                top_n_scores: int = 16, with_market: bool = True,
                with_disagreement: bool = True) -> ComposedPrediction:
        from app.services.features.engineered import build_feature_snapshot

        match = db.get(Match, match_id)
        if match is None:
            raise ValueError(f"unknown match: {match_id}")
        naive_cutoff = as_naive_utc(cutoff)
        if naive_cutoff is None:
            raise ValueError("cutoff is required")
        try:
            snapshot = build_feature_snapshot(db, match_id, cutoff, mode)
        except ValueError as exc:
            snapshot = {"error": str(exc)}

        from app.services.features.availability import assess_availability

        availability = assess_availability(db, match_id, cutoff, mode)
        selection = self._select_model(
            availability.as_dict(), model,
            xg_eligible=bool(availability.xg))
        core_model = build_core_model(selection["model"], seed=seed,
                                      simulations=self.simulations)
        core: FullPrediction = core_model.predict(db, match_id, cutoff, mode)

        status = "complete"
        if core.status == "insufficient_data":
            status = "insufficient_data"
        elif isinstance(snapshot, dict) and snapshot.get("error"):
            status = "partial"

        composed = ComposedPrediction(
            match={"match_id": match_id,
                   "home_team_id": match.home_team_id,
                   "away_team_id": match.away_team_id,
                   "league_id": match.league_id,
                   "kickoff_at": str(match.kickoff_at)},
            cutoff=str(naive_cutoff),
            model={"name": core.model_name, "version": core.model_version,
                   "requested": model or self.default_model,
                   "selection": selection,
                   "feature_version": FEATURE_VERSION},
            status=status,
            core_prediction=core.model_dump(),
            provenance=LayerProvenance(
                source="prediction_composer", model_version=core.model_version,
                cutoff=str(naive_cutoff), temporal_mode=mode.value, status=status),
        )

        home, draw, away = (core.home_win_probability, core.draw_probability,
                            core.away_win_probability)
        check_1x2 = derived.validate_1x2(home, draw, away)
        composed.probabilities = {"home": home, "draw": draw, "away": away,
                                  "validation": check_1x2}
        composed.goals = {"home_lambda": core.expected_home_goals,
                          "away_lambda": core.expected_away_goals,
                          "total_lambda": core.expected_total_goals}
        composed.score_distribution = dict(core.score_probabilities or {})

        composed.markets = self._derive_markets(core, top_n_scores)
        composed.uncertainty = self._summarize_uncertainty(core, availability)
        composed.data_quality = self._summarize_data_quality(
            core, availability, mode, snapshot, with_market=False)
        if with_disagreement:
            composed.model_disagreement = self.disagreement(
                db, match_id, cutoff, mode, seed=seed)
        if with_market:
            composed.market = self.market_context(db, match_id, cutoff, core)
            composed.data_quality.market_available = (
                composed.market.status == "ok")

        from app.services.intelligence.explanation import explain

        composed.explanation = explain(db, match_id, cutoff, mode, core,
                                       snapshot if isinstance(snapshot, dict) else {},
                                       composed.model_disagreement)
        return composed

    def _derive_markets(self, core: FullPrediction, top_n: int) -> DerivedMarkets:
        validation: Dict[str, Dict] = {}
        grid = dict(core.score_probabilities or {})
        if grid:
            validation["score_grid"] = derived.validate_distribution("score_grid", grid)
        lam_h, lam_w = core.expected_home_goals, core.expected_away_goals
        dist = derived.goal_distributions(lam_h, lam_w) \
            if lam_h is not None and lam_w is not None else {"status": "unavailable"}
        joint = dist.get("joint", {}) if dist.get("status") == "ok" else grid
        totals = derived.totals_from_joint(joint) if joint else {"status": "unavailable"}
        btts = derived.btts_from_joint(joint) if joint else {"status": "unavailable"}
        home, draw, away = (core.home_win_probability, core.draw_probability,
                            core.away_win_probability)
        dc = derived.double_chance(home, draw, away)
        team = derived.team_totals(lam_h, lam_w)
        scores = derived.correct_scores(joint, top_n=top_n) if joint else {"status": "unavailable"}
        if joint:
            validation["totals_consistency"] = {"consistent": totals.get("consistent", False),
                                                "checks": totals.get("checks", [])}
            validation["double_chance"] = {"consistent": dc.get("consistent", False),
                                           "checks": dc.get("checks", [])}
        return DerivedMarkets(
            totals=totals, btts=btts, double_chance=dc, team_totals=team,
            correct_scores=scores, goal_distributions=dist, validation=validation,
            provenance=LayerProvenance(
                source="derived_markets", model_version=core.model_version,
                cutoff=str(core.prediction_cutoff),
                temporal_mode=core.temporal_mode),
        )

    def _summarize_uncertainty(self, core: FullPrediction,
                               availability) -> UncertaintySummary:
        from app.services.predictions.advanced import prediction_entropy

        home, draw, away = (core.home_win_probability, core.draw_probability,
                            core.away_win_probability)
        ordered = sorted((home, draw, away), reverse=True)
        return UncertaintySummary(
            predictive_entropy=round(prediction_entropy(home, draw, away), 6),
            top_probability=round(ordered[0], 6),
            probability_margin=round(ordered[0] - ordered[1], 6),
            data_completeness={
                "home_history": availability.home_history,
                "away_history": availability.away_history,
                "home_xg_history": availability.home_xg_history,
                "away_xg_history": availability.away_xg_history,
                "xg_available": bool(availability.xg),
            },
        )

    def _summarize_data_quality(self, core: FullPrediction, availability,
                                mode: TemporalMode, snapshot: Dict,
                                with_market: bool = False) -> DataQuality:
        estimated: List[str] = []
        if mode == TemporalMode.HISTORICAL_ESTIMATED:
            estimated = [n for n in ("xg", "shots", "corners", "cards")
                         if (core.feature_availability or {}).get(n)]
        leaves = self._count_snapshot_leaves(snapshot) if isinstance(snapshot, dict) else (0, 0)
        return DataQuality(
            feature_count=leaves[0] + leaves[1],
            available_feature_count=leaves[0],
            missing_feature_count=leaves[1],
            strict_mode=(mode == TemporalMode.STRICT_PREMATCH),
            estimated_fields=estimated,
            xg_available=bool(availability.xg),
            event_data_available=bool(availability.events),
            lineup_data_available=bool(availability.lineups),
            market_available=with_market,
        )

    def _count_snapshot_leaves(self, snapshot: Dict) -> tuple:
        available = missing = 0

        def walk(node):
            nonlocal available, missing
            if isinstance(node, dict):
                if "available" in node and "value" in node:
                    if node.get("available"):
                        available += 1
                    else:
                        missing += 1
                    return
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(snapshot)
        return available, missing

    def disagreement(self, db: Session, match_id: int, cutoff: datetime,
                     mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
                     seed: Optional[int] = None,
                     members: tuple = DISAGREEMENT_MEMBERS) -> ModelDisagreement:
        """1X2 per member model with mean/std/min/max/range per outcome."""
        member_probs: Dict[str, Dict] = {}
        for name in members:
            try:
                model = build_core_model(name, seed=seed,
                                         simulations=self.simulations)
            except ValueError:
                member_probs[name] = {"status": "unknown_model"}
                continue
            try:
                pred = model.predict(db, match_id, cutoff, mode)
            except Exception as exc:
                member_probs[name] = {"status": "failed", "error": str(exc)[:200]}
                continue
            if pred.status != "valid":
                member_probs[name] = {"status": pred.status,
                                      "notes": pred.data_quality[:2]}
                continue
            member_probs[name] = {"status": "valid",
                                  "version": pred.model_version,
                                  "home": pred.home_win_probability,
                                  "draw": pred.draw_probability,
                                  "away": pred.away_win_probability}
        per_outcome = {}
        for outcome in ("home", "draw", "away"):
            values = [m[outcome] for m in member_probs.values()
                      if m.get("status") == "valid"]
            if not values:
                per_outcome[outcome] = {"status": "no_valid_members"}
                continue
            mean = sum(values) / len(values)
            var = sum((v - mean) ** 2 for v in values) / len(values)
            per_outcome[outcome] = {
                "mean": round(mean, 6), "std": round(var ** 0.5, 6),
                "min": round(min(values), 6), "max": round(max(values), 6),
                "range": round(max(values) - min(values), 6),
                "n_members": len(values),
                "members": sorted(m for m, v in member_probs.items()
                                  if v.get("status") == "valid"),
            }
        return ModelDisagreement(members=member_probs, per_outcome=per_outcome)

    def market_context(self, db: Session, match_id: int, cutoff: datetime,
                       core: FullPrediction) -> MarketContext:
        """Pre-cutoff market state only. Closing snapshots are excluded from
        consensus (flagged when present); closing_state() is never consulted
        for a pre-match prediction."""
        from app.services.market.compare import compare as compare_market
        from app.services.market.consensus import consensus
        from app.services.market.probabilities import (
            market_completeness,
            no_vig_probabilities,
        )
        from app.services.market.repository import snapshots_before

        try:
            snaps = snapshots_before(db, match_id, cutoff, "h2h")
        except Exception as exc:
            return MarketContext(status="unavailable",
                                 consensus={"error": str(exc)[:200]})
        # Latest NON-CLOSING snapshot per bookmaker. Closing lines are
        # excluded even when timestamped pre-cutoff: they concentrate
        # close-time information and are a benchmark, not context.
        # (Closing rule mirrors repository._is_closing: C-suffixed source prefix.)
        latest: Dict = {}
        closing_present = False
        for snap in snaps:
            market_id = snap.source_market_id or ""
            is_closing = (":" in market_id and len(market_id.split(":", 1)[0]) > 1
                          and market_id.split(":", 1)[0].endswith("C"))
            if is_closing:
                closing_present = True
                continue
            key = snap.bookmaker_id
            if key not in latest or (snap.timestamp, snap.id) >= (
                    latest[key].timestamp, latest[key].id):
                latest[key] = snap
        from app.db.models.odds import Bookmaker, OddsSelection

        per_book = {}
        book_names = []
        partial_books = 0
        for bookmaker_id, snap in latest.items():
            rows = db.query(OddsSelection).filter_by(snapshot_id=snap.id).all()
            selections = {r.selection: {"price": r.odds, "point": r.point}
                          for r in rows if r.selection}
            if market_completeness("h2h", list(selections)) != "complete":
                # Partial books cannot form a 1X2 consensus: normalizing them
                # would fabricate the missing selection's price.
                partial_books += 1
                continue
            prices = {sel: det["price"] for sel, det in selections.items()
                      if det.get("price")}
            if len(prices) < 3:
                partial_books += 1
                continue
            probs, _ = no_vig_probabilities(prices)
            book = db.get(Bookmaker, bookmaker_id) if bookmaker_id else None
            name = book.name if book and book.name else str(bookmaker_id)
            book_names.append(name)
            if probs:
                per_book[name] = probs
        if not per_book:
            return MarketContext(status="unavailable", consensus={
                "reason": "no pre-cutoff non-closing complete books",
                "partial_books_excluded": partial_books,
                "closing_snapshots_present": closing_present,
                "timestamp": str(max((s.timestamp for s in snaps), default=None))})
        agreed = consensus(per_book)
        values = agreed.get("values", {})
        mapping = {"home_win": "home", "draw": "draw", "away_win": "away",
                   "home": "home", "away": "away"}
        consensus_1x2 = {mapped: values[k] for k, mapped in mapping.items() if k in values}
        model_probs = {"home": core.home_win_probability,
                       "draw": core.draw_probability, "away": core.away_win_probability}
        comparison = compare_market(model_probs, consensus_1x2) if len(consensus_1x2) == 3 \
            else {"status": "incomplete_consensus"}
        return MarketContext(
            status="ok" if len(consensus_1x2) == 3 else "partial",
            consensus={"values": consensus_1x2, "detail": agreed,
                       "closing_snapshots_excluded": closing_present,
                       "partial_books_excluded": partial_books},
            timestamp=str(max((s.timestamp for s in snaps), default=None)),
            bookmakers=sorted(book_names),
            model_market_difference=comparison,
            overround=None,
        )
