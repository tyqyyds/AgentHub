"""安全Agent - 6层安全防护：Prompt注入防护→意图扫描→沙箱检测→变更窗口→配置回滚→限流"""

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """安全级别"""
    SAFE = "safe"
    WARNING = "warning"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


class ThreatType(Enum):
    """威胁类型"""
    PROMPT_INJECTION = "prompt_injection"
    MALICIOUS_INTENT = "malicious_intent"
    DANGEROUS_COMMAND = "dangerous_command"
    SENSITIVE_OPERATION = "sensitive_operation"
    RATE_LIMITED = "rate_limited"
    OUTSIDE_WINDOW = "outside_window"
    POLICY_VIOLATION = "policy_violation"


@dataclass
class SecurityCheckResult:
    """安全检查结果"""
    level: SecurityLevel
    threat_type: Optional[ThreatType] = None
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    blocked: bool = False
    sanitized_input: Optional[str] = None


@dataclass
class SecurityConfig:
    """安全Agent配置"""
    enable_prompt_injection_detection: bool = True
    enable_sandbox_detection: bool = True
    enable_change_window: bool = True
    enable_rate_limiting: bool = True
    enable_rollback: bool = True
    max_requests_per_minute: int = 60
    max_requests_per_hour: int = 500
    change_window_start: str = "02:00"
    change_window_end: str = "06:00"
    change_window_enabled: bool = False
    sensitive_commands: list[str] = field(default_factory=lambda: [
        "erase", "format", "delete", "reload", "reboot",
        "shutdown", "factory-reset", "restore",
    ])


# Prompt注入检测模式（58种）
PROMPT_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"ignore\s+(previous|above|all|prior)\s+(instructions|prompts|rules)",
        r"forget\s+(everything|all|previous|prior)",
        r"you\s+are\s+now\s+",
        r"pretend\s+(you\s+are|to\s+be)",
        r"act\s+as\s+(if\s+you\s+are|a|an)",
        r"disregard\s+(all|any|previous|safety)",
        r"override\s+(safety|security|previous)",
        r"bypass\s+(security|safety|restrictions|filters)",
        r"system\s*:\s*",
        r"<\|im_start\|>",
        r"\[INST\]",
        r"###\s*Instruction",
        r"jailbreak",
        r"DAN\s+mode",
        r"developer\s+mode",
        r"sudo\s+rm",
        r"rm\s+-rf\s+/",
        r";\s*rm\s+",
        r"\|\s*rm\s+",
        r"\$\(",
        r"`[^`]*`",
        r"\\x[0-9a-fA-F]{2}",
        r"\\u[0-9a-fA-F]{4}",
        r"0x[0-9a-fA-F]+",
        r"eval\s*\(",
        r"exec\s*\(",
        r"subprocess",
        r"os\.system",
        r"import\s+os",
        r"__import__",
        r"__class__",
        r"__subclasses__",
        r"__globals__",
        r"__builtins__",
        r"base64\.b64decode",
        r"pickle\.loads",
        r"yaml\.load\s*\(",
        r"marshal\.loads",
        r"shelve\.open",
        r"webbrowser\.open",
        r"socket\.socket",
        r"requests\.(post|put|delete|patch)",
        r"urllib\.request",
        r"http\.client",
        r"paramiko",
        r"fabric",
        r"ansible",
        r"terraform\s+(apply|destroy)",
        r"kubectl\s+(delete|exec)",
        r"docker\s+(rm|exec|rmi)",
        r"crontab",
        r"nohup",
        r"chmod\s+777",
        r"chown\s+root",
        r"iptables\s+-F",
        r"setenforce\s+0",
        r"systemctl\s+(stop|disable)\s+(firewall|ssh)",
    ]
]

# 危险命令模式（19条）
DANGEROUS_COMMAND_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"erase\s+(flash|startup|running)",
        r"delete\s+(flash|nvram)",
        r"format\s+flash",
        r"reload",
        r"reboot",
        r"shutdown",
        r"factory-reset",
        r"restore\s+default",
        r"no\s+ip\s+routing",
        r"no\s+spanning-tree",
        r"no\s+access-list",
        r"clear\s+(arp|mac|ip\s+route)\s+",
        r"write\s+(erase|memory)",
        r"copy\s+running-config\s+startup-config",
        r"configure\s+replace",
        r"rollback\s+running-config",
        r"issu\s+(abort|changeversion)",
        r"license\s+(reset|install\s+boot)",
        r"boot\s+system\s+",
    ]
]

# 恶意意图模式（31条）
MALICIOUS_INTENT_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"删除\s*(所有|全部)\s*(配置|数据|文件)",
        r"清空\s*(设备|路由|ARP)",
        r"关闭\s*(防火墙|安全|认证)",
        r"绕过\s*(安全|认证|授权)",
        r"提权|提权|root\s*权限",
        r"后门|木马|病毒",
        r"嗅探|抓包|监听",
        r"攻击|入侵|渗透",
        r"DDoS|拒绝服务",
        r"暴力破解|字典攻击",
        r"SQL\s*注入",
        r"XSS|跨站脚本",
        r"CSRF|跨站请求",
        r"中间人攻击",
        r"ARP\s*欺骗",
        r"DNS\s*劫持",
        r"端口扫描",
        r"漏洞利用",
        r"提权漏洞",
        r"零日漏洞",
        r"社工攻击",
        r"钓鱼攻击",
        r"勒索软件",
        r"挖矿程序",
        r"僵尸网络",
        r"远程控制",
        r"数据泄露",
        r"隐私窃取",
        r"密钥窃取",
        r"证书伪造",
        r"身份冒充",
    ]
]


class SecurityAgent:
    """安全Agent - 6层安全防护"""

    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or SecurityConfig()
        self._rate_limit_tracker: dict[str, list[float]] = {}
        self._rollback_snapshots: dict[str, dict[str, Any]] = {}
        self._stats: dict[str, int] = {
            "total_checks": 0,
            "prompt_injections_blocked": 0,
            "dangerous_commands_blocked": 0,
            "malicious_intents_blocked": 0,
            "rate_limits_triggered": 0,
            "change_window_violations": 0,
            "rollbacks_performed": 0,
        }
        logger.info(f"安全Agent初始化完成, 注入模式: {settings.prompt_injection_patterns_count}种, 沙箱命令: {settings.sandbox_dangerous_commands}条")

    def check_prompt_injection(self, user_input: str) -> SecurityCheckResult:
        """第1层：Prompt注入防护"""
        if not self.config.enable_prompt_injection_detection:
            return SecurityCheckResult(level=SecurityLevel.SAFE)

        detected_patterns = []
        for i, pattern in enumerate(PROMPT_INJECTION_PATTERNS):
            if pattern.search(user_input):
                detected_patterns.append(f"pattern_{i+1}")

        if detected_patterns:
            self._stats["prompt_injections_blocked"] += 1
            logger.warning(f"Prompt注入检测: 发现 {len(detected_patterns)} 个匹配模式")
            return SecurityCheckResult(
                level=SecurityLevel.BLOCKED,
                threat_type=ThreatType.PROMPT_INJECTION,
                message=f"检测到Prompt注入攻击，匹配 {len(detected_patterns)} 个模式",
                details={"patterns": detected_patterns},
                blocked=True,
            )

        return SecurityCheckResult(level=SecurityLevel.SAFE)

    def check_intent_safety(self, intent: dict[str, Any]) -> SecurityCheckResult:
        """第2层：意图安全扫描"""
        intent_str = str(intent)
        for pattern in MALICIOUS_INTENT_PATTERNS:
            if pattern.search(intent_str):
                self._stats["malicious_intents_blocked"] += 1
                return SecurityCheckResult(
                    level=SecurityLevel.BLOCKED,
                    threat_type=ThreatType.MALICIOUS_INTENT,
                    message="检测到恶意意图",
                    details={"intent": intent},
                    blocked=True,
                )

        intent_type = intent.get("intent_type", "")
        high_risk_types = ["delete_config", "reset_device", "shutdown_interface"]
        if intent_type in high_risk_types:
            return SecurityCheckResult(
                level=SecurityLevel.WARNING,
                threat_type=ThreatType.SENSITIVE_OPERATION,
                message=f"敏感操作: {intent_type}",
                details={"intent": intent},
                requires_approval=True,
            )

        return SecurityCheckResult(level=SecurityLevel.SAFE)

    def check_sandbox(self, commands: list[str]) -> SecurityCheckResult:
        """第3层：沙箱检测"""
        if not self.config.enable_sandbox_detection:
            return SecurityCheckResult(level=SecurityLevel.SAFE)

        dangerous_found = []
        for cmd in commands:
            for pattern in DANGEROUS_COMMAND_PATTERNS:
                if pattern.search(cmd):
                    dangerous_found.append(cmd)
                    break
            for sensitive in self.config.sensitive_commands:
                if sensitive.lower() in cmd.lower():
                    dangerous_found.append(cmd)
                    break

        if dangerous_found:
            self._stats["dangerous_commands_blocked"] += 1
            return SecurityCheckResult(
                level=SecurityLevel.DANGEROUS,
                threat_type=ThreatType.DANGEROUS_COMMAND,
                message=f"检测到 {len(dangerous_found)} 条危险命令",
                details={"dangerous_commands": dangerous_found},
                requires_approval=True,
            )

        return SecurityCheckResult(level=SecurityLevel.SAFE)

    def check_change_window(self) -> SecurityCheckResult:
        """第4层：变更窗口检查"""
        if not self.config.enable_change_window:
            return SecurityCheckResult(level=SecurityLevel.SAFE)

        now = time.localtime()
        current_time = f"{now.tm_hour:02d}:{now.tm_min:02d}"

        start = self.config.change_window_start
        end = self.config.change_window_end

        if start <= current_time <= end:
            return SecurityCheckResult(level=SecurityLevel.SAFE)

        self._stats["change_window_violations"] += 1
        return SecurityCheckResult(
            level=SecurityLevel.WARNING,
            threat_type=ThreatType.OUTSIDE_WINDOW,
            message=f"当前不在变更窗口内 ({start}-{end})",
            details={"current_time": current_time, "window": f"{start}-{end}"},
            requires_approval=True,
        )

    def save_snapshot(self, device_id: str, config_data: dict[str, Any]):
        """第5层：保存配置快照用于回滚"""
        if not self.config.enable_rollback:
            return
        self._rollback_snapshots[device_id] = {
            "config": config_data,
            "timestamp": time.time(),
        }
        logger.info(f"配置快照已保存: {device_id}")

    def get_snapshot(self, device_id: str) -> Optional[dict[str, Any]]:
        """获取配置快照"""
        snapshot = self._rollback_snapshots.get(device_id)
        if snapshot:
            return snapshot.get("config")
        return None

    def check_rate_limit(self, user_id: str) -> SecurityCheckResult:
        """第6层：限流检查"""
        if not self.config.enable_rate_limiting:
            return SecurityCheckResult(level=SecurityLevel.SAFE)

        now = time.time()
        if user_id not in self._rate_limit_tracker:
            self._rate_limit_tracker[user_id] = []

        timestamps = self._rate_limit_tracker[user_id]
        timestamps.append(now)

        timestamps[:] = [t for t in timestamps if now - t < 3600]
        self._rate_limit_tracker[user_id] = timestamps

        recent_minute = [t for t in timestamps if now - t < 60]
        if len(recent_minute) > self.config.max_requests_per_minute:
            self._stats["rate_limits_triggered"] += 1
            return SecurityCheckResult(
                level=SecurityLevel.BLOCKED,
                threat_type=ThreatType.RATE_LIMITED,
                message=f"触发分钟限流 ({len(recent_minute)}/{self.config.max_requests_per_minute})",
                blocked=True,
            )

        if len(timestamps) > self.config.max_requests_per_hour:
            self._stats["rate_limits_triggered"] += 1
            return SecurityCheckResult(
                level=SecurityLevel.BLOCKED,
                threat_type=ThreatType.RATE_LIMITED,
                message=f"触发小时限流 ({len(timestamps)}/{self.config.max_requests_per_hour})",
                blocked=True,
            )

        return SecurityCheckResult(level=SecurityLevel.SAFE)

    def full_security_check(
        self,
        user_input: str,
        intent: Optional[dict] = None,
        commands: Optional[list] = None,
        user_id: str = "default",
    ) -> SecurityCheckResult:
        """完整6层安全检查"""
        self._stats["total_checks"] += 1

        result = self.check_prompt_injection(user_input)
        if result.blocked:
            return result

        result = self.check_rate_limit(user_id)
        if result.blocked:
            return result

        if intent:
            result = self.check_intent_safety(intent)
            if result.blocked:
                return result

        if commands:
            result = self.check_sandbox(commands)
            if result.blocked:
                return result

        result = self.check_change_window()
        return result

    def get_stats(self) -> dict[str, Any]:
        """获取安全统计"""
        return self._stats

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Agent标准处理接口"""
        action = input_data.get("action", "full_check")

        if action == "full_check":
            result = self.full_security_check(
                user_input=input_data.get("user_input", ""),
                intent=input_data.get("intent"),
                commands=input_data.get("commands"),
                user_id=input_data.get("user_id", "default"),
            )
            return {
                "action": "full_check",
                "level": result.level.value,
                "threat_type": result.threat_type.value if result.threat_type else None,
                "message": result.message,
                "requires_approval": result.requires_approval,
                "blocked": result.blocked,
            }

        elif action == "prompt_injection_check":
            result = self.check_prompt_injection(input_data.get("user_input", ""))
            return {"action": "prompt_injection_check", "level": result.level.value, "blocked": result.blocked}

        elif action == "sandbox_check":
            result = self.check_sandbox(input_data.get("commands", []))
            return {"action": "sandbox_check", "level": result.level.value, "requires_approval": result.requires_approval}

        elif action == "save_snapshot":
            self.save_snapshot(input_data.get("device_id", ""), input_data.get("config_data", {}))
            return {"action": "save_snapshot", "success": True}

        elif action == "get_snapshot":
            config = self.get_snapshot(input_data.get("device_id", ""))
            return {"action": "get_snapshot", "config": config}

        else:
            return {"action": action, "error": "未知操作"}

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "patterns_loaded": {
                "prompt_injection": len(PROMPT_INJECTION_PATTERNS),
                "dangerous_commands": len(DANGEROUS_COMMAND_PATTERNS),
                "malicious_intents": len(MALICIOUS_INTENT_PATTERNS),
            },
            "snapshots_stored": len(self._rollback_snapshots),
            "stats": self._stats,
        }
