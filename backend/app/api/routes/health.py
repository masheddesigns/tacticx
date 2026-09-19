from __future__ import annotations

from fastapi import APIRouter, Response

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Process liveness probe")
@router.get("/health", summary="Health check (legacy / live)")
def health_live() -> dict:
    """Liveness probe: returns 200 if the process is responsive.
    Does not depend on external systems."""
    return {"status": "ok", "live": True, "service": "tacticx-backend"}


@router.get("/health/ready", summary="Dependency readiness probe")
@router.get("/ready", summary="Readiness probe (legacy)")
def health_ready(response: Response) -> dict:
    """Readiness probe: validates critical dependencies.
    - Database is critical (fails with 503 if unreachable).
    - Redis is non-fatal: cache gracefully falls back to memory and does not fail readiness."""
    checks = {}
    db_ok = False

    # 1. Database check (CRITICAL)
    try:
        from app.db.session import get_engine
        from sqlalchemy import text

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
        db_ok = False

    # 2. Cache check (NON-FATAL)
    try:
        from app.services.caching.cache import backend_name, cache_get, cache_set

        cache_set("__ready_probe__", "1", 10)
        cache_val = cache_get("__ready_probe__")
        b_name = backend_name()
        if cache_val == "1":
            checks["cache"] = "ok" if b_name == "redis" else "memory_fallback"
        else:
            checks["cache"] = "degraded"
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = f"error: {exc}"

    if not db_ok:
        response.status_code = 503
        status = "unhealthy"
    elif checks.get("cache") == "ok":
        status = "ok"
    else:
        status = "degraded"

    return {"status": status, "checks": checks}
