"""PredictionProvider interface (Phase 1: architecture + stub only).

Phase 2 will add EloModel / PoissonModel / XGModel / MonteCarloModel /
MLModel / MarketModel / EnsembleModel behind this same interface.
"""
from __future__ import annotations

from typing import Optional

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field


class PredictionOutput(BaseModel):
    home_win_probability: float = Field(ge=0, le=1)
    draw_probability: float = Field(ge=0, le=1)
    away_win_probability: float = Field(ge=0, le=1)
    over_2_5_probability: Optional[float] = None
    under_2_5_probability: Optional[float] = None
    btts_yes_probability: Optional[float] = None
    btts_no_probability: Optional[float] = None
    confidence: Optional[float] = None
    model_version: str = "stub-0.1"


class PredictionProvider(ABC):
    model_version: str = "stub-0.1"

    @abstractmethod
    def predict(self, input_snapshot: dict) -> PredictionOutput: ...


class StubPredictionProvider(PredictionProvider):
    """Phase-1 placeholder. Returns uniform probabilities — NEVER presented as real."""
    model_version = "stub-0.1"

    def predict(self, input_snapshot: dict) -> PredictionOutput:
        return PredictionOutput(
            home_win_probability=1 / 3, draw_probability=1 / 3, away_win_probability=1 / 3,
            confidence=0.0, model_version=self.model_version,
        )
