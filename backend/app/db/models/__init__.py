"""Import all models here so Alembic autogenerate and Base.metadata see everything."""
from app.db.base import Base  # noqa: F401
from app.db.models.acquisition import (  # noqa: F401
    AcquisitionJob,
    AcquisitionRun,
    SourceActivation,
)
from app.db.models.core import (  # noqa: F401
    League,
    Lineup,
    Match,
    MatchEvent,
    MatchStatistic,
    Player,
    Standing,
    Team,
    TeamStatistic,
)
from app.db.models.freshness import MatchObservation  # noqa: F401
from app.db.models.intelligence import (  # noqa: F401
    AnalogueResult,
    MiroFishRun,
    PredictionExplanation,
    ScenarioRun,
)
from app.db.models.intelligence_v2 import IntelligenceSnapshot  # noqa: F401
from app.db.models.lifecycle import (  # noqa: F401
    PredictionDiff,
    PredictionEvaluation,
    PredictionVersion,
    SourceHealth,
)
from app.db.models.logs import DataSyncLog, ProviderRequestLog  # noqa: F401
from app.db.models.mirofish import MiroFishScenarioRun  # noqa: F401
from app.db.models.odds import Bookmaker, Market, OddsSelection, OddsSnapshot  # noqa: F401
from app.db.models.player_intelligence import (  # noqa: F401
    PlayerFeatureProvenance,
    PlayerFeatureSnapshot,
    PlayerTeamMembership,
)
from app.db.models.predictions import (  # noqa: F401
    BacktestRun,
    ModelEvaluation,
    ModelTrainingRun,
    Prediction,
    PredictionResult,
)
from app.db.models.provenance import (  # noqa: F401
    MatchSourceMapping,
    PlayerProviderMapping,
    RawDataRecord,
    SourceConflict,
    TeamProviderMapping,
)
from app.db.models.qualification import SourceQualification  # noqa: F401
from app.db.models.reconciliation import (  # noqa: F401
    CanonicalFieldVersion,
    ManualMapping,
    ReconciliationConflict,
    StatDefinition,
    UnresolvedRecord,
)
from app.db.models.prematch import PreMatchReadinessCertificate  # noqa: F401
from app.db.models.governance import (  # noqa: F401
    ModelApprovalRecord,
    ModelArtifact,
    ModelGovernanceEvent,
    ModelPromotionRequest,
    ModelRegistry,
    ModelValidationReport,
    ShadowPredictionSnapshot,
)
from app.db.models.research_registry import (  # noqa: F401
    ResearchCandidate,
    ResearchDataset,
    ResearchExperiment,
)
from app.db.models.evaluation_records import (  # noqa: F401
    MatchOutcomeSnapshot,
    PredictionEvaluationRecord,
)
from app.db.models.prediction_snapshots import (  # noqa: F401
    PredictionFeatureSnapshot,
    PreMatchPredictionSnapshot,
)
from app.db.models.research import ResearchModel  # noqa: F401
from app.db.models.scheduler import (  # noqa: F401
    AcquisitionJobLock,
    AcquisitionJobRecord,
)
