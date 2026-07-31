"""图片压缩处理服务"""

import io

from PIL import Image

from app.config import settings


def compress_image(image_bytes: bytes) -> bytes:
    """压缩图片至目标尺寸和大小限制内

    策略：
    1. 将长边缩放至 IMAGE_TARGET_WIDTH (512px)
    2. 以 JPEG 格式输出，从 quality=85 开始逐步降低直到满足 MAX_IMAGE_SIZE_KB

    Args:
        image_bytes: 原始图片二进制数据

    Returns:
        压缩后的图片二进制数据（JPEG）
    """
    img = Image.open(io.BytesIO(image_bytes))

    # 转为 RGB（处理 RGBA/P 模式的 PNG）
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # 等比缩放：长边归一化至目标宽度
    target_width = settings.IMAGE_TARGET_WIDTH
    w, h = img.size
    if max(w, h) > target_width:
        if w >= h:
            new_w = target_width
            new_h = int(h * target_width / w)
        else:
            new_h = target_width
            new_w = int(w * target_width / h)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    # 逐步降低质量直到满足大小限制
    max_bytes = settings.MAX_IMAGE_SIZE_KB * 1024
    quality = 85

    while quality >= 10:
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        if buffer.tell() <= max_bytes:
            return buffer.getvalue()
        quality -= 10

    # 最低质量仍超限，直接返回最低质量结果
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=10, optimize=True)
    return buffer.getvalue()


def image_to_base64(image_bytes: bytes) -> str:
    """将图片字节转为 base64 字符串（供 OCR API 使用）"""
    import base64
    return base64.b64encode(image_bytes).decode("utf-8")
