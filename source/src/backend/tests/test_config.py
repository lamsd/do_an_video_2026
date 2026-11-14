from app.config import Settings


def test_database_url_quotes_reserved_postgres_components():
    settings = Settings(
        vexa_api_base="http://vexa.test",
        postgres_db="meeting/data",
        postgres_user="operator@example.com",
        postgres_password="p@ss:/?#word",
    )

    assert settings.database_url == (
        "postgresql+asyncpg://operator%40example.com:"
        "p%40ss%3A%2F%3F%23word@postgres:5432/meeting%2Fdata"
    )


def test_explicit_database_url_is_preserved():
    explicit_url = "postgresql+asyncpg://managed-user:managed-password@db.example/meeting"

    settings = Settings(
        vexa_api_base="http://vexa.test",
        database_url=explicit_url,
    )

    assert settings.database_url == explicit_url
