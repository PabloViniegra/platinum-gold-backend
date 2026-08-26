# The Binding of Isaac API

FastAPI backend for structured data from The Binding of Isaac. PostgreSQL is
the source of truth and Redis provides disposable runtime infrastructure.

This repository currently contains the executable foundation described in
`tasks/spec.md`, Clerk API-key authentication described in `tasks/spec-auth.md`,
the authenticated read API for items, and the offline ingestion flow described
in `tasks/spec-initial-ingestion.md`. Caching and rate limiting are not
implemented yet.

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

## Offline Ingestion

Platinum God is the upstream source. Ingestion runs offline from an explicit,
versioned JSON snapshot and never scrapes or contacts the upstream source from
the API runtime.

After configuring `DATABASE_URL` and `REDIS_URL` in `.env`, publish the example
snapshot with:

```bash
uv run python -m scripts.ingest --input data/items.example.json
```

The command validates the complete snapshot before opening a transaction,
upserts items by `gameId`, preserves records absent from the snapshot, and
updates dataset metadata only after the full transaction succeeds. Invalid
input or a database failure exits non-zero without publishing partial data.
The snapshot contract and update policy are documented in
`tasks/spec-initial-ingestion.md`.

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

Pull requests and pushes to `main` run the quality gates and the PostgreSQL
integration job from `.github/workflows/ci.yml`.

Run PostgreSQL integration tests against an explicit database with:

```bash
docker compose exec -T postgres psql -U postgres -d postgres -c 'CREATE DATABASE isaac_api_test;'
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api make integration
```

The integration target only accepts local PostgreSQL databases whose name ends
in `_test`, and applies migrations before running. Integration tests are opt-in
so the regular test suite does not require Docker or a live database.

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
|-- ingestion/  # Offline snapshot validation and persistence
|-- items/      # Item model and authenticated read API
|-- meta/       # Dataset metadata model
`-- main.py     # FastAPI application factory and lifespan
alembic/        # Database migrations
data/           # Non-authoritative local example snapshots
scripts/        # Offline administrative commands
tests/          # Unit, API, and opt-in integration tests
tasks/          # Approved specification and implementation plan
```
