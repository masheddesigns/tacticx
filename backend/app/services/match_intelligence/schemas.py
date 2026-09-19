"""Canonical match-intelligence product schema (Phase 17).

``match_intelligence_v1`` is a versioned, consumer-facing reshaping of the
Phase 15 intelligence response plus the Phase 16 MiroFish scenario layer.
No values are recalculated here: every section is projected from existing
service outputs, so the statistical backbone cannot drift.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "match_intelligence_v1"


class MatchSection(BaseModel):
    match_id: int = 0
    home_team: Dict[str, Any] = Field(default_factory=dict)
    away_team: Dict[str, Any] = Field(default_factory=dict)
    competition: Dict[str, Any] = Field(default_factory=dict)
    season: str = ""
    kickoff: str = ""
    venue: Optional[str] = None
    status: str = ""
    sources: List[Dict[str, Any]] = Field(default_factory=list)


class CutoffSection(BaseModel):
    cutoff: str = ""
    cutoff_policy: str = "strict_prematch: only pre-cutoff records contribute"
    prediction_as_of: str = ""
    market_as_of: Optional[str] = None
    temporal_quality: str = "unknown"
    has_estimated_timing: bool = False
    has_unknown_timing: bool = False


class TemporalQualitySection(BaseModel):
    strict: List[str] = Field(default_factory=list)
    estimated: List[str] = Field(default_factory=list)
    unknown: List[str] = Field(default_factory=list)


class MirofishSection(BaseModel):
    status: str = "unavailable"
    provider: str = ""
    contract_version: str = ""
    scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ProvenanceSection(BaseModel):
    match_id: int = 0
    cutoff: str = ""
    prediction_snapshot: Dict[str, Any] = Field(default_factory=dict)
    model_version: str = ""
    feature_version: str = ""
    dataset_version: str = ""
    intelligence_snapshot: Dict[str, Any] = Field(default_factory=dict)
    scenario_version: str = ""
    mirofish_contract_version: str = ""
    mirofish_provider: str = ""
    request_hash: str = ""
    response_hash: str = ""
    generated_at: str = ""


class MatchIntelligence(BaseModel):
    schema_version: str = SCHEMA_VERSION
    match: MatchSection = Field(default_factory=MatchSection)
    cutoff: CutoffSection = Field(default_factory=CutoffSection)
    core_prediction: Dict[str, Any] = Field(default_factory=dict)
    derived_markets: Dict[str, Any] = Field(default_factory=dict)
    expected_goals: Dict[str, Any] = Field(default_factory=dict)
    correct_score: Dict[str, Any] = Field(default_factory=dict)
    uncertainty: Dict[str, Any] = Field(default_factory=dict)
    model_disagreement: Dict[str, Any] = Field(default_factory=dict)
    data_quality: Dict[str, Any] = Field(default_factory=dict)
    temporal_quality: TemporalQualitySection = Field(
        default_factory=TemporalQualitySection)
    market: Dict[str, Any] = Field(default_factory=dict)
    analogues: Dict[str, Any] = Field(default_factory=dict)
    scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    mirofish: MirofishSection = Field(default_factory=MirofishSection)
    explanation: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    provenance: ProvenanceSection = Field(default_factory=ProvenanceSection)
