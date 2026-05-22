FROM node:20-slim AS frontend-builder

WORKDIR /build
COPY src/astra/ui/frontend/package.json src/astra/ui/frontend/package-lock.json ./
RUN npm install
COPY src/astra/ui/frontend/ ./
RUN npm run build

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
 && rm -rf /var/lib/apt/lists/* \
 && addgroup --system --gid 1001 appuser \
 && adduser --system --uid 1001 --gid 1001 --no-create-home appuser

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1
COPY pyproject.toml .
RUN pip install uv \
 && uv sync --no-dev --no-install-project
COPY src/ src/
COPY --from=frontend-builder /build/build /app/src/astra/ui/frontend/build
RUN uv sync --no-dev

COPY .env.example .env

RUN mkdir -p /data/builds /data/exports /data/db \
 && chown -R appuser:appuser /app /data

USER appuser

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "astra.ui.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
