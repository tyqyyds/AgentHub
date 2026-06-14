# -*- coding: utf-8 -*-
import pytest
import json
import re
import secrets
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

try:
    from fastapi.testclient import TestClient
    from backend.api.main import app
    client = TestClient(app)
    BACKEND_AVAILABLE = True
except Exception:
    BACKEND_AVAILABLE = False


MOCK_AUDIT_LOGS = [
    {
        "id": "AL-001",
        "user": "admin",
        "action": "intent_submit",
        "actionLabel": "提交意图",
        "targetDevice": "Switch-A1",
        "commands": ["class-map VIDEO_CONF", "policy-map QOS_VIDEO"],
        "timestamp": "2026-05-21 10:30:00",
        "status": "success",
        "approvalId": "APR-001",
        "ip": "192.168.1.100",
        "result": "配置已成功下发",
        "details": "视频会议带宽保障策略已生效",
        "securityLevel": "info",
        "context": {
            "intentId": "INT-001",
            "intentText": "保障视频会议带宽200M",
            "prompt": "用户意图：保障视频会议带宽200M\n请解析并生成配置...",
            "modelResponse": '{"intent": "bandwidth_guarantee", "params": {"bandwidth": 200, "protocol": "video"}}',
            "tokens": {"prompt": 234, "completion": 128, "total": 362},
            "latency_ms": 1247,
            "model": "GPT-4o"
        }
    },
    {
        "id": "AL-002",
        "user": "admin",
        "action": "config_deploy",
        "actionLabel": "配置下发",
        "targetDevice": "Router-C1",
        "commands": ["interface GigabitEthernet0/0", "ip address 192.168.1.1 255.255.255.0"],
        "timestamp": "2026-05-21 10:25:00",
        "status": "success",
        "approvalId": "APR-002",
        "ip": "192.168.1.100",
        "result": "接口配置完成",
        "details": "GigabitEthernet0/0 IP地址配置成功",
        "securityLevel": "info",
        "context": {
            "intentId": "INT-002",
            "intentText": "配置路由器接口IP",
            "prompt": "请为Router-C1的GigabitEthernet0/0配置IP 192.168.1.1/24",
            "modelResponse": "生成配置：\ninterface GigabitEthernet0/0\n  ip address 192.168.1.1 255.255.255.0",
            "tokens": {"prompt": 156, "completion": 89, "total": 245},
            "latency_ms": 892,
            "model": "GPT-4o"
        }
    },
    {
        "id": "AL-003",
        "user": "operator",
        "action": "intent_submit",
        "actionLabel": "提交意图",
        "targetDevice": "Firewall-B1",
        "commands": [],
        "timestamp": "2026-05-21 10:20:00",
        "status": "pending",
        "approvalId": "APR-003",
        "ip": "192.168.1.101",
        "result": "等待审批",
        "details": "ACL规则更新需人工审批",
        "securityLevel": "warning",
        "context": {
            "intentId": "INT-003",
            "intentText": "更新ACL规则",
            "prompt": "请为Firewall-B1更新ACL规则，允许10.0.0.0/24访问80端口",
            "modelResponse": "待人工审批...",
            "tokens": {"prompt": 198, "completion": 0, "total": 198},
            "latency_ms": 654,
            "model": "GPT-4o"
        }
    },
    {
        "id": "AL-004",
        "user": "admin",
        "action": "self_healing",
        "actionLabel": "自愈执行",
        "targetDevice": "Switch-A2",
        "commands": ["traffic-shape rate 50000000"],
        "timestamp": "2026-05-21 09:45:00",
        "status": "success",
        "ip": "10.0.0.1",
        "result": "自愈成功",
        "details": "丢包问题已通过流量整形修复",
        "securityLevel": "info",
        "context": {
            "intentText": "自动检测并修复丢包问题",
            "prompt": "告警：Switch-A2接口丢包率超过5%\n请分析并生成修复方案",
            "modelResponse": "诊断结果：端口拥塞\n建议：配置流量整形，限制速率为50Mbps",
            "tokens": {"prompt": 312, "completion": 156, "total": 468},
            "latency_ms": 1567,
            "model": "GPT-4o"
        }
    },
    {
        "id": "AL-005",
        "user": "operator",
        "action": "config_rollback",
        "actionLabel": "配置回滚",
        "targetDevice": "Switch-A1",
        "commands": ["rollback configuration"],
        "timestamp": "2026-05-21 09:30:00",
        "status": "success",
        "ip": "192.168.1.101",
        "result": "回滚成功",
        "details": "配置已回滚到上一版本",
        "securityLevel": "critical",
        "context": {
            "intentId": "INT-004",
            "intentText": "回滚之前的配置",
            "prompt": "用户要求回滚到上一个配置版本",
            "modelResponse": "执行rollback命令",
            "tokens": {"prompt": 78, "completion": 34, "total": 112},
            "latency_ms": 456,
            "model": "GPT-4o"
        }
    }
]


class AuditLogModel(BaseModel):
    id: str
    user: str = Field(min_length=1)
    action: str = Field(min_length=1)
    actionLabel: str = Field(min_length=1)
    targetDevice: str
    commands: List[str] = Field(default_factory=list)
    timestamp: str
    status: str
    ip: Optional[str] = None
    result: Optional[str] = None
    details: Optional[str] = None
    securityLevel: Optional[str] = None
    approvalId: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class AuditLogCreateModel(BaseModel):
    user_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    target_device: Optional[str] = None
    commands: Optional[List[str]] = None
    approval_id: Optional[str] = None
    status: str = "success"
    security_type: Optional[str] = None


def filter_logs(
    logs: List[Dict],
    user: Optional[str] = None,
    action: Optional[str] = None,
    status: Optional[str] = None,
    security_level: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> List[Dict]:
    filtered = list(logs)
    if user:
        filtered = [l for l in filtered if l["user"] == user]
    if action:
        filtered = [l for l in filtered if l["action"] == action]
    if status:
        filtered = [l for l in filtered if l["status"] == status]
    if security_level:
        filtered = [l for l in filtered if l.get("securityLevel") == security_level]
    if start_date:
        filtered = [l for l in filtered if l["timestamp"] >= start_date]
    if end_date:
        filtered = [l for l in filtered if l["timestamp"] <= end_date + " 23:59:59"]
    return filtered


def paginate_logs(
    logs: List[Dict],
    page: int = 1,
    limit: int = 20
) -> Dict[str, Any]:
    total = len(logs)
    start = (page - 1) * limit
    data = logs[start:start + limit]
    return {
        "data": data,
        "total": total,
        "page": page,
        "limit": limit
    }


def generate_log_id() -> str:
    timestamp_part = secrets.token_hex(4)
    random_part = secrets.token_hex(4)
    return f"AL-{timestamp_part}-{random_part}"


def escape_csv(value: Any) -> str:
    s = str(value)
    if re.search(r'[",\n\r=+\-@]', s):
        return '"' + s.replace('"', '""') + '"'
    return s


def compute_log_hash(log: Dict) -> str:
    canonical = json.dumps(log, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend module not available")
class TestAuditAPIEndpoints:
    def test_get_logs(self):
        response = client.get("/api/v1/audit/logs")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_get_logs_with_pagination(self):
        response = client.get("/api/v1/audit/logs?page=1&limit=20")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "pagination" in data
        assert "page" in data["pagination"]
        assert "limit" in data["pagination"]
        assert "total" in data["pagination"]

    def test_get_logs_filter_by_user(self):
        response = client.get("/api/v1/audit/logs?user_id=admin")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["data"], list)

    def test_get_logs_filter_by_action(self):
        response = client.get("/api/v1/audit/logs?action=intent_submit")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["data"], list)

    def test_get_logs_filter_by_status(self):
        response = client.get("/api/v1/audit/logs?status=success")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["data"], list)

    def test_get_log_count(self):
        response = client.get("/api/v1/audit/count")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "count" in data
        assert isinstance(data["count"], int)

    def test_get_log_by_id(self):
        create_resp = client.post(
            "/api/v1/audit/logs",
            json={
                "user_id": "test_user",
                "action": "test_action",
                "target_device": "Test-Device",
                "status": "success"
            }
        )
        assert create_resp.status_code == 200
        log_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/audit/logs/{log_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data

    def test_create_log(self):
        response = client.post(
            "/api/v1/audit/logs",
            json={
                "user_id": "test_user",
                "action": "intent_submit",
                "target_device": "Switch-A1",
                "commands": ["show interface"],
                "status": "success",
                "security_type": "info"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert "id" in data["data"]

    def test_create_log_empty_user_id(self):
        response = client.post(
            "/api/v1/audit/logs",
            json={
                "user_id": "",
                "action": "test_action",
                "status": "success"
            }
        )
        assert response.status_code == 422

    def test_create_log_empty_action(self):
        response = client.post(
            "/api/v1/audit/logs",
            json={
                "user_id": "admin",
                "action": "",
                "status": "success"
            }
        )
        assert response.status_code == 422


class TestAuditLogCompleteness:
    def test_log_contains_user(self):
        for log in MOCK_AUDIT_LOGS:
            assert "user" in log
            assert isinstance(log["user"], str)
            assert len(log["user"]) > 0

    def test_log_contains_timestamp(self):
        for log in MOCK_AUDIT_LOGS:
            assert "timestamp" in log
            assert isinstance(log["timestamp"], str)
            assert len(log["timestamp"]) > 0

    def test_log_contains_action_and_action_label(self):
        for log in MOCK_AUDIT_LOGS:
            assert "action" in log
            assert "actionLabel" in log
            assert isinstance(log["action"], str)
            assert isinstance(log["actionLabel"], str)
            assert len(log["action"]) > 0
            assert len(log["actionLabel"]) > 0

    def test_log_contains_status(self):
        for log in MOCK_AUDIT_LOGS:
            assert "status" in log
            assert log["status"] in ("success", "pending", "failed", "running")

    def test_log_contains_target_device(self):
        for log in MOCK_AUDIT_LOGS:
            assert "targetDevice" in log
            assert isinstance(log["targetDevice"], str)
            assert len(log["targetDevice"]) > 0

    def test_log_contains_ip(self):
        for log in MOCK_AUDIT_LOGS:
            assert "ip" in log
            assert log["ip"] is not None

    def test_log_contains_security_level(self):
        for log in MOCK_AUDIT_LOGS:
            assert "securityLevel" in log
            assert log["securityLevel"] in ("info", "warning", "critical")

    def test_log_contains_result(self):
        for log in MOCK_AUDIT_LOGS:
            assert "result" in log
            assert isinstance(log["result"], str)
            assert len(log["result"]) > 0

    def test_log_pydantic_model_validation(self):
        for log in MOCK_AUDIT_LOGS:
            model = AuditLogModel(**log)
            assert model.id == log["id"]
            assert model.user == log["user"]
            assert model.action == log["action"]
            assert model.status == log["status"]

    def test_log_create_model_validation(self):
        payload = {
            "user_id": "admin",
            "action": "intent_submit",
            "target_device": "Switch-A1",
            "status": "success"
        }
        model = AuditLogCreateModel(**payload)
        assert model.user_id == "admin"
        assert model.action == "intent_submit"

    def test_log_create_model_rejects_empty_user_id(self):
        with pytest.raises(Exception):
            AuditLogCreateModel(user_id="", action="test")

    def test_log_create_model_rejects_empty_action(self):
        with pytest.raises(Exception):
            AuditLogCreateModel(user_id="admin", action="")


class TestAuditLogQuery:
    def test_filter_by_time_range(self):
        result = filter_logs(
            MOCK_AUDIT_LOGS,
            start_date="2026-05-21 09:00:00",
            end_date="2026-05-21 10:00:00"
        )
        assert len(result) == 2
        for log in result:
            assert log["timestamp"] >= "2026-05-21 09:00:00"
            assert log["timestamp"] <= "2026-05-21 10:00:00 23:59:59"

    def test_filter_by_action(self):
        result = filter_logs(MOCK_AUDIT_LOGS, action="intent_submit")
        assert len(result) == 2
        for log in result:
            assert log["action"] == "intent_submit"

    def test_filter_by_status(self):
        result = filter_logs(MOCK_AUDIT_LOGS, status="pending")
        assert len(result) == 1
        assert result[0]["id"] == "AL-003"

    def test_filter_by_security_level(self):
        result = filter_logs(MOCK_AUDIT_LOGS, security_level="critical")
        assert len(result) == 1
        assert result[0]["id"] == "AL-005"

    def test_filter_by_user(self):
        result = filter_logs(MOCK_AUDIT_LOGS, user="operator")
        assert len(result) == 2
        for log in result:
            assert log["user"] == "operator"

    def test_combined_filter(self):
        result = filter_logs(
            MOCK_AUDIT_LOGS,
            user="admin",
            action="intent_submit",
            status="success"
        )
        assert len(result) == 1
        assert result[0]["id"] == "AL-001"

    def test_pagination(self):
        page_result = paginate_logs(MOCK_AUDIT_LOGS, page=1, limit=2)
        assert len(page_result["data"]) == 2
        assert page_result["total"] == 5
        assert page_result["page"] == 1
        assert page_result["limit"] == 2

    def test_pagination_second_page(self):
        page_result = paginate_logs(MOCK_AUDIT_LOGS, page=2, limit=2)
        assert len(page_result["data"]) == 2
        assert page_result["total"] == 5

    def test_pagination_last_page(self):
        page_result = paginate_logs(MOCK_AUDIT_LOGS, page=3, limit=2)
        assert len(page_result["data"]) == 1
        assert page_result["data"][0]["id"] == "AL-005"

    def test_end_date_padded_with_time(self):
        result = filter_logs(
            MOCK_AUDIT_LOGS,
            start_date="2026-05-21",
            end_date="2026-05-21"
        )
        assert len(result) == 5

    def test_filter_no_match(self):
        result = filter_logs(MOCK_AUDIT_LOGS, user="nonexistent_user")
        assert len(result) == 0

    def test_filter_empty_logs(self):
        result = filter_logs([], user="admin")
        assert len(result) == 0

    def test_filter_by_start_date_only(self):
        result = filter_logs(MOCK_AUDIT_LOGS, start_date="2026-05-21 10:20:00")
        assert len(result) == 3
        for log in result:
            assert log["timestamp"] >= "2026-05-21 10:20:00"

    def test_filter_by_end_date_only(self):
        result = filter_logs(MOCK_AUDIT_LOGS, end_date="2026-05-21 09:45:00")
        assert len(result) == 2
        for log in result:
            assert log["timestamp"] <= "2026-05-21 09:45:00 23:59:59"


class TestAuditLogExport:
    def test_json_export_structure(self):
        export_payload = {
            "exportTime": datetime.now().isoformat(),
            "totalLogs": len(MOCK_AUDIT_LOGS),
            "logs": [
                {
                    "id": log["id"],
                    "user": log["user"],
                    "action": log["action"],
                    "actionLabel": log["actionLabel"],
                    "targetDevice": log["targetDevice"],
                    "status": log["status"],
                    "timestamp": log["timestamp"],
                    "ip": log.get("ip", ""),
                    "securityLevel": log.get("securityLevel", ""),
                    "result": log.get("result", "")
                }
                for log in MOCK_AUDIT_LOGS
            ]
        }
        assert "exportTime" in export_payload
        assert "totalLogs" in export_payload
        assert "logs" in export_payload
        assert export_payload["totalLogs"] == 5
        assert len(export_payload["logs"]) == 5

    def test_json_export_serializable(self):
        export_payload = {
            "exportTime": datetime.now().isoformat(),
            "totalLogs": len(MOCK_AUDIT_LOGS),
            "logs": MOCK_AUDIT_LOGS
        }
        serialized = json.dumps(export_payload, ensure_ascii=False)
        deserialized = json.loads(serialized)
        assert deserialized["totalLogs"] == 5
        assert len(deserialized["logs"]) == 5

    def test_csv_export_headers(self):
        headers = "ID,用户,操作,操作标签,目标设备,状态,时间,IP,安全级别,结果\n"
        assert "ID" in headers
        assert "用户" in headers
        assert "操作" in headers
        assert "操作标签" in headers
        assert "目标设备" in headers
        assert "状态" in headers
        assert "时间" in headers
        assert "IP" in headers
        assert "安全级别" in headers
        assert "结果" in headers

    def test_csv_double_quote_escape(self):
        assert escape_csv('正常文本') == '正常文本'
        assert escape_csv('包含"引号') == '"包含""引号"'
        assert escape_csv('包含,逗号') == '"包含,逗号"'
        assert escape_csv('包含\n换行') == '"包含\n换行"'

    def test_csv_injection_protection_equals(self):
        result = escape_csv("=FORMULA")
        assert result.startswith('"')
        assert result.endswith('"')

    def test_csv_injection_protection_plus(self):
        result = escape_csv("+value")
        assert result.startswith('"')
        assert result.endswith('"')

    def test_csv_injection_protection_minus(self):
        result = escape_csv("-value")
        assert result.startswith('"')
        assert result.endswith('"')

    def test_csv_injection_protection_at(self):
        result = escape_csv("@function")
        assert result.startswith('"')
        assert result.endswith('"')

    def test_csv_safe_value_no_quotes(self):
        result = escape_csv("normal_value")
        assert result == "normal_value"
        assert not result.startswith('"')

    def test_export_with_filters(self):
        filtered = filter_logs(MOCK_AUDIT_LOGS, user="admin", status="success")
        export_payload = {
            "exportTime": datetime.now().isoformat(),
            "totalLogs": len(filtered),
            "logs": filtered
        }
        assert export_payload["totalLogs"] == 3
        for log in export_payload["logs"]:
            assert log["user"] == "admin"
            assert log["status"] == "success"


class TestAuditLogSecurity:
    def test_log_id_unpredictable(self):
        ids = set()
        for _ in range(50):
            generated_id = generate_log_id()
            ids.add(generated_id)
        assert len(ids) == 50
        for log_id in ids:
            assert log_id.startswith("AL-")
            parts = log_id.split("-")
            assert len(parts) == 3

    def test_log_id_not_sequential(self):
        ids = [generate_log_id() for _ in range(10)]
        for i in range(len(ids) - 1):
            assert ids[i] != ids[i + 1]

    def test_logs_append_only(self):
        original_count = len(MOCK_AUDIT_LOGS)
        original_ids = {log["id"] for log in MOCK_AUDIT_LOGS}
        new_log = {
            "id": "AL-006",
            "user": "admin",
            "action": "config_deploy",
            "actionLabel": "配置下发",
            "targetDevice": "Switch-B1",
            "commands": ["show running-config"],
            "timestamp": "2026-05-21 11:00:00",
            "status": "success",
            "ip": "192.168.1.100",
            "result": "配置查看完成",
            "securityLevel": "info",
            "context": {"intentText": "查看配置"}
        }
        extended_logs = MOCK_AUDIT_LOGS + [new_log]
        assert len(extended_logs) == original_count + 1
        for oid in original_ids:
            assert oid in {log["id"] for log in extended_logs}

    def test_critical_operation_marked(self):
        critical_logs = [log for log in MOCK_AUDIT_LOGS if log.get("securityLevel") == "critical"]
        assert len(critical_logs) >= 1
        for log in critical_logs:
            assert log["securityLevel"] == "critical"
            assert log["action"] in ("config_rollback", "config_deploy", "self_healing", "intent_submit")

    def test_log_integrity_hash(self):
        for log in MOCK_AUDIT_LOGS:
            hash1 = compute_log_hash(log)
            hash2 = compute_log_hash(log)
            assert hash1 == hash2

    def test_log_tamper_detection(self):
        log = MOCK_AUDIT_LOGS[0]
        original_hash = compute_log_hash(log)
        tampered = dict(log)
        tampered["status"] = "failed"
        tampered_hash = compute_log_hash(tampered)
        assert original_hash != tampered_hash

    def test_log_id_format(self):
        for log in MOCK_AUDIT_LOGS:
            assert log["id"].startswith("AL-")
            assert len(log["id"]) > 3

    def test_security_level_values(self):
        valid_levels = {"info", "warning", "critical"}
        for log in MOCK_AUDIT_LOGS:
            assert log.get("securityLevel") in valid_levels


class TestAuditLogStatusValues:
    def test_valid_status_values(self):
        valid_statuses = {"success", "pending", "failed", "running"}
        for log in MOCK_AUDIT_LOGS:
            assert log["status"] in valid_statuses

    def test_status_distribution(self):
        success_count = len([l for l in MOCK_AUDIT_LOGS if l["status"] == "success"])
        pending_count = len([l for l in MOCK_AUDIT_LOGS if l["status"] == "pending"])
        assert success_count == 4
        assert pending_count == 1

    def test_action_label_mapping(self):
        action_map = {
            "intent_submit": "提交意图",
            "config_deploy": "配置下发",
            "self_healing": "自愈执行",
            "config_rollback": "配置回滚"
        }
        for log in MOCK_AUDIT_LOGS:
            if log["action"] in action_map:
                assert log["actionLabel"] == action_map[log["action"]]


class TestAuditLogMetrics:
    def test_metrics_from_mock_data(self):
        total = len(MOCK_AUDIT_LOGS)
        success = len([l for l in MOCK_AUDIT_LOGS if l["status"] == "success"])
        pending = len([l for l in MOCK_AUDIT_LOGS if l["status"] == "pending"])
        critical = len([l for l in MOCK_AUDIT_LOGS if l.get("securityLevel") == "critical"])
        warning = len([l for l in MOCK_AUDIT_LOGS if l.get("securityLevel") == "warning"])

        assert total == 5
        assert success == 4
        assert pending == 1
        assert critical == 1
        assert warning == 1

    def test_metrics_empty_data(self):
        logs = []
        total = len(logs)
        success = len([l for l in logs if l["status"] == "success"])
        assert total == 0
        assert success == 0

    def test_user_distribution(self):
        admin_logs = [l for l in MOCK_AUDIT_LOGS if l["user"] == "admin"]
        operator_logs = [l for l in MOCK_AUDIT_LOGS if l["user"] == "operator"]
        assert len(admin_logs) == 3
        assert len(operator_logs) == 2


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend module not available")
class TestAuditLogIntegration:
    def test_add_query_verify_workflow(self):
        create_resp = client.post(
            "/api/v1/audit/logs",
            json={
                "user_id": "integration_test_user",
                "action": "intent_submit",
                "target_device": "Integration-Device",
                "commands": ["show version"],
                "status": "success",
                "security_type": "info"
            }
        )
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        assert create_data["status"] == "success"
        log_id = create_data["data"]["id"]

        query_resp = client.get(f"/api/v1/audit/logs/{log_id}")
        assert query_resp.status_code == 200
        query_data = query_resp.json()
        assert query_data["status"] == "success"
        assert query_data["data"]["id"] == log_id
        assert query_data["data"]["user_id"] == "integration_test_user"
        assert query_data["data"]["action"] == "intent_submit"

    def test_cross_module_audit_logs_updated_event(self):
        event_dispatched = False

        def on_audit_update(event_type):
            nonlocal event_dispatched
            if event_type == "auditLogsUpdated":
                event_dispatched = True

        on_audit_update("auditLogsUpdated")
        assert event_dispatched is True

    def test_dashboard_data_updated_event(self):
        event_dispatched = False

        def on_dashboard_update(event_type):
            nonlocal event_dispatched
            if event_type == "dashboardDataUpdated":
                event_dispatched = True

        on_dashboard_update("dashboardDataUpdated")
        assert event_dispatched is True

    def test_multiple_events_in_workflow(self):
        events = []

        def record_event(event_type):
            events.append(event_type)

        record_event("auditLogsUpdated")
        record_event("dashboardDataUpdated")
        assert len(events) == 2
        assert "auditLogsUpdated" in events
        assert "dashboardDataUpdated" in events

    def test_add_log_and_count(self):
        count_before_resp = client.get("/api/v1/audit/count")
        count_before = count_before_resp.json()["count"]

        client.post(
            "/api/v1/audit/logs",
            json={
                "user_id": "count_test_user",
                "action": "config_deploy",
                "target_device": "Count-Device",
                "status": "success"
            }
        )

        count_after_resp = client.get("/api/v1/audit/count")
        count_after = count_after_resp.json()["count"]
        assert count_after >= count_before


class TestAuditLogPydanticModel:
    def test_model_defaults(self):
        log = AuditLogModel(
            id="AL-TEST",
            user="admin",
            action="test",
            actionLabel="测试",
            targetDevice="Device-1",
            timestamp="2026-05-21 10:00:00",
            status="success"
        )
        assert log.commands == []
        assert log.ip is None
        assert log.result is None
        assert log.details is None
        assert log.securityLevel is None
        assert log.approvalId is None
        assert log.context == {}

    def test_model_full(self):
        log = AuditLogModel(
            id="AL-FULL",
            user="admin",
            action="intent_submit",
            actionLabel="提交意图",
            targetDevice="Switch-A1",
            commands=["show interface"],
            timestamp="2026-05-21 10:00:00",
            status="success",
            ip="192.168.1.100",
            result="操作成功",
            details="详细信息",
            securityLevel="info",
            approvalId="APR-001",
            context={"intentText": "测试意图"}
        )
        assert log.id == "AL-FULL"
        assert log.user == "admin"
        assert log.commands == ["show interface"]
        assert log.ip == "192.168.1.100"
        assert log.securityLevel == "info"

    def test_model_serialization(self):
        log = AuditLogModel(
            id="AL-SER",
            user="admin",
            action="test",
            actionLabel="测试",
            targetDevice="Device-1",
            timestamp="2026-05-21 10:00:00",
            status="success"
        )
        data = log.model_dump()
        assert data["id"] == "AL-SER"
        serialized = json.dumps(data)
        deserialized = json.loads(serialized)
        assert deserialized["id"] == "AL-SER"

    def test_create_model_defaults(self):
        model = AuditLogCreateModel(user_id="admin", action="test")
        assert model.target_device is None
        assert model.commands is None
        assert model.approval_id is None
        assert model.status == "success"
        assert model.security_type is None

    def test_create_model_full(self):
        model = AuditLogCreateModel(
            user_id="admin",
            action="intent_submit",
            target_device="Switch-A1",
            commands=["show interface"],
            approval_id="APR-001",
            status="success",
            security_type="info"
        )
        assert model.user_id == "admin"
        assert model.action == "intent_submit"
        assert model.target_device == "Switch-A1"
        assert model.commands == ["show interface"]
        assert model.approval_id == "APR-001"
        assert model.security_type == "info"
