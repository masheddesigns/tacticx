"""Phase 32 real-data champion/challenger shadow pipeline.

Shared cutoff-safe feature snapshots; isolated challenger outputs;
shared verified outcomes. Read-only against production predictions,
intelligence, registry, outcomes, and evaluations.
"""
from app.services.shadow_execution.contracts import (  # noqa: F401
    ELIGIBLE,
    EVAL_EVALUATED,
    EVAL_INSUFFICIENT,
    EVAL_PENDING,
    NO_ELIGIBLE_MATCHES,
    SHADOW_CONTRACT_VERSION,
    SHADOW_INCOMPATIBLE,
    SHADOW_PAIR_INVALID,
    canonical_hash,
    shadow_execution_key,
)
from app.services.shadow_execution.eligibility import (  # noqa: F401
    ShadowIneligible,
    check_challenger,
    check_match,
    find_eligible_matches,
)
from app.services.shadow_execution.evaluation import (  # noqa: F401
    ShadowEvaluationError,
    evaluate_shadow_pair,
    evaluations_for_challenger,
    shadow_evaluation_to_dict,
)
from app.services.shadow_execution.execution import (  # noqa: F401
    ShadowExecutionError,
    execute_shadow,
    find_shadow,
    shadow_to_dict,
    validate_shadow_pair,
)
from app.services.shadow_execution.monitoring import (  # noqa: F401
    shadow_comparison,
    shadow_summary,
)
