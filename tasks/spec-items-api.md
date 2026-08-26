# Spec: API de items `/v1`

## Objective

Exponer lectura autenticada del catalogo de items ya persistido. Un cliente
con `X-API-Key` y scope `api:access` puede listar, buscar, obtener por
`game_id`, pedir uno aleatorio y consultar metadata del dataset.

Esta fase incluye:

- `GET /v1/items` con paginacion limit/offset, search, quality, type, version,
  sort y order.
- `GET /v1/items/random` con los mismos filtros, sin paginacion.
- `GET /v1/items/{id}` donde `{id}` es el `game_id` de Isaac.
- `GET /v1/meta` con version de API, recuento de items y campos de sync nulos.
- Proteccion con `require_scopes("api:access")` en las cuatro rutas.
- Router fino, service, repository de feature y schemas Pydantic separados
  del modelo SQLAlchemy.
- Dependencia `get_session` sobre `app.state.session_factory`.
- Tests HTTP con verificador y repositorio falsos. Sin Postgres vivo.

Esta fase no incluye:

- Cache-aside, rate limiting, ETags ni `Cache-Control`.
- Filtros que exigen tablas ausentes: pool, transformation, tag, unlockable.
- `pg_trgm` ni busqueda fuzzy.
- Ingestion, seed, CLI ni `scrape_runs`.
- Escritura HTTP (POST/PATCH/DELETE).
- Relacionados (`/v1/items/{id}/pools`, etc.).

## Tech Stack

Sin dependencias nuevas.

- FastAPI `APIRouter` con `prefix`, `tags` y `dependencies`.
  Fuente: https://fastapi.tiangolo.com/tutorial/bigger-applications/
- Pydantic v2 para request/response. `response_model` serializa y documenta.
  Fuente: https://fastapi.tiangolo.com/tutorial/response-model/
- SQLAlchemy 2 async `select` en el repository.
- HTTPX `ASGITransport` en tests, igual que auth.

## Commands

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

## Project Structure

```text
app/items/
|-- __init__.py
|-- models.py          # ya existe
|-- schemas.py         # contratos HTTP
|-- repository.py      # queries de feature
|-- service.py         # orquesta repository
|-- router.py          # HTTP fino
|-- dependencies.py    # get_item_repository
app/core/database.py   # + get_session
app/main.py            # include_router
tests/test_items_api.py
tasks/spec-items-api.md
```

No se crea `app/shared/` todavia: solo hay una coleccion.

## Code Style

Router con dependencias compartidas. `random` se declara antes de `/{id}`.

Fuente: https://fastapi.tiangolo.com/tutorial/bigger-applications/

```python
from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_scopes
from app.items.schemas import ItemResponse
from app.items.service import ItemService

router = APIRouter(
    prefix="/v1/items",
    tags=["items"],
    dependencies=[Depends(require_scopes("api:access"))],
)


@router.get("/random", response_model=ItemResponse)
async def get_random_item(service: Annotated[ItemService, Depends()]) -> ItemResponse:
    return await service.get_random()
```

Convenciones:

- Routers solo HTTP, validacion e inyeccion.
- `ItemService` no importa FastAPI.
- El repository no expone `find_all` generico. Metodos: `get_by_game_id`,
  `list_items`, `count_items`, `get_random`.
- JSON publico en camelCase (`gameId`, `imageUrl`). Query params como el PRD:
  `search`, `quality`, `type`, `version`, `sort`, `order`, `limit`, `offset`.
- El query `type` mapea a la columna `item_type`.
- `{id}` es `game_id`, no la PK subrogada.
- 404 de item usa `AppError` con `ITEM_NOT_FOUND`, no el 404 generico.
- Escape de `%` y `_` en `search` antes del `ILIKE`.
- Imports absolutos desde `app`. Sin comentarios que repitan el codigo.

## API Contract

Todas las rutas de esta fase exigen `X-API-Key` con `api:access`. Health no
cambia.

### Item JSON

```json
{
  "gameId": 118,
  "name": "Brimstone",
  "description": "...",
  "quality": 4,
  "type": "passive",
  "rechargeTime": null,
  "imageUrl": "https://...",
  "introducedInVersion": "rebirth"
}
```

No se exponen `id`, `createdAt` ni `updatedAt`.

### `GET /v1/items`

| Query     | Tipo        | Default | Reglas                          |
| --------- | ----------- | ------- | ------------------------------- |
| `search`  | string      | —       | substring case-insensitive name |
| `quality` | int         | —       | 0..4                            |
| `type`    | string      | —       | igualdad exacta con `item_type` |
| `version` | string      | —       | igualdad con `introduced_in_version` |
| `sort`    | enum        | `name`  | `name`, `quality`, `game_id`    |
| `order`   | enum        | `asc`   | `asc`, `desc`                   |
| `limit`   | int         | 20      | 1..100                          |
| `offset`  | int         | 0       | >= 0                            |

Orden estable: campo pedido y, como desempate, `game_id`.

```json
{
  "items": [],
  "total": 0,
  "limit": 20,
  "offset": 0
}
```

Coleccion vacia → `200`, no `404`.

### `GET /v1/items/{id}`

`id` entero = `game_id`. No existe → `404` `ITEM_NOT_FOUND`:

```json
{
  "error": {
    "code": "ITEM_NOT_FOUND",
    "message": "Item 9999 does not exist"
  }
}
```

### `GET /v1/items/random`

Mismos filtros que el listado, sin `limit`/`offset`/`sort`/`order`. Un item.
Ninguno coincide → `404` `ITEM_NOT_FOUND` con mensaje
`"No item matches the given filters"`.

### `GET /v1/meta`

```json
{
  "apiVersion": "0.1.0",
  "gameVersion": null,
  "lastSync": null,
  "items": 0
}
```

`apiVersion` sale de `Settings.app_version`. `items` es el recuento en
PostgreSQL. `gameVersion` y `lastSync` quedan `null` hasta ingestion.

### Errores

| Situacion              | HTTP | code                       |
| ---------------------- | ---- | -------------------------- |
| Sin clave / invalida   | 401  | (contrato auth, sin cambio)|
| Sin `api:access`       | 403  | (contrato auth, sin cambio)|
| Query invalida         | 422  | `VALIDATION_ERROR`         |
| Item o random vacio    | 404  | `ITEM_NOT_FOUND`           |
| Postgres caido         | 503  | `SERVICE_UNAVAILABLE`      |

No se anade `INVALID_FILTER`. Pydantic cubre los valores ilegales.

## Testing Strategy

`tests/test_items_api.py`. HTTPX `ASGITransport`. Clerk y el repository se
sustituyen. La suite no arranca Compose ni Neon.

Casos:

- Sin clave → 401 en cada ruta nueva.
- Fake sin `api:access` → 403.
- Listado vacio → 200 `{items:[], total:0}`.
- Filtro `quality` y `search` reducen el resultado del fake.
- `limit`/`offset` aparecen en la respuesta.
- `GET /v1/items/118` → 200 del fake; ausente → 404 `ITEM_NOT_FOUND`.
- `GET /v1/items/random` → 200; fake vacio → 404 `ITEM_NOT_FOUND`.
- `GET /v1/meta` → `apiVersion` y `items` del fake.
- `quality=9` o `limit=0` → 422.
- `/health` sigue publico.
- OpenAPI documenta las cuatro rutas y `X-API-Key`.

RED, GREEN, REFACTOR por comportamiento.

## Boundaries

### Always

- Proteger las cuatro rutas con `api:access`.
- Usar `AppError` para `ITEM_NOT_FOUND`.
- Mantener modelos SQLAlchemy y schemas Pydantic separados.
- Tests de esta fase sin Docker, Neon ni Clerk real.
- Timeouts ya existentes en la sesion / engine.

### Ask first

- Cache, rate limit, ETags o headers de cache HTTP.
- `pg_trgm` o cambio de esquema.
- Filtros que requieran tablas nuevas.
- Dependencia nueva.
- Exponer PK subrogada o timestamps en el JSON.

### Never

- `create_all()` en runtime.
- Loguear API keys o URLs con credenciales.
- Contactar Platinum God desde el runtime.
- Implementar cache-aside o rate limit en esta fase.
- Devolver coleccion vacia si PostgreSQL esta caido.

## Success Criteria

- Las cuatro rutas responden el contrato con clave valida.
- Sin clave o sin scope se comportan como auth.
- `{id}` resuelve por `game_id`.
- Listado pagina y filtra sin tablas extra.
- Meta cuenta items y deja sync en `null`.
- `uv run pytest`, Ruff y Pyright verdes.
- Ningun test de esta fase requiere PostgreSQL en marcha.

## Assumptions

1. Rama `feat/items-api` desde `main` (PR #2 ya mergeado).
2. `{id}` es `game_id`. El ejemplo del PRD (`/v1/items/118`) es Brimstone.
3. JSON camelCase; query params del PRD en snake/simple.
4. Search es `ILIKE` en `name`, no trigram.
5. Sin pool/tag/transformation hasta que existan esas tablas.
6. `lastSync` y `gameVersion` son `null` hasta ingestion.
7. Tests con repository fake. `get_session` existe, pero la suite HTTP no
   abre engine.

## Open Questions

Ninguna bloqueante si se aceptan las assumptions. La que mas cambia el
contrato es la 2: `{id}` como `game_id` frente a PK subrogada.
