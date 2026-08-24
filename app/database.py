"""异步数据库引擎与会话管理"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# 异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=5,
    max_overflow=10,
)

# 会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """ORM 模型基类"""

# 这段时死代码，没用的。
# async def get_session() -> AsyncSession:
#     """FastAPI 依赖注入：获取数据库会话"""
#     async with async_session_factory() as session:
#         try:
#             yield session
#             await session.commit()
#         except Exception:
#             await session.rollback()
#             raise
#         finally:
#             await session.close()
#

async def init_db():
    """创建所有表（仅限开发/脚本环境使用）

    ⚠️ 生产环境 schema 由 Alembic 迁移管理（alembic upgrade head），
    main.py 启动时自动执行；本函数保留供测试与一次性脚本使用。
    """
    # 导入所有模型，确保它们注册到 Base.metadata
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
