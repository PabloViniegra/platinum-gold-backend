# Implementation Plan: Base ejecutable de The Binding of Isaac API

## Overview

Construir la base en incrementos verificables: primero toolchain y configuracion,
despues un proceso FastAPI vivo, a continuacion conexiones y readiness, y por
ultimo migraciones y documentacion. Cada incremento debe mantener el proyecto
importable y con sus pruebas enfocadas en verde.

## Dependency Graph

```text
Toolchain and local services
          |
          v
Typed configuration
          |
          v
FastAPI + liveness
          |
          +-----------------+
          |                 |
          v                 v
Database/Redis lifecycle  Request observability
          |                 |
          v                 |
Readiness checks <----------+
          |
          v
Alembic baseline
          |
          v
Bootstrap documentation
```

## Architecture Decisions

- Mantener un monolito modular orientado por feature. Solo `core` sera
  transversal; `health` sera el primer vertical completo.
- Usar una factoria `create_app` para que los tests puedan inyectar configuracion
  y dependencias sin contactar servicios reales.
- Crear engine y clientes durante el lifespan, no durante imports. Esto permite
  importar OpenAPI, ejecutar tests y usar Alembic sin I/O accidental.
- Mantener readiness fail-closed: si PostgreSQL o Redis no responden dentro del
  timeout, se devuelve `503` sin detalles internos.
- Mantener liveness libre de I/O para distinguir proceso vivo de infraestructura
  lista.
- Usar Alembic como unica autoridad de esquema. La revision inicial vacia valida
  el pipeline sin inventar modelos de dominio antes de tiempo.
- Usar dependencias/fakes para comprobar readiness. Los tests rapidos no arrancan
  contenedores ni llaman servicios cloud.
- Mantener el cliente Redis y el engine SQLAlchemy en `app.state`; las
  dependencias HTTP acceden a recursos ya inicializados por el lifespan.

## Implementation Order

### Phase 1: Foundation

- Task 1: Configurar dependencias, quality gates y servicios locales.
- Task 2: Implementar configuracion tipada mediante TDD.
- Task 3: Crear la aplicacion FastAPI y el vertical de liveness mediante TDD.

### Checkpoint: Foundation

- `uv sync --all-groups` termina correctamente.
- La configuracion invalida falla antes de iniciar el servidor.
- `GET /health` responde sin PostgreSQL ni Redis.
- Tests, Ruff y Pyright estan en verde para el alcance construido.

### Phase 2: Runtime Infrastructure

- Task 4: Gestionar PostgreSQL y Redis durante el lifespan.
- Task 5: Implementar readiness con degradacion segura mediante TDD.
- Task 6: Incorporar request IDs, logging y errores consistentes mediante TDD.

### Checkpoint: Runtime

- Los recursos se crean una vez y se cierran al finalizar el lifespan.
- Readiness devuelve `200` o `503` segun el estado real inyectado.
- Los request IDs coinciden entre cabecera y logs.
- Ningun log o error expone configuracion sensible.

### Phase 3: Schema and Developer Experience

- Task 7: Inicializar Alembic con una revision base vacia.
- Task 8: Documentar y verificar el bootstrap local completo.

### Checkpoint: Complete

- Alembic aplica `upgrade head` en PostgreSQL local.
- El servidor arranca con el entorno local documentado.
- Todos los criterios de `tasks/spec.md` estan cubiertos.
- Suite completa, formato, lint y tipos estan en verde.
- El cambio queda listo para revision de calidad y seguridad.

## Verification Strategy

Cada tarea de comportamiento sigue RED, GREEN, REFACTOR:

1. Escribir el test observable y confirmar que falla por el comportamiento
   ausente.
2. Implementar solo el minimo necesario para hacerlo pasar.
3. Ejecutar el test enfocado.
4. Refactorizar solo si reduce complejidad y volver a ejecutar el test.
5. Ejecutar el checkpoint acumulado cuando corresponda.

Comandos finales:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
docker compose up -d postgres redis
uv run alembic upgrade head
```

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Inicializar clientes en imports | Alto | Crear recursos exclusivamente en lifespan |
| Tests acoplados a cloud | Alto | Sustituir checks por fakes y separar smoke test local |
| Readiness filtra errores internos | Medio | Respuesta cerrada y logs saneados |
| URL Neon incompatible con Alembic | Medio | Compartir configuracion async y usar `run_sync` |
| Redis bloquea lecturas futuras | Medio | Mantener cliente desacoplado; la politica fail-open se implementara con cache/rate limit |
| Setup inventa dominio prematuramente | Medio | Revision Alembic vacia, sin modelos de items |
| Dependencias divergen | Bajo | Unico manifiesto `pyproject.toml` y `uv.lock` |

## Parallelization

No se paralelizara la escritura de esta base porque todas las tareas comparten
la factoria y la configuracion. La consulta de documentacion oficial y la
revision final si pueden ejecutarse en paralelo cuando los contratos esten
estables.

## Open Questions

Ninguna.
