# Single image: builds the React app, then serves it and the API from FastAPI on :8000.
# UNTESTED: Docker isn't installed on the dev machine yet (see README).

# ---- 1. frontend build ------------------------------------------------------
FROM node:22-alpine AS frontend
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
# Apply migrations on every start (idempotent), then serve.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
