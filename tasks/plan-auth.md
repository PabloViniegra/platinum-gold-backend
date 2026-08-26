# Implementation Plan: Autenticacion Clerk por API key

## Overview

Entregar el vertical de auth en tres incrementos: primero el contrato HTTP con
un verificador fake, despues el adaptador real de `clerk-backend-api`, y por
ultimo el cliente en el lifespan, OpenAPI y documentacion. Cada incremento deja
la suite en verde. No se tocan items, cache ni rate limit.

El spec aprobado es `tasks/spec-auth.md`. El plan de la base ejecutable sigue
en `tasks/plan.md` y `tasks/todo.md`.

## Dependency Graph

```text
Application error codes
          |
          v
ApiPrincipal + verifier protocol + HTTP dependency
          |
          v
HTTP contract (401 / 403 / 503 / 200) with fake
          |
          v
Clerk adapter (verify_api_key_async)
          |
          v
Lifespan client + OpenAPI + README
```

## Architecture Decisions

- Un `Protocol` `ApiKeyVerifier` es el unico punto de sustitucion en tests.
  `dependency_overrides` gana al cliente real, igual que readiness.
- Los errors de aplicacion (`API_KEY_REQUIRED`, etc.) viajan en una excepcion
  propia. El handler actual aplasta `detail`; hay que respetar `code` y
  `message` sin cambiar 404/422.
- `ApiPrincipal.user_id` sale de `subject`. Caducada y revocada se colapsan a
  401. Clerk caido o timeout es 503.
- Un cliente `Clerk` por proceso, context manager async en el lifespan, con
  `timeout_ms` derivado de `dependency_timeout_seconds`.
- Si falta `CLERK_SECRET_KEY`, el runtime falla cerrado. Settings no se vuelve
  mas estricto, para no romper tests que no autentican.
- Ninguna ruta de producto. Los tests HTTP montan un stub protegido sobre
  `create_app()`.
- `clerk_backend_api` solo se importa en `app/auth/clerk.py`.

## Implementation Order

### Phase 1: HTTP contract

- Task 1: Contrato 401/403/503/200 con verificador fake, mediante TDD.

### Checkpoint: Contract

- La ruta stub cubre los cinco casos del spec.
- `GET /health` 404/422 no cambian de envelope.
- `uv run pytest tests/test_auth.py tests/test_observability.py` verde.

### Phase 2: Clerk adapter

- Task 2: Adaptar `verify_api_key_async` a `ApiPrincipal`, mediante TDD.

### Checkpoint: Adapter

- El adaptador no hace I/O en tests; el SDK se sustituye.
- 400/404/expired/revoked → invalida. Timeout/5xx/sin secret → 503.
- Ningun test de esta fase llama a Clerk de verdad.

### Phase 3: Runtime wiring

- Task 3: Lifespan, esquema OpenAPI, health publico y README.

### Checkpoint: Complete

- OpenAPI documenta `X-API-Key`.
- Health sigue publico y no contacta Clerk.
- `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run pyright` verde.
- Listo para review de calidad y seguridad.

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
| El handler aplasta codes de auth | Alto | Excepcion de aplicacion + tests de 404/422 intactos |
| Clerk 200 con `expired`/`revoked` | Alto | Tratar ambos flags como invalida, ademas de 400/404 |
| Cliente Clerk en import | Alto | Crear solo en lifespan, igual que Redis |
| Types de Clerk se filtran | Medio | Un solo modulo importa el SDK; Pyright en routers |
| Tests golpean Clerk real | Alto | Protocol + override; adapter tests con fake SDK |
| OpenAPI no muestra el esquema | Bajo | Registrar `X-API-Key` en `create_app`, no esperar rutas de producto |

## Parallelization

No. Las tres tareas comparten handler, dependencias y `create_app`.

## Open Questions

Ninguna. El spec esta aprobado, incluido 503 si Clerk no responde.
