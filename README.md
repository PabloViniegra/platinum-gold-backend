<div align="center">

<img src="https://img.shields.io/badge/THE%20BINDING%20OF%20ISAAC-API-2A0A14?style=for-the-badge&labelColor=1A0610&color=8B0000&logo=fastapi&logoColor=FFFFFF" alt="The Binding of Isaac API" />

<br />

<img src="https://upload.wikimedia.org/wikipedia/en/thumb/a/a2/The_Binding_of_Isaac-_Rebirth.jpg/640px-The_Binding_of_Isaac-_Rebirth.jpg" alt="The Binding of Isaac cover art" width="640" />

<br />

<p><strong>A typed, authenticated read API for the catalog dataset of The Binding of Isaac.</strong></p>

<p>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=FFFFFF" alt="Python 3.13" /></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.141-009688?style=flat-square&logo=fastapi&logoColor=FFFFFF" alt="FastAPI" /></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-17-4169E1?style=flat-square&logo=postgresql&logoColor=FFFFFF" alt="PostgreSQL 17" /></a>
  <a href="https://redis.io/"><img src="https://img.shields.io/badge/Redis-8-DC382D?style=flat-square&logo=redis&logoColor=FFFFFF" alt="Redis 8" /></a>
  <a href="https://clerk.com/"><img src="https://img.shields.io/badge/Auth-Clerk-6C47FF?style=flat-square&logo=clerk&logoColor=FFFFFF" alt="Clerk auth" /></a>
  <a href="https://docs.astral.sh/uv/"><img src="https://img.shields.io/badge/uv-managed-DE5FE9?style=flat-square&logo=uv&logoColor=FFFFFF" alt="uv" /></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=FFFFFF" alt="Docker Compose" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22C55E?style=flat-square" alt="MIT License" /></a>
</p>

</div>

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Local Setup](#local-setup)
- [Offline Ingestion](#offline-ingestion)
- [API](#api)
- [Health Checks](#health-checks)
- [Cache Behavior](#cache-behavior)
- [Quality Gates](#quality-gates)
- [Configuration](#configuration)
- [Project Layout](#project-layout)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Overview

This repository implements the executable foundation described in `tasks/spec.md`,
the Clerk API-key authentication layer described in `tasks/spec-auth.md`, the
authenticated read API for items, the generational Redis cache, and the offline
ingestion flow described in `tasks/spec-initial-ingestion.md`. Rate limiting is
not implemented yet.

The service exposes structured catalog data for **The Binding of Isaac**.
PostgreSQL is the source of truth. Redis provides disposable runtime
infrastructure for cache-aside reads. The dataset is published offline from an
explicit, versioned JSON snapshot; the API runtime never scrapes or contacts
the upstream source.

## Architecture

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.13 | Strict type checking with Pyright |
| Web framework | FastAPI | Async, OpenAPI 3.1 |
| Database | PostgreSQL 17 | Async SQLAlchemy 2.0 with `asyncpg` |
| Migrations | Alembic | Authoritative schema changes |
| Cache | Redis 8 | Cache-aside, generational invalidation |
| Auth | Clerk Backend API | API-key bearer, fail-closed |
| Settings | Pydantic Settings | Strict URL validation |
| Packaging | `uv` | Locked workspace with dev group |
| Local infra | Docker Compose | PostgreSQL + Redis only |

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

The interactive API documentation is available at
`http://127.0.0.1:8000/docs`.

A Makefile shortcut wraps the same flow:

```bash
make setup     # locked dependency install
make up        # start PostgreSQL and Redis
make migrate   # apply pending migrations
make dev       # run the development server
```

## Offline Ingestion

Platinum God is the upstream source. Ingestion runs offline from an explicit,
versioned JSON snapshot and never scrapes or contacts the upstream source from
the API runtime.

After configuring `DATABASE_URL` and `REDIS_URL` in `.env`, publish an explicit
snapshot with:

```bash
make ingest SNAPSHOT=/path/to/items.json
```

The command is manual by design; there is no automatic synchronization job.
Replace `/path/to/items.json` with the prepared snapshot path; it is not a
repository file.

The command validates the complete snapshot before opening a transaction,
upserts items by `gameId`, preserves records absent from the snapshot, and
updates dataset metadata only after the full transaction succeeds. After the
PostgreSQL transaction commits, the command increments the shared Redis cache
generation so old entries become unreachable. A run that is not newer than the
recorded synchronization is a successful no-op, so an older run cannot replace
committed data. The command does not infer ordering from the opaque
`datasetVersion` label. Invalid input or a database failure exits non-zero
without publishing partial data. If PostgreSQL commits but Redis invalidation
fails, the command exits non-zero with a sanitized partial-state message;
repeat the ingestion to retry invalidation.

The snapshot contract and update policy are documented in
`tasks/spec-initial-ingestion.md`.

## API

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Liveness probe |
| `GET` | `/health/ready` | None | Readiness probe (PostgreSQL + Redis) |
| `GET` | `/v1/items` | `X-API-Key` | Paginated item list |
| `GET` | `/v1/items/{item_id}` | `X-API-Key` | Item by stable identifier |
| `GET` | `/v1/items/random` | `X-API-Key` | Single random item, never cached |
| `GET` | `/v1/meta` | `X-API-Key` | Dataset metadata |

Authenticated routes expect a Clerk-issued API key in the `X-API-Key` header.
The verifier is bound at startup and fails closed when `CLERK_SECRET_KEY` is
absent.

Every response includes an `X-Request-ID` header. A valid client-provided
request ID is preserved; otherwise the API generates a UUID.

## Health Checks

`GET /health` is a liveness check and does not contact infrastructure.

```json
{"status":"ok"}
```

`GET /health/ready` checks PostgreSQL and Redis. It returns `200` when both are
available and `503` with a generic error plus sanitized dependency states when
either dependency is unavailable.

## Cache Behavior

`GET /v1/items`, `GET /v1/items/{item_id}`, and `GET /v1/meta` use cache-aside
lookups backed by PostgreSQL. A valid cache hit avoids the corresponding
PostgreSQL query. Redis is disposable: connection, timeout, pool, and command
failures fall back to PostgreSQL and emit a structured warning without URLs,
credentials, filters, or payloads. Corrupt or invalidated payloads are treated
as misses. Programming errors and cancellation are not hidden.

Item and metadata entries expire after `86400` seconds by default; list
entries expire after `900` seconds. These TTLs are bounded configuration
values, not Redis URL query parameters. `/v1/items/random`, errors, and `404`
results are never cached.

The ingestion command bumps the cache generation after a successful PostgreSQL
commit. Older generations become unreachable without a key sweep.

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
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api_test make integration
```

The integration target only accepts local PostgreSQL databases whose name
ends in `_test`, and applies migrations before running. Integration tests are
opt-in so the regular test suite does not require Docker or a live database.

Production schema changes must use Alembic. The application never creates
tables automatically at startup.

## Configuration

| Variable | Required | Purpose |
|---|---:|---|
| `DATABASE_URL` | Yes | Async SQLAlchemy URL using `postgresql+asyncpg` |
| `REDIS_URL` | Yes | Redis URL using `redis` or `rediss` |
| `REDIS_MAX_CONNECTIONS` | No | Maximum Redis pool size, defaults to `20` |
| `DEPENDENCY_TIMEOUT_SECONDS` | No | PostgreSQL/Redis timeout, defaults to `2` |
| `CACHE_ITEM_TTL_SECONDS` | No | Item cache TTL, defaults to `86400` |
| `CACHE_LIST_TTL_SECONDS` | No | List cache TTL, defaults to `900` |
| `CACHE_META_TTL_SECONDS` | No | Metadata cache TTL, defaults to `86400` |
| `CLERK_SECRET_KEY` | No | Clerk Backend secret for protected routes. Missing values fail closed. |
| `ENVIRONMENT` | No | `development`, `test`, or `production` |
| `LOG_LEVEL` | No | Python log level, defaults to `INFO` |

Non-loopback PostgreSQL connections use verified TLS in every environment.
Remote production Redis must use `rediss://`. Local loopback and Unix-socket
connections may remain unencrypted for development.

`REDIS_URL` accepts only a hostname, an optional numeric database path from
`0` through `15`, and no query parameters or fragments. Remote production Redis
also requires a password and certificate/hostname verification. The ingestion
command uses the same Redis URL validation and requires `REDIS_URL` before it
opens PostgreSQL.

The ingestion command requires an explicit database hostname or the approved
local socket directories (`/run/postgresql` or `/var/run/postgresql`), plus
the database name and remote credentials in `DATABASE_URL`; it rejects driver
environment overrides, ambient trust stores, key logging, and routing or TLS
query parameters. The asyncpg `prepared_statement_cache_size` option remains
supported from `0` through `1000`.

Do not embed API keys intended for server-to-server use in public browser
JavaScript.

## Project Layout

```text
app/
|-- core/       # Configuration and runtime infrastructure
|-- health/     # Liveness and readiness feature
|-- ingestion/  # Offline snapshot validation and persistence
|-- items/      # Item model and authenticated read API
|-- auth/       # Clerk API-key verifier binding
|-- meta/       # Dataset metadata model
`-- main.py     # FastAPI application factory and lifespan
alembic/        # Database migrations
data/           # Non-authoritative local example snapshots
scripts/        # Offline administrative commands
tests/          # Unit, API, and opt-in integration tests
tasks/          # Approved specifications and implementation plans
```

## License

Released under the [MIT License](LICENSE).

## Acknowledgements

- Upstream dataset: [Platinum God](https://platinumgod.com/)
- Game and artwork: The Binding of Isaac, by Edmund McMillen and Florian Himsl
  (published by Nicalis). All game-related trademarks and imagery are the
  property of their respective owners. This project is a community-driven
  data layer and is not affiliated with or endorsed by the rights holders.
