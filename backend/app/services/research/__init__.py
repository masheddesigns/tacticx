"""Phase 29 controlled research pipeline.

Strictly isolated from production: invokes production model classes
read-only through the same cutoff-safe path, never modifies production
files, configuration, snapshots, evaluations, or providers.
"""
from app.services.research.candidates import (  # noqa: F401
    BUILTIN_CANDIDATES,
    CandidateError,
    candidate_to_dict,
    get_candidate,
    predict_with_candidate,
    register_builtin,
    register_candidate,
    validate_declared_inputs,
)
from app.services.research.contracts import (  # noqa: F401
    BASELINE_MODEL_ID,
    EVALUATION_PROTOCOL,
    EVALUATION_PROTOCOL_VERSION,
    EVIDENCE_IMPROVEMENT,
    EVIDENCE_INSUFFICIENT,
    EVIDENCE_NONE,
    EVIDENCE_REGRESSION,
    LEAKAGE_INVALID,
    LEAKAGE_PASS,
    RESEARCH_CONTRACT_VERSION,
    STATUS_COMPLETED,
    STATUS_DRAFT,
    STATUS_INVALID,
    STATUS_RUNNING,
    STATUS_SUPERSEDED,
    canonical_hash,
)
from app.services.research.datasets import (  # noqa: F401
    DatasetError,
    audit_temporal_integrity,
    build_dataset,
    dataset_to_dict,
    split_observations,
)
from app.services.research.experiments import (  # noqa: F401
    ExperimentError,
    experiment_to_dict,
    run_experiment,
)
from app.services.research.isolation import (  # noqa: F401
    production_fingerprint,
    verify_fingerprint,
)
