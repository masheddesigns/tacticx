# ==============================================================================
# TacticX Backend Production Dockerfile (Multi-Stage Build, Non-Root)
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

COPY pyproject.toml /build/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# --- Stage 2: Minimal, secure runtime ---
FROM python:3.12-slim AS runtime

# Install only runtime libpq library (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged system user & group (UID/GID 10001)
RUN addgroup --system --gid 10001 appgroup && \
    adduser --system --uid 10001 --ingroup appgroup --home /app --no-create-home appuser

WORKDIR /app

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Copy application source code with non-root ownership
COPY --chown=appuser:appgroup . /app

# Run as unprivileged user
USER appuser

EXPOSE 8000

# Native Python healthcheck (zero external curl/wget binary dependency)
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

# Graceful shutdown: Uvicorn responds to SIGTERM by stopping ingress and draining in-flight requests
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "15"]
