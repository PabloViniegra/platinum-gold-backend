# The Binding of Isaac API

FastAPI backend for structured data from The Binding of Isaac. PostgreSQL is
the source of truth and Redis provides disposable runtime infrastructure.

This repository currently contains the executable foundation described in
`tasks/spec.md`, plus Clerk API-key authentication described in
`tasks/spec-auth.md`. Item resources, caching, rate limiting, and ingestion
are not implemented yet.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose

## Local Setup

```bash
uv sync --all-groups
cp .env.example .env
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The API documentation is available at `http://127.0.0.1:8000/docs`.

## Health Checks

`GET /health` is a liveness check and does not contact infrastructure.

```json
{"status":"ok"}
```

`GET /health/ready` checks PostgreSQL and Redis. It returns `200` when both are
available and `503` with a generic error plus sanitized dependency states when
either dependency is unavailable.

Every response includes `X-Request-ID`. A valid client-provided request ID is
preserved; otherwise the API generates a UUID.

## Quality Gates

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

Apply and roll back migrations with:

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
```

Production schema changes must use Alembic. The application never creates
tables automatically at startup.

## Configuration

| Variable | Required | Purpose |
|---|---:|---|
| `DATABASE_URL` | Yes | Async SQLAlchemy URL using `postgresql+asyncpg` |
| `REDIS_URL` | Yes | Redis URL using `redis` or `rediss` |
| `CLERK_SECRET_KEY` | No | Clerk Backend secret for protected routes. Missing values fail closed. |
| `ENVIRONMENT` | No | `development`, `test`, or `production` |
| `LOG_LEVEL` | No | Python log level, defaults to `INFO` |

Remote production URLs must use encrypted connections: TLS is required for
PostgreSQL and Redis must use `rediss://`. Local loopback connections may remain
unencrypted for development.

Do not embed API keys intended for server-to-server use in public browser
JavaScript.

## Project Layout

```text
app/
|-- core/       # Configuration and runtime infrastructure
|-- health/     # Liveness and readiness feature
`-- main.py     # FastAPI application factory and lifespan
alembic/        # Database migrations
tests/          # Unit and API tests
tasks/          # Approved specification and implementation plan
```
