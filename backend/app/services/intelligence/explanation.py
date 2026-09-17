"""Prediction explanation service (Phase 6).

Every statement is generated from actual feature values, model internals or
availability records. Language discipline: "receives a higher model
probability partly because ..." — never "will win because ...". Unsupported
causal claims are not generated; missing inputs are reported as missing,
never filled.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.features.temporal import TemporalMode
from app.services.intelligence.schemas import CALCULATION_VERSION, Explanation, LayerProvenance
from app.services.predictions.outputs import FullPrediction


def _pct(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def explain(db: Session, match_id: int, cutoff: datetime,
            mode: TemporalMode, core: FullPrediction, snapshot: Dict,
            disagreement=None) -> Explanation:
    """Build a factual explanation for one core prediction."""
    from app.db.models.core import Match, Team

    match = db.get(Match, match_id)
    home_name, away_name = "home team", "away team"
    if match is not None:
        home = db.get(Team, match.home_team_id) if match.home_team_id else None
        away = db.get(Team, match.away_team_id) if match.away_team_id else None
        home_name = (home.name if home and home.name else home_name)
        away_name = (away.name if away and away.name else away_name)

    home, draw, away = (core.home_win_probability, core.draw_probability,
                        core.away_win_probability)
    ordered = sorted((("home", home), ("draw", draw), ("away", away)),
                     key=lambda kv: kv[1], reverse=True)
    fav_label = {"home": home_name, "draw": "a draw", "away": away_name}[ordered[0][0]]
    headline = (
        f"The {core.model_version} model assigns {fav_label} the highest "
        f"probability ({_pct(ordered[0][1])}; H={_pct(home)} D={_pct(draw)} "
        f"A={_pct(away)}). These are statistical estimates with uncertainty, "
        f"not certainties."
    )

    factors: List[Dict] = []
    elo_block = _explain_elo(db, match_id, cutoff, mode, home_name, away_name)
    factors.extend(elo_block.pop("factors", []))
    poisson_block = _explain_poisson(db, match_id, cutoff, mode, core,
                                     home_name, away_name)
    factors.extend(poisson_block.pop("factors", []))
    xg_block = _explain_xg(core, mode)
    factors.extend(xg_block.pop("factors", []))
    feature_block = _explain_features(core, snapshot)
    factors.extend(feature_block.pop("factors", []))

    margin = ordered[0][1] - ordered[1][1]
    if margin >= 0.25:
        spread_note = "Model outputs are relatively concentrated on one outcome."
    elif margin >= 0.10:
        spread_note = "Model disagreement across outcomes is moderate."
    else:
        spread_note = "Model outputs are spread across outcomes (open match)."
    if disagreement is not None and getattr(disagreement, "per_outcome", None):
        ranges = [v.get("range") for v in disagreement.per_outcome.values()
                  if isinstance(v, dict) and v.get("range") is not None]
        if ranges and max(ranges) > 0.15:
            spread_note += " Member models diverge noticeably on at least one outcome."

    return Explanation(
        headline=headline, factors=factors, elo=elo_block, poisson=poisson_block,
        xg=xg_block, features=feature_block,
        model_disagreement_note=spread_note,
        provenance=LayerProvenance(
            source="prediction_explanation", calculation_version=CALCULATION_VERSION,
            model_version=core.model_version, cutoff=str(core.prediction_cutoff),
            temporal_mode=core.temporal_mode,
            status="ok" if core.status == "valid" else core.status),
    )


def _explain_elo(db: Session, match_id: int, cutoff: datetime, mode: TemporalMode,
                 home_name: str, away_name: str) -> Dict:
    """Elo inputs from the same pre-cutoff history the model uses."""
    from app.services.predictions.elo import EloModel
    from app.services.predictions.math_utils import logistic_expected

    block: Dict = {"factors": []}
    try:
        model = EloModel()
        repo_history = model.ratings_at(db, cutoff, None, mode)
        ratings, n_history = repo_history
    except Exception as exc:
        block["status"] = f"unavailable ({str(exc)[:120]})"
        return block
    from app.db.models.core import Match

    match = db.get(Match, match_id)
    if match is None:
        block["status"] = "unavailable (match missing)"
        return block
    home_r = ratings.get(match.home_team_id, model.config.initial_rating)
    away_r = ratings.get(match.away_team_id, model.config.initial_rating)
    edge = model._home_edge()
    expected = logistic_expected(home_r - away_r + edge)
    block.update({
        "status": "ok",
        "home_elo": round(home_r, 1), "away_elo": round(away_r, 1),
        "elo_difference": round(home_r - away_r, 1),
        "home_advantage_points": edge,
        "expected_home_result": round(expected, 4),
        "history_matches": n_history,
        "method": "logistic(home - away + home_advantage); draw from pre-cutoff "
                  "league empirical rate",
    })
    direction = home_name if home_r >= away_r else away_name
    block["factors"].append({
        "factor": "elo_ratings",
        "statement": (
            f"{direction} receives a higher model probability partly because "
            f"its pre-cutoff Elo rating is higher "
            f"({max(home_r, away_r):.0f} vs {min(home_r, away_r):.0f}, "
            f"{n_history} pre-cutoff matches in rating history)."),
        "source": "elo ratings_at (pre-cutoff finished matches only)",
    })
    return block


def _explain_poisson(db: Session, match_id: int, cutoff: datetime,
                     mode: TemporalMode, core: FullPrediction,
                     home_name: str, away_name: str) -> Dict:
    """Poisson strengths/lambdas where the implementation exposes them."""
    from app.services.predictions.poisson import PoissonModel

    block: Dict = {"factors": []}
    if core.expected_home_goals is None or core.expected_away_goals is None:
        block["status"] = "unavailable (core prediction carries no goal lambdas)"
        block["factors"].append({
            "factor": "goal_rates",
            "statement": "No goal-rate inputs are available for this match; "
                         "goal-based factors are omitted, not estimated.",
            "source": "core prediction lambdas (missing)",
        })
        return block
    try:
        lam_h, lam_a, diag = PoissonModel().estimate_lambdas(db, match_id, cutoff, mode)
    except Exception as exc:
        block = {"status": f"unavailable ({str(exc)[:150]})", "factors": []}
        block["factors"].append({
            "factor": "goal_rates",
            "statement": "Goal-rate inputs could not be reconstructed under the "
                         "same cutoff; goal-based factors are omitted.",
            "source": "poisson estimate_lambdas (failed under cutoff)",
        })
        return block
    block.update({
        "status": "ok",
        "home_lambda": round(lam_h, 3), "away_lambda": round(lam_a, 3),
        "league_avg_home": diag.get("league_avg_home"),
        "league_avg_away": diag.get("league_avg_away"),
        "venue_counts": diag.get("venue_counts"),
        "n_history": diag.get("n_history"),
        "xg_used": diag.get("xg_used", False),
        "method": "venue-split recency-weighted attack/defense vs league averages",
    })
    leader = home_name if lam_h >= lam_a else away_name
    block["factors"].append({
        "factor": "scoring_rates",
        "statement": (
            f"{leader} receives a higher model probability partly because its "
            f"estimated scoring rate is higher "
            f"(home λ={lam_h:.2f}, away λ={lam_a:.2f}, venue-split pre-cutoff "
            f"rates vs league averages H={diag.get('league_avg_home')} "
            f"A={diag.get('league_avg_away')})."),
        "source": "poisson estimate_lambdas (pre-cutoff finished matches only)",
    })
    return block


def _explain_xg(core: FullPrediction, mode: TemporalMode) -> Dict:
    avail = core.feature_availability or {}
    home_n = avail.get("home_xg_history", 0)
    away_n = avail.get("away_xg_history", 0)
    block: Dict = {"factors": []}
    if core.xg_used:
        block.update({"xg_status": "used",
                      "xg_quality": "estimated" if mode == TemporalMode.HISTORICAL_ESTIMATED else "strict",
                      "home_xg_history": home_n, "away_xg_history": away_n})
        block["factors"].append({
            "factor": "expected_goals",
            "statement": "Expected-goals history contributed to the goal estimate "
                         f"(quality: {block['xg_quality']}; histories "
                         f"home={home_n}, away={away_n}).",
            "source": "match_statistics expected_goals rows (mode-eligible only)",
        })
    else:
        block.update({"xg_status": "unavailable",
                      "home_xg_history": home_n, "away_xg_history": away_n})
        reason = "; ".join(avail.get("notes", [])[:2])
        block["factors"].append({
            "factor": "expected_goals",
            "statement": (
                "xG is unavailable for this prediction, so the goal estimate "
                "uses goals-only rates. xG is not treated as zero; it is "
                f"reported missing (histories home={home_n}, away={away_n}"
                + (f"; {reason}" if reason else "") + ")."),
            "source": "feature availability record (missing stays missing)",
        })
    return block


def _explain_features(core: FullPrediction, snapshot: Dict) -> Dict:
    """Advanced-model contributions (coefficient × standardized feature) only
    when a fitted model and a sufficient row exist; otherwise availability."""
    from app.services.predictions.advanced import build_feature_row

    block: Dict = {"factors": []}
    names, values, sufficient = ([], [], False)
    try:
        if isinstance(snapshot, dict) and "home_team" in snapshot:
            names, values, sufficient = build_feature_row(snapshot, use_xg=False)
    except Exception:
        sufficient = False
    avail = core.feature_availability or {}
    block.update({
        "feature_version": (snapshot.get("feature_version", "features_v1")
                            if isinstance(snapshot, dict) else "features_v1"),
        "row_sufficient": bool(sufficient),
        "goals_history": {"home": avail.get("home_history"),
                          "away": avail.get("away_history")},
        "secondary": {k: avail.get(k) for k in ("shots", "corners", "cards")},
    })
    if sufficient:
        block["factors"].append({
            "factor": "form_and_context",
            "statement": ("Pre-cutoff form and context inputs are available "
                          f"(features: {', '.join(names[:4])}); they feed the "
                          "advanced model where fitted. Raw values describe "
                          "inputs, not causes."),
            "source": "feature snapshot (pre-cutoff only)",
        })
    else:
        block["factors"].append({
            "factor": "form_and_context",
            "statement": ("The full advanced feature row is not sufficient for "
                          "this match; form/context factors are omitted rather "
                          "than estimated."),
            "source": "feature snapshot sufficiency gate",
        })
    return block


def advanced_contributions(fitted_model, snapshot: Dict, use_xg: bool = False) -> Dict:
    """Per-class model contributions (coef × standardized feature) for a
    fitted AdvancedModel. Labeled model contribution, never cause of outcome."""
    from app.services.predictions.advanced import build_feature_row

    reg = getattr(fitted_model, "regression", None)
    coef = getattr(reg, "coef_", None)
    if coef is None or not getattr(fitted_model, "_fitted", False):
        return {"status": "unavailable", "reason": "model not fitted"}
    names, values, sufficient = build_feature_row(snapshot, use_xg=use_xg)
    if not sufficient or not values:
        return {"status": "unavailable", "reason": "feature row insufficient"}
    try:
        import numpy as np

        mean = np.asarray(getattr(reg, "mean_", [0.0] * len(values)), dtype=float)
        scale = np.asarray(getattr(reg, "scale_", [1.0] * len(values)), dtype=float)
        standardized = (np.asarray(values, dtype=float) - mean) / scale
        classes = ["home", "draw", "away"]
        per_class = {}
        for i, cls in enumerate(classes):
            row = coef[i][:len(values)] * standardized
            per_class[cls] = {
                names[j]: round(float(row[j]), 6) for j in range(len(names))
            }
        return {"status": "ok", "features": names,
                "standardized_values": [round(float(v), 6) for v in standardized],
                "per_class_contribution": per_class,
                "label": "model contribution (softmax coefficient x standardized "
                         "feature), not cause of outcome"}
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:150]}
