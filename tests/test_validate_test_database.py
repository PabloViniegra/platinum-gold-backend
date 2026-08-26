import pytest

from scripts.validate_test_database import validate_test_database_url


def test_validate_test_database_url_accepts_local_test_database() -> None:
    url = "postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api_test"

    assert validate_test_database_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://postgres:postgres@database.example:5432/isaac_api_test",
        "postgresql+asyncpg://postgres:postgres@localhost:5433/isaac_api_test",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api_test?host=remote.example",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/isaac_api_test#fragment",
    ],
)
def test_validate_test_database_url_rejects_unsafe_database(url: str) -> None:
    with pytest.raises(ValueError):
        validate_test_database_url(url)
