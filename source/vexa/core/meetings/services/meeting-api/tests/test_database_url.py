from meeting_api import __main__ as meeting_main


def test_database_url_quotes_reserved_database_components(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "vexa/name")
    monkeypatch.setenv("DB_USER", "operator@example.com")
    monkeypatch.setenv("DB_PASSWORD", "p@ss:/?#word")

    assert meeting_main._database_url() == (
        "postgresql+asyncpg://operator%40example.com:"
        "p%40ss%3A%2F%3F%23word@postgres:5432/vexa%2Fname"
    )
