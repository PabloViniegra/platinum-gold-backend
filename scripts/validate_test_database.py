import os
from urllib.parse import urlsplit

ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}
VALIDATION_ERROR = (
    "TEST_DATABASE_URL must use a local PostgreSQL database on port 5432 "
    "ending in _test without query parameters"
)


def validate_test_database_url(url: str | None) -> str | None:
    if url is None:
        return None
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(VALIDATION_ERROR) from exc
    database_name = parsed.path.removeprefix("/")
    if (
        parsed.scheme != "postgresql+asyncpg"
        or parsed.hostname not in ALLOWED_HOSTS
        or port not in {None, 5432}
        or not database_name.endswith("_test")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(VALIDATION_ERROR)
    return url


def main() -> None:
    try:
        validate_test_database_url(os.getenv("TEST_DATABASE_URL"))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
