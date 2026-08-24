"""Qwen3-OCR 服务封装 - 经 LangChain ChatOpenAI 调用 Dashscope OpenAI 兼容接口

与主 Agent（ChatDeepSeek）共用同一套 LangChain 调用栈：调用自动进 LangSmith
追踪，并打上 run_name/tags 标签，方便整图的统一监控与管理。
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.logger import get_logger
from app.services.image import compress_image, image_to_base64

logger = get_logger(__name__)

# ─── LangChain LLM 实例（统一监控入口）──────────────────────────────────────
# 选型说明（对比 langchain_community.ChatTongyi）：
# - ChatTongyi 走 Dashscope 原生 SDK（dashscope.Generation），其多模态模型只声明
#   支持 qwen-vl-*，不含 qwen3.5-ocr；且 async 实为 run_in_executor 线程池包装的
#   伪异步，与 asyncio.timeout 超时熔断配合变扭。
# - ChatOpenAI 走 Dashscope OpenAI 兼容端点（compatible-mode/v1），与线上实测路径
#   一致，视觉 image_url 原生支持，错误类型保持 openai.APIError 体系（上层
#   nodes.py 的 except OpenAIError 无需改动）。
# - 两者都是标准 Runnable，调用自动进 LangSmith 追踪；此处另打 run_name/tags 标签，
#   LangSmith 中与主 Agent 调用一目了然。将来换其他 OpenAI 兼容 OCR 服务商，
#   只需改 DASHSCOPE_BASE_URL + QWEN_OCR_MODEL_NAME，其余代码不动。
_ocr_llm = ChatOpenAI(
    model=settings.QWEN_OCR_MODEL_NAME,
    api_key=settings.DASHSCOPE_API_KEY,
    base_url=settings.DASHSCOPE_BASE_URL,
    # OCR 是转录任务：低温降低采样随机性（qwen3.5-ocr 偶发切回"文本框数组"
    # 模式与随机性有关，temperature=0 可进一步压低该概率）
    temperature=0,
)

# 实测结论（2026-08-14）：
# - qwen3.5-ocr 的默认输出是"文本框数组"（[{"rotate_rect":..., "text":...}]），
#   即使要求键值 JSON 也偶尔会切回该模式（随机）。必须显式禁止，并加重试兜底。
# - 键值模式下它输出 交易金额/店铺名称/交易时间/订单编号 等中文字段，
#   具体键名映射由 parse_ocr_output 兼容处理。
OCR_SYSTEM_PROMPT = """你是一个专业的 OCR 文字提取助手。请从图片中提取所有可见的文字信息，整理成键值对 JSON 输出。

## 输出要求
1. 必须输出 JSON 键值对对象；禁止输出文本框数组（不要输出 rotate_rect/text 列表）。
2. 至少提取以下字段（识别不到就留空字符串，不要编造）：
   - 店铺名称
   - 交易金额
   - 交易时间
   - 订单编号
   - 收货信息
   - 其他文字

## 硬性规则
1. 只转录图片中真实可见的文字；不纠错、不补全、不推断。
2. 金额只转录票面印刷的金额，严禁猜测常见金额；不要自行加总或换算。
3. 某个信息看不清（模糊、遮挡、残缺、不存在）时，对应字段留空字符串。
4. 图片中没有任何可读文字时，输出 {"未识别": "未识别到文字"}。"""


# ─── 结构化解析与防幻觉校验 ───────────────────────────────────────────────────

_CURRENCY_RE = re.compile(r"(CNY|RMB|USD|EUR|JPY|元|块|圆|人民币|美元|¥|￥|\$)")

# 字段键映射：兼容自定义英文 schema 与 qwen3.5-ocr 原生中文 schema
_AMOUNT_TERMS = ("金额", "合计", "总计", "total", "amount")
_MERCHANT_TERMS = ("merchant", "店铺", "商户", "商家", "收款方", "公司")
_DATE_TERMS = ("transaction_date", "交易时间", "下单时间", "支付时间", "日期", "date", "time")
_CURRENCY_TERMS = ("currency", "币种", "货币")
_IGNORE_KEYS = {"recognized", "reason", "items", "unclear_fields", "unclear", "商品明细"}


@dataclass
class OcrResult:
    """OCR 结构化识别结果（供防幻觉闸门与下游 Agent 使用）"""

    recognized: bool = False
    merchant: str | None = None
    amount: str | None = None
    currency: str | None = None
    transaction_date: str | None = None
    items: list[dict] = field(default_factory=list)
    other_text: list[str] = field(default_factory=list)
    unclear_fields: list[str] = field(default_factory=list)
    reason: str | None = None

    @property
    def amount_decimal(self) -> Decimal | None:
        return _parse_amount(self.amount)

    def is_bookable(self) -> bool:
        """是否允许进入记账：必须识别成功且金额有效（金额是记账的硬性字段，猜不得）"""
        return self.recognized and self.amount_decimal is not None

    def to_agent_text(self) -> str:
        """格式化为给记账 Agent 的上下文"""
        amt = self.amount_decimal
        lines = ["[OCR 结构化识别结果]"]
        if self.merchant:
            lines.append(f"商户: {self.merchant}")
        if amt is not None:
            lines.append(f"金额: {amt}")
        if self.currency:
            lines.append(f"币种: {self.currency}")
        if self.transaction_date:
            lines.append(f"交易时间: {self.transaction_date}")
        if self.items:
            lines.append("商品明细:")
            lines += [f"- {it.get('name', '?' )}: {it.get('price', '?')}" for it in self.items if isinstance(it, dict)]
        if self.other_text:
            lines.append("其他识别文字:")
            lines += [f"- {t}" for t in self.other_text]
        if self.unclear_fields:
            lines.append(f"[置信度提示] 以下字段未能清晰识别，需向用户确认: {', '.join(self.unclear_fields)}")
        return "\n".join(lines)


def _clean_str(value) -> str | None:
    """把字段值归一化为非空字符串；null / 占位词一律视为 None"""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "n/a", "na", "unknown", "无", "无法识别"):
        return None
    return s


def _parse_amount(value) -> Decimal | None:
    """把 OCR 金额字符串解析为 Decimal；无法可靠解析返回 None"""
    s = _clean_str(value)
    if not s:
        return None
    # 去货币符号、中文单位、千分位逗号
    s = _CURRENCY_RE.sub("", s).strip().replace(",", "").replace(" ", "")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    if d == 0:
        return None
    return d


def _extract_json(text: str) -> dict:
    """从模型输出中稳健提取 JSON 对象

    容错处理：
    - 剥离 markdown 代码围栏（```json ... ```）
    - 只取第一个 { 到最后一个 } 之间的内容
    - 兼容尾随逗号（模型常见输出错误）
    """
    if not text:
        return {}
    text = text.strip()
    # 剥离代码围栏
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lstrip("`").strip().lower() in ("json", ""):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # 兼容尾随逗号
    cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {}


def _first_value(data: dict, terms: tuple) -> object | None:
    """在 data 中按 key 包含 terms 中任一词，返回首个匹配字段的值"""
    for k, v in data.items():
        kl = str(k).lower()
        if any(t.lower() in kl for t in terms):
            return v
    return None


def _consumed_keys(data: dict, term_sets) -> set:
    """返回 data 中所有被任一术语集合命中的 key（用于避免 other_text 重复）"""
    consumed = set()
    for k in data:
        kl = str(k).lower()
        if any(t.lower() in kl for t in _IGNORE_KEYS):
            consumed.add(k)
            continue
        for terms in term_sets:
            if any(t.lower() in kl for t in terms):
                consumed.add(k)
                break
    return consumed


def _pick_amount(data: dict) -> str | None:
    """从 data 中挑选最像最终金额的值

    优先"实付/实收"类，其次"合计/总计"类，再回退到任意含金额词的字段；
    只有能被 _parse_amount 解析成合法金额才采用。
    """
    candidates = []
    for k, v in data.items():
        kl = str(k).lower()
        if any(t.lower() in kl for t in _AMOUNT_TERMS):
            candidates.append((k, v))
    if not candidates:
        return None

    def _rank(item):
        k = str(item[0])
        if any(t in k for t in ("实付", "实收", "payable", "paid")):
            return 0
        if any(t in k for t in ("合计", "总计", "总额", "total")):
            return 1
        return 2

    candidates.sort(key=_rank)
    for _k, v in candidates:
        if _parse_amount(v) is not None:
            return _clean_str(v)
    return None


def _collect_other(data: dict, consumed: set) -> list[str]:
    """把所有未被识别的字段转成 '键: 值' 文本行，保留原始信息给下游"""
    lines = []
    for k, v in data.items():
        if k in consumed:
            continue
        if isinstance(v, (dict, list)):
            continue
        s = _clean_str(v)
        if s:
            lines.append(f"{k}: {s}")
    return lines


def parse_ocr_output(text: str) -> OcrResult:
    """将模型原始输出解析为 OcrResult

    兼容两种 schema：
    - 自定义英文 schema（recognized/merchant/amount/...）
    - qwen3.5-ocr 原生中文 schema（交易金额/店铺名称/交易时间/...）
    模型未输出可解析的 JSON 时，一律视为"识别结果不可靠"（recognized=False），
    由上层闸门拦截，防止不可靠内容进入记账。
    """
    data = _extract_json(text)
    if not data:
        return OcrResult(recognized=False, reason="OCR 未返回结构化结果，无法校验识别可靠性")

    # recognized 可能是字符串 "false"（模型输出不规范）；原生 schema 无此字段，默认 True
    rec = data.get("recognized", True)
    if isinstance(rec, str):
        rec = rec.strip().lower() == "true"

    if not bool(rec):
        return OcrResult(recognized=False, reason=_clean_str(data.get("reason")) or "图片中未识别到有效文字")

    amount = _pick_amount(data)
    merchant = _first_value(data, _MERCHANT_TERMS)
    txn_date = _first_value(data, _DATE_TERMS)
    currency = _first_value(data, _CURRENCY_TERMS)
    consumed = _consumed_keys(data, (_AMOUNT_TERMS, _MERCHANT_TERMS, _DATE_TERMS, _CURRENCY_TERMS))

    return OcrResult(
        recognized=True,
        merchant=_clean_str(merchant),
        amount=_clean_str(amount),
        currency=_clean_str(currency),
        transaction_date=_clean_str(txn_date),
        items=data.get("items") if isinstance(data.get("items"), list) else [],
        other_text=_collect_other(data, consumed),
        unclear_fields=[],
    )


def is_raw_boxes(text: str) -> bool:
    """判断模型是否返回了文本框数组（rotate_rect 模式），而非键值 JSON"""
    return "rotate_rect" in text


async def recognize_structured(
    image_bytes: bytes, max_attempts: int = 2, b64_hint: str | None = None
) -> tuple["OcrResult", str]:
    """调用 OCR 并解析为 OcrResult，文本框数组模式下自动重试

    实测 qwen3.5-ocr 偶尔会无视提示词、切回原生"文本框数组"输出，
    该模式无法安全提取金额。此处检测到后重试一次（模型随机，第二次
    通常回到键值模式）；仍失败则由上层闸门拦截。

    Args:
        image_bytes: 原始图片二进制数据
        max_attempts: 最大尝试次数
        b64_hint: 前端传来的原始 base64（若可直通则复用，跳过重新压缩/编码）

    Returns:
        (OcrResult, 最后一次模型原始输出)
    """
    result: OcrResult | None = None
    raw = ""
    for attempt in range(1, max_attempts + 1):
        raw = await recognize_image(image_bytes, b64_hint=b64_hint)
        result = parse_ocr_output(raw)
        if result.is_bookable() or not is_raw_boxes(raw) or attempt >= max_attempts:
            break
        logger.warning(f"[OCR] 第 {attempt} 次返回文本框数组（rotate_rect 模式），重试...")
    return result, raw


def _pass_through_b64(image_bytes: bytes) -> bool:
    """判断图片可否 base64 直通 OCR API（跳过重新压缩/编码）

    条件与 compress_image 的快速路径一致：JPEG、长边在像素预算内、
    无 EXIF 旋转。Pillow 懒加载只读头部，不重采样、不重编码。
    """
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        if (img.format or "").upper() != "JPEG":
            return False
        if max(img.size) > settings.IMAGE_TARGET_LONG_EDGE:
            return False
        return img.getexif().get(274, 1) == 1
    except Exception:
        return False


def _content_to_text(content) -> str:
    """把模型回复的 content 归一化为纯文本

    LangChain 回复 content 通常为字符串；多模态回复可能是内容块列表
    （[{"type": "text", "text": ...}, ...]），此处兼容两种形态。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)
    return str(content) if content else ""


# ─── OCR 调用 ─────────────────────────────────────────────────────────────────

async def recognize_image(image_bytes: bytes, b64_hint: str | None = None) -> str:
    """对图片进行 OCR 识别，返回模型原始输出

    流程：
    1. （可选）base64 直通：若图片满足直通条件（JPEG/预算内/无旋转），
       直接复用前端传来的 base64，跳过重新压缩与重新编码。
    2. 否则预处理图片（像素预算缩放 + 格式归一化）后转 base64。
    3. 经 LangChain ChatOpenAI 调用 Qwen3-OCR 模型识别（自动进 LangSmith 追踪）。
    4. 设置超时熔断（OCR_TIMEOUT_SECONDS）。

    Args:
        image_bytes: 原始图片二进制数据
        b64_hint: 前端传来的原始 base64（可直通时复用，避免"解码→再编码"）

    Returns:
        OCR 模型原始输出（通常为 JSON 字符串，需经 parse_ocr_output 解析）

    Raises:
        TimeoutError: OCR 调用超时
        Exception: API 调用失败
    """
    # 1. 决定传输用 base64：优先直通，否则重新压缩/编码
    if b64_hint and _pass_through_b64(image_bytes):
        b64_data = b64_hint.split(",", 1)[-1]  # 兼容可能的 data: 前缀
        mime_type = "image/jpeg"
        logger.info(
            f"[OCR] base64 直通（前端已压缩，跳过重新压缩/编码）| 尺寸: {len(image_bytes) / 1024:.1f} KB"
        )
    else:
        logger.info(f"[OCR] 开始处理 | 原始图片大小: {len(image_bytes) / 1024:.1f} KB")
        compressed, mime_type = compress_image(image_bytes)
        b64_data = image_to_base64(compressed)
        logger.info(f"[OCR] 预处理完成 | 输出格式: {mime_type} | 大小: {len(compressed) / 1024:.1f} KB")

    # 2. 构造 LangChain 消息（多模态内容块：image_url + text）
    messages = [
        SystemMessage(content=OCR_SYSTEM_PROMPT),
        HumanMessage(
            content=[
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                },
                {
                    "type": "text",
                    "text": "请识别这张图片中的所有文字信息。",
                },
            ]
        ),
    ]

    # 3. 带超时的 LangChain 调用（自动进 LangSmith 追踪，run_name/tags 便于整图监控）
    logger.debug(f"[OCR] 调用 Qwen 模型: {settings.QWEN_OCR_MODEL_NAME} | 超时: {settings.OCR_TIMEOUT_SECONDS}s")
    start = time.time()
    try:
        async with asyncio.timeout(settings.OCR_TIMEOUT_SECONDS):
            response = await _ocr_llm.ainvoke(
                messages,
                config={"run_name": "qwen3-ocr", "tags": ["ocr"]},
            )
            result = _content_to_text(response.content)
            elapsed = time.time() - start
            logger.info(f"[OCR] 识别成功 | 耗时: {elapsed:.2f}s | 文字长度: {len(result)}")
            logger.debug(f"[OCR] 识别内容: {result[:300]}")
            return result
    except TimeoutError:
        elapsed = time.time() - start
        logger.exception(f"[OCR] 识别超时 | 耗时: {elapsed:.2f}s | 超时限制: {settings.OCR_TIMEOUT_SECONDS}s")
        raise TimeoutError(
            f"OCR 识别超时（>{settings.OCR_TIMEOUT_SECONDS}s），请手动输入交易信息。"
        ) from None
    except Exception as e:
        elapsed = time.time() - start
        logger.exception(f"[OCR] API 调用失败 | 耗时: {elapsed:.2f}s | {type(e).__name__}: {e}")
        raise


