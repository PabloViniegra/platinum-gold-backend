from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import cast

from fastapi import FastAPI

from app.core.config import Settings
from app.core.database import create_database
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.redis import create_redis
from app.health.router import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        settings_factory = cast(Callable[[], Settings], Settings)
        runtime_settings = settings or settings_factory()
        configure_logging(runtime_settings.log_level)
        async with AsyncExitStack() as stack:
            database_engine, session_factory = create_database(runtime_settings)
            stack.push_async_callback(database_engine.dispose)
            redis = create_redis(runtime_settings)
            stack.push_async_callback(redis.aclose)
            app.state.settings = runtime_settings
            app.state.database_engine = database_engine
            app.state.session_factory = session_factory
            app.state.redis = redis
            yield

    app = FastAPI(
        title=settings.app_name if settings else "The Binding of Isaac API",
        version=settings.app_version if settings else "0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    return app


app = create_app()
