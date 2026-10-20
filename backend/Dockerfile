# The build context is the repo root (context: .. in docker compose) so data/ goes into the image:
# product catalog, knowledge base, benefits and demo customers all live in data/, read from <repo root>/data (/data in the container).
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ ./
COPY data/ /data/
EXPOSE 8000
# The app writes its own access log (with request IDs; JSON in production), so uvicorn's plain-text access log is off to avoid duplicates
CMD ["sh", "-c", "uv run --no-dev alembic upgrade head && uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
