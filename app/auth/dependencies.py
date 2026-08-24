"""FastAPI 鉴权依赖：从请求头提取并验证 JWT，注入当前用户"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from app.auth.jwt import decode_access_token
from app.database import async_session_factory
from app.logger import get_logger
from app.models.user import User

logger = get_logger(__name__)

# OAuth2 方案：从 Authorization: Bearer <token> 提取
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """从 JWT token 中解析出当前用户

    作为 FastAPI 依赖注入使用，如果 token 无效或用户不存在则抛出 401。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        logger.warning("[Auth] Token 无效或已过期")
        raise credentials_exception

    user_id: str | None = payload.get("sub")
    if user_id is None:
        logger.warning("[Auth] Token 中缺少 sub 字段")
        raise credentials_exception

    # 从数据库查询用户
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if user is None:
        logger.warning(f"[Auth] 用户不存在: user_id={user_id}")
        raise credentials_exception

    logger.debug(f"[Auth] 鉴权成功: user={user.username} (id={user.id})")
    return user
