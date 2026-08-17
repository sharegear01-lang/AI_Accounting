"""LangGraph 节点实现"""

import base64
import re
import time

from langchain_core.messages import SystemMessage, AIMessage, ToolMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_deepseek import ChatDeepSeek
from langgraph.errors import GraphInterrupt
from openai import OpenAIError

from app.config import settings
from app.agent.state import AgentState
from app.agent.tools import ALL_TOOLS
from app.logger import get_logger
from app.services.ocr_service import recognize_structured

logger = get_logger(__name__)

# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是个人财务记账助手。

## 功能

1. 记账：用户描述消费/收入时，调用 add_transaction。
2. 查询：用户想查看账单时，调用 query_transactions。
3. 修改：用户要修改记录时，先调用 query_transactions 找到 ID，然后立即调用 update_transactions（一个或多个 ID 一次传入，只确认一次）。
4. 删除：用户要删除记录时，先调用 query_transactions 找到 ID，然后立即调用 delete_transactions（一个或多个 ID 一次传入，只确认一次）。

## 规则

- **批量操作必须用批量工具**：用户要求修改/删除多条记录时，必须把全部 ID 放进一次 update_transactions / delete_transactions 调用（展示完整明细、只确认一次）；禁止为每条记录分别调用 update_transaction / delete_transaction（那会导致逐条确认）。
- 金额：支出正数，收入负数。
- 日期：根据当前日期推算，格式 YYYY-MM-DD。当前日期：{today}。
- 分类：自动推断（餐饮、购物、交通、娱乐、居住、医疗、教育、其他）。
- 信息不足时礼貌追问。
- 始终用中文回复。
- 查询结果用表格展示，必要时汇总。
- 记账完成（add_transaction 成功）后直接向用户返回结果，禁止对刚创建的记录再次查询或修改。
- 仅在用户明确要求修改/删除某条已有记录时，才调用修改/删除工具；不要自行推断用户有修改意图。
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


# ─── 预处理节点（OCR + 防幻觉闸门）──────────────────────────────────────────

async def preprocess_node(state: AgentState, config: RunnableConfig) -> dict:
    """预处理节点：把用户输入转成 HumanMessage；有图片时先 OCR 并过防幻觉闸门

    - 无图片：直接透传用户文本。
    - 有图片：从 config["configurable"]["image_base64"] 读取（图片**不经过 state**，
      避免 checkpointer 持久化图片字节——隐私 + 体积），解码 → recognize_structured
      → 防幻觉闸门：
      - 解码失败 / OCR 失败 / 识别失败 / 金额不可信 → 写入 ocr_block，
        由路由 should_block 转到 respond_blocked_node 拦截，绝不进入 agent
        （防止 LLM 猜测金额记账）。
      - 识别成功 → 生成含 OCR 上下文的 HumanMessage。

    返回前清空 user_input / ocr_block，原始输入不进 checkpoint（会话记忆只
    保存处理后的消息）。
    """
    user_input = state.get("user_input", "")
    image_b64 = (config.get("configurable") or {}).get("image_base64") if config else None

    if not image_b64:
        return {
            "messages": [HumanMessage(content=user_input)],
            "user_input": None,
        }

    logger.info("[Preprocess] 检测到图片，开始 OCR 识别...")
    try:
        image_bytes = base64.b64decode(image_b64, validate=True)
    except Exception:
        logger.warning("[Preprocess] base64 解码失败，拦截")
        return {
            "ocr_block": {"kind": "bad_image", "detail": "图片数据格式错误"},
            "user_input": None,
        }

    try:
        ocr, raw_ocr = await recognize_structured(image_bytes, b64_hint=image_b64)
    except (TimeoutError, OpenAIError) as e:
        logger.error(f"[Preprocess] OCR 调用失败: {type(e).__name__}: {e}")
        return {
            "ocr_block": {"kind": "ocr_error", "detail": str(e)},
            "user_input": None,
        }

    logger.info(
        f"[Preprocess] OCR 完成 | recognized={ocr.recognized} | amount={ocr.amount} | unclear={ocr.unclear_fields}"
    )

    # ─── 防幻觉闸门：无法可靠识别就拦截，绝不让 agent 猜金额记账 ───
    if not ocr.recognized:
        reason = ocr.reason or "未识别到可读的文字"
        logger.warning(f"[Preprocess] OCR 未识别到有效内容，拦截 | reason={reason} | 原始输出: {raw_ocr[:200]}")
        return {
            "ocr_block": {"kind": "no_text", "detail": reason},
            "user_input": None,
        }
    if not ocr.is_bookable():
        logger.warning(f"[Preprocess] OCR 金额缺失或无效，拦截记账 | 原始输出: {raw_ocr[:200]}")
        return {
            "ocr_block": {"kind": "no_amount", "detail": ""},
            "user_input": None,
        }

    enhanced = (
        f"{ocr.to_agent_text()}\n\n"
        f"[用户说]：{user_input}\n"
        f"请根据以上 OCR 识别结果新增一笔交易记录（调用 add_transaction）。\n"
        f"金额以 OCR 识别结果为准（{ocr.amount}），不可改、不可四舍五入、不可猜测；"
        f"若置信度提示中列出未识别字段，先向用户确认后再记账，不得臆测。"
    )
    return {
        "messages": [HumanMessage(content=enhanced)],
        "user_input": None,
    }


async def respond_blocked_node(state: AgentState) -> dict:
    """防幻觉拦截回复节点：不进入 agent，直接返回错误提示"""
    block = state.get("ocr_block") or {}
    kind = block.get("kind", "no_text")
    detail = block.get("detail", "")

    if kind == "no_amount":
        reply = (
            "❌ 图片中的**金额**无法被可靠识别（模糊、缺失或格式异常）。"
            "为避免记错账，已取消本次自动记账。\n\n"
            "请重新拍摄金额区域清晰的图片，或直接手动输入交易信息。"
        )
    elif kind == "bad_image":
        reply = "❌ 图片数据格式错误，请重新上传（支持 JPG/PNG）。"
    elif kind == "ocr_error":
        reply = f"❌ 图片识别暂时失败（{detail or '服务异常'}）。请稍后重试，或直接手动输入交易信息。"
    else:
        reply = (
            f"❌ 无法从这张图片中识别到有效的交易信息（{detail or '未识别到可读的文字'}）。\n\n"
            "建议：重新拍摄，保证单据正对镜头、光线充足、文字清晰；也可以直接手动输入交易信息。"
        )

    logger.info(f"[Preprocess] 拦截回复: {reply[:80]}")
    return {"messages": [AIMessage(content=reply)], "ocr_block": None}


# ─── 节点函数 ─────────────────────────────────────────────────────────────────

def _last_user_message_wants_modify_delete(messages) -> bool:
    """检查用户最近的实际意图是否包含修改/删除请求

    只看最后一条 HumanMessage，且只扫描用户真正输入的部分
    （"[用户说]：" 标记之后），不扫描 OCR 注入的识别文本——
    单据截图常含"修改地址""删除订单"等字样，若扫描全文会把普通
    记账请求误判为修改/删除意图，进而触发 tool_choice="any" 强制
    重试，让已完成记账的 agent 再次调用工具（多余的双动作）。
    """
    for msg in reversed(messages):
        if type(msg).__name__ == "HumanMessage":
            content = (msg.content or "").lower()
            marker = "[用户说]"
            idx = content.rfind(marker)
            if idx != -1:
                # 只取用户实际输入部分，忽略 OCR 识别文本与系统注入的指令
                content = content[idx + len(marker):]
            return bool(re.search(r'(修改|删除|更改|改一下|改成|变更为|删掉|去掉)', content))
    return False


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
    from datetime import date

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


# ─── 工具执行节点 ─────────────────────────────────────────────────────────────

async def tools_node(state: AgentState, config: RunnableConfig) -> dict:
    """执行 LLM 请求的工具调用

    安全说明：工具不再接收 user_id 参数——当前用户 ID 由 JWT 鉴权写入
    config["configurable"]["user_id"]，经 LangChain 自动注入到工具的
    config 参数中。LLM 看不到也无法伪造该字段，保证多租户数据隔离。
    """
    last_message = state["messages"][-1]
    tool_map = {t.name: t for t in ALL_TOOLS}
    results: list[ToolMessage] = []

    for tc in last_message.tool_calls:
        name = tc["name"]
        args = dict(tc.get("args", {}) or {})

        tool = tool_map.get(name)
        if tool is None:
            content = f"❌ 未知工具: {name}"
        else:
            try:
                content = str(await tool.ainvoke(args, config=config))
            except GraphInterrupt:
                raise  # interrupt 必须向上传播，不能被吞掉
            except Exception as e:
                logger.exception(f"[Tools] {name} 执行失败: {e}")
                content = f"❌ 工具 {name} 执行失败：{e}"
        logger.debug(f"[Tools] {name}({args}) → {content[:120]}")
        results.append(ToolMessage(content=content, tool_call_id=tc["id"]))

    return {"messages": results}


# ─── 路由函数 ─────────────────────────────────────────────────────────────────

def should_block(state: AgentState) -> str:
    """预处理后路由：OCR 防幻觉拦截是否生效

    返回:
        "blocked" - 进入 respond_blocked 直接回复拦截文案
        "proceed" - 进入 agent 正常推理
    """
    if state.get("ocr_block"):
        logger.debug("[Router] preprocess → blocked")
        return "blocked"
    logger.debug("[Router] preprocess → proceed")
    return "proceed"


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
