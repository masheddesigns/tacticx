"""Phase 29 versioned research datasets with temporal audit.

Datasets are explicit observation lists: (match_id, cutoff) pairs over
FINISHED scored matches, split chronologically into train/validation/test
by kickoff thirds. The builder never rebuilds silently: identical inputs
yield identical hashes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.db.models.research_registry import ResearchDataset
from app.services.features.temporal import as_naive_utc

from .contracts import (
    LEAKAGE_INVALID,
    LEAKAGE_PASS,
    canonical_hash,
)

CUTOFF_POLICY = "kickoff_minus_24h"
CUTOFF_BUFFER = timedelta(hours=24)


class DatasetError(Exception):
    def __init__(self, reason: str, *, code: str = "DATASET_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def _cutoff_for(kickoff: datetime) -> datetime:
    naive = as_naive_utc(kickoff)
    if naive is None:
        raise DatasetError("match kickoff is required", code="MISSING_KICKOFF")
    return naive - CUTOFF_BUFFER


def build_dataset(
    db: Session,
    *,
    competitions: Optional[List[str]] = None,
    seasons: Optional[List[str]] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    min_history: int = 3,
    limit: int = 500,
    dataset_version: str = "v1",
) -> ResearchDataset:
    """Build, hash, and persist (or reuse) a versioned dataset."""
    query = db.query(Match).filter(
        Match.status == "FINISHED",
        Match.home_score.isnot(None), Match.away_score.isnot(None),
        Match.kickoff_at.isnot(None),
        Match.home_team_id.isnot(None), Match.away_team_id.isnot(None))
    league_ids = None
    if competitions or seasons:
        league_query = db.query(League.id)
        if competitions:
            league_query = league_query.filter(League.code.in_(competitions))
        if seasons:
            league_query = league_query.filter(League.season.in_(seasons))
        league_ids = [row[0] for row in league_query.all()]
        query = query.filter(Match.league_id.in_(league_ids) if league_ids else False)
    if date_from is not None:
        query = query.filter(Match.kickoff_at >= date_from)
    if date_to is not None:
        query = query.filter(Match.kickoff_at <= date_to)
    matches = query.order_by(Match.kickoff_at.asc()).limit(limit).all()

    observations = []
    for match in matches:
        cutoff = _cutoff_for(match.kickoff_at)
        home_n = db.query(Match).filter(
            ((Match.home_team_id == match.home_team_id)
             | (Match.away_team_id == match.home_team_id)),
            Match.status == "FINISHED",
            Match.kickoff_at < cutoff).count()
        away_n = db.query(Match).filter(
            ((Match.home_team_id == match.away_team_id)
             | (Match.away_team_id == match.away_team_id)),
            Match.status == "FINISHED",
            Match.kickoff_at < cutoff).count()
        if home_n < min_history or away_n < min_history:
            continue
        observations.append({
            "match_id": match.id,
            "cutoff": cutoff.replace(microsecond=0).isoformat(),
            "kickoff": as_naive_utc(match.kickoff_at).replace(
                microsecond=0).isoformat(),
        })
    if not observations:
        raise DatasetError("no observations satisfy the inclusion rules",
                           code="EMPTY_DATASET")

    n = len(observations)
    train_end = max(1, n // 3)
    val_end = max(train_end + 1, 2 * n // 3)
    splits = {
        "train": observations[:train_end],
        "validation": observations[train_end:val_end],
        "test": observations[val_end:],
    }
    if not splits["test"]:
        raise DatasetError("test split is empty; widen the scope",
                           code="EMPTY_TEST_SPLIT")

    spec = {
        "competitions": sorted(competitions or []),
        "seasons": sorted(seasons or []),
        "feature_version": "features_v1",
        "cutoff_policy": CUTOFF_POLICY,
        "min_history": min_history,
        "observations": observations,
    }
    dataset_hash = canonical_hash(spec)
    existing = db.query(ResearchDataset).filter_by(
        dataset_hash=dataset_hash).first()
    if existing is not None:
        return existing

    def period(rows: list) -> Dict[str, Any]:
        kicks = [r["kickoff"] for r in rows]
        return {"from": min(kicks), "to": max(kicks), "count": len(rows)}

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    row = ResearchDataset(
        dataset_id=f"ds_{uuid.uuid4().hex[:12]}",
        dataset_version=dataset_version,
        competitions={"values": sorted(competitions or [])},
        seasons={"values": sorted(seasons or [])},
        feature_version="features_v1",
        cutoff_policy=CUTOFF_POLICY,
        inclusion_rules={"min_history": min_history,
                         "status": "FINISHED_scored",
                         "cutoff_policy": CUTOFF_POLICY},
        observations={"items": observations, "count": n},
        train_period=period(splits["train"]),
        validation_period=period(splits["validation"]),
        test_period=period(splits["test"]),
        provenance={"builder": "research.datasets.build_dataset",
                    "cutoff_policy": CUTOFF_POLICY,
                    "created_at": now,
                    "source": "canonical matches table (read-only)"},
        dataset_hash=dataset_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def split_observations(dataset: ResearchDataset) -> Dict[str, List[Dict[str, Any]]]:
    items = (dataset.observations or {}).get("items", [])
    n = len(items)
    train_end = max(1, n // 3)
    val_end = max(train_end + 1, 2 * n // 3)
    return {"train": items[:train_end],
            "validation": items[train_end:val_end],
            "test": items[val_end:]}


def audit_temporal_integrity(dataset: ResearchDataset) -> Dict[str, Any]:
    """Verify cutoffs precede kickoffs and splits are chronological."""
    items = (dataset.observations or {}).get("items", [])
    violations = []
    for obs in items:
        try:
            cutoff = datetime.fromisoformat(obs["cutoff"])
            kickoff = datetime.fromisoformat(obs["kickoff"])
        except (KeyError, ValueError):
            violations.append({"match_id": obs.get("match_id"),
                               "issue": "unparseable timestamps"})
            continue
        if not cutoff < kickoff:
            violations.append({"match_id": obs.get("match_id"),
                               "issue": "cutoff_not_before_kickoff"})
    splits = split_observations(dataset)
    bounds = {}
    for name, rows in splits.items():
        kicks = sorted(r["kickoff"] for r in rows)
        bounds[name] = (kicks[0], kicks[-1]) if kicks else (None, None)
    for earlier, later in (("train", "validation"), ("validation", "test")):
        e_end, l_start = bounds[earlier][1], bounds[later][0]
        if e_end is not None and l_start is not None and not e_end <= l_start:
            violations.append({"issue": f"{earlier}_overlaps_{later}"})
    return {
        "status": LEAKAGE_INVALID if violations else LEAKAGE_PASS,
        "violations": violations,
        "observation_count": len(items),
    }


def dataset_to_dict(row: ResearchDataset) -> Dict[str, Any]:
    return {
        "dataset_id": row.dataset_id,
        "dataset_version": row.dataset_version,
        "competitions": row.competitions,
        "seasons": row.seasons,
        "feature_version": row.feature_version,
        "cutoff_policy": row.cutoff_policy,
        "inclusion_rules": row.inclusion_rules,
        "observation_count": (row.observations or {}).get("count", 0),
        "train_period": row.train_period,
        "validation_period": row.validation_period,
        "test_period": row.test_period,
        "provenance": row.provenance,
        "dataset_hash": row.dataset_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
