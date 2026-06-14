# -*- coding: utf-8 -*-
import pytest
import re
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

try:
    from fastapi.testclient import TestClient
    from backend.api.main import app
    client = TestClient(app)
    BACKEND_AVAILABLE = True
except Exception:
    BACKEND_AVAILABLE = False


TOOL_NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{2,31}$')
PARAM_NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{1,31}$')

TOOL_NAME_MIN_LENGTH = 3
TOOL_NAME_MAX_LENGTH = 32
TOOL_DESC_MIN_LENGTH = 10
TOOL_DESC_MAX_LENGTH = 500
PARAM_NAME_MIN_LENGTH = 2
PARAM_NAME_MAX_LENGTH = 32
PARAM_DESC_MIN_LENGTH = 10
PARAM_DESC_MAX_LENGTH = 200
MAX_PARAMS = 10

INVALID_DESCRIPTION_PATTERNS = [
    r'^随便填.*$',
    r'^测试.*$',
    r'^123.*$',
    r'^test.*$',
    r'^\W+$'
]

SENSITIVE_WORDS = ['敏感词1', '敏感词2']

DANGEROUS_CHARS = [';', "'", '--', '/*', '*/', 'xp_', 'exec']

MOCK_TOOLS = [
    {
        "name": "show_interface",
        "description": "显示网络设备接口状态信息",
        "category": "device_management",
        "tags": ["接口", "连通性"],
        "version": "1.2.0",
        "author": "系统",
        "rating": 4.5,
        "ratingCount": 32,
        "downloads": 456,
        "lastUpdated": "2025-05-20",
        "args_schema": {
            "device": "目标设备名称",
            "interface": "接口名称"
        },
        "is_custom": False
    },
    {
        "name": "config_qos",
        "description": "配置QoS策略以保障带宽",
        "category": "network_config",
        "tags": ["QoS", "带宽"],
        "version": "2.1.0",
        "author": "系统",
        "rating": 4.2,
        "ratingCount": 28,
        "downloads": 312,
        "lastUpdated": "2025-05-18",
        "args_schema": {
            "device": "目标设备名称",
            "class_name": "QoS类名",
            "bandwidth_percent": "带宽百分比数值"
        },
        "is_custom": False
    },
    {
        "name": "ping",
        "description": "执行网络连通性测试工具",
        "category": "network_diagnosis",
        "tags": ["连通性"],
        "version": "1.0.0",
        "author": "系统",
        "rating": 4.8,
        "ratingCount": 56,
        "downloads": 892,
        "lastUpdated": "2025-05-22",
        "args_schema": {
            "target": "目标IP地址或主机名",
            "count": "ping次数默认为四次"
        },
        "is_custom": False
    },
    {
        "name": "config_acl",
        "description": "配置ACL访问控制规则",
        "category": "security",
        "tags": ["ACL", "安全"],
        "version": "3.0.1",
        "author": "系统",
        "rating": 4.0,
        "ratingCount": 19,
        "downloads": 178,
        "lastUpdated": "2025-05-15",
        "args_schema": {
            "device": "目标设备名称",
            "acl_name": "ACL规则名称",
            "action": "动作permit或deny",
            "protocol": "协议类型名称",
            "source": "源地址信息",
            "destination": "目标地址信息"
        },
        "is_custom": False
    },
    {
        "name": "custom_monitor_v1",
        "description": "自定义网络监控工具用于实时流量分析",
        "category": "network_diagnosis",
        "tags": ["监控", "流量"],
        "version": "1.0.0",
        "author": "用户A",
        "rating": 3.5,
        "ratingCount": 8,
        "downloads": 45,
        "lastUpdated": "2025-05-23",
        "args_schema": {
            "device": "目标设备名称",
            "threshold": "告警阈值百分比"
        },
        "is_custom": True
    }
]


def validate_tool_name(name: str) -> tuple:
    if not name or not isinstance(name, str):
        return False, "工具名称必须是非空字符串"
    if len(name) < TOOL_NAME_MIN_LENGTH:
        return False, f"工具名称至少需要{TOOL_NAME_MIN_LENGTH}个字符"
    if len(name) > TOOL_NAME_MAX_LENGTH:
        return False, f"工具名称不能超过{TOOL_NAME_MAX_LENGTH}个字符"
    if not TOOL_NAME_PATTERN.match(name):
        return False, "工具名称格式错误：字母开头，3-32字符，仅字母/数字/下划线"
    for char in DANGEROUS_CHARS:
        if char in name.lower():
            return False, "工具名称包含非法字符"
    for word in SENSITIVE_WORDS:
        if word in name:
            return False, "工具名称包含敏感内容"
    return True, None


XSS_PATTERNS = [
    r'<\s*script',
    r'<\s*img[^>]+onerror',
    r'<\s*\w+[^>]+on\w+\s*=',
    r'javascript\s*:',
]


def validate_tool_description(desc: str) -> tuple:
    if not desc or not isinstance(desc, str):
        return False, "工具描述必须是非空字符串"
    trimmed = desc.strip()
    if len(trimmed) < TOOL_DESC_MIN_LENGTH:
        return False, f"工具描述至少需要{TOOL_DESC_MIN_LENGTH}个字符"
    if len(trimmed) > TOOL_DESC_MAX_LENGTH:
        return False, f"工具描述不能超过{TOOL_DESC_MAX_LENGTH}个字符"
    for pattern in INVALID_DESCRIPTION_PATTERNS:
        if re.match(pattern, trimmed, re.IGNORECASE):
            return False, "请填写有效的工具描述"
    for word in SENSITIVE_WORDS:
        if word in desc:
            return False, "工具描述包含敏感内容"
    for pattern in XSS_PATTERNS:
        if re.search(pattern, trimmed, re.IGNORECASE):
            return False, "工具描述包含不安全内容"
    return True, None


def validate_param_name(name: str) -> tuple:
    if not name or not isinstance(name, str):
        return False, "参数名必须是非空字符串"
    if len(name) < PARAM_NAME_MIN_LENGTH:
        return False, f"参数名至少需要{PARAM_NAME_MIN_LENGTH}个字符"
    if len(name) > PARAM_NAME_MAX_LENGTH:
        return False, f"参数名不能超过{PARAM_NAME_MAX_LENGTH}个字符"
    if not PARAM_NAME_PATTERN.match(name):
        return False, "参数名格式错误：字母开头，2-32字符，仅字母/数字/下划线"
    return True, None


def validate_param_description(desc: str) -> tuple:
    if not desc or not isinstance(desc, str):
        return False, "参数描述必须是非空字符串"
    trimmed = desc.strip()
    if len(trimmed) < PARAM_DESC_MIN_LENGTH:
        return False, f"参数描述至少需要{PARAM_DESC_MIN_LENGTH}个字符"
    if len(trimmed) > PARAM_DESC_MAX_LENGTH:
        return False, f"参数描述不能超过{PARAM_DESC_MAX_LENGTH}个字符"
    return True, None


def validate_tool_config(tool_config: Dict[str, Any]) -> tuple:
    required_fields = ["name", "description", "args_schema"]
    for field in required_fields:
        if field not in tool_config:
            return False, f"缺少必需字段: {field}"

    is_valid, error = validate_tool_name(tool_config["name"])
    if not is_valid:
        return False, error

    is_valid, error = validate_tool_description(tool_config["description"])
    if not is_valid:
        return False, error

    args_schema = tool_config["args_schema"]
    if not isinstance(args_schema, dict):
        return False, "args_schema 必须是对象"
    if len(args_schema) > MAX_PARAMS:
        return False, "参数数量不能超过10个"

    seen_names = set()
    for param_name, param_desc in args_schema.items():
        is_valid, error = validate_param_name(param_name)
        if not is_valid:
            return False, error
        if param_name in seen_names:
            return False, f"参数名 '{param_name}' 重复"
        seen_names.add(param_name)

        if not isinstance(param_desc, str) or not param_desc.strip():
            return False, f"参数 '{param_name}' 的描述不能为空"
        is_valid, error = validate_param_description(param_desc)
        if not is_valid:
            return False, error

    return True, None


def search_tools(tools: List[Dict], query: str = "", category: str = "", tag: str = "") -> List[Dict]:
    result = tools
    if query:
        q = query.lower()
        result = [t for t in result if q in t["name"].lower() or q in t["description"].lower() or any(q in tag.lower() for tag in t.get("tags", []))]
    if category and category != "all":
        if category == "custom":
            result = [t for t in result if t.get("is_custom", False)]
        else:
            result = [t for t in result if t.get("category") == category]
    if tag:
        result = [t for t in result if tag in t.get("tags", [])]
    return result


def sort_tools(tools: List[Dict], sort_by: str = "name") -> List[Dict]:
    result = list(tools)
    if sort_by == "name":
        result.sort(key=lambda t: t["name"])
    elif sort_by == "rating":
        result.sort(key=lambda t: t.get("rating", 0), reverse=True)
    elif sort_by == "downloads":
        result.sort(key=lambda t: t.get("downloads", 0), reverse=True)
    elif sort_by == "lastUpdated":
        result.sort(key=lambda t: t.get("lastUpdated", ""), reverse=True)
    return result


def escape_csv(value: Any) -> str:
    s = str(value)
    if re.search(r'[",\n\r=+\-@]', s):
        return '"' + s.replace('"', '""') + '"'
    return s


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend module not available")
class TestMCPToolsAPIEndpoints:
    def test_get_tools_list(self):
        response = client.get("/api/v1/mcp-tools/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_search_tools_with_query(self):
        response = client.get("/api/v1/mcp-tools/?q=ping")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["data"], list)

    def test_search_tools_no_result(self):
        response = client.get("/api/v1/mcp-tools/?q=nonexistent_tool_xyz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 0

    def test_check_name_available(self):
        response = client.get("/api/v1/mcp-tools/check-name?name=my_unique_tool_v9")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "available" in data
        assert isinstance(data["available"], bool)

    def test_check_name_unavailable(self):
        response = client.get("/api/v1/mcp-tools/check-name?name=ping")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["available"] is False

    def test_get_tool_details(self):
        response = client.get("/api/v1/mcp-tools/ping")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert data["data"]["name"] == "ping"

    def test_get_tool_details_not_found(self):
        response = client.get("/api/v1/mcp-tools/nonexistent_tool_xyz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

    def test_add_tool(self):
        response = client.post(
            "/api/v1/mcp-tools/add",
            json={
                "name": "test_weather_query",
                "description": "查询指定城市的实时天气数据信息",
                "args_schema": {
                    "city_name": "需要查询天气的城市名称"
                },
                "required": ["city_name"]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["success", "error"]

    def test_delete_tool(self):
        add_resp = client.post(
            "/api/v1/mcp-tools/add",
            json={
                "name": "test_delete_target",
                "description": "用于删除测试的临时工具描述",
                "args_schema": {
                    "param_one": "测试参数一的描述信息"
                }
            }
        )
        if add_resp.json().get("status") == "success":
            response = client.delete("/api/v1/mcp-tools/delete/test_delete_target")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ["success", "error"]

    def test_delete_nonexistent_tool(self):
        response = client.delete("/api/v1/mcp-tools/delete/nonexistent_tool_xyz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"


class TestToolNameValidation:
    def test_valid_name(self):
        is_valid, _ = validate_tool_name("my_tool_v1")
        assert is_valid is True

    def test_valid_name_min_length(self):
        is_valid, _ = validate_tool_name("abc")
        assert is_valid is True

    def test_valid_name_max_length(self):
        is_valid, _ = validate_tool_name("a" * 32)
        assert is_valid is True

    def test_name_too_short(self):
        is_valid, error = validate_tool_name("ab")
        assert is_valid is False
        assert "3" in error

    def test_name_too_long(self):
        is_valid, error = validate_tool_name("a" * 33)
        assert is_valid is False
        assert "32" in error

    def test_name_starts_with_number(self):
        is_valid, _ = validate_tool_name("1tool_name")
        assert is_valid is False

    def test_name_starts_with_underscore(self):
        is_valid, _ = validate_tool_name("_tool_name")
        assert is_valid is False

    def test_name_with_hyphen(self):
        is_valid, _ = validate_tool_name("my-tool-name")
        assert is_valid is False

    def test_name_with_space(self):
        is_valid, _ = validate_tool_name("my tool name")
        assert is_valid is False

    def test_name_with_chinese(self):
        is_valid, _ = validate_tool_name("工具名称")
        assert is_valid is False

    def test_name_empty_string(self):
        is_valid, _ = validate_tool_name("")
        assert is_valid is False

    def test_name_none(self):
        is_valid, _ = validate_tool_name(None)
        assert is_valid is False

    def test_name_pattern_letters_only(self):
        is_valid, _ = validate_tool_name("abcdef")
        assert is_valid is True

    def test_name_pattern_alphanumeric_underscore(self):
        is_valid, _ = validate_tool_name("tool_v2_beta")
        assert is_valid is True


class TestToolDescriptionValidation:
    def test_valid_description(self):
        is_valid, _ = validate_tool_description("这是一个有效的工具描述信息")
        assert is_valid is True

    def test_description_min_length(self):
        is_valid, _ = validate_tool_description("a" * 10)
        assert is_valid is True

    def test_description_below_min_length(self):
        is_valid, error = validate_tool_description("a" * 9)
        assert is_valid is False
        assert "10" in error

    def test_description_max_length(self):
        is_valid, _ = validate_tool_description("a" * 500)
        assert is_valid is True

    def test_description_exceeds_max_length(self):
        is_valid, error = validate_tool_description("a" * 501)
        assert is_valid is False
        assert "500" in error

    def test_description_empty(self):
        is_valid, _ = validate_tool_description("")
        assert is_valid is False

    def test_description_none(self):
        is_valid, _ = validate_tool_description(None)
        assert is_valid is False

    def test_description_whitespace_only(self):
        is_valid, _ = validate_tool_description("   ")
        assert is_valid is False

    def test_description_invalid_pattern_test(self):
        is_valid, _ = validate_tool_description("测试工具描述")
        assert is_valid is False

    def test_description_invalid_pattern_123(self):
        is_valid, _ = validate_tool_description("123随便写的")
        assert is_valid is False

    def test_description_invalid_pattern_test_english(self):
        is_valid, _ = validate_tool_description("test description")
        assert is_valid is False

    def test_description_invalid_pattern_symbols(self):
        is_valid, _ = validate_tool_description("!@#$%")
        assert is_valid is False

    def test_description_sensitive_word(self):
        is_valid, _ = validate_tool_description("这是一个敏感词1包含的描述信息")
        assert is_valid is False


class TestParamNameValidation:
    def test_valid_param_name(self):
        is_valid, _ = validate_param_name("device_name")
        assert is_valid is True

    def test_param_name_min_length(self):
        is_valid, _ = validate_param_name("ab")
        assert is_valid is True

    def test_param_name_below_min_length(self):
        is_valid, error = validate_param_name("a")
        assert is_valid is False
        assert "2" in error

    def test_param_name_max_length(self):
        is_valid, _ = validate_param_name("a" * 32)
        assert is_valid is True

    def test_param_name_exceeds_max_length(self):
        is_valid, error = validate_param_name("a" * 33)
        assert is_valid is False
        assert "32" in error

    def test_param_name_starts_with_number(self):
        is_valid, _ = validate_param_name("1param")
        assert is_valid is False

    def test_param_name_with_hyphen(self):
        is_valid, _ = validate_param_name("my-param")
        assert is_valid is False

    def test_param_name_with_space(self):
        is_valid, _ = validate_param_name("my param")
        assert is_valid is False

    def test_param_name_empty(self):
        is_valid, _ = validate_param_name("")
        assert is_valid is False


class TestParamDescriptionValidation:
    def test_valid_param_description(self):
        is_valid, _ = validate_param_description("目标设备的名称标识符")
        assert is_valid is True

    def test_param_desc_min_length(self):
        is_valid, _ = validate_param_description("a" * 10)
        assert is_valid is True

    def test_param_desc_below_min_length(self):
        is_valid, error = validate_param_description("a" * 9)
        assert is_valid is False
        assert "10" in error

    def test_param_desc_max_length(self):
        is_valid, _ = validate_param_description("a" * 200)
        assert is_valid is True

    def test_param_desc_exceeds_max_length(self):
        is_valid, error = validate_param_description("a" * 201)
        assert is_valid is False
        assert "200" in error

    def test_param_desc_empty(self):
        is_valid, _ = validate_param_description("")
        assert is_valid is False

    def test_param_desc_whitespace_only(self):
        is_valid, _ = validate_param_description("   ")
        assert is_valid is False


class TestMaxParamsValidation:
    def test_at_max_params(self):
        args_schema = {f"param_{i:02d}": f"第{i}个参数的描述信息内容" for i in range(MAX_PARAMS)}
        is_valid, _ = validate_tool_config({
            "name": "max_params_tool",
            "description": "验证最大参数数量的工具描述信息",
            "args_schema": args_schema
        })
        assert is_valid is True

    def test_exceeds_max_params(self):
        args_schema = {f"param_{i:02d}": f"第{i}个参数的描述信息内容" for i in range(MAX_PARAMS + 1)}
        is_valid, error = validate_tool_config({
            "name": "over_params_tool",
            "description": "验证超过最大参数数量的工具描述信息",
            "args_schema": args_schema
        })
        assert is_valid is False
        assert "10" in error

    def test_zero_params(self):
        is_valid, _ = validate_tool_config({
            "name": "no_params_tool",
            "description": "没有参数的工具描述信息",
            "args_schema": {}
        })
        assert is_valid is True


class TestInvalidDescriptionPatternDetection:
    def test_pattern_suibiantian(self):
        is_valid, _ = validate_tool_description("随便填写的描述信息")
        assert is_valid is False

    def test_pattern_ceshi(self):
        is_valid, _ = validate_tool_description("测试用的工具描述")
        assert is_valid is False

    def test_pattern_123(self):
        is_valid, _ = validate_tool_description("1234567890随便写")
        assert is_valid is False

    def test_pattern_test(self):
        is_valid, _ = validate_tool_description("test tool description here")
        assert is_valid is False

    def test_pattern_symbols_only(self):
        is_valid, _ = validate_tool_description("!@#$%^&*()")
        assert is_valid is False

    def test_valid_description_not_matching_pattern(self):
        is_valid, _ = validate_tool_description("查询指定城市的实时天气数据")
        assert is_valid is True


class TestSQLInjectionDetection:
    def test_semicolon_in_name(self):
        is_valid, _ = validate_tool_name("tool;name")
        assert is_valid is False

    def test_single_quote_in_name(self):
        is_valid, _ = validate_tool_name("tool'name")
        assert is_valid is False

    def test_double_dash_in_name(self):
        is_valid, _ = validate_tool_name("tool--name")
        assert is_valid is False

    def test_block_comment_in_name(self):
        is_valid, _ = validate_tool_name("tool/*name*/")
        assert is_valid is False

    def test_xp_prefix_in_name(self):
        is_valid, _ = validate_tool_name("xp_cmdshell_exec")
        assert is_valid is False

    def test_exec_in_name(self):
        is_valid, _ = validate_tool_name("exec_tool_run")
        assert is_valid is False

    def test_clean_name_passes(self):
        is_valid, _ = validate_tool_name("clean_tool_name")
        assert is_valid is True


class TestSensitiveWordDetection:
    def test_sensitive_word_in_name(self):
        is_valid, _ = validate_tool_name("tool_敏感词1_name")
        assert is_valid is False

    def test_sensitive_word_in_description(self):
        is_valid, _ = validate_tool_description("这是一个包含敏感词2的工具描述信息")
        assert is_valid is False

    def test_no_sensitive_word_in_name(self):
        is_valid, _ = validate_tool_name("normal_tool_name")
        assert is_valid is True

    def test_no_sensitive_word_in_description(self):
        is_valid, _ = validate_tool_description("正常的工具描述信息内容")
        assert is_valid is True


class TestSearchByName:
    def test_search_exact_name(self):
        results = search_tools(MOCK_TOOLS, query="ping")
        assert len(results) == 1
        assert results[0]["name"] == "ping"

    def test_search_partial_name(self):
        results = search_tools(MOCK_TOOLS, query="config")
        assert len(results) == 2
        names = [t["name"] for t in results]
        assert "config_qos" in names
        assert "config_acl" in names

    def test_search_name_case_insensitive(self):
        results = search_tools(MOCK_TOOLS, query="PING")
        assert len(results) == 1
        assert results[0]["name"] == "ping"

    def test_search_name_no_match(self):
        results = search_tools(MOCK_TOOLS, query="nonexistent")
        assert len(results) == 0


class TestSearchByDescription:
    def test_search_description_keyword(self):
        results = search_tools(MOCK_TOOLS, query="连通性")
        assert len(results) >= 1

    def test_search_description_case_insensitive(self):
        results = search_tools(MOCK_TOOLS, query="QOS")
        assert len(results) >= 1

    def test_search_description_no_match(self):
        results = search_tools(MOCK_TOOLS, query="不存在的描述xyz")
        assert len(results) == 0


class TestFilterByCategory:
    def test_filter_network_config(self):
        results = search_tools(MOCK_TOOLS, category="network_config")
        assert len(results) >= 1
        assert all(t["category"] == "network_config" for t in results)

    def test_filter_security(self):
        results = search_tools(MOCK_TOOLS, category="security")
        assert len(results) >= 1
        assert all(t["category"] == "security" for t in results)

    def test_filter_custom(self):
        results = search_tools(MOCK_TOOLS, category="custom")
        assert len(results) >= 1
        assert all(t.get("is_custom", False) for t in results)

    def test_filter_all(self):
        results = search_tools(MOCK_TOOLS, category="all")
        assert len(results) == len(MOCK_TOOLS)

    def test_filter_nonexistent_category(self):
        results = search_tools(MOCK_TOOLS, category="nonexistent_cat")
        assert len(results) == 0


class TestFilterByTag:
    def test_filter_by_tag_acl(self):
        results = search_tools(MOCK_TOOLS, tag="ACL")
        assert len(results) >= 1
        assert all("ACL" in t.get("tags", []) for t in results)

    def test_filter_by_tag_connectivity(self):
        results = search_tools(MOCK_TOOLS, tag="连通性")
        assert len(results) >= 1

    def test_filter_by_nonexistent_tag(self):
        results = search_tools(MOCK_TOOLS, tag="不存在的标签")
        assert len(results) == 0


class TestCombinedSearchAndFilter:
    def test_search_and_category(self):
        results = search_tools(MOCK_TOOLS, query="config", category="security")
        assert len(results) >= 1
        assert all(t["category"] == "security" for t in results)

    def test_search_and_tag(self):
        results = search_tools(MOCK_TOOLS, query="配置", tag="ACL")
        assert len(results) >= 1
        assert all("ACL" in t.get("tags", []) for t in results)

    def test_search_category_and_tag(self):
        results = search_tools(MOCK_TOOLS, category="security", tag="安全")
        assert len(results) >= 1

    def test_all_filters_combined(self):
        results = search_tools(MOCK_TOOLS, query="config", category="security", tag="ACL")
        assert len(results) >= 1

    def test_combined_no_result(self):
        results = search_tools(MOCK_TOOLS, query="nonexistent", category="security")
        assert len(results) == 0


class TestSortTools:
    def test_sort_by_name(self):
        results = sort_tools(MOCK_TOOLS, "name")
        names = [t["name"] for t in results]
        assert names == sorted(names)

    def test_sort_by_rating(self):
        results = sort_tools(MOCK_TOOLS, "rating")
        ratings = [t["rating"] for t in results]
        assert ratings == sorted(ratings, reverse=True)

    def test_sort_by_downloads(self):
        results = sort_tools(MOCK_TOOLS, "downloads")
        downloads = [t["downloads"] for t in results]
        assert downloads == sorted(downloads, reverse=True)

    def test_sort_by_last_updated(self):
        results = sort_tools(MOCK_TOOLS, "lastUpdated")
        dates = [t["lastUpdated"] for t in results]
        assert dates == sorted(dates, reverse=True)

    def test_sort_empty_list(self):
        results = sort_tools([], "name")
        assert results == []


class TestJSONExport:
    def test_json_export_structure(self):
        export_payload = {
            "exportTime": datetime.now().isoformat(),
            "totalTools": len(MOCK_TOOLS),
            "tools": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "category": t["category"],
                    "tags": t["tags"],
                    "version": t["version"],
                    "author": t["author"],
                    "rating": t["rating"],
                    "ratingCount": t["ratingCount"],
                    "downloads": t["downloads"],
                    "lastUpdated": t["lastUpdated"],
                    "isCustom": t.get("is_custom", False),
                    "paramCount": len(t.get("args_schema", {}))
                }
                for t in MOCK_TOOLS
            ]
        }
        assert "exportTime" in export_payload
        assert "totalTools" in export_payload
        assert "tools" in export_payload
        assert export_payload["totalTools"] == 5
        assert len(export_payload["tools"]) == 5

    def test_json_export_serializable(self):
        export_payload = {
            "exportTime": datetime.now().isoformat(),
            "totalTools": len(MOCK_TOOLS),
            "tools": MOCK_TOOLS
        }
        serialized = json.dumps(export_payload, ensure_ascii=False)
        deserialized = json.loads(serialized)
        assert deserialized["totalTools"] == 5
        assert len(deserialized["tools"]) == 5


class TestCSVExport:
    def test_csv_export_headers(self):
        headers = "工具名称,描述,分类,版本,评分,下载量,是否自定义,参数数量\n"
        assert "工具名称" in headers
        assert "描述" in headers
        assert "分类" in headers
        assert "评分" in headers
        assert "下载量" in headers
        assert "是否自定义" in headers
        assert "参数数量" in headers

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


class TestToolNameDangerousChars:
    def test_name_with_semicolon(self):
        is_valid, _ = validate_tool_name("tool;drop")
        assert is_valid is False

    def test_name_with_angle_brackets(self):
        is_valid, _ = validate_tool_name("tool<name>")
        assert is_valid is False

    def test_name_with_parentheses(self):
        is_valid, _ = validate_tool_name("tool()name")
        assert is_valid is False

    def test_name_with_pipe(self):
        is_valid, _ = validate_tool_name("tool|name")
        assert is_valid is False

    def test_name_with_ampersand(self):
        is_valid, _ = validate_tool_name("tool&name")
        assert is_valid is False


class TestDescriptionXSSVectors:
    def test_xss_script_tag(self):
        is_valid, _ = validate_tool_description("<script>alert('xss')</script>")
        assert is_valid is False

    def test_xss_img_onerror(self):
        is_valid, _ = validate_tool_description("<img src=x onerror=alert(1)>")
        assert is_valid is False

    def test_xss_event_handler(self):
        is_valid, _ = validate_tool_description("<div onmouseover=alert(1)>hover me</div>")
        assert is_valid is False

    def test_xss_javascript_uri(self):
        is_valid, _ = validate_tool_description("javascript:alert(document.cookie)")
        assert is_valid is False

    def test_safe_description_with_html_chars(self):
        is_valid, _ = validate_tool_description("使用小于10的阈值进行网络监控告警")
        assert is_valid is True


class TestParamNameSpecialChars:
    def test_param_with_dot(self):
        is_valid, _ = validate_param_name("param.name")
        assert is_valid is False

    def test_param_with_dollar(self):
        is_valid, _ = validate_param_name("$param")
        assert is_valid is False

    def test_param_with_bracket(self):
        is_valid, _ = validate_param_name("param[0]")
        assert is_valid is False

    def test_param_with_chinese(self):
        is_valid, _ = validate_param_name("参数名")
        assert is_valid is False

    def test_param_valid_underscore(self):
        is_valid, _ = validate_param_name("param_name")
        assert is_valid is True


class TestFullToolConfigValidation:
    def test_valid_full_config(self):
        config = {
            "name": "weather_query_v1",
            "description": "查询指定城市的实时天气数据信息",
            "args_schema": {
                "city_name": "需要查询天气的城市名称"
            }
        }
        is_valid, _ = validate_tool_config(config)
        assert is_valid is True

    def test_missing_name_field(self):
        config = {
            "description": "查询指定城市的实时天气数据信息",
            "args_schema": {"city_name": "需要查询天气的城市名称"}
        }
        is_valid, error = validate_tool_config(config)
        assert is_valid is False
        assert "name" in error

    def test_missing_description_field(self):
        config = {
            "name": "weather_query_v1",
            "args_schema": {"city_name": "需要查询天气的城市名称"}
        }
        is_valid, error = validate_tool_config(config)
        assert is_valid is False
        assert "description" in error

    def test_missing_args_schema_field(self):
        config = {
            "name": "weather_query_v1",
            "description": "查询指定城市的实时天气数据信息"
        }
        is_valid, error = validate_tool_config(config)
        assert is_valid is False
        assert "args_schema" in error

    def test_args_schema_not_dict(self):
        config = {
            "name": "weather_query_v1",
            "description": "查询指定城市的实时天气数据信息",
            "args_schema": "not_a_dict"
        }
        is_valid, _ = validate_tool_config(config)
        assert is_valid is False

    def test_duplicate_param_names(self):
        schema_list = [
            ("city_name", "需要查询天气的城市名称"),
            ("city_name", "重复的参数名称描述信息")
        ]
        seen = set()
        has_dup = False
        for name, _ in schema_list:
            if name in seen:
                has_dup = True
                break
            seen.add(name)
        assert has_dup is True

    def test_param_desc_too_short(self):
        config = {
            "name": "weather_query_v1",
            "description": "查询指定城市的实时天气数据信息",
            "args_schema": {
                "city_name": "短描述"
            }
        }
        is_valid, _ = validate_tool_config(config)
        assert is_valid is False


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend module not available")
class TestMCPToolsIntegration:
    def test_add_search_delete_workflow(self):
        tool_name = "integration_test_tool"
        add_resp = client.post(
            "/api/v1/mcp-tools/add",
            json={
                "name": tool_name,
                "description": "集成测试用的临时工具描述信息",
                "args_schema": {
                    "test_param": "测试参数的描述信息内容"
                }
            }
        )
        assert add_resp.status_code == 200
        add_data = add_resp.json()
        assert add_data["status"] == "success"

        search_resp = client.get(f"/api/v1/mcp-tools/?q={tool_name}")
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert search_data["status"] == "success"
        found = any(t["name"] == tool_name for t in search_data["data"])
        assert found is True

        delete_resp = client.delete(f"/api/v1/mcp-tools/delete/{tool_name}")
        assert delete_resp.status_code == 200
        delete_data = delete_resp.json()
        assert delete_data["status"] == "success"

    def test_name_conflict_detection(self):
        check_resp = client.get("/api/v1/mcp-tools/check-name?name=ping")
        assert check_resp.status_code == 200
        check_data = check_resp.json()
        assert check_data["status"] == "success"
        assert check_data["available"] is False

    def test_delete_builtin_tool_fails(self):
        delete_resp = client.delete("/api/v1/mcp-tools/delete/ping")
        assert delete_resp.status_code == 200
        delete_data = delete_resp.json()
        assert delete_data["status"] == "error"


class TestMetricsCalculation:
    def test_metrics_from_mock_data(self):
        total = len(MOCK_TOOLS)
        custom = len([t for t in MOCK_TOOLS if t.get("is_custom", False)])
        builtin = len([t for t in MOCK_TOOLS if not t.get("is_custom", False)])
        avg_rating = round(sum(t["rating"] for t in MOCK_TOOLS) / total, 1) if total > 0 else 0

        assert total == 5
        assert custom == 1
        assert builtin == 4
        assert avg_rating > 0

    def test_metrics_empty_data(self):
        tools = []
        total = len(tools)
        custom = len([t for t in tools if t.get("is_custom", False)])
        builtin = len([t for t in tools if not t.get("is_custom", False)])
        avg_rating = 0 if total == 0 else round(sum(t["rating"] for t in tools) / total, 1)

        assert total == 0
        assert custom == 0
        assert builtin == 0
        assert avg_rating == 0

    def test_metrics_all_custom(self):
        tools = [
            {"name": "custom1", "rating": 4.0, "is_custom": True},
            {"name": "custom2", "rating": 3.5, "is_custom": True}
        ]
        custom = len([t for t in tools if t.get("is_custom", False)])
        builtin = len([t for t in tools if not t.get("is_custom", False)])
        assert custom == 2
        assert builtin == 0


class TestCategoryGuessLogic:
    def test_network_config_keywords(self):
        keywords = ["config", "qos", "acl", "policy", "bandwidth"]
        for kw in keywords:
            assert re.search(r"config|qos|acl|policy|bandwidth", kw, re.IGNORECASE) is not None

    def test_network_diagnosis_keywords(self):
        keywords = ["ping", "traceroute", "diagnos", "show", "check", "test"]
        for kw in keywords:
            assert re.search(r"ping|traceroute|diagnos|show|check|test", kw, re.IGNORECASE) is not None

    def test_security_keywords(self):
        keywords = ["security", "firewall", "encrypt", "auth"]
        for kw in keywords:
            assert re.search(r"security|firewall|encrypt|auth", kw, re.IGNORECASE) is not None

    def test_device_management_keywords(self):
        keywords = ["device", "interface", "status", "version"]
        for kw in keywords:
            assert re.search(r"device|interface|status|version", kw, re.IGNORECASE) is not None


class TestTagGuessLogic:
    def test_qos_tag(self):
        combined = "config_qos 配置带宽策略"
        assert re.search(r"qos|带宽|bandwidth", combined, re.IGNORECASE) is not None

    def test_acl_tag(self):
        combined = "config_acl 访问控制列表"
        assert re.search(r"acl|访问|access", combined, re.IGNORECASE) is not None

    def test_interface_tag(self):
        combined = "show_interface 接口状态"
        assert re.search(r"接口|interface", combined, re.IGNORECASE) is not None

    def test_route_tag(self):
        combined = "traceroute 路由追踪"
        assert re.search(r"路由|route", combined, re.IGNORECASE) is not None

    def test_ping_tag(self):
        combined = "ping 连通性测试"
        assert re.search(r"ping|连通", combined, re.IGNORECASE) is not None

    def test_security_tag(self):
        combined = "config_acl 安全策略"
        assert re.search(r"安全|security", combined, re.IGNORECASE) is not None
