# Spec: Base ejecutable de The Binding of Isaac API

## Objective

Preparar una base ejecutable y verificable para el monolito modular descrito en
`docs/PRD.md`. Esta fase debe permitir desarrollar los verticales del MVP sin
reorganizar el proyecto ni acoplar el runtime a servicios externos durante los
tests.

Esta fase incluye:

- Proyecto Python 3.13 gestionado con `uv`.
- Aplicacion FastAPI creada mediante una factoria.
- Configuracion tipada desde variables de entorno.
- Clientes asincronos reutilizables para PostgreSQL y Redis.
- Migraciones gestionadas exclusivamente con Alembic.
- Endpoints publicos `GET /health` y `GET /health/ready`.
- Formato de error base y request ID para preparar una API consistente.
- Logging estructurado de peticiones sin secretos.
- Entorno local reproducible para PostgreSQL y Redis.
- Tests, lint y comprobacion estatica de tipos.

Esta fase no incluye:

- Verificacion de API keys con Clerk.
- Endpoints de items o metadata.
- Cache-aside, rate limiting o estadisticas.
- Modelos o migraciones del dominio.
- Scraping, ingestion o CLI administrativa.
- Despliegue, CDN, ETags o cache HTTP.

## Tech Stack

- Python `>=3.13`.
- FastAPI y Uvicorn.
- Pydantic 2 y Pydantic Settings.
- SQLAlchemy 2 asincrono, asyncpg y Alembic.
- redis-py con su API `asyncio`.
- Serializacion Pydantic mediante response models de FastAPI.
- pytest, pytest-asyncio y HTTPX para tests.
- Ruff para formato y lint.
- Pyright para comprobacion estatica de tipos.
- Docker Compose solo para PostgreSQL y Redis locales.

Las versiones exactas quedaran resueltas y bloqueadas en `uv.lock`; no se
mantendra un segundo fichero de dependencias.

## Commands

```bash
uv sync --all-groups
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

## Project Structure

```text
app/
|-- __init__.py
|-- main.py                 # Factoria y aplicacion ASGI
|-- core/
|   |-- __init__.py
|   |-- config.py           # Pydantic Settings
|   |-- database.py         # Engine y sesiones SQLAlchemy
|   |-- redis.py            # Cliente Redis
|   |-- logging.py          # Logging estructurado
|   `-- exceptions.py       # Errores y handlers HTTP compartidos
`-- health/
    |-- __init__.py
    |-- router.py           # Liveness y readiness
    `-- schemas.py          # Contratos de respuesta
alembic/
|-- versions/
`-- env.py
tests/
|-- conftest.py
|-- test_health.py
`-- test_config.py
tasks/
|-- spec.md
|-- plan.md
`-- todo.md
alembic.ini
compose.yaml
.env.example
pyproject.toml
```

Los futuros recursos se agregaran como modulos de primer nivel dentro de
`app/`, por ejemplo `app/items/`, sin repositorios o servicios genericos.

## Code Style

Se usaran nombres explicitos, anotaciones de tipos y dependencias inyectadas en
los limites HTTP. No se crearan abstracciones para casos de uso futuros.

```python
from typing import Annotated

from fastapi import APIRouter, Depends

from app.health.schemas import ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(checks: Annotated[ReadinessChecks, Depends()]) -> ReadinessResponse:
    return await checks.run()
```

Convenciones:

- Lineas de hasta 88 caracteres, aplicadas por Ruff.
- Imports absolutos desde `app`.
- `async` solo en operaciones con I/O.
- Schemas Pydantic separados de modelos SQLAlchemy.
- Routers limitados a HTTP, validacion e inyeccion de dependencias.
- Sin `Any` salvo en limites externos que realmente lo requieran.
- Sin comentarios que repitan lo que expresa el codigo.

## API Contract

### `GET /health`

- Publico y sin acceso a PostgreSQL, Redis o Clerk.
- Responde `200` con `{"status": "ok"}` mientras el proceso pueda atender
  peticiones.

### `GET /health/ready`

- Publico.
- Comprueba PostgreSQL y Redis con timeouts explicitos.
- Responde `200` cuando ambos estan disponibles.
- Responde `503` si falla alguna dependencia.
- Expone el estado por dependencia, pero no URLs, credenciales, excepciones ni
  detalles internos.

### Errores

Los errores controlados siguen esta forma desde el inicio:

```json
{
  "error": {
    "code": "SERVICE_UNAVAILABLE",
    "message": "A required service is unavailable"
  }
}
```

Cada respuesta incluye `X-Request-ID`. Solo se acepta un identificador aportado
por el cliente si cumple el formato y limite definidos; en otro caso se genera
uno nuevo.

## Configuration

La configuracion se carga desde variables de entorno con prefijo no obligatorio
y nombres definidos en el PRD:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api
REDIS_URL=redis://localhost:6379/0
CLERK_SECRET_KEY=
ENVIRONMENT=development
LOG_LEVEL=INFO
```

`DATABASE_URL` y `REDIS_URL` son obligatorias para ejecutar el servidor. La
clave de Clerk puede estar vacia en esta fase porque no existe autenticacion
todavia. `.env.example` solo contiene valores locales o placeholders; `.env`
nunca se versiona.

El engine usa la URL PostgreSQL asincrona tal como la recibe. No se intentara
reescribir automaticamente URLs de proveedores.

## Testing Strategy

- Tests unitarios para carga y validacion de configuracion.
- Tests API con HTTPX y transporte ASGI para liveness, readiness y request IDs.
- Dependencias de readiness sustituidas por fakes deterministas; la suite base
  no requiere Docker, Neon, Upstash ni Clerk.
- Alembic se valida aplicando `upgrade head` contra PostgreSQL local en una
  comprobacion separada del test unitario.
- Todo comportamiento nuevo se implementa con ciclo RED, GREEN, REFACTOR.

No se fija un porcentaje artificial de cobertura durante el scaffolding. Todo
comportamiento incluido en esta fase debe tener una prueba observable.

## Boundaries

### Always

- Mantener PostgreSQL como fuente de verdad y Redis como infraestructura
  descartable.
- Usar timeouts en dependencias externas.
- Mantener secretos, URLs completas y API keys fuera de logs y respuestas.
- Gestionar cambios de esquema mediante Alembic.
- Ejecutar tests, Ruff y Pyright antes de considerar completa la fase.
- Mantener el runtime importable sin conectarse a servicios externos.

### Ask First

- Agregar dependencias fuera de las enumeradas en esta especificacion.
- Crear el primer modelo o migracion de dominio.
- Cambiar contratos HTTP definidos en el PRD.
- Introducir servicios cloud requeridos por los tests.
- Implementar autenticacion, cache de negocio o rate limiting.

### Never

- Versionar secretos o usar credenciales de produccion en local.
- Ejecutar `Base.metadata.create_all()` en el arranque.
- Contactar Platinum God desde el runtime de la API.
- Registrar `X-API-Key`, `CLERK_SECRET_KEY`, `DATABASE_URL` o `REDIS_URL`.
- Ocultar una caida de PostgreSQL devolviendo colecciones vacias.
- Crear capas genericas o recursos futuros durante este setup.

## Success Criteria

- `uv sync --all-groups` instala un entorno reproducible con Python 3.13.
- `uv run uvicorn app.main:app` arranca con configuracion local valida.
- `GET /health` devuelve `200` sin consultar infraestructura.
- `GET /health/ready` diferencia correctamente entre estado listo y no listo.
- Todas las respuestas contienen un `X-Request-ID` valido y los logs usan el
  mismo valor.
- El runtime cierra correctamente los pools de PostgreSQL y Redis.
- Alembic puede aplicar `upgrade head` sobre PostgreSQL local sin usar
  `create_all()`.
- `.env` permanece ignorado y `.env.example` no contiene secretos.
- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` y
  `uv run pyright` finalizan correctamente.
- README documenta el bootstrap local y todos los comandos anteriores.

## Open Questions

Ninguna. El alcance confirmado es la base ejecutable; el resto del MVP se
planificara como trabajo posterior.
