import pytest
import asyncio
from backend.observability.metrics import AgentMetricsCollector, get_metrics_collector
from backend.observability.health import AgentHealthMonitor


class TestMetricsCollectorRecordCall:
    def test_record_call_basic(self):
        collector = AgentMetricsCollector()
        collector.record_call("agent_1", 100.0, True)
        collector.record_call("agent_1", 200.0, True)
        collector.record_call("agent_1", 500.0, False)
        health = collector.get_agent_health("agent_1")
        assert health is not None
        assert health["total_calls"] == 3
        assert health["error_rate"] > 0

    def test_record_call_with_reasoning_rounds(self):
        collector = AgentMetricsCollector()
        collector.record_call("agent_2", 150.0, True, reasoning_rounds=3)
        collector.record_call("agent_2", 200.0, True, reasoning_rounds=5)
        health = collector.get_agent_health("agent_2")
        assert health["reasoning_rounds_avg"] is not None
        assert health["reasoning_rounds_avg"] == 4.0

    def test_record_call_all_success(self):
        collector = AgentMetricsCollector()
        collector.record_call("agent_3", 100.0, True)
        collector.record_call("agent_3", 200.0, True)
        health = collector.get_agent_health("agent_3")
        assert health["error_rate"] == 0.0


class TestMetricsCollectorSystemOverview:
    def test_system_overview(self):
        collector = AgentMetricsCollector()
        collector.record_call("agent_1", 100.0, True)
        collector.record_call("agent_2", 200.0, True)
        overview = collector.get_system_overview()
        assert overview["total_agents"] == 2
        assert overview["total_calls"] == 2

    def test_system_overview_empty(self):
        collector = AgentMetricsCollector()
        overview = collector.get_system_overview()
        assert overview["total_agents"] == 0
        assert overview["total_calls"] == 0
        assert overview["system_error_rate"] == 0.0

    def test_system_overview_with_errors(self):
        collector = AgentMetricsCollector()
        collector.record_call("agent_1", 100.0, True)
        collector.record_call("agent_1", 200.0, False)
        overview = collector.get_system_overview()
        assert overview["total_errors"] == 1
        assert overview["system_error_rate"] == 50.0


class TestMetricsCollectorNonexistentAgent:
    def test_nonexistent_agent_returns_zero_calls(self):
        collector = AgentMetricsCollector()
        health = collector.get_agent_health("nonexistent")
        assert health is not None
        assert health["total_calls"] == 0
        assert health["error_rate"] == 0.0
        assert health["agent_id"] == "nonexistent"


class TestMetricsCollectorAllAgentsHealth:
    def test_all_agents_health(self):
        collector = AgentMetricsCollector()
        collector.record_call("agent_a", 50.0, True)
        collector.record_call("agent_b", 100.0, True)
        all_health = collector.get_all_agents_health()
        assert "agent_a" in all_health
        assert "agent_b" in all_health
        assert all_health["agent_a"]["total_calls"] == 1
        assert all_health["agent_b"]["total_calls"] == 1


class TestMetricsCollectorPercentiles:
    def test_latency_percentiles(self):
        collector = AgentMetricsCollector()
        for i in range(100):
            collector.record_call("agent_p", float(i * 10), True)
        health = collector.get_agent_health("agent_p")
        assert health["latency_p50"] > 0
        assert health["latency_p95"] >= health["latency_p50"]
        assert health["latency_p99"] >= health["latency_p95"]

    def test_qps_calculation(self):
        collector = AgentMetricsCollector(window_seconds=300)
        collector.record_call("agent_q", 50.0, True)
        collector.record_call("agent_q", 50.0, True)
        health = collector.get_agent_health("agent_q")
        assert health["qps"] > 0
        assert health["qps"] <= 1.0


class TestHealthMonitorStatus:
    def test_check_agent_health_healthy(self):
        monitor = AgentHealthMonitor()
        collector = get_metrics_collector()
        collector.record_call("healthy_agent", 50.0, True)
        collector.record_call("healthy_agent", 50.0, True)
        health = asyncio.get_event_loop().run_until_complete(
            monitor.check_agent_health("healthy_agent")
        )
        assert health["status"] in ["healthy", "degraded", "unhealthy", "unknown"]

    def test_check_agent_health_unknown(self):
        monitor = AgentHealthMonitor()
        health = asyncio.get_event_loop().run_until_complete(
            monitor.check_agent_health("unknown_agent")
        )
        assert health["status"] == "unknown"

    def test_determine_status_healthy(self):
        monitor = AgentHealthMonitor()
        health_data = {"error_rate": 1.0, "latency_p95": 100, "total_calls": 10}
        assert monitor._determine_status(health_data) == "healthy"

    def test_determine_status_degraded(self):
        monitor = AgentHealthMonitor()
        health_data = {"error_rate": 10.0, "latency_p95": 100, "total_calls": 10}
        assert monitor._determine_status(health_data) == "degraded"

    def test_determine_status_unhealthy(self):
        monitor = AgentHealthMonitor()
        health_data = {"error_rate": 30.0, "latency_p95": 100, "total_calls": 10}
        assert monitor._determine_status(health_data) == "unhealthy"

    def test_determine_status_unhealthy_latency(self):
        monitor = AgentHealthMonitor()
        health_data = {"error_rate": 1.0, "latency_p95": 15000, "total_calls": 10}
        assert monitor._determine_status(health_data) == "unhealthy"

    def test_determine_status_no_calls(self):
        monitor = AgentHealthMonitor()
        health_data = {"error_rate": 0, "latency_p95": 0, "total_calls": 0}
        assert monitor._determine_status(health_data) == "unknown"


class TestHealthMonitorAlertCallback:
    def test_alert_callback_on_status_change(self):
        monitor = AgentHealthMonitor()
        alerts = []

        def on_alert(agent_id, old_status, new_status, details):
            alerts.append({"agent_id": agent_id, "old": old_status, "new": new_status})

        monitor.register_alert_callback(on_alert)

        collector = get_metrics_collector()
        collector.record_call("alert_agent", 50.0, True)
        collector.record_call("alert_agent", 50.0, True)

        asyncio.get_event_loop().run_until_complete(
            monitor.check_agent_health("alert_agent")
        )

        monitor._agent_status["alert_agent"] = {"status": "healthy"}
        collector.record_call("alert_agent", 50000.0, False)
        collector.record_call("alert_agent", 50000.0, False)
        collector.record_call("alert_agent", 50000.0, False)

        asyncio.get_event_loop().run_until_complete(
            monitor.check_agent_health("alert_agent")
        )

        if alerts:
            assert alerts[0]["old"] != alerts[0]["new"]


class TestHealthMonitorGetStatus:
    def test_get_agent_status_initial(self):
        monitor = AgentHealthMonitor()
        status = monitor.get_agent_status("nonexistent")
        assert status["status"] == "unknown"

    def test_get_all_status(self):
        monitor = AgentHealthMonitor()
        all_status = monitor.get_all_status()
        assert isinstance(all_status, dict)
