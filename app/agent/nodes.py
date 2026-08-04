"""LangGraph 节点实现"""

import re
import time

from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from langchain_deepseek import ChatDeepSeek
from langgraph.prebuilt import ToolNode

from app.config import settings
from app.agent.state import AgentState
from app.agent.tools import ALL_TOOLS
from app.logger import get_logger

logger = get_logger(__name__)

# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是个人财务记账助手。

## 功能

1. 记账：用户描述消费/收入时，调用 add_transaction。
2. 查询：用户想查看账单时，调用 query_transactions。
3. 修改：用户要修改记录时，先调用 query_transactions 找到 ID，然后立即调用 update_transaction。
4. 删除：用户要删除记录时，先调用 query_transactions 找到 ID，然后立即调用 delete_transaction。

## 规则

- 金额：支出正数，收入负数。
- 日期：根据当前日期推算，格式 YYYY-MM-DD。当前日期：{today}。
- 分类：自动推断（餐饮、购物、交通、娱乐、居住、医疗、教育、其他）。
- 信息不足时礼貌追问。
- 始终用中文回复。
- 查询结果用表格展示，必要时汇总。
"""

# ─── LLM 实例 ────────────────────────────────────────────────────────────────

def _get_llm(thinking=False, tool_choice=None):
    """创建 DeepSeek LLM 实例并绑定工具

    Args:
        thinking: 是否启用思考模式（默认关闭，避免 reasoning_content 兼容问题）
        tool_choice: 工具选择策略，如 "any" 强制调用工具
    """
    model_kwargs = {}
    if not thinking:
        # 禁用思考模式以避免 reasoning_content 兼容问题
        model_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    llm = ChatDeepSeek(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        streaming=True,
        model_kwargs=model_kwargs,
    )
    if tool_choice:
        return llm.bind_tools(ALL_TOOLS, tool_choice=tool_choice)
    return llm.bind_tools(ALL_TOOLS)


# ─── 节点函数 ─────────────────────────────────────────────────────────────────

def _last_user_message_wants_modify_delete(messages) -> bool:
    """检查最后一条用户消息是否包含修改/删除意图

    只看最后一条 HumanMessage，不扫描历史。
    """
    for msg in reversed(messages):
        if type(msg).__name__ == "HumanMessage":
            content = (msg.content or "").lower()
            return bool(re.search(r'(修改|删除|更改|改一下|改成|变更为|删掉|去掉)', content))
    return False


async def agent_node(state: AgentState) -> dict:
    """Agent 推理节点：调用 LLM 进行决策"""
    from datetime import date

    messages = state["messages"]
    logger.debug(f"[Agent] 输入消息数: {len(messages)} | 最后一条: {str(messages[-1].content)[:100]}")

    # 确保 system prompt 存在且包含最新日期
    today_str = date.today().isoformat()
    system_msg = SystemMessage(content=SYSTEM_PROMPT.format(today=today_str))

    # 组装消息：system + 历史对话
    # 1. 清除 reasoning_content（DeepSeek 思考模式残留）
    # 2. 修补孤儿 tool_calls（interrupt 暂停后 checkpoint 中缺少 ToolMessage）
    full_messages = [system_msg]
    for msg in messages:
        if hasattr(msg, 'additional_kwargs') and 'reasoning_content' in msg.additional_kwargs:
            msg_copy = msg.model_copy()
            msg_copy.additional_kwargs = {k: v for k, v in msg.additional_kwargs.items() if k != 'reasoning_content'}
            full_messages.append(msg_copy)
        else:
            full_messages.append(msg)

    # 修补孤儿 tool_calls：找到有 tool_calls 但缺少对应 ToolMessage 的 AI 消息
    existing_tool_ids = {m.tool_call_id for m in full_messages if isinstance(m, ToolMessage)}
    patched = []
    for msg in full_messages:
        patched.append(msg)
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["id"] not in existing_tool_ids:
                    patched.append(ToolMessage(
                        content="⏸️ 操作已暂停，等待用户确认。",
                        tool_call_id=tc["id"],
                    ))
                    logger.debug(f"[Agent] 修补孤儿 tool_call: {tc['id']}")
    full_messages = patched

    # 第一步：调用 LLM（禁用思考模式以避免 reasoning_content 问题）
    llm = _get_llm(thinking=False)
    start = time.time()
    response = await llm.ainvoke(full_messages)
    elapsed = time.time() - start

    has_tool_calls = hasattr(response, "tool_calls") and response.tool_calls

    # 如果用户有修改/删除意图但 LLM 没调工具，用 tool_choice="any" 重试
    wants_modify_delete = _last_user_message_wants_modify_delete(messages)
    if wants_modify_delete and not has_tool_calls:
        logger.info("[Agent] LLM 未调用工具，强制重试...")
        force_llm = _get_llm(thinking=False, tool_choice="any")
        start2 = time.time()
        response = await force_llm.ainvoke(full_messages)
        elapsed2 = time.time() - start2
        has_tool_calls = hasattr(response, "tool_calls") and response.tool_calls
        elapsed = elapsed + elapsed2
        logger.info(f"[Agent] 重试完成 | 耗时: {elapsed2:.2f}s | 工具调用: {has_tool_calls}")

    # 记录 LLM 决策结果
    if has_tool_calls:
        tool_names = [tc["name"] for tc in response.tool_calls]
        logger.info(f"[Agent] LLM 决策: 调用工具 {tool_names} | 耗时: {elapsed:.2f}s")
        for tc in response.tool_calls:
            logger.debug(f"[Agent] 工具参数: {tc['name']}({tc['args']})")
    else:
        logger.info(f"[Agent] LLM 决策: 直接回复 | 耗时: {elapsed:.2f}s | 长度: {len(response.content)}")
        logger.debug(f"[Agent] 回复内容: {response.content[:200]}")

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
        logger.debug("[Router] → tools")
        return "tools"
    logger.debug("[Router] → __end__")
    return "__end__"
