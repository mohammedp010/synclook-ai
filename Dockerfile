# ─────────────────────────────────────────────────────────────
#  Synclook — Multi-stage Docker Build
# ─────────────────────────────────────────────────────────────

# ---------- Stage 1: Builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install Poetry
RUN pip install --no-cache-dir poetry==2.3.3

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

# Create upload directory
RUN mkdir -p /app/uploads && chown -R synclook:synclook /app

USER synclook

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
