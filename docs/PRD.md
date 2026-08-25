# The Binding of Isaac API — Product Requirements Document

## 1. Overview

The Binding of Isaac API is a personal project that provides a fast, structured, developer-friendly REST API for accessing information about items and other entities from **The Binding of Isaac**.

The API will use data extracted from **Platinum God** through a controlled scraping and ingestion pipeline. The scraped information will be normalized, validated and persisted in PostgreSQL.

The service should prioritize:

- Fast response times.
- Simple and maintainable architecture.
- Reliable and validated game data.
- API-key-based authentication.
- Efficient caching.
- Good developer experience.
- Easy extension with additional Isaac entities in the future.

This is a personal project, so unnecessary enterprise complexity should be avoided.

---

# 2. Goals

## Primary Goals

- Provide structured information about The Binding of Isaac items.
- Require a valid API key for protected API requests.
- Provide low-latency responses.
- Build a reliable scraping and synchronization pipeline.
- Allow powerful filtering and searching.
- Provide high-quality OpenAPI documentation.
- Make the project easy to extend with new game entities.
- Maintain a clean but pragmatic software architecture.

## Non-Goals

The initial version will **not** attempt to implement:

- Microservices.
- CQRS.
- Event sourcing.
- Kafka or RabbitMQ.
- Elasticsearch.
- Complex DDD tactical patterns.
- A custom authentication system.
- A custom API-key storage system.
- Distributed transactions.
- Complex analytics infrastructure.

---

# 3. Technology Stack

## Backend

- Python 3.13+
- FastAPI
- Pydantic 2
- Uvicorn
- `uv` for dependency and project management

## Database

- PostgreSQL
- Neon
- SQLAlchemy 2
- Async SQLAlchemy
- asyncpg
- Alembic

The Neon pooled PostgreSQL endpoint should be used for application traffic.

## Cache

- Redis
- Upstash or another managed Redis provider
- `redis-py` using its asyncio API

Redis will initially be responsible for:

- Response/data caching.
- Rate limiting.
- Potential short-lived authentication caching.
- Lightweight usage statistics.

## Authentication

- Clerk
- Clerk Backend API / Python SDK
- Clerk API Keys

## Serialization

- Pydantic
- `orjson` where useful

---

# 4. High-Level Architecture

The application will use a **modular monolith** organized primarily by feature.

A strict Clean Architecture or Hexagonal Architecture implementation is intentionally avoided because the project does not justify the additional abstraction and boilerplate.

The architecture should still maintain clear boundaries between:

- HTTP layer.
- Authentication.
- Business/application logic.
- Persistence.
- Caching.
- Data ingestion.

```text
Client
  │
  │ X-API-Key
  ▼
FastAPI
  │
  ├── Clerk authentication
  ├── Redis rate limiting
  │
  ▼
Application / Service
  │
  ├──────── Redis
  │
  └──────── PostgreSQL / Neon
                 │
                 ▼
              Response
```

---

# 5. Suggested Project Structure

```text
app/
├── main.py
│
├── core/
│   ├── config.py
│   ├── database.py
│   ├── redis.py
│   ├── logging.py
│   └── exceptions.py
│
├── auth/
│   ├── clerk.py
│   ├── dependencies.py
│   ├── permissions.py
│   └── models.py
│
├── items/
│   ├── router.py
│   ├── schemas.py
│   ├── service.py
│   ├── repository.py
│   ├── cache.py
│   └── models.py
│
├── characters/
│   └── ...
│
├── transformations/
│   └── ...
│
├── shared/
│   ├── pagination.py
│   └── responses.py
│
└── ...

scripts/
├── scrape/
│   ├── fetch.py
│   ├── parse.py
│   └── selectors.py
│
├── ingest/
│   ├── normalize.py
│   ├── validate.py
│   ├── diff.py
│   └── persist.py
│
└── sync.py
```

The project should prefer feature-oriented modules such as:

```text
items/
characters/
transformations/
```

instead of generic top-level directories such as:

```text
controllers/
services/
repositories/
```

---

# 6. API Authentication

Every protected API request must contain a valid Clerk API key.

The key will travel through a dedicated HTTP header:

```http
X-API-Key: ak_xxxxxxxxxxxxxxxxx
```

The `Authorization` header will remain unused by this authentication mechanism, allowing it to be used for other authentication strategies in the future if necessary.

## Authentication Flow

```text
Request
   │
   ▼
X-API-Key exists?
   │
   ├── No ───────────────► 401
   │
   ▼
Verify with Clerk
   │
   ├── Invalid ──────────► 401
   ├── Expired ──────────► 401
   ├── Revoked ──────────► 401
   │
   ▼
API Principal
   │
   ▼
Check required scope
   │
   ├── Missing ──────────► 403
   │
   ▼
Endpoint
```

FastAPI's `APIKeyHeader` should be used:

```python
api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)
```

---

# 7. Authentication Abstraction

Application endpoints should not directly depend on Clerk models.

Clerk authentication should produce an internal representation such as:

```python
@dataclass(frozen=True)
class ApiPrincipal:
    user_id: str
    scopes: frozenset[str]
```

Application code should work with `ApiPrincipal` rather than `ClerkUser`, `ClerkApiKey`, or other provider-specific models.

This keeps the application loosely coupled to Clerk.

---

# 8. API Key Scopes

The system should be prepared to support scopes.

Example:

```text
api:access
items:read
characters:read
```

A key generated through the official application flow may be required to contain:

```text
api:access
```

This can be used to prevent API keys generated through unintended flows from accessing the API.

Future permissions may include:

```text
items:read
characters:read
transformations:read
admin:sync
```

---

# 9. Authentication Status Codes

Authentication errors must follow these rules:

```text
Missing API key     → 401
Invalid API key     → 401
Expired API key     → 401
Revoked API key     → 401
Missing permission  → 403
```

---

# 10. Authentication Performance

Initially, Clerk verification should be performed normally for each request.

Performance must be measured before introducing additional complexity.

If Clerk becomes a meaningful latency bottleneck, Redis may cache successful authentication results for a short period.

Example:

```text
X-API-Key
    │
    ▼
SHA-256
    │
    ▼
Redis
 │
 ├── HIT ───────► authenticated
 │
 └── MISS
       │
       ▼
     Clerk
       │
       ▼
 cache validation
```

Suggested TTL:

```text
30–120 seconds
```

The raw API key must **never** be stored in Redis.

Only a secure hash or Clerk API-key identifier should be used.

Short-lived authentication caching introduces a delay between revocation in Clerk and effective revocation in the API, so this optimization should only be implemented if measurements justify it.

---

# 11. PostgreSQL

PostgreSQL running on Neon will be the application's source of truth.

SQLAlchemy models and Pydantic API schemas should remain separate.

The application should use:

```text
SQLAlchemy AsyncSession
        ↓
asyncpg
        ↓
Neon pooled endpoint
```

Database queries should remain performant even when Redis does not contain the requested resource.

---

# 12. Initial Item Model

The exact schema will evolve according to the information available from the source.

A conceptual initial model could include:

```text
items
──────────────────────
id
game_id
name
description
quality
type
recharge_time
image_url
introduced_in_version_id
created_at
updated_at
```

Possible related entities:

```text
tags
item_tags

pools
item_pools

transformations
item_transformations

game_versions
```

Relational modeling should be preferred when the information is naturally relational instead of placing large amounts of domain data inside JSON columns.

---

# 13. Game Versions

The data model should be capable of distinguishing between game versions/DLCs.

Examples:

```text
Rebirth
Afterbirth
Afterbirth+
Repentance
Repentance+
```

Example:

```http
GET /v1/items?version=repentance
```

The initial implementation does not need to support complex historical item state, but the database design should avoid making version support difficult later.

---

# 14. Redis Caching

The API should implement the **cache-aside** pattern.

```text
GET /v1/items/118
        │
        ▼
      Redis
     /     \
   HIT     MISS
    │        │
    │        ▼
    │    PostgreSQL
    │        │
    │        ▼
    │     serialize
    │        │
    │        ▼
    │    Redis SET
    │        │
    └────┬───┘
         ▼
      Response
```

Example Redis key:

```text
items:118
```

---

# 15. Cache TTL

The Binding of Isaac data changes infrequently, so caching can be relatively aggressive.

Suggested starting points:

| Resource | TTL |
|---|---:|
| Individual item | 24 hours |
| Item listing | 5–30 minutes |
| Filtered item listing | 10–30 minutes |
| Character | 24 hours |
| Transformation | 24 hours |
| Global metadata | 24 hours |

Long-term, explicit invalidation after synchronization should be preferred over relying exclusively on TTL expiration.

---

# 16. Cache Invalidation

When the ingestion process modifies an entity:

```text
Database update
      │
      ▼
Commit transaction
      │
      ▼
Invalidate affected Redis keys
```

Redis must only be invalidated **after** the PostgreSQL transaction succeeds.

The next API request can repopulate the cache.

---

# 17. Cache Warming

The ingestion pipeline may optionally warm frequently requested cache entries after synchronization.

Potential candidates:

```text
items listing
quality=4
devil pool
angel pool
frequently accessed items
metadata
```

Flow:

```text
Scrape
  ↓
Normalize
  ↓
Persist
  ↓
Invalidate
  ↓
Warm popular cache entries
```

Cache warming is an optimization and is not required for the initial MVP.

---

# 18. Data Source

The initial data source will be **Platinum God**.

The system will scrape relevant information and convert it into structured application data.

The API runtime must never depend directly on Platinum God.

Clients always consume data from our own PostgreSQL database.

```text
Platinum God
      │
      ▼
Scraper
      │
      ▼
Normalization
      │
      ▼
Validation
      │
      ▼
PostgreSQL
      │
      ▼
FastAPI
```

The scraping implementation should respect the source site's applicable terms, robots directives and reasonable request rates.

---

# 19. Data Ingestion Pipeline

Scraping should not be implemented as one large script.

The pipeline should separate:

```text
FETCH
  ↓
PARSE
  ↓
NORMALIZE
  ↓
VALIDATE
  ↓
DIFF
  ↓
PERSIST
  ↓
INVALIDATE CACHE
```

Each stage should have a clear responsibility.

---

# 20. Fetch

Responsible for:

- Downloading source HTML.
- Handling HTTP failures.
- Applying sensible timeouts.
- Applying retries where appropriate.
- Avoiding unnecessarily aggressive scraping.
- Producing raw source data.

Parsing logic should not be mixed into HTTP fetching logic.

---

# 21. Parse

Responsible for translating Platinum God HTML into an intermediate representation.

CSS selectors and HTML-specific assumptions should remain isolated in this layer.

This makes source-site changes easier to fix.

---

# 22. Normalize

Scraped values should be converted into the application's canonical representation.

Examples:

```text
trim strings
normalize enum values
normalize whitespace
convert numeric strings
normalize URLs
map game versions
map item types
```

The database should not contain raw presentation-specific HTML values unless explicitly required.

---

# 23. Validation

Scraped data must be validated before reaching PostgreSQL.

Required information may include:

```text
game_id
name
description
image
```

Pydantic models can be used to validate the ingestion representation.

Invalid records should fail predictably rather than silently polluting PostgreSQL.

---

# 24. Scraper Safeguards

The ingestion process must detect suspicious scraping results.

Example:

```text
Previous synchronization: 816 items
Current scraping result:    17 items
```

This should be considered suspicious rather than interpreted as 799 deleted items.

Possible safeguard:

```python
if scraped_count < current_count * 0.8:
    raise SuspiciousScrapeResult()
```

Other checks may include:

- Required fields unexpectedly disappearing.
- Unexpected duplicate IDs.
- Massive deletion counts.
- Invalid game IDs.
- Invalid enum values.
- Empty source responses.
- Significant schema changes.

When a suspicious result is detected:

```text
ABORT
   ↓
DO NOT MODIFY DATABASE
   ↓
LOG FAILURE
```

---

# 25. Incremental Synchronization

The pipeline should calculate differences between the scraped dataset and the current database.

Example:

```text
Scraped dataset
       │
       ▼
Compare with PostgreSQL
       │
       ├── New
       ├── Changed
       ├── Unchanged
       └── Missing
```

Only necessary records should be modified.

This allows precise Redis invalidation.

---

# 26. Idempotency

The synchronization process must be idempotent.

Executing:

```bash
uv run python -m scripts.sync
```

multiple times against the same source data should result in the same database state.

PostgreSQL upserts should be used where appropriate.

Conceptually:

```sql
INSERT ...
ON CONFLICT (...)
DO UPDATE ...
```

---

# 27. Transactional Ingestion

Database modifications belonging to one synchronization should be transactional where practical.

```text
BEGIN

upsert items
update relations
update versions
record sync metadata

COMMIT
```

On failure:

```text
ROLLBACK
```

Redis invalidation must happen after a successful commit.

---

# 28. Scrape History

Synchronization runs should be tracked.

Example table:

```text
scrape_runs
──────────────────────
id
started_at
finished_at
source
status
items_found
items_created
items_updated
items_deleted
source_hash
error
```

This provides visibility into the ingestion system.

Example:

```text
Run #42

Found:    816
Created:  0
Updated:  3
Deleted:  0
Status:   SUCCESS
```

---

# 29. Source Snapshots

The ingestion system should optionally preserve normalized or raw snapshots.

Example:

```text
snapshots/
├── 2026-08-20.json
├── 2026-08-25.json
└── ...
```

Snapshots help with:

- Debugging parser changes.
- Detecting source changes.
- Reproducing ingestion problems.
- Comparing datasets.
- Testing parsers without repeatedly scraping the live website.

Snapshots should not become part of the API runtime.

---

# 30. Search

The API should provide fast item search.

Example:

```http
GET /v1/items?search=brimstone
```

Partial and fuzzy matching should eventually support queries such as:

```text
brim
brimstone
brimstne
```

PostgreSQL `pg_trgm` should be considered before introducing an external search engine.

Example:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

A GIN trigram index can then be used on relevant searchable fields.

Elasticsearch or Meilisearch should not be introduced unless PostgreSQL becomes demonstrably insufficient.

---

# 31. Filtering

The API should provide useful domain-specific filtering.

Potential query parameters:

```text
quality
type
pool
version
transformation
unlockable
tag
search
sort
order
```

Example:

```http
GET /v1/items?quality=4&type=passive&pool=devil&sort=name&order=asc
```

Filters should be implemented efficiently using appropriate PostgreSQL indexes.

---

# 32. Pagination

Collection endpoints must support pagination.

The exact strategy may initially use limit/offset pagination.

Example:

```http
GET /v1/items?limit=20&offset=40
```

Responses should provide enough metadata for consumers to navigate collections.

Cursor pagination may be introduced later if necessary.

---

# 33. Random Items

The API should support random item discovery.

Examples:

```http
GET /v1/items/random
```

```http
GET /v1/items/random?quality=4
```

```http
GET /v1/items/random?pool=devil
```

Random selection should support relevant filters where practical.

---

# 34. Item Relationships

The data model should eventually support relationships useful to consumers.

Potential endpoints:

```http
GET /v1/items/{id}/pools
GET /v1/items/{id}/transformations
GET /v1/items/{id}/synergies
```

Not every relationship needs to be implemented in v1.

---

# 35. Future Resources

Although items are the initial focus, the architecture should allow additional modules such as:

```text
/v1/items
/v1/trinkets
/v1/cards
/v1/pills
/v1/characters
/v1/transformations
/v1/pools
/v1/achievements
```

The initial codebase should not artificially generalize these resources through generic repositories or services.

Each module can contain domain-specific queries and behavior.

---

# 36. Repository Design

Avoid generic abstractions such as:

```python
Repository[T]
```

with universal methods like:

```text
find_all()
find_by()
save()
delete()
```

Repositories should expose operations meaningful to their feature.

Example:

```python
class ItemRepository:

    async def get_by_id(
        self,
        item_id: int,
    ) -> Item | None:
        ...

    async def search(
        self,
        *,
        query: str | None,
        quality: int | None,
        item_type: ItemType | None,
        limit: int,
        offset: int,
    ) -> list[Item]:
        ...
```

---

# 37. Service Layer

Services coordinate persistence, caching and application behavior.

Example:

```text
ItemService
    │
    ├── ItemCache
    │
    └── ItemRepository
```

Typical read:

```text
ItemService.get_by_id()
        │
        ▼
check cache
        │
    ┌───┴───┐
   HIT     MISS
    │        │
    │        ▼
    │   repository
    │        │
    │        ▼
    │     cache
    │        │
    └────┬───┘
         ▼
       return
```

Avoid introducing a separate use-case/query-handler class for trivial reads unless future complexity justifies it.

---

# 38. Router Design

FastAPI routers should remain thin.

They are responsible for:

- HTTP concerns.
- Input validation.
- Dependency injection.
- Calling the appropriate service.
- Returning the response.

Business or persistence logic should not live inside route handlers.

---

# 39. Rate Limiting

Redis should provide API-key-based rate limiting.

Initial example:

```text
Default:
100 requests / minute
```

The exact limit can be adjusted later.

Possible future tiers:

```text
default
trusted
internal
```

Example:

```text
default → 100 req/min
trusted → 500 req/min
```

Rate-limited requests return:

```http
429 Too Many Requests
```

---

# 40. Usage Statistics

Redis may maintain lightweight statistics associated with API keys.

Potential metrics:

```text
total requests
daily requests
errors
rate-limit hits
most-used endpoints
```

This could eventually power:

```http
GET /v1/account/usage
```

Example:

```json
{
  "requestsToday": 382,
  "limit": 5000,
  "remaining": 4618
}
```

Advanced analytics are outside the initial MVP.

---

# 41. Metadata Endpoint

The API should expose basic metadata.

Example:

```http
GET /v1/meta
```

Potential response:

```json
{
  "apiVersion": "1.0",
  "gameVersion": "Repentance+",
  "lastSync": "2026-08-25T18:42:13Z",
  "items": 819
}
```

This endpoint allows clients to understand the state and freshness of the dataset.

---

# 42. Health Checks

Provide a lightweight liveness endpoint:

```http
GET /health
```

Example:

```json
{
  "status": "ok"
}
```

A separate readiness endpoint may verify infrastructure:

```http
GET /health/ready
```

Possible dependencies:

```text
PostgreSQL
Redis
```

Clerk should not necessarily be contacted during every health check.

---

# 43. API Versioning

The API should be versioned from the beginning.

Use:

```text
/v1
```

Examples:

```http
GET /v1/items
GET /v1/items/118
GET /v1/items/random
GET /v1/meta
```

This leaves room for future breaking changes through:

```text
/v2
```

---

# 44. HTTP Caching

Because game data changes infrequently, HTTP-level caching should be considered.

Potential response header:

```http
Cache-Control: public, max-age=3600
```

Caching behavior must account for authentication and must never leak user-specific information.

---

# 45. ETags

Stable resources may support conditional HTTP requests.

Example response:

```http
ETag: "item-118-v17"
```

Client:

```http
If-None-Match: "item-118-v17"
```

If unchanged:

```http
304 Not Modified
```

This can reduce unnecessary response payloads.

ETags are optional for the initial MVP.

---

# 46. CDN

A CDN such as Cloudflare may eventually sit in front of FastAPI:

```text
Client
   │
   ▼
Cloudflare
   │
   ▼
FastAPI
   │
   ▼
Redis
   │
   ▼
Neon
```

Because requests contain `X-API-Key`, CDN caching must be designed carefully.

CDN integration is not necessary for the initial version.

---

# 47. Error Format

Errors should follow a consistent application format.

Example:

```json
{
  "error": {
    "code": "ITEM_NOT_FOUND",
    "message": "Item 9999 does not exist"
  }
}
```

Rate limit example:

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded"
  }
}
```

Potential error codes:

```text
API_KEY_REQUIRED
INVALID_API_KEY
INSUFFICIENT_PERMISSIONS
ITEM_NOT_FOUND
INVALID_FILTER
RATE_LIMIT_EXCEEDED
INTERNAL_ERROR
```

---

# 48. OpenAPI Documentation

FastAPI's generated OpenAPI documentation should be treated as part of the product.

The documentation should clearly describe:

- Authentication.
- `X-API-Key`.
- Endpoints.
- Query parameters.
- Pagination.
- Filters.
- Responses.
- Error codes.
- Rate limits.
- Examples.

Pydantic fields should provide useful descriptions and examples where appropriate.

The security scheme should allow API keys to be entered through Swagger UI.

---

# 49. Observability

The initial version should provide structured application logs.

Useful request information:

```text
request_id
method
path
status
duration_ms
cache status
```

Example:

```json
{
  "request_id": "01J...",
  "method": "GET",
  "path": "/v1/items/118",
  "status": 200,
  "duration_ms": 12.4,
  "cache": "hit"
}
```

API keys and secrets must never appear in logs.

---

# 50. Performance Metrics

The project should eventually monitor:

```text
p50 latency
p95 latency
p99 latency
Redis hit rate
database query latency
Clerk verification latency
error rate
```

This data should drive optimization decisions.

Performance optimizations should generally be implemented after measurement rather than speculation.

---

# 51. Performance Strategy

Optimization priorities:

```text
1. Geographic proximity between services
2. Redis caching
3. Efficient PostgreSQL queries
4. Correct PostgreSQL indexes
5. Minimize external network calls
6. Connection pooling
7. Efficient serialization
8. Python-level microoptimizations
```

FastAPI, Redis and Neon should ideally be deployed in geographically close regions.

---

# 52. Database Indexing

Indexes should reflect actual API access patterns.

Likely candidates:

```sql
CREATE INDEX idx_items_quality
ON items (quality);

CREATE INDEX idx_items_type
ON items (type);

CREATE INDEX idx_items_name
ON items (name);
```

Search may use:

```sql
CREATE INDEX idx_items_name_trgm
ON items
USING gin (name gin_trgm_ops);
```

Indexes should be verified using real query plans instead of added indiscriminately.

---

# 53. Administrative CLI

Administrative functionality should be exposed through a small CLI instead of accumulating unrelated scripts.

Typer can be used.

Potential commands:

```bash
isaac-api scrape
isaac-api sync
isaac-api validate
isaac-api cache clear
isaac-api cache warm
isaac-api stats
```

The CLI should reuse application ingestion and infrastructure code rather than duplicate it.

---

# 54. Dependency Guidelines

Initial dependencies may include:

```text
fastapi
uvicorn[standard]
pydantic
pydantic-settings

sqlalchemy[asyncio]
asyncpg
alembic

redis
orjson

clerk-backend-api

typer
```

Additional dependencies should only be introduced when they solve a concrete problem.

---

# 55. Configuration

Environment-specific values should be provided through environment variables.

Example:

```env
DATABASE_URL=
REDIS_URL=
CLERK_SECRET_KEY=
ENVIRONMENT=development
LOG_LEVEL=INFO
```

Secrets must never be committed to source control.

Pydantic Settings should provide typed application configuration.

---

# 56. Testing Strategy

The project should include:

## Unit Tests

Focus on:

- Normalization.
- Validation.
- Diff calculation.
- Services.
- Cache behavior.
- Rate-limit logic.
- Authentication mapping.

## Repository Tests

Test PostgreSQL queries against a test database where practical.

## Scraper Tests

Scraper parsing should primarily use saved HTML fixtures/snapshots instead of repeatedly requesting Platinum God.

This allows tests to detect when parser behavior changes.

## API Tests

Test:

```text
missing API key
invalid API key
valid API key
insufficient scopes
successful item retrieval
not found
filters
pagination
rate limiting
```

External systems such as Clerk should generally be mocked in automated tests.

---

# 57. Scraper Testing

The scraper is one of the most fragile components because it depends on external HTML.

Representative HTML fixtures should therefore be stored for parser tests.

Example:

```text
tests/
└── fixtures/
    └── platinumgod/
        ├── items.html
        └── item.html
```

Parser tests should verify expected extraction without contacting the live site.

---

# 58. Security Requirements

The system must:

- Never log API keys.
- Never persist raw Clerk API keys.
- Keep `CLERK_SECRET_KEY` server-side.
- Use HTTPS in production.
- Validate all external scraped data.
- Rate-limit API consumers.
- Prevent suspicious scraper results from corrupting PostgreSQL.
- Keep dependencies updated.
- Use parameterized SQL through SQLAlchemy.
- Return generic server errors without exposing stack traces in production.

---

# 59. MVP

The first production-capable version should contain:

### API

- `/v1/items`
- `/v1/items/{id}`
- `/v1/items/random`
- `/v1/meta`
- `/health`
- `/health/ready`

### Items

- Item details.
- Pagination.
- Search.
- Quality filtering.
- Type filtering.
- Game-version filtering where available.
- Sorting.

### Authentication

- Clerk API keys.
- `X-API-Key`.
- API-key validation.
- `ApiPrincipal`.
- Basic scope support.

### Database

- Neon PostgreSQL.
- SQLAlchemy async.
- Alembic migrations.
- Appropriate indexes.

### Cache

- Redis.
- Cache-aside.
- Item caching.
- Listing caching.
- Cache invalidation.

### Protection

- Redis rate limiting.

### Ingestion

- Platinum God fetching.
- Parsing.
- Normalization.
- Validation.
- Diff calculation.
- Transactional persistence.
- Incremental synchronization.
- Scraper safeguards.
- Scrape-run tracking.
- Redis invalidation.

### Developer Experience

- OpenAPI documentation.
- Consistent errors.
- Structured logging.
- Tests.
- Administrative sync command.

---

# 60. Post-MVP

Potential future features:

- Trinkets.
- Cards.
- Pills.
- Characters.
- Transformations.
- Achievements.
- Item pools.
- Item synergies.
- Advanced search.
- API usage dashboard.
- Multiple API-key tiers.
- Cache warming.
- ETags.
- CDN integration.
- Authentication verification caching.
- Advanced observability.
- Historical game-version data.
- Multiple data sources.

---

# 61. End-to-End Data Flow

## Ingestion

```text
              Platinum God
                    │
                    ▼
              ┌───────────┐
              │   Fetch   │
              └─────┬─────┘
                    ▼
              ┌───────────┐
              │   Parse   │
              └─────┬─────┘
                    ▼
              ┌───────────┐
              │ Normalize │
              └─────┬─────┘
                    ▼
              ┌───────────┐
              │ Validate  │
              └─────┬─────┘
                    ▼
              ┌───────────┐
              │   Diff    │
              └─────┬─────┘
                    ▼
              ┌───────────┐
              │PostgreSQL │
              │   Neon    │
              └─────┬─────┘
                    │
                    ▼
               invalidate
                    │
                    ▼
              ┌───────────┐
              │   Redis   │
              └───────────┘
```

## API Request

```text
Client
  │
  │ X-API-Key
  ▼
FastAPI
  │
  ▼
Clerk verification
  │
  ▼
ApiPrincipal
  │
  ▼
Redis rate limit
  │
  ▼
Service
  │
  ▼
Redis Cache
  │
  ├── HIT ───────────────────┐
  │                          │
  └── MISS                   │
       │                     │
       ▼                     │
 PostgreSQL / Neon            │
       │                     │
       ▼                     │
  Cache result               │
       │                     │
       └──────────┬──────────┘
                  ▼
               FastAPI
                  │
                  ▼
                JSON
```

---

# 62. Architectural Principles

The project should follow these principles:

1. **Keep it simple.** This is a personal project, not a distributed enterprise platform.

2. **Optimize the hot path.** API reads should require as little work as possible.

3. **PostgreSQL is the source of truth.** Redis is disposable.

4. **Scraped data is untrusted input.** Validate it before persistence.

5. **The source website is not part of the runtime.** Platinum God outages must not make the API unavailable.

6. **Prefer explicit code over premature abstractions.**

7. **Organize by feature.** The codebase should communicate the application's domain.

8. **Keep routers thin.**

9. **Do not leak Clerk into the application domain.**

10. **Measure before optimizing.**

11. **Make synchronization idempotent.**

12. **Never allow a scraper failure to destroy valid existing data.**

13. **Invalidate cache only after successful database writes.**

14. **Do not store or log secrets.**

15. **Design v1 so future Isaac resources can be added without redesigning the entire application.**

---

# 63. Definition of Success

The project will be considered successful when a developer can:

1. Obtain a valid API key.
2. Send it using:

```http
X-API-Key: ak_xxxxxxxxx
```

3. Query:

```http
GET /v1/items
```

4. Search and filter the Isaac dataset.
5. Retrieve individual items with low latency.
6. Receive consistent errors and rate-limit information.
7. Understand the entire API through `/docs`.

At the same time, the system should be capable of:

```text
Platinum God changes
        │
        ▼
Run synchronization
        │
        ▼
Detect changes
        │
        ▼
Validate dataset
        │
        ▼
Update PostgreSQL safely
        │
        ▼
Invalidate affected cache
        │
        ▼
Serve fresh data
```

without requiring manual database manipulation or application redeployment.

---

# 64. Performance Targets

The API is primarily read-heavy and should prioritize low latency.

Initial performance targets:

```text
Redis cache hit:
p50 < 25 ms
p95 < 75 ms
Database-backed request:
p50 < 100 ms
p95 < 250 ms
```
These values are initial targets rather than strict SLAs.

Network latency from Clerk, Neon and Redis must be taken into account.

Performance must be measured from the deployed environment rather than exclusively from local development.

The application should aim for a Redis cache hit ratio above:
`90%`
for frequently requested resources once traffic patterns stabilize.

---

# 65. Performance Budget

The expected hot path should ideally be:

```text
HTTP Request │ ▼ Authentication │ ▼ Rate Limit │ ▼ Redis HIT │ ▼ Serialization │ ▼ Response
```

PostgreSQL should not participate in most repeated reads.

Potential latency contributors:

```text
Clerk verification
Redis network latency
PostgreSQL query latency
JSON serialization
Application processing
Network distance
```

Optimizations should focus first on network and data-access costs.

---

# 66. Source of Truth Rules

PostgreSQL is the authoritative source of application data.

Redis must always be considered disposable.

The following relationship must hold:

```text
Platinum God │ │ source ▼ Ingestion Pipeline │ ▼ PostgreSQL │ │ source of truth ▼ Redis │ │ derived cache ▼ API Response
```

Deleting the Redis database must never cause permanent data loss.

The system should be able to rebuild all caches from PostgreSQL.

---

# 67. Scraping Failure Strategy

The scraper must fail safely.

A failed scrape must never make the currently available API dataset unavailable.

Example:

```text
Current valid dataset │ ▼ PostgreSQL │ │ New scrape begins │ ▼ Parsing failure │ ▼ ABORT │ └────► Existing data remains unchanged
```

Failures should be recorded in `scrape_runs`.

The previous valid dataset should remain available until a new synchronization completes successfully.

---

# 68. Deletion Strategy

Missing records from a scrape should not automatically be deleted without validation.

Before deleting an entity, the ingestion process should determine whether:

- The entity was genuinely removed.
- The source HTML changed.
- The parser failed.
- The entity moved to another section.
- The source temporarily returned incomplete data.

For the initial implementation, suspicious deletions should require conservative handling.

A possible strategy:

```text
Detected missing item
       │
       ▼
Mark as potentially removed
       │
       ▼
Validate scrape health
       │
       ├── suspicious scrape → abort
       │
       └── healthy scrape
               │
               ▼
            delete/update
```

Soft deletion may be considered later if historical tracking becomes useful.

---

# 69. Data Provenance

Where practical, entities should retain enough metadata to understand where their information originated.

Possible fields:

```text
source
source_url
source_updated_at
last_scraped_at
```

Example:
```json
{
  "source": "platinumgod",
  "sourceUrl": "https://...",
  "lastScrapedAt": "2026-08-25T20:15:00Z"
}
```
Not all source metadata needs to be exposed publicly through the API.

---

# 70. Data Normalization Rules

The ingestion pipeline should establish canonical values for domain concepts.

For example:

```text
"Passive"
"passive"
"PASSIVE"
```

should not become three database values.

Instead:

`PASSIVE`

or another canonical enum representation should be used internally.

Normalization should cover:

- Item types.
- Game versions.
- Pools.
- Quality values.
- Recharge values.
- URLs.
- Names.
- Descriptions.
- Boolean flags.
- Identifiers.

Raw scraped strings should not dictate the application's domain model.

---

# 71. Domain Enums

Stable domain values should use explicit enums where appropriate.

Example:

```python
class ItemType(str, Enum):
    PASSIVE = "passive"
    ACTIVE = "active"
    FAMILIAR = "familiar"
```

Possible enums may include:

```text
ItemType
GameVersion
PoolType
RechargeType
```

Enums should only be introduced for values with a sufficiently stable and finite domain.

---

# 72. Data Integrity

PostgreSQL constraints should enforce important invariants.

Examples:

```text
item game_id must be unique
quality must be within its valid range
name cannot be null
game version references must exist
```

Where appropriate:

```sql
UNIQUE
NOT NULL
CHECK
FOREIGN KEY
```

constraints should complement Pydantic validation.

Validation should exist at both:

```text
Application boundary
+
Database boundary
```

for critical invariants.

---

# 73. Database Migrations

Alembic will manage PostgreSQL schema evolution.

Rules:

- Database schema changes must be represented by migrations.
- Production databases must not rely on Base.metadata.create_all().
- Migrations should be reproducible.
- Migrations should be reviewed before applying.
- Destructive migrations should be treated cautiously.

Typical commands:

```bash
uv run alembic revision --autogenerate -m "create items"
uv run alembic upgrade head
```
---

# 74. Redis Key Conventions

Redis keys should follow predictable naming conventions.

Examples:

```text
cache:item:118
cache:items:list:{hash}
cache:meta

rate_limit:{api_key_id}:{window}

auth:{api_key_hash}

stats:{api_key_id}:daily:{date}
```

Prefixes make administration and debugging significantly easier.

Cache keys for filtered requests should be deterministic.

For example, normalized filters:

`quality=4&type=passive&page=1`

could produce a hash used as:

`cache:items:list:5b7a9d...`

---

# 75. Cache Stampede Protection

Popular cache entries may receive many simultaneous requests after expiration.

Potential flow without protection:

```text
Cache expires
    │
    ├── Request 1 → PostgreSQL
    ├── Request 2 → PostgreSQL
    ├── Request 3 → PostgreSQL
    ├── Request 4 → PostgreSQL
    └── Request N → PostgreSQL
```

This is known as a cache stampede.

The initial project does not necessarily need protection.

If it becomes relevant, possible approaches include:

- Short-lived Redis locks.
- Stale-while-revalidate.
- TTL jitter.
- Cache warming.

A simple TTL jitter can prevent many keys from expiring simultaneously.

---

# 76. Negative Caching

Repeated requests for nonexistent resources can still create database load.

For example:

`GET /v1/items/999999`

If necessary, short-lived negative caching may be introduced.

Example:

```text
cache:item:999999 = NOT_FOUND
TTL = 30–60 seconds
```

Negative caching must use short TTLs to avoid hiding newly created records.

This is an optimization, not an MVP requirement.

---

# 77. Rate Limit Headers

When rate limiting is implemented, responses should ideally expose useful metadata.

Possible headers:

```text
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 73
X-RateLimit-Reset: 1756153200
```

When exceeded:

```text
HTTP/1.1 429 Too Many Requests
Retry-After: 42
```

This improves the developer experience for API consumers.

---

# 78. Request IDs

Every request should receive a unique identifier.

Example response header:

```text
X-Request-ID: 01K3...
```

The same identifier should appear in structured logs.

This makes debugging significantly easier:

```text
Client error
   │
   ▼
request_id
   │
   ▼
search logs
   │
   ▼
complete request trace
```

Clients may provide their own request ID, but the application should validate or replace invalid values.

---

# 79. CORS

CORS should be configured explicitly.

Development may allow local frontend origins such as:

```text
http://localhost:3000
http://localhost:5173
```

Production should avoid:

`allow_origins=["*"]`

unless public browser access genuinely requires it.

Because API keys are sensitive credentials, browser-based usage must be considered carefully.

API keys intended to remain secret should not be embedded directly into public frontend JavaScript.

---

# 80. API Key Usage Model

The expected usage is primarily server-to-server or developer tooling.

Recommended:

```text
Backend
CLI
Desktop application with secure storage
Server script
CI job
```

Potentially unsafe:

`Public browser JavaScript`

because users can inspect requests and retrieve the API key.

Documentation should make this distinction clear.

---

# 81. API Key Rotation

Users should be able to maintain multiple API keys.

Example:

```text
User
 ├── Development
 ├── Production
 └── CI
```

This allows safe rotation:

```text
Create new key
      │
      ▼
Update consumer
      │
      ▼
Verify new key works
      │
      ▼
Revoke old key
```

The system should avoid assuming that one user has exactly one API key.

---

# 82. Secret Handling

Secrets must be provided through environment variables or the deployment platform's secret manager.

Examples:

```text
CLERK_SECRET_KEY
DATABASE_URL
REDIS_URL
```

Rules:

```text
Never commit them.
Never log them.
Never return them through APIs.
Never include them in exceptions.
Never place them in test fixtures.
```

A `.env.example` should contain placeholders only.

Example:

```text
DATABASE_URL=
REDIS_URL=
CLERK_SECRET_KEY=
```

---

# 83. Local Development

Local development should be easy to bootstrap.

Possible workflow:

```bash
git clone ...
cd isaac-api

uv sync

cp .env.example .env

uv run alembic upgrade head

uv run uvicorn app.main:app --reload
```

Redis and PostgreSQL may either use:

- Local Docker containers.
- Remote development instances.
- A combination of both.

Production credentials must not be reused locally.

---

# 84. HTTP Client Reuse

Any outgoing HTTP requests used by the runtime or scraper should reuse HTTP clients where appropriate.

For example:

```text
httpx.AsyncClient
```

rather than opening a fresh TCP/TLS connection for every request.

This applies particularly to:

- Clerk.
- Scraping.
- Future external data sources.

Connection reuse reduces latency and resource consumption.

---

# 85. Timeout Policy

All external network calls must have explicit timeouts.

This includes:

```text
Clerk
Platinum God
Redis
PostgreSQL
future external services
```

No request should be able to wait indefinitely on an external dependency.

Different operations may use different timeout budgets.

---

# 86. Retry Policy

Retries should only be used for operations where retrying is safe.

Good candidates:

```text
GET scraping request
temporary connection error
transient 5xx
```

Retries should use:

```text
limited attempts
+
exponential backoff
+
optional jitter
```

Database writes must not be blindly retried without considering idempotency.

---

# 87. Graceful Degradation

Redis is an optimization layer.

Where appropriate, temporary Redis failures should not necessarily make read endpoints unavailable.

Possible behavior:

```text
Redis unavailable
       │
       ▼
log warning
       │
       ▼
query PostgreSQL
       │
       ▼
return response
```

However, Redis-backed rate limiting may require a defined fail-open or fail-closed policy.

For this personal project, a reasonable initial choice is:

```text
Data cache failure → fall back to PostgreSQL
Rate limiter failure → log and temporarily fail open
```

This can be revisited if the service becomes public and heavily used.

---

# 88. Clerk Failure Policy

If Clerk cannot verify a previously uncached API key because Clerk is unavailable, the safest default is:

`fail closed`

Meaning:

```text
Cannot authenticate
      │
      ▼
request rejected
```

Authentication availability should not be silently replaced by unauthenticated access.

A short-lived authentication cache may later improve resilience.

---

# 89. Database Failure Policy

PostgreSQL is the source of truth.

For cached resources:

```text
PostgreSQL unavailable
+
Redis HIT
```

may still allow the API to serve cached data.

For cache misses:

```text
PostgreSQL unavailable
+
Redis MISS
```

the request should fail with an appropriate server error.

The application should never return misleading empty collections when the database is actually unavailable.

---

# 90. Code Quality

Prefer a small set of high-value development tools.

Recommended:

```text
Ruff
Pytest
Pyright
```

Avoid installing multiple tools that solve the same problem without clear benefit.

For example, there is little reason to combine:

```text
Black
isort
Flake8
Ruff
```

when Ruff can cover most of those responsibilities.

---

# 91. Type Safety

Application code should use Python type annotations extensively.

Particular attention should be paid to boundaries:

```text
HTTP request
Pydantic schema
service
repository
scraper intermediate models
configuration
```

Avoid widespread use of:

```python
Any
```
unless dealing with genuinely dynamic external structures.

---

# 92. Testing Performance

Performance-sensitive endpoints should eventually have lightweight benchmarks or load tests.

Potential tools:

```text
Locust
k6
wrk
hey
```

Important scenarios:

```text
GET cached item
GET uncached item
filtered listing
search
concurrent requests
rate limiting
```

Load tests should target the deployed environment when meaningful.

---

# 93. Architectural Decisions Summary

| Concern            | Decision                   |
| ------------------ | -------------------------- |
| Architecture       | Modular monolith           |
| Organization       | Feature-oriented           |
| API framework      | FastAPI                    |
| Database           | PostgreSQL via Neon        |
| ORM                | SQLAlchemy 2 async         |
| Driver             | asyncpg                    |
| Migrations         | Alembic                    |
| Cache              | Redis                      |
| Redis provider     | Upstash or equivalent      |
| Authentication     | Clerk API Keys             |
| API key transport  | `X-API-Key`                |
| Rate limiting      | Redis                      |
| Source data        | Platinum God               |
| Data ingestion     | Dedicated scripts/CLI      |
| Search             | PostgreSQL + `pg_trgm`     |
| API version        | `/v1`                      |
| Dependency manager | `uv`                       |
| Configuration      | Pydantic Settings          |
| CLI                | Typer                      |
| Serialization      | Pydantic / optional orjson |
| Deployment         | Containerized FastAPI      |
| Source of truth    | PostgreSQL                 |


# 94. Final Architecture

```text
                          ┌─────────────────────┐
                          │    Platinum God     │
                          └──────────┬──────────┘
                                     │
                                     │ scrape
                                     ▼
                           ┌────────────────────┐
                           │   Fetch / Parse    │
                           └──────────┬─────────┘
                                      │
                                      ▼
                           ┌────────────────────┐
                           │ Normalize/Validate │
                           └──────────┬─────────┘
                                      │
                                      ▼
                           ┌────────────────────┐
                           │        Diff        │
                           └──────────┬─────────┘
                                      │
                                      ▼
                            ┌──────────────────┐
                            │ PostgreSQL / Neon│
                            │ Source of Truth  │
                            └─────────┬────────┘
                                      │
                                invalidate
                                      │
                                      ▼
                                ┌───────────┐
                                │   Redis   │
                                └───────────┘


                              RUNTIME


 ┌────────────┐
 │ API Client │
 └─────┬──────┘
       │
       │ X-API-Key
       ▼
 ┌─────────────────────────────────────────┐
 │                 FastAPI                 │
 │                                         │
 │  Request ID                             │
 │      │                                  │
 │      ▼                                  │
 │  Authentication ─────────────► Clerk    │
 │      │                                  │
 │      ▼                                  │
 │  Rate Limiting ──────────────► Redis    │
 │      │                                  │
 │      ▼                                  │
 │  Router                                 │
 │      │                                  │
 │      ▼                                  │
 │  Service                                │
 │      │                                  │
 │      ├──────── Cache ─────────► Redis   │
 │      │                                  │
 │      └──────── Repository ────► Neon    │
 │                                         │
 └────────────────────┬────────────────────┘
                      │
                      ▼
                    JSON
``
