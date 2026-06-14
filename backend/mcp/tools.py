from typing import Any, Dict, List, Optional
import json
import os
import re
from pathlib import Path


# 自定义工具存储文件
CUSTOM_TOOLS_FILE = Path(__file__).parent / "custom_tools.json"

# 验证正则
NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{2,31}$')
PARAM_NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{1,31}$')

# 无效内容模式
INVALID_DESCRIPTION_PATTERNS = [
    r'^随便填.*$',
    r'^测试.*$',
    r'^123.*$',
    r'^test.*$',
    r'^\W+$'  # 纯符号
]

# 敏感词列表（示例）
SENSITIVE_WORDS = ['敏感词1', '敏感词2']


def get_default_tools() -> List[Dict[str, Any]]:
    """获取默认内置工具列表"""
    return [
        {
            "name": "show_interface",
            "description": "显示网络设备接口状态",
            "args_schema": {
                "device": "目标设备名称",
                "interface": "接口名称"
            },
            "is_custom": False
        },
        {
            "name": "config_qos",
            "description": "配置QoS策略",
            "args_schema": {
                "device": "目标设备名称",
                "class_name": "QoS类名",
                "bandwidth_percent": "带宽百分比"
            },
            "is_custom": False
        },
        {
            "name": "ping",
            "description": "执行网络连通性测试",
            "args_schema": {
                "target": "目标IP地址或主机名",
                "count": "ping次数"
            },
            "is_custom": False
        },
        {
            "name": "config_acl",
            "description": "配置ACL规则",
            "args_schema": {
                "device": "目标设备名称",
                "acl_name": "ACL名称",
                "action": "动作: permit或deny",
                "protocol": "协议",
                "source": "源地址",
                "destination": "目标地址"
            },
            "is_custom": False
        },
        {
            "name": "get_device_status",
            "description": "获取设备状态",
            "args_schema": {
                "device": "目标设备名称"
            },
            "is_custom": False
        }
    ]


def load_custom_tools() -> List[Dict[str, Any]]:
    """加载自定义工具"""
    if not CUSTOM_TOOLS_FILE.exists():
        return []
    try:
        with open(CUSTOM_TOOLS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_custom_tools(tools: List[Dict[str, Any]]):
    """保存自定义工具"""
    with open(CUSTOM_TOOLS_FILE, "w", encoding="utf-8") as f:
        json.dump(tools, f, ensure_ascii=False, indent=2)


def get_mcp_tools() -> List[Dict[str, Any]]:
    """获取所有可用的MCP工具列表（内置 + 自定义）"""
    default_tools = get_default_tools()
    custom_tools = load_custom_tools()
    return default_tools + custom_tools


def search_tools(keyword: str) -> List[Dict[str, Any]]:
    """搜索工具（按名称或描述）"""
    all_tools = get_mcp_tools()
    keyword_lower = keyword.lower()
    
    return [
        tool for tool in all_tools
        if keyword_lower in tool["name"].lower() 
        or keyword_lower in tool["description"].lower()
    ]


def check_name_available(name: str) -> bool:
    """检查工具名称是否可用"""
    all_tools = get_mcp_tools()
    for tool in all_tools:
        if tool["name"] == name:
            return False
    return True


def validate_tool_config(tool_config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    验证工具配置是否有效
    
    Returns:
        (is_valid, error_message)
    """
    # 检查必需字段
    required_fields = ["name", "description", "args_schema"]
    for field in required_fields:
        if field not in tool_config:
            return False, f"缺少必需字段: {field}"
    
    # 验证工具名称
    name = tool_config["name"]
    if not name or not isinstance(name, str):
        return False, "工具名称必须是非空字符串"
    
    if not NAME_PATTERN.match(name):
        return False, "工具名称格式错误：字母开头，3-32字符，仅字母/数字/下划线"
    
    # 检查 SQL 注入和特殊字符
    dangerous_chars = [';', "'", '--', '/*', '*/', 'xp_', 'exec']
    for char in dangerous_chars:
        if char in name.lower():
            return False, "工具名称包含非法字符"
    
    # 检查敏感词
    for word in SENSITIVE_WORDS:
        if word in name:
            return False, "工具名称包含敏感内容"
    
    # 检查是否与现有工具冲突
    if not check_name_available(name):
        return False, f"工具 '{name}' 已存在"
    
    # 验证描述
    description = tool_config["description"]
    if not description or not isinstance(description, str):
        return False, "工具描述必须是非空字符串"
    
    description_trimmed = description.strip()
    if len(description_trimmed) < 10:
        return False, "工具描述至少需要10个字符"
    
    if len(description_trimmed) > 500:
        return False, "工具描述不能超过500个字符"
    
    # 检查无效描述
    for pattern in INVALID_DESCRIPTION_PATTERNS:
        if re.match(pattern, description_trimmed, re.IGNORECASE):
            return False, "请填写有效的工具描述"
    
    # 检查敏感词
    for word in SENSITIVE_WORDS:
        if word in description:
            return False, "工具描述包含敏感内容"
    
    # 验证参数 schema
    args_schema = tool_config["args_schema"]
    if not isinstance(args_schema, dict):
        return False, "args_schema 必须是对象"
    
    # 检查参数数量
    if len(args_schema) > 10:
        return False, "参数数量不能超过10个"
    
    # 验证每个参数
    param_names = set()
    for param_name, param_desc in args_schema.items():
        if not PARAM_NAME_PATTERN.match(param_name):
            return False, f"参数 '{param_name}' 格式错误：字母开头，2-32字符，仅字母/数字/下划线"
        
        if param_name in param_names:
            return False, f"参数名 '{param_name}' 重复"
        param_names.add(param_name)
        
        if not isinstance(param_desc, str) or not param_desc.strip():
            return False, f"参数 '{param_name}' 的描述不能为空"
        
        if len(param_desc.strip()) < 10:
            return False, f"参数 '{param_name}' 的描述至少需要10个字符"
        
        if len(param_desc.strip()) > 200:
            return False, f"参数 '{param_name}' 的描述不能超过200个字符"
    
    return True, None


def add_custom_tool(tool_config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    添加自定义工具
    
    Returns:
        (success, error_message)
    """
    # 验证配置
    is_valid, error_msg = validate_tool_config(tool_config)
    if not is_valid:
        return False, error_msg
    
    # 添加自定义标记
    tool_config["is_custom"] = True
    
    # 保存
    custom_tools = load_custom_tools()
    custom_tools.append(tool_config)
    save_custom_tools(custom_tools)
    
    return True, None


def delete_custom_tool(tool_name: str) -> tuple[bool, Optional[str]]:
    """
    删除自定义工具
    
    Returns:
        (success, error_message)
    """
    # 加载所有自定义工具
    custom_tools = load_custom_tools()
    
    # 检查工具是否存在并且是自定义工具
    tool_index = None
    for i, tool in enumerate(custom_tools):
        if tool["name"] == tool_name:
            tool_index = i
            break
    
    if tool_index is None:
        return False, f"工具 '{tool_name}' 不是自定义工具或不存在"
    
    # 删除工具
    custom_tools.pop(tool_index)
    save_custom_tools(custom_tools)
    
    return True, None
