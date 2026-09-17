"""Import all models here so Alembic autogenerate and Base.metadata see everything."""
from app.db.base import Base  # noqa: F401
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
from app.db.models.logs import DataSyncLog, ProviderRequestLog  # noqa: F401
from app.db.models.lifecycle import (  # noqa: F401
    PredictionDiff,
    PredictionEvaluation,
    PredictionVersion,
    SourceHealth,
)
from app.db.models.intelligence import (  # noqa: F401
    AnalogueResult,
    MiroFishRun,
    PredictionExplanation,
    ScenarioRun,
)
from app.db.models.odds import Bookmaker, Market, OddsSelection, OddsSnapshot  # noqa: F401
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
