# Implementation Plan: Ingesta inicial offline del catalogo de items

## Overview

Implementar el contrato aprobado en `tasks/spec-initial-ingestion.md` como un
flujo vertical: cargar y validar un snapshot JSON, publicarlo de forma atomica
en PostgreSQL mediante upsert por `game_id`, registrar el estado actual del
dataset y reflejarlo en `/v1/meta`. La API seguira sin scraping, lectura de
ficheros ni ejecucion de ingesta.

El plan usa documentos especificos de la feature (`plan-initial-ingestion.md` y
`todo-initial-ingestion.md`) porque `tasks/plan.md` y `tasks/todo.md` son los
artefactos historicos de la base ejecutable y se mantienen como referencia de
las fases ya completadas.

## Baseline and Constraints

- La rama parte de `main` en `4373b4d`, con el worktree limpio salvo el spec
  aprobado y `CONTEXT.md` de esta feature.
- `items.game_id` ya tiene una restriccion unica y el modelo permite los campos
  definidos por el snapshot.
- `ItemService.get_meta` actualmente devuelve metadata nula; la implementacion
  sustituira ese fallback por una lectura opcional sin romper el estado previo a
  la primera ingesta.
- Alembic es la unica autoridad de esquema. No se usara `create_all()`.
- No se agregaran dependencias ni se conectara ningun servicio externo.

## Architecture Decisions

- El limite de entrada sera un loader JSON pequeno y un schema Pydantic estricto.
  El loader devuelve un snapshot validado; no mezcla lectura de ficheros con
  SQL.
- `DatasetMetadata` sera una tabla singleton con clave fija, version de dataset,
  version de juego nullable y `last_sync` UTC. No se modelara historial de
  ejecuciones.
- Un `IngestionService` abrira una unica transaccion mediante la factoría de
  sesiones, ejecutara los upserts de items y actualizara metadata en ese mismo
  contexto. Cualquier excepcion aborta el lote.
- La escritura usara el dialecto PostgreSQL `INSERT ... ON CONFLICT (game_id)`.
  Se conservaran la PK interna y `created_at`; los campos del snapshot y
  `updated_at` se actualizaran en conflictos.
- La lectura de metadata se anadira al repository de items existente para que
  `/v1/meta` conserve su dependencia y su manejo de errores. No se creara un
  repository generico.
- El CLI sera un modulo `scripts.ingest` invocable con `python -m`, cargara y
  validara antes de crear la transaccion y convertira fallos operativos en un
  codigo de salida no cero sin imprimir secretos.
- El snapshot de ejemplo sera pequeno, explicito y no sensible. No se
  versionara un dataset real si no existe una decision separada sobre su
  licencia y mantenimiento.

## Dependency Graph

```text
Snapshot JSON contract + loader
             |
             v
Validated ItemSnapshot
             |
             +---------------------+
             |                     |
             v                     v
DatasetMetadata model/migration   PostgreSQL item upsert
             |                     |
             +----------+----------+
                        v
              Transactional ingestion service
                        |
              +---------+----------+
              |                    |
              v                    v
       scripts.ingest        /v1/meta read
              |                    |
              +---------+----------+
                        v
             Integration and quality gates
```

The migration and PostgreSQL-specific upsert are sequential. Snapshot
validation and unit tests can be developed independently before the database
work; documentation can be updated after the public contract is wired.

## Implementation Order

### Phase 1: Input Boundary

1. Implement the strict Pydantic snapshot/item contract and JSON loader with
   unit tests for malformed input, unknown fields, empty strings, invalid URLs,
   out-of-range quality and duplicate `gameId`.

**Checkpoint: Input**

- Invalid snapshots fail without opening a database transaction.
- A valid fixture produces one normalized Python snapshot.
- Focused validation tests and Pyright pass.

### Phase 2: Persistence Foundation

2. Add the `DatasetMetadata` domain model and reversible Alembic migration for
   the singleton table; register the model with the migration metadata without
   changing runtime startup behavior.
3. Add the PostgreSQL ingestion repository for batch item upsert and metadata
   upsert, including preservation of internal identity and update timestamps.

**Checkpoint: Persistence**

- The migration applies and downgrades against the local `_test` database.
- An integration fixture can insert, update and repeat a snapshot without
  duplicate `game_id` values.
- The repository never commits per item and exposes no credential data.

### Phase 3: Transactional Use Case and Public Metadata

4. Implement the ingestion service transaction boundary and its failure tests,
   proving that a repository/metadata failure rolls back the entire batch.
5. Add `scripts.ingest` as the offline command, including explicit input path,
   sanitized operational errors and deterministic non-zero exit behavior.
6. Wire optional dataset metadata into `ItemRepository` and `/v1/meta`, keeping
   all three dataset fields null before the first successful ingestion and
   adding `datasetVersion` after one.

**Checkpoint: End-to-End Slice**

- The CLI loads the example snapshot and publishes it through the service.
- Re-running it is safe and updates the metadata timestamp only after commit.
- `/v1/meta` reports the committed dataset while `/health` remains unchanged.

### Phase 4: Verification and Documentation

7. Complete opt-in PostgreSQL integration coverage for atomicity, metadata,
   rollback and repeatability; update README and task artifacts with the
   supported command and boundaries.
8. Run all repository quality gates and perform the mandatory code and security
   review before considering the slice ready to ship.

**Checkpoint: Complete**

- Base and opt-in integration suites pass.
- Ruff, format and Pyright pass.
- No API runtime import or lifespan path performs ingestion I/O.
- The diff contains no secrets and matches the approved spec.

## Verification Strategy

Each behavior follows RED, GREEN, REFACTOR:

1. Add the smallest failing unit or integration test for the contract.
2. Implement only the code required to make that test pass.
3. Run the focused test and Pyright for the touched module.
4. Refactor only when it reduces complexity, then rerun the focused checks.
5. Run the phase checkpoint before moving to the next dependency layer.

Commands used during implementation and final verification:

```bash
uv run pytest tests/test_ingestion.py
uv run pytest tests/test_ingestion_service.py
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api_test make integration
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Pydantic coerces source types unexpectedly | Alto | Use strict field types and tests for stringified numbers/booleans |
| Upsert behavior differs from the read model | Alto | Test the real PostgreSQL dialect against the local integration database |
| Metadata is marked before item writes commit | Alto | Keep both operations inside one `session.begin()` and test rollback |
| Missing records are accidentally deleted | Alto | Implement only `ON CONFLICT DO UPDATE`; add no delete path |
| API meta changes break existing fakes | Medio | Extend the repository contract and update HTTP tests in the same increment |
| CLI leaks database details on failure | Medio | Catch operational errors at the boundary and emit sanitized messages |
| Example data becomes a hidden production source | Bajo | Require `--input` and keep the example clearly non-authoritative |

## Parallelization

- Safe in parallel: input schema/loader tests and glossary/documentation review.
- Sequential: metadata migration before repository integration; repository before
  service/CLI; public metadata wiring after its repository contract is stable.
- Review can run in parallel with the final quality-gate pass once the diff is
  complete, but findings must be merged before shipping.

## Open Questions

None. The source, update policy, failure behavior and `/v1/meta` extension are
approved in `tasks/spec-initial-ingestion.md`.
