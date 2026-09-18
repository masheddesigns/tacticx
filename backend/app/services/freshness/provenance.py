"""Temporal provenance model (Phase 10).

Four timestamps, never interchangeable:

  event_time:   when the football event occurred (kickoff, match minute).
  effective_at: when the information became knowable/valid for prediction
                purposes. NEVER inferred from event_time unless the source
                contract explicitly supports that interpretation.
  retrieved_at: when TacticX acquired the record.
  created_at:   when TacticX persisted the record.

Temporal status is derived deterministically from effective_at vs cutoff:

  effective_at <= cutoff -> known_pre_cutoff
  effective_at >  cutoff -> known_post_cutoff
  effective_at =  NULL   -> unknown (or estimated_* when parent-anchored and
                             the caller explicitly allows estimation)

Estimated timing is never presented as known timing.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel

from app.services.features.temporal import as_naive_utc

KNOWN_PRE, KNOWN_POST = "known_pre_cutoff", "known_post_cutoff"
UNKNOWN = "unknown"
ESTIMATED_PRE, ESTIMATED_POST = "estimated_pre_cutoff", "estimated_post_cutoff"


class TemporalProvenance(BaseModel):
    event_time: Optional[datetime] = None
    effective_at: Optional[datetime] = None
    retrieved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    anchor: str = ""  # e.g. "parent_match:123" for estimated rows
    model_config = {"arbitrary_types_allowed": True}


def classify(effective_at: Optional[datetime], cutoff: datetime,
             estimated: bool = False,
             anchor_before_cutoff: bool = False) -> str:
    """Deterministic temporal status. Estimated only when explicitly allowed
    AND the anchor predates cutoff; otherwise unknown stays unknown."""
    naive_cutoff = as_naive_utc(cutoff)
    eff = as_naive_utc(effective_at)
    if eff is not None and naive_cutoff is not None:
        return KNOWN_PRE if eff <= naive_cutoff else KNOWN_POST
    if estimated and anchor_before_cutoff:
        return ESTIMATED_PRE
    if estimated and not anchor_before_cutoff:
        return ESTIMATED_POST
    return UNKNOWN


def age_days(effective_at: Optional[datetime], cutoff: datetime) -> Optional[float]:
    """cutoff - effective_at in days. None when effective_at unknown."""
    eff = as_naive_utc(effective_at)
    naive_cutoff = as_naive_utc(cutoff)
    if eff is None or naive_cutoff is None:
        return None
    return max(0.0, (naive_cutoff - eff).total_seconds() / 86400.0)


def describe(record: Dict) -> Dict:
    """Attach semantics documentation to a provenance dict (for reports)."""
    return {
        "event_time": record.get("event_time"),
        "event_time_semantics": "when the football event occurred",
        "effective_at": record.get("effective_at"),
        "effective_at_semantics": "when the information became knowable/valid "
                                  "for prediction; never inferred from "
                                  "event_time unless the source contract says so",
        "retrieved_at": record.get("retrieved_at"),
        "retrieved_at_semantics": "when TacticX acquired the record",
        "created_at": record.get("created_at"),
        "created_at_semantics": "when TacticX persisted the record",
    }
