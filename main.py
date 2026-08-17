"""AI 会计助手 - FastAPI 启动入口"""

import sys
import asyncio

# Windows 下 psycopg 异步需要 SelectorEventLoop（必须在所有异步库导入前设置）
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 尽早把 .env 载入 os.environ。
# LangSmith SDK 只从环境变量读取追踪配置（LANGSMITH_TRACING / API_KEY / PROJECT /
# ENDPOINT）。pydantic-settings 解析 .env 只是填充 Settings 对象，不会写入 os.environ，
# 因此不主动 load_dotenv 的话，即使 .env 里 LANGSMITH_TRACING=true 也不会产生任何追踪。
from dotenv import load_dotenv

load_dotenv()

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import init_db
from app.checkpointer import init_checkpointer, close_checkpointer
from app.logger import setup_logging, get_logger

# 初始化日志系统
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表 + 初始化 checkpointer，关闭时清理"""
    logger.info("应用启动中...")
    await init_db()
    logger.info("数据库表初始化完成")
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
from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
app.include_router(auth_router)
app.include_router(chat_router)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=["logs/*", "__pycache__/*", ".idea/*"],
        loop="asyncio",
    )
