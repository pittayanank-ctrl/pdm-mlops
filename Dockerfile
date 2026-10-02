FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# libgomp1: OpenMP runtime for xgboost; curl: container healthcheck; git: code version in MLflow
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl git \
    && rm -rf /var/lib/apt/lists/*

# dependencies first so code changes don't invalidate this layer
COPY requirements.txt requirements.lock ./
RUN pip install -r requirements.txt -c requirements.lock

COPY pyproject.toml ./
COPY configs ./configs
COPY scripts ./scripts
COPY src ./src
RUN mkdir -p data logs reports

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["sh", "scripts/start_api.sh"]
