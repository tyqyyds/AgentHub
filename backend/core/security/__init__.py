from .rbac import rbac_manager, RBACManager
from .rate_limiter import rate_limiter, RateLimiter
from .prompt_guard import prompt_guard, PromptInjectionGuard
from .change_window import change_window_manager, ChangeWindowManager

# 第2层：意图安全扫描 & 第3层：沙箱检测 & 第5层：配置回滚
# 实际实现在 agents/security.py，此处重新导出以保持6层安全架构的统一入口
from ...agents.security import (
    SecurityAgent,
    SecurityConfig,
    SecurityCheckResult,
    SecurityLevel,
    ThreatType,
    PROMPT_INJECTION_PATTERNS,
    DANGEROUS_COMMAND_PATTERNS,
    MALICIOUS_INTENT_PATTERNS,
)

# 意图扫描器：第2层安全防护，从SecurityAgent中提取意图扫描能力
class IntentScanner:
    """意图安全扫描器 - 第2层：SQL/Shell/路径遍历检测"""

    def __init__(self):
        self._agent = SecurityAgent()

    def scan(self, intent: dict) -> SecurityCheckResult:
        """扫描意图安全性"""
        return self._agent.check_intent_safety(intent)

    def is_safe(self, intent: dict) -> bool:
        """判断意图是否安全"""
        result = self.scan(intent)
        return not result.blocked


# 配置回滚管理器：第5层安全防护
class ConfigRollbackManager:
    """配置回滚管理器 - 第5层：自动备份/回滚"""

    def __init__(self):
        self._agent = SecurityAgent()

    def save_snapshot(self, device_id: str, config_data: dict):
        """保存配置快照"""
        self._agent.save_snapshot(device_id, config_data)

    def get_snapshot(self, device_id: str):
        """获取配置快照"""
        return self._agent.get_snapshot(device_id)

    def has_snapshot(self, device_id: str) -> bool:
        """是否存在快照"""
        return device_id in self._agent._rollback_snapshots


intent_scanner = IntentScanner()
config_rollback_manager = ConfigRollbackManager()

__all__ = [
    # 第1层：Prompt注入防护
    "prompt_guard",
    "PromptInjectionGuard",
    # 第2层：意图安全扫描
    "intent_scanner",
    "IntentScanner",
    # 第3层：沙箱检测（通过SecurityAgent）
    "SecurityAgent",
    "DANGEROUS_COMMAND_PATTERNS",
    "MALICIOUS_INTENT_PATTERNS",
    # 第4层：变更窗口管理
    "change_window_manager",
    "ChangeWindowManager",
    # 第5层：配置回滚
    "config_rollback_manager",
    "ConfigRollbackManager",
    # 第6层：速率限制
    "rate_limiter",
    "RateLimiter",
    # RBAC权限
    "rbac_manager",
    "RBACManager",
    # 通用
    "SecurityConfig",
    "SecurityCheckResult",
    "SecurityLevel",
    "ThreatType",
    "PROMPT_INJECTION_PATTERNS",
]
