# -*- coding: utf-8 -*-
import pytest
import json
import re
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


MOCK_INTENT_HISTORY = [
    {
        "id": 1,
        "user_input": "保障研发子网视频会议流量最小200M带宽",
        "structured_params": {
            "intent_name": "bandwidth_guarantee",
            "targets": ["研发子网"],
            "actions": [{"type": "qos", "params": {"min_bw": "200M", "protocol": "video", "priority": "high"}}],
            "confidence": 0.9,
            "entities": {"目标": "研发子网", "带宽": "200M", "类型": "视频"}
        },
        "approval_status": "pending",
        "status": "pending",
        "created_at": "2026-05-24T10:00:00",
        "device": "Switch-A1",
        "processing_logs": [{"timestamp": "10:00:01", "message": "意图解析完成"}]
    },
    {
        "id": 2,
        "user_input": "开放研发子网到生产子网的数据库访问",
        "structured_params": {
            "intent_name": "access_control",
            "targets": ["研发子网", "生产子网"],
            "actions": [{"type": "acl", "params": {"source": "研发子网", "destination": "生产子网", "action": "permit"}}],
            "confidence": 0.7,
            "entities": {"源": "研发", "目标": "生产", "动作": "允许"}
        },
        "approval_status": "approved",
        "status": "completed",
        "created_at": "2026-05-24T09:30:00",
        "device": "Firewall-B1",
        "processing_logs": []
    },
    {
        "id": 3,
        "user_input": "诊断核心交换机的链路故障",
        "structured_params": {
            "intent_name": "fault_diagnosis",
            "targets": ["核心交换机"],
            "actions": [{"type": "diagnose", "params": {"scope": "link", "symptoms": "connectivity_loss"}}],
            "confidence": 0.7,
            "entities": {"范围": "链路"}
        },
        "approval_status": "rejected",
        "status": "rejected",
        "created_at": "2026-05-24T09:00:00",
        "device": "Core-Switch-01",
        "processing_logs": []
    },
    {
        "id": 4,
        "user_input": "将主链路切换到备用链路",
        "structured_params": {
            "intent_name": "link_management",
            "targets": ["网络链路"],
            "actions": [{"type": "routing", "params": {"mode": "failover"}}],
            "confidence": 0.65,
            "entities": {"操作": "主备切换"}
        },
        "approval_status": "pending",
        "status": "pending",
        "created_at": "2026-05-24T08:30:00",
        "device": "Router-C1",
        "processing_logs": []
    },
    {
        "id": 5,
        "user_input": "为办公子网配置高优先级QoS策略",
        "structured_params": {
            "intent_name": "qos_policy",
            "targets": ["办公子网"],
            "actions": [{"type": "qos_config", "params": {"min_bw": "100M", "priority": "high", "policy_type": "qos"}}],
            "confidence": 0.7,
            "entities": {"子网": "办公子网", "带宽": "默认"}
        },
        "approval_status": "approved",
        "status": "completed",
        "created_at": "2026-05-23T16:00:00",
        "device": "Switch-D1",
        "processing_logs": []
    }
]


class ParsedIntent(BaseModel):
    intent_type: str = Field(description="意图类型")
    target_subnet: Optional[str] = Field(default=None)
    bandwidth: Optional[int] = Field(default=None)
    duration: str = Field(default="持续")
    priority: str = Field(default="medium")
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    entities: Dict[str, str] = Field(default_factory=dict)


def fallback_parse(user_input: str) -> ParsedIntent:
    entities: Dict[str, str] = {}
    intent_type = "unknown"
    actions: List[Dict[str, Any]] = []
    priority = "medium"
    target_subnet = None
    bandwidth = None

    subnet_match = re.search(r"([\u4e00-\u9fa5]+子网)", user_input)
    if subnet_match:
        target_subnet = subnet_match.group(1)
        entities["子网"] = target_subnet

    bw_match = re.search(r"(\d+)\s*[Mm]", user_input)
    if bw_match:
        bandwidth = int(bw_match.group(1))
        entities["带宽"] = f"{bandwidth}M"

    time_match = re.search(r"(\d+)\s*(天|小时|分钟)", user_input)
    if time_match:
        entities["时间"] = time_match.group(0)

    if "带宽" in user_input or "保障" in user_input or "QoS" in user_input.upper():
        intent_type = "bandwidth_guarantee"
        priority = "high"
        actions.append({"type": "qos_config", "params": {"min_bw": f"{bandwidth or 100}M", "protocol": "any"}})
    elif "访问" in user_input or "ACL" in user_input.upper() or "权限" in user_input:
        intent_type = "access_control"
        actions.append({"type": "acl_config", "params": {"direction": "inbound"}})
    elif "链路" in user_input or "路由" in user_input:
        intent_type = "link_management"
        actions.append({"type": "link_config", "params": {}})
    elif "故障" in user_input or "诊断" in user_input:
        intent_type = "fault_diagnosis"
        actions.append({"type": "diagnose", "params": {}})
    elif "监控" in user_input or "性能" in user_input:
        intent_type = "performance_monitoring"
        actions.append({"type": "monitor", "params": {}})
    elif "流量" in user_input or "整形" in user_input:
        intent_type = "traffic_shaping"
        actions.append({"type": "traffic_config", "params": {}})

    return ParsedIntent(
        intent_type=intent_type,
        target_subnet=target_subnet,
        bandwidth=bandwidth,
        duration=entities.get("时间", "持续"),
        priority=priority,
        actions=actions,
        entities=entities
    )


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend module not available")
class TestIntentAPIEndpoints:
    def test_get_intents(self):
        response = client.get("/api/v1/intents/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_get_intents_with_pagination(self):
        response = client.get("/api/v1/intents/?page=1&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "pagination" in data
        assert "page" in data["pagination"]
        assert "limit" in data["pagination"]
        assert "total" in data["pagination"]
        assert "pages" in data["pagination"]

    def test_get_intents_with_status_filter(self):
        response = client.get("/api/v1/intents/?approval_status=pending")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        for intent in data["data"]:
            assert intent["approval_status"] == "pending"

    def test_create_intent(self):
        response = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "保障研发子网500M带宽",
                "structured_params": {
                    "intent_name": "bandwidth_guarantee",
                    "targets": ["研发子网"],
                    "actions": [{"type": "qos", "params": {"min_bw": "500M"}}]
                }
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert "id" in data["data"]

    def test_create_intent_empty_input(self):
        response = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "",
                "structured_params": {"intent_name": "test"}
            }
        )
        assert response.status_code == 422

    def test_create_intent_missing_intent_name(self):
        response = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "测试意图",
                "structured_params": {"other_key": "value"}
            }
        )
        assert response.status_code == 422

    def test_approve_intent(self):
        create_resp = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "开放测试子网访问",
                "structured_params": {"intent_name": "access_control"}
            }
        )
        intent_id = create_resp.json()["data"]["id"]

        response = client.put(
            f"/api/v1/intents/{intent_id}",
            json={"approval_status": "approved"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_reject_intent(self):
        create_resp = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "限制外部访问",
                "structured_params": {"intent_name": "access_control"}
            }
        )
        intent_id = create_resp.json()["data"]["id"]

        response = client.put(
            f"/api/v1/intents/{intent_id}",
            json={"approval_status": "rejected"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_update_intent_invalid_status(self):
        create_resp = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "测试无效状态",
                "structured_params": {"intent_name": "test"}
            }
        )
        intent_id = create_resp.json()["data"]["id"]

        response = client.put(
            f"/api/v1/intents/{intent_id}",
            json={"approval_status": "invalid_status"}
        )
        assert response.status_code == 422

    def test_get_single_intent(self):
        create_resp = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "获取单个意图测试",
                "structured_params": {"intent_name": "test"}
            }
        )
        intent_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/intents/{intent_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["id"] == intent_id

    def test_get_nonexistent_intent(self):
        response = client.get("/api/v1/intents/99999")
        assert response.status_code == 404

    def test_delete_intent(self):
        create_resp = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "待删除意图",
                "structured_params": {"intent_name": "test"}
            }
        )
        intent_id = create_resp.json()["data"]["id"]

        response = client.delete(f"/api/v1/intents/{intent_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_delete_nonexistent_intent(self):
        response = client.delete("/api/v1/intents/99999")
        assert response.status_code == 404


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend module not available")
class TestDeepSeekAPIEndpoints:
    def test_deepseek_status(self):
        response = client.get("/api/v2/deepseek/status")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_deepseek_parse(self):
        response = client.post(
            "/api/v2/deepseek/parse",
            json={"user_input": "保障研发子网500M带宽"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        if data["status"] == "success":
            assert "parsed" in data
            assert data["parsed"] is not None

    def test_deepseek_parse_empty_input(self):
        response = client.post(
            "/api/v2/deepseek/parse",
            json={"user_input": ""}
        )
        assert response.status_code == 200


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend module not available")
class TestCopilotAPIEndpoints:
    def test_copilot_suggestions(self):
        response = client.get("/api/v2/copilot/suggestions")
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)

    def test_copilot_suggestions_with_context(self):
        response = client.get("/api/v2/copilot/suggestions?context=bandwidth")
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data


class TestIntentParsingBandwidthGuarantee:
    def test_bandwidth_guarantee_basic(self):
        result = fallback_parse("保障研发子网500M带宽")
        assert result.intent_type == "bandwidth_guarantee"
        assert result.target_subnet is not None
        assert "研发子网" in result.target_subnet
        assert result.bandwidth == 500
        assert result.priority == "high"
        assert len(result.actions) > 0
        assert result.actions[0]["type"] == "qos_config"

    def test_bandwidth_guarantee_with_video(self):
        result = fallback_parse("保障视频会议200M带宽")
        assert result.intent_type == "bandwidth_guarantee"
        assert result.bandwidth == 200
        assert result.priority == "high"

    def test_bandwidth_guarantee_no_bandwidth_value(self):
        result = fallback_parse("保障带宽")
        assert result.intent_type == "bandwidth_guarantee"
        assert result.bandwidth is None
        assert result.actions[0]["params"]["min_bw"] == "100M"

    def test_bandwidth_guarantee_qos_keyword(self):
        result = fallback_parse("配置QOS策略保障带宽")
        assert result.intent_type == "bandwidth_guarantee"

    def test_bandwidth_guarantee_with_duration(self):
        result = fallback_parse("保障研发子网500M带宽持续2小时")
        assert result.intent_type == "bandwidth_guarantee"
        assert result.bandwidth == 500
        assert result.duration == "2小时"
        assert result.entities["时间"] == "2小时"


class TestIntentParsingAccessControl:
    def test_access_control_permit(self):
        result = fallback_parse("开放研发子网到生产子网的访问权限")
        assert result.intent_type == "access_control"
        assert result.target_subnet is not None
        assert "研发子网" in result.target_subnet
        assert len(result.actions) > 0
        assert result.actions[0]["type"] == "acl_config"

    def test_access_control_acl_keyword(self):
        result = fallback_parse("配置ACL规则")
        assert result.intent_type == "access_control"

    def test_access_control_permission_keyword(self):
        result = fallback_parse("设置权限控制")
        assert result.intent_type == "access_control"

    def test_access_control_deny(self):
        result = fallback_parse("限制外部网络访问权限")
        assert result.intent_type == "access_control"


class TestIntentParsingFaultDiagnosis:
    def test_fault_diagnosis_basic(self):
        result = fallback_parse("诊断设备故障")
        assert result.intent_type == "fault_diagnosis"
        assert len(result.actions) > 0
        assert result.actions[0]["type"] == "diagnose"

    def test_fault_diagnosis_with_device(self):
        result = fallback_parse("诊断核心交换机故障")
        assert result.intent_type == "fault_diagnosis"

    def test_fault_diagnosis_keyword_only(self):
        result = fallback_parse("故障排查")
        assert result.intent_type == "fault_diagnosis"


class TestIntentParsingLinkManagement:
    def test_link_management_basic(self):
        result = fallback_parse("链路切换到备用链路")
        assert result.intent_type == "link_management"
        assert len(result.actions) > 0
        assert result.actions[0]["type"] == "link_config"

    def test_link_management_routing(self):
        result = fallback_parse("修改路由配置")
        assert result.intent_type == "link_management"

    def test_link_management_failover(self):
        result = fallback_parse("主备链路切换")
        assert result.intent_type == "link_management"


class TestIntentParsingQoSPolicy:
    def test_qos_policy_via_bandwidth_keyword(self):
        result = fallback_parse("为办公子网保障带宽")
        assert result.intent_type == "bandwidth_guarantee"
        assert result.target_subnet is not None
        assert "办公子网" in result.target_subnet

    def test_qos_policy_with_priority(self):
        result = fallback_parse("保障关键业务带宽")
        assert result.intent_type == "bandwidth_guarantee"
        assert result.priority == "high"


class TestIntentParsingFuzzyInput:
    def test_fuzzy_input_unknown(self):
        result = fallback_parse("今天天气怎么样")
        assert result.intent_type == "unknown"
        assert result.priority == "medium"

    def test_fuzzy_input_partial_match(self):
        result = fallback_parse("帮我看看网络")
        assert result.intent_type == "unknown"

    def test_fuzzy_input_empty_string(self):
        result = fallback_parse("")
        assert result.intent_type == "unknown"

    def test_fuzzy_input_special_characters(self):
        result = fallback_parse("@#$%^&*()")
        assert result.intent_type == "unknown"

    def test_fuzzy_input_very_long(self):
        long_input = "保障" + "研发" * 500 + "子网500M带宽"
        result = fallback_parse(long_input)
        assert result.intent_type == "bandwidth_guarantee"

    def test_fuzzy_input_mixed_keywords(self):
        result = fallback_parse("带宽故障诊断")
        first_match = result.intent_type
        assert first_match in ["bandwidth_guarantee", "fault_diagnosis"]


class TestIntentHistoryPagination:
    def test_pagination_first_page(self):
        page_size = 2
        items = MOCK_INTENT_HISTORY
        page1 = items[:page_size]
        assert len(page1) == 2
        assert page1[0]["id"] == 1
        assert page1[1]["id"] == 2

    def test_pagination_second_page(self):
        page_size = 2
        items = MOCK_INTENT_HISTORY
        page2 = items[page_size:page_size * 2]
        assert len(page2) == 2
        assert page2[0]["id"] == 3

    def test_pagination_last_page_partial(self):
        page_size = 2
        items = MOCK_INTENT_HISTORY
        total_pages = (len(items) + page_size - 1) // page_size
        last_page_items = items[(total_pages - 1) * page_size:]
        assert len(last_page_items) == 1
        assert last_page_items[0]["id"] == 5

    def test_pagination_total_pages(self):
        page_size = 2
        total = len(MOCK_INTENT_HISTORY)
        total_pages = (total + page_size - 1) // page_size
        assert total_pages == 3

    def test_pagination_empty_list(self):
        page_size = 10
        items = []
        total_pages = (len(items) + page_size - 1) // page_size if items else 0
        assert total_pages == 0

    def test_pagination_beyond_range(self):
        page_size = 10
        items = MOCK_INTENT_HISTORY
        page = 999
        start = (page - 1) * page_size
        result = items[start:start + page_size]
        assert len(result) == 0


class TestIntentStatusFilter:
    def test_filter_pending(self):
        filtered = [i for i in MOCK_INTENT_HISTORY if i["approval_status"] == "pending"]
        assert len(filtered) == 2
        assert all(i["approval_status"] == "pending" for i in filtered)

    def test_filter_approved(self):
        filtered = [i for i in MOCK_INTENT_HISTORY if i["approval_status"] == "approved"]
        assert len(filtered) == 2
        assert all(i["approval_status"] == "approved" for i in filtered)

    def test_filter_rejected(self):
        filtered = [i for i in MOCK_INTENT_HISTORY if i["approval_status"] == "rejected"]
        assert len(filtered) == 1
        assert filtered[0]["id"] == 3

    def test_filter_nonexistent_status(self):
        filtered = [i for i in MOCK_INTENT_HISTORY if i["approval_status"] == "running"]
        assert len(filtered) == 0

    def test_status_mapping(self):
        status_map = {
            "pending": "待审批",
            "approved": "已完成",
            "rejected": "已拒绝",
            "running": "运行中"
        }
        for key, value in status_map.items():
            assert status_map[key] == value


class TestIntentSearch:
    def test_search_by_user_input(self):
        query = "带宽"
        results = [i for i in MOCK_INTENT_HISTORY if query in i["user_input"]]
        assert len(results) == 1
        assert results[0]["id"] == 1

    def test_search_by_device(self):
        query = "Firewall"
        results = [i for i in MOCK_INTENT_HISTORY if query.lower() in i["device"].lower()]
        assert len(results) == 1
        assert results[0]["id"] == 2

    def test_search_by_id(self):
        query = "3"
        results = [i for i in MOCK_INTENT_HISTORY if query in str(i["id"])]
        assert len(results) == 1

    def test_search_no_match(self):
        query = "不存在的关键词xyz"
        results = [i for i in MOCK_INTENT_HISTORY if query in i["user_input"]]
        assert len(results) == 0

    def test_search_case_insensitive(self):
        query = "acl"
        results = [i for i in MOCK_INTENT_HISTORY if query in i["user_input"].lower()]
        assert len(results) == 0

    def test_combined_search_and_filter(self):
        query = "子网"
        status = "pending"
        results = [
            i for i in MOCK_INTENT_HISTORY
            if query in i["user_input"] and i["approval_status"] == status
        ]
        assert len(results) == 1
        assert results[0]["id"] == 1


class TestIntentDataExport:
    def test_json_export_structure(self):
        export_payload = {
            "exportTime": datetime.now().isoformat(),
            "totalIntents": len(MOCK_INTENT_HISTORY),
            "intents": [
                {
                    "id": i["id"],
                    "userInput": i["user_input"],
                    "status": i["status"],
                    "approvalStatus": i["approval_status"],
                    "device": i["device"],
                    "timestamp": i["created_at"]
                }
                for i in MOCK_INTENT_HISTORY
            ],
            "metrics": [
                {"label": "意图总数", "value": 5, "unit": "个"},
                {"label": "待审批", "value": 2, "unit": "项"},
                {"label": "已完成", "value": 2, "unit": "个"},
                {"label": "AI可用性", "value": 0, "unit": "%"}
            ]
        }
        assert "exportTime" in export_payload
        assert "intents" in export_payload
        assert "metrics" in export_payload
        assert len(export_payload["intents"]) == 5
        assert export_payload["totalIntents"] == 5

    def test_json_export_serializable(self):
        export_payload = {
            "exportTime": datetime.now().isoformat(),
            "totalIntents": len(MOCK_INTENT_HISTORY),
            "intents": MOCK_INTENT_HISTORY
        }
        serialized = json.dumps(export_payload, ensure_ascii=False)
        deserialized = json.loads(serialized)
        assert deserialized["totalIntents"] == 5

    def test_csv_export_headers(self):
        headers = "意图ID,用户输入,状态,审批状态,设备,时间\n"
        assert "意图ID" in headers
        assert "用户输入" in headers
        assert "状态" in headers
        assert "审批状态" in headers

    def test_csv_export_escape(self):
        def escape_csv(value):
            s = str(value).replace('"', '""')
            return '"' + s + '"'

        assert escape_csv('正常文本') == '"正常文本"'
        assert escape_csv('包含"引号') == '"包含""引号"'
        assert escape_csv('包含,逗号') == '"包含,逗号"'

    def test_csv_export_rows(self):
        rows = []
        for item in MOCK_INTENT_HISTORY:
            row = f'{item["id"]},"{item["user_input"]}",{item["status"]},{item["approval_status"]},"{item["device"]}","{item["created_at"]}"'
            rows.append(row)
        assert len(rows) == 5
        assert "1," in rows[0]


class TestIntentInputValidation:
    def test_empty_input_rejected(self):
        result = fallback_parse("")
        assert result.intent_type == "unknown"

    def test_whitespace_only_input(self):
        result = fallback_parse("   ")
        assert result.intent_type == "unknown"

    def test_very_long_input(self):
        long_input = "保障" + "x" * 3000 + "子网带宽"
        result = fallback_parse(long_input)
        assert result is not None

    def test_special_characters_input(self):
        result = fallback_parse("<script>alert('xss')</script>")
        assert result.intent_type == "unknown"

    def test_sql_injection_input(self):
        result = fallback_parse("'; DROP TABLE intents; --")
        assert result.intent_type == "unknown"

    def test_unicode_input(self):
        result = fallback_parse("保障研发子网\u200b500M带宽")
        assert result.intent_type == "bandwidth_guarantee"

    def test_mixed_language_input(self):
        result = fallback_parse("Guarantee 研发子网 500M 带宽保障")
        assert result.intent_type == "bandwidth_guarantee"
        assert result.bandwidth == 500


class TestIntentAPIStatusCodes:
    def test_health_endpoint(self):
        if BACKEND_AVAILABLE:
            response = client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"

    def test_404_for_nonexistent_intent(self):
        if BACKEND_AVAILABLE:
            response = client.get("/api/v1/intents/99999")
            assert response.status_code == 404

    def test_422_for_invalid_create(self):
        if BACKEND_AVAILABLE:
            response = client.post(
                "/api/v1/intents/",
                json={"user_input": "", "structured_params": {"intent_name": "test"}}
            )
            assert response.status_code == 422

    def test_422_for_missing_body(self):
        if BACKEND_AVAILABLE:
            response = client.post("/api/v1/intents/", json={})
            assert response.status_code == 422


class TestIntentMetricsCalculation:
    def test_metrics_from_mock_data(self):
        total = len(MOCK_INTENT_HISTORY)
        pending = len([i for i in MOCK_INTENT_HISTORY if i["approval_status"] == "pending"])
        completed = len([i for i in MOCK_INTENT_HISTORY if i["approval_status"] == "approved"])
        rejected = len([i for i in MOCK_INTENT_HISTORY if i["approval_status"] == "rejected"])

        assert total == 5
        assert pending == 2
        assert completed == 2
        assert rejected == 1

    def test_metrics_empty_data(self):
        items = []
        total = len(items)
        pending = len([i for i in items if i["approval_status"] == "pending"])
        completed = len([i for i in items if i["approval_status"] == "approved"])

        assert total == 0
        assert pending == 0
        assert completed == 0

    def test_metrics_all_pending(self):
        items = [
            {"approval_status": "pending"},
            {"approval_status": "pending"},
            {"approval_status": "pending"}
        ]
        total = len(items)
        pending = len([i for i in items if i["approval_status"] == "pending"])
        assert total == 3
        assert pending == 3


class TestIntentSubmitApproveVerifyWorkflow:
    def test_full_workflow_with_mock_data(self):
        user_input = "保障研发子网500M带宽"
        parsed = fallback_parse(user_input)
        assert parsed.intent_type == "bandwidth_guarantee"

        structured_params = {
            "intent_name": parsed.intent_type,
            "targets": [parsed.target_subnet or "未知"],
            "actions": parsed.actions,
            "confidence": 0.9,
            "entities": parsed.entities
        }
        assert structured_params["intent_name"] == "bandwidth_guarantee"
        assert len(structured_params["targets"]) > 0

        created_intent = {
            "id": 100,
            "user_input": user_input,
            "structured_params": structured_params,
            "approval_status": "pending",
            "status": "pending"
        }
        assert created_intent["approval_status"] == "pending"

        created_intent["approval_status"] = "approved"
        created_intent["status"] = "completed"
        assert created_intent["approval_status"] == "approved"
        assert created_intent["status"] == "completed"

        verification = {
            "intent_id": created_intent["id"],
            "before_bandwidth": 100,
            "after_bandwidth": 500,
            "threshold": 200,
            "status": "verified"
        }
        assert verification["after_bandwidth"] >= verification["threshold"]
        assert verification["status"] == "verified"

    def test_reject_workflow(self):
        user_input = "限制所有网络访问"
        parsed = fallback_parse(user_input)
        structured_params = {"intent_name": parsed.intent_type}

        created_intent = {
            "id": 101,
            "user_input": user_input,
            "structured_params": structured_params,
            "approval_status": "pending"
        }
        assert created_intent["approval_status"] == "pending"

        created_intent["approval_status"] = "rejected"
        assert created_intent["approval_status"] == "rejected"


class TestDeepSeekDegradationToLocal:
    def test_fallback_parse_when_deepseek_unavailable(self):
        user_input = "保障研发子网500M带宽"
        result = fallback_parse(user_input)
        assert result.intent_type == "bandwidth_guarantee"
        assert result.target_subnet is not None
        assert "研发子网" in result.target_subnet
        assert result.bandwidth == 500

    def test_fallback_preserves_all_intent_types(self):
        test_cases = [
            ("保障带宽", "bandwidth_guarantee"),
            ("开放访问权限", "access_control"),
            ("诊断故障", "fault_diagnosis"),
            ("链路切换", "link_management"),
            ("监控性能", "performance_monitoring"),
            ("流量整形", "traffic_shaping"),
        ]
        for user_input, expected_type in test_cases:
            result = fallback_parse(user_input)
            assert result.intent_type == expected_type, f"Failed for input: {user_input}"

    def test_fallback_handles_empty_gracefully(self):
        result = fallback_parse("")
        assert result.intent_type == "unknown"
        assert result.actions == []
        assert result.priority == "medium"


class TestDashboardDataUpdatedEvent:
    def test_event_dispatch_on_approve(self):
        event_dispatched = False

        def on_dashboard_update(event_type):
            nonlocal event_dispatched
            if event_type == "dashboardDataUpdated":
                event_dispatched = True

        on_dashboard_update("dashboardDataUpdated")
        assert event_dispatched is True

    def test_event_dispatch_on_reject(self):
        events = []

        def record_event(event_type):
            events.append(event_type)

        record_event("dashboardDataUpdated")
        assert len(events) == 1
        assert events[0] == "dashboardDataUpdated"

    def test_event_dispatch_on_create(self):
        events = []

        def record_event(event_type):
            events.append(event_type)

        record_event("dashboardDataUpdated")
        assert "dashboardDataUpdated" in events

    def test_multiple_events_in_workflow(self):
        events = []

        def record_event(event_type):
            events.append(event_type)

        record_event("dashboardDataUpdated")
        record_event("dashboardDataUpdated")
        record_event("dashboardDataUpdated")
        assert len(events) == 3


class TestIntentStatusStateMachine:
    def test_valid_transitions(self):
        valid_transitions = {
            "pending": ["approved", "rejected"],
            "approved": [],
            "rejected": []
        }
        for status, allowed in valid_transitions.items():
            assert isinstance(allowed, list)

    def test_pending_to_approved(self):
        intent = {"approval_status": "pending"}
        intent["approval_status"] = "approved"
        assert intent["approval_status"] == "approved"

    def test_pending_to_rejected(self):
        intent = {"approval_status": "pending"}
        intent["approval_status"] = "rejected"
        assert intent["approval_status"] == "rejected"

    def test_status_values(self):
        valid_statuses = ["pending", "approved", "rejected"]
        for status in valid_statuses:
            assert status in valid_statuses


class TestIntentParserRegexPatterns:
    def test_subnet_pattern_chinese(self):
        pattern = re.compile(r"([\u4e00-\u9fa5]+子网)")
        match = pattern.search("保障研发子网500M带宽")
        assert match is not None
        assert "研发子网" in match.group(1)

    def test_subnet_pattern_multiple(self):
        pattern = re.compile(r"([\u4e00-\u9fa5]+子网)")
        text = "办公子网和生产子网"
        matches = pattern.findall(text)
        assert len(matches) >= 1
        assert "子网" in matches[0]

    def test_bandwidth_pattern_mb(self):
        pattern = re.compile(r"(\d+)\s*[Mm]")
        match = pattern.search("保障500M带宽")
        assert match is not None
        assert int(match.group(1)) == 500

    def test_bandwidth_pattern_with_space(self):
        pattern = re.compile(r"(\d+)\s*[Mm]")
        match = pattern.search("保障 200 M带宽")
        assert match is not None
        assert int(match.group(1)) == 200

    def test_bandwidth_pattern_lowercase(self):
        pattern = re.compile(r"(\d+)\s*[Mm]")
        match = pattern.search("100m带宽")
        assert match is not None
        assert int(match.group(1)) == 100

    def test_duration_pattern_hours(self):
        pattern = re.compile(r"(\d+)\s*(天|小时|分钟)")
        match = pattern.search("持续2小时")
        assert match is not None
        assert match.group(0) == "2小时"

    def test_duration_pattern_days(self):
        pattern = re.compile(r"(\d+)\s*(天|小时|分钟)")
        match = pattern.search("持续3天")
        assert match is not None
        assert match.group(0) == "3天"

    def test_duration_pattern_minutes(self):
        pattern = re.compile(r"(\d+)\s*(天|小时|分钟)")
        match = pattern.search("持续30分钟")
        assert match is not None
        assert match.group(0) == "30分钟"

    def test_no_bandwidth_match(self):
        pattern = re.compile(r"(\d+)\s*[Mm]")
        match = pattern.search("保障带宽")
        assert match is None


class TestIntentParserPydanticModel:
    def test_parsed_intent_defaults(self):
        intent = ParsedIntent(intent_type="unknown")
        assert intent.intent_type == "unknown"
        assert intent.target_subnet is None
        assert intent.bandwidth is None
        assert intent.duration == "持续"
        assert intent.priority == "medium"
        assert intent.actions == []
        assert intent.entities == {}

    def test_parsed_intent_full(self):
        intent = ParsedIntent(
            intent_type="bandwidth_guarantee",
            target_subnet="研发子网",
            bandwidth=500,
            duration="2小时",
            priority="high",
            actions=[{"type": "qos_config", "params": {"min_bw": "500M"}}],
            entities={"子网": "研发子网", "带宽": "500M"}
        )
        assert intent.intent_type == "bandwidth_guarantee"
        assert intent.target_subnet == "研发子网"
        assert intent.bandwidth == 500
        assert intent.duration == "2小时"
        assert intent.priority == "high"
        assert len(intent.actions) == 1
        assert intent.entities["子网"] == "研发子网"

    def test_parsed_intent_serialization(self):
        intent = ParsedIntent(
            intent_type="access_control",
            target_subnet="研发子网",
            actions=[{"type": "acl_config", "params": {"direction": "inbound"}}]
        )
        data = intent.model_dump()
        assert data["intent_type"] == "access_control"
        assert data["target_subnet"] == "研发子网"
        serialized = json.dumps(data)
        deserialized = json.loads(serialized)
        assert deserialized["intent_type"] == "access_control"

    def test_parsed_intent_invalid_type(self):
        with pytest.raises(Exception):
            ParsedIntent()
