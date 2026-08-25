import ssl

from app.core.config import Settings
from app.core.database import database_connect_args


def test_remote_production_database_uses_verified_tls() -> None:
    settings = Settings.model_validate(
        {
            "environment": "production",
            "database_url": (
                "postgresql+asyncpg://user:password@database.example/isaac_api"
            ),
            "redis_url": "rediss://cache.example/0",
        }
    )

    context = database_connect_args(settings)["ssl"]

    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
