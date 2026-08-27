from urllib.parse import urlsplit

from redis.asyncio import Redis
from redis.asyncio.utils import from_url

from app.core.config import Settings


def create_redis(settings: Settings) -> Redis:
    redis_url = settings.redis_url.get_secret_value()
    options: dict[str, object] = {
        "decode_responses": True,
        "socket_connect_timeout": settings.dependency_timeout_seconds,
        "socket_timeout": settings.dependency_timeout_seconds,
        "max_connections": settings.redis_max_connections,
    }
    if urlsplit(redis_url).scheme == "rediss":
        options.update(ssl_cert_reqs="required", ssl_check_hostname=True)
    return from_url(redis_url, **options)
