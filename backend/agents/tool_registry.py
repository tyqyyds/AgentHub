"""工具注册中心 - MCP工具的注册、发现、生命周期管理"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..core.config import settings
from ..database.models import MCPToolStatus, MCPServerStatus

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """工具分类"""
    DEVICE_OPERATION = "device_operation"
    CONFIG_GENERATION = "config_generation"
    DIAGNOSTICS = "diagnostics"
    SECURITY = "security"
    MONITORING = "monitoring"
    HEALING = "healing"
    NOTIFICATION = "notification"
    DATA_QUERY = "data_query"


@dataclass
class ToolInfo:
    """工具信息"""
    tool_id: str
    name: str
    description: str
    category: ToolCategory
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    endpoint_url: str = ""
    status: MCPToolStatus = MCPToolStatus.ACTIVE
    version: str = "1.0.0"
    server_id: str = ""
    avg_latency_ms: float = 0.0
    success_rate: float = 1.0
    total_calls: int = 0
    success_calls: int = 0
    last_called_at: float = 0.0
    registered_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.registered_at:
            self.registered_at = time.time()


@dataclass
class MCPServerInfo:
    """MCP远程服务器信息"""
    server_id: str
    name: str
    endpoint_url: str
    status: MCPServerStatus = MCPServerStatus.DISCONNECTED
    api_key: str = ""
    capabilities: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    last_sync_at: float = 0.0
    registered_at: float = 0.0
    health_score: float = 1.0

    def __post_init__(self):
        if not self.registered_at:
            self.registered_at = time.time()


@dataclass
class ToolRegistryConfig:
    """工具注册中心配置"""
    max_tools: int = 500
    max_servers: int = 50
    health_check_interval_seconds: int = 60
    sync_interval_seconds: int = 300
    auto_disable_on_failure_rate: float = 0.3
    auto_disable_check_window: int = 100


class ToolRegistry:
    """工具注册中心：MCP工具的注册与发现"""

    def __init__(self, config: Optional[ToolRegistryConfig] = None):
        self.config = config or ToolRegistryConfig()
        self._tools: dict[str, ToolInfo] = {}
        self._servers: dict[str, MCPServerInfo] = {}
        self._category_index: dict[str, list[str]] = {}
        self._server_tool_index: dict[str, list[str]] = {}
        self._stats: dict[str, int] = {
            "total_registrations": 0,
            "total_deregistrations": 0,
            "total_calls": 0,
            "discovery_queries": 0,
            "server_syncs": 0,
        }
        logger.info("工具注册中心初始化完成")

    def register_tool(self, tool_info: ToolInfo) -> bool:
        """注册工具"""
        if len(self._tools) >= self.config.max_tools and tool_info.tool_id not in self._tools:
            logger.warning(f"工具注册中心已满，无法注册: {tool_info.tool_id}")
            return False

        tool_info.registered_at = time.time()
        self._tools[tool_info.tool_id] = tool_info

        # 更新分类索引
        cat = tool_info.category.value
        if cat not in self._category_index:
            self._category_index[cat] = []
        if tool_info.tool_id not in self._category_index[cat]:
            self._category_index[cat].append(tool_info.tool_id)

        # 更新服务器-工具索引
        if tool_info.server_id:
            if tool_info.server_id not in self._server_tool_index:
                self._server_tool_index[tool_info.server_id] = []
            if tool_info.tool_id not in self._server_tool_index[tool_info.server_id]:
                self._server_tool_index[tool_info.server_id].append(tool_info.tool_id)

        self._stats["total_registrations"] += 1
        logger.info(f"工具注册: {tool_info.tool_id}, 名称: {tool_info.name}, 分类: {tool_info.category.value}")
        return True

    def deregister_tool(self, tool_id: str) -> bool:
        """注销工具"""
        if tool_id not in self._tools:
            return False

        tool_info = self._tools.pop(tool_id)

        # 清理分类索引
        cat = tool_info.category.value
        if cat in self._category_index:
            self._category_index[cat] = [tid for tid in self._category_index[cat] if tid != tool_id]
            if not self._category_index[cat]:
                del self._category_index[cat]

        # 清理服务器-工具索引
        if tool_info.server_id and tool_info.server_id in self._server_tool_index:
            self._server_tool_index[tool_info.server_id] = [
                tid for tid in self._server_tool_index[tool_info.server_id] if tid != tool_id
            ]
            if not self._server_tool_index[tool_info.server_id]:
                del self._server_tool_index[tool_info.server_id]

        self._stats["total_deregistrations"] += 1
        logger.info(f"工具注销: {tool_id}")
        return True

    def register_server(self, server_info: MCPServerInfo) -> bool:
        """注册MCP远程服务器"""
        if len(self._servers) >= self.config.max_servers and server_info.server_id not in self._servers:
            logger.warning(f"MCP服务器注册上限已满: {server_info.server_id}")
            return False

        server_info.registered_at = time.time()
        self._servers[server_info.server_id] = server_info
        logger.info(f"MCP服务器注册: {server_info.server_id}, 名称: {server_info.name}")
        return True

    def deregister_server(self, server_id: str) -> bool:
        """注销MCP远程服务器，同时注销其所有工具"""
        if server_id not in self._servers:
            return False

        # 注销该服务器下的所有工具
        tool_ids = list(self._server_tool_index.get(server_id, []))
        for tid in tool_ids:
            self.deregister_tool(tid)

        del self._servers[server_id]
        logger.info(f"MCP服务器注销: {server_id}, 关联工具: {len(tool_ids)}")
        return True

    def get_tool(self, tool_id: str) -> Optional[ToolInfo]:
        """获取工具信息"""
        return self._tools.get(tool_id)

    def get_server(self, server_id: str) -> Optional[MCPServerInfo]:
        """获取服务器信息"""
        return self._servers.get(server_id)

    def discover_by_category(self, category: ToolCategory, status_filter: Optional[MCPToolStatus] = None) -> list[ToolInfo]:
        """按分类发现工具"""
        self._stats["discovery_queries"] += 1
        tool_ids = self._category_index.get(category.value, [])
        tools = [self._tools[tid] for tid in tool_ids if tid in self._tools]

        if status_filter:
            tools = [t for t in tools if t.status == status_filter]
        else:
            tools = [t for t in tools if t.status == MCPToolStatus.ACTIVE]

        tools.sort(key=lambda t: t.success_rate, reverse=True)
        return tools

    def discover_by_capability(self, keyword: str) -> list[ToolInfo]:
        """按能力关键词发现工具"""
        self._stats["discovery_queries"] += 1
        keyword_lower = keyword.lower()
        results = []
        for tool in self._tools.values():
            if tool.status != MCPToolStatus.ACTIVE:
                continue
            searchable = f"{tool.name} {tool.description} {tool.category.value}".lower()
            if keyword_lower in searchable:
                results.append(tool)
        results.sort(key=lambda t: t.success_rate, reverse=True)
        return results

    def discover_by_server(self, server_id: str) -> list[ToolInfo]:
        """按服务器发现工具"""
        tool_ids = self._server_tool_index.get(server_id, [])
        return [self._tools[tid] for tid in tool_ids if tid in self._tools]

    def update_tool_result(self, tool_id: str, success: bool, latency_ms: float = 0.0) -> None:
        """更新工具调用结果"""
        tool = self._tools.get(tool_id)
        if not tool:
            return

        tool.total_calls += 1
        if success:
            tool.success_calls += 1
        tool.success_rate = tool.success_calls / tool.total_calls if tool.total_calls > 0 else 0.0
        tool.last_called_at = time.time()

        if latency_ms > 0:
            total = tool.total_calls
            tool.avg_latency_ms = (tool.avg_latency_ms * (total - 1) + latency_ms) / total

        self._stats["total_calls"] += 1

        # 自动禁用检查
        if (tool.total_calls >= self.config.auto_disable_check_window
                and tool.success_rate < self.config.auto_disable_on_failure_rate):
            tool.status = MCPToolStatus.DISABLED
            logger.warning(f"工具自动禁用: {tool_id}, 成功率: {tool.success_rate:.2%}")

    def update_server_status(self, server_id: str, status: MCPServerStatus) -> bool:
        """更新服务器状态"""
        server = self._servers.get(server_id)
        if server:
            server.status = status
            logger.info(f"MCP服务器状态更新: {server_id} -> {status.value}")
            return True
        return False

    def sync_server_tools(self, server_id: str) -> dict[str, Any]:
        """同步远程MCP服务器的工具列表"""
        server = self._servers.get(server_id)
        if not server:
            return {"success": False, "error": f"服务器未注册: {server_id}"}

        self._stats["server_syncs"] += 1
        server.last_sync_at = time.time()

        # 模拟同步：实际应通过HTTP调用远程MCP服务器的/tools端点
        synced_count = len(self._server_tool_index.get(server_id, []))
        server.status = MCPServerStatus.CONNECTED

        logger.info(f"MCP服务器工具同步: {server_id}, 工具数: {synced_count}")
        return {
            "success": True,
            "server_id": server_id,
            "synced_tools": synced_count,
            "server_status": server.status.value,
        }

    def check_health(self) -> dict[str, Any]:
        """健康检查所有工具和服务器"""
        now = time.time()
        unhealthy_tools = []
        unhealthy_servers = []

        for tool_id, tool in self._tools.items():
            if tool.status == MCPToolStatus.ACTIVE:
                if tool.total_calls >= 10 and tool.success_rate < 0.5:
                    unhealthy_tools.append(tool_id)

        for server_id, server in self._servers.items():
            if server.status == MCPServerStatus.CONNECTED:
                if server.last_sync_at > 0 and (now - server.last_sync_at) > self.config.sync_interval_seconds * 2:
                    server.health_score = max(0.1, server.health_score - 0.2)
                    if server.health_score < 0.5:
                        unhealthy_servers.append(server_id)

        return {
            "total_tools": len(self._tools),
            "active_tools": sum(1 for t in self._tools.values() if t.status == MCPToolStatus.ACTIVE),
            "disabled_tools": sum(1 for t in self._tools.values() if t.status == MCPToolStatus.DISABLED),
            "total_servers": len(self._servers),
            "connected_servers": sum(1 for s in self._servers.values() if s.status == MCPServerStatus.CONNECTED),
            "unhealthy_tools": unhealthy_tools,
            "unhealthy_servers": unhealthy_servers,
        }

    def get_stats(self) -> dict[str, Any]:
        """获取注册中心统计"""
        return {
            **self._stats,
            "registered_tools": len(self._tools),
            "registered_servers": len(self._servers),
            "categories": list(self._category_index.keys()),
        }

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Agent标准处理接口"""
        action = input_data.get("action", "discover")

        if action == "register_tool":
            tool_data = input_data.get("tool_info", {})
            category_str = tool_data.pop("category", "device_operation")
            try:
                category = ToolCategory(category_str)
            except ValueError:
                category = ToolCategory.DEVICE_OPERATION
            tool_info = ToolInfo(category=category, **tool_data)
            success = self.register_tool(tool_info)
            return {"action": "register_tool", "success": success}

        elif action == "deregister_tool":
            success = self.deregister_tool(input_data.get("tool_id", ""))
            return {"action": "deregister_tool", "success": success}

        elif action == "register_server":
            server_data = input_data.get("server_info", {})
            server_info = MCPServerInfo(**server_data)
            success = self.register_server(server_info)
            return {"action": "register_server", "success": success}

        elif action == "deregister_server":
            success = self.deregister_server(input_data.get("server_id", ""))
            return {"action": "deregister_server", "success": success}

        elif action == "discover":
            category = input_data.get("category")
            keyword = input_data.get("keyword", "")
            if category:
                try:
                    cat_enum = ToolCategory(category)
                    tools = self.discover_by_category(cat_enum)
                except ValueError:
                    tools = self.discover_by_capability(keyword)
            elif keyword:
                tools = self.discover_by_capability(keyword)
            else:
                tools = list(self._tools.values())

            return {
                "action": "discover",
                "tools": [
                    {
                        "tool_id": t.tool_id,
                        "name": t.name,
                        "category": t.category.value,
                        "status": t.status.value,
                        "success_rate": t.success_rate,
                    }
                    for t in tools[:50]
                ],
            }

        elif action == "sync":
            server_id = input_data.get("server_id", "")
            result = self.sync_server_tools(server_id)
            return {"action": "sync", "result": result}

        elif action == "health_check":
            result = self.check_health()
            return {"action": "health_check", "result": result}

        else:
            return {"action": action, "error": "未知操作"}

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        health_result = self.check_health()
        status = "healthy"
        if health_result["unhealthy_tools"] or health_result["unhealthy_servers"]:
            status = "degraded"

        return {
            "status": status,
            "agent": self.__class__.__name__,
            "registered_tools": len(self._tools),
            "registered_servers": len(self._servers),
            "active_tools": health_result["active_tools"],
            "connected_servers": health_result["connected_servers"],
        }
