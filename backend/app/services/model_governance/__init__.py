"""Phase 30 controlled model validation & promotion governance.

Authority only: activation changes the registry binding, never prediction
code, historical snapshots, or default execution paths. No automatic
promotion exists anywhere in this package.
"""
from app.services.model_governance.approval import (  # noqa: F401
    approvals_for_request,
    approval_to_dict,
    decide,
    required_approvals,
)
from app.services.model_governance.artifact import (  # noqa: F401
    artifact_identity,
    artifact_to_dict,
    champion_artifact_identity,
    get_artifact,
    register_artifact,
)
from app.services.model_governance.audit import (  # noqa: F401
    active_champion_view,
    champion_lineage,
    reconstruct,
)
from app.services.model_governance.contracts import (  # noqa: F401
    ALLOWED_TRANSITIONS,
    APPROVAL_PENDING,
    APPROVED,
    CANARY_ELIGIBLE,
    CHALLENGER,
    DEPLOYMENT_CANARY,
    DEPLOYMENT_PRODUCTION,
    DEPLOYMENT_SHADOW,
    GOVERNANCE_CONTRACT_VERSION,
    MIN_SHADOW_PAIRS,
    PRODUCTION_ACTIVE,
    PROMOTION_REQUESTED,
    REQUIRED_APPROVAL_COUNT,
    RESEARCH_ONLY,
    ROLE_CHALLENGER,
    ROLE_CHAMPION,
    VALIDATED,
    canonical_hash,
)
from app.services.model_governance.deployment import (  # noqa: F401
    activate_production,
    activation_history,
    check_canary_eligibility,
    mark_canary_eligible,
    rollback,
)
from app.services.model_governance.lifecycle import (  # noqa: F401
    GovernanceError,
    audit_trail,
    allowed_transitions as lifecycle_transitions,
    event_to_dict,
    events_for_artifact,
    log_event,
    transition,
)
from app.services.model_governance.promotion import (  # noqa: F401
    get_request,
    list_requests,
    promotion_to_dict,
    request_promotion,
)
from app.services.model_governance.registry import (  # noqa: F401
    bind_challenger,
    current_champion,
    ensure_champion,
    list_bindings,
    resolve_active_model_id,
)
from app.services.model_governance.service import (  # noqa: F401
    full_flow_status,
    promote_to_challenger,
    register_candidate_artifact,
)
from app.services.model_governance.shadow import (  # noqa: F401
    evaluate_shadow,
    run_shadow_pair,
    shadow_pairs,
    shadow_to_dict,
    start_shadow,
)
from app.services.model_governance.validation import (  # noqa: F401
    check_compatibility,
    validate_candidate,
    validation_to_dict,
)
