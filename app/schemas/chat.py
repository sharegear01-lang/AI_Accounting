"""Chat 接口的请求/响应模型"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """聊天请求体"""

    message: str = Field(
        default="",
        description="用户文本消息（HITL 按钮决策时可为空）",
    )
    thread_id: str = Field(
        default="default_thread",
        description="会话线程ID，用于维持上下文记忆",
    )
    image_base64: str | None = Field(
        default=None,
        description="可选：图片的 base64 编码（用于 OCR 识别记账）",
    )
    approve: bool | None = Field(
        default=None,
        description=(
            "HITL 人工确认决策：True=同意 / False=拒绝。设置该字段时不再走 Agent 流程，"
            "直接恢复被 interrupt 暂停的 LangGraph（前端按钮点击后调用）"
        ),
    )


class ChatResponse(BaseModel):
    """聊天响应体（非流式备用）"""

    reply: str = Field(..., description="AI 回复内容")
    thread_id: str = Field(..., description="会话线程ID")
    requires_confirmation: bool = Field(
        default=False,
        description=(
            "是否等待用户确认（HITL interrupt 暂停）。为 True 时前端应渲染"
            "『同意 / 拒绝』按钮，点击后带 approve 字段重新请求 /chat"
        ),
    )
    preview: str | None = Field(
        default=None,
        description="待确认操作的预览文本（requires_confirmation=True 时有效）",
    )
    expires_in_seconds: int | None = Field(
        default=None,
        description=(
            "确认剩余有效秒数（requires_confirmation=True 时有效）。"
            "超时后后端自动按拒绝处理，避免 interrupt 永久挂起阻塞图执行"
        ),
    )
    cancelled_confirmations: int = Field(
        default=0,
        description=(
            "本次请求自动取消的待确认操作数量：用户未点击确认按钮就发送了新消息，"
            "后端自动按拒绝取消这些挂起的 interrupt。"
            "前端应把仍在展示中的确认卡片标记为『已取消』（禁用按钮），"
            "避免用户点击失效按钮后收到『无需重复确认』的困惑提示"
        ),
    )
