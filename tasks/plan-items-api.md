# Implementation Plan: API de items `/v1`

## Overview

Entregar las cuatro rutas de lectura en tres incrementos TDD: primero
`GET /v1/items/{id}` con auth y `ITEM_NOT_FOUND`, despues el listado con
filtros y paginacion, y por ultimo random, meta, el repository SQLAlchemy y
los quality gates. Cada incremento deja la suite en verde. No hay cache,
rate limit ni ingestion.

El spec aprobado es `tasks/spec-items-api.md`. Trabajo en `feat/items-api`
desde `main`.

## Dependency Graph

```text
get_session + ItemRepository protocol
          |
          v
ItemService + ItemResponse
          |
          v
GET /v1/items/{id}  (auth + 404)
          |
          +------------------+
          |                  |
          v                  v
GET /v1/items          GET /v1/items/random
(list/filter/page)            |
          |                  |
          +--------+---------+
                   |
                   v
            GET /v1/meta
                   |
                   v
     SqlAlchemy repo + quality gates
```

## Architecture Decisions

- `{id}` es `game_id`. El JSON no expone la PK subrogada ni timestamps.
- JSON camelCase via alias Pydantic. Query params como el PRD.
- `APIRouter(prefix="/v1/items", dependencies=[require_scopes("api:access")])`.
  `/v1/meta` vive en el mismo modulo con otro router `prefix="/v1"`.
- `get_session` lee `request.app.state.session_factory`. Los tests HTTP
  sustituyen `get_item_repository`, no abren engine.
- Repository de feature, no generico. Metodos del spec: `get_by_game_id`,
  `list_items`, `count_items`, `get_random`.
- `/random` se declara antes de `/{id}` para que no caiga en validacion int.
- Search: `ILIKE` con `%` y `_` escapados. Sin `pg_trgm`.
- Postgres caido en el repository real → `AppError` 503. El fake no cubre eso.

## Implementation Order

### Phase 1: Lectura por id

- Task 1: `GET /v1/items/{id}` con fake repository, mediante TDD.

### Checkpoint: Get by id

- Sin clave → 401. Sin scope → 403. Ausente → 404 `ITEM_NOT_FOUND`.
- Fake con `game_id=118` → 200 camelCase.
- `uv run pytest tests/test_items_api.py tests/test_auth.py` verde.

### Phase 2: Coleccion

- Task 2: `GET /v1/items` con filtros, sort y paginacion, mediante TDD.

### Checkpoint: List

- Vacio → 200 `{items:[], total:0}`.
- `quality`/`search` reducen el fake. `limit`/`offset` en la respuesta.
- `quality=9` o `limit=0` → 422.
- `/health` sigue publico.

### Phase 3: Random, meta y persistencia

- Task 3: `GET /v1/items/random`, `GET /v1/meta`, repository SQLAlchemy,
  `get_session` y quality gates.

### Checkpoint: Complete

- Random vacio → 404 `ITEM_NOT_FOUND`. Meta cuenta y deja sync en `null`.
- OpenAPI documenta las cuatro rutas y `X-API-Key`.
- `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run pyright` verde.
- Listo para review.

## Verification Strategy

Cada tarea de comportamiento sigue RED, GREEN, REFACTOR:

1. Escribir el test observable y confirmar que falla por el comportamiento
   ausente.
2. Implementar solo el minimo para hacerlo pasar.
3. Ejecutar el test enfocado.
4. Refactorizar solo si reduce complejidad y volver a ejecutar el test.
5. Ejecutar el checkpoint acumulado cuando corresponda.

Comandos finales:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `/items/random` lo captura `{id}` | Alto | Declarar `/random` antes de `/{id}` |
| 404 generico aplasta `ITEM_NOT_FOUND` | Alto | `AppError`, igual que auth |
| Tests abren Postgres | Alto | Override de `get_item_repository` |
| `ILIKE` interpreta `%` del cliente | Medio | Escapar `%` y `_` en el repository |
| Repo SQL sin test de integracion | Medio | Pyright + queries explicitas; integracion en un vertical posterior |

## Parallelization

No. El listado y random reutilizan service, schemas y el protocol del Task 1.

## Open Questions

Ninguna. El spec esta aprobado, incluido `{id}` = `game_id`.
