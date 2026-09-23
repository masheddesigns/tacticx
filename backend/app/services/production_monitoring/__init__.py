"""Phase 28 production monitoring: observability + analysis only.

Read-only aggregation over immutable prediction/evaluation records.
Never modifies predictions, evaluations, outcomes, models, or providers.
"""
from app.services.production_monitoring.anomalies import (  # noqa: F401
    detect_anomalies,
)
from app.services.production_monitoring.breakdown import breakdown  # noqa: F401
from app.services.production_monitoring.calibration import (  # noqa: F401
    calibration_detail,
)
from app.services.production_monitoring.contracts import (  # noqa: F401
    BUCKET_DEFINITION_VERSION,
    METRIC_DEFINITION_VERSION,
    MONITORING_CONTRACT_VERSION,
    bootstrap_mean_ci,
    canonical_hash,
    safe_rate,
    wilson_interval,
)
from app.services.production_monitoring.coverage import (  # noqa: F401
    coverage_funnel,
)
from app.services.production_monitoring.data_quality import (  # noqa: F401
    data_quality_report,
)
from app.services.production_monitoring.drift import drift_analysis  # noqa: F401
from app.services.production_monitoring.performance import (  # noqa: F401
    performance_overview,
    temporal_windows,
)
from app.services.production_monitoring.providers import (  # noqa: F401
    provider_report,
)
