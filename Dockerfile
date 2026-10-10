# ==============================================================================
# TacticX Production Dockerfile (Backend on Render, Railway & Cloud Hosts)
# ==============================================================================

# --- Stage 1: Build & wheels compilation ---
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/pyproject.toml /build/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# --- Stage 2: Minimal, secure runtime ---
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 10001 appgroup && \
    adduser --system --uid 10001 --ingroup appgroup --home /app --no-create-home appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

COPY --chown=appuser:appgroup backend/ /app

USER appuser

EXPOSE 8000
EXPOSE 10000

# Native Python healthcheck
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", 8000)}/health/live')" || exit 1

# Render dynamically injects $PORT (defaults to 10000). Bind to $PORT or default to 8000.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-graceful-shutdown 15"]
