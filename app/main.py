from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.auth.clerk import bind_api_key_verifier
from app.core.config import Settings
from app.core.database import create_database
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.redis import create_redis
from app.health.router import router as health_router
from app.items.router import meta_router
from app.items.router import router as items_router


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        settings_factory = cast(Callable[[], Settings], Settings)
        runtime_settings = settings or settings_factory()
        app.version = runtime_settings.app_version
        configure_logging(runtime_settings.log_level)
        async with AsyncExitStack() as stack:
            database_engine, session_factory = create_database(runtime_settings)
            stack.push_async_callback(database_engine.dispose)
            redis = create_redis(runtime_settings)
            stack.push_async_callback(redis.aclose)
            secret = (
                runtime_settings.clerk_secret_key.get_secret_value()
                if runtime_settings.clerk_secret_key is not None
                else None
            )
            timeout_ms = int(runtime_settings.dependency_timeout_seconds * 1000)
            app.state.settings = runtime_settings
            app.state.database_engine = database_engine
            app.state.session_factory = session_factory
            app.state.redis = redis
            app.state.api_key_verifier = await bind_api_key_verifier(
                stack,
                secret,
                timeout_ms,
            )
            yield

    app = FastAPI(
        title=settings.app_name if settings else "The Binding of Isaac API",
        version=settings.app_version if settings else "0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(items_router)
    app.include_router(meta_router)

    def openapi() -> dict[str, object]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        schemes = components.setdefault("securitySchemes", {})
        schemes["X-API-Key"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app


app = create_app()
