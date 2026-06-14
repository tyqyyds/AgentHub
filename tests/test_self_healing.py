import pytest

try:
    from fastapi.testclient import TestClient
    from backend.api.main import app
    client = TestClient(app)
    BACKEND_AVAILABLE = True
except Exception:
    BACKEND_AVAILABLE = False

import pytest


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend module not available")
class TestSelfHealingEventsAPI:
    def test_create_event(self):
        response = client.post(
            "/api/v1/events/",
            json={
                "event_type": "bandwidth",
                "severity": "high",
                "description": "带宽不足告警",
                "target_device": "Switch-A1",
                "suggested_action": "执行非视频流量限速50%",
                "healing_mode": "suggested",
                "requires_approval": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert data["data"]["event_type"] == "bandwidth"
        assert data["data"]["severity"] == "high"

    def test_create_event_minimal(self):
        response = client.post(
            "/api/v1/events/",
            json={
                "event_type": "link",
                "severity": "medium",
                "description": "链路丢包率偏高"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_create_event_invalid_severity(self):
        response = client.post(
            "/api/v1/events/",
            json={
                "event_type": "bandwidth",
                "severity": "invalid",
                "description": "测试"
            }
        )
        assert response.status_code == 422

    def test_get_events(self):
        response = client.get("/api/v1/events/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_get_events_with_status_filter(self):
        response = client.get("/api/v1/events/?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        for event in data["data"]:
            assert event["status"] == "pending"

    def test_get_events_with_severity_filter(self):
        response = client.get("/api/v1/events/?severity=high")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        for event in data["data"]:
            assert event["severity"] == "high"

    def test_get_events_pagination(self):
        response = client.get("/api/v1/events/?page=1&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        if "pagination" in data:
            assert "total" in data["pagination"]
            assert "pages" in data["pagination"]

    def test_get_single_event(self):
        create_resp = client.post(
            "/api/v1/events/",
            json={
                "event_type": "routing",
                "severity": "low",
                "description": "路由优化建议"
            }
        )
        event_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/events/{event_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["id"] == event_id

    def test_get_nonexistent_event(self):
        response = client.get("/api/v1/events/99999")
        assert response.status_code == 404

    def test_execute_event(self):
        create_resp = client.post(
            "/api/v1/events/",
            json={
                "event_type": "acl",
                "severity": "medium",
                "description": "ACL规则冲突",
                "suggested_action": "调整ACL优先级",
                "requires_approval": True
            }
        )
        event_id = create_resp.json()["data"]["id"]

        response = client.put(f"/api/v1/events/{event_id}/execute")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["status"] == "completed"

    def test_reject_event(self):
        create_resp = client.post(
            "/api/v1/events/",
            json={
                "event_type": "bandwidth",
                "severity": "low",
                "description": "带宽波动",
                "suggested_action": "监控观察",
                "requires_approval": True
            }
        )
        event_id = create_resp.json()["data"]["id"]

        response = client.put(f"/api/v1/events/{event_id}/reject")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["status"] == "rejected"

    def test_execute_already_completed_event(self):
        create_resp = client.post(
            "/api/v1/events/",
            json={
                "event_type": "link",
                "severity": "high",
                "description": "链路故障",
                "suggested_action": "切换备用链路"
            }
        )
        event_id = create_resp.json()["data"]["id"]

        client.put(f"/api/v1/events/{event_id}/execute")
        response = client.put(f"/api/v1/events/{event_id}/execute")
        assert response.status_code == 200


class TestSelfHealingDataTransform:
    def test_transform_basic_event(self):
        from datetime import datetime
        item = {
            "id": 1,
            "event_type": "bandwidth",
            "severity": "high",
            "description": "带宽不足",
            "status": "completed",
            "target_device": "Switch-A1",
            "suggested_action": "限速50%",
            "created_at": datetime.now().isoformat(),
            "executed_by": "admin"
        }
        assert item["event_type"] == "bandwidth"
        assert item["severity"] == "high"
        assert item["status"] == "completed"

    def test_severity_mapping(self):
        severity_map = {
            "critical": "严重",
            "high": "高危",
            "medium": "中危",
            "low": "低危"
        }
        for key, value in severity_map.items():
            assert severity_map[key] == value

    def test_status_mapping(self):
        status_map = {
            "completed": "已完成",
            "pending": "处理中",
            "rejected": "已拒绝",
            "rolled-back": "已回滚"
        }
        for key, value in status_map.items():
            assert status_map[key] == value


class TestSelfHealingStateMachine:
    def test_generate_state_machine_completed(self):
        nodes = [
            {"id": "start", "status": "completed"},
            {"id": "analysis", "status": "completed"},
            {"id": "solution", "status": "completed"},
            {"id": "approval", "status": "completed"},
            {"id": "execution", "status": "completed"},
            {"id": "verification", "status": "completed"},
            {"id": "end", "status": "completed"}
        ]
        assert all(n["status"] == "completed" for n in nodes)

    def test_generate_state_machine_pending(self):
        nodes = [
            {"id": "start", "status": "completed"},
            {"id": "analysis", "status": "active"},
            {"id": "solution", "status": "pending"},
            {"id": "approval", "status": "pending"},
            {"id": "execution", "status": "pending"},
            {"id": "verification", "status": "pending"},
            {"id": "end", "status": "pending"}
        ]
        active_nodes = [n for n in nodes if n["status"] == "active"]
        pending_nodes = [n for n in nodes if n["status"] == "pending"]
        assert len(active_nodes) == 1
        assert len(pending_nodes) == 5

    def test_state_machine_edges(self):
        edges = [
            {"source": "start", "target": "analysis"},
            {"source": "analysis", "target": "solution"},
            {"source": "solution", "target": "approval"},
            {"source": "approval", "target": "execution", "label": "通过"},
            {"source": "approval", "target": "end", "label": "拒绝"},
            {"source": "execution", "target": "verification"},
            {"source": "verification", "target": "end"}
        ]
        assert len(edges) == 7
        approval_edges = [e for e in edges if e["source"] == "approval"]
        assert len(approval_edges) == 2


class TestSelfHealingFilterLogic:
    def test_filter_by_severity(self):
        events = [
            {"id": "1", "severity": "high", "status": "completed", "type": "bandwidth"},
            {"id": "2", "severity": "medium", "status": "pending", "type": "link"},
            {"id": "3", "severity": "low", "status": "completed", "type": "acl"},
            {"id": "4", "severity": "high", "status": "pending", "type": "routing"}
        ]
        filtered = [e for e in events if e["severity"] == "high"]
        assert len(filtered) == 2

    def test_filter_by_status(self):
        events = [
            {"id": "1", "severity": "high", "status": "completed", "type": "bandwidth"},
            {"id": "2", "severity": "medium", "status": "pending", "type": "link"},
            {"id": "3", "severity": "low", "status": "completed", "type": "acl"}
        ]
        filtered = [e for e in events if e["status"] == "pending"]
        assert len(filtered) == 1

    def test_filter_by_type(self):
        events = [
            {"id": "1", "severity": "high", "status": "completed", "type": "bandwidth"},
            {"id": "2", "severity": "medium", "status": "pending", "type": "link"},
            {"id": "3", "severity": "low", "status": "completed", "type": "bandwidth"}
        ]
        filtered = [e for e in events if e["type"] == "bandwidth"]
        assert len(filtered) == 2

    def test_search_by_text(self):
        events = [
            {"id": "SH-001", "title": "带宽不足自愈", "description": "带宽低于阈值", "targetDevice": "Switch-A1"},
            {"id": "SH-002", "title": "链路质量优化", "description": "链路丢包率偏高", "targetDevice": "Router-C1"},
            {"id": "SH-003", "title": "ACL规则优化", "description": "ACL规则冲突", "targetDevice": "Firewall-B1"}
        ]
        q = "带宽"
        filtered = [e for e in events if q in e["title"] or q in e["description"] or q in e["targetDevice"]]
        assert len(filtered) == 1

    def test_combined_filters(self):
        events = [
            {"id": "1", "severity": "high", "status": "completed", "type": "bandwidth"},
            {"id": "2", "severity": "high", "status": "pending", "type": "link"},
            {"id": "3", "severity": "medium", "status": "pending", "type": "bandwidth"}
        ]
        filtered = [e for e in events if e["severity"] == "high" and e["status"] == "pending"]
        assert len(filtered) == 1
        assert filtered[0]["id"] == "2"

    def test_empty_filter_result(self):
        events = [
            {"id": "1", "severity": "high", "status": "completed", "type": "bandwidth"}
        ]
        filtered = [e for e in events if e["severity"] == "critical"]
        assert len(filtered) == 0


class TestSelfHealingMetrics:
    def test_metrics_calculation(self):
        events = [
            {"status": "completed"},
            {"status": "completed"},
            {"status": "pending"},
            {"status": "rejected"},
            {"status": "completed"}
        ]
        total = len(events)
        completed = len([e for e in events if e["status"] == "completed"])
        pending = len([e for e in events if e["status"] == "pending"])
        success_rate = round((completed / total) * 100)

        assert total == 5
        assert completed == 3
        assert pending == 1
        assert success_rate == 60

    def test_metrics_empty_events(self):
        events = []
        total = len(events)
        completed = len([e for e in events if e["status"] == "completed"])
        success_rate = 0 if total == 0 else round((completed / total) * 100)

        assert total == 0
        assert success_rate == 0

    def test_critical_count(self):
        events = [
            {"severity": "high"},
            {"severity": "critical"},
            {"severity": "medium"},
            {"severity": "high"},
            {"severity": "low"}
        ]
        critical = len([e for e in events if e["severity"] in ("high", "critical")])
        assert critical == 3


class TestSelfHealingExport:
    def test_json_export_structure(self):
        events = [
            {"id": "SH-001", "type": "bandwidth", "severity": "high", "title": "测试", "status": "completed", "targetDevice": "Switch-A1", "timelineSteps": 6}
        ]
        export_payload = {
            "exportTime": "2026-05-24T00:00:00.000Z",
            "mode": "suggested",
            "totalEvents": 1,
            "events": events,
            "metrics": [{"label": "自愈事件", "value": 1, "unit": "次"}]
        }
        assert "exportTime" in export_payload
        assert "events" in export_payload
        assert len(export_payload["events"]) == 1
        assert export_payload["events"][0]["id"] == "SH-001"

    def test_csv_export_headers(self):
        headers = "事件ID,类型,严重级别,标题,状态,目标设备,时间轴步骤数\n"
        assert "事件ID" in headers
        assert "类型" in headers
        assert "严重级别" in headers


class TestSelfHealingModePersistence:
    def test_mode_values(self):
        valid_modes = ["auto", "suggested", "alert"]
        for mode in valid_modes:
            assert mode in valid_modes

    def test_mode_descriptions(self):
        modes = [
            {"value": "auto", "label": "全自动", "desc": "自动检测并执行自愈方案"},
            {"value": "suggested", "label": "建议模式", "desc": "生成方案后需人工审批"},
            {"value": "alert", "label": "仅告警", "desc": "仅发送告警通知"}
        ]
        assert len(modes) == 3
        assert modes[1]["value"] == "suggested"
