from redis.asyncio import Redis
from redis.asyncio.utils import from_url

from app.core.config import Settings


def create_redis(settings: Settings) -> Redis:
    return from_url(
        settings.redis_url.get_secret_value(),
        decode_responses=True,
        socket_connect_timeout=settings.dependency_timeout_seconds,
        socket_timeout=settings.dependency_timeout_seconds,
    )
