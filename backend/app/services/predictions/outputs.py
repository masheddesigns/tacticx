"""Phase 2 prediction outputs and model interface.

FullPrediction is the rich, versioned output every Phase 2 model produces.
The Phase 1 PredictionOutput/Provider interface is left untouched.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class FullPrediction(BaseModel):
    model_name: str = ""
    model_version: str = ""
    status: str = "valid"  # valid | insufficient_data | temporal_risk
    # 1X2 — must sum to ~1.0 (validated).
    home_win_probability: float = Field(ge=0.0, le=1.0)
    draw_probability: float = Field(ge=0.0, le=1.0)
    away_win_probability: float = Field(ge=0.0, le=1.0)
    # Expected goals.
    expected_home_goals: Optional[float] = None
    expected_away_goals: Optional[float] = None
    expected_total_goals: Optional[float] = None
    # Over/Under.
    over_1_5_probability: Optional[float] = None
    under_1_5_probability: Optional[float] = None
    over_2_5_probability: Optional[float] = None
    under_2_5_probability: Optional[float] = None
    over_3_5_probability: Optional[float] = None
    under_3_5_probability: Optional[float] = None
    # BTTS.
    btts_yes_probability: Optional[float] = None
    btts_no_probability: Optional[float] = None
    # Correct-score distribution, e.g. {"2-1": 0.09}. Never a single score.
    score_probabilities: Dict[str, float] = Field(default_factory=dict)
    # Audit trail.
    confidence: Optional[float] = None
    xg_used: bool = False
    feature_availability: Dict = Field(default_factory=dict)
    temporal_mode: str = "strict_prematch"
    prediction_cutoff: Optional[str] = None
    random_seed: Optional[int] = None
    data_quality: List[str] = Field(default_factory=list)

    def outcome_sum(self) -> float:
        return (self.home_win_probability + self.draw_probability
                + self.away_win_probability)
