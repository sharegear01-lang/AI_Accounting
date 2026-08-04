"""Chat 路由 - POST /chat"""

import base64
import time

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphInterrupt

from app.schemas.chat import ChatRequest, ChatResponse
from app.agent.graph import compile_graph
from app.checkpointer import get_checkpointer
from app.services.ocr_service import recognize_image
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])


async def _execute_pending_tool(tool_name: str, tool_args: dict, approved: bool) -> str:
    """手动执行待确认的工具操作

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

    if tool_name == "delete_transaction":
        # 直接执行删除（不再走 interrupt）
        tid = tool_args.get("transaction_id")
        uid = tool_args.get("user_id", "default_user")
        async with async_session_factory() as session:
            stmt = sql_delete(Transaction).where(
                Transaction.id == tid, Transaction.user_id == uid
            )
            await session.execute(stmt)
            await session.commit()
        return f"✅ 交易 #{tid} 已删除。"

    elif tool_name == "update_transaction":
        # 直接执行修改（不再走 interrupt）
        tid = tool_args.get("transaction_id")
        uid = tool_args.get("user_id", "default_user")

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
                Transaction.id == tid, Transaction.user_id == uid
            ).values(**update_values)
            result = await session.execute(stmt)
            await session.commit()

        if result.rowcount == 0:
            return f"❌ 未找到ID为 {tid} 的交易记录。"

        changed = "、".join(f"{k}={v}" for k, v in update_values.items())
        return f"✅ 交易 #{tid} 修改成功（{changed}）。"

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
        config = {"configurable": {"thread_id": request.thread_id}}
        checkpointer = get_checkpointer()
        agent_app = compile_graph(checkpointer=checkpointer)

        # 检查该 thread 是否有待确认的 interrupt
        state = await agent_app.aget_state(config)
        is_pending = state.next == ("tools",) if state and state.next else False

        if is_pending and request.message.strip() in ("确认", "确认。", "好的", "批准", "同意", "ok", "OK"):
            logger.info(f"[/chat] 用户确认操作，恢复图执行 | thread={request.thread_id}")
            return await _resume_graph(request.thread_id, approved=True)
        elif is_pending and request.message.strip() in ("取消", "取消。", "拒绝", "不", "算了"):
            logger.info(f"[/chat] 用户拒绝操作，恢复图执行 | thread={request.thread_id}")
            return await _resume_graph(request.thread_id, approved=False)

        # 构造用户消息
        user_content = request.message

        # 如果有图片，先 OCR
        if request.image_base64:
            logger.info("[/chat] 检测到图片，开始 OCR 识别...")
            image_bytes = base64.b64decode(request.image_base64)
            ocr_text = await recognize_image(image_bytes)
            logger.info(f"[/chat] OCR 完成 | 识别文字长度: {len(ocr_text)}")
            logger.debug(f"[/chat] OCR 结果: {ocr_text[:200]}")
            user_content = (
                f"[以下是用户上传的订单截图经 OCR 识别出的文字内容]\n"
                f"{ocr_text}\n\n"
                f"[用户说]：{request.message}\n"
                f"请根据以上 OCR 文字提取交易信息（商户、金额、日期、分类），完成记账。"
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


async def _resume_graph(thread_id: str, approved: bool) -> ChatResponse:
    """处理 interrupt 暂停后的审批

    不使用 Command(resume=...)（LangGraph resume 行为不稳定），
    而是手动执行/跳过待确认操作，修补 checkpoint，再让 agent 生成回复。
    """
    config = {"configurable": {"thread_id": thread_id}}
    checkpointer = get_checkpointer()
    agent_app = compile_graph(checkpointer=checkpointer)

    # 1. 获取当前状态，找到待执行的 tool_call
    state = await agent_app.aget_state(config)
    messages = state.values.get("messages", []) if state and state.values else []

    pending_tool_call = None
    pending_tool_name = None
    pending_tool_args = {}

    # 从后往前找最后一条带 tool_calls 的 AI 消息
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            pending_tool_call = msg.tool_calls[0]  # 取第一个待确认的
            pending_tool_name = pending_tool_call["name"]
            pending_tool_args = pending_tool_call.get("args", {})
            break

    if not pending_tool_call:
        logger.warning(f"[/resume] 未找到待确认的 tool_call")
        return ChatResponse(reply="⚠️ 没有找到待确认的操作。", thread_id=thread_id)

    tool_call_id = pending_tool_call["id"]
    logger.info(f"[/resume] 待确认操作: {pending_tool_name}({pending_tool_args}) | approved={approved}")

    # 2. 手动执行或跳过工具
    tool_result = await _execute_pending_tool(pending_tool_name, pending_tool_args, approved)
    logger.info(f"[/resume] 工具执行结果: {tool_result[:100]}")

    # 3. 通过 aupdate_state 注入 ToolMessage，修补 checkpoint
    await agent_app.aupdate_state(
        config,
        {"messages": [ToolMessage(content=tool_result, tool_call_id=tool_call_id)]},
    )
    logger.info(f"[/resume] checkpoint 已修补，tool_call_id={tool_call_id}")

    # 直接返回工具结果（agent 下次用户消息时会自动生成总结回复）
    return ChatResponse(reply=tool_result, thread_id=thread_id)


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
        return await _resume_graph(thread_id, approved=True)
    except GraphInterrupt:
        # 可能还有下一个 interrupt（连续多个修改操作）
        return await _resume_graph(thread_id, approved=True)
    except Exception as e:
        logger.exception(f"[/approve] 异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reject/{thread_id}", response_model=ChatResponse)
async def reject(thread_id: str, current_user: User = Depends(get_current_user)):
    """拒绝被暂停的操作（修改/删除交易）"""
    logger.info(f"[/reject] 用户 {current_user.username} 拒绝操作 | thread={thread_id}")
    try:
        return await _resume_graph(thread_id, approved=False)
    except Exception as e:
        logger.exception(f"[/reject] 异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))
