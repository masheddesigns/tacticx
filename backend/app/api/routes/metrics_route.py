"""Prometheus metrics endpoint with internal exposure controls."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.config import get_settings
from app.observability.metrics import collector

router = APIRouter(tags=["metrics"])


@router.get("/metrics", summary="Prometheus metrics exposition")
def get_metrics(request: Request) -> Response:
    """Exposes Prometheus text format metrics.

    Controlled by METRICS_ENABLED. When METRICS_INTERNAL_ONLY is configured with
    a METRICS_TOKEN, requests must provide matching authorization.
    In containerized deployments, Nginx blocks external ingress to this route.
    """
    settings = get_settings()
    if not settings.METRICS_ENABLED:
        raise HTTPException(status_code=404, detail="Metrics disabled")

    if settings.METRICS_INTERNAL_ONLY and settings.METRICS_TOKEN:
        auth_header = request.headers.get("Authorization", "")
        internal_header = request.headers.get("X-Metrics-Token", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif internal_header:
            token = internal_header.strip()

        if token != settings.METRICS_TOKEN:
            raise HTTPException(status_code=403, detail="Unauthorized metrics access")

    content = collector.generate_prometheus_text()
    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
