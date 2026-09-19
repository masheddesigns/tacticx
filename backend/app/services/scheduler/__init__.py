"""Production acquisition scheduler (Phase 20).

Orchestrates recurring acquisition jobs without requiring manual
intervention. Append-only observations, temporal provenance, source
qualification, source health, fallback rules, idempotency, historical
integrity, prediction cutoff safety, provider rate limits, operational
auditability.

Prediction is always downstream: acquisition → data readiness →
prediction MAY later consume it. The scheduler never triggers model
training, prediction generation, or model promotion.
"""
from app.services.scheduler.config import (  # noqa: F401
    ALL_JOB_TYPES,
    JOB_FIXTURE_REFRESH,
    JOB_FRESHNESS_AUDIT,
    JOB_HEALTH_CHECK,
    JOB_QUALIFICATION,
    JOB_RESULT_REFRESH,
    JOB_STATUS_REFRESH,
    get_job_config,
    get_scheduler_config,
    lock_key,
)
from app.services.scheduler.dashboard import scheduler_status  # noqa: F401
from app.services.scheduler.monitoring import (  # noqa: F401
    check_alerts,
    detect_anomalies,
    operational_summary,
)
from app.services.scheduler.orchestrator import (  # noqa: F401
    run_due,
    run_job,
    run_job_manual,
)
from app.services.scheduler.store import (  # noqa: F401
    acquire_lock,
    cleanup_expired_locks,
    create_record,
    find_due_jobs,
    is_due,
    recent_records,
    release_lock,
)
