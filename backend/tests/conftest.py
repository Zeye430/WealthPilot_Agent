"""Tests use a separate database (name suffixed _test), never shared with development / demo data.

DATABASE_URL must be set before any app module is imported: pytest loads this file first, then the
test modules.
If the database is down, nothing fails here; database-dependent tests skip themselves.
"""

import os

from sqlalchemy.engine import make_url

from app.core.config import Settings

# Rate limiting is off by default in tests (one test account sends many requests within seconds);
# test_auth.py tests it separately
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

_base = make_url(os.environ.get("DATABASE_URL") or Settings().database_url)
TEST_DB = f"{_base.database}_test" if not _base.database.endswith("_test") else _base.database
os.environ["DATABASE_URL"] = _base.set(database=TEST_DB).render_as_string(hide_password=False)


def _prepare_test_database() -> None:
    import psycopg
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    if not TEST_DB.endswith("_test"):  # never wipe a non-test database
        raise RuntimeError(f"拒绝在非测试库 {TEST_DB} 上运行测试")
    admin = _base.set(drivername="postgresql").render_as_string(hide_password=False)
    try:
        with psycopg.connect(admin, autocommit=True, connect_timeout=3) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    except psycopg.OperationalError:
        return  # database not running: database-dependent tests will skip

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.upgrade(cfg, "head")
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        if tables:
            conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    engine.dispose()


_prepare_test_database()


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def test_identity():
    """Use the request-header identity double by default; tests of real sign-in remove this
    override themselves."""
    from app.api.deps import get_current_user
    from app.main import app
    from tests.identity import header_identity

    app.dependency_overrides[get_current_user] = header_identity
    yield
    app.dependency_overrides.pop(get_current_user, None)
