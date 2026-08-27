# Tasks: Hardening Redis y cache-aside de items

El spec aprobado es `tasks/spec-redis-cache.md` y el plan de implementación es
`tasks/plan-redis-cache.md`. Cada tarea sigue RED, GREEN, REFACTOR y deja el
repositorio verificable.

## Task 1: Cerrar el boundary de conexion Redis

**Description:** Endurecer `REDIS_URL` y la construccion del cliente para que
ninguna opcion de URL pueda anular TLS, timeouts, decoding o limites del pool.

**Acceptance criteria:**

- [x] Solo se aceptan URLs `redis`/`rediss` con target, puerto, credenciales y
  base conformes al spec; query parameters y fragments se rechazan.
- [x] Produccion remota exige TLS y password sin exponerlos en errores.
- [x] El cliente configura TLS/hostname, timeouts, decoding y pool acotado de
  forma explicita.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_config.py tests/test_redis.py`
- [x] `uv run ruff check app/core tests/test_config.py tests/test_redis.py`
- [x] `uv run pyright app/core tests/test_config.py tests/test_redis.py`

**Dependencies:** None

**Files likely touched:**

- `app/core/config.py`
- `app/core/redis.py`
- `tests/test_config.py`
- `tests/test_redis.py`

**Estimated scope:** Medium

## Task 2: Implementar cache generacional tipada

**Description:** Crear el adaptador Redis especifico de items con generacion,
claves deterministas, TTL y validacion de payloads, sin integrar aun FastAPI.

**Acceptance criteria:**

- [x] Item, listado y metadata producen claves versionadas; filtros equivalentes
  producen el mismo hash sin texto en claro.
- [x] Los payloads validos hacen round-trip y los ausentes/corruptos son miss.
- [x] Toda escritura tiene TTL y `invalidate()` incrementa la generacion.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_cache.py`
- [x] `uv run ruff check app/items/cache.py tests/test_cache.py`
- [x] `uv run pyright app/items/cache.py tests/test_cache.py`

**Dependencies:** Task 1

**Files likely touched:**

- `app/items/cache.py`
- `tests/test_cache.py`

**Estimated scope:** Small

## Task 3: Integrar cache-aside en lecturas deterministas

**Description:** Inyectar `ItemCache` en el servicio y cubrir el camino
hit/miss/fallback de item, listado y metadata sin cachear `/random`.

**Acceptance criteria:**

- [x] Un hit devuelve la respuesta sin invocar el repository y un miss consulta
  PostgreSQL y repuebla Redis.
- [x] Fallos Redis operativos o payloads invalidos caen a PostgreSQL y producen
  warnings sanitizados; errores de programacion no se ocultan.
- [x] `/random`, auth, errores y cuerpos HTTP conservan el comportamiento actual.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_cache.py tests/test_items_api.py`
- [x] `uv run ruff check app/items tests/test_cache.py tests/test_items_api.py`
- [x] `uv run pyright app/items tests/test_cache.py tests/test_items_api.py`

**Dependencies:** Task 2

**Files likely touched:**

- `app/items/cache.py`
- `app/items/dependencies.py`
- `app/items/router.py`
- `app/items/service.py`
- `tests/test_items_api.py`

**Estimated scope:** Medium

## Checkpoint: Cache read path

- [x] Tasks 1-3 cumplen sus tests enfocados.
- [x] Una lectura repetida evita PostgreSQL.
- [x] Redis indisponible no rompe una lectura resoluble desde PostgreSQL.

## Task 4: Invalidar despues de la ingesta

**Description:** Extender la configuracion y el CLI offline para crear Redis,
incrementar la generacion solo tras commit y cerrar todos los recursos.

**Acceptance criteria:**

- [x] Una ingesta confirmada invalida despues del commit; rollback o
  configuracion invalida no cambian la generacion.
- [x] Redis se cierra en exito y fallo, igual que el engine PostgreSQL.
- [x] Un fallo post-commit termina no cero, explica el estado parcial sin
  secretos y puede recuperarse repitiendo la ingesta.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_config.py tests/test_ingestion_service.py tests/test_ingest_cli.py`
- [x] `uv run ruff check app/core app/ingestion scripts tests/test_ingestion_service.py tests/test_ingest_cli.py`
- [x] `uv run pyright app/core app/ingestion scripts tests/test_ingestion_service.py tests/test_ingest_cli.py`

**Dependencies:** Tasks 1-2

**Files likely touched:**

- `app/core/config.py`
- `app/items/cache.py`
- `scripts/ingest.py`
- `tests/test_config.py`
- `tests/test_ingest_cli.py`

**Estimated scope:** Medium

## Task 5: Documentar y verificar la slice completa

**Description:** Actualizar configuracion/documentacion, ejecutar todos los
gates y resolver solo findings introducidas por este trabajo.

**Acceptance criteria:**

- [x] README documenta el contrato Redis, TTLs, fail-open e invalidacion.
- [x] Spec, plan, tareas y codigo no se contradicen.
- [x] Reviews de calidad, Python y seguridad no dejan findings introducidas sin
  resolver.

**Verification:**

- [x] `uv run pytest`
- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pyright`
- [x] `git diff --check`
- [x] Review con `code-reviewer`, `python-reviewer` y `security-reviewer`

**Dependencies:** Tasks 3-4

**Files likely touched:**

- `README.md`
- `tasks/spec-redis-cache.md`
- `tasks/plan-redis-cache.md`
- `tasks/todo-redis-cache.md`

**Estimated scope:** Small

## Checkpoint: Complete

- [x] Todos los criterios de `tasks/spec-redis-cache.md` estan cubiertos.
- [x] Todos los gates estan verdes.
- [x] El diff esta listo para el workflow de shipping, sin desplegarlo.
