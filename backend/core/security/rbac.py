from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from typing import Optional, Dict, List

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class User:
    def __init__(self, username: str, role: str, permissions: List[str]):
        self.username = username
        self.role = role
        self.permissions = permissions

class RBACManager:
    def __init__(self):
        self.roles = {
            "admin": ["intents:create", "intents:read", "intents:update", "intents:delete",
                      "events:read", "events:execute", "agents:manage", "audit:read"],
            "operator": ["intents:create", "intents:read", "events:read", "audit:read"],
            "viewer": ["intents:read", "events:read", "audit:read"]
        }
        
        self.users: Dict[str, User] = {
            "admin": User("admin", "admin", self.roles["admin"]),
            "operator": User("operator", "operator", self.roles["operator"]),
            "viewer": User("viewer", "viewer", self.roles["viewer"])
        }
    
    def get_user(self, username: str) -> Optional[User]:
        return self.users.get(username)
    
    def has_permission(self, username: str, permission: str) -> bool:
        user = self.get_user(username)
        if not user:
            return False
        return permission in user.permissions
    
    def require_permission(self, username: str, permission: str):
        if not self.has_permission(username, permission):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

rbac_manager = RBACManager()

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    user = rbac_manager.get_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

def requires_permission(permission: str):
    async def dependency(user: User = Depends(get_current_user)):
        rbac_manager.require_permission(user.username, permission)
        return user
    return dependency