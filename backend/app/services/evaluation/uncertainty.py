"""Descriptive uncertainty quantities (never correctness claims)."""
from __future__ import annotations

import math
from typing import Dict, List

from app.services.predictions.advanced import prediction_entropy


def probability_margin(probs: List[float]) -> Dict:
    """Top probability, runner-up, and their gap. Descriptive only."""
    ordered = sorted(((p, i) for i, p in enumerate(probs)), reverse=True)
    top, second = ordered[0][0], ordered[1][0] if len(ordered) > 1 else 0.0
    return {"top_probability": round(top, 6),
            "second_probability": round(second, 6),
            "margin": round(top - second, 6),
            "top_class": ordered[0][1]}


def describe_details(details: List[Dict]) -> List[Dict]:
    """Attach entropy + margin to each detail row (new list, inputs untouched)."""
    out = []
    for row in details:
        home, draw, away = (float(row["probs"][0]), float(row["probs"][1]),
                            float(row["probs"][2]))
        total = home + draw + away
        if total <= 0:
            continue
        home, draw, away = home / total, draw / total, away / total
        entry = dict(row)
        entry["entropy"] = round(prediction_entropy(home, draw, away), 6)
        entry.update(probability_margin([home, draw, away]))
        out.append(entry)
    return out


def ensemble_disagreement(member_details: Dict[str, List[Dict]]) -> Dict:
    """Dispersion of member probabilities per match, then averaged.

    Stored as ensemble_disagreement_v1. High disagreement flags matches
    where components diverge — never evidence for any particular outcome.
    """
    by_match: Dict[int, Dict[str, List[float]]] = {}
    for name, rows in member_details.items():
        for row in rows:
            slot = by_match.setdefault(row["match_id"], {})
            slot[name] = [float(row["probs"][0]), float(row["probs"][1]),
                          float(row["probs"][2])]
    per_match = []
    for match_id, slot in by_match.items():
        per_outcome = {}
        for idx, outcome in enumerate(("home", "draw", "away")):
            values = [probs[idx] for probs in slot.values()]
            mean = sum(values) / len(values)
            var = sum((v - mean) ** 2 for v in values) / len(values)
            per_outcome[outcome] = {
                "mean": round(mean, 6),
                "std": round(math.sqrt(var), 6),
                "min": round(min(values), 6),
                "max": round(max(values), 6),
                "n_members": len(values),
            }
        per_match.append({"match_id": match_id, "members": sorted(slot),
                          "per_outcome": per_outcome})
    aggregate = {}
    for outcome in ("home", "draw", "away"):
        stds = [m["per_outcome"][outcome]["std"] for m in per_match]
        aggregate[outcome] = {
            "mean_std": round(sum(stds) / len(stds), 6) if stds else None,
            "max_std": round(max(stds), 6) if stds else None,
        }
    return {"version": "ensemble_disagreement_v1",
            "n_matches": len(per_match),
            "aggregate": aggregate,
            "per_match": sorted(per_match, key=lambda m: m["match_id"])}
