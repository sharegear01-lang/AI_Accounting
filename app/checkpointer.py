"""PostgresSaver checkpointer - 会话记忆持久化

使用 LangGraph 的 AsyncPostgresSaver 将对话状态保存到 PostgreSQL，
实现基于 thread_id 的多轮对话记忆。
"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

# 全局 checkpointer 单例（在 lifespan 中初始化）
_checkpointer = None
_context_manager = None


async def init_checkpointer():
    """初始化 PostgresSaver checkpointer

    创建连接池并在数据库中建立 checkpoint 所需的表结构。
    应在应用 lifespan 启动阶段调用。
    """
    global _checkpointer, _context_manager

    logger.info("初始化 PostgresSaver checkpointer...")
    # AsyncPostgresSaver 使用原生 psycopg，需要去掉 SQLAlchemy 的驱动后缀
    psycopg_url = settings.DATABASE_URL.replace("+psycopg", "")
    _context_manager = AsyncPostgresSaver.from_conn_string(psycopg_url)
    _checkpointer = await _context_manager.__aenter__()
    await _checkpointer.setup()
    logger.info("PostgresSaver checkpointer 初始化完成")

    return _checkpointer


async def close_checkpointer():
    """关闭 checkpointer 连接池"""
    global _checkpointer, _context_manager

    if _context_manager is not None:
        await _context_manager.__aexit__(None, None, None)
        _checkpointer = None
        _context_manager = None
        logger.info("PostgresSaver checkpointer 已关闭")


def get_checkpointer() -> AsyncPostgresSaver | None:
    """获取当前 checkpointer 实例"""
    return _checkpointer
