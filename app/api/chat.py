"""Chat 路由 - POST /chat"""

import base64

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from app.schemas.chat import ChatRequest, ChatResponse
from app.agent.graph import compile_graph
from app.services.ocr_service import recognize_image

router = APIRouter(tags=["chat"])

# MVP 阶段：无 checkpointer（后续加入 PostgresSaver 实现会话记忆）
_agent_app = compile_graph()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """与 AI 记账助手对话

    - 纯文本：直接发送给 Agent 处理
    - 带图片：先 OCR 识别，再将识别结果 + 用户消息一起发给 Agent
    """
    try:
        # 构造用户消息
        user_content = request.message

        # 如果有图片，先 OCR
        if request.image_base64:
            image_bytes = base64.b64decode(request.image_base64)
            ocr_text = await recognize_image(image_bytes)
            user_content = (
                f"[以下是用户上传的订单截图经 OCR 识别出的文字内容]\n"
                f"{ocr_text}\n\n"
                f"[用户说]：{request.message}\n"
                f"请根据以上 OCR 文字提取交易信息（商户、金额、日期、分类），完成记账。"
            )

        # 调用 Agent
        input_state = {
            "messages": [HumanMessage(content=user_content)],
            "current_user_id": "default_user",
        }
        config = {"configurable": {"thread_id": request.thread_id}}

        result = await _agent_app.ainvoke(input_state, config=config)

        # 取最后一条 AI 回复
        reply = result["messages"][-1].content

        return ChatResponse(reply=reply, thread_id=request.thread_id)

    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误：{str(e)}")
