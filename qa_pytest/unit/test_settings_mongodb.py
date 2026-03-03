from api.settings import Settings


def test_mongodb_helpers_with_explicit_url() -> None:
    cfg = Settings(
        _env_file=None,
        DB_TYPE="mongodb",
        MONGODB_URL="mongodb://user:pass@mongo:27017",
        MONGODB_DB_NAME="apidb",
    )

    assert cfg.normalized_db_type() == "mongodb"
    assert cfg.is_mongodb()
    assert not cfg.is_sql_database()
    assert cfg.get_mongodb_url() == "mongodb://user:pass@mongo:27017"


def test_mongodb_helpers_build_url_from_parts(monkeypatch) -> None:
    monkeypatch.delenv("MONGODB_URL", raising=False)
    monkeypatch.setenv("MONGODB_ROOT_USER", "mongo")
    monkeypatch.setenv("MONGODB_ROOT_PASSWORD", "secret")

    cfg = Settings(
        _env_file=None,
        DB_TYPE="mongodb",
        DB_HOST="mongodb",
        MONGODB_PORT=27017,
    )

    assert cfg.get_mongodb_url() == "mongodb://mongo:secret@mongodb:27017"


def test_postgres_alias_is_sql_database() -> None:
    cfg = Settings(_env_file=None, DB_TYPE="postgres")
    assert cfg.normalized_db_type() == "postgres"
    assert cfg.is_sql_database()
    assert not cfg.is_mongodb()
