"""Chat 路由 - POST /chat"""

import base64
import time

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphInterrupt

from app.schemas.chat import ChatRequest, ChatResponse
from app.agent.graph import compile_graph
from app.checkpointer import get_checkpointer
from app.services.ocr_service import recognize_structured
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])


def _thread_config(user_id: str, thread_id: str) -> dict:
    """按用户命名空间隔离会话线程，防止跨用户访问对话记忆

    checkpointer 以 thread_id 为 key，若不含用户维度，A 用户复用 B 的
    thread_id 即可读到/续接 B 的对话。这里统一加用户前缀命名空间。
    """
    return {"configurable": {"thread_id": f"{user_id}:{thread_id}"}}


async def _execute_pending_tool(
    tool_name: str, tool_args: dict, approved: bool, user_id: str
) -> str:
    """手动执行待确认的工具操作（单个或批量）

    直接操作数据库，绕过 interrupt 机制。
    """
    from datetime import date
    from decimal import Decimal

    from sqlalchemy import delete as sql_delete
    from sqlalchemy import select, update as sql_update

    from app.database import async_session_factory
    from app.models.transaction import Transaction

    if not approved:
        return "❌ 用户拒绝了此操作。"

    # 解析目标 ID 列表（兼容单个与批量工具）
    if tool_name in ("delete_transaction", "update_transaction"):
        ids = [int(tool_args.get("transaction_id"))] if tool_args.get("transaction_id") else []
    else:
        ids = [int(i) for i in (tool_args.get("transaction_ids") or [])]
    ids = list(dict.fromkeys(ids))

    if not ids:
        return "❌ 未提供交易记录ID。"

    if tool_name in ("delete_transaction", "delete_transactions"):
        # 直接执行删除（不再走 interrupt）
        async with async_session_factory() as session:
            stmt = sql_delete(Transaction).where(
                Transaction.id.in_(ids), Transaction.user_id == user_id
            )
            result = await session.execute(stmt)
            await session.commit()
        if result.rowcount == 0:
            return "❌ 未找到匹配的交易记录。"
        return f"✅ 已删除 {result.rowcount} 笔交易记录。"

    elif tool_name in ("update_transaction", "update_transactions"):
        # 直接执行修改（不再走 interrupt）
        update_values = {}
        if tool_args.get("merchant"):
            update_values["merchant"] = tool_args["merchant"]
        if tool_args.get("amount"):
            update_values["amount"] = Decimal(str(tool_args["amount"]))
        if tool_args.get("transaction_date"):
            try:
                update_values["transaction_date"] = date.fromisoformat(tool_args["transaction_date"])
            except ValueError:
                return f"❌ 日期格式错误：'{tool_args['transaction_date']}'"
        if tool_args.get("category"):
            update_values["category"] = tool_args["category"]
        if tool_args.get("description"):
            update_values["description"] = tool_args["description"]

        if not update_values:
            return "⚠️ 没有需要修改的字段。"

        async with async_session_factory() as session:
            stmt = sql_update(Transaction).where(
                Transaction.id.in_(ids), Transaction.user_id == user_id
            ).values(**update_values)
            result = await session.execute(stmt)
            await session.commit()

        if result.rowcount == 0:
            return "❌ 未找到匹配的交易记录。"

        changed = "、".join(f"{k}={v}" for k, v in update_values.items())
        return f"✅ 已修改 {result.rowcount} 笔交易记录（{changed}）。"

    return f"❌ 未知工具: {tool_name}"


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

        # 构造用户消息
        user_content = request.message

        # 如果有图片，先 OCR
        if request.image_base64:
            logger.info("[/chat] 检测到图片，开始 OCR 识别...")
            # 先做粗略长度预检，避免超大 base64 直接解码占用内存
            if len(request.image_base64) > settings.MAX_UPLOAD_BYTES * 4 // 3 + 8:
                raise HTTPException(status_code=400, detail="图片过大，请压缩后重新上传")
            try:
                image_bytes = base64.b64decode(request.image_base64, validate=True)
            except Exception:
                raise HTTPException(status_code=400, detail="图片数据格式错误，请重新上传")

            # OCR 识别 + 结构化解析（文本框数组模式会自动重试）
            ocr, raw_ocr = await recognize_structured(image_bytes)
            logger.info(f"[/chat] OCR 完成 | recognized={ocr.recognized} | amount={ocr.amount} | unclear={ocr.unclear_fields}")

            # ─── 防幻觉闸门：无法可靠识别就拦截，绝不让 agent 猜金额记账 ───
            if not ocr.recognized:
                reason = ocr.reason or "未识别到可读的文字"
                logger.warning(f"[/chat] OCR 未识别到有效内容，拦截 | reason={reason} | 原始输出: {raw_ocr[:200]}")
                return ChatResponse(
                    reply=(
                        f"❌ 无法从这张图片中识别到有效的交易信息（{reason}）。\n\n"
                        "建议：重新拍摄，保证单据正对镜头、光线充足、文字清晰；"
                        "也可以直接手动输入交易信息。"
                    ),
                    thread_id=request.thread_id,
                )
            if not ocr.is_bookable():
                logger.warning(f"[/chat] OCR 金额缺失或无效，拦截记账 | 原始输出: {raw_ocr[:200]}")
                return ChatResponse(
                    reply=(
                        "❌ 图片中的**金额**无法被可靠识别（模糊、缺失或格式异常）。"
                        "为避免记错账，已取消本次自动记账。\n\n"
                        "请重新拍摄金额区域清晰的图片，或直接手动输入交易信息。"
                    ),
                    thread_id=request.thread_id,
                )

            user_content = (
                f"{ocr.to_agent_text()}\n\n"
                f"[用户说]：{request.message}\n"
                f"请根据以上 OCR 识别结果新增一笔交易记录（调用 add_transaction）。\n"
                f"金额以 OCR 识别结果为准（{ocr.amount}），不可改、不可四舍五入、不可猜测；"
                f"若置信度提示中列出未识别字段，先向用户确认后再记账，不得臆测。"
            )

        # 调用 Agent
        input_state = {
            "messages": [HumanMessage(content=user_content)],
            "current_user_id": current_user.id,
        }

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


async def _resume_graph(thread_id: str, approved: bool, user_id: str) -> ChatResponse:
    """处理 interrupt 暂停后的审批（单个或批量）

    不使用 Command(resume=...)（LangGraph resume 行为不稳定），
    而是手动执行/跳过待确认操作，修补 checkpoint，再让 agent 生成回复。
    """
    config = _thread_config(user_id, thread_id)
    checkpointer = get_checkpointer()
    agent_app = compile_graph(checkpointer=checkpointer)

    # 1. 获取当前状态，找到待执行的 tool_call
    state = await agent_app.aget_state(config)
    messages = state.values.get("messages", []) if state and state.values else []

    # 从后往前找最后一条带 tool_calls 的 AI 消息，取出其全部待确认调用
    pending_calls = []
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            pending_calls = msg.tool_calls
            break

    if not pending_calls:
        logger.warning(f"[/resume] 未找到待确认的 tool_call")
        return ChatResponse(reply="⚠️ 没有找到待确认的操作。", thread_id=thread_id)

    # 跳过已执行的调用（tools_node 在 interrupt 前已完成的部分，如同一消息里的 add_transaction），
    # 避免重复执行造成重复记账
    executed_ids = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}

    results: list[tuple[str, str]] = []
    for tc in pending_calls:
        tool_call_id = tc["id"]
        if tool_call_id in executed_ids:
            logger.info(f"[/resume] 跳过已执行的 tool_call: {tc['name']}({tool_call_id})")
            continue
        tool_name = tc["name"]
        tool_args = tc.get("args", {}) or {}
        logger.info(f"[/resume] 待确认操作: {tool_name}({tool_args}) | approved={approved}")
        tool_result = await _execute_pending_tool(tool_name, tool_args, approved, user_id)
        logger.info(f"[/resume] 工具执行结果: {tool_result[:100]}")
        results.append((tool_call_id, tool_result))

    if not results:
        return ChatResponse(reply="⚠️ 所有待确认的操作都已被处理。", thread_id=thread_id)

    # 3. 通过 aupdate_state 注入所有 ToolMessage，修补 checkpoint
    await agent_app.aupdate_state(
        config,
        {"messages": [ToolMessage(content=res, tool_call_id=tid) for tid, res in results]},
    )
    logger.info(f"[/resume] checkpoint 已修补，tool_call_ids={[tid for tid, _ in results]}")

    # 直接返回工具结果（agent 下次用户消息时会自动生成总结回复）
    reply = "\n\n".join(res for _, res in results)
    return ChatResponse(reply=reply, thread_id=thread_id)


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
    except GraphInterrupt:
        # 可能还有下一个 interrupt（连续多个修改操作）
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
