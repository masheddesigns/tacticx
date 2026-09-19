"""Deterministic acquisition plans (Phase 19).

An AcquisitionPlan binds competition + season + candidate sources +
selected/ fallback sources + field authorities + reason. Identical
(registry, qualification, season, competition) inputs produce identical
plans; the plan hash proves it.
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AcquisitionPlan(BaseModel):
    competition: str = ""
    season: str = ""
    candidate_sources: List[str] = Field(default_factory=list)
    selected_source: str = ""
    fallback_sources: List[str] = Field(default_factory=list)
    field_authorities: Dict[str, List[str]] = Field(default_factory=dict)
    reason: str = ""
    plan_hash: str = ""


def build_plan(competition: str, season: str,
               qualified: Dict[str, str],
               field_authority: Optional[Dict[str, List[str]]] = None) -> AcquisitionPlan:
    """Build the deterministic plan.

    ``qualified`` maps source_id -> level ("A"/"B"/"C"/"D"). Canonical
    selection: lowest-priority-number Level-A source, else no canonical
    source (supplementary/market sources never silently promote).
    """
    from app.services.provider_qualification import registry as registry_mod

    reg = registry_mod.get_registry()
    ordered_ids = sorted(qualified)
    canonical: List[str] = []
    for source_id in ordered_ids:
        if qualified[source_id] != "A":
            continue
        try:
            entry = reg.get(source_id)
        except ValueError:
            continue
        if entry.enabled and competition in (entry.supported_competitions or []):
            canonical.append(source_id)
    canonical.sort(key=lambda sid: (reg.get(sid).priority, sid))
    selected = canonical[0] if canonical else ""
    fallbacks = [sid for sid in canonical[1:]]
    authorities: Dict[str, List[str]] = {}
    source = field_authority or {}
    for field, sources in source.items():
        authorities[field] = sorted(sources)
    if selected:
        reason = (f"selected {selected}: lowest-priority Level-A source "
                  f"supporting {competition}")
    else:
        reason = (f"no Level-A source for {competition}: canonical fixtures "
                  f"unavailable; supplementary sources not promoted")
    plan = AcquisitionPlan(
        competition=competition, season=season,
        candidate_sources=ordered_ids, selected_source=selected,
        fallback_sources=fallbacks, field_authorities=authorities,
        reason=reason)
    plan.plan_hash = _hash_plan(plan)
    return plan


def _hash_plan(plan: AcquisitionPlan) -> str:
    canonical = json.dumps(plan.model_dump(exclude={"plan_hash"}),
                           sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
