"""Central application configuration — every tunable lives here (env vars), never hard-coded."""
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg2://bet:bet@localhost:5432/betpredictor"
    REDIS_URL: str = "redis://localhost:6379/0"

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:3000"

    FOOTBALL_PROVIDER: str = "api_football"
    FOOTBALL_API_KEY: str = ""
    FOOTBALL_API_BASE_URL: str = "https://v3.football.api-sports.io"

    ODDS_PROVIDER: str = "odds_api"
    ODDS_API_KEY: str = ""
    ODDS_API_BASE_URL: str = "https://api.the-odds-api.com/v4"
    ODDS_REGIONS: str = "uk,eu"
    # NOTE: The Odds API has no BTTS market — valid keys include h2h, spreads, totals.
    ODDS_MARKETS: str = "h2h,totals"

    SUPPORTED_LEAGUES: str = (
        "EPL:39:2024,LA_LIGA:140:2024,SERIE_A:135:2024,"
        "BUNDESLIGA:78:2024,LIGUE_1:61:2024,UCL:2:2024"
    )

    # Cache TTLs (seconds)
    TTL_FIXTURES_FAR: int = 21600
    TTL_FIXTURES_NEAR: int = 3600
    TTL_PRE_MATCH: int = 900
    TTL_LINEUPS: int = 600
    TTL_LIVE: int = 30
    TTL_FINISHED: int = 86400
    NEAR_KICKOFF_HOURS: int = 24

    # Quota protection
    PROVIDER_MAX_REQUESTS_PER_MINUTE: int = 25
    PROVIDER_MAX_REQUESTS_PER_DAY: int = 7000
    PROVIDER_RETRY_ATTEMPTS: int = 4
    PROVIDER_RETRY_BASE_SECONDS: float = 1.0
    PROVIDER_TIMEOUT_SECONDS: float = 20.0

    # MiroFish scenario layer (optional; safe defaults when unconfigured).
    MIROFISH_ENABLED: bool = False
    MIROFISH_ENDPOINT: str = ""
    MIROFISH_API_KEY: str = ""
    MIROFISH_TIMEOUT_SECONDS: float = 20.0
    MIROFISH_RETRY_ATTEMPTS: int = 2
    MIROFISH_RETRY_BASE_SECONDS: float = 1.0
    MIROFISH_MAX_SCENARIOS: int = 7
    MIROFISH_CONTRACT_VERSION: str = "mirofish_contract_v1"
    MIROFISH_RESPONSE_MAX_BYTES: int = 65536

    # --- Phase 3: market intelligence (analytical only, never betting) ---
    # Consensus aggregates no-vig probabilities across bookmakers.
    ODDS_CONSENSUS_METHOD: str = "median"  # median | mean | trimmed_mean
    # Snapshots within this window count as simultaneous for best-price views.
    ODDS_CONSENSUS_TIME_WINDOW_MINUTES: int = 5
    # Minimum bookmakers required to publish a consensus.
    ODDS_CONSENSUS_MIN_BOOKMAKERS: int = 2
    # Price moves smaller than this (decimal) are noise, not movement.
    ODDS_MOVEMENT_FLAT_TOLERANCE: float = 0.005
    # Velocity needs a meaningful interval: bulk imports stamp batches
    # milliseconds apart, which would annualize into nonsense. Intervals
    # below this (seconds) yield velocity None (movement still recorded).
    ODDS_MIN_VELOCITY_INTERVAL_SECONDS: float = 60.0
    # Model-vs-market agreement bands (absolute probability points).
    MODEL_MARKET_NEUTRAL_THRESHOLD: float = 0.03
    MODEL_MARKET_STRONG_THRESHOLD: float = 0.08

    # --- Phase 7: live pipeline + prediction lifecycle (analytical only) ---
    # Upcoming-match discovery window (hours ahead). Never hard-coded elsewhere.
    NEXT_MATCH_LOOKAHEAD_HOURS: int = 168
    # Odds re-poll interval floor (minutes). Polls must not run more often.
    ODDS_REFRESH_INTERVAL_MINUTES: int = 15
    # Per-provider rate limits (requests/minute). The limiter reads these by
    # provider name and falls back to PROVIDER_MAX_REQUESTS_PER_MINUTE.
    API_FOOTBALL_RATE_LIMIT_PER_MINUTE: int = 25
    ODDS_API_RATE_LIMIT_PER_MINUTE: int = 25
    # Cache TTLs for lifecycle reads (seconds).
    UPCOMING_FIXTURES_CACHE_TTL_SECONDS: int = 900
    CURRENT_ODDS_CACHE_TTL_SECONDS: int = 300
    SOURCE_META_CACHE_TTL_SECONDS: int = 3600
    # Monitoring: rolling windows and drift bands (descriptive, never switching).
    MONITOR_ROLLING_WINDOWS: str = "50,100"
    DRIFT_WATCH_BRIER_DELTA: float = 0.02
    DRIFT_DEGRADED_BRIER_DELTA: float = 0.05

    # --- Phase 8: reconciliation (evidence preserved, never silently merged) ---
    # Kickoff differences within this tolerance merge; larger ones conflict.
    MATCH_KICKOFF_TOLERANCE_MINUTES: int = 15
    # Event matching window across sources (seconds).
    EVENT_TIME_TOLERANCE_SECONDS: int = 30
    # Field-level source authority ("field:source;..."). No universal winner:
    # each field names its authoritative source explicitly and reviewably.
    FIELD_SOURCE_PRIORITY: str = (
        "score:api_football;status:api_football;kickoff:api_football;"
        "xg:statsbomb;odds:odds_api;closing_odds:football_data_co_uk"
    )

    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- Phase 1.6: source-agnostic data layer ---
    # APIs are optional fallback/validation sources; bulk data comes from
    # dataset/scraper adapters. Names are resolved via the source registry.
    FOOTBALL_SOURCE_PRIMARY: str = "api_football"
    FOOTBALL_SOURCE_FALLBACK: str = ""
    ODDS_SOURCE_PRIMARY: str = "odds_api"
    ODDS_SOURCE_FALLBACK: str = ""
    HISTORICAL_SOURCE: str = "csv"
    # Source priority for conflict reconciliation (first wins), comma-separated.
    SOURCE_PRIORITY: str = "api_football,football_data_co_uk,csv,odds_api"

    # Polite scraping constraints (never bypass rate limits / protections).
    SCRAPER_MIN_DELAY_SECONDS: float = 2.0
    SCRAPER_MAX_REQUESTS_PER_MINUTE: int = 20
    SCRAPER_TIMEOUT_SECONDS: float = 20.0
    SCRAPER_CACHE_TTL_SECONDS: int = 3600
    SCRAPER_USER_AGENT: str = "BetPredictor/1.6 (+personal-analysis; polite fetcher)"
    DATASET_BASE_URL: str = "https://football-data.co.uk/mmz4281"
    # StatsBomb Open Data (public research use with attribution). Raw GitHub
    # JSON: competitions.json, matches/{comp}/{season}.json, events/{match}.json.
    STATSBOMB_BASE_URL: str = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
    # Local dataset cache (downloaded season files). Never committed.
    DATA_DIR: str = "data"

    # Explicit team-name aliases only (JSON object: variant -> canonical).
    # Deterministic, manually curated from real cross-source evidence —
    # never fuzzy-matched. Canonicals are full names; import StatsBomb
    # seasons before football-data.co.uk to establish them first.
    TEAM_ALIASES_JSON: str = (
        '{"Ipswich Town": "Ipswich", '
        '"Wolves": "Wolverhampton Wanderers", '
        '"Man United": "Manchester United", "Man City": "Manchester City", '
        '"Bournemouth": "AFC Bournemouth", '
        '"Leicester": "Leicester City", "Newcastle": "Newcastle United", '
        '"Tottenham": "Tottenham Hotspur", "West Ham": "West Ham United", '
        '"Ath Bilbao": "Athletic Club", "Ath Madrid": "Atlético Madrid", '
        '"Celta": "Celta Vigo", "Vallecano": "Rayo Vallecano", '
        '"Sociedad": "Real Sociedad", "Betis": "Real Betis", '
        '"Espanol": "Espanyol", "La Coruna": "RC Deportivo La Coruña", '
        '"Levante": "Levante UD", "Sp Gijon": "Sporting Gijón", '
        '"Dortmund": "Borussia Dortmund", '
        '"M\'gladbach": "Borussia Mönchengladbach", '
        '"Leverkusen": "Bayer Leverkusen", '
        '"Ein Frankfurt": "Eintracht Frankfurt", '
        '"Darmstadt": "Darmstadt 98", "Mainz": "FSV Mainz 05", '
        '"Heidenheim": "FC Heidenheim", "Stuttgart": "VfB Stuttgart"}'
    )
    # Explicit player-name aliases (variant -> canonical). Same rules as teams.
    PLAYER_ALIASES_JSON: str = "{}"

    # Raw provenance payload retention (days). 0 = keep indefinitely.
    RAW_RETENTION_DAYS: int = 90

    # --- Phase 4: feature engineering + advanced models ---
    # All decays expressed as half-lives (days); converted via decay = ln(2)/half_life.
    FORM_DECAY_HALF_LIFE_DAYS: float = 120.0
    XG_DECAY_HALF_LIFE_DAYS: float = 180.0
    MIN_FORM_MATCHES: int = 3
    MIN_XG_MATCHES: int = 5
    MIN_H2H_MATCHES: int = 3
    # Multinomial logistic regression (numpy, deterministic full-batch GD).
    ML_L2: float = 1.0
    ML_LEARNING_RATE: float = 0.5
    ML_ITERATIONS: int = 2000
    # Ensemble weight grid search step over the simplex (deterministic).
    ENSEMBLE_GRID_STEP: float = 0.1
    # Temperature calibration (calibration_v1) needs a minimum fit sample.
    CALIBRATION_MIN_SAMPLE: int = 50
    # Bootstrap confidence intervals for reported metrics.
    BOOTSTRAP_SAMPLES: int = 1000
    BOOTSTRAP_SEED: int = 7

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_football_configured(self) -> bool:
        return bool(self.FOOTBALL_API_KEY.strip())

    @property
    def is_odds_configured(self) -> bool:
        return bool(self.ODDS_API_KEY.strip())

    @property
    def is_mirofish_configured(self) -> bool:
        return bool(self.MIROFISH_ENABLED and self.MIROFISH_ENDPOINT.strip())

    def diagnose(self) -> dict:
        """Safe diagnostics: presence only — NEVER include secret values."""
        return {
            "FOOTBALL_API_KEY": "configured" if self.is_football_configured else "missing",
            "ODDS_API_KEY": "configured" if self.is_odds_configured else "missing",
            "MIROFISH": "configured" if self.is_mirofish_configured else "missing",
            "DATABASE": "configured" if self.DATABASE_URL else "missing",
            "REDIS": "configured" if self.REDIS_URL else "missing",
            "football_provider": self.FOOTBALL_PROVIDER,
            "odds_provider": self.ODDS_PROVIDER,
            "environment": self.ENVIRONMENT,
        }

    def supported_leagues_parsed(self) -> list[dict]:
        """Parse 'CODE:provider_id:season' entries so leagues change without code edits."""
        out: list[dict] = []
        for entry in self.SUPPORTED_LEAGUES.split(","):
            parts = entry.strip().split(":")
            if len(parts) == 3:
                code, pid, season = parts
                out.append({"code": code, "provider_id": pid, "season": season})
        return out

    @property
    def source_priority_list(self) -> list[str]:
        return [s.strip().lower() for s in self.SOURCE_PRIORITY.split(",") if s.strip()]

    @property
    def team_aliases(self) -> dict:
        import json as _json

        try:
            raw = _json.loads(self.TEAM_ALIASES_JSON or "{}")
        except ValueError:
            return {}
        return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}

    @property
    def player_aliases(self) -> dict:
        import json as _json

        try:
            raw = _json.loads(self.PLAYER_ALIASES_JSON or "{}")
        except ValueError:
            return {}
        return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
