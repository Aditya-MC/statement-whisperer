# One image: builds the React app, then serves it and the API from FastAPI.
# Used by Render (see render.yaml); also runs anywhere Docker does.

# ---- 1. frontend build ------------------------------------------------------
# Debian-based (glibc) so Vite's native bundler binaries install cleanly.
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
# frontend/.npmrc points the cache at a Windows path; it is excluded via .dockerignore.
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. runtime ---------------------------------------------------------------
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    DATABASE_URL=sqlite:////app/data/ledger.db \
    FRONTEND_DIST=/app/frontend/dist \
    SAMPLES_DIR=/app/samples/synthetic

WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install .
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY samples/synthetic /app/samples/synthetic
COPY --from=frontend /app/frontend/dist /app/frontend/dist

RUN useradd --create-home --uid 1000 ledger && mkdir -p /app/data && chown -R ledger /app/data /app/backend
USER ledger

EXPOSE 8000
# 1. Apply database migrations (idempotent).
# 2. Serve on the port the host assigns ($PORT on Render).
#    --proxy-headers: behind Render's proxy, trust X-Forwarded-* so the real client IP
#      (used by rate limits) and https scheme are seen.
#    --no-access-log: request URLs can carry search terms (?q=...), so don't log them.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
