# ─────────────────────────────────────────────────────────────
#  Synclook — Multi-stage Docker Build
# ─────────────────────────────────────────────────────────────

# ---------- Stage 1: Builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install Poetry (2.x moved `poetry export` into a plugin)
RUN pip install --no-cache-dir poetry==2.3.3 poetry-plugin-export==1.10.1

# Copy dependency files first (cache layer)
COPY pyproject.toml poetry.lock* ./

# Export dependencies to requirements.txt (no dev deps)
RUN poetry export -f requirements.txt --without dev -o requirements.txt

# ---------- Stage 2: Runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r synclook && \
    useradd -r -g synclook -d /app -s /sbin/nologin synclook

# Install Python dependencies
COPY --from=builder /build/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY main.py .
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY data/demo_closet/ ./data/demo_closet/

RUN chown -R synclook:synclook /app

USER synclook

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/v1/health || exit 1

# The host sets PORT (Render: 10000). Migrations run at boot because Render's free plan has no
# pre-deploy command; on an up-to-date database it is one quick query.
# 1 worker: measured peak RSS 157 MB (smoke run + 10 visitors at once, 1,750 requests); a free instance has 512 MB, and the
# in-memory rate limits count per process.
# --forwarded-allow-ips '*': trust the host's proxy for the visitor IP (rate limits) and https (MCP URLs);
# only that proxy can reach the container.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips '*'"]
