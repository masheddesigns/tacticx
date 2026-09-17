"""Statistic reconciliation + semantic definitions + xG separation (Phase 8).

Providers define statistics differently (Phase 1.8: 444 known
statistic-definition conflicts). Numerical differences are classified, not
blindly flagged:

  definition_difference  — same canonical name, different provider semantics
  measurement_difference — same semantics, small numerical gap
  true_conflict          — same semantics, material gap
  unknown                — cannot be established

xG is source-specific: values carry xg_source/definition/version/effective_at,
multiple sources are preserved side by side, never blindly averaged.
Incompatible statistics are never combined automatically (gating support).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.core import MatchStatistic
from app.db.models.reconciliation import StatDefinition
from app.services.reconciliation import conflicts as conflict_svc

MEASUREMENT_TOLERANCE = {
    "shots_total": 2.0,
    "shots_on_target": 1.0,
    "corners": 1.0,
    "fouls": 2.0,
    "possession": 3.0,
    "default": 1.0,
}

# Canonical stat -> {source: provider definition}. Seeded below; extendable.
KNOWN_DEFINITIONS: List[Dict] = [
    {"metric_name": "shots_total", "source": "football_data_co_uk",
     "provider_definition": "HS/AS columns: all recorded shots including blocked",
     "unit": "count", "aggregation": "match total", "canonical_name": "shots_total"},
    {"metric_name": "shots_total", "source": "api_football",
     "provider_definition": "Total Shots type: on+off+blocked as reported by data vendor",
     "unit": "count", "aggregation": "match total", "canonical_name": "shots_total"},
    {"metric_name": "shots_on_target", "source": "football_data_co_uk",
     "provider_definition": "HST/AST columns: shots on target (scored + saved)",
     "unit": "count", "aggregation": "match total", "canonical_name": "shots_on_target"},
    {"metric_name": "shots_on_target", "source": "api_football",
     "provider_definition": "Shots on Goal type: vendor definition, excludes woodwork",
     "unit": "count", "aggregation": "match total", "canonical_name": "shots_on_target"},
    {"metric_name": "possession", "source": "api_football",
     "provider_definition": "Ball Possession percentage as reported by vendor",
     "unit": "percent", "aggregation": "match average", "canonical_name": "possession"},
    {"metric_name": "expected_goals", "source": "statsbomb",
     "provider_definition": "StatsBomb Open Data shot-based xG model v1",
     "unit": "goals", "aggregation": "sum over shots", "canonical_name": "expected_goals"},
    {"metric_name": "expected_goals", "source": "api_football",
     "provider_definition": "Vendor expected_goals (model undisclosed)",
     "unit": "goals", "aggregation": "match total", "canonical_name": "expected_goals"},
]

XG_NAMES = {"xg", "expected_goals", "expected_goals_for", "exp_g"}


def ensure_stat_definitions(db: Session) -> int:
    """Seed the definition registry (idempotent). Returns rows added."""
    added = 0
    for entry in KNOWN_DEFINITIONS:
        exists = db.query(StatDefinition).filter_by(
            metric_name=entry["metric_name"], source=entry["source"]).first()
        if exists is None:
            db.add(StatDefinition(**entry))
            added += 1
    if added:
        db.commit()
    return added


def _parse(value: str) -> Optional[float]:
    try:
        return float(str(value).rstrip("%"))
    except (TypeError, ValueError):
        return None


def definitions_for(db: Session, canonical_name: str) -> Dict[str, StatDefinition]:
    return {d.source: d for d in db.query(StatDefinition).filter_by(
        metric_name=canonical_name).all()}


def classify_stat_difference(db: Session, canonical_name: str, source_a: str,
                             value_a: float, source_b: str,
                             value_b: float) -> str:
    """Semantic classification of a same-stat numerical gap."""
    definitions = definitions_for(db, canonical_name)
    def_a = definitions.get(source_a)
    def_b = definitions.get(source_b)
    if def_a is not None and def_b is not None and \
            def_a.provider_definition != def_b.provider_definition:
        return conflict_svc.CLASS_DEFINITION
    if def_a is None or def_b is None:
        # One side undefined: cannot rule definition difference out.
        tolerance = MEASUREMENT_TOLERANCE.get(canonical_name,
                                              MEASUREMENT_TOLERANCE["default"])
        if abs(value_a - value_b) <= tolerance:
            return conflict_svc.CLASS_MEASUREMENT
        return conflict_svc.CLASS_UNKNOWN
    tolerance = MEASUREMENT_TOLERANCE.get(canonical_name,
                                          MEASUREMENT_TOLERANCE["default"])
    if abs(value_a - value_b) <= tolerance:
        return conflict_svc.CLASS_MEASUREMENT
    return conflict_svc.CLASS_TRUE_CONFLICT


def reconcile_match_statistics(db: Session, match_id: int,
                               dry_run: bool = False) -> Dict:
    """Compare same (team, stat, period) rows across sources for one match."""
    rows = db.query(MatchStatistic).filter_by(match_id=match_id).all()
    groups: Dict[Tuple, List] = {}
    for row in rows:
        groups.setdefault((row.team, row.stat_name, row.period or "full"), []).append(row)
    summary = {"match_id": match_id, "stat_groups": len(groups),
               "compared": 0, "definition_difference": 0,
               "measurement_difference": 0, "true_conflict": 0, "unknown": 0,
               "dry_run": dry_run}
    for (team, stat_name, period), members in groups.items():
        by_source: Dict[str, List] = {}
        for row in members:
            by_source.setdefault(row.source or "unknown", []).append(row)
        sources = sorted(by_source)
        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                for a in by_source[sources[i]]:
                    for b in by_source[sources[j]]:
                        va, vb = _parse(a.stat_value), _parse(b.stat_value)
                        if va is None or vb is None:
                            summary["unknown"] += 1
                            continue
                        summary["compared"] += 1
                        if va == vb:
                            continue
                        classification = classify_stat_difference(
                            db, stat_name, a.source or "unknown", va,
                            b.source or "unknown", vb)
                        summary[classification] = summary.get(classification, 0) + 1
                        if classification == conflict_svc.CLASS_TRUE_CONFLICT \
                                and not dry_run:
                            conflict_svc.record_conflict(
                                db, "statistic", match_id, "statistic_mismatch",
                                f"{team}:{stat_name}:{period}",
                                a.source or "unknown", b.source or "unknown",
                                a.stat_value, b.stat_value,
                                classification=classification)
    return summary


def xg_by_source(db: Session, match_id: int) -> Dict:
    """xG values separated by source (never averaged). Each entry carries
    source/definition/version/effective_at where the stored row has them."""
    rows = db.query(MatchStatistic).filter_by(match_id=match_id).filter(
        MatchStatistic.stat_name.in_(XG_NAMES)).all()
    definitions = {d.source: d for d in db.query(StatDefinition).filter(
        StatDefinition.metric_name.in_(XG_NAMES)).all()}
    out: Dict[str, List[Dict]] = {}
    for row in rows:
        source = row.source or "unknown"
        definition = definitions.get(source)
        out.setdefault(source, []).append({
            "xg_value": _parse(row.stat_value),
            "xg_source": source,
            "xg_definition": definition.provider_definition if definition else "",
            "xg_version": "",
            "team": row.team,
            "period": row.period,
            "effective_at": str(row.effective_at) if row.effective_at else None,
            "temporal_quality": "unknown" if row.effective_at is None else "verified",
        })
    return {"match_id": match_id, "by_source": out,
            "note": "Source-specific values preserved side by side; never averaged."}


def compatible_sources(db: Session, canonical_name: str,
                       sources: List[str]) -> Dict:
    """Gating helper: sources sharing one provider definition are combinable;
    mixed definitions must stay source-specific."""
    definitions = definitions_for(db, canonical_name)
    defined = {s: definitions[s].provider_definition for s in sources
               if s in definitions}
    distinct = set(defined.values())
    if len(distinct) <= 1 and len(defined) == len(sources):
        return {"compatible": True, "sources": sources,
                "definition": next(iter(distinct), "")}
    return {"compatible": False, "sources": sources,
            "reason": "mixed or undefined provider semantics; keep source-specific"}
