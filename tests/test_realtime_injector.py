import pytest
from backend.knowledge.realtime_injector import (
    RealtimeKnowledgeInjector,
    KnowledgeItem,
    get_realtime_injector,
)


class TestKnowledgeItem:
    def test_create_item(self):
        item = KnowledgeItem(
            source="alert",
            title="核心路由器CPU告警",
            content="路由器core-router-01 CPU使用率达到95%",
            severity="critical",
            metadata={"device": "core-router-01"},
        )
        assert item.source == "alert"
        assert item.severity == "critical"


class TestRealtimeInjector:
    def test_inject_alert(self):
        injector = RealtimeKnowledgeInjector()
        item = injector.inject_from_alert({
            "type": "cpu_high",
            "device": "core-router-01",
            "severity": "critical",
            "message": "CPU使用率达到95%",
        })
        assert item is not None
        assert item.source == "alert"
        assert item.severity == "critical"

    def test_inject_metric(self):
        injector = RealtimeKnowledgeInjector()
        item = injector.inject_from_metric({
            "device": "core-switch-01",
            "metric": "bandwidth_mbps",
            "value": 850.5,
            "threshold": 1000,
        })
        assert item is not None
        assert item.source == "metric"

    def test_inject_audit(self):
        injector = RealtimeKnowledgeInjector()
        item = injector.inject_from_audit({
            "action": "config_acl",
            "user": "admin",
            "target": "firewall-01",
            "status": "success",
        })
        assert item is not None
        assert item.source == "audit"

    def test_get_recent_items(self):
        injector = RealtimeKnowledgeInjector()
        injector.inject_from_alert({"type": "test", "device": "dev1", "severity": "warning", "message": "test"})
        injector.inject_from_metric({"device": "dev2", "metric": "cpu", "value": 80, "threshold": 90})
        items = injector.get_recent_items(limit=10)
        assert len(items) == 2

    def test_search_items(self):
        injector = RealtimeKnowledgeInjector()
        injector.inject_from_alert({"type": "cpu_high", "device": "core-router-01", "severity": "critical", "message": "CPU高"})
        results = injector.search("CPU")
        assert len(results) > 0


def test_get_realtime_injector_singleton():
    i1 = get_realtime_injector()
    i2 = get_realtime_injector()
    assert i1 is i2
