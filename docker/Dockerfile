# Stage 1: Build React SPA
FROM node:20-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --ignore-scripts; else npm install --ignore-scripts; fi
COPY frontend/ ./
RUN mkdir -p /build/backend/app/static && npm run build

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && mkdir -p /data && chown appuser:appuser /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ ./app/
COPY --from=frontend-build /build/backend/app/static/ ./app/static/

RUN chown -R appuser:appuser /app

USER appuser

ENV AI_NEWS_DB_PATH=/data/ainews.db \
    AI_NEWS_DATA_DIR=/data \
    AI_NEWS_SEED_PATH=/app/seed/sources.json \
    AI_NEWS_LOG_LEVEL=INFO

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
