"""Qwen3-OCR 服务封装 - 通过 Dashscope OpenAI 兼容接口调用"""

import asyncio

from openai import AsyncOpenAI

from app.config import settings
from app.services.image import compress_image, image_to_base64

# Dashscope OpenAI 兼容端点
_dashscope_client = AsyncOpenAI(
    api_key=settings.DASHSCOPE_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

OCR_SYSTEM_PROMPT = (
    "你是一个专业的 OCR 文字提取助手。请从图片中提取所有可见的文字信息，"
    "特别关注：商户名称、金额、交易时间、商品名称等财务相关信息。"
    "请以结构化的方式输出识别到的文字内容。"
)


async def recognize_image(image_bytes: bytes) -> str:
    """对图片进行 OCR 识别，返回提取的文字内容

    流程：
    1. 压缩图片至目标尺寸
    2. 转为 base64
    3. 调用 Qwen3-OCR 模型识别
    4. 设置超时熔断（OCR_TIMEOUT_SECONDS）

    Args:
        image_bytes: 原始图片二进制数据

    Returns:
        OCR 识别出的文字内容

    Raises:
        TimeoutError: OCR 调用超时
        Exception: API 调用失败
    """
    # 1. 压缩图片
    compressed = compress_image(image_bytes)
    b64_data = image_to_base64(compressed)

    # 2. 构造请求
    messages = [
        {"role": "system", "content": OCR_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"},
                },
                {
                    "type": "text",
                    "text": "请识别这张图片中的所有文字信息。",
                },
            ],
        },
    ]

    # 3. 带超时的 API 调用
    try:
        async with asyncio.timeout(settings.OCR_TIMEOUT_SECONDS):
            response = await _dashscope_client.chat.completions.create(
                model=settings.QWEN_OCR_MODEL_NAME,
                messages=messages,
            )
            return response.choices[0].message.content or ""
    except asyncio.TimeoutError:
        raise TimeoutError(
            f"OCR 识别超时（>{settings.OCR_TIMEOUT_SECONDS}s），请手动输入交易信息。"
        )
