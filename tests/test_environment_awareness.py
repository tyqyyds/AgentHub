import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta


@pytest.fixture
def mock_ws_manager():
    manager = MagicMock()
    manager.send_to_user = AsyncMock()
    manager.broadcast = AsyncMock()
    return manager


@pytest.fixture
def engine(mock_ws_manager):
    from backend.agents.environment_awareness import EnvironmentAwarenessEngine
    e = EnvironmentAwarenessEngine()
    e.set_ws_manager(mock_ws_manager)
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
        user_patterns = [
            {"action": "daily_inspection", "hour": now.hour, "minute": now.minute, "day_of_week": now.weekday()},
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
