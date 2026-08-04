"""Agent 状态定义"""

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """LangGraph 状态机的全局状态

    - messages: 对话消息列表，使用 add_messages 注解实现追加语义
    - current_user_id: 当前操作用户 ID（由 JWT 鉴权注入）
    """

    messages: Annotated[list, add_messages]
    current_user_id: str
