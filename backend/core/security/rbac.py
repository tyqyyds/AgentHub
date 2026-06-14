from fastapi import HTTPException, Depends, Request, Response
from fastapi.security import OAuth2PasswordBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt
from typing import Optional, Dict, List
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from backend.core.config import settings
from backend.core.security.token_blacklist import token_blacklist

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

ALGORITHM = "HS256"


class User:
    def __init__(self, username: str, role: str, permissions: List[str], user_id: int = None):
        self.username = username
        self.role = role
        self.permissions = permissions
        self.user_id = user_id


class RBACManager:
    def __init__(self):
        self.roles = {
            "admin": ["intents:create", "intents:read", "intents:update", "intents:delete",
                      "intents:approve", "intents:execute",
                      "events:read", "events:execute", "events:create", "events:rollback",
                      "agents:manage", "audit:read",
                      "users:manage", "system:manage",
                      "workflow:create", "workflow:read", "workflow:manage",
                      "playbook:approve", "playbook:execute", "playbook:create", "playbook:manage",
                      "intent:execute",
                      "llm-router:manage",
                      "grayscale-healing:manage",
                      "webhook:manage",
                      "terraform:manage",
                      "agent:upgrade",
                      "security:manage",
                      "knowledge:version", "knowledge:manage",
                      "notification:manage",
                      "quick-command:manage",
                      "observability:read",
                      "sla:read"],
            "operator": ["intents:create", "intents:read", "intents:update",
                         "intents:execute",
                         "events:read", "events:execute", "audit:read",
                         "workflow:create", "workflow:read",
                         "playbook:execute", "playbook:create", "playbook:read",
                         "intent:execute",
                         "grayscale-healing:manage",
                         "knowledge:version", "knowledge:read",
                         "quick-command:manage",
                         "observability:read",
                         "sla:read",
                         "mcp:read", "validation:read", "scheduler:read",
                         "webhook:manage",
                         "map:read", "telemetry:read"],
            "viewer": ["intents:read", "events:read", "workflow:read",
                       "observability:read", "sla:read",
                       "knowledge:read", "playbook:read",
                       "map:read", "telemetry:read", "mcp:read"]
        }

    def get_permissions(self, role: str) -> List[str]:
        return self.roles.get(role, [])

    def has_permission(self, role: str, permission: str) -> bool:
        return permission in self.get_permissions(role)

    def require_permission(self, role: str, permission: str):
        if not self.has_permission(role, permission):
            raise HTTPException(status_code=403, detail="Insufficient permissions")


rbac_manager = RBACManager()


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire, "type": "access", "jti": uuid4().hex})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh", "jti": uuid4().hex})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def _extract_token_from_request(request: Request, bearer_token: Optional[str] = None) -> Optional[str]:
    if bearer_token:
        return bearer_token
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token
    return None


async def get_current_user(request: Request, token: Optional[str] = Depends(oauth2_scheme)) -> User:
    actual_token = _extract_token_from_request(request, token)
    if actual_token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(actual_token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    jti = payload.get("jti")
    if jti and token_blacklist.is_blacklisted(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")
    username: str = payload.get("sub")
    role: str = payload.get("role", "viewer")
    user_id: int = payload.get("user_id")
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    permissions = rbac_manager.get_permissions(role)
    return User(username=username, role=role, permissions=permissions, user_id=user_id)


def requires_permission(permission: str):
    async def dependency(user: User = Depends(get_current_user)):
        rbac_manager.require_permission(user.role, permission)
        return user
    return dependency
