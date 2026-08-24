"""Agent 推理节点：LLM 决策 + 历史裁剪 + 结束路由"""

import time
from datetime import date

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.nodes.llm import SYSTEM_PROMPT, _get_llm
from app.agent.state import AgentState
from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


def _trim_history(messages: list) -> list:
    """滑动窗口裁剪：保留最近 N 条消息，向前对齐到 HumanMessage 起点

    记账助手是任务型应用，只需短期记忆（最近几轮）；更早的消息只增
    成本与噪音。对齐原因：工具调用对（AIMessage.tool_calls ↔ ToolMessage）
    必须成对出现，从中间切开会产生孤儿 tool_call，被孤儿修补逻辑误补
    为"⏸️ 已暂停"误导 LLM——因此宁可略超几条，绝不切开工具链。
    """
    limit = settings.MAX_HISTORY_MESSAGES
    if len(messages) <= limit:
        return messages
    window = messages[-limit:]
    # 从窗口起点向后找第一条 HumanMessage，作为完整轮次的起点
    for i, msg in enumerate(window):
        if isinstance(msg, HumanMessage):
            return window[i:]
    return window  # 兜底：窗口内无 HumanMessage（理论不出现）


async def agent_node(state: AgentState) -> dict:
    """Agent 推理节点：调用 LLM 进行决策"""
    raw_messages = state["messages"]
    messages = _trim_history(raw_messages)
    if len(messages) < len(raw_messages):
        logger.info(
            f"[Agent] 历史裁剪: {len(raw_messages)} → {len(messages)} 条"
            f"（保留最近 {settings.MAX_HISTORY_MESSAGES} 条并轮次对齐）"
        )
    logger.debug(f"[Agent] 输入消息数: {len(messages)} | 最后一条: {str(messages[-1].content)[:100]}")

    # 确保 system prompt 存在且包含最新日期
    today_str = date.today().isoformat()
    system_msg = SystemMessage(content=SYSTEM_PROMPT.format(today=today_str))

    # 组装消息：system + 历史对话
    # 注意：这里不再清理 reasoning_content——本图始终以 thinking=False 调用，
    # API 不会返回该字段。若未来启用 thinking 模式，DeepSeek 要求
    # reasoning_content 原样回传（缺失报 400），届时需改为保留该字段。
    full_messages = [system_msg, *messages]

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
