# Tasks: API de items `/v1`

## Task 1: GET /v1/items/{id}

**Description:** Entregar la lectura por `game_id` protegida con
`api:access`. El repository se sustituye por un fake. Incluye schemas
camelCase y el 404 `ITEM_NOT_FOUND`.

**Acceptance criteria:**

- [x] Sin `X-API-Key` → `401` `API_KEY_REQUIRED`.
- [x] Fake sin `api:access` → `403` `INSUFFICIENT_PERMISSIONS`.
- [x] Fake con item `118` → `200` y JSON camelCase (`gameId`, `type`, ...).
- [x] Ausente → `404` `ITEM_NOT_FOUND` (`"Item 9999 does not exist"`).
- [x] El JSON no incluye PK subrogada ni timestamps.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_items_api.py`
- [x] `uv run pytest tests/test_auth.py`
- [x] `uv run pyright app/items app/main.py tests/test_items_api.py`

**Dependencies:** None

**Files likely touched:**

- `app/items/schemas.py`
- `app/items/repository.py`
- `app/items/service.py`
- `app/items/router.py`
- `app/main.py`
- `tests/test_items_api.py`

**Estimated scope:** Medium

## Task 2: GET /v1/items (filtros y paginacion)

**Description:** Listar items con search, quality, type, version, sort, order,
limit y offset. Validacion de query via Pydantic. Sigue usando el fake.

**Acceptance criteria:**

- [x] Listado vacio → `200` `{items:[], total:0, limit:20, offset:0}`.
- [x] `quality` y `search` reducen el resultado del fake.
- [x] `limit` y `offset` se reflejan en la respuesta.
- [x] `quality=9` o `limit=0` → `422` `VALIDATION_ERROR`.
- [x] La ruta exige `api:access`.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_items_api.py`
- [x] `uv run pyright app/items tests/test_items_api.py`

**Dependencies:** Task 1

**Files likely touched:**

- `app/items/schemas.py`
- `app/items/repository.py`
- `app/items/service.py`
- `app/items/router.py`
- `tests/test_items_api.py`

**Estimated scope:** Medium

## Task 3: Random, meta, session y repository SQL

**Description:** Anadir random y meta, cablear `get_session` y el repository
SQLAlchemy, y pasar los quality gates. `/random` se declara antes de `/{id}`.

**Acceptance criteria:**

- [x] Random con fake → `200`. Fake vacio → `404` `ITEM_NOT_FOUND`.
- [x] Meta devuelve `apiVersion`, `items` del fake, `gameVersion`/`lastSync`
      `null`.
- [x] `get_session` usa `app.state.session_factory`.
- [x] Existe implementacion SQLAlchemy de los cuatro metodos del repository.
- [x] OpenAPI documenta las cuatro rutas y `X-API-Key`.
- [x] `/health` sigue publico.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_items_api.py tests/test_health.py`
- [x] `uv run pytest`
- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pyright`

**Dependencies:** Task 2

**Files likely touched:**

- `app/core/database.py`
- `app/items/repository.py`
- `app/items/service.py`
- `app/items/router.py`
- `app/items/schemas.py`
- `tests/test_items_api.py`

**Estimated scope:** Medium

## Task 4: Integracion PostgreSQL del repository

**Description:** Verificar los cuatro metodos del repository contra PostgreSQL
real sin hacer que la suite unitaria dependa de infraestructura externa.

**Acceptance criteria:**

- [x] La suite opt-in cubre lectura por `game_id`, filtros, escape de `ILIKE`,
      recuento, paginacion y random.
- [x] Cada test revierte su transaccion y no deja datos persistidos.
- [x] Sin `TEST_DATABASE_URL`, la suite normal no intenta conectarse a PostgreSQL.
- [x] `make integration` aplica migraciones y ejecuta solo los tests marcados.

**Verification:**

- [x] `TEST_DATABASE_URL=... make integration`
- [x] `uv run pytest`
- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pyright`

**Dependencies:** Task 3

**Files likely touched:**

- `tests/integration/test_items_repository_postgres.py`
- `Makefile`
- `pyproject.toml`
- `README.md`

**Estimated scope:** Small

## Task 5: Quality gates en CI

**Description:** Ejecutar quality gates y la integracion PostgreSQL en GitHub
Actions para pull requests y pushes a `main`.

**Acceptance criteria:**

- [x] CI ejecuta Ruff, formato, Pyright y la suite base.
- [x] CI levanta PostgreSQL 17, aplica migraciones y ejecuta la suite de
      integracion con una base `_test`.
- [x] El workflow no usa secretos de produccion ni Redis real.

**Verification:**

- [x] El YAML del workflow parsea correctamente.
- [x] Los mismos comandos pasan localmente.

**Dependencies:** Task 4

**Files likely touched:**

- `.github/workflows/ci.yml`
- `README.md`

**Estimated scope:** Small
