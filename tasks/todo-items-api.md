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

- [ ] Listado vacio → `200` `{items:[], total:0, limit:20, offset:0}`.
- [ ] `quality` y `search` reducen el resultado del fake.
- [ ] `limit` y `offset` se reflejan en la respuesta.
- [ ] `quality=9` o `limit=0` → `422` `VALIDATION_ERROR`.
- [ ] La ruta exige `api:access`.

**Verification:**

- [ ] RED y GREEN: `uv run pytest tests/test_items_api.py`
- [ ] `uv run pyright app/items tests/test_items_api.py`

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

- [ ] Random con fake → `200`. Fake vacio → `404` `ITEM_NOT_FOUND`.
- [ ] Meta devuelve `apiVersion`, `items` del fake, `gameVersion`/`lastSync`
      `null`.
- [ ] `get_session` usa `app.state.session_factory`.
- [ ] Existe implementacion SQLAlchemy de los cuatro metodos del repository.
- [ ] OpenAPI documenta las cuatro rutas y `X-API-Key`.
- [ ] `/health` sigue publico.

**Verification:**

- [ ] RED y GREEN: `uv run pytest tests/test_items_api.py tests/test_health.py`
- [ ] `uv run pytest`
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pyright`

**Dependencies:** Task 2

**Files likely touched:**

- `app/core/database.py`
- `app/items/repository.py`
- `app/items/service.py`
- `app/items/router.py`
- `app/items/schemas.py`
- `tests/test_items_api.py`

**Estimated scope:** Medium
