"""Chat 路由 - POST /chat"""

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


async def _resume_graph(thread_id: str, approved: bool, user_id: str) -> ChatResponse:
    """处理 interrupt 暂停后的审批（单个或批量）

    从 checkpoint 读取 interrupt payload（与预览数据完全一致），
    批准时调用 crud 公共执行函数 execute_delete / execute_update，
    拒绝时生成拒绝 ToolMessage，最后 aupdate_state 修补 checkpoint。

    说明：不使用 LangGraph 原生 Command(resume)——1.2.9 的 resume 语义为
    "重放整个 tools 节点"，已完成工具会被重复执行（LangGraph 官方已知
    缺陷，PR #3126 修复未合并），故保留手动执行路径。
    """
    config = _thread_config(user_id, thread_id)
    checkpointer = get_checkpointer()
    agent_app = compile_graph(checkpointer=checkpointer)

    # 1. 获取当前状态：消息历史 + 待确认的 interrupt payloads
    state = await agent_app.aget_state(config)
    messages = state.values.get("messages", []) if state and state.values else []

    payloads = []
    for task in (state.tasks or []):
        for intr in (getattr(task, "interrupts", None) or []):
            v = intr.value if hasattr(intr, "value") else intr
            if isinstance(v, dict) and v.get("type") in ("delete_preview", "update_preview"):
                payloads.append(v)

    if not payloads:
        logger.warning(f"[/resume] 未找到待确认的 interrupt payload")
        return ChatResponse(reply="⚠️ 没有找到待确认的操作。", thread_id=thread_id)

    # 2. 定位待确认的调用 ID：最后一条带 tool_calls 的 AI 消息中，
    #    按顺序取 HITL 工具调用，与 payloads 对齐（同消息 add+delete 时，
    #    add 不产生 payload，不会被重复执行）
    hitl_calls = []
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            hitl_calls = [tc for tc in msg.tool_calls if tc["name"] in _HITL_TOOLS]
            break

    # 3. 逐个执行/拒绝
    results: list[tuple[str, str]] = []
    for idx, payload in enumerate(payloads):
        tool_call_id = hitl_calls[idx]["id"] if idx < len(hitl_calls) else f"resume-{idx}"
        ptype = payload.get("type")

        if ptype == "delete_preview":
            ids = payload.get("transaction_ids") or ([payload["transaction_id"]] if payload.get("transaction_id") else [])
            if approved:
                rowcount, err = await execute_delete(ids, user_id)
                content = f"✅ 已删除 {rowcount} 笔交易记录。" if not err else err
            else:
                content = "❌ 用户拒绝了删除操作。"
        elif ptype == "update_preview":
            ids = payload.get("transaction_ids") or ([payload["transaction_id"]] if payload.get("transaction_id") else [])
            if approved:
                fields = dict(payload.get("fields", {}) or {})
                rowcount, err = await execute_update(ids, fields, user_id)
                changed = "、".join(f"{k}={v}" for k, v in fields.items())
                content = f"✅ 已修改 {rowcount} 笔交易记录（{changed}）。" if not err else err
            else:
                content = "❌ 用户拒绝了修改操作。"
        else:
            continue

        logger.info(f"[/resume] 待确认操作: {ptype} | approved={approved} | 结果: {content[:60]}")
        results.append((tool_call_id, content))

    if not results:
        return ChatResponse(reply="⚠️ 没有找到待确认的操作。", thread_id=thread_id)

    # 4. 通过 aupdate_state 注入所有 ToolMessage，修补 checkpoint
    await agent_app.aupdate_state(
        config,
        {"messages": [ToolMessage(content=res, tool_call_id=tid) for tid, res in results]},
    )
    logger.info(f"[/resume] checkpoint 已修补，tool_call_ids={[tid for tid, _ in results]}")

    # 直接返回工具结果（agent 下次用户消息时会自动生成总结回复）
    reply = "\n\n".join(res for _, res in results)
    return ChatResponse(reply=reply, thread_id=thread_id)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, current_user: User = Depends(get_current_user)):
    """与 AI 记账助手对话

    - 纯文本：直接发送给 Agent 处理
    - 带图片：先 OCR 识别，再将识别结果 + 用户消息一起发给 Agent
    """
    start_time = time.time()
    logger.info(f"[/chat] 收到请求 | user={current_user.username} | thread={request.thread_id} | 消息: {request.message[:80]} | 含图片: {bool(request.image_base64)}")

    try:
        # 检查是否是确认/取消回复（恢复被 interrupt 暂停的图）
        config = _thread_config(current_user.id, request.thread_id)
        checkpointer = get_checkpointer()
        agent_app = compile_graph(checkpointer=checkpointer)

        # 检查该 thread 是否有待确认的 interrupt
        state = await agent_app.aget_state(config)
        is_pending = state.next == ("tools",) if state and state.next else False

        if is_pending and request.message.strip() in ("确认", "确认。", "好的", "批准", "同意", "ok", "OK"):
            logger.info(f"[/chat] 用户确认操作，恢复图执行 | thread={request.thread_id}")
            return await _resume_graph(request.thread_id, approved=True, user_id=current_user.id)
        elif is_pending and request.message.strip() in ("取消", "取消。", "拒绝", "不", "算了"):
            logger.info(f"[/chat] 用户拒绝操作，恢复图执行 | thread={request.thread_id}")
            return await _resume_graph(request.thread_id, approved=False, user_id=current_user.id)

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
            raw = e.args[0] if e.args else {}
            interrupt_value = raw.value if hasattr(raw, 'value') else raw
            if not isinstance(interrupt_value, dict):
                interrupt_value = {}
            preview = interrupt_value.get("preview", "需要您确认一项操作。")
            return await _handle_interrupt(agent_app, config, request.thread_id, preview, start_time)
        
        # ainvoke 正常返回，检查是否有 interrupt 暂停（LangGraph 新版本行为）
        state = await agent_app.aget_state(config)
        if state and state.next:
            logger.debug(f"[/chat] state.next={state.next} | tasks={len(state.tasks) if state.tasks else 0}")
            # 检查是否有待处理的 interrupt
            interrupts = state.tasks[0].interrupts if state.tasks else []
            if interrupts:
                logger.info(f"[/chat] 检测到 interrupt | 数量: {len(interrupts)}")
                raw = interrupts[0]
                interrupt_value = raw.value if hasattr(raw, 'value') else raw
                if not isinstance(interrupt_value, dict):
                    interrupt_value = {}
                preview = interrupt_value.get("preview", "需要您确认一项操作。")
                return await _handle_interrupt(agent_app, config, request.thread_id, preview, start_time)

        # 取最后一条 AI 回复
        reply = result["messages"][-1].content
        elapsed = time.time() - start_time
        logger.info(f"[/chat] 请求完成 | 耗时: {elapsed:.2f}s | 回复长度: {len(reply)}")

        return ChatResponse(reply=reply, thread_id=request.thread_id)

    except TimeoutError as e:
        elapsed = time.time() - start_time
        logger.error(f"[/chat] 超时 | 耗时: {elapsed:.2f}s | {e}")
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception(f"[/chat] 异常 | 耗时: {elapsed:.2f}s | {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误：{str(e)}")


async def _handle_interrupt(agent_app, config, thread_id, preview, start_time) -> ChatResponse:
    """处理 interrupt 暂停：返回预览给用户确认
    
    注意：不在这里修补孤儿 tool_calls，因为修补会修改 checkpoint，
    导致后续 resume 时图状态不正确。孤儿修补由 agent_node 在下次
    发送给 LLM 前自动处理。
    """
    elapsed = time.time() - start_time
    logger.info(f"[/chat] 图执行暂停，等待用户确认 | 耗时: {elapsed:.2f}s | preview: {preview[:100]}")

    return ChatResponse(
        reply=f"{preview}\n\n请回复“确认”批准操作，或回复“取消”拒绝。",
        thread_id=thread_id,
    )


@router.post("/approve/{thread_id}", response_model=ChatResponse)
async def approve(thread_id: str, current_user: User = Depends(get_current_user)):
    """批准被暂停的操作（修改/删除交易）"""
    logger.info(f"[/approve] 用户 {current_user.username} 批准操作 | thread={thread_id}")
    try:
        return await _resume_graph(thread_id, approved=True, user_id=current_user.id)
    except Exception as e:
        logger.exception(f"[/approve] 异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reject/{thread_id}", response_model=ChatResponse)
async def reject(thread_id: str, current_user: User = Depends(get_current_user)):
    """拒绝被暂停的操作（修改/删除交易）"""
    logger.info(f"[/reject] 用户 {current_user.username} 拒绝操作 | thread={thread_id}")
    try:
        return await _resume_graph(thread_id, approved=False, user_id=current_user.id)
    except Exception as e:
        logger.exception(f"[/reject] 异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))
