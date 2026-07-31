"""应用配置 - 基于 pydantic-settings 从 .env 加载环境变量"""

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

    # 图片处理策略
    MAX_IMAGE_SIZE_KB: int = 200
    IMAGE_TARGET_WIDTH: int = 512
    OCR_TIMEOUT_SECONDS: int = 5

    # LangSmith
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: str = "https://api.smith.LangChain.com"
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "LangGraph-tutorial"


# 全局单例
settings = Settings()
