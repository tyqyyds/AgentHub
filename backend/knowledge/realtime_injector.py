from __future__ import annotations

import re
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeItem:
    source: str
    title: str
    content: str
    severity: str = "info"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    item_id: str = ""

    def __post_init__(self):
        if not self.item_id:
            self.item_id = f"{self.source}_{int(self.created_at * 1000)}"


class RealtimeKnowledgeInjector:
    def __init__(self, max_items: int = 1000):
        self._items: List[KnowledgeItem] = []
        self._max_items = max_items

    def inject_from_alert(self, alert: Dict[str, Any]) -> Optional[KnowledgeItem]:
        alert_type = alert.get("type", "unknown")
        device = alert.get("device", "未知设备")
        severity = alert.get("severity", "warning")
        message = alert.get("message", "")

        title = f"[告警] {device} - {alert_type}"
        content = f"设备 {device} 触发 {severity} 级别告警: {message} (类型: {alert_type})"

        item = KnowledgeItem(
            source="alert",
            title=title,
            content=content,
            severity=severity,
            metadata={"device": device, "alert_type": alert_type},
        )
        self._add_item(item)
        logger.info(f"Injected alert knowledge: {title}")
        return item

    def inject_from_metric(self, metric: Dict[str, Any]) -> Optional[KnowledgeItem]:
        device = metric.get("device", "未知设备")
        metric_name = metric.get("metric", "unknown")
        value = metric.get("value", 0)
        threshold = metric.get("threshold", 0)

        severity = "warning" if value >= threshold * 0.8 else "info"
        title = f"[指标] {device} - {metric_name}"
        content = f"设备 {device} 的 {metric_name} 当前值为 {value}，阈值 {threshold}"

        item = KnowledgeItem(
            source="metric",
            title=title,
            content=content,
            severity=severity,
            metadata={"device": device, "metric": metric_name, "value": value, "threshold": threshold},
        )
        self._add_item(item)
        return item

    def inject_from_audit(self, audit: Dict[str, Any]) -> Optional[KnowledgeItem]:
        action = audit.get("action", "unknown")
        user = audit.get("user", "unknown")
        target = audit.get("target", "unknown")
        status = audit.get("status", "unknown")

        severity = "critical" if action in ("config_acl", "delete_intent", "restart_device") else "info"
        title = f"[审计] {user} - {action}"
        content = f"用户 {user} 对 {target} 执行了 {action} 操作，状态: {status}"

        item = KnowledgeItem(
            source="audit",
            title=title,
            content=content,
            severity=severity,
            metadata={"action": action, "user": user, "target": target, "status": status},
        )
        self._add_item(item)
        return item

    def inject_custom(self, source: str, title: str, content: str, severity: str = "info", metadata: Dict[str, Any] = None) -> KnowledgeItem:
        item = KnowledgeItem(
            source=source,
            title=title,
            content=content,
            severity=severity,
            metadata=metadata or {},
        )
        self._add_item(item)
        return item

    def get_recent_items(self, limit: int = 20, source: str = None, severity: str = None) -> List[KnowledgeItem]:
        items = list(self._items)
        if source:
            items = [i for i in items if i.source == source]
        if severity:
            items = [i for i in items if i.severity == severity]
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items[:limit]

    def search(self, query: str, limit: int = 10) -> List[KnowledgeItem]:
        query_lower = query.lower()
        scored = []
        for item in self._items:
            score = 0
            if query_lower in item.title.lower():
                score += 3
            if query_lower in item.content.lower():
                score += 2
            for v in item.metadata.values():
                if isinstance(v, str) and query_lower in v.lower():
                    score += 1
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def _add_item(self, item: KnowledgeItem):
        self._items.append(item)
        if len(self._items) > self._max_items:
            self._items = self._items[-self._max_items:]

    def get_stats(self) -> Dict[str, Any]:
        source_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        for item in self._items:
            source_counts[item.source] = source_counts.get(item.source, 0) + 1
            severity_counts[item.severity] = severity_counts.get(item.severity, 0) + 1
        return {
            "total_items": len(self._items),
            "source_counts": source_counts,
            "severity_counts": severity_counts,
        }


_injector: Optional[RealtimeKnowledgeInjector] = None


def get_realtime_injector() -> RealtimeKnowledgeInjector:
    global _injector
    if _injector is None:
        _injector = RealtimeKnowledgeInjector()
    return _injector
