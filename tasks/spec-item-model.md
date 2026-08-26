# Spec: Modelo Item y migracion Alembic

## Objective

Persistir el item de The Binding of Isaac como tabla PostgreSQL, con un modelo
SQLAlchemy 2 y una migracion Alembic reversible. Esta fase deja el esquema
listo para el vertical de `/v1/items` sin implementar todavia HTTP, cache,
ingestion ni tablas relacionadas.

Esta fase incluye:

- Modulo de feature `app/items/` con el modelo SQLAlchemy `Item`.
- Tabla `items` alineada con el modelo conceptual del PRD seccion 12.
- Restricciones de integridad en PostgreSQL (`UNIQUE`, `NOT NULL`, `CHECK`).
- Indices para los filtros previstos (`quality`, `item_type`, `name`).
- Convencion de nombres de constraints en `Base.metadata`.
- Revision Alembic posterior al baseline, con `upgrade` y `downgrade`.
- Import del modelo en `alembic/env.py` para que autogenerate vea la tabla.
- Tests de metadatos del modelo y de la revision, sin base de datos viva.

Esta fase no incluye:

- Endpoints `/v1/items`, `/v1/items/{id}`, `/v1/items/random` ni `/v1/meta`.
- Schemas Pydantic, router, service, repository ni cache.
- Tablas `game_versions`, `tags`, `pools`, `transformations` ni junctions.
- Extension `pg_trgm` ni indice GIN.
- Seed de datos, scraping ni CLI.
- Enums de dominio persistidos como tipo PostgreSQL.
- Triggers para `updated_at`.

## Tech Stack

Sin dependencias nuevas.

- SQLAlchemy 2 asincrono ya declarado (`sqlalchemy[asyncio]>=2.0.52`).
- Alembic ya declarado (`alembic>=1.19.1`).
- PostgreSQL 17 local via Compose, igual que la base ejecutable.
- Modelo declarativo con `Mapped` / `mapped_column`.
  Fuente: https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html

## Commands

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run alembic revision --autogenerate -m "create items"
uv run alembic upgrade head
uv run alembic downgrade -1
```

La suite pytest no arranca Compose ni habla con Neon. `upgrade` / `downgrade`
contra PostgreSQL local es un verify aparte, como en `tasks/spec.md`.

## Project Structure

```text
app/items/
|-- __init__.py
`-- models.py              # Item(Base)
app/core/database.py       # Base + naming_convention
alembic/env.py             # importa app.items.models
alembic/versions/
|-- 3159b05b2715_baseline.py
`-- <revision>_create_items.py
tests/test_item_model.py
tasks/spec-item-model.md
```

No se anaden `router.py`, `schemas.py`, `service.py` ni `repository.py`.

## Code Style

SQLAlchemy 2 declarativo. Nullability sale de `Mapped[T]` / `Mapped[T | None]`.
`mapped_column()` sustituye a `Column()` en mappings ORM.

Fuente: https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html

```python
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (CheckConstraint("quality BETWEEN 0 AND 4", name="quality_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(Text, index=True)
    description: Mapped[str] = mapped_column(Text)
    quality: Mapped[int | None] = mapped_column(Integer, index=True)
    item_type: Mapped[str | None] = mapped_column(Text, index=True)
    recharge_time: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(Text)
    introduced_in_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
```

Convenciones:

- `TEXT` sin limite artificial. `TIMESTAMPTZ` via `DateTime(timezone=True)`.
- Atributo Python `item_type`, columna `item_type`. Evita el identificador
  `type`. El contrato HTTP podra exponer `type` en el siguiente vertical.
- `recharge_time` es `TEXT`: el dominio incluye valores no numericos.
- `quality` admite `NULL`. En PostgreSQL un `CHECK` se cumple si el resultado
  es true o unknown, asi que `NULL` pasa `quality BETWEEN 0 AND 4`.
- Sin comentarios que repitan el codigo.
- Imports absolutos desde `app`.

## Schema Contract

| Columna                 | Tipo PG     | Nulo | Notas                                      |
| ----------------------- | ----------- | ---- | ------------------------------------------ |
| `id`                    | `INTEGER`   | no   | PK subrogada                               |
| `game_id`               | `INTEGER`   | no   | ID de Isaac; `UNIQUE`                      |
| `name`                  | `TEXT`      | no   |                                            |
| `description`           | `TEXT`      | no   |                                            |
| `quality`               | `INTEGER`   | si   | `CHECK` 0..4; indice                       |
| `item_type`             | `TEXT`      | si   | indice; no enum PG                         |
| `recharge_time`         | `TEXT`      | si   |                                            |
| `image_url`             | `TEXT`      | no   | requerido al persistir un item validado    |
| `introduced_in_version` | `TEXT`      | si   | slug/texto; no FK                          |
| `created_at`            | `TIMESTAMPTZ` | no | `now()` de servidor                        |
| `updated_at`            | `TIMESTAMPTZ` | no | `now()` de servidor; lo actualiza la app   |

Indices / constraints:

- `pk_items` sobre `id` (naming convention).
- `uq_items_game_id` sobre `game_id`.
- `ck_items_quality_range` sobre `quality BETWEEN 0 AND 4`.
- Indices btree en `quality`, `item_type` y `name`.

`Base` declara `MetaData(naming_convention=...)` con las plantillas oficiales
(`ix_`, `uq_`, `ck_`, `fk_`, `pk_`).

Fuente: https://docs.sqlalchemy.org/en/20/core/constraints.html

La tabla nace vacia. `CREATE INDEX` va en la misma migracion que `CREATE TABLE`
porque no hay filas ni writers. `CONCURRENTLY` no aplica.

## Testing Strategy

`tests/test_item_model.py` inspecciona metadatos SQLAlchemy. Sin engine, sin
Compose, sin Neon.

Casos:

- `Item.__tablename__ == "items"`.
- `"items" in Base.metadata.tables` tras importar `app.items.models`.
- Columnas presentes, tipos y nullability segun el contrato.
- `game_id` es unique.
- Existe el `CHECK` de `quality`.
- Existen indices en `quality`, `item_type` y `name`.
- `created_at` / `updated_at` usan timezone y `server_default`.
- La revision Alembic tiene `down_revision` igual al baseline `3159b05b2715`.
- `upgrade` crea `items` y `downgrade` la elimina.

RED, GREEN, REFACTOR por comportamiento.

Verify aparte, no en pytest:

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

contra el PostgreSQL de Compose.

## Boundaries

### Always

- Cambios de esquema solo via Alembic. Nunca `create_all()` en runtime.
- Mantener modelos SQLAlchemy separados de schemas Pydantic (aun no existen).
- Tests de esta fase sin Docker, Neon ni Clerk.
- Revisar el SQL autogenerado antes de commitearlo.

### Ask first

- Anadir `game_versions` u otras tablas relacionadas.
- Extension `pg_trgm` o indice GIN.
- Enum PostgreSQL para `item_type`.
- Dependencia nueva.
- Endpoints o schemas HTTP.
- Columnas de provenance (`source`, `source_url`, `last_scraped_at`).

### Never

- Endpoints, cache, rate limit o ingestion en esta fase.
- Editar la revision baseline ya aplicada.
- Sembrar datos de Platinum God.
- JSONB con el dominio del item.
- Repositorio/servicio generico.

## Success Criteria

- Existe `Item` en `app/items/models.py` registrado en `Base.metadata`.
- La migracion crea `items` con el contrato de columnas, unique, check e
  indices, y el downgrade la elimina.
- `alembic/env.py` importa el modelo; autogenerate no genera un diff vacio
  por olvido de import.
- `uv run pytest`, Ruff y Pyright siguen verdes.
- Ningun test de esta fase requiere PostgreSQL en marcha.
- No hay router ni contrato HTTP nuevo.

## Assumptions

1. Rama nueva `feat/item-model` desde `main`. El modelo no depende de Clerk;
   no ensucia el PR #1.
2. Solo tabla `items`. `introduced_in_version` es texto nullable, no FK a
   `game_versions`. Extraer versiones cuando exista ingestion.
3. Sin tags, pools, transformations ni provenance. El PRD dice que el esquema
   evolucionara con la fuente.
4. `image_url` es `NOT NULL` porque la validacion de ingestion exige imagen.
5. `quality` es nullable: no esta en los campos obligatorios de ingestion.
6. Sin `pg_trgm` hasta el vertical de busqueda.
7. La suite no usa base de datos viva; `upgrade`/`downgrade` es verify local.

## Open Questions

Ninguna bloqueante si se aceptan las assumptions. La que mas cambia el
esquema es la 2: texto ahora frente a tabla `game_versions` + FK.
