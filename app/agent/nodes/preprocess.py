"""消息组装节点与防幻觉拦截回复"""

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.state import AgentState
from app.logger import get_logger

logger = get_logger(__name__)


async def preprocess_node(state: AgentState) -> dict:
    """把用户输入转成 HumanMessage；OCR 成功时拼入增强上下文

    - 无 OCR 结果（无图片）：直接透传用户文本。
    - 有 OCR 结果：生成含 OCR 上下文的 HumanMessage（结构化字段 + 原用户文本，
      供 agent 直接 add_transactions）。

    返回前清空 user_input，原始输入不进 checkpoint（会话记忆只保存
    处理后的消息）。
    """
    user_input = state.get("user_input", "")
    ocr = state.get("ocr_result")

    if ocr is None:
        return {
            "messages": [HumanMessage(content=user_input)],
            "user_input": None,
        }

    enhanced = (
        f"{ocr.to_agent_text()}\n\n"
        f"[用户说]：{user_input}\n"
        f"请根据以上 OCR 识别结果新增交易记录（调用 add_transactions，一笔或多笔一次传入）。\n"
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


def should_block(state: AgentState) -> str:
    """ocr 节点后路由：OCR 防幻觉拦截是否生效

    返回:
        "blocked" - 进入 respond_blocked 直接回复拦截文案
        "proceed" - 进入 preprocess 正常组装消息
    """
    if state.get("ocr_block"):
        logger.debug("[Router] ocr → blocked")
        return "blocked"
    logger.debug("[Router] ocr → proceed")
    return "proceed"
