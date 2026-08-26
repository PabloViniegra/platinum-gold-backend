# Tasks: Ingesta inicial offline del catalogo de items

El spec aprobado es `tasks/spec-initial-ingestion.md` y el plan aprobado es
`tasks/plan-initial-ingestion.md`. Cada tarea se ejecuta como un incremento
TDD independiente y deja el repositorio en un estado verificable.

## Task 1: Contrato y loader del snapshot

**Description:** Implementar el schema Pydantic estricto y el loader JSON que
conviertan un fichero UTF-8 en un `ItemSnapshot` validado, sin abrir una
conexion ni depender de la API.

**Acceptance criteria:**

- [x] Un snapshot valido con aliases camelCase produce modelos Python en
  snake_case y elimina espacios exteriores de strings.
- [x] JSON invalido, campos desconocidos, tipos incompatibles, strings vacios,
  URLs no HTTP(S), calidad fuera de rango, lista vacia y `gameId` duplicado
  fallan con errores de validacion observables.
- [x] La validacion completa ocurre antes de exponer el snapshot al servicio de
  persistencia.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_ingestion.py`
- [x] `uv run pyright app/ingestion tests/test_ingestion.py`
- [x] `uv run ruff check app/ingestion tests/test_ingestion.py`

**Dependencies:** None

**Files likely touched:**

- `app/ingestion/__init__.py`
- `app/ingestion/schemas.py`
- `app/ingestion/loader.py`
- `tests/test_ingestion.py`

**Estimated scope:** Medium

## Task 2: Metadata singleton y migracion

**Description:** Crear el modelo SQLAlchemy de metadata del dataset y su
migracion reversible, registrando el modelo en Alembic sin modificar el
arranque automatico de tablas.

**Acceptance criteria:**

- [x] La tabla tiene una unica fila identificada por una clave singleton,
  `dataset_version` y `last_sync` obligatorios, y `game_version` nullable.
- [x] `upgrade` y `downgrade` crean y eliminan la tabla con sus restricciones
  sin usar `Base.metadata.create_all()`.
- [x] Alembic conoce el modelo y la migracion no requiere secretos versionados.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_dataset_metadata.py`
- [x] `TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api_test make integration`
- [x] `uv run pyright app/meta alembic tests/test_dataset_metadata.py`

**Dependencies:** None

**Files likely touched:**

- `app/meta/__init__.py`
- `app/meta/models.py`
- `alembic/env.py`
- `alembic/versions/*_create_dataset_metadata.py`
- `tests/test_dataset_metadata.py`

**Estimated scope:** Medium

## Task 3: Persistencia PostgreSQL del snapshot

**Description:** Añadir el repository de escritura que ejecute upsert batch de
items por `game_id` y upsert de la fila singleton de metadata, sin hacer
commit propio.

**Acceptance criteria:**

- [x] Un item nuevo se inserta y un item existente se actualiza por `game_id`
  sin cambiar su PK interna ni `created_at`.
- [x] Los campos del snapshot y `updated_at` se actualizan en un conflicto;
  los registros ausentes no se eliminan.
- [x] La metadata se crea o actualiza con `dataset_version`, `game_version` y
  `last_sync` UTC dentro de la sesion recibida.

**Verification:**

- [x] RED y GREEN: `TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api_test uv run pytest -o addopts='' tests/integration/test_ingestion_postgres.py`
- [x] `uv run ruff check app/ingestion tests/integration/test_ingestion_postgres.py`
- [x] `uv run pyright app/ingestion tests/integration/test_ingestion_postgres.py`

**Dependencies:** Task 1, Task 2

**Files likely touched:**

- `app/ingestion/repository.py`
- `tests/integration/test_ingestion_postgres.py`

**Estimated scope:** Medium

## Task 4: Servicio transaccional

**Description:** Orquestar la persistencia de un snapshot validado con una
unica transaccion de session factory y demostrar el rollback completo cuando
falla un paso posterior.

**Acceptance criteria:**

- [x] El servicio valida/recibe el lote antes de abrir la transaccion y
  ejecuta items y metadata en el mismo contexto.
- [x] Una excepcion de persistencia no deja cambios parciales y no publica
  metadata de sincronizacion.
- [x] El servicio no importa FastAPI ni realiza llamadas de red.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_ingestion_service.py`
- [x] `uv run pyright app/ingestion tests/test_ingestion_service.py`
- [x] `uv run ruff check app/ingestion tests/test_ingestion_service.py`

**Dependencies:** Task 3

**Files likely touched:**

- `app/ingestion/service.py`
- `tests/test_ingestion_service.py`

**Estimated scope:** Small

## Task 5: CLI offline

**Description:** Exponer `python -m scripts.ingest` con ruta de entrada
explicita, carga previa a la transaccion y errores operativos sanitizados.

**Acceptance criteria:**

- [ ] `uv run python -m scripts.ingest --input data/items.example.json` usa
  `DATABASE_URL` y termina correctamente contra una base configurada.
- [ ] Falta de ruta, fichero ilegible, JSON invalido, validacion fallida o
  PostgreSQL indisponible terminan con codigo no cero sin mostrar secretos.
- [ ] El modulo no contacta la red upstream ni se registra en el lifespan HTTP.

**Verification:**

- [ ] RED y GREEN: `uv run pytest tests/test_ingest_cli.py`
- [ ] `uv run pyright scripts tests/test_ingest_cli.py`
- [ ] `uv run ruff check scripts tests/test_ingest_cli.py`

**Dependencies:** Task 1, Task 4

**Files likely touched:**

- `scripts/ingest.py`
- `data/items.example.json`
- `tests/test_ingest_cli.py`

**Estimated scope:** Medium

## Task 6: Metadata en `/v1/meta`

**Description:** Extender la lectura existente del catalogo para devolver la
metadata disponible y mantener los nulos antes de la primera ingesta.

**Acceptance criteria:**

- [ ] `MetaResponse` expone `datasetVersion` nullable sin romper el contrato
  camelCase existente.
- [ ] Sin fila de metadata, `/v1/meta` mantiene `datasetVersion`,
  `gameVersion` y `lastSync` en `null`.
- [ ] Con metadata, `/v1/meta` devuelve sus valores y el recuento real de
  items; health y autenticacion permanecen sin cambios.

**Verification:**

- [ ] RED y GREEN: `uv run pytest tests/test_items_api.py`
- [ ] `uv run pyright app/items tests/test_items_api.py`
- [ ] `uv run ruff check app/items tests/test_items_api.py`

**Dependencies:** Task 2

**Files likely touched:**

- `app/items/repository.py`
- `app/items/service.py`
- `app/items/schemas.py`
- `tests/test_items_api.py`

**Estimated scope:** Medium

## Task 7: Integracion, fixture y documentacion

**Description:** Completar la verificacion opt-in de repeticion y atomicidad,
documentar el comando soportado y actualizar los artefactos de tareas con el
estado real de la implementacion.

**Acceptance criteria:**

- [ ] La integracion cubre rollback de lote, metadata posterior a commit,
  repeticion y conservacion de filas ausentes.
- [ ] README documenta la fuente de ejecucion, el comando offline, la base
  local de prueba y que no existe scraping en runtime.
- [ ] El spec y el plan no contradicen el comportamiento implementado.

**Verification:**

- [ ] `TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api_test make integration`
- [ ] `uv run pytest`
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pyright`

**Dependencies:** Tasks 1-6

**Files likely touched:**

- `tests/integration/test_ingestion_postgres.py`
- `README.md`
- `tasks/todo-initial-ingestion.md`

**Estimated scope:** Medium

## Task 8: Review de calidad y seguridad

**Description:** Revisar el diff completo contra el spec aprobado, comprobar
que no hay secretos ni I/O de ingestion en la API y corregir solo problemas
introducidos por esta slice.

**Acceptance criteria:**

- [ ] La revision de calidad no encuentra regresiones sin resolver.
- [ ] La revision de seguridad no encuentra credenciales, logs sensibles ni
  rutas de escritura remota fuera del alcance aprobado.
- [ ] El worktree queda con verificaciones finales documentadas y listo para
  el flujo de shipping.

**Verification:**

- [ ] `git diff --check`
- [ ] `uv run pytest`
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pyright`
- [ ] Review con `code-reviewer`, `python-reviewer` y `security-reviewer`

**Dependencies:** Task 7

**Files likely touched:**

- Ninguno previsto; solo se modifican archivos si una finding introducida lo
  requiere.

**Estimated scope:** Small

## Checkpoint: After Tasks 1-2

- [ ] El contrato de entrada y la tabla de metadata están definidos y
  verificables.
- [ ] La suite base permanece en verde.

## Checkpoint: After Tasks 3-5

- [ ] Un snapshot válido atraviesa persistencia, transacción y CLI.
- [ ] Un fallo no deja cambios parciales.

## Checkpoint: Complete

- [ ] Todos los criterios de `tasks/spec-initial-ingestion.md` están cubiertos.
- [ ] Base e integración opt-in pasan junto con Ruff y Pyright.
- [ ] La revisión de calidad y seguridad está resuelta.
