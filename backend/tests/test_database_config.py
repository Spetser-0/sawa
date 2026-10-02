from app.config import normalize_database_url


def test_normalize_render_postgres_url():
    assert normalize_database_url(
        "postgres://user:pass@host.example/db"
    ) == "postgresql+psycopg://user:pass@host.example/db"


def test_normalize_postgresql_url():
    assert normalize_database_url(
        "postgresql://user:pass@host.example/db"
    ) == "postgresql+psycopg://user:pass@host.example/db"


def test_keep_sqlite_url_unchanged():
    assert normalize_database_url("sqlite:///./sawa.db") == "sqlite:///./sawa.db"


def test_keep_explicit_driver_url_unchanged():
    url = "postgresql+psycopg2://user:pass@host.example/db"
    assert normalize_database_url(url) == url
