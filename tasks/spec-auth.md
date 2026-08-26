# Spec: Autenticacion Clerk por API key

## Objective

Proteger los endpoints de aplicacion con API keys de Clerk transportadas en
`X-API-Key`, sin filtrar tipos de Clerk al resto del codigo y sin implementar
todavia items, cache-aside ni rate limiting.

Esta fase incluye:

- Lectura de `X-API-Key` con `APIKeyHeader(auto_error=False)`.
- Verificacion contra Clerk mediante `clerk-backend-api` ya declarado.
- Mapeo a `ApiPrincipal` interno (`user_id`, `scopes`).
- Exigir el scope `api:access` en rutas protegidas.
- 401 / 403 / 503 con el envelope de error existente.
- Esquema OpenAPI para introducir la clave en Swagger UI.
- Tests con Clerk sustituido por un fake.

Esta fase no incluye:

- Cache de autenticacion en Redis.
- Endpoints de items o metadata.
- Rate limiting.
- Uso del header `Authorization`.
- Contactar Clerk en `/health` o `/health/ready`.

## Tech Stack

Sin dependencias nuevas. Se usa `clerk-backend-api>=7` ya en `pyproject.toml`.

Verificacion oficial: `Clerk(...).api_keys.verify_api_key_async(secret=...)`,
equivalente a `POST /api_keys/verify`. El cliente se autentica con
`CLERK_SECRET_KEY` como bearer.

## Commands

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
make check
```

## Project Structure

```text
app/auth/
|-- __init__.py
|-- principal.py       # ApiPrincipal
|-- clerk.py           # Adaptador Clerk -> ApiPrincipal
`-- dependencies.py    # APIKeyHeader, get_principal, require_scopes
tests/test_auth.py
tasks/spec-auth.md
```

Los endpoints de producto no se anaden. Los tests HTTP montan una ruta stub
protegida sobre `create_app()`.

## Code Style

```python
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

from app.auth.principal import ApiPrincipal


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class ApiPrincipal:
    user_id: str
    scopes: frozenset[str]


async def get_principal(
    api_key: Annotated[str | None, Security(api_key_header)],
) -> ApiPrincipal: ...
```

Convenciones:

- `user_id` sale del campo `subject` de Clerk, no de un `user_id` del SDK.
- Ningun modulo fuera de `app/auth/clerk.py` importa `clerk_backend_api`.
- `require_scopes("api:access")` es una factory de dependencia. Esta fase solo
  exige `api:access`.
- Reutilizar `dependency_timeout_seconds` como timeout de Clerk.
- No registrar el valor de `X-API-Key` ni `CLERK_SECRET_KEY`.

## API Contract

### Header

```http
X-API-Key: ak_xxxxxxxxxxxxxxxxx
```

`Authorization` no se usa.

### Quien queda publico

- `GET /health`
- `GET /health/ready`

### Codigos

| Situacion                         | HTTP | code                      |
| --------------------------------- | ---- | ------------------------- |
| Falta `X-API-Key`                 | 401  | `API_KEY_REQUIRED`        |
| Clave invalida, caducada o revocada | 401  | `INVALID_API_KEY`         |
| Clerk 400/404 al verificar        | 401  | `INVALID_API_KEY`         |
| Falta `api:access`                | 403  | `INSUFFICIENT_PERMISSIONS`|
| Clerk caido, timeout o sin secret | 503  | `SERVICE_UNAVAILABLE`     |

Mensajes genericos, sin distinguir caducada de revocada. El envelope no cambia:

```json
{
  "error": {
    "code": "API_KEY_REQUIRED",
    "message": "API key required"
  }
}
```

El handler HTTP actual aplasta `detail` a `HTTP_{status}`. Hay que respetar
`code` y `message` de aplicacion cuando el endpoint los aporta, sin filtrar
texto de Clerk.

### OpenAPI

El esquema de seguridad `X-API-Key` debe aparecer en Swagger UI. Health sigue
sin exigir autenticacion.

## Configuration

`CLERK_SECRET_KEY` sigue siendo opcional en `Settings` para no romper tests que
no autentican. El adaptador real falla cerrado si falta la clave.

No hay cache de auth. Medir primero, como dice el PRD.

## Testing Strategy

HTTPX `ASGITransport`. Clerk mockeado. La suite no llama a Clerk, Neon ni
Upstash.

Casos:

- Sin header: 401 `API_KEY_REQUIRED`.
- Fake que rechaza: 401 `INVALID_API_KEY`.
- Fake con scopes sin `api:access`: 403 `INSUFFICIENT_PERMISSIONS`.
- Fake valido con `api:access`: 200 en la ruta stub.
- Fake que simula Clerk caido: 503 `SERVICE_UNAVAILABLE`.
- `/health` y `/health/ready` siguen publicos.
- OpenAPI documenta `X-API-Key`.
- Los logs de peticion no contienen el valor de la clave.

RED, GREEN, REFACTOR en cada comportamiento.

## Boundaries

### Always

- Fallar cerrado si Clerk no puede verificar.
- Mantener tipos de Clerk fuera de routers y del resto de `app/`.
- Timeouts en la llamada a Clerk.
- Mockear Clerk en tests.

### Ask first

- Cache de autenticacion.
- Nuevo scope de producto distinto de `api:access`.
- Endpoint de producto (`/v1/me`, items, etc.).
- Dependencia adicional.

### Never

- Loguear o persistir la API key en claro.
- Usar `Authorization` para este mecanismo.
- Contactar Clerk desde health.
- Aceptar una peticion autenticada si Clerk no responde.
- Implementar items, cache-aside o rate limit en esta fase.

## Success Criteria

- Una ruta protegida de test exige `X-API-Key` valida con scope `api:access`.
- Falta de clave, clave invalida y falta de scope responden 401/403 con los
  codes del contrato.
- Clerk indisponible responde 503 y no deja pasar la peticion.
- Health no cambia de contrato ni llama a Clerk.
- OpenAPI permite introducir `X-API-Key` en Swagger UI.
- `uv run pytest`, Ruff y Pyright siguen verdes.
- Ningun test de esta fase contacta Clerk de verdad.

## Assumptions

1. `ApiPrincipal.user_id` es el `subject` de `verify_api_key_async`.
2. Caducada y revocada se colapsan a 401 `INVALID_API_KEY`.
3. Clerk caido o timeout es 503, no 401, para no fingir una clave invalida.
4. No hay endpoint de producto en esta fase. Solo stub de test.
5. Un cliente Clerk por proceso, creado en el lifespan, igual que Redis.

## Open Questions

Ninguna bloqueante si se aceptan las assumptions. La decision que mas cambia
el contrato es la 3: 503 frente a 401 cuando Clerk no responde.
