# Implementation Plan: Modelo Item y migracion Alembic

## Overview

Entregar el esquema `items` en tres incrementos: primero el modelo SQLAlchemy
con tests de metadatos, despues la revision Alembic reversible, y por ultimo
el verify local `upgrade`/`downgrade` y los quality gates. Cada incremento
deja la suite en verde. No hay HTTP, cache, ingestion ni tablas hermanas.

El spec aprobado es `tasks/spec-item-model.md`. Los planes de la base y de
auth siguen en `tasks/plan.md` y `tasks/plan-auth.md`.

Trabajo en `feat/item-model` ramificada desde `main`.

## Dependency Graph

```text
Base naming_convention
          |
          v
Item model + metadata tests
          |
          v
alembic/env.py importa el modelo
          |
          v
Revision create_items (upgrade / downgrade)
          |
          v
Verify local Alembic + quality gates
```

## Architecture Decisions

- Un solo modelo `Item` en `app/items/models.py`. Sin schemas Pydantic, router,
  service ni repository.
- `Base.metadata` lleva la naming convention oficial de SQLAlchemy para que
  Alembic capture nombres estables (`pk_`, `uq_`, `ck_`, `ix_`, `fk_`).
- `item_type` es el nombre de columna. `introduced_in_version` es texto
  nullable, no FK.
- La suite inspecciona metadatos y el fichero de revision. No abre engine ni
  Compose.
- La revision se autogenera y se revisa a mano antes de commitearla. No se
  edita el baseline `3159b05b2715`.
- Indices btree van en el mismo `CREATE TABLE` porque la tabla nace vacia.

## Implementation Order

### Phase 1: Modelo

- Task 1: `Item` + naming convention, mediante TDD sobre metadatos.

### Checkpoint: Model

- `Item` esta en `Base.metadata.tables["items"]`.
- Columnas, nullability, unique, check e indices coinciden con el spec.
- `uv run pytest tests/test_item_model.py tests/test_database.py` verde.

### Phase 2: Migracion

- Task 2: Import en `alembic/env.py` y revision `create_items`, mediante TDD.

### Checkpoint: Migration

- `down_revision` es el baseline `3159b05b2715`.
- `upgrade` crea `items`; `downgrade` la elimina.
- `env.py` importa `app.items.models`.
- `uv run pytest tests/test_item_model.py` verde.

### Phase 3: Verify

- Task 3: `upgrade` / `downgrade` / `upgrade` contra Compose y quality gates.

### Checkpoint: Complete

- Alembic local aplica y revierte sin `create_all()`.
- `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run pyright` verde.
- Listo para review de calidad.

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
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Autogenerate omite check o indices | Alto | Tests de metadatos + revisar el SQL generado |
| `env.py` no importa el modelo | Alto | Test que exige el import; metadata no vacia |
| Autogenerate pide SERIAL vs IDENTITY | Bajo | Aceptar el default de SQLAlchemy 2 en PostgreSQL |
| Tests cargan `alembic/env.py` y Settings | Medio | Inspeccionar el fichero/revision, no importar env |
| Naming convention rompe tests de TLS | Bajo | `tests/test_database.py` no toca metadata |

## Parallelization

No. El modelo alimenta la migracion; la migracion alimenta el verify.

## Open Questions

Ninguna. El spec esta aprobado, incluida la rama desde `main`.
