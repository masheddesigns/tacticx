from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health check")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe (DB + Redis)")
def ready() -> dict:
    checks = {}
    try:
        from app.db.session import get_engine
        from sqlalchemy import text

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
    try:
        from app.services.caching.cache import cache_set, cache_get

        cache_set("__ready_probe__", "1", 10)
        checks["cache"] = "ok" if cache_get("__ready_probe__") == "1" else "error"
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = f"error: {exc}"
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
