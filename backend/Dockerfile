FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir uv && uv sync --no-dev

COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/

RUN addgroup --system --gid 1001 quorum && \
    adduser --system --uid 1001 --ingroup quorum --no-create-home --home /app quorum && \
    mkdir -p /tmp/uv-cache && chown quorum:quorum /tmp/uv-cache && \
    chown -R quorum:quorum /app

ENV UV_CACHE_DIR=/tmp/uv-cache
USER quorum

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
