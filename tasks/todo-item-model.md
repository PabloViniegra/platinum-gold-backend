# Tasks: Modelo Item y migracion Alembic

## Task 1: Modelo Item y naming convention

**Description:** Crear `app/items/models.py` con `Item` y declarar la naming
convention en `Base`. Los tests inspeccionan metadatos SQLAlchemy, sin engine.

**Acceptance criteria:**

- [x] `Item.__tablename__ == "items"` y `"items" in Base.metadata.tables`.
- [x] Columnas, tipos y nullability coinciden con el schema contract.
- [x] `game_id` es unique; `quality` tiene `CHECK` 0..4.
- [x] Hay indices en `quality`, `item_type` y `name`.
- [x] `created_at` / `updated_at` usan timezone y `server_default`.
- [x] `Base.metadata` usa la naming convention oficial.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_item_model.py`
- [x] `uv run pytest tests/test_database.py`
- [x] `uv run pyright app/items app/core/database.py tests/test_item_model.py`

**Dependencies:** None

**Files likely touched:**

- `app/core/database.py`
- `app/items/__init__.py`
- `app/items/models.py`
- `tests/test_item_model.py`

**Estimated scope:** Medium

## Task 2: Revision Alembic create_items

**Description:** Hacer visible `Item` a Alembic e introducir una revision
reversible posterior al baseline. Los tests leen la revision y `env.py`, no
abren PostgreSQL.

**Acceptance criteria:**

- [x] `alembic/env.py` importa `app.items.models`.
- [x] La revision tiene `down_revision == "3159b05b2715"`.
- [x] `upgrade` crea la tabla `items`.
- [x] `downgrade` elimina la tabla `items`.
- [x] El baseline `3159b05b2715` no se modifica.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_item_model.py`
- [x] Revisar el SQL autogenerado antes de dejarlo en el repo.
- [x] `uv run pyright alembic tests/test_item_model.py`

**Dependencies:** Task 1

**Files likely touched:**

- `alembic/env.py`
- `alembic/versions/<revision>_create_items.py`
- `tests/test_item_model.py`

**Estimated scope:** Small

## Task 3: Verify local y quality gates

**Description:** Aplicar y revertir la migracion contra el PostgreSQL de
Compose y pasar la suite completa, Ruff y Pyright.

**Acceptance criteria:**

- [ ] `alembic upgrade head` crea `items` en local.
- [ ] `alembic downgrade -1` la elimina.
- [ ] Un segundo `upgrade head` vuelve a dejarla.
- [ ] No se usa `create_all()` en runtime.
- [ ] No hay router ni contrato HTTP nuevo.

**Verification:**

- [ ] `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `uv run pytest`
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pyright`

**Dependencies:** Task 2

**Files likely touched:**

- Ninguno, salvo correccion si el verify falla.

**Estimated scope:** Small
