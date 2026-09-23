"""Phase 26 pre-match prediction execution layer.

Execution/integration only. No model mathematics live here; the promoted
production ensemble is invoked unmodified through its existing predict().
"""
from app.services.prediction_execution.contracts import (  # noqa: F401
    ELIGIBLE_READINESS,
    EXECUTION_CONTRACT_VERSION,
    PREDICTION_MODE,
    SUPPORTED_MODEL_IDS,
    canonical_hash,
    execution_key,
)
from app.services.prediction_execution.service import (  # noqa: F401
    PredictionBlocked,
    describe_match_predictions,
    execute_pre_match_prediction,
    get_latest_certificate,
    get_prediction,
    resolve_certificate,
)
