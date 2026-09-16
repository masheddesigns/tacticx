"""MiroFish scenario layer — intentionally decoupled (future Phase 5).

It must NEVER overwrite the statistical model's probabilities; it only adds
scenario/reasoning output on top.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field


class MiroFishInput(BaseModel):
    match_context: dict = Field(default_factory=dict)
    historical_data: dict = Field(default_factory=dict)
    current_statistics: dict = Field(default_factory=dict)
    team_information: dict = Field(default_factory=dict)
    market_movement: dict = Field(default_factory=dict)


class MiroFishOutput(BaseModel):
    scenario_analysis: str = ""
    agent_opinions: list[str] = Field(default_factory=list)
    scenario_probabilities: dict = Field(default_factory=dict)
    key_factors: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    summary: str = ""


class MiroFishService(ABC):
    @abstractmethod
    async def analyze(self, payload: MiroFishInput) -> MiroFishOutput: ...
