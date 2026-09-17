"""Phase 5 evaluation package: robustness, cross-league validation,
probability quality. See backend/docs/PHASE5_VALIDATION.md (to be written)."""
from app.services.evaluation import (
    artifacts,
    calibration,
    compare,
    regimes,
    sensitivity,
    subgroups,
    uncertainty,
)

__all__ = ["artifacts", "calibration", "compare", "regimes", "sensitivity",
           "subgroups", "uncertainty"]
