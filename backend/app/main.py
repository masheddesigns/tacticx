"""FastAPI application entrypoint with production middleware and observability."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import (
    MetricsAndAccessLoggingMiddleware,
    RateLimitingMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from app.api.routes import (
    acquisition,
    catalog,
    health,
    intelligence,
    jobs,
    lifecycle,
    markets,
    match_intelligence,
    matches,
    metrics_route,
    mirofish,
    model_governance,
    monitoring,
    odds,
    player_features,
    prediction_evaluation,
    prediction_execution,
    predictions,
    reconciliation,
    research,
    sources,
    sync,
    validation,
    version_route,
)
from app.config import get_settings
from app.logging_config import configure_logging
from app.version import get_version_info

settings = get_settings()
settings.validate_production()
configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

app = FastAPI(
    title="Football Prediction & Market Intelligence Engine",
    version="0.1.0",
    description="TacticX Phase 22: Production-deployable and observable analytical intelligence engine.",
)

# Middleware registration:
# Starlette executes middlewares in reverse addition order:
# Request -> RequestID -> SecurityHeaders -> CORS -> RateLimiting -> Metrics & Access -> App
app.add_middleware(MetricsAndAccessLoggingMiddleware)
app.add_middleware(
    RateLimitingMiddleware,
    max_requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
    exempt_testclient=(settings.ENVIRONMENT.lower() != "production"),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

# Root observability & health endpoints
app.include_router(health.router)
app.include_router(metrics_route.router)
app.include_router(version_route.router)

# API v1 routes
prefix = settings.API_V1_PREFIX
app.include_router(health.router, prefix=prefix)
app.include_router(version_route.router, prefix=prefix)
app.include_router(matches.router, prefix=prefix)
app.include_router(catalog.router, prefix=prefix)
app.include_router(odds.router, prefix=prefix)
app.include_router(markets.router, prefix=prefix)
app.include_router(predictions.router, prefix=prefix)
app.include_router(sync.router, prefix=prefix)
app.include_router(validation.router, prefix=prefix)
app.include_router(lifecycle.router, prefix=prefix)
app.include_router(reconciliation.router, prefix=prefix)
app.include_router(research.router, prefix=prefix)
app.include_router(player_features.router, prefix=prefix)
app.include_router(prediction_execution.router, prefix=prefix)
app.include_router(prediction_evaluation.router, prefix=prefix)
app.include_router(intelligence.router, prefix=prefix)
app.include_router(monitoring.router, prefix=prefix)
app.include_router(model_governance.router, prefix=prefix)
app.include_router(mirofish.router, prefix=prefix)
app.include_router(match_intelligence.router, prefix=prefix)
app.include_router(acquisition.router, prefix=prefix)
app.include_router(sources.router, prefix=prefix)
app.include_router(jobs.router, prefix=prefix)


@app.get("/", include_in_schema=False)
def root() -> dict:
    v_info = get_version_info()
    return {
        "service": "bet-predictor",
        "version": v_info.get("version", "0.1.0"),
        "commit": v_info.get("commit", "unknown"),
        "docs": "/docs",
        "health": "/health/live",
        "ready": "/health/ready",
        "metrics": "/metrics",
        "version_info": "/version",
    }
