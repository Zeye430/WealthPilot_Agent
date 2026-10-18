"""测试使用独立数据库（库名加 _test 后缀），不与开发 / 演示数据共用。

必须在任何 app 模块被导入之前设置 DATABASE_URL：pytest 会先加载本文件，再导入测试模块。
数据库不可用时不报错，依赖数据库的测试会自行跳过。
"""

import os

from sqlalchemy.engine import make_url

from app.core.config import Settings

_base = make_url(os.environ.get("DATABASE_URL") or Settings().database_url)
TEST_DB = f"{_base.database}_test" if not _base.database.endswith("_test") else _base.database
os.environ["DATABASE_URL"] = _base.set(database=TEST_DB).render_as_string(hide_password=False)


def _prepare_test_database() -> None:
    import psycopg
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    if not TEST_DB.endswith("_test"):  # 防止误清空非测试库
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
        return  # 数据库未启动：依赖数据库的测试会跳过

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
