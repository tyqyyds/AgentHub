import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from collections import Counter

logger = logging.getLogger(__name__)


class EnvironmentAwarenessEngine:
    def __init__(self):
        self._ws_manager = None
        self._user_behavior: Dict[str, List[Dict[str, Any]]] = {}
        self._alert_rate_tracker: Dict[str, List[datetime]] = {}
        self._inspection_interval = 300
        self._inspection_task: Optional[asyncio.Task] = None

    def set_ws_manager(self, manager):
        self._ws_manager = manager

    async def on_alert(self, alert: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        alert_type = alert.get("alert_type", "unknown")
        device_id = alert.get("device_id", "unknown")
        severity = alert.get("severity", "warning")
        message = alert.get("message", "")

        self._track_alert_rate(device_id)

        diagnosis = {
            "device_id": device_id,
            "anomaly_type": alert_type,
            "severity": severity,
            "root_cause": self._infer_root_cause(alert_type, message),
            "affected_devices": [],
        }

        suggestion = await self.generate_suggestion(diagnosis)

        push_data = {
            "push_type": "alert_diagnosis",
            "severity": severity,
            "title": f"告警诊断 - {device_id}",
            "message": f"检测到 {device_id} {alert_type}：{message}",
            "device_id": device_id,
            "diagnosis": diagnosis,
            "suggested_actions": suggestion.get("suggested_actions", []),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self.push_to_all(push_data)
        return push_data

    async def on_metric_anomaly(self, metric: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        trend = metric.get("trend", "stable")
        current_value = metric.get("current_value", 0)
        threshold = metric.get("threshold", 0)

        is_escalating = trend == "escalating" or current_value >= threshold

        if not is_escalating:
            return None

        device_id = metric.get("device_id", "unknown")
        metric_type = metric.get("metric_type", "unknown")
        duration = metric.get("duration_minutes", 0)

        severity = "critical" if current_value >= threshold * 1.2 else "warning"

        push_data = {
            "push_type": "trend_warning",
            "severity": severity,
            "title": f"趋势预警 - {device_id}",
            "message": f"{device_id} 的 {metric_type} 持续上升，当前值 {current_value}，阈值 {threshold}，持续 {duration} 分钟",
            "device_id": device_id,
            "metric_type": metric_type,
            "current_value": current_value,
            "threshold": threshold,
            "is_escalating": is_escalating,
            "suggested_actions": [
                {"label": "查看详情", "type": "navigate", "params": {"route": "/topology"}},
                {"label": "设置阈值", "type": "execute", "params": {"command": "set_threshold"}},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self.push_to_all(push_data)
        return push_data

    async def on_intent_status_change(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        new_status = event.get("new_status", "")
        intent_id = event.get("intent_id", 0)

        if new_status not in ("failed", "conflict"):
            return None

        severity = "critical" if new_status == "failed" else "warning"
        error_message = event.get("error_message", "")

        push_data = {
            "push_type": "operation_suggestion",
            "severity": severity,
            "title": f"操作建议 - 意图#{intent_id}",
            "message": f"意图 #{intent_id} 状态变为 {new_status}。{error_message}",
            "intent_id": intent_id,
            "new_status": new_status,
            "suggested_actions": [
                {"label": "查看详情", "type": "navigate", "params": {"route": "/intent"}},
                {"label": "重试", "type": "execute", "params": {"command": "retry_intent", "intent_id": intent_id}},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self.push_to_all(push_data)
        return push_data

    async def run_inspection(self) -> Dict[str, Any]:
        metrics = await self._collect_system_metrics()
        total = metrics.get("total_devices", 1)
        online = metrics.get("online_devices", 0)
        critical = metrics.get("critical_alerts", 0)
        warning = metrics.get("warning_alerts", 0)
        active_intents = metrics.get("active_intents", 0)

        health_pct = round((online / total * 100), 1) if total else 100

        if health_pct >= 90 and critical == 0:
            severity = "info"
            status_text = "🟢 良好"
        elif health_pct >= 70 and critical <= 3:
            severity = "warning"
            status_text = "🟡 一般"
        else:
            severity = "critical"
            status_text = "🔴 告警"

        push_data = {
            "push_type": "inspection_report",
            "severity": severity,
            "title": "系统巡检报告",
            "message": f"系统状态：{status_text}\n健康度：{health_pct}%\n在线设备：{online}/{total}\n严重告警：{critical}\n警告告警：{warning}\n活跃意图：{active_intents}",
            "health_percentage": health_pct,
            "total_devices": total,
            "online_devices": online,
            "critical_alerts": critical,
            "warning_alerts": warning,
            "active_intents": active_intents,
            "suggested_actions": [
                {"label": "查看指挥舱", "type": "navigate", "params": {"route": "/"}},
                {"label": "查看告警", "type": "query", "params": {"query": "pending_alerts"}},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self.push_to_all(push_data)
        return push_data

    async def _collect_system_metrics(self) -> Dict[str, Any]:
        try:
            from backend.database.connection import async_session_maker
            from backend.database.models import Device, AuditLog, Intent
            from sqlalchemy import select, func

            async with async_session_maker() as db:
                total_devices = await db.scalar(select(func.count(Device.id)))
                online_devices = await db.scalar(select(func.count(Device.id)).where(Device.status == 'online'))
                critical_count = await db.scalar(select(func.count(AuditLog.id)).where(AuditLog.security_type == 'critical'))
                warning_count = await db.scalar(select(func.count(AuditLog.id)).where(AuditLog.security_type == 'warning'))
                active_intents = await db.scalar(select(func.count(Intent.id)).where(Intent.status.in_(["pending", "executing"])))

                return {
                    "total_devices": total_devices or 0,
                    "online_devices": online_devices or 0,
                    "critical_alerts": critical_count or 0,
                    "warning_alerts": warning_count or 0,
                    "active_intents": active_intents or 0,
                }
        except Exception as e:
            logger.error(f"Collect system metrics failed: {e}")
            return {
                "total_devices": 0,
                "online_devices": 0,
                "critical_alerts": 0,
                "warning_alerts": 0,
                "active_intents": 0,
            }

    def predict_next_action(self, username: str, user_history: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if len(user_history) < 2:
            return None

        action_sequences = []
        for i in range(len(user_history) - 1):
            current = user_history[i].get("action", "")
            next_action = user_history[i + 1].get("action", "")
            if current and next_action:
                action_sequences.append((current, next_action))

        if not action_sequences:
            return None

        last_action = user_history[-1].get("action", "")
        transitions_from_last = [n for c, n in action_sequences if c == last_action]

        if not transitions_from_last:
            return None

        counter = Counter(transitions_from_last)
        most_common = counter.most_common(1)[0]
        predicted_action = most_common[0]
        confidence = most_common[1] / len(transitions_from_last)

        return {
            "predicted_action": predicted_action,
            "confidence": round(confidence, 2),
            "based_on_actions": len(action_sequences),
        }

    def predict_time_based_reminder(self, username: str, user_patterns: List[Dict[str, Any]], now: datetime) -> Optional[Dict[str, Any]]:
        for pattern in user_patterns:
            hour = pattern.get("hour")
            minute = pattern.get("minute")
            day_of_week = pattern.get("day_of_week")
            action = pattern.get("action", "")

            if hour is None or minute is None:
                continue

            if day_of_week is not None and day_of_week != now.weekday():
                continue

            time_diff = abs(now.hour * 60 + now.minute - hour * 60 - minute)
            if time_diff <= 30:
                return {
                    "push_type": "knowledge_reminder",
                    "severity": "info",
                    "title": f"定时提醒 - {action}",
                    "message": f"根据您的习惯，现在通常是 {action} 的时间",
                    "suggested_actions": [
                        {"label": f"执行{action}", "type": "execute", "params": {"command": action}},
                    ],
                }

        return None

    async def generate_suggestion(self, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        anomaly_type = diagnosis.get("anomaly_type", "unknown")
        device_id = diagnosis.get("device_id", "unknown")

        suggestions_map = {
            "link_down": [
                {"label": "查看拓扑", "type": "navigate", "params": {"route": "/topology"}},
                {"label": "启动自愈", "type": "execute", "params": {"command": "auto_heal", "device_id": device_id}},
            ],
            "cpu_overload": [
                {"label": "查看设备详情", "type": "query", "params": {"query": "device_status", "device_id": device_id}},
                {"label": "优化负载", "type": "execute", "params": {"command": "optimize_bandwidth"}},
            ],
            "memory_leak": [
                {"label": "查看内存趋势", "type": "query", "params": {"query": "memory_trend", "device_id": device_id}},
                {"label": "重启设备", "type": "execute", "params": {"command": "restart_device", "device_id": device_id}},
            ],
        }

        suggested_actions = suggestions_map.get(anomaly_type, [
            {"label": "查看详情", "type": "navigate", "params": {"route": "/topology"}},
        ])

        return {
            "diagnosis": diagnosis,
            "suggested_actions": suggested_actions,
        }

    async def get_environment_snapshot(self) -> Dict[str, Any]:
        metrics = await self._collect_system_metrics()
        total = metrics.get("total_devices", 1)
        online = metrics.get("online_devices", 0)
        health_pct = round((online / total * 100), 1) if total else 100

        return {
            "health_percentage": health_pct,
            "alert_summary": {
                "critical": metrics.get("critical_alerts", 0),
                "warning": metrics.get("warning_alerts", 0),
            },
            "active_intents": metrics.get("active_intents", 0),
            "total_devices": total,
            "online_devices": online,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _track_alert_rate(self, device_id: str):
        now = datetime.now(timezone.utc)
        if device_id not in self._alert_rate_tracker:
            self._alert_rate_tracker[device_id] = []
        self._alert_rate_tracker[device_id].append(now)
        cutoff = now.timestamp() - 60
        self._alert_rate_tracker[device_id] = [
            t for t in self._alert_rate_tracker[device_id] if t.timestamp() > cutoff
        ]

    def get_alert_rate(self, device_id: str) -> int:
        return len(self._alert_rate_tracker.get(device_id, []))

    def is_alert_storm(self, threshold: int = 5) -> bool:
        for device_id, timestamps in self._alert_rate_tracker.items():
            if len(timestamps) >= threshold:
                return True
        return False

    def _infer_root_cause(self, alert_type: str, message: str) -> str:
        cause_map = {
            "link_down": "链路中断，可能原因：光模块故障、线缆松动、对端设备离线",
            "cpu_overload": "CPU过载，可能原因：流量突增、路由震荡、进程异常",
            "memory_leak": "内存泄漏，可能原因：软件缺陷、缓冲区未释放、长时间未重启",
            "config_error": "配置错误，可能原因：手动配置失误、自动化脚本异常",
        }
        return cause_map.get(alert_type, f"未知异常类型：{alert_type}")

    async def push_to_user(self, username: str, push_data: Dict[str, Any]):
        if self._ws_manager:
            try:
                await self._ws_manager.send_to_user(username, {
                    "type": "proactive_push",
                    "data": push_data,
                })
            except Exception as e:
                logger.warning(f"Push to user {username} failed: {e}")

    async def push_to_all(self, push_data: Dict[str, Any]):
        if self._ws_manager:
            try:
                await self._ws_manager.broadcast({
                    "type": "proactive_push",
                    "data": push_data,
                })
            except Exception as e:
                logger.warning(f"Push to all failed: {e}")

    def start_scheduled_inspection(self, interval_seconds: int = 300):
        self._inspection_interval = interval_seconds
        if self._inspection_task and not self._inspection_task.done():
            return
        self._inspection_task = asyncio.create_task(self._inspection_loop())

    def stop_scheduled_inspection(self):
        if self._inspection_task and not self._inspection_task.done():
            self._inspection_task.cancel()

    async def _inspection_loop(self):
        while True:
            try:
                await asyncio.sleep(self._inspection_interval)
                await self.run_inspection()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Inspection loop error: {e}")


_engine: Optional[EnvironmentAwarenessEngine] = None


def get_environment_awareness_engine() -> EnvironmentAwarenessEngine:
    global _engine
    if _engine is None:
        _engine = EnvironmentAwarenessEngine()
    return _engine
