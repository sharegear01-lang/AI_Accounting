"""AI 会计助手 - FastAPI 启动入口"""

import asyncio
import os
import sys

# Windows 下 psycopg 异步需要 SelectorEventLoop（必须在所有异步库导入前设置）
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 尽早把 .env 载入 os.environ。
# LangSmith SDK 只从环境变量读取追踪配置（LANGSMITH_TRACING / API_KEY / PROJECT /
# ENDPOINT）。pydantic-settings 解析 .env 只是填充 Settings 对象，不会写入 os.environ，
# 因此不主动 load_dotenv 的话，即使 .env 里 LANGSMITH_TRACING=true 也不会产生任何追踪。
from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI

from alembic import command
from app.checkpointer import close_checkpointer, init_checkpointer
from app.config import settings
from app.logger import get_logger, setup_logging

# 初始化日志系统
setup_logging()
logger = get_logger(__name__)


def run_migrations() -> None:
    """编程式执行 alembic upgrade head（启动时自动同步 schema）

    迁移是 schema 的唯一来源（取代启动时 create_all）：
    - 新环境：首次启动自动建表
    - 旧环境（create_all 时代建的库）：初始迁移幂等跳过已存在表，只登记版本
    - 失败即抛异常 → 应用启动失败（fail fast），避免带脏 schema 上线
    """
    cfg = AlembicConfig(str(Path(__file__).resolve().parent / "alembic.ini"))
    command.upgrade(cfg, "head")
    logger.info("数据库迁移完成（alembic upgrade head）")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时执行迁移 + 初始化 checkpointer，关闭时清理"""
    logger.info("应用启动中...")
    await asyncio.to_thread(run_migrations)
    logger.info("数据库 schema 同步完成")
    await init_checkpointer()
    yield
    logger.info("应用关闭")
    await close_checkpointer()



app = FastAPI(
    title="AI 会计助手",
    description="基于 LangGraph + DeepSeek 的智能记账系统",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "AI 会计助手运行中"}


# 注册路由
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.transactions import router as transactions_router

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(transactions_router)


if __name__ == "__main__":
    # 注意：policy 必须在 uvicorn 创建事件循环前设置，故外部执行
    # `uvicorn main:app`（Windows 下）会因 ProactorEventLoop 失败；
    # 统一使用 `python main.py` 启动（生产环境 systemd 同样用该入口）。
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=settings.DEBUG,  # 生产 .env 设 DEBUG=False 即关闭热重载
        reload_excludes=["logs/*", "__pycache__/*", ".idea/*"],
        loop="asyncio",
    )
