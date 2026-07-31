"""LangGraph 节点实现"""

from langchain_core.messages import SystemMessage
from langchain_deepseek import ChatDeepSeek
from langgraph.prebuilt import ToolNode

from app.config import settings
from app.agent.state import AgentState
from app.agent.tools import ALL_TOOLS

# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是一个专业的个人财务记账助手。你的职责是：

1. **记账**：当用户描述一笔消费或收入时，提取关键信息（商户、金额、分类、日期、描述），调用 add_transaction 工具完成记账。
2. **查询**：当用户想查看历史账单时，根据条件调用 query_transactions 工具查询。

## 规则

- 金额：支出为正数，收入为负数。
- 日期：如果用户说"今天"、"昨天"等相对日期，请根据当前日期推算出 YYYY-MM-DD 格式。当前日期为 {today}。
- 分类：自动推断最合适的分类（餐饮、购物、交通、娱乐、居住、医疗、教育、其他）。如果无法确定，使用"其他"。
- 信息不足：如果用户提供的信息不足以完成记账（例如缺少金额），请礼貌地追问。
- 查询结果：以清晰易读的格式呈现给用户，必要时做汇总统计。
- 语言：始终使用中文回复。
"""


# ─── LLM 实例 ────────────────────────────────────────────────────────────────

def _get_llm():
    """创建 DeepSeek LLM 实例并绑定工具"""
    llm = ChatDeepSeek(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        streaming=True,
    )
    return llm.bind_tools(ALL_TOOLS)


# ─── 节点函数 ─────────────────────────────────────────────────────────────────

async def agent_node(state: AgentState) -> dict:
    """Agent 推理节点：调用 LLM 进行决策"""
    from datetime import date

    messages = state["messages"]

    # 确保 system prompt 存在且包含最新日期
    today_str = date.today().isoformat()
    system_msg = SystemMessage(content=SYSTEM_PROMPT.format(today=today_str))

    # 组装消息：system + 历史对话
    full_messages = [system_msg] + messages

    llm = _get_llm()
    response = await llm.ainvoke(full_messages)

    return {"messages": [response]}


# 工具执行节点（使用 LangGraph 预构建的 ToolNode）
tools_node = ToolNode(ALL_TOOLS)


# ─── 路由函数 ─────────────────────────────────────────────────────────────────

def should_continue(state: AgentState) -> str:
    """判断 Agent 是否需要调用工具

    返回:
        "tools" - 需要执行工具调用
        "__end__" - 无需工具，直接结束
    """
    last_message = state["messages"][-1]

    # 如果最后一条消息包含 tool_calls，则进入工具节点
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "__end__"
