"""Auth 路由 - 注册 & 登录"""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.database import async_session_factory
from app.models.user import User
from app.auth.jwt import hash_password, verify_password, create_access_token
from app.schemas.auth import RegisterRequest, RegisterResponse, LoginRequest, TokenResponse
from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """用户注册"""
    logger.info(f"[/register] 注册请求: username={request.username}")

    async with async_session_factory() as session:
        # 检查用户名是否已存在
        result = await session.execute(
            select(User).where(User.username == request.username)
        )
        if result.scalar_one_or_none() is not None:
            logger.warning(f"[/register] 用户名已存在: {request.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在",
            )

        # 创建新用户
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            username=request.username,
            hashed_password=hash_password(request.password),
        )
        session.add(user)
        await session.commit()

    logger.info(f"[/register] 注册成功: user_id={user_id}, username={request.username}")
    return RegisterResponse(user_id=user_id, username=request.username)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """用户登录，返回 JWT token"""
    logger.info(f"[/login] 登录请求: username={request.username}")

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.username == request.username)
        )
        user = result.scalar_one_or_none()

    if user is None or not verify_password(request.password, user.hashed_password):
        logger.warning(f"[/login] 登录失败: 用户名或密码错误 username={request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    token = create_access_token(subject=user.id)
    logger.info(f"[/login] 登录成功: user_id={user.id}")
    return TokenResponse(access_token=token)
