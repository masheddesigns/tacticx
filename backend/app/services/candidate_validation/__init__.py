"""Phase 34 controlled candidate validation gate.

Reads research evidence, governance artifacts, and operational health;
writes candidate_validation_reports only. Never promotes, approves,
activates, or rolls back anything.
"""
from app.services.candidate_validation.contracts import (  # noqa: F401
    CALCULATION_VERSION,
    DEFAULT_CONFIG_ID,
    RULE_BLOCKED,
    RULE_INCONCLUSIVE,
    RULE_INSUFFICIENT,
    RULE_PASS,
    RULE_WARNING,
    STALENESS_STALE,
    STALENESS_SUPERSEDED,
    STALENESS_VALID,
    STATE_BLOCKED,
    STATE_INCONCLUSIVE,
    STATE_INSUFFICIENT,
    STATE_INVALID,
    STATE_PENDING,
    STATE_VALIDATED,
    VALIDATION_CONFIGS,
    VALIDATION_CONTRACT_VERSION,
    canonical_hash,
    get_config,
)
from app.services.candidate_validation.rules import (  # noqa: F401
    evaluate_rules,
)
from app.services.candidate_validation.service import (  # noqa: F401
    ValidationRunError,
    check_staleness,
    get_validation,
    run_validation,
    validation_to_dict,
)
