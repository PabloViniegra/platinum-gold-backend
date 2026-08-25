# Tasks: Base ejecutable de The Binding of Isaac API

## Task 1: Toolchain y servicios locales

**Description:** Declarar solo las dependencias de runtime y desarrollo aprobadas,
configurar Ruff/Pyright/pytest y proporcionar PostgreSQL y Redis locales.

**Acceptance criteria:**

- [x] `pyproject.toml` contiene las dependencias y comandos del spec.
- [x] `uv.lock` queda sincronizado para Python 3.13.
- [x] `compose.yaml` ofrece PostgreSQL y Redis con health checks locales.
- [x] `.env.example` contiene valores locales/placeholders y `.env` sigue ignorado.

**Verification:**

- [x] `uv sync --all-groups`
- [x] `uv run ruff check .`
- [x] Inspeccion del diff para confirmar que no hay secretos.

**Dependencies:** None

**Files likely touched:**

- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `.env.example`
- `.gitignore`

**Estimated scope:** Medium

## Task 2: Configuracion tipada

**Description:** Cargar y validar entorno, URLs y nivel de log sin realizar I/O
ni exponer secretos.

**Acceptance criteria:**

- [x] Valores validos producen una configuracion inmutable y tipada.
- [x] URLs ausentes o esquemas incompatibles fallan de forma explicita.
- [x] La representacion de settings no muestra credenciales.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_config.py`
- [x] `uv run pyright app/core/config.py tests/test_config.py`

**Dependencies:** Task 1

**Files likely touched:**

- `app/__init__.py`
- `app/core/__init__.py`
- `app/core/config.py`
- `tests/test_config.py`

**Estimated scope:** Medium

## Task 3: FastAPI y liveness

**Description:** Crear la factoria ASGI y el primer vertical orientado por feature,
sin acceso a infraestructura.

**Acceptance criteria:**

- [x] `GET /health` devuelve exactamente `200` y `{"status": "ok"}`.
- [x] OpenAPI registra el endpoint bajo el tag `health`.
- [x] Importar `app.main` no abre conexiones.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_health.py -k liveness`
- [x] `uv run ruff check app tests`

**Dependencies:** Task 2

**Files likely touched:**

- `app/main.py`
- `app/health/__init__.py`
- `app/health/router.py`
- `app/health/schemas.py`
- `tests/test_health.py`

**Estimated scope:** Medium

## Task 4: Lifespan de PostgreSQL y Redis

**Description:** Crear recursos asincronos una vez por proceso, exponerlos mediante
dependencias y cerrarlos correctamente al apagar la aplicacion.

**Acceptance criteria:**

- [x] Engine, session factory y Redis se crean desde settings durante lifespan.
- [x] Los recursos quedan disponibles en `app.state`.
- [x] El apagado dispone ambos pools incluso tras uso normal.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_lifespan.py`
- [x] `uv run pyright app/core tests/test_lifespan.py`

**Dependencies:** Task 3

**Files likely touched:**

- `app/core/database.py`
- `app/core/redis.py`
- `app/main.py`
- `tests/test_lifespan.py`

**Estimated scope:** Medium

## Task 5: Readiness de infraestructura

**Description:** Comprobar PostgreSQL y Redis con timeouts y un contrato HTTP que
no confunda indisponibilidad con datos vacios.

**Acceptance criteria:**

- [x] Ambos checks sanos producen `200` y estado por dependencia.
- [x] Cualquier fallo o timeout produce `503` con error consistente.
- [x] La respuesta no incluye URLs ni excepciones internas.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_health.py -k readiness`
- [x] `uv run ruff check app/health tests/test_health.py`

**Dependencies:** Task 4

**Files likely touched:**

- `app/health/checks.py`
- `app/health/router.py`
- `app/health/schemas.py`
- `tests/test_health.py`

**Estimated scope:** Medium

## Task 6: Request IDs, logging y errores

**Description:** Correlacionar cada peticion y unificar errores controlados sin
registrar secretos.

**Acceptance criteria:**

- [x] Cada respuesta contiene un `X-Request-ID` valido.
- [x] IDs de cliente invalidos se sustituyen; los validos se conservan.
- [x] El log estructurado contiene metodo, ruta, estado, duracion e ID.
- [x] Readiness `503` usa el formato de error definido en el spec.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_observability.py tests/test_health.py`
- [x] Inspeccion de logs de test para confirmar ausencia de secretos.

**Dependencies:** Task 5

**Files likely touched:**

- `app/core/logging.py`
- `app/core/exceptions.py`
- `app/main.py`
- `tests/test_observability.py`
- `tests/test_health.py`

**Estimated scope:** Medium

## Task 7: Baseline de Alembic

**Description:** Configurar migraciones asincronas y una revision inicial vacia,
sin crear modelos de dominio.

**Acceptance criteria:**

- [x] Alembic obtiene la URL desde la configuracion y no desde secretos versionados.
- [x] No existe llamada a `Base.metadata.create_all()`.
- [x] La revision base puede subir y bajar limpiamente.

**Verification:**

- [x] `docker compose up -d postgres redis`
- [x] `uv run alembic upgrade head`
- [x] `uv run alembic downgrade base`
- [x] `uv run alembic upgrade head`

**Dependencies:** Task 4

**Files likely touched:**

- `alembic.ini`
- `alembic/env.py`
- `alembic/script.py.mako`
- `alembic/versions/*_baseline.py`
- `app/core/database.py`

**Estimated scope:** Medium

## Task 8: Documentacion y verificacion final

**Description:** Documentar el bootstrap local, ejecutar todos los quality gates y
corregir unicamente problemas introducidos por este setup.

**Acceptance criteria:**

- [x] README permite arrancar desde un clon limpio siguiendo comandos literales.
- [x] El alcance y los siguientes verticales quedan claros.
- [x] Todos los success criteria de `tasks/spec.md` estan comprobados.

**Verification:**

- [x] `uv run pytest`
- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pyright`
- [x] `uv run uvicorn app.main:app` y smoke test de ambos health endpoints.

**Dependencies:** Tasks 1-7

**Files likely touched:**

- `README.md`
- `tasks/todo.md`

**Estimated scope:** Small
