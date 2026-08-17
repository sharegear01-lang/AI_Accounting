"""Agent 状态定义"""

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """LangGraph 状态机的全局状态

    - messages: 对话消息列表，使用 add_messages 注解实现追加语义
    - current_user_id: 当前操作用户 ID（由 JWT 鉴权注入）
    - user_input: 本次请求的原始用户文本（preprocess 消费后清空）
    - ocr_block: 防幻觉拦截信息（respond_blocked 消费后清空）

    注意：图片 base64 **不属于 state**——它经 config["configurable"] 传入
    preprocess 节点，避免图片字节被 checkpointer 持久化（隐私 + 体积）。
    """

    messages: Annotated[list, add_messages]
    current_user_id: str
    user_input: str
    ocr_block: dict | None
