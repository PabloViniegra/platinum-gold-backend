# Tasks: Autenticacion Clerk por API key

## Task 1: Contrato HTTP con verificador fake

**Description:** Entregar el contrato de autenticacion sobre una ruta stub,
sustituyendo Clerk por un fake. Incluye codes de aplicacion en el handler HTTP
sin cambiar 404 ni 422.

**Acceptance criteria:**

- [x] Sin `X-API-Key` → `401` `API_KEY_REQUIRED`.
- [x] Fake que rechaza → `401` `INVALID_API_KEY`.
- [x] Fake sin `api:access` → `403` `INSUFFICIENT_PERMISSIONS`.
- [x] Fake valido con `api:access` → `200` en el stub.
- [x] Fake que simula Clerk caido → `503` `SERVICE_UNAVAILABLE`.
- [x] `404` sigue `NOT_FOUND` y `422` sigue `VALIDATION_ERROR`.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_auth.py tests/test_observability.py`
- [x] `uv run pyright app/auth app/core/exceptions.py tests/test_auth.py`

**Dependencies:** None

**Files likely touched:**

- `app/core/exceptions.py`
- `app/auth/__init__.py`
- `app/auth/principal.py`
- `app/auth/dependencies.py`
- `tests/test_auth.py`

**Estimated scope:** Medium

## Task 2: Adaptador Clerk

**Description:** Traducir `verify_api_key_async` a `ApiPrincipal` o a error de
aplicacion. Timeout y secret ausente fallan cerrado. Los tests no abren red.

**Acceptance criteria:**

- [x] `subject` → `user_id` y `scopes` → `frozenset[str]`.
- [x] `expired` o `revoked` → invalida, aunque el SDK devuelva 200.
- [x] Errores 400/404 del SDK → invalida.
- [x] Timeout, 5xx o `CLERK_SECRET_KEY` ausente → no disponible.
- [x] Ningun modulo fuera de `app/auth/clerk.py` importa `clerk_backend_api`.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_clerk_adapter.py`
- [x] `uv run pyright app/auth tests/test_clerk_adapter.py`
- [x] `rg clerk_backend_api app` solo encuentra `app/auth/clerk.py`

**Dependencies:** Task 1

**Files likely touched:**

- `app/auth/clerk.py`
- `tests/test_clerk_adapter.py`

**Estimated scope:** Small

## Task 3: Lifespan, OpenAPI y documentacion

**Description:** Crear el cliente Clerk en el lifespan, documentar `X-API-Key`
en OpenAPI, dejar health publico y actualizar el README.

**Acceptance criteria:**

- [x] Lifespan guarda un `ApiKeyVerifier` en `app.state`.
- [x] Sin secret, el verifier de produccion falla cerrado.
- [x] OpenAPI documenta el esquema `X-API-Key`.
- [x] `GET /health` y `GET /health/ready` siguen sin exigir clave.
- [x] README indica que las rutas protegidas necesitan `CLERK_SECRET_KEY`.

**Verification:**

- [x] RED y GREEN: `uv run pytest tests/test_auth.py tests/test_health.py`
- [x] `uv run pytest`
- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pyright`

**Dependencies:** Task 2

**Files likely touched:**

- `app/main.py`
- `tests/test_auth.py`
- `README.md`

**Estimated scope:** Small
