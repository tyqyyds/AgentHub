from fastapi import APIRouter, HTTPException, Depends, Response, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict
import re
import os
import time
import logging
from datetime import datetime, timezone
from backend.database.connection import get_db_session
from backend.database.models import User
from backend.core.security.rbac import (
    verify_password, hash_password, create_access_token,
    create_refresh_token, decode_token, get_current_user, requires_permission, rbac_manager
)
from backend.core.security.token_blacklist import token_blacklist
from backend.core.config import settings
from backend.api.response import success_response

router = APIRouter()
logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")

_login_failures: Dict[str, list] = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[str] = Field(None, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip() != "":
            if not _EMAIL_RE.match(v):
                raise ValueError("邮箱格式不正确")
            return v
        return None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_info: dict


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str, expires_in: int):
    secure = settings.environment == "production"
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=expires_in,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/"
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth"
    )


def _clear_auth_cookies(response: Response):
    secure = settings.environment == "production"
    response.delete_cookie(key="access_token", path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie(key="refresh_token", path="/api/v1/auth", secure=secure, httponly=True, samesite="lax")


class UserInfoResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    role: str
    permissions: list
    is_active: bool
    last_login: Optional[datetime]


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, response: Response, db: AsyncSession = Depends(get_db_session)):
    now = time.time()
    failures = _login_failures.get(request.username, [])
    recent_failures = [t for t in failures if now - t < LOCKOUT_DURATION_SECONDS]
    if len(recent_failures) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Account temporarily locked due to too many failed attempts. Try again later.")
    result = await db.execute(select(User).where(User.username == request.username))
    user = result.scalars().first()
    if not user or not verify_password(request.password, user.password_hash):
        _login_failures.setdefault(request.username, []).append(now)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    _login_failures.pop(request.username, None)
    user.last_login = datetime.now(timezone.utc)
    await db.commit()
    token_data = {"sub": user.username, "role": user.role, "user_id": user.id}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    expires_in = settings.access_token_expire_minutes * 60
    _set_auth_cookies(response, access_token, refresh_token, expires_in)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user_info={
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "permissions": rbac_manager.get_permissions(user.role)
        }
    )


@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(User).where(User.username == request.username))
    if result.scalars().first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    if request.email is not None:
        result = await db.execute(select(User).where(User.email == request.email))
        if result.scalars().first():
            raise HTTPException(status_code=409, detail="该邮箱已被注册")
    try:
        user = User(
            username=request.username,
            email=request.email,
            password_hash=hash_password(request.password),
            role="viewer"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="用户名或邮箱已被使用，请更换后重试")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="注册失败，请稍后重试")
    token_data = {"sub": user.username, "role": user.role, "user_id": user.id}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    expires_in = settings.access_token_expire_minutes * 60
    _set_auth_cookies(response, access_token, refresh_token, expires_in)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user_info={
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "permissions": rbac_manager.get_permissions(user.role)
        }
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, response: Response, db: AsyncSession = Depends(get_db_session)):
    body = None
    try:
        body = await request.json()
    except Exception:
        pass
    rt = body.get("refresh_token") if body else None
    if not rt:
        rt = request.cookies.get("refresh_token")
    if not rt:
        raise HTTPException(status_code=401, detail="Refresh token required")
    payload = decode_token(rt)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    jti = payload.get("jti")
    if jti and token_blacklist.is_blacklisted(jti):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")
    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")
    if jti:
        token_blacklist.add(jti, payload.get("exp", 0))
    token_data = {"sub": user.username, "role": user.role, "user_id": user.id}
    access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)
    expires_in = settings.access_token_expire_minutes * 60
    _set_auth_cookies(response, access_token, new_refresh_token, expires_in)
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=expires_in,
        user_info={
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "permissions": rbac_manager.get_permissions(user.role)
        }
    )


@router.get("/me", response_model=UserInfoResponse)
async def get_me(user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(User).where(User.username == user.username))
    db_user = result.scalars().first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserInfoResponse(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        role=db_user.role,
        permissions=rbac_manager.get_permissions(db_user.role),
        is_active=db_user.is_active,
        last_login=db_user.last_login
    )


@router.get("/users")
async def list_users(
    role: Optional[str] = None,
    current_user=Depends(requires_permission("users:manage")),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        query = select(User)
        if role:
            query = query.where(User.role == role)
        result = await db.execute(query.order_by(User.id))
        users = result.scalars().all()
        return success_response(data=[{
            "id": u.id,
            "username": u.username,
            "email": u.email or "",
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        } for u in users])
    except Exception as e:
        logger.error(f"List users failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    email: Optional[str] = None


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    current_user=Depends(requires_permission("users:manage")),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        if body.role is not None:
            if body.role not in ("admin", "operator", "viewer"):
                raise HTTPException(status_code=400, detail="无效的角色")
            user.role = body.role
        if body.is_active is not None:
            user.is_active = body.is_active
        if body.email is not None:
            user.email = body.email
        await db.commit()
        await db.refresh(user)
        return success_response(data={
            "id": user.id,
            "username": user.username,
            "email": user.email or "",
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        })
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Update user failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user=Depends(requires_permission("users:manage")),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        if user.id == current_user.user_id:
            raise HTTPException(status_code=400, detail="不能删除自己")
        await db.delete(user)
        await db.commit()
        return success_response(message="用户已删除")
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Delete user failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/init-admin")
async def init_admin(db: AsyncSession = Depends(get_db_session), current_user=Depends(requires_permission("users:manage"))):
    result = await db.execute(select(User).where(User.username == "admin"))
    if result.scalars().first():
        raise HTTPException(status_code=409, detail="Admin user already exists")
    admin_password = os.environ.get("ADMIN_INITIAL_PASSWORD")
    operator_password = os.environ.get("OPERATOR_INITIAL_PASSWORD")
    viewer_password = os.environ.get("VIEWER_INITIAL_PASSWORD")
    if not admin_password or len(admin_password) < 12:
        raise HTTPException(status_code=500, detail="ADMIN_INITIAL_PASSWORD must be set via environment variable and be at least 12 characters")
    if not operator_password or len(operator_password) < 8:
        raise HTTPException(status_code=500, detail="OPERATOR_INITIAL_PASSWORD must be set via environment variable and be at least 8 characters")
    if not viewer_password or len(viewer_password) < 8:
        raise HTTPException(status_code=500, detail="VIEWER_INITIAL_PASSWORD must be set via environment variable and be at least 8 characters")
    admin = User(
        username="admin",
        email="admin@agenthub.local",
        password_hash=hash_password(admin_password),
        role="admin"
    )
    operator = User(
        username="operator",
        email="operator@agenthub.local",
        password_hash=hash_password(operator_password),
        role="operator"
    )
    viewer = User(
        username="viewer",
        email="viewer@agenthub.local",
        password_hash=hash_password(viewer_password),
        role="viewer"
    )
    db.add_all([admin, operator, viewer])
    await db.commit()
    return {"message": "Default users created", "users": ["admin", "operator", "viewer"]}


@router.post("/logout")
async def logout(request: Request, response: Response):
    access_token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header[7:]
    if not access_token:
        access_token = request.cookies.get("access_token")

    if access_token:
        payload = decode_token(access_token)
        if payload:
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if jti:
                token_blacklist.add(jti, exp)

    refresh_cookie = request.cookies.get("refresh_token")
    if refresh_cookie:
        rt_payload = decode_token(refresh_cookie)
        if rt_payload:
            rt_jti = rt_payload.get("jti")
            rt_exp = rt_payload.get("exp", 0)
            if rt_jti:
                token_blacklist.add(rt_jti, rt_exp)

    _clear_auth_cookies(response)
    return {"status": "success", "message": "Logged out"}
