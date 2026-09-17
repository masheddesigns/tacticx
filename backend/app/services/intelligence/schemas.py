"""Canonical composed-prediction schemas (Phase 6).

ComposedPrediction wraps the statistical core output (FullPrediction,
unchanged) with separately labeled layers: derived markets, uncertainty,
disagreement, market context, explanation, scenarios, analogues, MiroFish.
No layer overwrites another; every number traces to source + version +
cutoff + calculation version.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

CALCULATION_VERSION = "composer_v1"


class LayerProvenance(BaseModel):
    source: str = ""
    calculation_version: str = CALCULATION_VERSION
    model_version: str = ""
    feature_version: str = "features_v1"
    cutoff: str = ""
    temporal_mode: str = "strict_prematch"
    status: str = "ok"


class DerivedMarkets(BaseModel):
    totals: Dict = Field(default_factory=dict)
    btts: Dict = Field(default_factory=dict)
    double_chance: Dict = Field(default_factory=dict)
    team_totals: Dict = Field(default_factory=dict)
    correct_scores: Dict = Field(default_factory=dict)
    goal_distributions: Dict = Field(default_factory=dict)
    validation: Dict = Field(default_factory=dict)
    provenance: LayerProvenance = Field(default_factory=LayerProvenance)


class UncertaintySummary(BaseModel):
    predictive_entropy: Optional[float] = None
    top_probability: Optional[float] = None
    probability_margin: Optional[float] = None
    model_disagreement: Dict = Field(default_factory=dict)
    data_completeness: Dict = Field(default_factory=dict)
    note: str = ("Probability, uncertainty and data quality are different "
                 "concepts; none of them is a correctness guarantee.")


class ModelDisagreement(BaseModel):
    members: Dict[str, Dict] = Field(default_factory=dict)
    per_outcome: Dict = Field(default_factory=dict)
    label: str = "model disagreement (descriptive, not a correctness signal)"


class MarketContext(BaseModel):
    status: str = "unavailable"
    consensus: Dict = Field(default_factory=dict)
    timestamp: Optional[str] = None
    bookmakers: List = Field(default_factory=list)
    overround: Optional[float] = None
    movement: Dict = Field(default_factory=dict)
    model_market_difference: Dict = Field(default_factory=dict)
    note: str = "Market = external observed information, never a model input."


class Explanation(BaseModel):
    headline: str = ""
    factors: List[Dict] = Field(default_factory=list)
    elo: Dict = Field(default_factory=dict)
    poisson: Dict = Field(default_factory=dict)
    xg: Dict = Field(default_factory=dict)
    features: Dict = Field(default_factory=dict)
    model_disagreement_note: str = ""
    provenance: LayerProvenance = Field(default_factory=LayerProvenance)


class ScenarioOutput(BaseModel):
    name: str = ""
    parameters: Dict = Field(default_factory=dict)
    probabilities: Dict = Field(default_factory=dict)
    goals: Dict = Field(default_factory=dict)
    markets: Dict = Field(default_factory=dict)
    score_top: List[Dict] = Field(default_factory=list)
    difference_from_baseline: Dict = Field(default_factory=dict)
    label: str = "sensitivity analysis, not a prediction of what will happen"


class AnalogueResult(BaseModel):
    status: str = "ok"
    analogues: List[Dict] = Field(default_factory=list)
    outcome_distribution: Dict = Field(default_factory=dict)
    methodology: str = ""
    provenance: LayerProvenance = Field(default_factory=LayerProvenance)


class MiroFishResult(BaseModel):
    status: str = "unavailable"
    output: Dict = Field(default_factory=dict)
    version: str = ""
    input_reference: str = ""
    note: str = ("MiroFish is an independent scenario layer; it never "
                 "overwrites the statistical prediction.")


class DataQuality(BaseModel):
    feature_count: int = 0
    available_feature_count: int = 0
    missing_feature_count: int = 0
    strict_mode: bool = True
    estimated_fields: List[str] = Field(default_factory=list)
    xg_available: bool = False
    event_data_available: bool = False
    lineup_data_available: bool = False
    market_available: bool = False


class ComposedPrediction(BaseModel):
    match: Dict = Field(default_factory=dict)
    cutoff: str = ""
    model: Dict = Field(default_factory=dict)
    status: str = "complete"
    probabilities: Dict = Field(default_factory=dict)
    goals: Dict = Field(default_factory=dict)
    markets: DerivedMarkets = Field(default_factory=DerivedMarkets)
    score_distribution: Dict = Field(default_factory=dict)
    uncertainty: UncertaintySummary = Field(default_factory=UncertaintySummary)
    model_disagreement: ModelDisagreement = Field(default_factory=ModelDisagreement)
    market: MarketContext = Field(default_factory=MarketContext)
    explanation: Explanation = Field(default_factory=Explanation)
    scenarios: List[ScenarioOutput] = Field(default_factory=list)
    analogues: AnalogueResult = Field(default_factory=AnalogueResult)
    mirofish: MiroFishResult = Field(default_factory=MiroFishResult)
    data_quality: DataQuality = Field(default_factory=DataQuality)
    core_prediction: Dict = Field(default_factory=dict)
    provenance: LayerProvenance = Field(default_factory=LayerProvenance)
