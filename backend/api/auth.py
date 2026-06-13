from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .deps import get_db_session, get_current_user
from ..database.models import User
from ..core.security.jwt import (
    verify_password, hash_password,
    create_access_token, create_refresh_token, decode_token
)
from pydantic import BaseModel

router = APIRouter()


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


@router.post("/login", response_model=LoginResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    # 检查锁定
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is temporarily locked"
        )

    # 登录成功，重置失败计数
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.commit()

    access_token = create_access_token(data={"sub": user.username, "role": user.role.value})
    refresh_token = create_refresh_token(data={"sub": user.username})

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    refresh_token_body: dict,
    db: AsyncSession = Depends(get_db_session)
):
    token = refresh_token_body.get("refresh_token")
    if not token:
        raise HTTPException(status_code=400, detail="Refresh token required")

    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    new_access = create_access_token(data={"sub": user.username, "role": user.role.value})
    new_refresh = create_refresh_token(data={"sub": user.username})

    return LoginResponse(access_token=new_access, refresh_token=new_refresh)


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserOut(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role.value,
        is_active=current_user.is_active,
    )


