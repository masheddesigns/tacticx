"""Phase 35 observation lifecycle accounting (read-only).

Answers why N real paired observations exist, with exclusion reasons.
Never writes, never mutates, never promotes.
"""
from app.services.observation.contracts import (  # noqa: F401
    EXCLUDE_DUPLICATE,
    EXCLUDE_INSUFFICIENT_HISTORY,
    EXCLUDE_INVALID_PAIR,
    EXCLUDE_MISSING_OUTCOME,
    EXCLUDE_NOT_EVALUATED,
    EXCLUDE_NO_READINESS,
    EXCLUDE_NO_SHADOW,
    EXCLUDE_PENDING_OUTCOME,
    EXCLUDE_POST_CUTOFF,
    EXCLUDE_PROVIDER_INACTIVE,
    EXCLUDE_READINESS_BLOCKED,
    OBSERVATION_CONTRACT_VERSION,
    STAGE_DISCOVERED,
    STAGE_ELIGIBLE,
    STAGE_EVALUATED,
    STAGE_FINISHED,
    STAGE_INCLUDED,
    STAGE_OUTCOME_VERIFIED,
    STAGE_PAIRED,
    STAGE_PREDICTED,
    STAGE_SHADOWED,
)
from app.services.observation.lifecycle import (  # noqa: F401
    observation_summary,
)
