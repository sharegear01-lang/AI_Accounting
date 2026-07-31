"""Chat 接口的请求/响应模型"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """聊天请求体"""

    message: str = Field(..., description="用户文本消息", min_length=1)
    thread_id: str = Field(
        default="default_thread",
        description="会话线程ID，用于维持上下文记忆",
    )
    image_base64: str | None = Field(
        default=None,
        description="可选：图片的 base64 编码（用于 OCR 识别记账）",
    )


class ChatResponse(BaseModel):
    """聊天响应体（非流式备用）"""

    reply: str = Field(..., description="AI 回复内容")
    thread_id: str = Field(..., description="会话线程ID")
