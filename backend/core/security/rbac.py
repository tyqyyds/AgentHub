from fastapi import HTTPException
from typing import Optional, Dict, List

from ...database.models import User as DBUser


class RBACManager:
    """RBAC权限管理器，仅负责权限映射和检查逻辑。
    
    用户认证统一走 api.deps.get_current_user（数据库JWT认证）。
    本类不涉及认证流程，仅做权限判断。
    """

    def __init__(self):
        self.roles: Dict[str, List[str]] = {
            "admin": ["intents:create", "intents:read", "intents:update", "intents:delete",
                      "events:read", "events:execute", "agents:manage", "audit:read"],
            "operator": ["intents:create", "intents:read", "events:read", "audit:read"],
            "viewer": ["intents:read", "events:read", "audit:read"]
        }

    def get_permissions(self, role: str) -> List[str]:
        """获取指定角色的权限列表"""
        return self.roles.get(role, [])

    def has_permission(self, role: str, permission: str) -> bool:
        """检查指定角色是否拥有某权限"""
        return permission in self.get_permissions(role)

    def require_permission(self, role: str, permission: str):
        """要求指定角色拥有某权限，否则抛出403异常"""
        if not self.has_permission(role, permission):
            raise HTTPException(status_code=403, detail="Insufficient permissions")


rbac_manager = RBACManager()
