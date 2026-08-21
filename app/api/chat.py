"""Chat 路由 - POST /chat（含 HITL 按钮决策，无独立 approve/reject 接口）"""

import time

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.errors import GraphInterrupt

from app.schemas.chat import ChatRequest, ChatResponse
from app.agent.graph import compile_graph
from app.agent.tools.crud import execute_delete, execute_update
from app.checkpointer import get_checkpointer
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])

# 触发 interrupt 的工具名（审批路径按此从 tool_calls 中定位待确认调用）
_HITL_TOOLS = ("delete_transaction", "delete_transactions", "update_transaction", "update_transactions")


def _thread_config(user_id: str, thread_id: str) -> dict:
    """按用户命名空间隔离会话线程，防止跨用户访问对话记忆

    checkpointer 以 thread_id 为 key，若不含用户维度，A 用户复用 B 的
    thread_id 即可读到/续接 B 的对话。这里统一加用户前缀命名空间；
    同时注入当前用户 ID（工具经 config 读取，多租户隔离）。
    """
    return {"configurable": {"thread_id": f"{user_id}:{thread_id}", "user_id": user_id}}


# ─── HITL interrupt 工具函数 ─────────────────────────────────────────────────

def _collect_pending_payloads(state) -> list[dict]:
    """从 checkpoint state 提取所有待确认的 interrupt payload（删除/修改预览）"""
    payloads = []
    for task in (state.tasks or []):
        for intr in (getattr(task, "interrupts", None) or []):
            v = intr.value if hasattr(intr, "value") else intr
            if isinstance(v, dict) and v.get("type") in ("delete_preview", "update_preview"):
                payloads.append(v)
    return payloads


def _find_hitl_calls(messages: list) -> list[dict]:
    """定位待确认的调用 ID：最后一条带 tool_calls 的 AI 消息中，
    按顺序取 HITL 工具调用，与 payloads 对齐（同消息 add+delete 时，
    add 不产生 payload，不会被重复执行）"""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            return [tc for tc in msg.tool_calls if tc["name"] in _HITL_TOOLS]
    return []


def _pending_expired(payloads: list[dict]) -> bool:
    """是否有待确认操作超过 HITL_EXPIRY_SECONDS 未处理（需自动取消）"""
    if not payloads:
        return False
    now = time.time()
    for p in payloads:
        at = p.get("interrupt_at")
        if at is None:
            continue  # 旧 checkpoint 无时间戳，不判超时
        if now - at > settings.HITL_EXPIRY_SECONDS:
            return True
    return False


def _remaining_seconds(payloads: list[dict]) -> int | None:
    """计算确认剩余有效秒数（供前端倒计时展示）"""
    now = time.time()
    remaining = None
    for p in payloads:
        at = p.get("interrupt_at")
        if at is None:
            continue
        r = settings.HITL_EXPIRY_SECONDS - (now - at)
        remaining = min(r, remaining) if remaining is not None else r
    return max(0, int(remaining)) if remaining is not None else None


def _ids_from_payload(payload: dict) -> list[int]:
    """从 interrupt payload 提取目标交易 ID 列表（单条/批量统一）"""
    return payload.get("transaction_ids") or (
        [payload["transaction_id"]] if payload.get("transaction_id") else []
    )


async def _apply_decisions(
    agent_app,
    config: dict,
    state,
    approved: bool,
    reject_note: str,
    user_id: str,
    as_node: str | None = "tools",
) -> list[tuple[str, str]]:
    """执行/拒绝待确认操作，并把结果 ToolMessage 修补进 checkpoint

    - approved=True：调用 crud 公共执行函数 execute_delete / execute_update
      （与工具内执行路径共用，杜绝双实现漂移）
    - approved=False：生成拒绝 ToolMessage（文案由 reject_note 指定）

    说明：不使用 LangGraph 原生 Command(resume)——1.2.9 的 resume 语义为
    "重放整个 tools 节点"，已完成工具会被重复执行（LangGraph 官方已知
    缺陷，PR #3126 修复未合并），故保留手动执行 + aupdate_state 修补路径。

    as_node 语义：
    - "tools"：修补后图从 agent 节点继续 → 按钮点击后立即恢复图跑完（生成总结回复）
    - None：修补后图回到 END → 适合"新消息打断 → 自动取消后重新从 START 处理新消息"
    """
    messages = state.values.get("messages", []) if state and state.values else []
    hitl_calls = _find_hitl_calls(messages)
    payloads = _collect_pending_payloads(state)

    results: list[tuple[str, str]] = []
    for idx, payload in enumerate(payloads):
        tool_call_id = hitl_calls[idx]["id"] if idx < len(hitl_calls) else f"resume-{idx}"
        ptype = payload.get("type")

        if ptype == "delete_preview":
            ids = _ids_from_payload(payload)
            if approved:
                rowcount, err = await execute_delete(ids, user_id)
                content = f"✅ 已删除 {rowcount} 笔交易记录。" if not err else err
            else:
                content = reject_note
        elif ptype == "update_preview":
            ids = _ids_from_payload(payload)
            if approved:
                fields = dict(payload.get("fields", {}) or {})
                rowcount, err = await execute_update(ids, fields, user_id)
                changed = "、".join(f"{k}={v}" for k, v in fields.items())
                content = f"✅ 已修改 {rowcount} 笔交易记录（{changed}）。" if not err else err
            else:
                content = reject_note
        else:
            continue

        logger.info(f"[HITL] 待确认操作: {ptype} | approved={approved} | 结果: {content[:60]}")
        results.append((tool_call_id, content))

    if results:
        await agent_app.aupdate_state(
            config,
            {"messages": [ToolMessage(content=res, tool_call_id=tid) for tid, res in results]},
            as_node=as_node,
        )
        logger.info(f"[HITL] checkpoint 已修补，tool_call_ids={[tid for tid, _ in results]}")
    return results


async def _interrupt_response(agent_app, config, thread_id: str, cancelled: int = 0) -> ChatResponse:
    """图执行暂停：返回结构化确认信息（前端据此渲染『同意/拒绝』按钮）

    cancelled：本次请求在此之前自动取消的待确认操作数量（用户未确认就发新消息），
    前端需把仍在展示中的旧确认卡片标记为『已取消』。
    """
    state = await agent_app.aget_state(config)
    payloads = _collect_pending_payloads(state)
    preview = payloads[0].get("preview", "需要您确认一项操作。") if payloads else "需要您确认一项操作。"
    expires_in = _remaining_seconds(payloads) if payloads else None
    logger.info(f"[/chat] 图执行暂停，等待用户确认 | preview: {preview[:100]} | 剩余: {expires_in}s | 本次已取消确认: {cancelled}")
    return ChatResponse(
        reply="",
        thread_id=thread_id,
        requires_confirmation=True,
        preview=preview,
        expires_in_seconds=expires_in,
        cancelled_confirmations=cancelled,
    )


async def _resume_graph(
    agent_app,
    config: dict,
    thread_id: str,
    user_id: str,
    approved: bool,
    expired: bool = False,
) -> ChatResponse:
    """按钮决策路径：执行/拒绝 → 修补 checkpoint → （同意时）立即恢复图跑到 agent 总结回复

    前端点击『同意/拒绝』后带 approve 字段调用 /chat，走到这里。
    expired=True 时忽略用户的点击，强制按拒绝处理（确认已超时）。

    同意 → as_node="tools" + ainvoke(None) 恢复图，LLM 生成总结回复；
    拒绝/超时 → as_node=None 把图修补回 END，直接返回明确的拒绝结果
    （不恢复 agent，避免 LLM 据上下文再次发起操作造成"超时后又弹新卡"）。
    """
    state = await agent_app.aget_state(config)
    payloads = _collect_pending_payloads(state)
    if not payloads:
        return ChatResponse(reply="⚠️ 该操作已处理或已过期，无需重复确认。", thread_id=thread_id)

    if expired:
        approved = False
        reject_note = f"⏰ 确认超时（超过 {settings.HITL_EXPIRY_SECONDS} 秒未操作），操作已自动取消。"
    else:
        op_name = "修改" if payloads[0].get("type") == "update_preview" else "删除"
        reject_note = f"❌ 用户拒绝了{op_name}操作。"

    # 拒绝/超时：as_node=None 把图修补回 END，直接返回明确的拒绝结果。
    # 注意不要在此恢复 agent 跑总结——LLM 看到原始"删除/修改"请求 + 拒绝提示，
    # 可能按 prompt 规则再次调用工具，导致"超时/拒绝后又弹出新确认卡"的困惑。
    # 图已解除阻塞，agent 会在用户下一条消息时自然消化这段上下文。
    as_node = "tools" if approved else None
    results = await _apply_decisions(
        agent_app, config, state,
        approved=approved, reject_note=reject_note, user_id=user_id, as_node=as_node,
    )

    if not approved:
        return ChatResponse(reply="\n\n".join(res for _, res in results), thread_id=thread_id)

    # 恢复图：从 agent 节点继续，让 LLM 基于工具结果生成总结回复
    try:
        final = await agent_app.ainvoke(None, config=config)
        # 恢复过程中 agent 又触发了新的 interrupt（如再次发起删除/修改）→ 返回新确认卡
        new_state = await agent_app.aget_state(config)
        if _collect_pending_payloads(new_state):
            logger.info("[/chat] 恢复图后 agent 又发起新的待确认操作，返回新确认预览")
            return await _interrupt_response(agent_app, config, thread_id)
        last = final.get("messages", [None])[-1] if final and final.get("messages") else None
        reply = str(last.content) if last is not None else ""
        if not reply:
            reply = "\n\n".join(res for _, res in results)
    except GraphInterrupt:
        # 罕见情况：恢复时直接抛出 interrupt 异常（兼容旧版本）
        logger.warning("[/chat] 恢复图时捕获到 GraphInterrupt，返回新确认预览")
        return await _interrupt_response(agent_app, config, thread_id)
    except Exception as e:
        logger.exception(f"[/chat] 恢复图失败，直接返回工具结果: {e}")
        reply = "\n\n".join(res for _, res in results)

    return ChatResponse(reply=reply, thread_id=thread_id)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, current_user: User = Depends(get_current_user)):
    """与 AI 记账助手对话

    - 纯文本：直接发送给 Agent 处理
    - 带图片：先 OCR 识别，再将识别结果 + 用户消息一起发给 Agent
    - 带 approve 字段（True/False）：HITL 按钮决策，直接恢复被 interrupt
      暂停的图（不再使用自然语言"确认/取消"——那会增加误判机会）

    超时兜底：interrupt 暂停后若用户不处理（不点击、也不发新消息），
    超过 HITL_EXPIRY_SECONDS 后自动按拒绝取消；用户发新消息也会先自动
    取消挂起的确认再处理新消息，确保 interrupt 不会永久挂起阻塞图执行。
    """
    start_time = time.time()
    logger.info(
        f"[/chat] 收到请求 | user={current_user.username} | thread={request.thread_id} "
        f"| 消息: {request.message[:80]} | 含图片: {bool(request.image_base64)} | approve={request.approve}"
    )

    try:
        config = _thread_config(current_user.id, request.thread_id)
        checkpointer = get_checkpointer()
        agent_app = compile_graph(checkpointer=checkpointer)

        # ── HITL 按钮决策（前端点击 同意/拒绝）────────────────────────
        if request.approve is not None:
            state = await agent_app.aget_state(config)
            payloads = _collect_pending_payloads(state)
            if not payloads:
                return ChatResponse(
                    reply="⚠️ 该操作已处理或已过期，无需重复确认。",
                    thread_id=request.thread_id,
                )
            expired = _pending_expired(payloads)
            logger.info(f"[/chat] HITL 决策 | thread={request.thread_id} | approve={request.approve} | 已超时={expired}")
            return await _resume_graph(
                agent_app, config, request.thread_id, current_user.id,
                approved=request.approve, expired=expired,
            )

        if not request.message.strip() and not request.image_base64:
            raise HTTPException(status_code=422, detail="消息不能为空")

        # ── 检查该 thread 是否有挂起的 interrupt（上一次操作未确认）──────
        state = await agent_app.aget_state(config)
        pending = _collect_pending_payloads(state)
        cancelled = 0
        if pending:
            # 用户发来新消息 = 不再等待确认：自动取消挂起操作，解除图阻塞，再处理新消息。
            # 这是超时之外的第二种兜底——即使未到超时阈值，新消息也会让挂起的
            # 确认自动失效，interrupt 不会永久挂起。
            cancelled = len(pending)
            expired = _pending_expired(pending)
            reject_note = (
                f"⏰ 确认超时（超过 {settings.HITL_EXPIRY_SECONDS} 秒未操作），操作已自动取消。"
                if expired
                else "❌ 操作未获确认，已自动取消。"
            )
            logger.info(f"[/chat] 检测到 {cancelled} 个未确认操作，自动取消后处理新消息 | 已超时={expired}")
            await _apply_decisions(
                agent_app, config, state,
                approved=False, reject_note=reject_note,
                user_id=current_user.id, as_node=None,
            )

        # 构造图输入：user_input + 图片（OCR 识别与防幻觉闸门在 preprocess 节点内完成）
        # 图片经 config["configurable"] 传入（不进 state/checkpoint），避免图片字节被持久化
        if request.image_base64 and len(request.image_base64) > settings.MAX_UPLOAD_BYTES * 4 // 3 + 8:
            raise HTTPException(status_code=400, detail="图片过大，请压缩后重新上传")

        input_state = {
            "user_input": request.message,
            "current_user_id": current_user.id,
        }
        config["configurable"]["image_base64"] = request.image_base64

        logger.debug("[/chat] 调用 Agent...")

        try:
            result = await agent_app.ainvoke(input_state, config=config)
        except GraphInterrupt as e:
            # 某些情况下 GraphInterrupt 会直接抛出（兼容旧版本）
            logger.warning(f"[/chat] 捕获到 GraphInterrupt 异常: {e}")
            return await _interrupt_response(agent_app, config, request.thread_id, cancelled=cancelled)

        # ainvoke 正常返回，检查是否有 interrupt 暂停（LangGraph 新版本行为）
        state = await agent_app.aget_state(config)
        if state and state.next:
            payloads = _collect_pending_payloads(state)
            if payloads:
                logger.info(f"[/chat] 检测到 interrupt | state.next={state.next} | 数量: {len(payloads)}")
                return await _interrupt_response(agent_app, config, request.thread_id, cancelled=cancelled)

        # 取最后一条 AI 回复
        reply = result["messages"][-1].content
        elapsed = time.time() - start_time
        logger.info(f"[/chat] 请求完成 | 耗时: {elapsed:.2f}s | 回复长度: {len(reply)} | 本次已取消确认: {cancelled}")

        # 新消息打断了待确认操作：在回复前固定追加提示，即使确认卡片滚出视野用户也能看到
        if cancelled:
            reply = f"（提示：之前的 {cancelled} 项待确认操作已自动取消，未执行。）\n\n{reply}"

        return ChatResponse(reply=reply, thread_id=request.thread_id, cancelled_confirmations=cancelled)

    except TimeoutError as e:
        elapsed = time.time() - start_time
        logger.error(f"[/chat] 超时 | 耗时: {elapsed:.2f}s | {e}")
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception(f"[/chat] 异常 | 耗时: {elapsed:.2f}s | {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误：{str(e)}")
