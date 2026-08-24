"""OCR 识别图节点：图片解码 → 结构化识别 → 防幻觉闸门

作为独立图节点注册（graph: START -> ocr -> ...），LangSmith 追踪树中
可见独立的 ocr 节点 span（节点内 ChatOpenAI 调用再挂一个 qwen3-ocr 子 span），
整图的监控与统计一目了然。
"""

import base64

from langchain_core.runnables import RunnableConfig
from openai import OpenAIError

from app.logger import get_logger
from app.services.ocr_service import recognize_structured

logger = get_logger(__name__)


async def ocr_node(state: dict, config: RunnableConfig) -> dict:
    """OCR 识别节点：把图片转成结构化 OCR 结果，并过防幻觉闸门

    - 无图片：直接放行（ocr_result=None），由 preprocess 透传原文。
    - 有图片：从 config["configurable"]["image_base64"] 读取（图片**不经过
      state**，避免 checkpointer 持久化图片字节——隐私 + 体积），解码 →
      recognize_structured → 防幻觉闸门：
      - 解码失败 / OCR 调用失败 / 识别失败 / 金额不可信 → 写入 ocr_block，
        由路由 should_block 转到 respond_blocked_node 拦截，绝不进入 agent
        （防止 LLM 猜测金额记账）。
      - 识别成功 → 写入 ocr_result（仅结构化小字段，可安全持久化），
        由 preprocess 节点组装增强消息。

    拦截路径清空 user_input；成功路径保留，交由 preprocess 组装。
    """
    image_b64 = (config.get("configurable") or {}).get("image_base64") if config else None

    if not image_b64:
        return {"ocr_result": None}

    logger.info("[OCR] 检测到图片，开始识别...")
    try:
        image_bytes = base64.b64decode(image_b64, validate=True)
    except Exception:
        logger.warning("[OCR] base64 解码失败，拦截")
        return {
            "ocr_block": {"kind": "bad_image", "detail": "图片数据格式错误"},
            "user_input": None,
        }

    try:
        ocr, raw_ocr = await recognize_structured(image_bytes, b64_hint=image_b64)
    except (TimeoutError, OpenAIError) as e:
        logger.exception(f"[OCR] 调用失败: {type(e).__name__}: {e}")
        return {
            "ocr_block": {"kind": "ocr_error", "detail": str(e)},
            "user_input": None,
        }

    logger.info(
        f"[OCR] 识别完成 | recognized={ocr.recognized} | amount={ocr.amount} | unclear={ocr.unclear_fields}"
    )

    # ─── 防幻觉闸门：无法可靠识别就拦截，绝不让 agent 猜金额记账 ───
    if not ocr.recognized:
        reason = ocr.reason or "未识别到可读的文字"
        logger.warning(f"[OCR] 未识别到有效内容，拦截 | reason={reason} | 原始输出: {raw_ocr[:200]}")
        return {
            "ocr_block": {"kind": "no_text", "detail": reason},
            "user_input": None,
        }
    if not ocr.is_bookable():
        logger.warning(f"[OCR] 金额缺失或无效，拦截记账 | 原始输出: {raw_ocr[:200]}")
        return {
            "ocr_block": {"kind": "no_amount", "detail": ""},
            "user_input": None,
        }

    return {"ocr_result": ocr}
