"""主动通知Agent - 设备告警/任务完成等主动推送"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..core.config import settings
from ..database.models import NotificationPriority

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """通知类型"""
    DEVICE_ALARM = "device_alarm"           # 设备告警
    TASK_COMPLETED = "task_completed"       # 任务完成
    TASK_FAILED = "task_failed"             # 任务失败
    APPROVAL_REQUIRED = "approval_required" # 需要审批
    CONFIG_CHANGED = "config_changed"       # 配置变更
    HEALING_TRIGGERED = "healing_triggered" # 自愈触发
    SCHEDULE_REMINDER = "schedule_reminder" # 计划提醒
    SYSTEM_ALERT = "system_alert"           # 系统告警
    AGENT_STATUS = "agent_status"           # Agent状态变更


class NotificationChannel(Enum):
    """通知渠道"""
    WEBSOCKET = "websocket"
    WEBHOOK = "webhook"
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"


@dataclass
class NotificationRule:
    """通知规则"""
    rule_id: str
    event_type: str
    channels: list[NotificationChannel]
    priority_filter: list[NotificationPriority] = field(
        default_factory=lambda: [NotificationPriority.HIGH, NotificationPriority.URGENT]
    )
    cooldown_seconds: int = 300  # 同类通知冷却时间
    max_per_hour: int = 20
    enabled: bool = True


@dataclass
class Notification:
    """通知消息"""
    notification_id: str
    notification_type: NotificationType
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.MEDIUM
    target_users: list[int] = field(default_factory=list)
    channels: list[NotificationChannel] = field(default_factory=lambda: [NotificationChannel.WEBSOCKET])
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None


@dataclass
class ProactiveNotifierConfig:
    """主动通知Agent配置"""
    default_channels: list[NotificationChannel] = field(
        default_factory=lambda: [NotificationChannel.WEBSOCKET, NotificationChannel.IN_APP]
    )
    default_cooldown_seconds: int = 300
    max_notifications_per_hour: int = 50
    enable_deduplication: bool = True
    enable_priority_escalation: bool = True
    escalation_delay_minutes: int = 15
    ws_max_connections: int = 1000


# 默认通知规则
DEFAULT_RULES: list[NotificationRule] = [
    NotificationRule(
        rule_id="rule_alarm",
        event_type="device_alarm",
        channels=[NotificationChannel.WEBSOCKET, NotificationChannel.IN_APP],
        priority_filter=[NotificationPriority.HIGH, NotificationPriority.URGENT],
        cooldown_seconds=60,
    ),
    NotificationRule(
        rule_id="rule_task_done",
        event_type="task_completed",
        channels=[NotificationChannel.WEBSOCKET, NotificationChannel.IN_APP],
        priority_filter=[NotificationPriority.LOW, NotificationPriority.MEDIUM, NotificationPriority.HIGH],
        cooldown_seconds=0,
    ),
    NotificationRule(
        rule_id="rule_approval",
        event_type="approval_required",
        channels=[NotificationChannel.WEBSOCKET, NotificationChannel.EMAIL],
        priority_filter=[NotificationPriority.HIGH, NotificationPriority.URGENT],
        cooldown_seconds=0,
    ),
    NotificationRule(
        rule_id="rule_healing",
        event_type="healing_triggered",
        channels=[NotificationChannel.WEBSOCKET, NotificationChannel.IN_APP],
        priority_filter=[NotificationPriority.MEDIUM, NotificationPriority.HIGH, NotificationPriority.URGENT],
        cooldown_seconds=120,
    ),
]


class ProactiveNotifier:
    """主动通知Agent - 设备告警/任务完成等主动推送"""

    def __init__(self, config: Optional[ProactiveNotifierConfig] = None):
        self.config = config or ProactiveNotifierConfig()
        self._rules: dict[str, NotificationRule] = {r.rule_id: r for r in DEFAULT_RULES}
        self._pending: list[Notification] = []
        self._sent_history: list[dict[str, Any]] = []
        self._cooldown_tracker: dict[str, float] = {}  # event_key -> last_sent_time
        self._hourly_counts: dict[str, int] = {}  # rule_id -> count
        self._hourly_reset_time: float = time.time()
        self._ws_connections: dict[int, Any] = {}  # user_id -> connection
        self._notification_counter: int = 0
        self._stats: dict[str, int] = {
            "total_sent": 0,
            "total_suppressed": 0,
            "device_alarm_sent": 0,
            "task_completed_sent": 0,
            "approval_required_sent": 0,
            "healing_triggered_sent": 0,
            "dedup_suppressed": 0,
            "cooldown_suppressed": 0,
            "rate_limited": 0,
        }
        logger.info("主动通知Agent初始化完成")

    def _generate_notification_id(self) -> str:
        """生成通知ID"""
        self._notification_counter += 1
        return f"notif_{int(time.time())}_{self._notification_counter}"

    def _reset_hourly_counts_if_needed(self) -> None:
        """每小时重置计数"""
        if time.time() - self._hourly_reset_time >= 3600:
            self._hourly_counts.clear()
            self._hourly_reset_time = time.time()

    def _is_cooled_down(self, event_key: str, cooldown_seconds: int) -> bool:
        """检查冷却时间"""
        last_sent = self._cooldown_tracker.get(event_key, 0)
        if time.time() - last_sent < cooldown_seconds:
            return False
        return True

    def _is_rate_limited(self, rule_id: str) -> bool:
        """检查频率限制"""
        self._reset_hourly_counts_if_needed()
        rule = self._rules.get(rule_id)
        max_per_hour = rule.max_per_hour if rule else self.config.max_notifications_per_hour
        return self._hourly_counts.get(rule_id, 0) >= max_per_hour

    def _is_duplicate(self, notification: Notification) -> bool:
        """检查重复通知"""
        if not self.config.enable_deduplication:
            return False
        for sent in self._sent_history[-20:]:
            if (sent.get("type") == notification.notification_type.value
                    and sent.get("title") == notification.title
                    and time.time() - sent.get("sent_at", 0) < 60):
                return True
        return False

    def _match_rule(self, event_type: str, priority: NotificationPriority) -> Optional[NotificationRule]:
        """匹配通知规则"""
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            if rule.event_type != event_type:
                continue
            if priority in rule.priority_filter:
                return rule
        return None

    def _build_notification(
        self,
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        metadata: Optional[dict] = None,
    ) -> Notification:
        """构建通知对象"""
        return Notification(
            notification_id=self._generate_notification_id(),
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            channels=self.config.default_channels,
            metadata=metadata or {},
        )

    def notify_device_alarm(
        self,
        device_name: str,
        alarm_type: str,
        description: str,
        severity: str = "high",
    ) -> dict[str, Any]:
        """设备告警通知"""
        priority_map = {
            "critical": NotificationPriority.URGENT,
            "high": NotificationPriority.HIGH,
            "medium": NotificationPriority.MEDIUM,
            "low": NotificationPriority.LOW,
        }
        priority = priority_map.get(severity, NotificationPriority.MEDIUM)

        notification = self._build_notification(
            notification_type=NotificationType.DEVICE_ALARM,
            title=f"设备告警: {device_name}",
            message=f"[{alarm_type}] {description}",
            priority=priority,
            metadata={"device_name": device_name, "alarm_type": alarm_type, "severity": severity},
        )

        rule = self._match_rule("device_alarm", priority)
        if rule:
            notification.channels = rule.channels

        return self._send(notification, "device_alarm")

    def notify_task_completed(
        self,
        task_name: str,
        result: str,
        duration_seconds: float = 0,
    ) -> dict[str, Any]:
        """任务完成通知"""
        notification = self._build_notification(
            notification_type=NotificationType.TASK_COMPLETED,
            title=f"任务完成: {task_name}",
            message=f"结果: {result}, 耗时: {duration_seconds:.1f}秒",
            priority=NotificationPriority.LOW,
            metadata={"task_name": task_name, "duration": duration_seconds},
        )
        return self._send(notification, "task_completed")

    def notify_task_failed(
        self,
        task_name: str,
        error: str,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """任务失败通知"""
        notification = self._build_notification(
            notification_type=NotificationType.TASK_FAILED,
            title=f"任务失败: {task_name}",
            message=f"错误: {error}, 重试次数: {retry_count}",
            priority=NotificationPriority.HIGH,
            metadata={"task_name": task_name, "error": error, "retry_count": retry_count},
        )
        return self._send(notification, "task_failed")

    def notify_approval_required(
        self,
        intent_id: int,
        intent_name: str,
        risk_level: str = "medium",
    ) -> dict[str, Any]:
        """审批通知"""
        priority_map = {
            "极高": NotificationPriority.URGENT,
            "高": NotificationPriority.HIGH,
            "中": NotificationPriority.MEDIUM,
            "低": NotificationPriority.LOW,
        }
        priority = priority_map.get(risk_level, NotificationPriority.MEDIUM)

        notification = self._build_notification(
            notification_type=NotificationType.APPROVAL_REQUIRED,
            title=f"需要审批: {intent_name}",
            message=f"意图#{intent_id} 风险等级={risk_level}, 需要人工审批",
            priority=priority,
            metadata={"intent_id": intent_id, "risk_level": risk_level},
        )
        return self._send(notification, "approval_required")

    def notify_healing_triggered(
        self,
        event_type: str,
        device_name: str,
        action: str,
        mode: str = "suggested",
    ) -> dict[str, Any]:
        """自愈触发通知"""
        notification = self._build_notification(
            notification_type=NotificationType.HEALING_TRIGGERED,
            title=f"自愈触发: {device_name}",
            message=f"事件={event_type}, 动作={action}, 模式={mode}",
            priority=NotificationPriority.HIGH,
            metadata={"event_type": event_type, "device_name": device_name, "mode": mode},
        )
        return self._send(notification, "healing_triggered")

    def _send(self, notification: Notification, event_type: str) -> dict[str, Any]:
        """发送通知（含去重、冷却、限流检查）"""
        # 去重检查
        if self._is_duplicate(notification):
            self._stats["dedup_suppressed"] += 1
            self._stats["total_suppressed"] += 1
            logger.debug(f"通知去重抑制: {notification.title}")
            return {"status": "suppressed", "reason": "duplicate", "notification_id": notification.notification_id}

        # 冷却检查
        event_key = f"{event_type}:{notification.metadata.get('device_name', '')}"
        rule = self._match_rule(event_type, notification.priority)
        cooldown = rule.cooldown_seconds if rule else self.config.default_cooldown_seconds
        if cooldown > 0 and not self._is_cooled_down(event_key, cooldown):
            self._stats["cooldown_suppressed"] += 1
            self._stats["total_suppressed"] += 1
            logger.debug(f"通知冷却抑制: {notification.title}")
            return {"status": "suppressed", "reason": "cooldown", "notification_id": notification.notification_id}

        # 限流检查
        rule_id = rule.rule_id if rule else "default"
        if self._is_rate_limited(rule_id):
            self._stats["rate_limited"] += 1
            self._stats["total_suppressed"] += 1
            logger.debug(f"通知限流抑制: {notification.title}")
            return {"status": "suppressed", "reason": "rate_limited", "notification_id": notification.notification_id}

        # 发送
        self._cooldown_tracker[event_key] = time.time()
        self._hourly_counts[rule_id] = self._hourly_counts.get(rule_id, 0) + 1
        self._stats["total_sent"] += 1

        type_key = f"{event_type}_sent"
        if type_key in self._stats:
            self._stats[type_key] += 1

        self._sent_history.append({
            "notification_id": notification.notification_id,
            "type": notification.notification_type.value,
            "title": notification.title,
            "priority": notification.priority.value,
            "sent_at": time.time(),
        })
        if len(self._sent_history) > 200:
            self._sent_history = self._sent_history[-200:]

        self._pending.append(notification)

        logger.info(f"通知已发送: [{notification.priority.value}] {notification.title}")

        return {
            "status": "sent",
            "notification_id": notification.notification_id,
            "channels": [c.value for c in notification.channels],
        }

    def get_pending(self, user_id: Optional[int] = None) -> list[dict[str, Any]]:
        """获取待发送通知"""
        pending = self._pending[:]
        self._pending.clear()
        results = []
        for n in pending:
            if user_id and n.target_users and user_id not in n.target_users:
                continue
            results.append({
                "notification_id": n.notification_id,
                "type": n.notification_type.value,
                "title": n.title,
                "message": n.message,
                "priority": n.priority.value,
                "channels": [c.value for c in n.channels],
                "metadata": n.metadata,
                "created_at": n.created_at,
            })
        return results

    def add_rule(self, rule: NotificationRule) -> None:
        """添加通知规则"""
        self._rules[rule.rule_id] = rule
        logger.info(f"添加通知规则: {rule.rule_id}")

    def remove_rule(self, rule_id: str) -> bool:
        """移除通知规则"""
        if rule_id in self._rules:
            del self._rules[rule_id]
            logger.info(f"移除通知规则: {rule_id}")
            return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return self._stats

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Agent标准处理接口"""
        action = input_data.get("action", "notify")

        if action == "notify_device_alarm":
            return self.notify_device_alarm(
                device_name=input_data.get("device_name", "未知设备"),
                alarm_type=input_data.get("alarm_type", "generic"),
                description=input_data.get("description", ""),
                severity=input_data.get("severity", "high"),
            )
        elif action == "notify_task_completed":
            return self.notify_task_completed(
                task_name=input_data.get("task_name", ""),
                result=input_data.get("result", ""),
                duration_seconds=input_data.get("duration", 0),
            )
        elif action == "notify_task_failed":
            return self.notify_task_failed(
                task_name=input_data.get("task_name", ""),
                error=input_data.get("error", ""),
                retry_count=input_data.get("retry_count", 0),
            )
        elif action == "notify_approval_required":
            return self.notify_approval_required(
                intent_id=input_data.get("intent_id", 0),
                intent_name=input_data.get("intent_name", ""),
                risk_level=input_data.get("risk_level", "medium"),
            )
        elif action == "notify_healing_triggered":
            return self.notify_healing_triggered(
                event_type=input_data.get("event_type", ""),
                device_name=input_data.get("device_name", ""),
                action=input_data.get("action_desc", ""),
                mode=input_data.get("mode", "suggested"),
            )
        elif action == "get_pending":
            return {"pending": self.get_pending(user_id=input_data.get("user_id"))}
        else:
            return {"error": f"未知操作: {action}"}

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "rules_count": len(self._rules),
            "pending_count": len(self._pending),
            "history_size": len(self._sent_history),
            "stats": self._stats,
        }
