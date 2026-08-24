"""图级预处理节点测试（pytest）

覆盖 preprocess 节点 + 防幻觉闸门 + respond_blocked 节点的全部分支。
OCR 与 LLM 均为 mock，不依赖外部服务与数据库。
"""
import asyncio
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.graph import compile_graph
from app.services.ocr_service import OcrResult


def run(coro):
    return asyncio.run(coro)


class FakeLLM:
    """不调工具的假 LLM"""

    def __init__(self, content="测试回复"):
        self._content = content

    async def ainvoke(self, messages):
        return AIMessage(content=self._content)


def _app(checkpointer=None):
    return compile_graph(checkpointer=checkpointer)


def _ocr(recognized=True, amount="45.00", merchant="星巴克", reason=None):
    return OcrResult(
        recognized=recognized,
        merchant=merchant,
        amount=amount,
        transaction_date="2026-08-17",
        reason=reason,
    )


def _patch_llm():
    return patch("app.agent.nodes.agent._get_llm", return_value=FakeLLM())


async def _invoke(app, input_state, config=None):
    return await app.ainvoke(input_state, config=config)


def _img_config(thread_id="t1", image_b64="aGVsbG8="):
    return {"configurable": {"thread_id": thread_id, "image_base64": image_b64}}


# ─── 1. 纯文本透传 ───────────────────────────────────────────────────────────

def test_text_only_passthrough():
    async def _t():
        with _patch_llm():
            app = _app()
            result = await _invoke(app, {
                "user_input": "今天在星巴克花了 45 元",
                "image_base64": None,
                "current_user_id": "u1",
            })
        msgs = result["messages"]
        assert isinstance(msgs[0], HumanMessage)
        assert msgs[0].content == "今天在星巴克花了 45 元"
        assert msgs[-1].content == "测试回复"

    run(_t())


# ─── 2. OCR 识别成功 → 增强消息进入 agent ─────────────────────────────────────

def test_ocr_success_builds_enhanced_message():
    async def _t():
        with _patch_llm(), patch(
            "app.agent.nodes.ocr.recognize_structured",
            new=AsyncMock(return_value=(_ocr(), '{"店铺名称":"星巴克"}')),
        ):
            app = _app()
            result = await _invoke(app, {
                "user_input": "记一下这笔",
                "current_user_id": "u1",
            }, config=_img_config())
        first = result["messages"][0]
        assert isinstance(first, HumanMessage)
        content = first.content
        assert "[OCR 结构化识别结果]" in content
        assert "商户: 星巴克" in content
        assert "[用户说]：记一下这笔" in content
        assert "金额以 OCR 识别结果为准" in content

    run(_t())


# ─── 3. 未识别到文字 → no_text 拦截 ──────────────────────────────────────────

def test_ocr_no_text_blocked():
    async def _t():
        with _patch_llm(), patch(
            "app.agent.nodes.ocr.recognize_structured",
            new=AsyncMock(return_value=(_ocr(recognized=False, reason="图片中未识别到有效文字"), "raw")),
        ):
            app = _app()
            result = await _invoke(app, {
                "user_input": "记一下",
                "current_user_id": "u1",
            }, config=_img_config())
        reply = result["messages"][-1].content
        assert "无法从这张图片中识别到有效的交易信息" in reply
        assert "图片中未识别到有效文字" in reply
        # 拦截路径不产生 agent 回复
        assert reply != "测试回复"

    run(_t())


# ─── 4. 金额不可信 → no_amount 拦截 ──────────────────────────────────────────

def test_ocr_no_amount_blocked():
    async def _t():
        with _patch_llm(), patch(
            "app.agent.nodes.ocr.recognize_structured",
            new=AsyncMock(return_value=(_ocr(amount=None), "raw")),
        ):
            app = _app()
            result = await _invoke(app, {
                "user_input": "记一下",
                "current_user_id": "u1",
            }, config=_img_config())
        reply = result["messages"][-1].content
        assert "金额" in reply and "无法被可靠识别" in reply
        assert "已取消本次自动记账" in reply

    run(_t())


# ─── 5. base64 非法 → bad_image 拦截 ─────────────────────────────────────────

def test_bad_base64_blocked():
    async def _t():
        with _patch_llm():
            app = _app()
            result = await _invoke(app, {
                "user_input": "记一下",
                "current_user_id": "u1",
            }, config=_img_config(image_b64="!!!not-base64!!!"))
        reply = result["messages"][-1].content
        assert "图片数据格式错误" in reply

    run(_t())


# ─── 6. OCR 服务异常 → ocr_error 拦截（不 500）───────────────────────────────

def test_ocr_timeout_blocked():
    async def _t():
        with _patch_llm(), patch(
            "app.agent.nodes.ocr.recognize_structured",
            new=AsyncMock(side_effect=TimeoutError("OCR 识别超时（>5s）")),
        ):
            app = _app()
            result = await _invoke(app, {
                "user_input": "记一下",
                "current_user_id": "u1",
            }, config=_img_config())
        reply = result["messages"][-1].content
        assert "图片识别暂时失败" in reply

    run(_t())


# ─── 7. 图片字节不进 checkpoint ──────────────────────────────────────────────

def test_image_not_persisted_in_checkpoint():
    async def _t():
        from langgraph.checkpoint.memory import InMemorySaver

        checkpointer = InMemorySaver()
        with _patch_llm(), patch(
            "app.agent.nodes.ocr.recognize_structured",
            new=AsyncMock(return_value=(_ocr(), '{"店铺名称":"星巴克"}')),
        ):
            app = _app(checkpointer=checkpointer)
            config = _img_config()
            await _invoke(app, {
                "user_input": "记一下",
                "current_user_id": "u1",
            }, config=config)
            state = await app.aget_state(config)
        # 图片经 config 传入，绝不进入 checkpoint 的 state
        assert "image_base64" not in state.values, "图片不应作为 state 字段持久化"
        assert state.values.get("user_input") is None, "原始输入不应持久化到 checkpoint"
        # 历史里只有 OCR 增强消息与 agent 回复
        assert all(not isinstance(m, HumanMessage) or "[OCR 结构化识别结果]" in m.content
                   for m in state.values["messages"])

    run(_t())
