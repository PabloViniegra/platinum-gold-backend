# Spec: Hardening Redis y cache-aside de items

## Approved Decisions

1. El orden de trabajo es hardening de Redis, cache-aside e invalidacion tras
   ingesta. Rate limiting se especificara e implementara en una slice posterior.
2. Redis es una capa derivada y prescindible para las lecturas: un fallo de
   cache cae a PostgreSQL y no altera el contrato HTTP existente.
3. La ingesta offline usara tambien `REDIS_URL` e invalidara la cache solo
   despues de confirmar la transaccion PostgreSQL.
4. La invalidacion cambiara una generacion compartida de cache. Las claves de
   datos incluiran esa generacion, por lo que no se necesita recorrer ni borrar
   el keyspace y las escrituras concurrentes de la generacion anterior quedan
   inaccesibles.
5. No se cacheara `/v1/items/random`, respuestas de error ni resultados 404.
   Negative caching, warming y proteccion de stampede quedan fuera del MVP.

## Objective

Reducir las consultas PostgreSQL repetidas de los endpoints deterministas de
items sin convertir Redis en fuente de verdad ni en un requisito de
disponibilidad para las lecturas. A la vez, cerrar la superficie de
configuracion de `REDIS_URL` para impedir que query parameters o URLs ambiguas
anulen silenciosamente los timeouts y controles TLS establecidos por la
aplicacion.

La slice cubre `GET /v1/items`, `GET /v1/items/{item_id}` y `GET /v1/meta`.
Las respuestas, errores, autenticacion y OpenAPI conservan su contrato actual.

## Redis Connection Contract

- `REDIS_URL` admite unicamente `redis://` y `rediss://` con hostname explicito.
- Se rechazan fragments, query parameters, espacios, caracteres de control,
  multiples destinos, puertos fuera de `1..65535`, credenciales vacias y paths
  distintos de una base numerica entre `0` y `15`.
- Produccion exige `rediss://` para cualquier host no loopback y password para
  Redis remoto. Desarrollo y test pueden usar `redis://` en loopback.
- Los query parameters se rechazan porque redis-py les da precedencia sobre los
  kwargs de `from_url`; no pueden redefinir timeouts, TLS, decoding, retries ni
  limites del pool.
- `rediss://` usa verificacion de certificado y hostname de forma explicita.
- El cliente conserva timeouts de conexion y socket acotados por
  `dependency_timeout_seconds`, respuestas decodificadas y un pool acotado.
- No se registran URLs, usernames, passwords ni valores de cache.

redis-py 8.1.0 es la version fijada en `uv.lock`. Su documentacion define
`rediss://` como una conexion TCP envuelta en TLS y documenta que los query
parameters prevalecen ante kwargs en conflicto:

- https://github.com/redis/redis-py/blob/master/docs/connections.md
- https://github.com/redis/redis-py/blob/master/redis/connection.py

## Cache Contract

Se usara cache-aside con claves versionadas y deterministas:

```text
cache:items:generation
cache:v1:{generation}:item:{game_id}
cache:v1:{generation}:list:{sha256_of_canonical_params}
cache:v1:{generation}:meta:{api_version}
```

- La generacion ausente equivale a `0`.
- Los parametros de listado se serializan con nombres y valores normalizados,
  orden estable y sin incluir API keys. El hash evita almacenar busquedas del
  usuario en el nombre de la clave.
- Los payloads se serializan como el JSON camelCase del schema publico y se
  validan de nuevo al leerlos. Un payload ausente, invalido o incompatible se
  trata como miss; nunca se devuelve sin validacion.
- TTL inicial: item individual y metadata, `86400` segundos; listados,
  `900` segundos. Son configuracion tipada con limites positivos, no query
  parameters de `REDIS_URL`.
- Un hit evita toda consulta PostgreSQL para ese recurso.
- Un miss consulta PostgreSQL, construye la respuesta normal y luego intenta
  escribirla con expiracion mediante un unico `SET ... EX`.
- Fallos esperables de conexion, timeout, limite del pool o comando Redis
  generan un warning estructurado sin secretos y continuan por PostgreSQL. Los
  errores de programacion y cancelaciones no se ocultan.
- Un fallo al escribir cache despues de una lectura PostgreSQL correcta no
  cambia la respuesta HTTP.
- `/v1/items/random` siempre consulta PostgreSQL para preservar su semantica.

La operacion `SET` con `ex` sigue el contrato oficial de redis-py:
https://github.com/redis/redis-py/blob/master/docs/commands.md

## Invalidation Contract

Tras una ingesta exitosa y despues de salir del contexto transaccional, el CLI
incrementa atomicamente `cache:items:generation` en Redis.

- Nunca se invalida antes del commit PostgreSQL.
- Un fallo PostgreSQL no toca la generacion.
- Una ejecucion valida que resulta no-op puede incrementar la generacion; es
  seguro y mantiene simple el contrato de orquestacion.
- Si PostgreSQL confirma pero Redis no puede incrementar la generacion, el CLI
  termina con codigo no cero y un mensaje sanitizado que indica que los datos
  fueron publicados pero la invalidacion fallo. Repetir la ingesta es la via de
  recuperacion soportada y vuelve a intentar la invalidacion.
- Las generaciones antiguas no se borran sincronicamente. Sus claves expiran
  por TTL y no son alcanzables por nuevas lecturas.
- El cliente Redis se cierra incluso cuando persistencia o invalidacion fallan.

## API Contract

No cambian cuerpos ni status codes exitosos. Los endpoints protegidos mantienen
sus respuestas `401`, `403`, `404`, `422` y `503` existentes.

No se exponen headers de cache en esta slice. El estado hit/miss se registra
como evento estructurado interno sin incluir payloads, filtros en claro ni
credenciales.

## Threat Model

Trust boundaries:

- `REDIS_URL` entra desde configuracion externa y puede contener opciones que
  cambien seguridad, routing o consumo de recursos.
- Redis es un servicio externo y sus valores pueden estar corruptos, obsoletos
  o manipulados.
- Los query parameters HTTP participan en claves de cache y pueden intentar
  aumentar cardinalidad o filtrar datos sensibles a logs/keyspace.
- La ingesta cruza dos sistemas sin una transaccion distribuida: PostgreSQL es
  autoritativo y Redis solo recibe la invalidacion post-commit.

Controles:

- Validacion fail-closed de URL, TLS remoto verificado, timeouts y pool acotado.
- Hash determinista de filtros ya validados y TTL en todas las claves de datos.
- Revalidacion Pydantic de payloads y fallback a PostgreSQL.
- Errores sanitizados y eventos sin secretos.
- Generaciones para evitar races entre invalidacion y repoblado concurrente.

## Tech Stack

Sin dependencias nuevas.

- Python `>=3.13`.
- FastAPI 0.141.1 y Pydantic Settings 2.15.0.
- redis-py 8.1.0 con API `asyncio`.
- SQLAlchemy 2 asincrono y PostgreSQL como fuente de verdad.
- pytest, pytest-asyncio, Ruff y Pyright con los gates actuales.

## Commands

```bash
uv run pytest tests/test_config.py tests/test_redis.py
uv run pytest tests/test_cache.py tests/test_items_api.py
uv run pytest tests/test_ingestion_service.py tests/test_ingest_cli.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
git diff --check
```

La suite normal usara fakes y no necesitara Redis real. Una verificacion de
integracion Redis sera opt-in si aporta cobertura que no pueda demostrarse con
tests unitarios.

## Project Structure

```text
app/
|-- core/
|   |-- config.py           # Contrato estricto de REDIS_URL y TTLs
|   `-- redis.py            # Construccion segura del cliente
|-- items/
|   |-- cache.py            # Cache Redis tipada y generacional
|   |-- dependencies.py     # Wiring de repository y cache
|   `-- service.py          # Orquestacion cache-aside
|-- ingestion/
|   `-- service.py          # Persistencia; no invalida antes del commit
`-- main.py                 # Un unico cliente Redis por lifespan
scripts/
`-- ingest.py               # Cierre de recursos e invalidacion post-commit
tests/
|-- test_config.py
|-- test_redis.py
|-- test_cache.py
|-- test_items_api.py
|-- test_ingestion_service.py
`-- test_ingest_cli.py
tasks/spec-redis-cache.md
tasks/plan-redis-cache.md
tasks/todo-redis-cache.md
```

No se creara una capa generica de cache. El modulo de items define el contrato
minimo que consume `ItemService`; Redis queda contenido en su adaptador.

## Code Style

Los limites se expresan con Protocols pequenos y schemas existentes:

```python
class ItemCache(Protocol):
    async def get_item(self, game_id: int) -> ItemResponse | None: ...

    async def set_item(self, item: ItemResponse) -> None: ...
```

Convenciones:

- Imports absolutos desde `app` y `scripts`.
- Nombres Python en snake_case y JSON publico en camelCase.
- Sin `Any` salvo limites externos inevitables.
- Sin capturas de `Exception` para el flujo fail-open de cache.
- Sin abstracciones para proveedores de cache que no existen.
- La politica de cache vive fuera del repository PostgreSQL.

## Testing Strategy

- Tests de configuracion cubren URLs validas, TLS remoto, credenciales,
  fragments, query overrides, paths, puertos y errores sin secretos.
- Tests de construccion verifican kwargs de TLS, timeout, decoding y pool sin
  abrir conexiones reales.
- Tests del adaptador cubren claves deterministas, TTLs, serializacion,
  payload corrupto, generacion e invalidacion.
- Tests de servicio/API demuestran hit sin repository, miss con escritura,
  fallback ante cada fallo Redis esperado y ausencia de cache en `/random`.
- Tests de ingesta demuestran el orden commit-then-invalidate, ausencia de
  invalidacion en rollback, cierre de recursos y mensaje post-commit correcto.
- Todo comportamiento nuevo sigue RED, GREEN, REFACTOR.

## Boundaries

### Always

- Mantener PostgreSQL como fuente de verdad.
- Validar configuracion y payloads en sus limites.
- Aplicar TTL a toda clave de datos.
- Invalidar solo despues de commit.
- Hacer fail-open exclusivamente para fallos Redis esperables en lecturas.
- Ejecutar pytest, Ruff, formato y Pyright antes de completar la slice.

### Ask First

- Cambiar TTLs o la politica fail-open.
- Cachear 404, `/random`, autenticacion o respuestas de error.
- Añadir warming, locks, stale-while-revalidate o una dependencia nueva.
- Exponer headers o campos publicos de cache.
- Desplegar, migrar datos o modificar recursos Vercel/Upstash.

### Never

- Aceptar query parameters en `REDIS_URL`.
- Desactivar verificacion TLS o de hostname para Redis remoto.
- Devolver payloads Redis sin validarlos.
- Registrar URLs Redis, credenciales, API keys o valores cacheados.
- Invalidar antes de confirmar PostgreSQL.
- Convertir un miss con PostgreSQL caido en una coleccion vacia o un 404.

## Success Criteria

- Configuraciones Redis ambiguas o capaces de sobrescribir controles se
  rechazan sin exponer secretos.
- Una conexion remota de produccion solo se acepta con `rediss://`, password y
  verificacion TLS/hostname.
- La segunda lectura identica de item, listado o metadata se sirve desde Redis
  sin invocar el repository PostgreSQL.
- Claves de listados equivalentes son identicas y no contienen filtros en claro.
- Redis caido, lento, saturado o con payload corrupto no rompe una lectura que
  PostgreSQL puede resolver.
- `/v1/items/random`, autenticacion y contratos HTTP permanecen sin cambios.
- Una ingesta confirmada cambia la generacion despues del commit; un rollback
  no la cambia.
- Un fallo de invalidacion post-commit es observable, sanitizado y recuperable
  repitiendo la ingesta.
- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pyright` y `git diff --check` terminan correctamente.

## Open Questions

Ninguna. La ampliacion de la ingesta con Redis y la invalidacion post-commit
fueron aprobadas antes de escribir este documento.
