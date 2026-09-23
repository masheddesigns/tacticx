"""Phase 27 prediction evaluation lifecycle.

Measurement only: scores immutable Phase 26 prediction snapshots against
verified canonical outcomes. Never modifies predictions or models.
"""
from app.services.prediction_evaluation.aggregation import (  # noqa: F401
    summarize_evaluations,
)
from app.services.prediction_evaluation.calibration import (  # noqa: F401
    calibration_report,
)
from app.services.prediction_evaluation.contracts import (  # noqa: F401
    EVALUATION_CONTRACT_VERSION,
    OUTCOME_CONTRACT_VERSION,
    canonical_hash,
    evaluation_key,
)
from app.services.prediction_evaluation.drift import drift_report  # noqa: F401
from app.services.prediction_evaluation.metrics import (  # noqa: F401
    score_snapshot,
)
from app.services.prediction_evaluation.outcomes import (  # noqa: F401
    OutcomeNotReady,
    capture_outcome_snapshot,
    latest_outcome,
    outcome_eligibility,
    outcome_to_dict,
)
from app.services.prediction_evaluation.service import (  # noqa: F401
    EvaluationBlocked,
    describe_match_evaluation,
    evaluate_prediction_snapshot,
    evaluation_to_dict,
    evaluations_for_match,
    evaluations_for_prediction,
    get_snapshot,
)
