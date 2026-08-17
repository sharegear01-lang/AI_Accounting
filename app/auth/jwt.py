"""JWT 鉴权工具：密码哈希 + Token 生成/验证"""

import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


def _prehash(password: str) -> bytes:
    """SHA-256 预哈希

    bcrypt 有 72 字节长度上限（>=4.x 超限直接抛 ValueError，导致注册 500）。
    先做 SHA-256 预哈希（固定 32 字节），支持任意长度/多字节（如中文）密码。
    """
    return hashlib.sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希（SHA-256 预哈希，无长度限制）"""
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码是否与哈希匹配

    优先验证新格式（SHA-256 预哈希）；不匹配时回退旧格式（<=72 字节直接 bcrypt），
    兼容升级前已存储的旧哈希。旧版本对 >72 字节是静默截断，回退时同样截断比对。
    """
    # 新格式：SHA-256 预哈希后 bcrypt
    if bcrypt.checkpw(_prehash(plain_password), hashed_password.encode("utf-8")):
        return True
    # 旧格式兼容：截断到 72 字节后直接 bcrypt（与旧库行为一致）
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8")
        )
    except ValueError:
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """创建 JWT access token

    Args:
        subject: 用户标识（通常是 user_id）
        expires_delta: 过期时间差，默认使用配置中的 ACCESS_TOKEN_EXPIRE_MINUTES
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"sub": subject, "exp": expire}

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    logger.debug(f"[JWT] Token 已创建 | subject={subject} | 过期={expire.isoformat()}")
    return encoded_jwt


def decode_access_token(token: str) -> dict | None:
    """解码并验证 JWT token

    Returns:
        解析后的 payload dict，如果 token 无效或过期则返回 None
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        logger.debug(f"[JWT] Token 解码成功 | subject={payload.get('sub')}")
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("[JWT] Token 已过期")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"[JWT] Token 无效: {e}")
        return None
