"""Alembic 迁移环境配置（异步引擎）

- 连接串从 app.config.settings.DATABASE_URL 注入（与运行时代码同一配置源）
- target_metadata 使用 app.database.Base.metadata（users / transactions）
- 排除 LangGraph checkpointer 自管表（checkpoints 系列由 AsyncPostgresSaver.setup()
  自动创建/迁移，不归 Alembic 管，见 app/checkpointer.py）
- Windows 下 psycopg 异步需要 SelectorEventLoop（与 main.py 同策略）
"""

import asyncio
import sys

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models  # noqa: F401
from alembic import context

# 确保应用配置与 ORM 模型被加载（注册到 Base.metadata）
from app.config import settings
from app.database import Base

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

config = context.config

# 连接串统一从应用配置注入（.env），不维护两份
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata

# LangGraph AsyncPostgresSaver 自管的表（勿纳入 Alembic 版本管理）
_LANGGRAPH_TABLES = {"checkpoints", "checkpoint_writes", "checkpoint_blobs", "checkpoint_migrations"}


def _include_name(name, type_, parent_names):
    if type_ == "table":
        return name not in _LANGGRAPH_TABLES
    return True


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连数据库"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=_include_name,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=_include_name,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """在线模式：异步引擎连接数据库执行迁移"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
