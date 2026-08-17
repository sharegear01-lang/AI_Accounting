"""应用配置 - 基于 pydantic-settings 从 .env 加载环境变量"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 基础服务
    DEBUG: bool = True
    DATABASE_URL: str = "postgresql+psycopg://admin:secret@localhost:5432/ai_acct"

    # DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"

    # Qwen OCR (Dashscope)
    DASHSCOPE_API_KEY: str = ""
    QWEN_OCR_MODEL_NAME: str = "qwen3.5-ocr"

    # JWT 鉴权
    SECRET_KEY: str = "your-256-bit-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    # 图片处理策略（准确率与效率平衡）
    # OCR 延迟主要由视觉模型的输入像素数决定，而非字节数，
    # 因此不再做"降质量到体积达标"的压榨（只损失清晰度、省不下延迟）。
    IMAGE_TARGET_LONG_EDGE: int = 1280   # 长边上限：OCR 准确率甜点，也是像素/延迟预算
    JPEG_QUALITY: int = 80               # JPEG 输出质量（固定，不做降质循环）
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024  # 上传图片原始大小上限（防滥用）
    OCR_TIMEOUT_SECONDS: int = 5

    # 对话历史窗口（短期记忆定位）
    # 记账助手是任务型应用：逐轮消息基本独立，历史价值集中在最近几轮
    # （引用刚记的账、OCR 追问、HITL 上下文）。更早消息只增成本与噪音。
    # 传 LLM 前裁剪（checkpoint 保留完整历史供审计/调试）；按需调整。
    MAX_HISTORY_MESSAGES: int = 10

    # LangSmith
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: str = "https://api.smith.LangChain.com"
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "LangGraph-tutorial"


# 全局单例
settings = Settings()

# ─── LangSmith 追踪：回写到 os.environ ──────────────────────────────────────
# LangSmith SDK 运行时只从 os.environ 读取配置（LANGSMITH_TRACING / API_KEY /
# PROJECT / ENDPOINT），pydantic-settings 不会把它们导出到 os.environ。
# 这里显式回写，保证任何入口（main.py / uvicorn / 脚本）追踪都生效。
# 用 setdefault：若进程已有真实环境变量，以环境变量为准。
os.environ.setdefault("LANGSMITH_TRACING", "true" if settings.LANGSMITH_TRACING else "false")
if settings.LANGSMITH_API_KEY:
    os.environ.setdefault("LANGSMITH_API_KEY", settings.LANGSMITH_API_KEY)
if settings.LANGSMITH_PROJECT:
    os.environ.setdefault("LANGSMITH_PROJECT", settings.LANGSMITH_PROJECT)
if settings.LANGSMITH_ENDPOINT:
    os.environ.setdefault("LANGSMITH_ENDPOINT", settings.LANGSMITH_ENDPOINT)
