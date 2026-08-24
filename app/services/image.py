"""图片预处理服务"""

import io

from PIL import Image, ImageOps

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


def compress_image(image_bytes: bytes) -> tuple[bytes, str]:
    """对图片做 OCR 前预处理，返回 (图片二进制, MIME 类型)

    策略（准确率与效率平衡）：
    - OCR 延迟主要由视觉模型的输入像素数决定，而非字节数，因此不再做
      "降低质量直到体积达标" 的压榨（那只会损失文字清晰度、省不下延迟）。
    - 像素预算：仅当长边超过 IMAGE_TARGET_LONG_EDGE 时等比缩放，
      否则保持原始尺寸、不做无谓的重编码（快速路径原样返回）。
    - 分格式输出：PNG（数字截图/透明图）走无损，其余转 RGB 后以固定
      质量 JPEG 输出；先纠正 EXIF 旋转。

    Args:
        image_bytes: 原始图片二进制数据

    Returns:
        (预处理后的图片二进制数据, MIME 类型，如 "image/jpeg" / "image/png")
    """
    src = Image.open(io.BytesIO(image_bytes))
    original_format = (src.format or "").upper()
    logger.debug(
        f"[Image] 原始尺寸: {src.size[0]}x{src.size[1]} | 格式: {original_format} | 模式: {src.mode}"
    )

    # 纠正 EXIF 旋转（手机竖拍照片）
    orientation = src.getexif().get(0x0112, 1)
    if orientation != 1:
        img = ImageOps.exif_transpose(src)
        exif_rotated = True
        logger.debug(f"[Image] EXIF 旋转校正: orientation={orientation}")
    else:
        img = src
        exif_rotated = False

    # 像素预算：长边超过上限才缩放
    w, h = img.size
    target = settings.IMAGE_TARGET_LONG_EDGE
    if max(w, h) > target:
        if w >= h:
            new_w = target
            new_h = max(1, int(h * target / w))
        else:
            new_h = target
            new_w = max(1, int(w * target / h))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        logger.debug(f"[Image] 缩放: {w}x{h} → {new_w}x{new_h}")
    elif not exif_rotated and original_format == "JPEG" and img.mode == "RGB":
        # 快速路径：无需缩放/旋转且已是 RGB JPEG → 原样返回，零重编码
        logger.debug(f"[Image] 无需处理，原样返回 ({len(image_bytes) / 1024:.1f} KB)")
        return image_bytes, "image/jpeg"
    else:
        logger.debug("[Image] 像素数在预算内，保持原尺寸")

    # 分格式输出：数字截图/透明图走无损 PNG，其余固定质量 JPEG
    buffer = io.BytesIO()
    if original_format == "PNG" or img.mode in ("RGBA", "LA", "P"):
        img.save(buffer, format="PNG", optimize=True)
        mime = "image/png"
    else:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=settings.JPEG_QUALITY, optimize=True)
        mime = "image/jpeg"

    logger.debug(f"[Image] 处理完成 | 输出: {mime} | 大小: {buffer.tell() / 1024:.1f} KB")
    return buffer.getvalue(), mime


def image_to_base64(image_bytes: bytes) -> str:
    """将图片字节转为 base64 字符串（供 OCR API 使用）"""
    import base64
    return base64.b64encode(image_bytes).decode("utf-8")
