"""Phase 33 real-world performance evidence accumulation.

Read-only against predictions, outcomes, evaluations, and shadow
records. Produces immutable evidence snapshots; never decides,
promotes, or transitions governance.
"""
from app.services.evidence.cohort import (  # noqa: F401
    CohortError,
    build_cohort,
    cohort_to_dict,
    get_cohort,
)
from app.services.evidence.contracts import (  # noqa: F401
    BOOTSTRAP_CONFIDENCE,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    BUCKET_DEFINITION_VERSION,
    CALCULATION_VERSION,
    CALIBRATION_BINS,
    EVIDENCE_CONTRACT_VERSION,
    METRIC_DEFINITION_VERSION,
    MIN_CALIBRATION_PAIRS,
    MIN_PAIRED_EVIDENCE,
    STATE_CONFLICTING,
    STATE_DESCRIPTIVE,
    STATE_INCONCLUSIVE,
    STATE_INSUFFICIENT,
    STATE_INVALID,
    STATE_NO_DATA,
    STATE_SUPPORTED,
    canonical_hash,
)
from app.services.evidence.eligibility import (  # noqa: F401
    audit_cohort,
    audit_cohort_by_id,
)
from app.services.evidence.metrics import (  # noqa: F401
    paired_calibration,
    paired_metrics,
)
from app.services.evidence.snapshot import (  # noqa: F401
    EvidenceError,
    compute_evidence,
    decide_state,
    generate_snapshot,
    get_snapshot,
    snapshot_to_dict,
)
