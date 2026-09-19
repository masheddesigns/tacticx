"""Granular, bounded Prometheus metrics collector with zero external dependencies.

Enforces strict label cardinality limits. Never accepts raw query params,
IP addresses, or unnormalized identifiers as metric labels.
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from typing import Dict, Tuple

# Route normalization patterns to guarantee bounded metric cardinality
_ROUTE_NORMALIZERS = (
    (re.compile(r"^/api/v1/matches/\d+/intelligence(/.*)?$"), r"/api/v1/matches/{match_id}/intelligence\1"),
    (re.compile(r"^/api/v1/matches/\d+(/.*)?$"), r"/api/v1/matches/{match_id}\1"),
    (re.compile(r"^/api/v1/jobs/\d+$"), r"/api/v1/jobs/{job_id}"),
    (re.compile(r"^/api/v1/jobs/[a-zA-Z0-9_-]+/run$"), r"/api/v1/jobs/{job_type}/run"),
    (re.compile(r"^/api/v1/sources/[a-zA-Z0-9_-]+/qualify$"), r"/api/v1/sources/{source_id}/qualify"),
    (re.compile(r"^/api/v1/sources/[a-zA-Z0-9_-]+/status$"), r"/api/v1/sources/{source_id}/status"),
    (re.compile(r"^/api/v1/sources/[a-zA-Z0-9_-]+/qualification$"), r"/api/v1/sources/{source_id}/qualification"),
)

# Standard Prometheus histogram buckets for HTTP latency (seconds)
LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

MAX_CARDINALITY_ENTRIES = 500


class MetricsCollector:
    """Thread-safe Prometheus metrics store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (method, route, status) -> count
        self._http_requests: Dict[Tuple[str, str, str], int] = defaultdict(int)
        # (method, route) -> list of [sum, count, bucket_counts]
        self._http_durations: Dict[Tuple[str, str], list] = {}
        # (job_type, status) -> count
        self._job_counts: Dict[Tuple[str, str], int] = defaultdict(int)

    def normalize_route(self, path: str) -> str:
        """Strip query parameters and convert dynamic IDs into static route templates."""
        clean = path.split("?")[0].rstrip("/") or "/"
        for pattern, template in _ROUTE_NORMALIZERS:
            if pattern.match(clean):
                clean = pattern.sub(template, clean)
        # Bounded cardinality protection: normalize any remaining numeric IDs and hashes
        clean = re.sub(r"/(\d+)(?=/|$)", r"/{id}", clean)
        clean = re.sub(r"/snapshots/[a-zA-Z0-9_-]+", r"/snapshots/{snapshot_id}", clean)
        return clean

    def record_http_request(self, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        route = self.normalize_route(path)
        method_norm = method.upper()
        status_str = str(status_code)

        with self._lock:
            key = (method_norm, route, status_str)
            if len(self._http_requests) < MAX_CARDINALITY_ENTRIES or key in self._http_requests:
                self._http_requests[key] += 1

            dur_key = (method_norm, route)
            if dur_key not in self._http_durations:
                if len(self._http_durations) < MAX_CARDINALITY_ENTRIES:
                    # [sum, count, {le: count}]
                    bucket_counts = {b: 0 for b in LATENCY_BUCKETS}
                    self._http_durations[dur_key] = [0.0, 0, bucket_counts]
            if dur_key in self._http_durations:
                entry = self._http_durations[dur_key]
                entry[0] += duration_seconds
                entry[1] += 1
                for b in LATENCY_BUCKETS:
                    if duration_seconds <= b:
                        entry[2][b] += 1

    def record_job_execution(self, job_type: str, status: str) -> None:
        safe_job = (job_type or "unknown")[:32]
        safe_status = (status or "unknown")[:32]
        with self._lock:
            key = (safe_job, safe_status)
            if len(self._job_counts) < 100 or key in self._job_counts:
                self._job_counts[key] += 1

    def generate_prometheus_text(self) -> str:
        """Render metrics in Prometheus text exposition format (version 0.0.4)."""
        lines = []

        # 1. HTTP Request Total
        lines.append("# HELP http_requests_total Total number of HTTP requests processed")
        lines.append("# TYPE http_requests_total counter")
        with self._lock:
            req_items = list(self._http_requests.items())
            dur_items = list(self._http_durations.items())
            job_items = list(self._job_counts.items())

        for (method, route, status), count in sorted(req_items):
            lines.append(f'http_requests_total{{method="{method}",route="{route}",status="{status}"}} {count}')

        # 2. HTTP Request Duration Histogram
        lines.append("# HELP http_request_duration_seconds HTTP request duration in seconds")
        lines.append("# TYPE http_request_duration_seconds histogram")
        for (method, route), (total_sum, count, bucket_counts) in sorted(dur_items):
            for b in LATENCY_BUCKETS:
                b_count = bucket_counts[b]
                lines.append(f'http_request_duration_seconds_bucket{{method="{method}",route="{route}",le="{b}"}} {b_count}')
            lines.append(f'http_request_duration_seconds_bucket{{method="{method}",route="{route}",le="+Inf"}} {count}')
            lines.append(f'http_request_duration_seconds_sum{{method="{method}",route="{route}"}} {total_sum:.6f}')
            lines.append(f'http_request_duration_seconds_count{{method="{method}",route="{route}"}} {count}')

        # 3. System dependency health
        lines.append("# HELP tacticx_database_connected Database connectivity state (1=up, 0=down)")
        lines.append("# TYPE tacticx_database_connected gauge")
        db_up = self._check_db()
        lines.append(f"tacticx_database_connected {1 if db_up else 0}")

        lines.append("# HELP tacticx_cache_active Cache backend active (1=redis, 0=memory fallback)")
        lines.append("# TYPE tacticx_cache_active gauge")
        cache_state = self._check_cache()
        lines.append(f'tacticx_cache_active{{backend="{cache_state}"}} 1')

        # 4. Scheduler Jobs
        lines.append("# HELP tacticx_scheduler_jobs_total Total scheduler jobs executed by type and terminal status")
        lines.append("# TYPE tacticx_scheduler_jobs_total counter")
        for (job_type, status), count in sorted(job_items):
            lines.append(f'tacticx_scheduler_jobs_total{{job_type="{job_type}",status="{status}"}} {count}')

        # 5. Process uptime
        lines.append("# HELP tacticx_uptime_seconds Process uptime in seconds")
        lines.append("# TYPE tacticx_uptime_seconds gauge")
        uptime = time.time() - _PROCESS_START_TIME
        lines.append(f"tacticx_uptime_seconds {uptime:.1f}")

        return "\n".join(lines) + "\n"

    def _check_db(self) -> bool:
        try:
            from app.db.session import get_engine
            from sqlalchemy import text
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def _check_cache(self) -> str:
        try:
            from app.services.caching.cache import backend_name
            return backend_name()
        except Exception:
            return "unknown"


_PROCESS_START_TIME = time.time()
collector = MetricsCollector()
