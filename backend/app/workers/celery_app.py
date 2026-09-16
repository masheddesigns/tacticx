"""Celery app + beat schedule driven by match lifecycle + config TTLs.

- fixtures far from kickoff: every TTL_FIXTURES_FAR
- approaching kickoff: every TTL_FIXTURES_NEAR / TTL_PRE_MATCH
- live matches: every TTL_LIVE
Finished matches are never live-polled; historical data is kept permanently.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import schedule

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "bet_predictor",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "sync-fixtures-far": {
            "task": "app.workers.tasks.sync_fixtures_task",
            "schedule": schedule(run_every=settings.TTL_FIXTURES_FAR),
        },
        "sync-live": {
            "task": "app.workers.tasks.sync_live_task",
            "schedule": schedule(run_every=settings.TTL_LIVE),
        },
        "sync-odds": {
            "task": "app.workers.tasks.sync_odds_task",
            "schedule": schedule(run_every=settings.TTL_PRE_MATCH),
        },
    },
)
