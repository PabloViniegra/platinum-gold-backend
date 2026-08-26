import pytest


@pytest.fixture(autouse=True)
def clear_postgres_driver_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for variable in (
        "PGHOST",
        "PGPORT",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGUSER",
        "PGPASSWORD",
        "PGPASSFILE",
        "PGDATABASE",
        "PGSSLMODE",
        "PGSSLROOTCERT",
        "PGSSLCERT",
        "PGSSLKEY",
        "PGSSLCRL",
        "PGSSLPASSWORD",
        "PGSSLNEGOTIATION",
        "PGSSLMINPROTOCOLVERSION",
        "PGSSLMAXPROTOCOLVERSION",
        "PGTARGETSESSIONATTRS",
        "PGKRBSRVNAME",
        "PGGSSLIB",
        "SSLKEYLOGFILE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    ):
        monkeypatch.delenv(variable, raising=False)
