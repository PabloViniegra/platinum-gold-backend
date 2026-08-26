# Implementation Plan: Hardening Redis y cache-aside de items

## Overview

Implementar `tasks/spec-redis-cache.md` en cuatro incrementos TDD: cerrar
primero el contrato de conexion Redis, construir despues el adaptador de cache
generacional, integrarlo en las lecturas deterministas y, por ultimo, conectar
la invalidacion al CLI de ingesta despues del commit. Cada incremento mantiene
la suite en verde y no cambia el contrato HTTP publico.

## Dependency Graph

```text
Redis URL contract + safe client
               |
               v
Typed generational item cache
               |
               +--------------------+
               |                    |
               v                    v
Deterministic API cache-aside   Post-commit ingestion invalidation
               |                    |
               +---------+----------+
                         v
                 Documentation + review
```

## Architecture Decisions

- `app/core/redis.py` mantiene la construccion del cliente y
  `app/core/config.py` rechaza cualquier URL capaz de alterar sus kwargs.
- `app/items/cache.py` es un adaptador especifico de items, no un framework de
  cache generico. Usa los schemas de respuesta existentes como frontera tipada.
- Una clave de generacion compartida hace obsoletas todas las claves anteriores
  con un unico `INCR`, evita `SCAN` y elimina la race de repoblado durante un
  borrado por patron.
- `ItemService` orquesta cache-aside. El repository sigue representando solo
  PostgreSQL y no conoce Redis.
- El CLI crea y cierra su propio cliente Redis. La invalidacion ocurre despues
  de que `IngestionService.ingest()` haya salido del contexto transaccional.
- Solo fallos operativos Redis conocidos hacen fail-open en lecturas. Los
  errores de programacion y `CancelledError` siguen propagandose.

## Implementation Order

### Phase 1: Redis boundary

1. Escribir tests RED para URLs Redis ambiguas, opciones query, credenciales,
   bases, TLS y kwargs del cliente.
2. Endurecer `Settings`/`IngestionSettings` y `create_redis()` con el cambio
   minimo que satisfaga esos tests.
3. Ejecutar tests enfocados, Ruff y Pyright antes de ampliar el alcance.

### Phase 2: Cache adapter

1. Definir el `ItemCache` minimo y fakes desde los casos de uso observables.
2. Implementar generacion, claves deterministas, JSON validado, TTLs e
   invalidacion atomica.
3. Demostrar fallback ante miss, payload corrupto y fallos Redis esperables sin
   involucrar FastAPI ni PostgreSQL real.

### Phase 3: Read path

1. Inyectar el adaptador desde `app.state.redis` conservando overrides de tests.
2. Añadir cache-aside a item, listado y metadata; excluir `/random`.
3. Verificar hits sin repository, misses con repoblado, contrato HTTP intacto y
   warnings sanitizados en fallos operativos.

### Phase 4: Ingestion invalidation

1. Ampliar la configuracion offline con el contrato Redis aprobado.
2. Crear/cerrar Redis en el CLI e invalidar solo tras retorno exitoso del
   servicio transaccional.
3. Diferenciar el fallo post-commit en stderr sin credenciales y demostrar que
   rollback/configuracion invalida no invalidan.

### Phase 5: Completion

1. Actualizar README y los artefactos de tareas con el comportamiento real.
2. Ejecutar todos los gates y revisar el diff completo contra el spec.
3. Corregir solo findings introducidas por esta slice.

## Verification Checkpoints

### Checkpoint: Redis boundary

- `uv run pytest tests/test_config.py tests/test_redis.py`
- `uv run ruff check app/core tests/test_config.py tests/test_redis.py`
- `uv run pyright app/core tests/test_config.py tests/test_redis.py`

### Checkpoint: Cache read path

- `uv run pytest tests/test_cache.py tests/test_items_api.py`
- `uv run ruff check app/items tests/test_cache.py tests/test_items_api.py`
- `uv run pyright app/items tests/test_cache.py tests/test_items_api.py`

### Checkpoint: Ingestion invalidation

- `uv run pytest tests/test_ingestion_service.py tests/test_ingest_cli.py`
- `uv run ruff check app/ingestion scripts tests/test_ingestion_service.py tests/test_ingest_cli.py`
- `uv run pyright app/ingestion scripts tests/test_ingestion_service.py tests/test_ingest_cli.py`

### Checkpoint: Complete

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pyright`
- `git diff --check`
- Review con `code-reviewer`, `python-reviewer` y `security-reviewer`.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Query options de URL anulan controles | Alto | Rechazarlas antes de construir redis-py y testear precedencia |
| Redis corrupto sirve una forma invalida | Alto | Validar JSON con schemas Pydantic y caer a PostgreSQL |
| Invalidacion compite con repoblado | Alto | Cambiar generacion, no borrar claves por patron |
| PostgreSQL confirma y Redis falla | Medio | Error post-commit explicito y reintento idempotente soportado |
| Fallo Redis se oculta demasiado | Medio | Capturar solo excepciones operativas conocidas y emitir warning estructurado |
| Cardinalidad alta de filtros | Medio | Hash canonico, TTL obligatorio y limites HTTP existentes |
| Cache cambia semantica de `/random` | Medio | Excluir el endpoint y probar acceso directo al repository |
| Complejidad accidental en wiring | Bajo | Un protocolo pequeno y un adaptador especifico de items |

## Parallelization

No se paralelizara implementacion sobre los mismos modulos. El boundary Redis
precede al adaptador; el read path y la invalidacion comparten el contrato del
adaptador y se ejecutan secuencialmente para mantener diffs revisables.

## Open Questions

Ninguna. El spec fue aprobado y las decisiones de invalidacion y alcance estan
cerradas.
