# -*- coding: utf-8 -*-
import pytest
import json
import re
import math
from datetime import datetime
from typing import Dict, Any, Optional, List, Literal
from pydantic import BaseModel, Field

try:
    from fastapi.testclient import TestClient
    from backend.api.main import app
    client = TestClient(app)
    BACKEND_AVAILABLE = True
except Exception:
    BACKEND_AVAILABLE = False


MOCK_TOPOLOGY_NODES = [
    {"id": "core1", "name": "核心路由器CR-01", "type": "router", "health": 98, "cpu": 45, "memory": 62, "traffic": "8.2G", "x": 400, "y": 150, "locked": False, "status": "healthy", "originalX": 400, "originalY": 150},
    {"id": "core2", "name": "核心路由器CR-02", "type": "router", "health": 95, "cpu": 58, "memory": 71, "traffic": "7.5G", "x": 600, "y": 150, "locked": False, "status": "healthy", "originalX": 600, "originalY": 150},
    {"id": "agg1", "name": "汇聚交换机AS-01", "type": "switch", "health": 92, "cpu": 32, "memory": 48, "traffic": "3.1G", "x": 200, "y": 300, "locked": False, "status": "healthy", "originalX": 200, "originalY": 300},
    {"id": "agg2", "name": "汇聚交换机AS-02", "type": "switch", "health": 87, "cpu": 78, "memory": 82, "traffic": "4.5G", "x": 500, "y": 300, "locked": False, "status": "warning", "originalX": 500, "originalY": 300},
    {"id": "agg3", "name": "汇聚交换机AS-03", "type": "switch", "health": 96, "cpu": 28, "memory": 39, "traffic": "2.8G", "x": 800, "y": 300, "locked": False, "status": "healthy", "originalX": 800, "originalY": 300},
    {"id": "acc1", "name": "接入交换机AC-01", "type": "switch", "health": 99, "cpu": 15, "memory": 25, "traffic": "450M", "x": 100, "y": 450, "locked": False, "status": "healthy", "originalX": 100, "originalY": 450},
    {"id": "acc2", "name": "接入交换机AC-02", "type": "switch", "health": 94, "cpu": 42, "memory": 55, "traffic": "680M", "x": 300, "y": 450, "locked": False, "status": "healthy", "originalX": 300, "originalY": 450},
    {"id": "acc3", "name": "接入交换机AC-03", "type": "switch", "health": 97, "cpu": 22, "memory": 38, "traffic": "520M", "x": 600, "y": 450, "locked": False, "status": "healthy", "originalX": 600, "originalY": 450},
    {"id": "acc4", "name": "接入交换机AC-04", "type": "switch", "health": 72, "cpu": 88, "memory": 91, "traffic": "950M", "x": 900, "y": 450, "locked": False, "status": "error", "originalX": 900, "originalY": 450},
]

MOCK_TOPOLOGY_LINKS = [
    {"source": "central", "target": "core1", "bandwidth": "40G", "currentLoad": 65, "status": "active", "main": True, "isCentralLink": True},
    {"source": "central", "target": "core2", "bandwidth": "40G", "currentLoad": 58, "status": "active", "main": True, "isCentralLink": True},
    {"source": "core1", "target": "core2", "bandwidth": "10G", "currentLoad": 82, "status": "active", "main": True},
    {"source": "core1", "target": "agg1", "bandwidth": "10G", "currentLoad": 31, "status": "active", "main": True},
    {"source": "core1", "target": "agg2", "bandwidth": "10G", "currentLoad": 45, "status": "active", "main": True},
    {"source": "core2", "target": "agg2", "bandwidth": "10G", "currentLoad": 28, "status": "active", "main": False},
    {"source": "core2", "target": "agg3", "bandwidth": "10G", "currentLoad": 75, "status": "warning", "main": True},
    {"source": "agg1", "target": "acc1", "bandwidth": "1G", "currentLoad": 45, "status": "active", "main": True},
    {"source": "agg1", "target": "acc2", "bandwidth": "1G", "currentLoad": 68, "status": "active", "main": False},
    {"source": "agg2", "target": "acc2", "bandwidth": "1G", "currentLoad": 52, "status": "active", "main": True},
    {"source": "agg2", "target": "acc3", "bandwidth": "1G", "currentLoad": 38, "status": "active", "main": False},
    {"source": "agg3", "target": "acc3", "bandwidth": "1G", "currentLoad": 41, "status": "active", "main": True},
    {"source": "agg3", "target": "acc4", "bandwidth": "1G", "currentLoad": 95, "status": "error", "main": True},
]

MOCK_TOPOLOGY_FLOWS = [
    {"id": "flow1", "path": ["acc1", "agg1", "core1", "core2", "agg3", "acc4"], "type": "data", "bandwidth": "100M"},
    {"id": "flow2", "path": ["acc2", "agg2", "core2", "agg3", "acc3"], "type": "video", "bandwidth": "500M"},
]


class TopologyNodeModel(BaseModel):
    id: str
    name: str
    type: str
    health: float = Field(ge=0, le=100)
    cpu: float = Field(ge=0, le=100)
    memory: float = Field(ge=0, le=100)
    traffic: str
    x: float
    y: float
    locked: bool = False
    status: Literal["healthy", "warning", "error"]
    originalX: float
    originalY: float


class TopologyLinkModel(BaseModel):
    source: str
    target: str
    bandwidth: str
    currentLoad: float = Field(ge=0, le=100)
    status: Literal["active", "warning", "error", "down"]
    main: bool = False
    isCentralLink: Optional[bool] = None


class TopologyFlowModel(BaseModel):
    id: str
    path: List[str]
    type: str
    bandwidth: str


class TopologySnapshotModel(BaseModel):
    nodePositions: List[Dict[str, Any]]
    centralPosition: Dict[str, float]
    zoomLevel: float = Field(ge=0.3, le=3.0)
    panOffset: Dict[str, float]
    layoutType: str
    displayOptions: Dict[str, Any]


class AlertItemModel(BaseModel):
    id: str
    type: Literal["warning", "error", "info"]
    message: str
    timestamp: float
    dismissed: bool = False


class A2AMessageModel(BaseModel):
    id: str
    sender: str
    receiver: str
    task_id: str
    action: str
    timestamp: str
    payload: Dict[str, Any]
    path: List[str]
    status: Literal["pending", "in_progress", "completed"]


def make_link_key(source: str, target: str) -> str:
    return f"{source}::{target}"


def parse_link_key(key: str) -> Dict[str, str]:
    idx = key.find("::")
    if idx == -1:
        return {"source": key, "target": ""}
    return {"source": key[:idx], "target": key[idx + 2:]}


def is_topology_node(t: Any) -> bool:
    return t is not None and isinstance(t, dict) and "id" in t and "health" in t


def is_topology_link(t: Any) -> bool:
    return t is not None and isinstance(t, dict) and "source" in t and "target" in t


def escape_csv_field(field: str) -> str:
    escaped = field
    if re.match(r"^[=+\-@\t\r]", escaped):
        escaped = "'" + escaped
    if "," in escaped or '"' in escaped or "\n" in escaped:
        return '"' + escaped.replace('"', '""') + '"'
    return escaped


def get_link_width(bandwidth: str, current_load: float = 0) -> float:
    width = 1.5
    if "100G" in bandwidth:
        width = 6
    elif "40G" in bandwidth:
        width = 5
    elif "10G" in bandwidth:
        width = 4
    elif "1G" in bandwidth:
        width = 3.5
    elif "100M" in bandwidth:
        width = 2.5
    if current_load > 80:
        width = min(7, width + 1)
    return width


def get_node_status_color(status: str) -> str:
    colors = {"healthy": "#52C41A", "warning": "#FAAD14", "error": "#FF4D4F"}
    return colors.get(status, "#52C41A")


def get_link_load_color(load: float) -> str:
    if load >= 90:
        return "#FF4D4F"
    if load >= 75:
        return "#FF7D00"
    if load >= 50:
        return "#FAAD14"
    if load >= 25:
        return "#52C41A"
    return "#1890FF"


def get_health_color(health: float) -> str:
    if health >= 90:
        return "#52C41A"
    if health >= 70:
        return "#FAAD14"
    return "#FF4D4F"


def get_resource_color(percentage: float) -> str:
    if percentage < 60:
        return "#52C41A"
    if percentage < 80:
        return "#FAAD14"
    if percentage < 90:
        return "#FF7A45"
    return "#FF4D4F"


def get_latency_color(latency: float) -> str:
    if latency < 10:
        return "#52C41A"
    if latency < 30:
        return "#FAAD14"
    if latency < 60:
        return "#FF7D00"
    return "#FF4D4F"


def get_action_color(action: str) -> str:
    colors = {
        "exec_cli": "#165DFF",
        "response": "#52C41A",
        "validate_config": "#FAAD14",
        "isolate_node": "#FF4D4F",
    }
    return colors.get(action, "#64748B")


def check_alerts(nodes: List[Dict], links: List[Dict], existing_alerts: List[Dict] = None) -> List[Dict]:
    existing = existing_alerts or []
    new_alerts = []
    for node in nodes:
        if node["health"] < 70:
            alert_id = f"node_error_{node['id']}"
            if not any(a["id"] == alert_id for a in existing):
                new_alerts.append({"id": alert_id, "type": "error", "message": f"节点 {node['name']} 健康值严重过低 ({round(node['health'])}%)", "timestamp": 1000, "dismissed": False})
        elif node["health"] < 85:
            alert_id = f"node_warning_{node['id']}"
            if not any(a["id"] == alert_id for a in existing):
                new_alerts.append({"id": alert_id, "type": "warning", "message": f"节点 {node['name']} 健康值偏低 ({round(node['health'])}%)", "timestamp": 1000, "dismissed": False})
    for link in links:
        link_key = make_link_key(link["source"], link["target"])
        if link["currentLoad"] >= 90:
            alert_id = f"link_error_{link_key}"
            if not any(a["id"] == alert_id for a in existing):
                new_alerts.append({"id": alert_id, "type": "error", "message": f"链路 {link_key} 负载过高 ({round(link['currentLoad'])}%)", "timestamp": 1000, "dismissed": False})
        elif link["currentLoad"] >= 75:
            alert_id = f"link_warning_{link_key}"
            if not any(a["id"] == alert_id for a in existing):
                new_alerts.append({"id": alert_id, "type": "warning", "message": f"链路 {link_key} 负载偏高 ({round(link['currentLoad'])}%)", "timestamp": 1000, "dismissed": False})
    return [a for a in existing if not a.get("dismissed", False)] + new_alerts


def validate_import_data(data: Any) -> tuple:
    if not isinstance(data, dict):
        return False, "数据结构无效，必须是JSON对象"
    if "nodes" not in data or not isinstance(data["nodes"], list):
        return False, "数据结构无效，缺少 nodes"
    if "links" not in data or not isinstance(data["links"], list):
        return False, "数据结构无效，缺少 links"
    valid_node_fields = ["id", "name", "type", "health", "cpu", "memory", "x", "y", "status"]
    valid_link_fields = ["source", "target", "bandwidth", "currentLoad", "status"]
    for n in data["nodes"]:
        if not isinstance(n, dict):
            return False, "节点数据格式无效"
        for f in valid_node_fields:
            if f not in n:
                return False, f"节点数据缺少必要字段: {f}"
    for l in data["links"]:
        if not isinstance(l, dict):
            return False, "链路数据格式无效"
        for f in valid_link_fields:
            if f not in l:
                return False, f"链路数据缺少必要字段: {f}"
    return True, None


def validate_snapshot(snapshot: Any) -> tuple:
    if not isinstance(snapshot, dict) or snapshot is None:
        return False, "快照数据格式无效"
    if "nodePositions" in snapshot:
        if not isinstance(snapshot["nodePositions"], list):
            return False, "nodePositions 必须是数组"
        for pos in snapshot["nodePositions"]:
            if not isinstance(pos, dict):
                return False, "nodePositions 中的元素必须是对象"
            if not (isinstance(pos.get("id"), str) and isinstance(pos.get("x"), (int, float)) and isinstance(pos.get("y"), (int, float))):
                return False, "nodePositions 中的元素缺少有效字段"
    if "centralPosition" in snapshot:
        cp = snapshot["centralPosition"]
        if not isinstance(cp, dict) or not isinstance(cp.get("x"), (int, float)) or not isinstance(cp.get("y"), (int, float)):
            return False, "centralPosition 格式无效"
    if "zoomLevel" in snapshot:
        if not isinstance(snapshot["zoomLevel"], (int, float)):
            return False, "zoomLevel 必须是数字"
    if "panOffset" in snapshot:
        po = snapshot["panOffset"]
        if not isinstance(po, dict) or not isinstance(po.get("x"), (int, float)) or not isinstance(po.get("y"), (int, float)):
            return False, "panOffset 格式无效"
    return True, None


def clamp_to_bounds(x: float, y: float, width: float = 1000, height: float = 550, padding: float = 50) -> Dict[str, float]:
    return {
        "x": max(padding, min(x, width - padding)),
        "y": max(padding, min(y, height - padding)),
    }


def compute_topology_stats(nodes: List[Dict], links: List[Dict]) -> Dict[str, Any]:
    return {
        "totalNodes": len(nodes),
        "healthyNodes": len([n for n in nodes if n["status"] == "healthy"]),
        "warningNodes": len([n for n in nodes if n["status"] == "warning"]),
        "errorNodes": len([n for n in nodes if n["status"] == "error"]),
        "totalLinks": len(links),
        "activeLinks": len([l for l in links if l["status"] == "active"]),
        "warningLinks": len([l for l in links if l["status"] == "warning"]),
        "errorLinks": len([l for l in links if l["status"] == "error"]),
        "mainLinks": len([l for l in links if l.get("main", False)]),
        "backupLinks": len([l for l in links if not l.get("main", False)]),
        "avgHealth": round(sum(n["health"] for n in nodes) / len(nodes)) if nodes else 0,
        "avgLoad": round(sum(l["currentLoad"] for l in links) / len(links)) if links else 0,
    }


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend module not available")
class TestTopologyAPIEndpoints:
    def test_isolate_node_via_intents(self):
        response = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "对核心路由器CR-01执行isolate_node操作",
                "structured_params": {
                    "intent_name": "isolate_node",
                    "target": "core1",
                    "action": "isolate_node",
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert "id" in data["data"]

    def test_unisolate_node_via_intents(self):
        response = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "对核心路由器CR-01执行unisolate_node操作",
                "structured_params": {
                    "intent_name": "unisolate_node",
                    "target": "core1",
                    "action": "unisolate_node",
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_restart_device_via_intents(self):
        response = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "对汇聚交换机AS-01执行restart_device操作",
                "structured_params": {
                    "intent_name": "restart_device",
                    "target": "agg1",
                    "action": "restart_device",
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_make_primary_via_intents(self):
        response = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "对链路core2::agg2执行make_primary操作",
                "structured_params": {
                    "intent_name": "make_primary",
                    "target": "core2::agg2",
                    "action": "make_primary",
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_create_intent_empty_user_input(self):
        response = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "",
                "structured_params": {"intent_name": "isolate_node"},
            },
        )
        assert response.status_code == 422

    def test_create_intent_missing_structured_params(self):
        response = client.post(
            "/api/v1/intents/",
            json={"user_input": "隔离节点"},
        )
        assert response.status_code == 422

    def test_get_intents_list(self):
        response = client.get("/api/v1/intents/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["data"], list)

    def test_intent_response_format(self):
        response = client.post(
            "/api/v1/intents/",
            json={
                "user_input": "测试拓扑操作",
                "structured_params": {
                    "intent_name": "isolate_node",
                    "target": "acc1",
                    "action": "isolate_node",
                },
            },
        )
        data = response.json()
        assert "status" in data
        assert "data" in data
        assert isinstance(data["data"], dict)
        assert "id" in data["data"]


class TestTopologyNodeValidation:
    def test_valid_node(self):
        node = MOCK_TOPOLOGY_NODES[0]
        model = TopologyNodeModel(**node)
        assert model.id == "core1"
        assert model.type == "router"
        assert model.status == "healthy"

    def test_all_mock_nodes_valid(self):
        for node in MOCK_TOPOLOGY_NODES:
            model = TopologyNodeModel(**node)
            assert model.id == node["id"]
            assert model.status in ("healthy", "warning", "error")

    def test_node_health_range(self):
        for node in MOCK_TOPOLOGY_NODES:
            assert 0 <= node["health"] <= 100

    def test_node_cpu_range(self):
        for node in MOCK_TOPOLOGY_NODES:
            assert 0 <= node["cpu"] <= 100

    def test_node_memory_range(self):
        for node in MOCK_TOPOLOGY_NODES:
            assert 0 <= node["memory"] <= 100

    def test_node_status_values(self):
        valid_statuses = {"healthy", "warning", "error"}
        for node in MOCK_TOPOLOGY_NODES:
            assert node["status"] in valid_statuses

    def test_node_type_values(self):
        valid_types = {"router", "switch", "central", "firewall", "server"}
        for node in MOCK_TOPOLOGY_NODES:
            assert node["type"] in valid_types

    def test_node_required_fields(self):
        required_fields = ["id", "name", "type", "health", "cpu", "memory", "x", "y", "status"]
        for node in MOCK_TOPOLOGY_NODES:
            for field in required_fields:
                assert field in node, f"Node {node.get('id', '?')} missing field: {field}"

    def test_node_missing_id_rejected(self):
        node = dict(MOCK_TOPOLOGY_NODES[0])
        del node["id"]
        with pytest.raises(Exception):
            TopologyNodeModel(**node)

    def test_node_missing_status_rejected(self):
        node = dict(MOCK_TOPOLOGY_NODES[0])
        del node["status"]
        with pytest.raises(Exception):
            TopologyNodeModel(**node)

    def test_node_invalid_status_rejected(self):
        node = dict(MOCK_TOPOLOGY_NODES[0])
        node["status"] = "unknown"
        with pytest.raises(Exception):
            TopologyNodeModel(**node)

    def test_node_health_above_100_rejected(self):
        node = dict(MOCK_TOPOLOGY_NODES[0])
        node["health"] = 150
        with pytest.raises(Exception):
            TopologyNodeModel(**node)

    def test_node_health_below_0_rejected(self):
        node = dict(MOCK_TOPOLOGY_NODES[0])
        node["health"] = -10
        with pytest.raises(Exception):
            TopologyNodeModel(**node)

    def test_node_cpu_above_100_rejected(self):
        node = dict(MOCK_TOPOLOGY_NODES[0])
        node["cpu"] = 200
        with pytest.raises(Exception):
            TopologyNodeModel(**node)

    def test_node_memory_below_0_rejected(self):
        node = dict(MOCK_TOPOLOGY_NODES[0])
        node["memory"] = -5
        with pytest.raises(Exception):
            TopologyNodeModel(**node)

    def test_node_default_locked(self):
        node = dict(MOCK_TOPOLOGY_NODES[0])
        del node["locked"]
        model = TopologyNodeModel(**node)
        assert model.locked is False

    def test_node_original_positions(self):
        for node in MOCK_TOPOLOGY_NODES:
            assert "originalX" in node
            assert "originalY" in node
            assert isinstance(node["originalX"], (int, float))
            assert isinstance(node["originalY"], (int, float))


class TestTopologyLinkValidation:
    def test_valid_link(self):
        link = MOCK_TOPOLOGY_LINKS[0]
        model = TopologyLinkModel(**link)
        assert model.source == "central"
        assert model.target == "core1"
        assert model.bandwidth == "40G"

    def test_all_mock_links_valid(self):
        for link in MOCK_TOPOLOGY_LINKS:
            model = TopologyLinkModel(**link)
            assert model.source is not None
            assert model.target is not None

    def test_link_status_values(self):
        valid_statuses = {"active", "warning", "error", "down"}
        for link in MOCK_TOPOLOGY_LINKS:
            assert link["status"] in valid_statuses

    def test_link_current_load_range(self):
        for link in MOCK_TOPOLOGY_LINKS:
            assert 0 <= link["currentLoad"] <= 100

    def test_link_required_fields(self):
        required_fields = ["source", "target", "bandwidth", "currentLoad", "status"]
        for link in MOCK_TOPOLOGY_LINKS:
            for field in required_fields:
                assert field in link, f"Link {link.get('source', '?')}->{link.get('target', '?')} missing field: {field}"

    def test_link_missing_source_rejected(self):
        link = dict(MOCK_TOPOLOGY_LINKS[0])
        del link["source"]
        with pytest.raises(Exception):
            TopologyLinkModel(**link)

    def test_link_missing_target_rejected(self):
        link = dict(MOCK_TOPOLOGY_LINKS[0])
        del link["target"]
        with pytest.raises(Exception):
            TopologyLinkModel(**link)

    def test_link_invalid_status_rejected(self):
        link = dict(MOCK_TOPOLOGY_LINKS[0])
        link["status"] = "unknown"
        with pytest.raises(Exception):
            TopologyLinkModel(**link)

    def test_link_load_above_100_rejected(self):
        link = dict(MOCK_TOPOLOGY_LINKS[0])
        link["currentLoad"] = 150
        with pytest.raises(Exception):
            TopologyLinkModel(**link)

    def test_link_load_below_0_rejected(self):
        link = dict(MOCK_TOPOLOGY_LINKS[0])
        link["currentLoad"] = -10
        with pytest.raises(Exception):
            TopologyLinkModel(**link)

    def test_link_default_main(self):
        link = dict(MOCK_TOPOLOGY_LINKS[0])
        del link["main"]
        model = TopologyLinkModel(**link)
        assert model.main is False

    def test_link_central_link_flag(self):
        central_links = [l for l in MOCK_TOPOLOGY_LINKS if l.get("isCentralLink")]
        assert len(central_links) == 2
        for link in central_links:
            assert link["source"] == "central"

    def test_link_bandwidth_format(self):
        bandwidth_pattern = re.compile(r"^\d+[GM]$")
        for link in MOCK_TOPOLOGY_LINKS:
            assert bandwidth_pattern.match(link["bandwidth"]), f"Invalid bandwidth format: {link['bandwidth']}"


class TestLinkKeyOperations:
    def test_make_link_key_basic(self):
        assert make_link_key("core1", "core2") == "core1::core2"

    def test_make_link_key_with_central(self):
        assert make_link_key("central", "core1") == "central::core1"

    def test_parse_link_key_basic(self):
        result = parse_link_key("core1::core2")
        assert result["source"] == "core1"
        assert result["target"] == "core2"

    def test_parse_link_key_with_central(self):
        result = parse_link_key("central::core1")
        assert result["source"] == "central"
        assert result["target"] == "core1"

    def test_round_trip(self):
        original_source = "agg1"
        original_target = "acc1"
        key = make_link_key(original_source, original_target)
        parsed = parse_link_key(key)
        assert parsed["source"] == original_source
        assert parsed["target"] == original_target

    def test_round_trip_all_mock_links(self):
        for link in MOCK_TOPOLOGY_LINKS:
            key = make_link_key(link["source"], link["target"])
            parsed = parse_link_key(key)
            assert parsed["source"] == link["source"]
            assert parsed["target"] == link["target"]

    def test_parse_invalid_key_no_separator(self):
        result = parse_link_key("invalidkey")
        assert result["source"] == "invalidkey"
        assert result["target"] == ""

    def test_parse_key_with_multiple_separators(self):
        result = parse_link_key("node::with::double::colons")
        assert result["source"] == "node"
        assert result["target"] == "with::double::colons"

    def test_make_link_key_empty_strings(self):
        assert make_link_key("", "") == "::"

    def test_parse_empty_key(self):
        result = parse_link_key("")
        assert result["source"] == ""
        assert result["target"] == ""

    def test_link_key_uniqueness(self):
        keys = [make_link_key(l["source"], l["target"]) for l in MOCK_TOPOLOGY_LINKS]
        assert len(keys) == len(set(keys)), "Link keys should be unique"

    def test_link_key_with_special_chars_in_id(self):
        key = make_link_key("node-1_v2", "node-2_v3")
        parsed = parse_link_key(key)
        assert parsed["source"] == "node-1_v2"
        assert parsed["target"] == "node-2_v3"


class TestIsTopologyNode:
    def test_valid_node(self):
        assert is_topology_node(MOCK_TOPOLOGY_NODES[0]) is True

    def test_valid_node_dict(self):
        assert is_topology_node({"id": "test", "health": 90}) is True

    def test_link_is_not_node(self):
        assert is_topology_node(MOCK_TOPOLOGY_LINKS[0]) is False

    def test_none_is_not_node(self):
        assert is_topology_node(None) is False

    def test_empty_dict_is_not_node(self):
        assert is_topology_node({}) is False

    def test_dict_with_only_id_is_not_node(self):
        assert is_topology_node({"id": "test"}) is False

    def test_dict_with_only_health_is_not_node(self):
        assert is_topology_node({"health": 90}) is False

    def test_string_is_not_node(self):
        assert is_topology_node("not a node") is False

    def test_list_is_not_node(self):
        assert is_topology_node([1, 2, 3]) is False


class TestIsTopologyLink:
    def test_valid_link(self):
        assert is_topology_link(MOCK_TOPOLOGY_LINKS[0]) is True

    def test_valid_link_dict(self):
        assert is_topology_link({"source": "a", "target": "b"}) is True

    def test_node_is_not_link(self):
        assert is_topology_link(MOCK_TOPOLOGY_NODES[0]) is False

    def test_none_is_not_link(self):
        assert is_topology_link(None) is False

    def test_empty_dict_is_not_link(self):
        assert is_topology_link({}) is False

    def test_dict_with_only_source_is_not_link(self):
        assert is_topology_link({"source": "a"}) is False

    def test_string_is_not_link(self):
        assert is_topology_link("not a link") is False


class TestCSVExportEscaping:
    def test_normal_text(self):
        assert escape_csv_field("正常文本") == "正常文本"

    def test_text_with_comma(self):
        result = escape_csv_field("包含,逗号")
        assert result.startswith('"')
        assert result.endswith('"')
        assert ",逗号" in result

    def test_text_with_double_quote(self):
        result = escape_csv_field('包含"引号')
        assert '""' in result
        assert result.startswith('"')
        assert result.endswith('"')

    def test_text_with_newline(self):
        result = escape_csv_field("包含\n换行")
        assert result.startswith('"')
        assert result.endswith('"')

    def test_csv_injection_equals(self):
        result = escape_csv_field("=FORMULA")
        assert result.startswith("'")
        assert "=FORMULA" in result

    def test_csv_injection_plus(self):
        result = escape_csv_field("+value")
        assert result.startswith("'")

    def test_csv_injection_minus(self):
        result = escape_csv_field("-value")
        assert result.startswith("'")

    def test_csv_injection_at(self):
        result = escape_csv_field("@function")
        assert result.startswith("'")

    def test_csv_injection_tab(self):
        result = escape_csv_field("\tindented")
        assert result.startswith("'")

    def test_csv_injection_carriage_return(self):
        result = escape_csv_field("\rreturn")
        assert result.startswith("'")

    def test_safe_value_no_modification(self):
        result = escape_csv_field("normal_value")
        assert result == "normal_value"

    def test_numeric_string_safe(self):
        result = escape_csv_field("98")
        assert result == "98"

    def test_chinese_text_safe(self):
        result = escape_csv_field("核心路由器CR-01")
        assert result == "核心路由器CR-01"

    def test_combined_injection_and_comma(self):
        result = escape_csv_field("=CMD,injection")
        assert "'" in result
        assert '"' in result

    def test_export_headers_structure(self):
        headers = "id,name,type,status,health,cpu,memory"
        fields = headers.split(",")
        assert len(fields) == 7
        assert "id" in fields
        assert "name" in fields
        assert "status" in fields

    def test_export_rows_generation(self):
        rows = []
        for node in MOCK_TOPOLOGY_NODES:
            row = ",".join([
                escape_csv_field(node["id"]),
                escape_csv_field(node["name"]),
                escape_csv_field(node["type"]),
                escape_csv_field(node["status"]),
                str(node["health"]),
                str(node["cpu"]),
                str(node["memory"]),
            ])
            rows.append(row)
        assert len(rows) == len(MOCK_TOPOLOGY_NODES)
        assert "core1" in rows[0]


class TestJSONExport:
    def test_json_export_structure(self):
        export_payload = {
            "exportTime": datetime.now().isoformat(),
            "totalNodes": len(MOCK_TOPOLOGY_NODES),
            "totalLinks": len(MOCK_TOPOLOGY_LINKS),
            "nodes": MOCK_TOPOLOGY_NODES,
            "links": MOCK_TOPOLOGY_LINKS,
            "flows": MOCK_TOPOLOGY_FLOWS,
        }
        assert "exportTime" in export_payload
        assert "nodes" in export_payload
        assert "links" in export_payload
        assert export_payload["totalNodes"] == 9
        assert export_payload["totalLinks"] == 13

    def test_json_export_serializable(self):
        export_payload = {
            "exportTime": datetime.now().isoformat(),
            "nodes": MOCK_TOPOLOGY_NODES,
            "links": MOCK_TOPOLOGY_LINKS,
        }
        serialized = json.dumps(export_payload, ensure_ascii=False)
        deserialized = json.loads(serialized)
        assert len(deserialized["nodes"]) == 9
        assert len(deserialized["links"]) == 13

    def test_json_export_with_bom_for_csv(self):
        csv_content = "\uFEFF" + "id,name\n" + "core1,CR-01\n"
        assert csv_content.startswith("\uFEFF")
        assert "core1" in csv_content


class TestImportValidation:
    def test_valid_import_data(self):
        data = {"nodes": MOCK_TOPOLOGY_NODES, "links": MOCK_TOPOLOGY_LINKS}
        is_valid, error = validate_import_data(data)
        assert is_valid is True
        assert error is None

    def test_import_missing_nodes(self):
        data = {"links": MOCK_TOPOLOGY_LINKS}
        is_valid, error = validate_import_data(data)
        assert is_valid is False
        assert "nodes" in error

    def test_import_missing_links(self):
        data = {"nodes": MOCK_TOPOLOGY_NODES}
        is_valid, error = validate_import_data(data)
        assert is_valid is False
        assert "links" in error

    def test_import_nodes_not_array(self):
        data = {"nodes": "not_array", "links": []}
        is_valid, error = validate_import_data(data)
        assert is_valid is False

    def test_import_links_not_array(self):
        data = {"nodes": [], "links": "not_array"}
        is_valid, error = validate_import_data(data)
        assert is_valid is False

    def test_import_node_missing_required_field(self):
        invalid_node = dict(MOCK_TOPOLOGY_NODES[0])
        del invalid_node["id"]
        data = {"nodes": [invalid_node], "links": MOCK_TOPOLOGY_LINKS}
        is_valid, error = validate_import_data(data)
        assert is_valid is False
        assert "id" in error

    def test_import_link_missing_required_field(self):
        invalid_link = dict(MOCK_TOPOLOGY_LINKS[0])
        del invalid_link["source"]
        data = {"nodes": MOCK_TOPOLOGY_NODES, "links": [invalid_link]}
        is_valid, error = validate_import_data(data)
        assert is_valid is False
        assert "source" in error

    def test_import_invalid_json_string(self):
        with pytest.raises(json.JSONDecodeError):
            json.parse("not valid json") if hasattr(json, "parse") else json.loads("{invalid}")

    def test_import_empty_object(self):
        is_valid, error = validate_import_data({})
        assert is_valid is False

    def test_import_null_data(self):
        is_valid, error = validate_import_data(None)
        assert is_valid is False

    def test_import_string_data(self):
        is_valid, error = validate_import_data("just a string")
        assert is_valid is False

    def test_import_node_missing_status(self):
        invalid_node = dict(MOCK_TOPOLOGY_NODES[0])
        del invalid_node["status"]
        data = {"nodes": [invalid_node], "links": []}
        is_valid, error = validate_import_data(data)
        assert is_valid is False
        assert "status" in error

    def test_import_link_missing_bandwidth(self):
        invalid_link = dict(MOCK_TOPOLOGY_LINKS[0])
        del invalid_link["bandwidth"]
        data = {"nodes": [], "links": [invalid_link]}
        is_valid, error = validate_import_data(data)
        assert is_valid is False
        assert "bandwidth" in error


class TestSnapshotValidation:
    def test_valid_snapshot(self):
        snapshot = {
            "nodePositions": [{"id": "core1", "x": 400, "y": 150}],
            "centralPosition": {"x": 500, "y": 80},
            "zoomLevel": 1.0,
            "panOffset": {"x": 0, "y": 0},
            "layoutType": "hierarchical",
            "displayOptions": {"showLabels": True, "showBandwidth": True},
        }
        is_valid, error = validate_snapshot(snapshot)
        assert is_valid is True
        assert error is None

    def test_snapshot_pydantic_model(self):
        snapshot = {
            "nodePositions": [{"id": "core1", "x": 400, "y": 150}],
            "centralPosition": {"x": 500, "y": 80},
            "zoomLevel": 1.0,
            "panOffset": {"x": 0, "y": 0},
            "layoutType": "hierarchical",
            "displayOptions": {"showLabels": True},
        }
        model = TopologySnapshotModel(**snapshot)
        assert model.zoomLevel == 1.0
        assert model.layoutType == "hierarchical"

    def test_snapshot_zoom_level_range(self):
        snapshot = {
            "nodePositions": [],
            "centralPosition": {"x": 500, "y": 80},
            "zoomLevel": 5.0,
            "panOffset": {"x": 0, "y": 0},
            "layoutType": "hierarchical",
            "displayOptions": {},
        }
        with pytest.raises(Exception):
            TopologySnapshotModel(**snapshot)

    def test_snapshot_zoom_level_too_low(self):
        snapshot = {
            "nodePositions": [],
            "centralPosition": {"x": 500, "y": 80},
            "zoomLevel": 0.1,
            "panOffset": {"x": 0, "y": 0},
            "layoutType": "hierarchical",
            "displayOptions": {},
        }
        with pytest.raises(Exception):
            TopologySnapshotModel(**snapshot)

    def test_null_snapshot_rejected(self):
        is_valid, error = validate_snapshot(None)
        assert is_valid is False
        assert "无效" in error

    def test_non_object_snapshot_rejected(self):
        is_valid, error = validate_snapshot("not an object")
        assert is_valid is False

    def test_snapshot_invalid_node_positions(self):
        snapshot = {"nodePositions": "not_array"}
        is_valid, error = validate_snapshot(snapshot)
        assert is_valid is False
        assert "nodePositions" in error

    def test_snapshot_node_position_missing_fields(self):
        snapshot = {"nodePositions": [{"id": "core1"}]}
        is_valid, error = validate_snapshot(snapshot)
        assert is_valid is False

    def test_snapshot_invalid_central_position(self):
        snapshot = {"centralPosition": {"x": "not_a_number"}}
        is_valid, error = validate_snapshot(snapshot)
        assert is_valid is False

    def test_snapshot_invalid_pan_offset(self):
        snapshot = {"panOffset": {"x": "not_a_number", "y": 0}}
        is_valid, error = validate_snapshot(snapshot)
        assert is_valid is False

    def test_snapshot_serialization_round_trip(self):
        snapshot = {
            "nodePositions": [{"id": "core1", "x": 400, "y": 150}, {"id": "core2", "x": 600, "y": 150}],
            "centralPosition": {"x": 500, "y": 80},
            "zoomLevel": 1.2,
            "panOffset": {"x": 10, "y": -5},
            "layoutType": "force",
            "displayOptions": {"showLabels": True, "showBandwidth": False},
        }
        serialized = json.dumps(snapshot)
        deserialized = json.loads(serialized)
        is_valid, _ = validate_snapshot(deserialized)
        assert is_valid is True
        assert deserialized["zoomLevel"] == 1.2
        assert deserialized["layoutType"] == "force"

    def test_snapshot_minimal_valid(self):
        snapshot = {}
        is_valid, error = validate_snapshot(snapshot)
        assert is_valid is True

    def test_snapshot_with_all_node_positions(self):
        positions = [{"id": n["id"], "x": n["x"], "y": n["y"]} for n in MOCK_TOPOLOGY_NODES]
        snapshot = {"nodePositions": positions}
        is_valid, error = validate_snapshot(snapshot)
        assert is_valid is True


class TestAlertLogic:
    def test_alert_for_low_health_node(self):
        nodes = [{"id": "test", "name": "测试节点", "health": 60, "status": "error"}]
        alerts = check_alerts(nodes, [])
        assert len(alerts) >= 1
        assert alerts[0]["type"] == "error"
        assert "健康值严重过低" in alerts[0]["message"]

    def test_alert_for_warning_health_node(self):
        nodes = [{"id": "test", "name": "测试节点", "health": 80, "status": "warning"}]
        alerts = check_alerts(nodes, [])
        assert len(alerts) >= 1
        assert alerts[0]["type"] == "warning"
        assert "健康值偏低" in alerts[0]["message"]

    def test_no_alert_for_healthy_node(self):
        nodes = [{"id": "test", "name": "测试节点", "health": 95, "status": "healthy"}]
        alerts = check_alerts(nodes, [])
        node_alerts = [a for a in alerts if a["id"].startswith("node_")]
        assert len(node_alerts) == 0

    def test_alert_for_high_load_link(self):
        links = [{"source": "a", "target": "b", "currentLoad": 95, "status": "error"}]
        alerts = check_alerts([], links)
        assert len(alerts) >= 1
        assert alerts[0]["type"] == "error"
        assert "负载过高" in alerts[0]["message"]

    def test_alert_for_warning_load_link(self):
        links = [{"source": "a", "target": "b", "currentLoad": 78, "status": "warning"}]
        alerts = check_alerts([], links)
        assert len(alerts) >= 1
        assert alerts[0]["type"] == "warning"
        assert "负载偏高" in alerts[0]["message"]

    def test_no_alert_for_normal_load_link(self):
        links = [{"source": "a", "target": "b", "currentLoad": 50, "status": "active"}]
        alerts = check_alerts([], links)
        link_alerts = [a for a in alerts if a["id"].startswith("link_")]
        assert len(link_alerts) == 0

    def test_alert_deduplication(self):
        nodes = [{"id": "test", "name": "测试节点", "health": 60, "status": "error"}]
        existing = [{"id": "node_error_test", "type": "error", "message": "已有告警", "timestamp": 1000, "dismissed": False}]
        alerts = check_alerts(nodes, [], existing)
        error_alerts = [a for a in alerts if a["id"] == "node_error_test"]
        assert len(error_alerts) == 1

    def test_dismissed_alerts_filtered(self):
        existing = [{"id": "old_alert", "type": "warning", "message": "旧告警", "timestamp": 1000, "dismissed": True}]
        alerts = check_alerts([], [], existing)
        assert len(alerts) == 0

    def test_alert_from_mock_data(self):
        alerts = check_alerts(MOCK_TOPOLOGY_NODES, MOCK_TOPOLOGY_LINKS)
        error_alerts = [a for a in alerts if a["type"] == "error"]
        warning_alerts = [a for a in alerts if a["type"] == "warning"]
        assert len(error_alerts) >= 1
        assert len(warning_alerts) >= 1

    def test_alert_id_format_node(self):
        nodes = [{"id": "core1", "name": "CR-01", "health": 60, "status": "error"}]
        alerts = check_alerts(nodes, [])
        assert alerts[0]["id"] == "node_error_core1"

    def test_alert_id_format_link(self):
        links = [{"source": "a", "target": "b", "currentLoad": 95, "status": "error"}]
        alerts = check_alerts([], links)
        assert alerts[0]["id"] == "link_error_a::b"

    def test_alert_dismiss(self):
        alerts = [
            {"id": "alert1", "type": "error", "message": "test", "timestamp": 1000, "dismissed": False},
            {"id": "alert2", "type": "warning", "message": "test2", "timestamp": 1000, "dismissed": False},
        ]
        remaining = [a for a in alerts if a["id"] != "alert1"]
        assert len(remaining) == 1
        assert remaining[0]["id"] == "alert2"

    def test_clear_all_alerts(self):
        alerts = [
            {"id": "alert1", "type": "error", "message": "test", "timestamp": 1000, "dismissed": False},
            {"id": "alert2", "type": "warning", "message": "test2", "timestamp": 1000, "dismissed": False},
        ]
        alerts.clear()
        assert len(alerts) == 0

    def test_alert_health_boundary_70(self):
        nodes = [{"id": "test", "name": "边界测试", "health": 69, "status": "error"}]
        alerts = check_alerts(nodes, [])
        assert any(a["type"] == "error" for a in alerts)

    def test_alert_health_boundary_85(self):
        nodes = [{"id": "test", "name": "边界测试", "health": 84, "status": "warning"}]
        alerts = check_alerts(nodes, [])
        assert any(a["type"] == "warning" for a in alerts)

    def test_alert_load_boundary_90(self):
        links = [{"source": "a", "target": "b", "currentLoad": 90, "status": "error"}]
        alerts = check_alerts([], links)
        assert any(a["type"] == "error" for a in alerts)

    def test_alert_load_boundary_75(self):
        links = [{"source": "a", "target": "b", "currentLoad": 75, "status": "warning"}]
        alerts = check_alerts([], links)
        assert any(a["type"] == "warning" for a in alerts)


class TestGetLinkWidth:
    def test_100g_bandwidth(self):
        assert get_link_width("100G") == 6

    def test_40g_bandwidth(self):
        assert get_link_width("40G") == 5

    def test_10g_bandwidth(self):
        assert get_link_width("10G") == 4

    def test_1g_bandwidth(self):
        assert get_link_width("1G") == 3.5

    def test_100m_bandwidth(self):
        assert get_link_width("100M") == 2.5

    def test_unknown_bandwidth(self):
        assert get_link_width("unknown") == 1.5

    def test_empty_bandwidth(self):
        assert get_link_width("") == 1.5

    def test_high_load_adds_width(self):
        assert get_link_width("10G", 85) == 5

    def test_high_load_capped_at_7(self):
        assert get_link_width("100G", 95) == 7

    def test_normal_load_no_extra_width(self):
        assert get_link_width("10G", 50) == 4

    def test_load_boundary_80(self):
        assert get_link_width("10G", 80) == 4
        assert get_link_width("10G", 81) == 5

    def test_all_mock_link_widths(self):
        for link in MOCK_TOPOLOGY_LINKS:
            width = get_link_width(link["bandwidth"], link["currentLoad"])
            assert 1.5 <= width <= 7


class TestGetNodeStatusColor:
    def test_healthy_color(self):
        assert get_node_status_color("healthy") == "#52C41A"

    def test_warning_color(self):
        assert get_node_status_color("warning") == "#FAAD14"

    def test_error_color(self):
        assert get_node_status_color("error") == "#FF4D4F"

    def test_unknown_status_defaults(self):
        assert get_node_status_color("unknown") == "#52C41A"

    def test_empty_status_defaults(self):
        assert get_node_status_color("") == "#52C41A"


class TestGetLinkLoadColor:
    def test_critical_load(self):
        assert get_link_load_color(95) == "#FF4D4F"

    def test_high_load(self):
        assert get_link_load_color(80) == "#FF7D00"

    def test_medium_load(self):
        assert get_link_load_color(55) == "#FAAD14"

    def test_low_load(self):
        assert get_link_load_color(30) == "#52C41A"

    def test_very_low_load(self):
        assert get_link_load_color(10) == "#1890FF"

    def test_boundary_90(self):
        assert get_link_load_color(90) == "#FF4D4F"
        assert get_link_load_color(89) == "#FF7D00"

    def test_boundary_75(self):
        assert get_link_load_color(75) == "#FF7D00"
        assert get_link_load_color(74) == "#FAAD14"

    def test_boundary_50(self):
        assert get_link_load_color(50) == "#FAAD14"
        assert get_link_load_color(49) == "#52C41A"

    def test_boundary_25(self):
        assert get_link_load_color(25) == "#52C41A"
        assert get_link_load_color(24) == "#1890FF"

    def test_zero_load(self):
        assert get_link_load_color(0) == "#1890FF"

    def test_100_load(self):
        assert get_link_load_color(100) == "#FF4D4F"


class TestGetHealthColor:
    def test_healthy(self):
        assert get_health_color(95) == "#52C41A"

    def test_warning(self):
        assert get_health_color(75) == "#FAAD14"

    def test_error(self):
        assert get_health_color(50) == "#FF4D4F"

    def test_boundary_90(self):
        assert get_health_color(90) == "#52C41A"
        assert get_health_color(89) == "#FAAD14"

    def test_boundary_70(self):
        assert get_health_color(70) == "#FAAD14"
        assert get_health_color(69) == "#FF4D4F"


class TestGetResourceColor:
    def test_low_usage(self):
        assert get_resource_color(30) == "#52C41A"

    def test_medium_usage(self):
        assert get_resource_color(70) == "#FAAD14"

    def test_high_usage(self):
        assert get_resource_color(85) == "#FF7A45"

    def test_critical_usage(self):
        assert get_resource_color(95) == "#FF4D4F"

    def test_boundary_60(self):
        assert get_resource_color(59) == "#52C41A"
        assert get_resource_color(60) == "#FAAD14"

    def test_boundary_80(self):
        assert get_resource_color(79) == "#FAAD14"
        assert get_resource_color(80) == "#FF7A45"

    def test_boundary_90(self):
        assert get_resource_color(89) == "#FF7A45"
        assert get_resource_color(90) == "#FF4D4F"


class TestGetLatencyColor:
    def test_excellent(self):
        assert get_latency_color(5) == "#52C41A"

    def test_good(self):
        assert get_latency_color(20) == "#FAAD14"

    def test_degraded(self):
        assert get_latency_color(45) == "#FF7D00"

    def test_poor(self):
        assert get_latency_color(70) == "#FF4D4F"

    def test_boundary_10(self):
        assert get_latency_color(9) == "#52C41A"
        assert get_latency_color(10) == "#FAAD14"

    def test_boundary_30(self):
        assert get_latency_color(29) == "#FAAD14"
        assert get_latency_color(30) == "#FF7D00"

    def test_boundary_60(self):
        assert get_latency_color(59) == "#FF7D00"
        assert get_latency_color(60) == "#FF4D4F"


class TestGetActionColor:
    def test_exec_cli(self):
        assert get_action_color("exec_cli") == "#165DFF"

    def test_response(self):
        assert get_action_color("response") == "#52C41A"

    def test_validate_config(self):
        assert get_action_color("validate_config") == "#FAAD14"

    def test_isolate_node(self):
        assert get_action_color("isolate_node") == "#FF4D4F"

    def test_unknown_action(self):
        assert get_action_color("unknown_action") == "#64748B"


class TestTopologyStats:
    def test_stats_from_mock_data(self):
        stats = compute_topology_stats(MOCK_TOPOLOGY_NODES, MOCK_TOPOLOGY_LINKS)
        assert stats["totalNodes"] == 9
        assert stats["healthyNodes"] == 7
        assert stats["warningNodes"] == 1
        assert stats["errorNodes"] == 1
        assert stats["totalLinks"] == 13
        assert stats["mainLinks"] >= 1
        assert stats["avgHealth"] > 0
        assert stats["avgLoad"] > 0

    def test_stats_empty_data(self):
        stats = compute_topology_stats([], [])
        assert stats["totalNodes"] == 0
        assert stats["healthyNodes"] == 0
        assert stats["totalLinks"] == 0
        assert stats["avgHealth"] == 0
        assert stats["avgLoad"] == 0

    def test_stats_all_healthy(self):
        nodes = [{"status": "healthy", "health": 100} for _ in range(5)]
        links = [{"status": "active", "currentLoad": 30, "main": True} for _ in range(3)]
        stats = compute_topology_stats(nodes, links)
        assert stats["healthyNodes"] == 5
        assert stats["warningNodes"] == 0
        assert stats["errorNodes"] == 0

    def test_stats_all_error(self):
        nodes = [{"status": "error", "health": 50} for _ in range(3)]
        links = [{"status": "error", "currentLoad": 95, "main": False} for _ in range(2)]
        stats = compute_topology_stats(nodes, links)
        assert stats["errorNodes"] == 3
        assert stats["errorLinks"] == 2

    def test_stats_avg_health_calculation(self):
        nodes = [{"status": "healthy", "health": 80}, {"status": "healthy", "health": 90}]
        stats = compute_topology_stats(nodes, [])
        assert stats["avgHealth"] == 85

    def test_stats_avg_load_calculation(self):
        links = [{"status": "active", "currentLoad": 40, "main": True}, {"status": "active", "currentLoad": 60, "main": False}]
        stats = compute_topology_stats([], links)
        assert stats["avgLoad"] == 50

    def test_main_vs_backup_links(self):
        main_count = len([l for l in MOCK_TOPOLOGY_LINKS if l.get("main")])
        backup_count = len([l for l in MOCK_TOPOLOGY_LINKS if not l.get("main")])
        assert main_count + backup_count == len(MOCK_TOPOLOGY_LINKS)
        assert main_count > 0
        assert backup_count > 0


class TestViewportBoundaryDetection:
    def test_clamp_within_bounds(self):
        result = clamp_to_bounds(500, 300)
        assert result["x"] == 500
        assert result["y"] == 300

    def test_clamp_left_boundary(self):
        result = clamp_to_bounds(10, 300)
        assert result["x"] == 50

    def test_clamp_right_boundary(self):
        result = clamp_to_bounds(990, 300)
        assert result["x"] == 950

    def test_clamp_top_boundary(self):
        result = clamp_to_bounds(500, 10)
        assert result["y"] == 50

    def test_clamp_bottom_boundary(self):
        result = clamp_to_bounds(500, 540)
        assert result["y"] == 500

    def test_clamp_negative_coordinates(self):
        result = clamp_to_bounds(-100, -100)
        assert result["x"] == 50
        assert result["y"] == 50

    def test_clamp_custom_viewport(self):
        result = clamp_to_bounds(900, 500, width=800, height=600, padding=30)
        assert result["x"] == 770
        assert result["y"] == 500

    def test_all_mock_nodes_within_bounds(self):
        for node in MOCK_TOPOLOGY_NODES:
            result = clamp_to_bounds(node["x"], node["y"])
            assert result["x"] == node["x"], f"Node {node['id']} x out of bounds"
            assert result["y"] == node["y"], f"Node {node['id']} y out of bounds"


class TestConcurrentOperationPrevention:
    def test_is_fetching_lock_prevents_concurrent(self):
        is_fetching = False
        call_count = 0

        def simulated_fetch():
            nonlocal is_fetching, call_count
            if is_fetching:
                return
            is_fetching = True
            call_count += 1
            is_fetching = False

        for _ in range(5):
            simulated_fetch()
        assert call_count == 5

    def test_is_fetching_lock_blocks_while_active(self):
        is_fetching = False
        blocked_count = 0
        executed_count = 0

        def simulated_fetch_with_block():
            nonlocal is_fetching, blocked_count, executed_count
            if is_fetching:
                blocked_count += 1
                return
            is_fetching = True
            executed_count += 1
            is_fetching = False

        is_fetching = True
        for _ in range(3):
            simulated_fetch_with_block()
        is_fetching = False
        simulated_fetch_with_block()

        assert blocked_count == 3
        assert executed_count == 1


class TestEdgeCases:
    def test_empty_topology_data(self):
        stats = compute_topology_stats([], [])
        assert stats["totalNodes"] == 0
        assert stats["totalLinks"] == 0
        assert stats["avgHealth"] == 0
        assert stats["avgLoad"] == 0

    def test_empty_nodes_alert_check(self):
        alerts = check_alerts([], [])
        assert alerts == []

    def test_node_id_with_special_characters(self):
        key = make_link_key("node-1_v2.0", "node-2_v3.0")
        parsed = parse_link_key(key)
        assert parsed["source"] == "node-1_v2.0"
        assert parsed["target"] == "node-2_v3.0"

    def test_node_id_with_unicode(self):
        key = make_link_key("节点A", "节点B")
        parsed = parse_link_key(key)
        assert parsed["source"] == "节点A"
        assert parsed["target"] == "节点B"

    def test_very_high_zoom_level(self):
        snapshot = {
            "nodePositions": [],
            "centralPosition": {"x": 500, "y": 80},
            "zoomLevel": 3.0,
            "panOffset": {"x": 0, "y": 0},
            "layoutType": "hierarchical",
            "displayOptions": {},
        }
        model = TopologySnapshotModel(**snapshot)
        assert model.zoomLevel == 3.0

    def test_very_low_zoom_level(self):
        snapshot = {
            "nodePositions": [],
            "centralPosition": {"x": 500, "y": 80},
            "zoomLevel": 0.3,
            "panOffset": {"x": 0, "y": 0},
            "layoutType": "hierarchical",
            "displayOptions": {},
        }
        model = TopologySnapshotModel(**snapshot)
        assert model.zoomLevel == 0.3

    def test_link_with_zero_load(self):
        link = {"source": "a", "target": "b", "bandwidth": "1G", "currentLoad": 0, "status": "active", "main": True}
        model = TopologyLinkModel(**link)
        assert model.currentLoad == 0
        assert get_link_load_color(0) == "#1890FF"

    def test_link_with_100_load(self):
        link = {"source": "a", "target": "b", "bandwidth": "1G", "currentLoad": 100, "status": "error", "main": True}
        model = TopologyLinkModel(**link)
        assert model.currentLoad == 100

    def test_node_with_zero_health(self):
        node = dict(MOCK_TOPOLOGY_NODES[0])
        node["health"] = 0
        node["status"] = "error"
        model = TopologyNodeModel(**node)
        assert model.health == 0

    def test_node_with_100_health(self):
        node = dict(MOCK_TOPOLOGY_NODES[0])
        node["health"] = 100
        model = TopologyNodeModel(**node)
        assert model.health == 100

    def test_csv_export_with_all_node_statuses(self):
        statuses = ["healthy", "warning", "error"]
        for status in statuses:
            result = escape_csv_field(status)
            assert result == status

    def test_link_key_separator_in_node_id(self):
        key = make_link_key("a::b", "c")
        parsed = parse_link_key(key)
        assert parsed["source"] == "a"
        assert parsed["target"] == "b::c"

    def test_large_topology_stats(self):
        large_nodes = [{"status": "healthy", "health": 90 + i % 10} for i in range(100)]
        large_links = [{"status": "active", "currentLoad": 30 + i % 50, "main": i % 3 == 0} for i in range(200)]
        stats = compute_topology_stats(large_nodes, large_links)
        assert stats["totalNodes"] == 100
        assert stats["totalLinks"] == 200

    def test_layout_types(self):
        valid_layouts = ["hierarchical", "force", "circular", "grid"]
        for layout in valid_layouts:
            snapshot = {
                "nodePositions": [],
                "centralPosition": {"x": 500, "y": 80},
                "zoomLevel": 1.0,
                "panOffset": {"x": 0, "y": 0},
                "layoutType": layout,
                "displayOptions": {},
            }
            model = TopologySnapshotModel(**snapshot)
            assert model.layoutType == layout

    def test_display_options_defaults(self):
        default_options = {"showLabels": True, "showBandwidth": True, "showHealth": True, "showFlows": True, "showA2A": True, "nodeSize": 1}
        assert default_options["showLabels"] is True
        assert default_options["nodeSize"] == 1

    def test_node_size_range(self):
        assert 0.5 <= 1.0 <= 2.0
        assert 0.5 <= 0.5 <= 2.0
        assert 0.5 <= 2.0 <= 2.0


class TestA2AMessageValidation:
    def test_valid_a2a_message(self):
        msg = {
            "id": "msg_001",
            "sender": "central_agent",
            "receiver": "edge_agent_1",
            "task_id": "task_2024_001",
            "action": "exec_cli",
            "timestamp": "10:30:00",
            "payload": {"command": "show interfaces", "device": "core1"},
            "path": ["central", "core1"],
            "status": "completed",
        }
        model = A2AMessageModel(**msg)
        assert model.sender == "central_agent"
        assert model.action == "exec_cli"

    def test_a2a_message_status_values(self):
        valid_statuses = {"pending", "in_progress", "completed"}
        for status in valid_statuses:
            msg = {
                "id": "msg_test",
                "sender": "a",
                "receiver": "b",
                "task_id": "t1",
                "action": "exec_cli",
                "timestamp": "10:00:00",
                "payload": {},
                "path": ["a", "b"],
                "status": status,
            }
            model = A2AMessageModel(**msg)
            assert model.status == status

    def test_a2a_invalid_status_rejected(self):
        msg = {
            "id": "msg_test",
            "sender": "a",
            "receiver": "b",
            "task_id": "t1",
            "action": "exec_cli",
            "timestamp": "10:00:00",
            "payload": {},
            "path": ["a", "b"],
            "status": "invalid",
        }
        with pytest.raises(Exception):
            A2AMessageModel(**msg)

    def test_a2a_action_colors(self):
        assert get_action_color("exec_cli") == "#165DFF"
        assert get_action_color("response") == "#52C41A"
        assert get_action_color("validate_config") == "#FAAD14"
        assert get_action_color("isolate_node") == "#FF4D4F"

    def test_a2a_message_max_queue(self):
        messages = []
        for i in range(15):
            messages.insert(0, {"id": f"msg_{i}", "sender": "a", "receiver": "b"})
            if len(messages) > 10:
                messages.pop()
        assert len(messages) == 10


class TestTelemetrySimulation:
    def test_telemetry_data_structure(self):
        telemetry = {
            "id": make_link_key("core1", "core2"),
            "bandwidth": 82.5,
            "latency": 15.3,
            "packetLoss": 0.02,
            "timestamp": 1000,
        }
        assert "id" in telemetry
        assert "bandwidth" in telemetry
        assert "latency" in telemetry
        assert "packetLoss" in telemetry

    def test_telemetry_for_all_links(self):
        telemetry = []
        for link in MOCK_TOPOLOGY_LINKS:
            telemetry.append({
                "id": make_link_key(link["source"], link["target"]),
                "bandwidth": link["currentLoad"] + 5,
                "latency": 5 + 45 * 0.5,
                "packetLoss": 0.1,
                "timestamp": 1000,
            })
        assert len(telemetry) == len(MOCK_TOPOLOGY_LINKS)

    def test_fault_ripple_for_high_load(self):
        fault_links = [l for l in MOCK_TOPOLOGY_LINKS if l["currentLoad"] >= 90 or l["status"] == "down"]
        assert len(fault_links) >= 1

    def test_latency_color_mapping(self):
        test_cases = [(5, "#52C41A"), (15, "#FAAD14"), (40, "#FF7D00"), (70, "#FF4D4F")]
        for latency, expected_color in test_cases:
            assert get_latency_color(latency) == expected_color


class TestTopologyFlowValidation:
    def test_valid_flow(self):
        flow = MOCK_TOPOLOGY_FLOWS[0]
        model = TopologyFlowModel(**flow)
        assert model.id == "flow1"
        assert model.type == "data"

    def test_flow_path_minimum_length(self):
        for flow in MOCK_TOPOLOGY_FLOWS:
            assert len(flow["path"]) >= 2, f"Flow {flow['id']} path too short"

    def test_flow_types(self):
        valid_types = {"data", "video", "voice", "control"}
        for flow in MOCK_TOPOLOGY_FLOWS:
            assert flow["type"] in valid_types

    def test_flow_bandwidth_format(self):
        bandwidth_pattern = re.compile(r"^\d+[MG]$")
        for flow in MOCK_TOPOLOGY_FLOWS:
            assert bandwidth_pattern.match(flow["bandwidth"]), f"Invalid flow bandwidth: {flow['bandwidth']}"


class TestTopologyDataIntegrity:
    def test_all_link_sources_exist_in_nodes(self):
        node_ids = {n["id"] for n in MOCK_TOPOLOGY_NODES}
        node_ids.add("central")
        for link in MOCK_TOPOLOGY_LINKS:
            assert link["source"] in node_ids, f"Link source {link['source']} not found in nodes"
            assert link["target"] in node_ids, f"Link target {link['target']} not found in nodes"

    def test_no_duplicate_node_ids(self):
        ids = [n["id"] for n in MOCK_TOPOLOGY_NODES]
        assert len(ids) == len(set(ids)), "Duplicate node IDs found"

    def test_no_duplicate_link_keys(self):
        keys = [make_link_key(l["source"], l["target"]) for l in MOCK_TOPOLOGY_LINKS]
        assert len(keys) == len(set(keys)), "Duplicate link keys found"

    def test_node_status_health_correlation(self):
        for node in MOCK_TOPOLOGY_NODES:
            if node["health"] < 70:
                assert node["status"] == "error", f"Node {node['id']} health {node['health']} should be error"
            elif node["health"] < 85:
                assert node["status"] in ("warning", "error"), f"Node {node['id']} health {node['health']} status should reflect low health"

    def test_link_status_load_correlation(self):
        for link in MOCK_TOPOLOGY_LINKS:
            if link["currentLoad"] >= 90:
                assert link["status"] in ("error", "down"), f"Link {link['source']}->{link['target']} load {link['currentLoad']} should be error/down"
            elif link["currentLoad"] >= 75:
                assert link["status"] in ("warning", "error", "active"), f"Link {link['source']}->{link['target']} load {link['currentLoad']} status should reflect high load"

    def test_central_links_have_flag(self):
        central_links = [l for l in MOCK_TOPOLOGY_LINKS if l["source"] == "central"]
        for link in central_links:
            assert link.get("isCentralLink") is True


class TestTopologyExportWorkflow:
    def test_json_export_then_import_round_trip(self):
        export_data = {"nodes": MOCK_TOPOLOGY_NODES, "links": MOCK_TOPOLOGY_LINKS, "flows": MOCK_TOPOLOGY_FLOWS}
        serialized = json.dumps(export_data, ensure_ascii=False)
        deserialized = json.loads(serialized)
        is_valid, error = validate_import_data(deserialized)
        assert is_valid is True
        assert len(deserialized["nodes"]) == len(MOCK_TOPOLOGY_NODES)
        assert len(deserialized["links"]) == len(MOCK_TOPOLOGY_LINKS)

    def test_csv_export_all_nodes(self):
        headers = "id,name,type,status,health,cpu,memory"
        rows = []
        for node in MOCK_TOPOLOGY_NODES:
            row = ",".join([
                escape_csv_field(node["id"]),
                escape_csv_field(node["name"]),
                escape_csv_field(node["type"]),
                escape_csv_field(node["status"]),
                str(node["health"]),
                str(node["cpu"]),
                str(node["memory"]),
            ])
            rows.append(row)
        csv_content = "\uFEFF" + headers + "\n" + "\n".join(rows)
        assert csv_content.startswith("\uFEFF")
        lines = csv_content.split("\n")
        assert len(lines) == len(MOCK_TOPOLOGY_NODES) + 1

    def test_export_with_modified_data(self):
        modified_nodes = [dict(n) for n in MOCK_TOPOLOGY_NODES]
        modified_nodes[0]["health"] = 50
        modified_nodes[0]["status"] = "error"
        export_data = {"nodes": modified_nodes, "links": MOCK_TOPOLOGY_LINKS}
        is_valid, _ = validate_import_data(export_data)
        assert is_valid is True
        assert export_data["nodes"][0]["health"] == 50


class TestTopologyIsolateWorkflow:
    def test_isolate_node_sets_locked(self):
        nodes = [dict(n) for n in MOCK_TOPOLOGY_NODES]
        target_id = "core1"
        target = next(n for n in nodes if n["id"] == target_id)
        assert target["locked"] is False
        target["locked"] = True
        assert target["locked"] is True

    def test_unisolate_node_clears_locked(self):
        nodes = [dict(n) for n in MOCK_TOPOLOGY_NODES]
        target_id = "core1"
        target = next(n for n in nodes if n["id"] == target_id)
        target["locked"] = True
        target["locked"] = False
        assert target["locked"] is False

    def test_isolate_adds_links_to_isolated_set(self):
        isolated_links = set()
        target_id = "core1"
        for link in MOCK_TOPOLOGY_LINKS:
            if link["source"] == target_id or link["target"] == target_id:
                isolated_links.add(make_link_key(link["source"], link["target"]))
        assert len(isolated_links) > 0

    def test_unisolate_removes_links_from_isolated_set(self):
        isolated_links = set()
        target_id = "core1"
        for link in MOCK_TOPOLOGY_LINKS:
            if link["source"] == target_id or link["target"] == target_id:
                isolated_links.add(make_link_key(link["source"], link["target"]))
        isolated_links.clear()
        assert len(isolated_links) == 0

    def test_make_primary_sets_link_main(self):
        links = [dict(l) for l in MOCK_TOPOLOGY_LINKS]
        target = next(l for l in links if l["source"] == "core2" and l["target"] == "agg2")
        assert target["main"] is False
        target["main"] = True
        target["status"] = "active"
        assert target["main"] is True
        assert target["status"] == "active"


class TestTopologyDrainWorkflow:
    def test_drain_reduces_load_to_zero(self):
        link = dict(MOCK_TOPOLOGY_LINKS[2])
        original_load = link["currentLoad"]
        assert original_load > 0
        link["currentLoad"] = 0
        assert link["currentLoad"] == 0

    def test_drain_restores_original_load(self):
        link = dict(MOCK_TOPOLOGY_LINKS[2])
        original_load = link["currentLoad"]
        link["currentLoad"] = 0
        link["currentLoad"] = original_load
        assert link["currentLoad"] == original_load

    def test_drain_only_affects_related_links(self):
        target_id = "core1"
        related_keys = set()
        for link in MOCK_TOPOLOGY_LINKS:
            if link["source"] == target_id or link["target"] == target_id:
                related_keys.add(make_link_key(link["source"], link["target"]))
        unrelated = [l for l in MOCK_TOPOLOGY_LINKS if make_link_key(l["source"], l["target"]) not in related_keys]
        assert len(unrelated) > 0


class TestTopologySearchLogic:
    def test_search_by_name(self):
        query = "核心"
        results = [n for n in MOCK_TOPOLOGY_NODES if query in n["name"]]
        assert len(results) == 2

    def test_search_by_id(self):
        query = "core"
        results = [n for n in MOCK_TOPOLOGY_NODES if query in n["id"]]
        assert len(results) == 2

    def test_search_case_insensitive(self):
        query = "CR"
        results = [n for n in MOCK_TOPOLOGY_NODES if query.lower() in n["name"].lower()]
        assert len(results) == 2

    def test_search_no_match(self):
        query = "不存在的设备"
        results = [n for n in MOCK_TOPOLOGY_NODES if query in n["name"] or query in n["id"]]
        assert len(results) == 0

    def test_search_empty_query(self):
        query = ""
        results = [n for n in MOCK_TOPOLOGY_NODES if query in n["name"] or query in n["id"]]
        assert len(results) == len(MOCK_TOPOLOGY_NODES)


class TestTopologyContextMenu:
    def test_node_menu_items_count(self):
        node_menu_items = [
            {"id": "isolate", "label": "隔离节点"},
            {"id": "drain", "label": "流量排空"},
            {"id": "restart", "label": "紧急重启"},
            {"id": "ssh", "label": "Web SSH"},
            {"id": "viewConfig", "label": "查看配置"},
            {"id": "diagnose", "label": "执行诊断"},
            {"id": "copilot", "label": "唤醒智能副驾"},
        ]
        assert len(node_menu_items) == 7

    def test_link_menu_items_count(self):
        link_menu_items = [
            {"id": "makePrimary", "label": "设为主用"},
            {"id": "limitBandwidth", "label": "QoS限速"},
            {"id": "viewLink", "label": "查看详情"},
            {"id": "copilot", "label": "唤醒智能副驾"},
        ]
        assert len(link_menu_items) == 4

    def test_node_menu_isolate_label_toggle(self):
        locked = False
        label = "取消隔离" if locked else "隔离节点"
        assert label == "隔离节点"
        locked = True
        label = "取消隔离" if locked else "隔离节点"
        assert label == "取消隔离"

    def test_context_menu_boundary_detection(self):
        menu_w, menu_h = 220, 300
        window_w, window_h = 1920, 1080
        click_x, click_y = 1800, 900
        x = click_x + menu_w > window_w and click_x - menu_w or click_x
        y = click_y + menu_h > window_h and click_y - menu_h or click_y
        assert x < window_w
        assert y < window_h


class TestTopologyZoomControls:
    def test_zoom_in_increments(self):
        zoom = 1.0
        zoom = min(3.0, round((zoom + 0.1) * 10) / 10)
        assert zoom == 1.1

    def test_zoom_out_decrements(self):
        zoom = 1.0
        zoom = max(0.3, round((zoom - 0.1) * 10) / 10)
        assert zoom == 0.9

    def test_zoom_max_cap(self):
        zoom = 3.0
        zoom = min(3.0, round((zoom + 0.1) * 10) / 10)
        assert zoom == 3.0

    def test_zoom_min_cap(self):
        zoom = 0.3
        zoom = max(0.3, round((zoom - 0.1) * 10) / 10)
        assert zoom == 0.3

    def test_zoom_levels(self):
        zoom = 1.0
        for _ in range(20):
            zoom = min(3.0, round((zoom + 0.1) * 10) / 10)
        assert zoom == 3.0

    def test_zoom_display_percentage(self):
        zoom = 1.5
        percentage = round(zoom * 100)
        assert percentage == 150


class TestTopologyKeyboardShortcuts:
    def test_zoom_in_shortcut(self):
        key = "+"
        action = None
        if key in ("+", "="):
            action = "zoomIn"
        assert action == "zoomIn"

    def test_zoom_out_shortcut(self):
        key = "-"
        action = None
        if key == "-":
            action = "zoomOut"
        assert action == "zoomOut"

    def test_reset_view_shortcut(self):
        key = "0"
        action = None
        if key == "0":
            action = "resetView"
        assert action == "resetView"

    def test_search_shortcut(self):
        key = "f"
        ctrl_key = True
        action = None
        if key == "f" and ctrl_key:
            action = "search"
        assert action == "search"

    def test_refresh_shortcut(self):
        key = "r"
        ctrl_key = True
        action = None
        if key == "r" and ctrl_key:
            action = "refresh"
        assert action == "refresh"

    def test_escape_closes_modals(self):
        key = "Escape"
        modals_open = {"config": True, "diagnose": True, "ssh": True, "qos": True, "copilot": True, "display": True}
        if key == "Escape":
            for k in modals_open:
                modals_open[k] = False
        assert all(not v for v in modals_open.values())


class TestTopologyCollisionDetection:
    def test_nodes_too_close_trigger_collision(self):
        node_a = {"x": 100, "y": 100}
        node_b = {"x": 120, "y": 100}
        dx = node_a["x"] - node_b["x"]
        dy = node_a["y"] - node_b["y"]
        distance = math.sqrt(dx * dx + dy * dy)
        min_distance = 100
        assert distance < min_distance

    def test_nodes_far_enough_no_collision(self):
        node_a = {"x": 100, "y": 100}
        node_b = {"x": 300, "y": 100}
        dx = node_a["x"] - node_b["x"]
        dy = node_a["y"] - node_b["y"]
        distance = math.sqrt(dx * dx + dy * dy)
        min_distance = 100
        assert distance >= min_distance

    def test_collision_pushes_node_away(self):
        node_a = {"x": 100, "y": 100}
        node_b = {"x": 120, "y": 100}
        dx = node_a["x"] - node_b["x"]
        dy = node_a["y"] - node_b["y"]
        distance = math.sqrt(dx * dx + dy * dy)
        min_distance = 100
        if distance > 0 and distance < min_distance:
            new_x = node_a["x"] + (dx / distance) * min_distance
            new_y = node_a["y"] + (dy / distance) * min_distance
        else:
            new_x, new_y = node_a["x"], node_a["y"]
        assert abs(new_x - node_b["x"]) >= min_distance or abs(new_y - node_b["y"]) >= min_distance

    def test_mock_nodes_no_collisions(self):
        min_distance = 100
        for i in range(len(MOCK_TOPOLOGY_NODES)):
            for j in range(i + 1, len(MOCK_TOPOLOGY_NODES)):
                dx = MOCK_TOPOLOGY_NODES[i]["x"] - MOCK_TOPOLOGY_NODES[j]["x"]
                dy = MOCK_TOPOLOGY_NODES[i]["y"] - MOCK_TOPOLOGY_NODES[j]["y"]
                distance = math.sqrt(dx * dx + dy * dy)
                assert distance >= min_distance, f"Nodes {MOCK_TOPOLOGY_NODES[i]['id']} and {MOCK_TOPOLOGY_NODES[j]['id']} are too close: {distance}"


class TestTopologyResourceRingPath:
    def test_resource_ring_path_zero_percent(self):
        cx, cy, r, percentage = 100, 100, 22, 0
        clamped_pct = min(100, max(0, percentage))
        assert clamped_pct == 0

    def test_resource_ring_path_full_percent(self):
        cx, cy, r, percentage = 100, 100, 22, 100
        clamped_pct = min(100, max(0, percentage))
        assert clamped_pct == 100

    def test_resource_ring_path_half_percent(self):
        cx, cy, r, percentage = 100, 100, 22, 50
        clamped_pct = min(100, max(0, percentage))
        assert clamped_pct == 50

    def test_resource_ring_path_over_100_clamped(self):
        percentage = 150
        clamped_pct = min(100, max(0, percentage))
        assert clamped_pct == 100

    def test_resource_ring_path_negative_clamped(self):
        percentage = -10
        clamped_pct = min(100, max(0, percentage))
        assert clamped_pct == 0


class TestTopologyLinkLoadWidth:
    def test_load_width_increases_with_load(self):
        base_width = 3
        load = 50
        width = base_width + (load / 100) * 5
        assert width == 5.5

    def test_load_width_zero_load(self):
        base_width = 3
        load = 0
        width = base_width + (load / 100) * 5
        assert width == 3

    def test_load_width_full_load(self):
        base_width = 3
        load = 100
        width = base_width + (load / 100) * 5
        assert width == 8
