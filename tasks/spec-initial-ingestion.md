# Spec: Ingesta inicial offline del catalogo de items

## Approved Decisions

1. Platinum God es la fuente upstream autorizada, pero esta slice no hace
   scraping ni llamadas de red. Un proceso externo produce un snapshot JSON
   canonico y versionado; ese fichero es la unica entrada de ejecucion.
2. La primera politica de actualizacion es upsert-only por `gameId`: una fila
   ausente del snapshot no se borra ni se desactiva. La reconciliacion de
   eliminaciones necesita una politica de ciclo de vida que no existe todavia.
3. La metadata de la ultima ingesta exitosa se guarda en una tabla singleton y
   `/v1/meta` expone tambien `datasetVersion`. Antes de la primera ingesta los
   campos de dataset siguen siendo `null`.
4. Una ingesta recibe un snapshot completo de los registros que quiere
   publicar y debe ser no vacio. Los duplicados de `gameId` son un error de
   entrada, no un caso de merge.

## Objective

Proporcionar un flujo administrativo offline para cargar items desde un
snapshot JSON validado, de forma repetible y segura. El objetivo es que un
operador pueda ejecutar la misma ingesta mas de una vez sin duplicar items,
actualizar registros existentes por `gameId` y dejar `/v1/meta` describiendo la
ultima ejecucion exitosa.

El flujo no pertenece al runtime HTTP: la API nunca contacta Platinum God ni
lee snapshots automaticamente. El operador debe proporcionar explicitamente
la ruta del snapshot y una configuracion PostgreSQL valida.

## Input Contract

La entrada es un objeto JSON UTF-8 con campos desconocidos rechazados:

```json
{
  "datasetVersion": "platinum-god-2026-08-26",
  "gameVersion": "repentance",
  "items": [
    {
      "gameId": 118,
      "name": "Brimstone",
      "description": "Tears are replaced by a laser beam.",
      "quality": 4,
      "type": "passive",
      "rechargeTime": null,
      "imageUrl": "https://example.com/118.png",
      "introducedInVersion": "rebirth"
    }
  ]
}
```

Reglas de validacion:

- `datasetVersion` es obligatorio, no vacio y representa la version del
  snapshot upstream; no se genera silenciosamente a partir del reloj local.
- `gameVersion` es opcional y, cuando existe, no puede estar vacio.
- `items` es obligatorio, es una lista no vacia y no contiene `gameId`
  repetidos.
- `gameId` es un entero positivo representable por la columna PostgreSQL
  `INTEGER` (`1` a `2147483647`).
- `name`, `description` e `imageUrl` son strings no vacios despues de quitar
  espacios exteriores. `imageUrl` debe usar `http` o `https`.
- `quality` es obligatorio y puede ser `null` o un entero entre `0` y `4`.
- `type`, `rechargeTime` e `introducedInVersion` son opcionales; si se
  proporcionan, son strings no vacios.
- Se rechazan JSON invalido, campos desconocidos, tipos incompatibles y
  cualquier registro que no cumpla todas las reglas antes de abrir la
  transaccion de persistencia.

Los nombres del snapshot usan camelCase para que el contrato sea independiente
del modelo SQLAlchemy y coincida con el JSON publico. El adaptador futuro que
extraiga datos de Platinum God sera responsable de producir este formato; no
forma parte de esta slice.

## Update and Persistence Policy

- Cada `gameId` se inserta o actualiza mediante una unica operacion transaccional
  de PostgreSQL con conflicto en la restriccion unica de `items.game_id`.
- En un conflicto se actualizan los campos del snapshot (`name`, `description`,
  `quality`, `item_type`, `recharge_time`, `image_url` e
  `introduced_in_version`); no se cambia la PK interna ni `created_at`.
- La ejecucion conserva los registros que no aparecen en el snapshot. No hay
  borrado fisico, soft delete ni reconciliacion de ausencias en esta primera
  slice.
- Tras aplicar todos los upserts, la misma transaccion crea o actualiza una
  fila singleton de metadata con `dataset_version`, `game_version` y
  `last_sync` UTC, sin retroceder si dos ejecuciones concurrentes llegan con
  relojes desordenados. `last_sync` se escribe solo cuando toda la operacion
  puede confirmarse.
- Si el reloj de una ejecucion no produce un `last_sync` posterior al ya
  registrado, la ejecucion es un no-op exitoso: no modifica items ni metadata y
  devuelve el `last_sync` existente. Esto evita que una ejecucion obsoleta
  reemplace una publicacion ya confirmada.
- `datasetVersion` es una etiqueta opaca y no se usa para inferir orden entre
  snapshots. La seleccion de la revision upstream correcta ocurre antes de
  ejecutar este comando; la proteccion de esta slice solo ordena ejecuciones
  por su timestamp UTC.
- Repetir el mismo snapshot es idempotente respecto al conjunto y contenido
  de items: no crea duplicados y deja la misma metadata de dataset. El cambio
  de `last_sync` identifica la nueva ejecucion exitosa.

La nueva tabla de metadata tendra una clave singleton, version de dataset,
version de juego y timestamp de ultima sincronizacion. No se crea historial de
ejecuciones (`scrape_runs`) en esta slice.

## Failure Behavior

- Error al abrir o decodificar el fichero, una ruta que no sea un fichero regular
  o un snapshot que supere 5 MiB: el comando termina con codigo distinto de cero
  y no toca PostgreSQL.
- Error de validacion: el comando termina con codigo distinto de cero,
  muestra rutas de campos invalidos sin secretos y no toca PostgreSQL.
- Error en cualquier upsert o en la metadata: se revierte la transaccion
  completa, no queda un catalogo parcial, no se actualiza `last_sync` y el
  comando termina con codigo distinto de cero.
- Una ausencia de PostgreSQL no se convierte en una ingesta parcial ni en una
  ejecucion exitosa; se informa como fallo operativo sin mostrar la URL de
  conexion o credenciales.
- Ninguna ruta HTTP dispara el flujo ni intenta recuperar el snapshot.

## API Contract Change

`GET /v1/meta` conserva sus campos actuales y añade `datasetVersion`:

```json
{
  "apiVersion": "0.1.0",
  "datasetVersion": "platinum-god-2026-08-26",
  "gameVersion": "repentance",
  "lastSync": "2026-08-26T10:30:00Z",
  "items": 1
}
```

Cuando no existe una ingesta exitosa, `datasetVersion`, `gameVersion` y
`lastSync` son `null`, como en el contrato actual. `items` sigue siendo el
recuento real de PostgreSQL.

## Tech Stack

Sin dependencias nuevas.

- Python `>=3.13`, `uv` y `argparse` para el comando administrativo.
- Pydantic 2 para el contrato y validacion del snapshot.
- SQLAlchemy 2 asincrono y PostgreSQL para upsert y metadata.
- Alembic para la tabla de metadata.
- pytest, pytest-asyncio, HTTPX, Ruff y Pyright con los quality gates actuales.

## Commands

```bash
uv run python -m scripts.ingest --input data/items.json
uv run pytest tests/test_ingestion.py tests/test_items_api.py
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api_test make integration
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

El comando exige una ruta de entrada explicita y usa `DATABASE_URL` para la
conexion. No tiene una opcion que permita apuntar por accidente a una URL
remota desde la ruta de integracion local; la proteccion existente de
`TEST_DATABASE_URL` se mantiene. La configuracion de ingesta requiere un nombre
de base y credenciales explicitos para destinos remotos, rechaza overrides de
`PGHOST`, `PGPORT`, `PGSERVICE`, `PGUSER` y credenciales ambientales, y solo
permite opciones asyncpg no relacionadas con el destino.

## Project Structure

```text
app/
|-- ingestion/
|   |-- __init__.py
|   |-- schemas.py          # Contrato y validacion del snapshot
|   |-- loader.py           # Lectura offline y errores de fichero/JSON
|   |-- repository.py       # Upserts PostgreSQL de items y metadata
|   `-- service.py          # Orquestacion transaccional de la ingesta
|-- items/
|   |-- models.py           # Item existente
|   `-- repository.py        # Lectura de items y metadata para la API
|-- meta/
|   |-- __init__.py
|   `-- models.py           # Metadata singleton del dataset
scripts/
|-- __init__.py
`-- ingest.py               # CLI offline, sin scraping
alembic/versions/*_create_dataset_metadata.py
data/items.example.json     # Snapshot pequeno y no sensible para desarrollo
tests/
|-- test_ingestion.py       # JSON y validacion del snapshot
|-- test_ingestion_service.py # Orquestacion y rollback de la transaccion
|-- test_items_api.py       # Meta con y sin metadata
`-- integration/test_ingestion_postgres.py
tasks/spec-initial-ingestion.md
tasks/plan-initial-ingestion.md
tasks/todo-initial-ingestion.md
```

Si la implementacion demuestra que un modulo independiente solo envuelve una
operacion de items sin aportar una frontera util, se conservara la estructura
feature-oriented existente y no se añadiran capas genericas.

## Code Style

Los schemas de entrada permanecen separados de los modelos SQLAlchemy. La
validacion se expresa en el tipo y el servicio recibe un snapshot ya validado:

```python
from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ItemImport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    game_id: StrictInt = Field(gt=0, alias="gameId")
    name: str
    description: str
    image_url: str = Field(alias="imageUrl")
```

Convenciones:

- Imports absolutos desde `app` y `scripts`.
- Alias camelCase solo en el limite JSON; nombres Python en snake_case.
- El CLI coordina argumentos, lectura y salida; no contiene SQL de dominio.
- El servicio no importa FastAPI ni imprime secretos.
- La sesion se abre para la operacion y se confirma una sola vez.
- Sin `Any` salvo limites externos justificados y sin abstracciones genericas.

## Testing Strategy

- Tests unitarios verifican parseo, campos obligatorios, tipos estrictos,
  strings vacios, URL invalida, calidad fuera de rango y `gameId` duplicado.
- Tests de servicio con una dependencia de persistencia sustituible verifican
  que la validacion ocurre antes de persistir y que metadata solo se publica
  tras completar el lote.
- Tests de integracion opt-in contra PostgreSQL real verifican insercion,
  actualizacion por `game_id`, ausencia de duplicados, repeticion del snapshot,
  actualizacion de metadata y rollback del lote ante un fallo de persistencia.
- Tests HTTP verifican que `/v1/meta` conserva los nulos antes de la primera
  ingesta y expone la metadata despues de una metadata disponible.
- La suite normal no arranca Docker, no llama Platinum God y no necesita una
  URL PostgreSQL real. Los tests de integracion siguen usando una base local
  cuyo nombre termina en `_test` y aislamiento transaccional.
- Todo comportamiento nuevo sigue RED, GREEN, REFACTOR.

## Boundaries

### Always

- Tratar el snapshot JSON validado como unica entrada de ejecucion.
- Validar el lote completo antes de cualquier escritura.
- Ejecutar upserts y metadata en una sola transaccion.
- Mantener `game_id` como clave de negocio y preservar la PK interna al
  actualizar.
- Mantener la API libre de scraping, lectura de ficheros y tareas de ingesta.
- Usar Alembic para la tabla de metadata y conservar los tests de integracion
  opt-in.
- Ejecutar pytest, Ruff y Pyright antes de considerar completa la slice.

### Ask first

- Cambiar upsert-only por reconciliacion con borrado o soft delete.
- Añadir scraping, scheduler, endpoint HTTP o dependencia externa.
- Añadir historial de ejecuciones, estados de items o tablas relacionales de
  pools, tags o versiones de juego.
- Cambiar el contrato JSON, los nombres de `/v1/meta` o la politica de errores.
- Permitir snapshots vacios o conversion coercitiva de tipos.

### Never

- Contactar Platinum God desde el runtime de FastAPI.
- Hacer `commit` por registro o dejar una ingesta parcialmente aplicada.
- Ejecutar `Base.metadata.create_all()`.
- Registrar `DATABASE_URL`, credenciales, API keys o el contenido completo del
  snapshot en logs.
- Usar una base remota o no terminada en `_test` para la suite de integracion.
- Ocultar un fallo de ingesta marcando metadata como sincronizada.

## Success Criteria

- Un snapshot valido puede cargarse con un comando offline y termina con codigo
  cero.
- Un segundo procesamiento del mismo snapshot no duplica items ni cambia sus
  valores de negocio.
- Un `gameId` existente se actualiza por conflicto sin cambiar su PK interna o
  `created_at`.
- Un snapshot invalido no modifica ninguna fila de `items` ni metadata.
- Un fallo de base de datos revierte todos los upserts y no actualiza
  `last_sync`.
- `/v1/meta` devuelve `datasetVersion`, `gameVersion` y `lastSync` despues de
  una ingesta exitosa y mantiene los tres en `null` antes de ella.
- La API no hace I/O de ingesta al importar o atender peticiones.
- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` y
  `uv run pyright` terminan correctamente; la integracion opt-in tambien pasa.

## Open Questions

Ninguna. El snapshot JSON local, la politica upsert-only sin borrados y la
ampliacion de `/v1/meta` con `datasetVersion` fueron aprobados antes del plan.
