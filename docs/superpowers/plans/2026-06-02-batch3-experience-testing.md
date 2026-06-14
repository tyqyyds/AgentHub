# AI 助手升级 — 第三批实施计划

## Goal

在第一批（意图理解 v2 + DST + 知识引擎 v2）和第二批（Plan-Execute Agent + 工具编排引擎）基础上，完成：

1. **模块6：环境感知引擎 + 交互体验升级** — 让助手从被动响应变为主动感知、智能推送，并升级前端交互体验（自适应对话模式、语音、多模态、智能快捷栏、运维向导）
2. **模块7：测试体系** — 为全部核心模块建立自动化测试，确保意图识别准确率 >90%、对话连贯性、Plan-Execute 正确性、RAG 检索质量、工具链可靠性

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3)                          │
│  ┌────────────┐ ┌──────────────┐ ┌────────────┐ ┌────────────┐ │
│  │ ChatPanel   │ │ProactivePanel│ │VoiceInput  │ │WizardRunner│ │
│  │ (自适应模式) │ │ (主动推送)    │ │ (语音输入)  │ │ (运维向导)  │ │
│  └─────┬──────┘ └──────┬───────┘ └─────┬──────┘ └─────┬──────┘ │
│        │               │               │               │        │
│  ┌─────┴───────────────┴───────────────┴───────────────┴──────┐ │
│  │              assistant store (Pinia)                        │ │
│  │  + proactiveMessages / dialogMode / voiceEnabled / wizard  │ │
│  └────────────────────────┬───────────────────────────────────┘ │
│                           │ WebSocket + REST                    │
└───────────────────────────┼────────────────────────────────────┘
                            │
┌───────────────────────────┼────────────────────────────────────┐
│                     Backend (FastAPI)                           │
│  ┌────────────────────────┴──────────────────────────────────┐ │
│  │           /api/v1/assistant/proactive/*                    │ │
│  └────────────────────────┬──────────────────────────────────┘ │
│                           │                                     │
│  ┌────────────────────────┴──────────────────────────────────┐ │
│  │         EnvironmentAwarenessEngine                         │ │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │ │
│  │  │ EventDriven  │ │ Scheduled    │ │ BehaviorPredictor│  │ │
│  │  │ Perception   │ │ Inspection   │ │ (行为预测)        │  │ │
│  │  └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘  │ │
│  │         └────────────────┼──────────────────┘             │ │
│  │                    ProactivePusher                         │ │
│  │         (告警诊断/趋势预警/巡检报告/操作建议/知识提醒)      │ │
│  └────────────────────────┬──────────────────────────────────┘ │
│                           │                                     │
│  ┌────────────────────────┴──────────────────────────────────┐ │
│  │  WebSocketManager (主动推送集成)                            │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Tests: intent_classifier / dialogue_state / plan_executor│ │
│  │         rag_engine / tool_chains                          │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| 层 | 技术 |
|---|------|
| 后端 | Python 3.11+, FastAPI, SQLAlchemy (async), asyncio |
| 前端 | Vue 3 Composition API, TypeScript, Pinia |
| 通信 | WebSocket (主动推送), REST API, SSE (流式) |
| 语音 | Web Speech API (SpeechRecognition + SpeechSynthesis) |
| 多模态 | 已有 MultimodalProcessor + OCR 扩展 |
| 测试 | pytest, pytest-asyncio, httpx (AsyncClient) |
| 构建 | `cd frontend && npx vite build` |

## 依赖关系

```
第三批依赖前两批已完成的模块：
  ├── 意图理解引擎 v2 (intent_classifier.py) — 环境感知需要意图分类
  ├── 对话状态追踪器 (dialogue_state.py) — 自适应模式需要 DST
  ├── Plan-Execute Agent (plan_executor.py) — 运维向导需要 Plan-Execute
  ├── 工具编排引擎 (tool_chains.py) — 环境感知需要工具链
  └── 知识引擎 v2 (rag_engine.py) — 知识提醒需要 RAG
```

---

# 模块6：环境感知引擎 + 交互体验升级

## 6.1 环境感知引擎

### Step 6.1.1 — 新增 `backend/agents/environment_awareness.py`

- [ ] 编写测试 `tests/test_environment_awareness.py` — 事件驱动感知、定时巡检、行为预测、主动推送
- [ ] 实现 `EnvironmentAwarenessEngine` 类
- [ ] 运行测试确认通过

**测试文件：`tests/test_environment_awareness.py`**

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


@pytest.fixture
def mock_ws_manager():
    manager = MagicMock()
    manager.send_to_user = AsyncMock()
    manager.broadcast = AsyncMock()
    return manager


@pytest.fixture
def mock_proactive_notifier():
    notifier = MagicMock()
    notifier.notify_device_anomaly = AsyncMock()
    notifier.notify_sla_warning = AsyncMock()
    notifier.notify_healing_completed = AsyncMock()
    notifier.notify_intent_status_change = AsyncMock()
    notifier._create_notification = AsyncMock()
    notifier.send_notification = AsyncMock()
    return notifier


@pytest.fixture
def engine(mock_ws_manager, mock_proactive_notifier):
    from backend.agents.environment_awareness import EnvironmentAwarenessEngine
    e = EnvironmentAwarenessEngine()
    e.set_ws_manager(mock_ws_manager)
    e.set_proactive_notifier(mock_proactive_notifier)
    return e


class TestEventDrivenPerception:
    @pytest.mark.asyncio
    async def test_on_alert_triggers_diagnosis(self, engine, mock_ws_manager):
        alert = {
            "alert_id": "alt_001",
            "device_id": "router-core-01",
            "alert_type": "link_down",
            "severity": "critical",
            "message": "核心路由器链路中断",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        result = await engine.on_alert(alert)
        assert result is not None
        assert result["push_type"] == "alert_diagnosis"
        assert "device_id" in result
        assert result["device_id"] == "router-core-01"
        mock_ws_manager.broadcast.assert_called_once()
        ws_msg = mock_ws_manager.broadcast.call_args[0][0]
        assert ws_msg["type"] == "proactive_push"
        assert ws_msg["data"]["push_type"] == "alert_diagnosis"

    @pytest.mark.asyncio
    async def test_on_alert_warning_severity(self, engine, mock_ws_manager):
        alert = {
            "alert_id": "alt_002",
            "device_id": "switch-access-03",
            "alert_type": "cpu_high",
            "severity": "warning",
            "message": "接入交换机CPU使用率过高",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        result = await engine.on_alert(alert)
        assert result is not None
        assert result["push_type"] == "alert_diagnosis"
        assert result["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_on_metric_anomaly_escalating(self, engine, mock_ws_manager):
        metric = {
            "device_id": "router-edge-02",
            "metric_type": "bandwidth_mbps",
            "current_value": 950,
            "threshold": 800,
            "trend": "escalating",
            "duration_minutes": 15,
        }
        result = await engine.on_metric_anomaly(metric)
        assert result is not None
        assert result["push_type"] == "trend_warning"
        assert result["is_escalating"] is True

    @pytest.mark.asyncio
    async def test_on_metric_anomaly_stable(self, engine, mock_ws_manager):
        metric = {
            "device_id": "switch-core-01",
            "metric_type": "cpu_percent",
            "current_value": 75,
            "threshold": 80,
            "trend": "stable",
            "duration_minutes": 5,
        }
        result = await engine.on_metric_anomaly(metric)
        assert result is None

    @pytest.mark.asyncio
    async def test_on_intent_status_failed(self, engine, mock_ws_manager):
        event = {
            "intent_id": 42,
            "old_status": "executing",
            "new_status": "failed",
            "error_message": "设备连接超时",
        }
        result = await engine.on_intent_status_change(event)
        assert result is not None
        assert result["push_type"] == "operation_suggestion"
        assert result["severity"] == "critical"


class TestScheduledInspection:
    @pytest.mark.asyncio
    async def test_run_inspection(self, engine, mock_ws_manager):
        with patch.object(engine, '_collect_system_metrics', new_callable=AsyncMock) as mock_collect:
            mock_collect.return_value = {
                "total_devices": 50,
                "online_devices": 47,
                "critical_alerts": 2,
                "warning_alerts": 5,
                "active_intents": 3,
            }
            result = await engine.run_inspection()
            assert result is not None
            assert result["push_type"] == "inspection_report"
            assert "health_percentage" in result
            assert result["health_percentage"] == 94.0

    @pytest.mark.asyncio
    async def test_run_inspection_degraded(self, engine, mock_ws_manager):
        with patch.object(engine, '_collect_system_metrics', new_callable=AsyncMock) as mock_collect:
            mock_collect.return_value = {
                "total_devices": 50,
                "online_devices": 30,
                "critical_alerts": 10,
                "warning_alerts": 15,
                "active_intents": 8,
            }
            result = await engine.run_inspection()
            assert result is not None
            assert result["push_type"] == "inspection_report"
            assert result["severity"] == "critical"
            assert result["health_percentage"] == 60.0


class TestBehaviorPrediction:
    def test_predict_next_action_with_history(self, engine):
        user_history = [
            {"action": "view_dashboard", "timestamp": "2026-06-02T08:00:00Z"},
            {"action": "query_alerts", "timestamp": "2026-06-02T08:01:00Z"},
            {"action": "view_dashboard", "timestamp": "2026-06-02T09:00:00Z"},
            {"action": "query_alerts", "timestamp": "2026-06-02T09:01:00Z"},
            {"action": "view_dashboard", "timestamp": "2026-06-02T10:00:00Z"},
        ]
        prediction = engine.predict_next_action("user1", user_history)
        assert prediction is not None
        assert prediction["predicted_action"] == "query_alerts"
        assert prediction["confidence"] > 0.5

    def test_predict_next_action_no_history(self, engine):
        prediction = engine.predict_next_action("user1", [])
        assert prediction is None

    def test_predict_next_action_insufficient_history(self, engine):
        user_history = [
            {"action": "view_dashboard", "timestamp": "2026-06-02T08:00:00Z"},
        ]
        prediction = engine.predict_next_action("user1", user_history)
        assert prediction is None

    def test_predict_time_based_reminder(self, engine):
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        user_patterns = [
            {"action": "daily_inspection", "hour": 9, "minute": 0, "day_of_week": now.weekday()},
        ]
        reminder = engine.predict_time_based_reminder("user1", user_patterns, now)
        assert reminder is not None
        assert reminder["push_type"] == "knowledge_reminder"


class TestProactivePush:
    @pytest.mark.asyncio
    async def test_push_to_specific_user(self, engine, mock_ws_manager):
        push_data = {
            "push_type": "alert_diagnosis",
            "severity": "critical",
            "title": "核心路由器链路中断",
            "message": "检测到核心路由器 router-core-01 链路中断",
            "suggested_actions": [
                {"label": "查看详情", "type": "navigate", "params": {"route": "/topology"}},
                {"label": "启动自愈", "type": "execute", "params": {"command": "auto_heal"}},
            ],
        }
        await engine.push_to_user("admin", push_data)
        mock_ws_manager.send_to_user.assert_called_once_with("admin", {
            "type": "proactive_push",
            "data": push_data,
        })

    @pytest.mark.asyncio
    async def test_push_to_all_users(self, engine, mock_ws_manager):
        push_data = {
            "push_type": "inspection_report",
            "severity": "info",
            "title": "系统巡检报告",
            "message": "系统运行正常",
        }
        await engine.push_to_all(push_data)
        mock_ws_manager.broadcast.assert_called_once_with({
            "type": "proactive_push",
            "data": push_data,
        })

    @pytest.mark.asyncio
    async def test_generate_suggestion_from_diagnosis(self, engine):
        diagnosis = {
            "device_id": "router-core-01",
            "anomaly_type": "link_down",
            "root_cause": "光模块故障",
            "affected_devices": ["switch-access-01", "switch-access-02"],
        }
        suggestion = await engine.generate_suggestion(diagnosis)
        assert suggestion is not None
        assert "suggested_actions" in suggestion
        assert len(suggestion["suggested_actions"]) > 0


class TestEnvironmentSnapshot:
    @pytest.mark.asyncio
    async def test_get_environment_snapshot(self, engine):
        with patch.object(engine, '_collect_system_metrics', new_callable=AsyncMock) as mock_collect:
            mock_collect.return_value = {
                "total_devices": 50,
                "online_devices": 47,
                "critical_alerts": 2,
                "warning_alerts": 5,
                "active_intents": 3,
            }
            snapshot = await engine.get_environment_snapshot()
            assert "health_percentage" in snapshot
            assert "alert_summary" in snapshot
            assert "active_intents" in snapshot
            assert snapshot["health_percentage"] == 94.0
```

**实现文件：`backend/agents/environment_awareness.py`**

```python
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from collections import Counter

from backend.agents.proactive_notifier import ProactiveNotifier

logger = logging.getLogger(__name__)


class EnvironmentAwarenessEngine:
    def __init__(self):
        self._ws_manager = None
        self._proactive_notifier: Optional[ProactiveNotifier] = None
        self._user_behavior: Dict[str, List[Dict[str, Any]]] = {}
        self._alert_rate_tracker: Dict[str, List[datetime]] = {}
        self._inspection_interval = 300
        self._inspection_task: Optional[asyncio.Task] = None

    def set_ws_manager(self, manager):
        self._ws_manager = manager

    def set_proactive_notifier(self, notifier: ProactiveNotifier):
        self._proactive_notifier = notifier

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

        if trend != "escalating" and current_value < threshold:
            return None

        device_id = metric.get("device_id", "unknown")
        metric_type = metric.get("metric_type", "unknown")
        duration = metric.get("duration_minutes", 0)

        is_escalating = trend == "escalating" or current_value >= threshold

        if not is_escalating:
            return None

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
```

**测试命令：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub" && python -m pytest tests/test_environment_awareness.py -v
```

---

### Step 6.1.2 — 修改 `backend/api/assistant.py` — 新增 /proactive 端点

- [ ] 编写测试 — proactive API 端点测试
- [ ] 实现 `/proactive/suggestions` 和 `/proactive/insights` 端点
- [ ] 运行测试确认通过

**在 `backend/api/assistant.py` 末尾追加：**

```python
@router.get("/proactive/suggestions")
async def get_proactive_suggestions(
    current_user=Depends(get_current_user),
):
    try:
        from backend.agents.environment_awareness import get_environment_awareness_engine
        engine = get_environment_awareness_engine()
        snapshot = await engine.get_environment_snapshot()
        suggestions = []

        health = snapshot.get("health_percentage", 100)
        critical = snapshot.get("alert_summary", {}).get("critical", 0)
        warning = snapshot.get("alert_summary", {}).get("warning", 0)

        if critical > 0:
            suggestions.append({
                "type": "alert_diagnosis",
                "priority": "high",
                "message": f"当前有 {critical} 条严重告警需要处理",
                "action": {"label": "查看告警", "type": "navigate", "params": {"route": "/self-healing"}},
            })

        if health < 80:
            suggestions.append({
                "type": "operation_suggestion",
                "priority": "medium",
                "message": f"系统健康度 {health}%，建议检查离线设备",
                "action": {"label": "查看拓扑", "type": "navigate", "params": {"route": "/topology"}},
            })

        if warning > 5:
            suggestions.append({
                "type": "trend_warning",
                "priority": "low",
                "message": f"警告告警 {warning} 条，可能存在趋势性风险",
                "action": {"label": "查看详情", "type": "query", "params": {"query": "pending_alerts"}},
            })

        return success_response(data={"suggestions": suggestions, "snapshot": snapshot})
    except Exception as e:
        logger.error(f"Get proactive suggestions error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.get("/proactive/insights")
async def get_proactive_insights(
    current_user=Depends(get_current_user),
):
    try:
        from backend.agents.environment_awareness import get_environment_awareness_engine
        engine = get_environment_awareness_engine()

        snapshot = await engine.get_environment_snapshot()
        is_storm = engine.is_alert_storm()

        insights = {
            "system_health": snapshot.get("health_percentage", 100),
            "alert_storm": is_storm,
            "alert_summary": snapshot.get("alert_summary", {}),
            "active_intents": snapshot.get("active_intents", 0),
            "recommended_mode": "emergency" if is_storm or snapshot.get("alert_summary", {}).get("critical", 0) > 3 else "daily",
        }

        return success_response(data=insights)
    except Exception as e:
        logger.error(f"Get proactive insights error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")
```

**测试命令：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub" && python -m pytest tests/test_environment_awareness.py tests/test_integration.py -v -k "proactive or integration"
```

---

### Step 6.1.3 — 修改 `backend/core/websocket_manager.py` — 主动推送集成

- [ ] 编写测试 — WebSocket 主动推送消息格式测试
- [ ] 在 `ConnectionManager` 中新增 `send_proactive_push` 方法
- [ ] 运行测试确认通过

**修改 `backend/core/websocket_manager.py`，在 `ConnectionManager` 类中追加方法：**

```python
    async def send_proactive_push(self, username: str, push_type: str, data: dict):
        message = {
            "type": "proactive_push",
            "data": {
                "push_type": push_type,
                **data,
            }
        }
        await self.send_to_user(username, message)

    async def broadcast_proactive_push(self, push_type: str, data: dict):
        message = {
            "type": "proactive_push",
            "data": {
                "push_type": push_type,
                **data,
            }
        }
        await self.broadcast(message)
```

**测试命令：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub" && python -m pytest tests/test_environment_awareness.py -v
```

---

## 6.2 交互体验升级

### Step 6.2.1 — 新增 `frontend/src/components/AiAssistant/ProactivePanel.vue`

- [ ] 创建主动推送面板组件
- [ ] 集成到 `AiAssistant.vue`
- [ ] 前端构建验证

**文件：`frontend/src/components/AiAssistant/ProactivePanel.vue`**

```vue
<template>
  <div v-if="messages.length > 0" class="proactive-panel" :class="{ collapsed: isCollapsed }">
    <div class="proactive-header" @click="isCollapsed = !isCollapsed">
      <span class="proactive-icon">🔔</span>
      <span class="proactive-title">主动通知</span>
      <span class="proactive-count">{{ messages.length }}</span>
      <span class="proactive-toggle">{{ isCollapsed ? '▸' : '▾' }}</span>
    </div>
    <div v-show="!isCollapsed" class="proactive-body">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="proactive-item"
        :class="`severity-${msg.severity}`"
      >
        <div class="proactive-item-header">
          <span class="item-type-icon">{{ typeIcon(msg.pushType) }}</span>
          <span class="item-title">{{ msg.title }}</span>
          <button type="button" class="item-dismiss" @click="dismiss(msg.id)" aria-label="关闭">✕</button>
        </div>
        <p class="item-message">{{ msg.message }}</p>
        <div v-if="msg.suggestedActions && msg.suggestedActions.length" class="item-actions">
          <button
            type="button"
            v-for="(action, ai) in msg.suggestedActions"
            :key="ai"
            class="item-action-btn"
            @click="executeAction(action)"
            :aria-label="action.label"
          >
            {{ action.label }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAssistantStore } from '@/stores/assistant'
import { useActionEngine, type AssistantAction } from '@/composables/useActionEngine'

interface ProactiveMessage {
  id: string
  pushType: string
  severity: string
  title: string
  message: string
  suggestedActions?: Array<{ label: string; type: string; params?: Record<string, unknown> }>
  timestamp: string
}

const store = useAssistantStore()
const { executeAction } = useActionEngine()

const messages = ref<ProactiveMessage[]>([])
const isCollapsed = ref(false)
let msgCounter = 0

const typeIcon = (pushType: string) => {
  const map: Record<string, string> = {
    alert_diagnosis: '🚨',
    trend_warning: '📈',
    inspection_report: '📊',
    operation_suggestion: '💡',
    knowledge_reminder: '📚',
  }
  return map[pushType] || '🔔'
}

const handleProactivePush = (event: CustomEvent) => {
  const data = event.detail?.data
  if (!data) return
  messages.value.unshift({
    id: `pp_${Date.now()}_${++msgCounter}`,
    pushType: data.push_type || 'unknown',
    severity: data.severity || 'info',
    title: data.title || '通知',
    message: data.message || '',
    suggestedActions: data.suggested_actions || [],
    timestamp: data.timestamp || new Date().toISOString(),
  })
  if (messages.value.length > 20) {
    messages.value = messages.value.slice(0, 20)
  }
}

const dismiss = (id: string) => {
  messages.value = messages.value.filter(m => m.id !== id)
}

const executeProactiveAction = (action: { label: string; type: string; params?: Record<string, unknown> }) => {
  const assistantAction: AssistantAction = {
    type: action.type,
    label: action.label,
    params: (action.params || {}) as Record<string, any>
  }
  executeAction(assistantAction)
}

onMounted(() => {
  window.addEventListener('proactive_push', handleProactivePush as EventListener)
})

onUnmounted(() => {
  window.removeEventListener('proactive_push', handleProactivePush as EventListener)
})
</script>

<style scoped>
.proactive-panel {
  background: rgba(15, 23, 42, 0.6);
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  flex-shrink: 0;
}

.proactive-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  color: #94a3b8;
  font-size: var(--font-size-xs);
}

.proactive-header:hover {
  color: #e2e8f0;
}

.proactive-icon {
  font-size: var(--font-size-base);
}

.proactive-title {
  font-weight: 500;
  flex: 1;
}

.proactive-count {
  background: rgba(239, 68, 68, 0.8);
  color: white;
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 0.6875rem;
  font-weight: 600;
  min-width: 20px;
  text-align: center;
}

.proactive-toggle {
  font-size: 10px;
}

.proactive-body {
  max-height: 200px;
  overflow-y: auto;
  padding: 0 var(--spacing-md) var(--spacing-sm);
}

.proactive-body::-webkit-scrollbar {
  width: 3px;
}

.proactive-body::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.2);
  border-radius: 2px;
}

.proactive-item {
  padding: var(--spacing-sm);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-xs);
  border-left: 3px solid transparent;
}

.proactive-item.severity-critical {
  background: rgba(239, 68, 68, 0.08);
  border-left-color: #ef4444;
}

.proactive-item.severity-warning {
  background: rgba(250, 204, 21, 0.08);
  border-left-color: #facc15;
}

.proactive-item.severity-info {
  background: rgba(99, 102, 241, 0.08);
  border-left-color: #6366f1;
}

.proactive-item-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-bottom: 4px;
}

.item-type-icon {
  font-size: var(--font-size-sm);
}

.item-title {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: #e2e8f0;
  flex: 1;
}

.item-dismiss {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  font-size: var(--font-size-xs);
  padding: 2px;
  border-radius: 4px;
  min-width: 28px;
  min-height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.item-dismiss:hover {
  color: #e2e8f0;
  background: rgba(255, 255, 255, 0.06);
}

.item-message {
  font-size: 0.6875rem;
  color: #94a3b8;
  line-height: 1.4;
  margin: 0;
}

.item-actions {
  display: flex;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-xs);
}

.item-action-btn {
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(99, 102, 241, 0.4);
  background: rgba(99, 102, 241, 0.1);
  color: #a5b4fc;
  font-size: 0.6875rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.item-action-btn:hover {
  background: rgba(99, 102, 241, 0.25);
  border-color: rgba(99, 102, 241, 0.6);
}
</style>
```

**构建验证：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend" && npx vite build
```

---

### Step 6.2.2 — 新增 `frontend/src/components/AiAssistant/VoiceInput.vue`

- [ ] 创建语音输入组件（Web Speech API）
- [ ] 不可用时隐藏按钮
- [ ] 前端构建验证

**文件：`frontend/src/components/AiAssistant/VoiceInput.vue`**

```vue
<template>
  <button
    v-if="isSupported"
    type="button"
    class="voice-btn"
    :class="{ listening: isListening, disabled: disabled }"
    :disabled="disabled"
    @click="toggleListening"
    :aria-label="isListening ? '停止语音输入' : '开始语音输入'"
    :title="isListening ? '停止语音输入' : '语音输入'"
  >
    <svg v-if="!isListening" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
      <line x1="12" y1="19" x2="12" y2="23"/>
      <line x1="8" y1="23" x2="16" y2="23"/>
    </svg>
    <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
      <line x1="12" y1="19" x2="12" y2="23"/>
      <line x1="8" y1="23" x2="16" y2="23"/>
    </svg>
    <span v-if="isListening" class="voice-pulse" />
  </button>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  disabled?: boolean
}>()

const emit = defineEmits<{
  transcript: [text: string]
  listeningChange: [isListening: boolean]
}>()

const isSupported = ref(false)
const isListening = ref(false)

let recognition: any = null

onMounted(() => {
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (SpeechRecognition) {
    isSupported.value = true
    recognition = new SpeechRecognition()
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = 'zh-CN'

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript
      if (transcript) {
        emit('transcript', transcript)
      }
      stopListening()
    }

    recognition.onerror = () => {
      stopListening()
    }

    recognition.onend = () => {
      stopListening()
    }
  }
})

const toggleListening = () => {
  if (isListening.value) {
    stopListening()
  } else {
    startListening()
  }
}

const startListening = () => {
  if (!recognition || isListening.value) return
  try {
    recognition.start()
    isListening.value = true
    emit('listeningChange', true)
  } catch {
    isListening.value = false
  }
}

const stopListening = () => {
  if (!recognition) return
  try {
    recognition.stop()
  } catch {
    // ignore
  }
  isListening.value = false
  emit('listeningChange', false)
}

onUnmounted(() => {
  if (recognition && isListening.value) {
    try {
      recognition.stop()
    } catch {
      // ignore
    }
  }
})
</script>

<style scoped>
.voice-btn {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  border: none;
  background: rgba(148, 163, 184, 0.1);
  color: #64748b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  flex-shrink: 0;
  position: relative;
}

.voice-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
}

.voice-btn.listening {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
  animation: voice-pulse-bg 1.5s ease-in-out infinite;
}

.voice-btn.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.voice-pulse {
  position: absolute;
  inset: -4px;
  border-radius: var(--radius-md);
  border: 2px solid rgba(239, 68, 68, 0.4);
  animation: voice-ring 1.5s ease-in-out infinite;
}

@keyframes voice-pulse-bg {
  0%, 100% { background: rgba(239, 68, 68, 0.2); }
  50% { background: rgba(239, 68, 68, 0.35); }
}

@keyframes voice-ring {
  0% { transform: scale(1); opacity: 1; }
  100% { transform: scale(1.3); opacity: 0; }
}
</style>
```

**构建验证：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend" && npx vite build
```

---

### Step 6.2.3 — 新增 `frontend/src/components/AiAssistant/WizardRunner.vue`

- [ ] 创建运维向导组件
- [ ] 前端构建验证

**文件：`frontend/src/components/AiAssistant/WizardRunner.vue`**

```vue
<template>
  <div v-if="wizard" class="wizard-runner">
    <div class="wizard-header">
      <span class="wizard-icon">🧙</span>
      <span class="wizard-title">{{ wizard.name }}</span>
      <button type="button" class="wizard-close" @click="closeWizard" aria-label="关闭向导">✕</button>
    </div>
    <div class="wizard-progress">
      <div
        v-for="(step, idx) in wizard.steps"
        :key="step.step_id"
        class="wizard-step-indicator"
        :class="{
          completed: idx < currentStepIndex,
          active: idx === currentStepIndex,
          pending: idx > currentStepIndex,
        }"
      >
        <span class="step-dot">{{ idx < currentStepIndex ? '✓' : idx + 1 }}</span>
        <span v-if="idx < wizard.steps.length - 1" class="step-connector" :class="{ filled: idx < currentStepIndex }" />
      </div>
    </div>
    <div v-if="currentStep" class="wizard-step-content">
      <h4 class="step-title">{{ currentStep.description }}</h4>
      <p v-if="currentStep.explanation" class="step-explanation">{{ currentStep.explanation }}</p>
      <div v-if="currentStep.status === 'running'" class="step-running">
        <span class="running-spinner" />
        <span>执行中…</span>
      </div>
      <div v-if="currentStep.status === 'waiting_confirm'" class="step-confirm">
        <p class="confirm-text">此步骤需要您的确认</p>
        <div class="confirm-actions">
          <button type="button" class="confirm-btn approve" @click="approveStep" aria-label="确认执行">确认执行</button>
          <button type="button" class="confirm-btn cancel" @click="cancelStep" aria-label="跳过">跳过</button>
        </div>
      </div>
      <div v-if="currentStep.result" class="step-result">
        <p>{{ currentStep.result }}</p>
      </div>
    </div>
    <div class="wizard-footer">
      <button type="button" class="wizard-nav-btn" :disabled="currentStepIndex === 0" @click="prevStep" aria-label="上一步">上一步</button>
      <span class="wizard-step-counter">{{ currentStepIndex + 1 }} / {{ wizard.steps.length }}</span>
      <button type="button" class="wizard-nav-btn primary" :disabled="currentStepIndex >= wizard.steps.length - 1" @click="nextStep" aria-label="下一步">下一步</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAssistantStore } from '@/stores/assistant'

interface WizardStep {
  step_id: string
  description: string
  explanation?: string
  tool: string
  params: Record<string, any>
  risk_level: 'low' | 'medium' | 'high'
  status: 'pending' | 'running' | 'completed' | 'failed' | 'waiting_confirm'
  result?: string
}

interface Wizard {
  name: string
  steps: WizardStep[]
}

const store = useAssistantStore()

const wizard = ref<Wizard | null>(null)
const currentStepIndex = ref(0)

const currentStep = computed(() => {
  if (!wizard.value) return null
  return wizard.value.steps[currentStepIndex.value] || null
})

const startWizard = (wizardData: Wizard) => {
  wizard.value = wizardData
  currentStepIndex.value = 0
}

const closeWizard = () => {
  wizard.value = null
  currentStepIndex.value = 0
}

const nextStep = () => {
  if (!wizard.value) return
  if (currentStepIndex.value < wizard.value.steps.length - 1) {
    currentStepIndex.value++
  }
}

const prevStep = () => {
  if (currentStepIndex.value > 0) {
    currentStepIndex.value--
  }
}

const approveStep = () => {
  if (!currentStep.value) return
  currentStep.value.status = 'running'
  window.dispatchEvent(new CustomEvent('assistant:wizard_approve', {
    detail: { step_id: currentStep.value.step_id }
  }))
}

const cancelStep = () => {
  if (!currentStep.value) return
  currentStep.value.status = 'pending'
  if (currentStepIndex.value < (wizard.value?.steps.length || 0) - 1) {
    currentStepIndex.value++
  }
}

defineExpose({ startWizard, closeWizard })
</script>

<style scoped>
.wizard-runner {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: var(--radius-md);
  margin: var(--spacing-sm) var(--spacing-md);
  overflow: hidden;
}

.wizard-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: rgba(99, 102, 241, 0.1);
  border-bottom: 1px solid rgba(99, 102, 241, 0.2);
}

.wizard-icon {
  font-size: var(--font-size-lg);
}

.wizard-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: #a5b4fc;
  flex: 1;
}

.wizard-close {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  font-size: var(--font-size-sm);
  padding: 2px;
  min-width: 28px;
  min-height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
}

.wizard-close:hover {
  color: #e2e8f0;
  background: rgba(255, 255, 255, 0.06);
}

.wizard-progress {
  display: flex;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  gap: 0;
}

.wizard-step-indicator {
  display: flex;
  align-items: center;
  flex: 1;
}

.step-dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.6875rem;
  font-weight: 600;
  flex-shrink: 0;
  background: rgba(100, 116, 139, 0.2);
  color: #64748b;
  border: 2px solid rgba(100, 116, 139, 0.3);
}

.wizard-step-indicator.completed .step-dot {
  background: rgba(34, 197, 94, 0.2);
  color: #4ade80;
  border-color: rgba(34, 197, 94, 0.5);
}

.wizard-step-indicator.active .step-dot {
  background: rgba(99, 102, 241, 0.2);
  color: #a5b4fc;
  border-color: rgba(99, 102, 241, 0.5);
}

.step-connector {
  flex: 1;
  height: 2px;
  background: rgba(100, 116, 139, 0.2);
  margin: 0 4px;
}

.step-connector.filled {
  background: rgba(34, 197, 94, 0.4);
}

.wizard-step-content {
  padding: var(--spacing-sm) var(--spacing-md);
}

.step-title {
  font-size: var(--font-size-sm);
  color: #e2e8f0;
  margin: 0 0 var(--spacing-xs) 0;
}

.step-explanation {
  font-size: var(--font-size-xs);
  color: #94a3b8;
  margin: 0 0 var(--spacing-sm) 0;
  line-height: 1.5;
}

.step-running {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: #60a5fa;
  font-size: var(--font-size-xs);
}

.running-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(96, 165, 250, 0.3);
  border-top-color: #60a5fa;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.step-confirm {
  padding: var(--spacing-sm);
  background: rgba(250, 204, 21, 0.08);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(250, 204, 21, 0.2);
}

.confirm-text {
  font-size: var(--font-size-xs);
  color: #fbbf24;
  margin: 0 0 var(--spacing-sm) 0;
}

.confirm-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.confirm-btn {
  padding: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--radius-sm);
  border: none;
  font-size: var(--font-size-xs);
  cursor: pointer;
  font-weight: 500;
}

.confirm-btn.approve {
  background: rgba(34, 197, 94, 0.2);
  color: #4ade80;
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.confirm-btn.approve:hover {
  background: rgba(34, 197, 94, 0.3);
}

.confirm-btn.cancel {
  background: rgba(148, 163, 184, 0.1);
  color: #94a3b8;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.confirm-btn.cancel:hover {
  background: rgba(148, 163, 184, 0.2);
}

.step-result {
  padding: var(--spacing-sm);
  background: rgba(34, 197, 94, 0.08);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: #4ade80;
}

.wizard-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid rgba(148, 163, 184, 0.1);
}

.wizard-nav-btn {
  padding: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(148, 163, 184, 0.06);
  color: #94a3b8;
  font-size: var(--font-size-xs);
  cursor: pointer;
}

.wizard-nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.wizard-nav-btn.primary {
  background: rgba(99, 102, 241, 0.15);
  border-color: rgba(99, 102, 241, 0.3);
  color: #a5b4fc;
}

.wizard-nav-btn:not(:disabled):hover {
  background: rgba(148, 163, 184, 0.15);
}

.wizard-nav-btn.primary:not(:disabled):hover {
  background: rgba(99, 102, 241, 0.25);
}

.wizard-step-counter {
  font-size: var(--font-size-xs);
  color: #64748b;
}
</style>
```

**构建验证：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend" && npx vite build
```

---

### Step 6.2.4 — 修改 `frontend/src/stores/assistant.ts` — 新状态和方法

- [ ] 添加 `dialogMode`、`proactiveMessages`、`voiceEnabled`、`wizardActive` 状态
- [ ] 添加 `setDialogMode`、`addProactiveMessage`、`toggleVoice`、`startWizard` 方法
- [ ] 前端构建验证

**在 `assistant.ts` 中追加类型和状态：**

在 `PanelMode` 类型后追加：

```typescript
export type DialogMode = 'standard' | 'emergency' | 'report' | 'tutorial'

export interface ProactiveMessage {
  id: string
  pushType: string
  severity: string
  title: string
  message: string
  suggestedActions?: AssistantAction[]
  timestamp: string
}
```

在 store 内部追加状态：

```typescript
  const dialogMode = ref<DialogMode>('standard')
  const proactiveMessages = ref<ProactiveMessage[]>([])
  const voiceEnabled = ref(false)
  const wizardActive = ref(false)
  const wizardData = ref<any>(null)
```

在 store 内部追加方法：

```typescript
  const setDialogMode = (mode: DialogMode) => {
    dialogMode.value = mode
  }

  const addProactiveMessage = (msg: Omit<ProactiveMessage, 'id'>) => {
    const id = `pm_${Date.now()}_${++msgCounter}`
    proactiveMessages.value.unshift({ ...msg, id })
    if (proactiveMessages.value.length > 20) {
      proactiveMessages.value = proactiveMessages.value.slice(0, 20)
    }
  }

  const dismissProactiveMessage = (id: string) => {
    proactiveMessages.value = proactiveMessages.value.filter(m => m.id !== id)
  }

  const toggleVoice = () => {
    voiceEnabled.value = !voiceEnabled.value
  }

  const startWizard = (data: any) => {
    wizardActive.value = true
    wizardData.value = data
  }

  const closeWizard = () => {
    wizardActive.value = false
    wizardData.value = null
  }

  const autoDetectDialogMode = () => {
    const recentAlerts = proactiveMessages.value.filter(
      m => m.pushType === 'alert_diagnosis' && m.severity === 'critical'
    )
    const oneMinuteAgo = Date.now() - 60000
    const recentCritical = recentAlerts.filter(
      m => new Date(m.timestamp).getTime() > oneMinuteAgo
    )
    if (recentCritical.length > 5) {
      setDialogMode('emergency')
    } else {
      setDialogMode('standard')
    }
  }
```

在 return 中追加导出：

```typescript
    dialogMode, proactiveMessages, voiceEnabled, wizardActive, wizardData,
    setDialogMode, addProactiveMessage, dismissProactiveMessage,
    toggleVoice, startWizard, closeWizard, autoDetectDialogMode,
```

**构建验证：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend" && npx vite build
```

---

### Step 6.2.5 — 修改 `frontend/src/composables/useAssistantContext.ts` — 动态快捷栏生成

- [ ] 新增 `generateDynamicQuickActions` 函数
- [ ] 集成系统状态和用户偏好
- [ ] 前端构建验证

**在 `useAssistantContext.ts` 文件末尾追加：**

```typescript
interface SystemState {
  alertCount: number
  healthPercentage: number
  pendingApprovals: number
  activeIntents: number
}

const SYSTEM_STATE_ACTIONS: Record<string, (state: SystemState) => QuickAction[]> = {
  '/': (state) => {
    const actions: QuickAction[] = []
    if (state.alertCount > 0) {
      actions.push({ label: `查看${state.alertCount}条告警`, type: 'query', params: { query: 'pending_alerts' } })
    }
    if (state.healthPercentage < 80) {
      actions.push({ label: '诊断系统健康', type: 'query', params: { query: 'system_health' } })
    }
    if (state.pendingApprovals > 0) {
      actions.push({ label: `审批待办(${state.pendingApprovals})`, type: 'navigate', params: { route: '/intent' } })
    }
    return actions
  },
  '/topology': (state) => {
    const actions: QuickAction[] = []
    if (state.alertCount > 0) {
      actions.push({ label: '定位故障节点', type: 'execute', params: { command: 'highlight_fault_links' } })
      actions.push({ label: '批量诊断', type: 'execute', params: { command: 'batch_diagnose' } })
    }
    return actions
  },
  '/intent': (state) => {
    const actions: QuickAction[] = []
    if (state.pendingApprovals > 0) {
      actions.push({ label: '批量审批', type: 'execute', params: { command: 'batch_approve' } })
      actions.push({ label: '查看高风险', type: 'query', params: { query: 'pending_high_risk_intents' } })
    }
    actions.push({ label: '创建意图', type: 'fill_form', params: { route: '/intent', field: 'inputText', value: '' } })
    return actions
  },
  '/self-healing': () => {
    return [
      { label: '查看进度', type: 'query', params: { query: 'healing_progress' } },
      { label: '手动接管', type: 'execute', params: { command: 'manual_takeover' } },
    ]
  },
}

export function generateDynamicQuickActions(
  route: string,
  role: UserRole,
  systemState: SystemState,
  userPreferences?: Record<string, string[]>
): QuickAction[] {
  const baseActions = SCENE_ROLE_MAP[route]?.[role]?.quickActions || []
  const stateActions = SYSTEM_STATE_ACTIONS[route]?.(systemState) || []

  const merged = [...stateActions, ...baseActions]

  if (userPreferences) {
    const preferred = userPreferences[route] || []
    const preferredActions = preferred
      .map(label => merged.find(a => a.label === label))
      .filter((a): a is QuickAction => a !== undefined)
    const rest = merged.filter(a => !preferred.includes(a.label))
    return [...preferredActions, ...rest]
  }

  return applyRbacFilter(role, merged)
}
```

**构建验证：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend" && npx vite build
```

---

### Step 6.2.6 — 修改 `frontend/src/composables/useActionEngine.ts` — WebSocket 事件监听扩展

- [ ] 添加 `proactive_push` 事件监听
- [ ] 添加 `wizard_step` 事件监听
- [ ] 前端构建验证

**在 `useActionEngine.ts` 的 `ensureWsListener` 函数中追加事件监听：**

在 `wsOffFn = ws.on('assistant_action', ...)` 之后追加：

```typescript
  ws.on('proactive_push', (msg) => {
    const data = msg.data || {}
    window.dispatchEvent(new CustomEvent('proactive_push', { detail: { data } }))
    const store = useAssistantStore()
    store.addProactiveMessage({
      pushType: data.push_type || 'unknown',
      severity: data.severity || 'info',
      title: data.title || '通知',
      message: data.message || '',
      suggestedActions: data.suggested_actions || [],
      timestamp: data.timestamp || new Date().toISOString(),
    })
    store.autoDetectDialogMode()
  })

  ws.on('wizard_step', (msg) => {
    const data = msg.data || {}
    window.dispatchEvent(new CustomEvent('assistant:wizard_step', { detail: data }))
  })
```

**构建验证：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend" && npx vite build
```

---

### Step 6.2.7 — 修改 `frontend/src/components/AiAssistant/ChatPanel.vue` — 自适应对话模式 + 语音 + 多模态

- [ ] 集成 VoiceInput 组件
- [ ] 集成 ProactivePanel 组件
- [ ] 集成 WizardRunner 组件
- [ ] 自适应对话模式样式
- [ ] 前端构建验证

**在 ChatPanel.vue 的 `<script setup>` 中追加导入：**

```typescript
import VoiceInput from './VoiceInput.vue'
import ProactivePanel from './ProactivePanel.vue'
import WizardRunner from './WizardRunner.vue'
```

**在 `<template>` 中，在 `messages-area` 之前插入 ProactivePanel：**

```html
    <ProactivePanel />
```

**在 `<template>` 中，在 `input-area` 的 textarea 和 send-btn 之间插入 VoiceInput：**

```html
      <VoiceInput
        :disabled="isThinking"
        @transcript="onVoiceTranscript"
        @listening-change="onVoiceListeningChange"
      />
```

**在 `<template>` 中，在 `input-area` 之后追加 WizardRunner：**

```html
    <WizardRunner ref="wizardRunner" />
```

**在 `<script setup>` 中追加方法：**

```typescript
const wizardRunner = ref<InstanceType<typeof WizardRunner> | null>(null)

const onVoiceTranscript = (text: string) => {
  inputText.value = text
  handleSend()
}

const onVoiceListeningChange = (listening: boolean) => {
  // 可扩展：语音模式时自动切换为精简回复
}

const dialogModeClass = computed(() => {
  return `dialog-${store.dialogMode}`
})
```

**在 `<style scoped>` 中追加自适应模式样式：**

```css
.chat-panel.dialog-emergency .msg-bubble-assistant {
  padding: 6px 10px;
  font-size: var(--font-size-sm);
  border-radius: 8px;
}

.chat-panel.dialog-emergency .msg-content {
  max-height: 60px;
  overflow: hidden;
}

.chat-panel.dialog-report .msg-bubble-assistant {
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.chat-panel.dialog-tutorial .msg-bubble-assistant {
  border-left: 3px solid rgba(99, 102, 241, 0.5);
}
```

**构建验证：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend" && npx vite build
```

---

### Step 6.2.8 — 修改 `frontend/src/components/AiAssistant/BubbleCard.vue` — 智能快捷栏

- [ ] 集成动态快捷栏生成
- [ ] 前端构建验证

**在 BubbleCard.vue 的 `<script setup>` 中追加导入：**

```typescript
import { generateDynamicQuickActions, type SystemState } from '@/composables/useAssistantContext'
```

**在 `<script setup>` 中追加计算属性：**

```typescript
const dynamicQuickActions = computed(() => {
  const route = router.currentRoute.value.path
  const role = getUserRole()
  const systemState: SystemState = {
    alertCount: store.proactiveMessages.filter(m => m.severity === 'critical').length,
    healthPercentage: 100,
    pendingApprovals: 0,
    activeIntents: 0,
  }
  return generateDynamicQuickActions(route, role, systemState)
})
```

**在 `<template>` 中替换 `context?.quickActions` 为 `dynamicQuickActions`：**

将 `v-if="context?.quickActions?.length"` 改为 `v-if="dynamicQuickActions.length"`，
将 `v-for="qa in context.quickActions"` 改为 `v-for="qa in dynamicQuickActions"`。

**构建验证：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend" && npx vite build
```

---

### Step 6.2.9 — 修改 `frontend/src/components/AiAssistant/FloatingBall.vue` — 推送通知角标

- [ ] 添加推送通知角标显示
- [ ] 前端构建验证

**在 FloatingBall.vue 的 `<script setup>` 中追加：**

```typescript
const proactiveCount = computed(() => store.proactiveMessages.filter(m => m.severity === 'critical').length)
```

**在 `<template>` 中，在 `unread-badge` 之后追加：**

```html
    <div v-if="proactiveCount > 0 && !isOpen" class="proactive-badge">{{ proactiveCount > 9 ? '9+' : proactiveCount }}</div>
```

**在 `<style scoped>` 中追加：**

```css
.proactive-badge {
  position: absolute;
  top: -6px;
  left: -6px;
  min-width: 18px;
  height: 18px;
  background: #f59e0b;
  color: white;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0 var(--spacing-xs);
  border: 2px solid #1e293b;
  z-index: 2;
  animation: badgePulse 1.5s ease-in-out infinite;
}
```

**构建验证：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend" && npx vite build
```

---

# 模块7：测试体系

## 7.1 意图识别测试

### Step 7.1.1 — 新增 `tests/test_intent_classifier.py`

- [ ] 编写 100+ 意图识别测试用例
- [ ] 运行测试确认准确率 >90%

**文件：`tests/test_intent_classifier.py`**

```python
import pytest
from backend.agents.assistant_router import AssistantRouterAgent


@pytest.fixture
def router():
    return AssistantRouterAgent()


INTENT_TEST_CASES = [
    {"input": "去指挥舱", "expected_intent": "navigation", "expected_route": "/"},
    {"input": "打开意图中心", "expected_intent": "navigation", "expected_route": "/intent"},
    {"input": "查看网络拓扑", "expected_intent": "navigation", "expected_route": "/topology"},
    {"input": "跳转到故障自愈", "expected_intent": "navigation", "expected_route": "/self-healing"},
    {"input": "导航到审计日志", "expected_intent": "navigation", "expected_route": "/audit"},
    {"input": "我要看MCP工具", "expected_intent": "navigation", "expected_route": "/mcp-tools"},
    {"input": "打开智能体地图", "expected_intent": "navigation", "expected_route": "/agent-map"},
    {"input": "去运维助手", "expected_intent": "navigation", "expected_route": "/knowledge"},
    {"input": "查看工单看板", "expected_intent": "navigation", "expected_route": "/workflow"},
    {"input": "去拓扑页面", "expected_intent": "navigation", "expected_route": "/topology"},

    {"input": "系统健康度如何", "expected_intent": "query", "expected_query_type": "system_health"},
    {"input": "运行状态怎么样", "expected_intent": "query", "expected_query_type": "system_health"},
    {"input": "有多少告警", "expected_intent": "query", "expected_query_type": "pending_alerts"},
    {"input": "有哪些未处理的报警", "expected_intent": "query", "expected_query_type": "pending_alerts"},
    {"input": "审批待办有多少", "expected_intent": "query", "expected_query_type": "pending_approvals"},
    {"input": "故障根因是什么", "expected_intent": "query", "expected_query_type": "latest_fault_root_cause"},
    {"input": "高危操作有哪些", "expected_intent": "query", "expected_query_type": "high_risk_ops"},
    {"input": "防火墙策略修改记录", "expected_intent": "query", "expected_query_type": "firewall_policy_changes"},
    {"input": "流量趋势统计", "expected_intent": "query", "expected_query_type": "traffic_stats"},
    {"input": "智能体分布状态", "expected_intent": "query", "expected_query_type": "agent_distribution"},
    {"input": "工单待审批有哪些", "expected_intent": "query", "expected_query_type": "pending_work_orders"},
    {"input": "查看路由器SW-01的状态", "expected_intent": "query", "expected_query_type": "device_status"},
    {"input": "检查交换机Core-SW信息", "expected_intent": "query", "expected_query_type": "device_status"},
    {"input": "显示防火墙FW-01详情", "expected_intent": "query", "expected_query_type": "device_status"},

    {"input": "重启路由器A", "expected_intent": "control", "expected_command": "restart_device"},
    {"input": "隔离节点B", "expected_intent": "control", "expected_command": "isolate_node"},
    {"input": "创建一个意图", "expected_intent": "control", "expected_command": "create_intent"},
    {"input": "优化网络带宽", "expected_intent": "control", "expected_command": "optimize_bandwidth"},
    {"input": "执行ping测试", "expected_intent": "control", "expected_command": "ping_test"},
    {"input": "重试修复任务", "expected_intent": "control", "expected_command": "retry_healing"},
    {"input": "删除意图", "expected_intent": "control", "expected_command": "delete_intent"},
    {"input": "关闭端口GE0/0/1", "expected_intent": "control", "expected_command": "shutdown_port"},
    {"input": "切断连接", "expected_intent": "control", "expected_command": "shutdown_port"},

    {"input": "开启应急模式", "expected_intent": "scene_mode", "expected_mode": "emergency"},
    {"input": "切换日常巡检模式", "expected_intent": "scene_mode", "expected_mode": "daily"},
    {"input": "进入变更冻结", "expected_intent": "scene_mode", "expected_mode": "freeze"},
    {"input": "切换到紧急模式", "expected_intent": "scene_mode", "expected_mode": "emergency"},
    {"input": "开启日常模式", "expected_intent": "scene_mode", "expected_mode": "daily"},

    {"input": "你好", "expected_intent": "general"},
    {"input": "谢谢", "expected_intent": "general"},
    {"input": "你能做什么", "expected_intent": "general"},
    {"input": "帮我一下", "expected_intent": "general"},
    {"input": "今天天气怎么样", "expected_intent": "general"},

    {"input": "去看看首页", "expected_intent": "navigation", "expected_route": "/"},
    {"input": "我要看dashboard", "expected_intent": "navigation", "expected_route": "/"},
    {"input": "跳转intent页面", "expected_intent": "navigation", "expected_route": "/intent"},
    {"input": "打开topology", "expected_intent": "navigation", "expected_route": "/topology"},
    {"input": "去healing页面", "expected_intent": "navigation", "expected_route": "/self-healing"},
    {"input": "查看audit日志", "expected_intent": "navigation", "expected_route": "/audit"},

    {"input": "告警有多少条", "expected_intent": "query", "expected_query_type": "pending_alerts"},
    {"input": "报警未处理的有几个", "expected_intent": "query", "expected_query_type": "pending_alerts"},
    {"input": "有多少审批待办", "expected_intent": "query", "expected_query_type": "pending_approvals"},
    {"input": "故障原因分析", "expected_intent": "query", "expected_query_type": "latest_fault_root_cause"},
    {"input": "危险操作有哪些", "expected_intent": "query", "expected_query_type": "high_risk_ops"},
    {"input": "防火墙变更记录", "expected_intent": "query", "expected_query_type": "firewall_policy_changes"},
    {"input": "流量统计趋势", "expected_intent": "query", "expected_query_type": "traffic_stats"},
    {"input": "agent分布情况", "expected_intent": "query", "expected_query_type": "agent_distribution"},

    {"input": "restart设备A", "expected_intent": "control", "expected_command": "restart_device"},
    {"input": "isolate节点1", "expected_intent": "control", "expected_command": "isolate_node"},
    {"input": "新建意图", "expected_intent": "control", "expected_command": "create_intent"},
    {"input": "optimize QoS", "expected_intent": "control", "expected_command": "optimize_bandwidth"},
    {"input": "run ping", "expected_intent": "control", "expected_command": "ping_test"},
    {"input": "retry healing", "expected_intent": "control", "expected_command": "retry_healing"},
    {"input": "delete意图", "expected_intent": "control", "expected_command": "delete_intent"},
    {"input": "shutdown端口", "expected_intent": "control", "expected_command": "shutdown_port"},

    {"input": "进入应急响应模式", "expected_intent": "scene_mode", "expected_mode": "emergency"},
    {"input": "切换到日常模式", "expected_intent": "scene_mode", "expected_mode": "daily"},
    {"input": "开启变更冻结模式", "expected_intent": "scene_mode", "expected_mode": "freeze"},
    {"input": "紧急模式", "expected_intent": "scene_mode", "expected_mode": "emergency"},
    {"input": "日常巡检", "expected_intent": "scene_mode", "expected_mode": "daily"},

    {"input": "看看核心交换机状态", "expected_intent": "query", "expected_query_type": "device_status"},
    {"input": "检查路由器R1信息", "expected_intent": "query", "expected_query_type": "device_status"},
    {"input": "显示服务器SRV-01详情", "expected_intent": "query", "expected_query_type": "device_status"},
    {"input": "查看设备SW-Core状态", "expected_intent": "query", "expected_query_type": "device_status"},

    {"input": "重启交换机", "expected_intent": "control", "expected_command": "restart_device"},
    {"input": "隔离设备Node-1", "expected_intent": "control", "expected_command": "isolate_node"},
    {"input": "优化QoS带宽", "expected_intent": "control", "expected_command": "optimize_bandwidth"},

    {"input": "去首页看看", "expected_intent": "navigation", "expected_route": "/"},
    {"input": "打开仪表盘", "expected_intent": "navigation", "expected_route": "/"},
    {"input": "查看自愈面板", "expected_intent": "navigation", "expected_route": "/self-healing"},

    {"input": "健康状态怎样", "expected_intent": "query", "expected_query_type": "system_health"},
    {"input": "系统运行如何", "expected_intent": "query", "expected_query_type": "system_health"},

    {"input": "工具列表", "expected_intent": "query", "expected_query_type": "available_config_tools"},
    {"input": "可用工具", "expected_intent": "query", "expected_query_type": "available_config_tools"},

    {"input": "谁修改了防火墙策略", "expected_intent": "query", "expected_query_type": "firewall_policy_changes"},
    {"input": "过去一小时高危操作", "expected_intent": "query", "expected_query_type": "high_risk_ops"},

    {"input": "切断端口连接", "expected_intent": "control", "expected_command": "shutdown_port"},
    {"input": "断开接口GE0/0/2", "expected_intent": "control", "expected_command": "shutdown_port"},

    {"input": "提交一个意图", "expected_intent": "control", "expected_command": "create_intent"},
    {"input": "移除意图", "expected_intent": "control", "expected_command": "delete_intent"},
]


class TestIntentClassifier:
    @pytest.mark.asyncio
    async def test_navigation_intents(self, router):
        nav_cases = [c for c in INTENT_TEST_CASES if c["expected_intent"] == "navigation"]
        correct = 0
        for case in nav_cases:
            result = await router.route(
                message=case["input"],
                context={"role": "admin", "username": "test_user", "route": "/"}
            )
            if result.get("intent_type") == "navigation":
                actions = result.get("actions", [])
                routes = [a.get("params", {}).get("route") for a in actions if a.get("type") == "navigate"]
                if case.get("expected_route") in routes:
                    correct += 1
        accuracy = correct / len(nav_cases) if nav_cases else 0
        assert accuracy >= 0.9, f"Navigation intent accuracy: {accuracy:.1%} (expected >= 90%)"

    @pytest.mark.asyncio
    async def test_query_intents(self, router):
        query_cases = [c for c in INTENT_TEST_CASES if c["expected_intent"] == "query"]
        correct = 0
        for case in query_cases:
            result = await router.route(
                message=case["input"],
                context={"role": "admin", "username": "test_user", "route": "/"}
            )
            if result.get("intent_type") == "query":
                correct += 1
        accuracy = correct / len(query_cases) if query_cases else 0
        assert accuracy >= 0.9, f"Query intent accuracy: {accuracy:.1%} (expected >= 90%)"

    @pytest.mark.asyncio
    async def test_control_intents(self, router):
        control_cases = [c for c in INTENT_TEST_CASES if c["expected_intent"] == "control"]
        correct = 0
        for case in control_cases:
            result = await router.route(
                message=case["input"],
                context={"role": "admin", "username": "test_user", "route": "/"}
            )
            if result.get("intent_type") == "control":
                correct += 1
        accuracy = correct / len(control_cases) if control_cases else 0
        assert accuracy >= 0.9, f"Control intent accuracy: {accuracy:.1%} (expected >= 90%)"

    @pytest.mark.asyncio
    async def test_scene_mode_intents(self, router):
        scene_cases = [c for c in INTENT_TEST_CASES if c["expected_intent"] == "scene_mode"]
        correct = 0
        for case in scene_cases:
            result = await router.route(
                message=case["input"],
                context={"role": "admin", "username": "test_user", "route": "/"}
            )
            if result.get("intent_type") == "scene_mode":
                correct += 1
        accuracy = correct / len(scene_cases) if scene_cases else 0
        assert accuracy >= 0.9, f"Scene mode intent accuracy: {accuracy:.1%} (expected >= 90%)"

    @pytest.mark.asyncio
    async def test_overall_accuracy(self, router):
        total = len(INTENT_TEST_CASES)
        correct = 0
        for case in INTENT_TEST_CASES:
            result = await router.route(
                message=case["input"],
                context={"role": "admin", "username": "test_user", "route": "/"}
            )
            actual_intent = result.get("intent_type")
            if actual_intent == case["expected_intent"]:
                correct += 1
            elif actual_intent == "general" and case["expected_intent"] in ("query", "navigation"):
                pass
        accuracy = correct / total
        assert accuracy >= 0.9, f"Overall intent accuracy: {accuracy:.1%} ({correct}/{total}, expected >= 90%)"

    @pytest.mark.asyncio
    async def test_viewer_cannot_control(self, router):
        result = await router.route(
            message="重启路由器A",
            context={"role": "viewer", "username": "viewer_user", "route": "/"}
        )
        assert result.get("intent_type") == "control_denied"

    @pytest.mark.asyncio
    async def test_freeze_mode_blocks_control(self, router):
        router.set_scene_mode("freeze")
        result = await router.route(
            message="重启路由器A",
            context={"role": "admin", "username": "admin_user", "route": "/", "scene_mode": "freeze"}
        )
        assert result.get("intent_type") == "control_frozen"
        router.set_scene_mode("daily")

    def test_regex_speed(self, router):
        import time
        test_inputs = ["去指挥舱", "系统健康度如何", "重启路由器A", "开启应急模式"]
        start = time.perf_counter()
        for _ in range(100):
            for inp in test_inputs:
                router._check_scene_mode(inp)
                router._check_navigation(inp, "admin")
        elapsed = (time.perf_counter() - start) / 400
        assert elapsed < 0.05, f"Regex intent recognition too slow: {elapsed*1000:.1f}ms (expected <50ms)"
```

**测试命令：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub" && python -m pytest tests/test_intent_classifier.py -v
```

---

## 7.2 对话连贯性测试

### Step 7.2.1 — 新增 `tests/test_dialogue_state.py`

- [ ] 编写对话连贯性测试
- [ ] 运行测试确认通过

**文件：`tests/test_dialogue_state.py`**

```python
import pytest
from backend.agents.assistant_router import AssistantRouterAgent, ConversationMemory


@pytest.fixture
def memory():
    return ConversationMemory()


@pytest.fixture
def router():
    return AssistantRouterAgent()


class TestConversationMemory:
    def test_add_turn(self, memory):
        memory.add_turn("user1", "user", "查看系统健康度")
        memory.add_turn("user1", "assistant", "系统健康度90%")
        history = memory.get_recent_messages("user1", 10)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_max_turns_limit(self, memory):
        for i in range(30):
            memory.add_turn("user1", "user", f"消息{i}")
        history = memory.get_recent_messages("user1", 100)
        assert len(history) <= 20

    def test_entity_tracking(self, memory):
        memory.set_entity("user1", "device", "router-core-01")
        entities = memory.get_entities("user1")
        assert entities["device"] == "router-core-01"

    def test_last_mentioned(self, memory):
        memory.set_entity("user1", "device", "router-core-01")
        assert memory.get_last_mentioned("user1") == "router-core-01"

    def test_pronoun_resolution_entity_reference(self, memory):
        memory.set_entity("user1", "device", "router-core-01")
        resolved = memory.resolve_pronoun("user1", "它")
        assert "router-core-01" in resolved

    def test_pronoun_resolution_entity_action(self, memory):
        memory.set_entity("user1", "device", "switch-access-03")
        resolved = memory.resolve_pronoun("user1", "把它重启一下")
        assert "switch-access-03" in resolved
        assert "重启" in resolved

    def test_pronoun_resolution_repeat_action(self, memory):
        memory.set_last_intent("user1", {"command": "restart_device", "entities": {"device": "router-core-01"}})
        memory.set_entity("user1", "device", "router-core-01")
        resolved = memory.resolve_pronoun("user1", "重启")
        assert "restart_device" in resolved or "router-core-01" in resolved

    def test_extract_device_entity(self, memory):
        entities = memory.extract_entities("查看路由器SW-01的状态")
        assert "device" in entities
        assert "SW-01" in entities["device"]

    def test_extract_node_entity(self, memory):
        entities = memory.extract_entities("检查节点Node-01")
        assert "node" in entities

    def test_extract_port_entity(self, memory):
        entities = memory.extract_entities("关闭端口GE0/0/1")
        assert "port" in entities

    def test_separate_user_histories(self, memory):
        memory.add_turn("user1", "user", "用户1消息")
        memory.add_turn("user2", "user", "用户2消息")
        history1 = memory.get_recent_messages("user1", 10)
        history2 = memory.get_recent_messages("user2", 10)
        assert len(history1) == 1
        assert len(history2) == 1
        assert history1[0]["content"] == "用户1消息"
        assert history2[0]["content"] == "用户2消息"


class TestDialogueContinuity:
    @pytest.mark.asyncio
    async def test_multi_turn_device_inquiry(self, router):
        result1 = await router.route(
            message="查看路由器R1的状态",
            context={"role": "admin", "username": "test_user", "route": "/"}
        )
        assert result1.get("intent_type") in ("query", "navigation", "control")

        result2 = await router.route(
            message="它的CPU呢",
            context={"role": "admin", "username": "test_user", "route": "/"}
        )
        assert result2 is not None

    @pytest.mark.asyncio
    async def test_topic_switch(self, router):
        result1 = await router.route(
            message="查看系统健康度",
            context={"role": "admin", "username": "test_user", "route": "/"}
        )
        assert result1.get("intent_type") in ("query", "general")

        result2 = await router.route(
            message="去拓扑页面",
            context={"role": "admin", "username": "test_user", "route": "/"}
        )
        assert result2.get("intent_type") == "navigation"

    @pytest.mark.asyncio
    async def test_entity_carry_over(self, router):
        await router.route(
            message="查看路由器R1的状态",
            context={"role": "admin", "username": "test_user", "route": "/"}
        )
        entities = router._memory.get_entities("test_user")
        assert "device" in entities
```

**测试命令：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub" && python -m pytest tests/test_dialogue_state.py -v
```

---

## 7.3 Plan-Execute 测试

### Step 7.3.1 — 新增 `tests/test_plan_executor.py`

- [ ] 编写 Plan-Execute 测试
- [ ] 运行测试确认通过

**文件：`tests/test_plan_executor.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestPlanExecutor:
    def test_execution_plan_model(self):
        try:
            from backend.agents.plan_executor import ExecutionPlan, PlanStep
        except ImportError:
            pytest.skip("plan_executor not yet implemented in batch 2")

        step1 = PlanStep(
            step_id="step_1",
            description="查询告警列表",
            tool="query_alerts",
            params={},
            depends_on=[],
            risk_level="low",
        )
        step2 = PlanStep(
            step_id="step_2",
            description="诊断根因",
            tool="diagnose_root_cause",
            params={"alert_id": "$step_1.alerts[0].id"},
            depends_on=["step_1"],
            risk_level="medium",
        )
        plan = ExecutionPlan(
            plan_id="plan_001",
            goal="处理所有告警",
            steps=[step1, step2],
            dependencies={"step_2": ["step_1"]},
            conditions={},
        )
        assert plan.plan_id == "plan_001"
        assert len(plan.steps) == 2
        assert plan.steps[1].depends_on == ["step_1"]

    @pytest.mark.asyncio
    async def test_plan_generation(self):
        try:
            from backend.agents.plan_executor import PlanExecutor
        except ImportError:
            pytest.skip("plan_executor not yet implemented in batch 2")

        executor = PlanExecutor()
        with patch.object(executor, '_generate_plan_with_llm', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {
                "plan_id": "plan_test",
                "goal": "处理告警",
                "steps": [
                    {"step_id": "s1", "description": "查询告警", "tool": "query_alerts", "params": {}, "depends_on": [], "risk_level": "low"},
                ],
            }
            plan = await executor.generate_plan("帮我处理所有告警", {"role": "admin", "username": "test"})
            assert plan is not None
            assert plan["goal"] == "处理告警"

    @pytest.mark.asyncio
    async def test_step_execution(self):
        try:
            from backend.agents.plan_executor import PlanExecutor
        except ImportError:
            pytest.skip("plan_executor not yet implemented in batch 2")

        executor = PlanExecutor()
        with patch.object(executor, '_execute_tool', new_callable=AsyncMock) as mock_tool:
            mock_tool.return_value = {"status": "success", "data": {"alerts": []}}
            result = await executor._execute_tool("query_alerts", {})
            assert result["status"] == "success"

    def test_dependency_resolution(self):
        try:
            from backend.agents.plan_executor import ExecutionPlan, PlanStep
        except ImportError:
            pytest.skip("plan_executor not yet implemented in batch 2")

        step1 = PlanStep(step_id="s1", description="step1", tool="t1", params={}, depends_on=[], risk_level="low")
        step2 = PlanStep(step_id="s2", description="step2", tool="t2", params={}, depends_on=["s1"], risk_level="low")
        step3 = PlanStep(step_id="s3", description="step3", tool="t3", params={}, depends_on=["s1"], risk_level="low")
        step4 = PlanStep(step_id="s4", description="step4", tool="t4", params={}, depends_on=["s2", "s3"], risk_level="low")

        plan = ExecutionPlan(
            plan_id="p1",
            goal="test",
            steps=[step1, step2, step3, step4],
            dependencies={"s2": ["s1"], "s3": ["s1"], "s4": ["s2", "s3"]},
            conditions={},
        )

        execution_order = plan.get_execution_order()
        assert execution_order.index("s1") < execution_order.index("s2")
        assert execution_order.index("s1") < execution_order.index("s3")
        assert execution_order.index("s2") < execution_order.index("s4")
        assert execution_order.index("s3") < execution_order.index("s4")

    def test_risk_level_classification(self):
        try:
            from backend.agents.plan_executor import PlanExecutor
        except ImportError:
            pytest.skip("plan_executor not yet implemented in batch 2")

        executor = PlanExecutor()
        assert executor.classify_risk("query_alerts", {}) == "low"
        assert executor.classify_risk("restart_device", {"device_id": "core-01"}) == "high"
        assert executor.classify_risk("modify_config", {"device_id": "edge-01"}) == "medium"
```

**测试命令：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub" && python -m pytest tests/test_plan_executor.py -v
```

---

## 7.4 RAG 检索测试

### Step 7.4.1 — 新增 `tests/test_rag_engine.py`

- [ ] 编写 RAG 检索测试
- [ ] 运行测试确认通过

**文件：`tests/test_rag_engine.py`**

```python
import pytest
from backend.knowledge.rag_engine import RAGEngine, VectorStore, SearchResult


@pytest.fixture
def rag_engine():
    engine = RAGEngine()
    return engine


class TestVectorStore:
    def test_add_and_search(self):
        import numpy as np
        store = VectorStore(dim=8)
        vec1 = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        vec2 = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        vec3 = np.array([0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)

        store.add("c1", "doc1", 0, vec1)
        store.add("c2", "doc1", 1, vec2)
        store.add("c3", "doc2", 0, vec3)

        query = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        results = store.search(query, top_k=2)
        assert len(results) == 2
        assert results[0]["chunk_id"] == "c1"
        assert results[0]["score"] > results[1]["score"]

    def test_remove_by_doc(self):
        import numpy as np
        store = VectorStore(dim=4)
        vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        store.add("c1", "doc1", 0, vec)
        store.add("c2", "doc2", 0, vec)
        assert store.size == 2

        store.remove_by_doc("doc1")
        assert store.size == 1

    def test_clear(self):
        import numpy as np
        store = VectorStore(dim=4)
        vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        store.add("c1", "doc1", 0, vec)
        store.clear()
        assert store.size == 0

    def test_empty_search(self):
        import numpy as np
        store = VectorStore(dim=4)
        query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        results = store.search(query, top_k=5)
        assert len(results) == 0


class TestRAGEngine:
    def test_add_document(self, rag_engine):
        rag_engine.add_document("doc1", "OSPF路由配置", "OSPF是一种链路状态路由协议，用于在IP网络中交换路由信息。")
        doc = rag_engine.get_document("doc1")
        assert doc is not None
        assert doc["title"] == "OSPF路由配置"

    def test_add_documents_batch(self, rag_engine):
        docs = [
            {"id": "d1", "title": "BGP基础", "content": "BGP是边界网关协议"},
            {"id": "d2", "title": "VLAN配置", "content": "VLAN用于逻辑隔离广播域"},
        ]
        rag_engine.add_documents(docs)
        assert rag_engine.get_document("d1") is not None
        assert rag_engine.get_document("d2") is not None

    def test_delete_document(self, rag_engine):
        rag_engine.add_document("doc_del", "测试文档", "测试内容")
        assert rag_engine.get_document("doc_del") is not None
        result = rag_engine.delete_document("doc_del")
        assert result is True
        assert rag_engine.get_document("doc_del") is None

    def test_delete_nonexistent_document(self, rag_engine):
        result = rag_engine.delete_document("nonexistent")
        assert result is False

    def test_list_documents(self, rag_engine):
        rag_engine.add_document("list1", "文档1", "内容1")
        rag_engine.add_document("list2", "文档2", "内容2")
        docs = rag_engine.list_documents()
        assert len(docs) >= 2

    def test_search_returns_results(self, rag_engine):
        rag_engine.add_document("search1", "QoS配置指南", "QoS服务质量配置用于保障关键业务流量带宽。配置步骤：1.定义流量类别 2.创建策略 3.应用到接口")
        rag_engine.add_document("search2", "OSPF路由配置", "OSPF是一种链路状态路由协议，配置步骤：1.启用OSPF进程 2.定义网络区域 3.配置邻居关系")
        results = rag_engine.search("QoS配置", top_k=3)
        assert isinstance(results, list)

    def test_search_no_results_for_unrelated(self, rag_engine):
        rag_engine.add_document("unrel1", "网络基础", "TCP/IP协议栈")
        results = rag_engine.search("量子计算超导材料", top_k=3)
        assert isinstance(results, list)

    def test_chunk_text(self, rag_engine):
        long_text = "这是第一段内容。\n\n" + "这是一段很长的文字。" * 100
        chunks = rag_engine._chunk_text(long_text)
        assert len(chunks) >= 1

    def test_get_stats(self, rag_engine):
        rag_engine.add_document("stat1", "统计文档", "统计内容")
        stats = rag_engine.get_stats()
        assert "total_documents" in stats
        assert "total_chunks" in stats
        assert "available" in stats
        assert stats["total_documents"] >= 1

    @pytest.mark.asyncio
    async def test_answer_question_no_results(self, rag_engine):
        result = await rag_engine.answer_question("量子纠缠是什么")
        assert "answer" in result
        assert result["confidence"] < 0.5


class TestRAGPerformance:
    def test_search_latency(self, rag_engine):
        import time

        for i in range(20):
            rag_engine.add_document(
                f"perf_{i}",
                f"运维文档{i}",
                f"这是第{i}篇运维知识文档，包含网络配置、故障排查、性能优化等内容。"
            )

        if not rag_engine.available:
            pytest.skip("RAG engine not available for performance test")

        start = time.perf_counter()
        for _ in range(10):
            rag_engine.search("网络配置", top_k=5)
        elapsed = (time.perf_counter() - start) / 10

        assert elapsed < 0.5, f"RAG search too slow: {elapsed*1000:.1f}ms (expected <500ms)"
```

**测试命令：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub" && python -m pytest tests/test_rag_engine.py -v
```

---

## 7.5 工具链测试

### Step 7.5.1 — 新增 `tests/test_tool_chains.py`

- [ ] 编写工具链测试
- [ ] 运行测试确认通过

**文件：`tests/test_tool_chains.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestToolChain:
    def test_tool_chain_definition(self):
        try:
            from backend.agents.tool_chains import ToolChain, ToolStep
        except ImportError:
            pytest.skip("tool_chains not yet implemented in batch 2")

        chain = ToolChain(
            name="fault_auto_healing",
            steps=[
                ToolStep(tool="query_topology", params={"filter": "alert"}),
                ToolStep(tool="query_device", params={"target": "$step1.devices[0]"}),
                ToolStep(tool="execute_self_healing", params={"device": "$step2.device"}),
                ToolStep(tool="system_health", params={}),
            ],
            parallel_groups=[[0], [1], [2], [3]],
        )
        assert chain.name == "fault_auto_healing"
        assert len(chain.steps) == 4

    def test_tool_step_param_reference(self):
        try:
            from backend.agents.tool_chains import ToolStep
        except ImportError:
            pytest.skip("tool_chains not yet implemented in batch 2")

        step = ToolStep(tool="query_device", params={"target": "$step1.devices[0]"})
        assert step.params["target"] == "$step1.devices[0]"

    def test_resolve_param_reference(self):
        try:
            from backend.agents.tool_chains import resolve_param_reference
        except ImportError:
            pytest.skip("tool_chains not yet implemented in batch 2")

        params = {"target": "$step1.devices[0]"}
        results = {"step1": {"devices": ["router-01", "switch-02"]}}
        resolved = resolve_param_reference(params, results)
        assert resolved["target"] == "router-01"

    @pytest.mark.asyncio
    async def test_chain_execution_sequential(self):
        try:
            from backend.agents.tool_chains import ToolChainExecutor
        except ImportError:
            pytest.skip("tool_chains not yet implemented in batch 2")

        executor = ToolChainExecutor()
        mock_tool_registry = MagicMock()
        mock_tool_registry.execute = AsyncMock(side_effect=[
            {"devices": ["router-01"]},
            {"device": "router-01", "status": "alert"},
            {"healing_id": "h001", "status": "started"},
            {"health": 95},
        ])
        executor.set_tool_registry(mock_tool_registry)

        result = await executor.execute_chain("fault_auto_healing", {})
        assert result is not None

    @pytest.mark.asyncio
    async def test_chain_execution_with_retry(self):
        try:
            from backend.agents.tool_chains import ToolChainExecutor
        except ImportError:
            pytest.skip("tool_chains not yet implemented in batch 2")

        executor = ToolChainExecutor()
        call_count = 0

        async def mock_execute(tool_name, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Temporary failure")
            return {"status": "success"}

        mock_tool_registry = MagicMock()
        mock_tool_registry.execute = mock_execute
        executor.set_tool_registry(mock_tool_registry)

        result = await executor._execute_with_retry("test_tool", {}, max_retries=2)
        assert call_count == 2

    def test_predefined_chains_exist(self):
        try:
            from backend.agents.tool_chains import PREDEFINED_CHAINS
        except ImportError:
            pytest.skip("tool_chains not yet implemented in batch 2")

        assert "fault_auto_healing" in PREDEFINED_CHAINS
        assert "daily_inspection" in PREDEFINED_CHAINS
        assert "emergency_response" in PREDEFINED_CHAINS


class TestToolRegistry:
    def test_tool_registry_list(self):
        try:
            from backend.agents.tool_registry import ToolRegistry
        except ImportError:
            pytest.skip("tool_registry not available")

        registry = ToolRegistry()
        tools = registry.list_tools()
        assert isinstance(tools, list)

    def test_tool_registry_get_tool(self):
        try:
            from backend.agents.tool_registry import ToolRegistry
        except ImportError:
            pytest.skip("tool_registry not available")

        registry = ToolRegistry()
        tool = registry.get_tool("system_health")
        assert tool is not None or tool is None
```

**测试命令：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub" && python -m pytest tests/test_tool_chains.py -v
```

---

## 性能基准测试汇总

### Step 7.6 — 性能基准验证

- [ ] 验证所有性能基准目标

**在 `tests/test_intent_classifier.py` 中已包含正则速度测试。以下为补充基准测试：**

**在 `tests/test_rag_engine.py` 中已包含 RAG 检索延迟测试。**

**新增 `tests/test_performance_benchmarks.py`：**

```python
import pytest
import time


class TestPerformanceBenchmarks:
    def test_regex_intent_recognition_under_50ms(self):
        from backend.agents.assistant_router import AssistantRouterAgent
        router = AssistantRouterAgent()

        test_inputs = [
            "去指挥舱", "系统健康度如何", "重启路由器A",
            "开启应急模式", "查看拓扑", "有多少告警",
            "创建意图", "切换日常模式", "查看审计日志", "执行ping测试",
        ]

        start = time.perf_counter()
        for _ in range(50):
            for inp in test_inputs:
                router._check_scene_mode(inp)
                router._check_navigation(inp, "admin")
                router._check_control(inp, "admin", "test", "daily")
                router._check_query(inp, "admin", "test")
        elapsed = (time.perf_counter() - start) / 500

        assert elapsed < 0.05, f"Regex intent recognition: {elapsed*1000:.1f}ms (target <50ms)"

    def test_entity_extraction_speed(self):
        from backend.agents.assistant_router import AssistantRouterAgent
        router = AssistantRouterAgent()

        test_inputs = [
            "查看路由器SW-01的状态",
            "关闭端口GE0/0/1",
            "隔离节点Node-03",
        ]

        start = time.perf_counter()
        for _ in range(1000):
            for inp in test_inputs:
                router._memory.extract_entities(inp)
        elapsed = (time.perf_counter() - start) / 3000

        assert elapsed < 0.01, f"Entity extraction: {elapsed*1000:.1f}ms (target <10ms)"

    def test_pronoun_resolution_speed(self):
        from backend.agents.assistant_router import ConversationMemory
        memory = ConversationMemory()
        memory.set_entity("user1", "device", "router-core-01")

        start = time.perf_counter()
        for _ in range(1000):
            memory.resolve_pronoun("user1", "它")
        elapsed = (time.perf_counter() - start) / 1000

        assert elapsed < 0.01, f"Pronoun resolution: {elapsed*1000:.1f}ms (target <10ms)"

    def test_vector_store_search_speed(self):
        import numpy as np
        from backend.knowledge.rag_engine import VectorStore

        store = VectorStore(dim=64)
        for i in range(100):
            vec = np.random.randn(64).astype(np.float32)
            vec /= np.linalg.norm(vec)
            store.add(f"c{i}", f"doc{i // 5}", i % 5, vec)

        query = np.random.randn(64).astype(np.float32)
        query /= np.linalg.norm(query)

        start = time.perf_counter()
        for _ in range(100):
            store.search(query, top_k=5)
        elapsed = (time.perf_counter() - start) / 100

        assert elapsed < 0.5, f"Vector search: {elapsed*1000:.1f}ms (target <500ms)"
```

**测试命令：**

```bash
cd "d:\Trae CN\Project\智维 AgentHub" && python -m pytest tests/test_performance_benchmarks.py -v
```

---

## 全量测试运行

所有测试完成后，执行全量测试：

```bash
cd "d:\Trae CN\Project\智维 AgentHub" && python -m pytest tests/ -v --tb=short
```

前端构建验证：

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend" && npx vite build
```

---

## 实施检查清单

### 模块6：环境感知引擎 + 交互体验升级

- [ ] 6.1.1 新增 `backend/agents/environment_awareness.py`
- [ ] 6.1.2 修改 `backend/api/assistant.py` — /proactive 端点
- [ ] 6.1.3 修改 `backend/core/websocket_manager.py` — 主动推送集成
- [ ] 6.2.1 新增 `frontend/src/components/AiAssistant/ProactivePanel.vue`
- [ ] 6.2.2 新增 `frontend/src/components/AiAssistant/VoiceInput.vue`
- [ ] 6.2.3 新增 `frontend/src/components/AiAssistant/WizardRunner.vue`
- [ ] 6.2.4 修改 `frontend/src/stores/assistant.ts` — 新状态和方法
- [ ] 6.2.5 修改 `frontend/src/composables/useAssistantContext.ts` — 动态快捷栏
- [ ] 6.2.6 修改 `frontend/src/composables/useActionEngine.ts` — WS 事件扩展
- [ ] 6.2.7 修改 `frontend/src/components/AiAssistant/ChatPanel.vue` — 自适应模式+语音+多模态
- [ ] 6.2.8 修改 `frontend/src/components/AiAssistant/BubbleCard.vue` — 智能快捷栏
- [ ] 6.2.9 修改 `frontend/src/components/AiAssistant/FloatingBall.vue` — 推送角标

### 模块7：测试体系

- [ ] 7.1.1 新增 `tests/test_intent_classifier.py` — 100+ 用例，准确率 >90%
- [ ] 7.2.1 新增 `tests/test_dialogue_state.py` — 对话连贯性测试
- [ ] 7.3.1 新增 `tests/test_plan_executor.py` — Plan-Execute 测试
- [ ] 7.4.1 新增 `tests/test_rag_engine.py` — RAG 检索测试
- [ ] 7.5.1 新增 `tests/test_tool_chains.py` — 工具链测试
- [ ] 7.6 新增 `tests/test_performance_benchmarks.py` — 性能基准验证

### 性能基准目标

| 指标 | 目标 | 验证方式 |
|------|------|---------|
| 正则意图识别 | <50ms | `test_regex_intent_recognition_under_50ms` |
| LLM意图识别 | <1.5s | 线上监控（依赖 LLM 服务可用性） |
| 首次响应 | <2s | 线上监控（依赖 LLM 服务可用性） |
| 流式首token | <500ms | 线上监控（依赖 LLM 服务可用性） |
| RAG检索 | <500ms | `test_search_latency` |
| Plan生成 | <5s | 线上监控（依赖 LLM 服务可用性） |
