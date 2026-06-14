from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import httpx


@dataclass
class ToolDefinition:
    name: str
    description: str
    endpoint: str
    method: str
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    risk_level: str = "low"
    required_role: List[str] = field(default_factory=list)
    is_frontend_action: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._base_url: str = os.getenv("TOOL_REGISTRY_BASE_URL", "http://localhost:8000")
        self._register_builtin_tools()

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self, role: Optional[str] = None) -> List[ToolDefinition]:
        tools = list(self._tools.values())
        if role is None:
            return tools
        return [t for t in tools if "all" in t.required_role or role in t.required_role]

    def get_openai_tools_schema(self, role: Optional[str] = None) -> List[Dict[str, Any]]:
        tools = self.list_tools(role)
        schemas: List[Dict[str, Any]] = []
        for tool in tools:
            properties: Dict[str, Any] = {}
            required_params: List[str] = []
            for param_name, param_meta in tool.parameters.items():
                properties[param_name] = {
                    "type": param_meta.get("type", "string"),
                    "description": param_meta.get("description", ""),
                }
                if param_meta.get("required", False):
                    required_params.append(param_name)

            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required_params,
                    },
                },
            })
        return schemas

    async def execute_tool(self, name: str, params: Dict[str, Any], token: str) -> Dict[str, Any]:
        tool = self.get_tool(name)
        if tool is None:
            return {"error": f"Tool '{name}' not found"}

        if tool.is_frontend_action:
            return self._execute_frontend_action(tool, params)

        return await self._execute_api_call(tool, params, token)

    def _execute_frontend_action(self, tool: ToolDefinition, params: Dict[str, Any]) -> Dict[str, Any]:
        if tool.name == "navigate_to":
            return {
                "type": "frontend_action",
                "action": "navigate",
                "params": {"page": params.get("page", "")},
            }
        if tool.name == "highlight_node":
            return {
                "type": "frontend_action",
                "action": "highlight",
                "params": {"node_id": params.get("node_id", "")},
            }
        return {
            "type": "frontend_action",
            "action": tool.name,
            "params": params,
        }

    async def _execute_api_call(self, tool: ToolDefinition, params: Dict[str, Any], token: str) -> Dict[str, Any]:
        url = self._base_url + tool.endpoint

        path_params: Dict[str, str] = {}
        query_params: Dict[str, Any] = {}
        body_params: Dict[str, Any] = {}

        for param_name, param_meta in tool.parameters.items():
            value = params.get(param_name)
            if value is None:
                continue
            location = param_meta.get("in", "query")
            if location == "path":
                path_params[param_name] = str(value)
            elif location == "body":
                body_params[param_name] = value
            else:
                query_params[param_name] = value

        for pk, pv in path_params.items():
            url = url.replace(f"{{{pk}}}", pv)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if tool.method.upper() == "GET":
                    response = await client.get(url, params=query_params, headers=headers)
                elif tool.method.upper() == "POST":
                    response = await client.post(url, json=body_params or None, params=query_params, headers=headers)
                elif tool.method.upper() == "PUT":
                    response = await client.put(url, json=body_params or None, params=query_params, headers=headers)
                elif tool.method.upper() == "DELETE":
                    response = await client.delete(url, params=query_params, headers=headers)
                else:
                    return {"error": f"Unsupported HTTP method: {tool.method}"}

                try:
                    data = response.json()
                except Exception:
                    data = response.text

                return {
                    "status_code": response.status_code,
                    "data": data,
                }
            except httpx.TimeoutException:
                return {"error": f"Request to {url} timed out"}
            except httpx.RequestError as exc:
                return {"error": f"Request to {url} failed: {str(exc)}"}

    def _register_builtin_tools(self) -> None:
        self.register(ToolDefinition(
            name="query_topology",
            description="Query network topology and device status",
            endpoint="/api/v1/topology",
            method="GET",
            parameters={},
            risk_level="low",
            required_role=["admin", "operator", "viewer"],
        ))

        self.register(ToolDefinition(
            name="query_device",
            description="Get device details by device ID",
            endpoint="/api/v1/topology/devices/{device_id}",
            method="GET",
            parameters={
                "device_id": {
                    "type": "string",
                    "description": "The ID of the device to query",
                    "required": True,
                    "in": "path",
                },
            },
            risk_level="low",
            required_role=["admin", "operator", "viewer"],
        ))

        self.register(ToolDefinition(
            name="create_intent",
            description="Create a new operations intent",
            endpoint="/api/v1/intents",
            method="POST",
            parameters={
                "name": {
                    "type": "string",
                    "description": "Intent name",
                    "required": True,
                    "in": "body",
                },
                "intent_type": {
                    "type": "string",
                    "description": "Type of the intent",
                    "required": True,
                    "in": "body",
                },
                "target_devices": {
                    "type": "array",
                    "description": "List of target device IDs",
                    "required": False,
                    "in": "body",
                },
                "parameters": {
                    "type": "object",
                    "description": "Intent-specific parameters",
                    "required": False,
                    "in": "body",
                },
            },
            risk_level="medium",
            required_role=["admin", "operator"],
        ))

        self.register(ToolDefinition(
            name="list_intents",
            description="List all intents with optional filtering",
            endpoint="/api/v1/intents",
            method="GET",
            parameters={
                "status": {
                    "type": "string",
                    "description": "Filter by intent status",
                    "required": False,
                    "in": "query",
                },
                "intent_type": {
                    "type": "string",
                    "description": "Filter by intent type",
                    "required": False,
                    "in": "query",
                },
            },
            risk_level="low",
            required_role=["admin", "operator", "viewer"],
        ))

        self.register(ToolDefinition(
            name="execute_intent",
            description="Execute an approved intent",
            endpoint="/api/v1/intents/{intent_id}/execute",
            method="POST",
            parameters={
                "intent_id": {
                    "type": "string",
                    "description": "The ID of the intent to execute",
                    "required": True,
                    "in": "path",
                },
            },
            risk_level="high",
            required_role=["admin", "operator"],
        ))

        self.register(ToolDefinition(
            name="approve_intent",
            description="Approve a pending intent",
            endpoint="/api/v1/intents/{intent_id}/approve",
            method="POST",
            parameters={
                "intent_id": {
                    "type": "string",
                    "description": "The ID of the intent to approve",
                    "required": True,
                    "in": "path",
                },
            },
            risk_level="medium",
            required_role=["admin"],
        ))

        self.register(ToolDefinition(
            name="get_events",
            description="Get alert events with optional filtering",
            endpoint="/api/v1/events",
            method="GET",
            parameters={
                "severity": {
                    "type": "string",
                    "description": "Filter by event severity",
                    "required": False,
                    "in": "query",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by event status",
                    "required": False,
                    "in": "query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of events to return",
                    "required": False,
                    "in": "query",
                },
            },
            risk_level="low",
            required_role=["admin", "operator", "viewer"],
        ))

        self.register(ToolDefinition(
            name="execute_self_healing",
            description="Trigger self-healing action for an event",
            endpoint="/api/v1/events/{event_id}/execute",
            method="PUT",
            parameters={
                "event_id": {
                    "type": "string",
                    "description": "The ID of the event to self-heal",
                    "required": True,
                    "in": "path",
                },
                "action": {
                    "type": "string",
                    "description": "The self-healing action to perform",
                    "required": False,
                    "in": "body",
                },
            },
            risk_level="high",
            required_role=["admin", "operator"],
        ))

        self.register(ToolDefinition(
            name="get_audit_logs",
            description="Get audit logs for system activities",
            endpoint="/api/v1/audit",
            method="GET",
            parameters={
                "actor": {
                    "type": "string",
                    "description": "Filter by actor username",
                    "required": False,
                    "in": "query",
                },
                "action": {
                    "type": "string",
                    "description": "Filter by action type",
                    "required": False,
                    "in": "query",
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time for log range (ISO 8601)",
                    "required": False,
                    "in": "query",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time for log range (ISO 8601)",
                    "required": False,
                    "in": "query",
                },
            },
            risk_level="low",
            required_role=["admin"],
        ))

        self.register(ToolDefinition(
            name="system_health",
            description="Check system health status",
            endpoint="/api/v1/system/health",
            method="GET",
            parameters={},
            risk_level="low",
            required_role=["admin", "operator", "viewer"],
        ))

        self.register(ToolDefinition(
            name="navigate_to",
            description="Navigate to a specific page in the frontend UI",
            endpoint="",
            method="",
            parameters={
                "page": {
                    "type": "string",
                    "description": "The page path to navigate to",
                    "required": True,
                },
            },
            risk_level="low",
            required_role=["all"],
            is_frontend_action=True,
        ))

        self.register(ToolDefinition(
            name="highlight_node",
            description="Highlight a specific node in the topology view",
            endpoint="",
            method="",
            parameters={
                "node_id": {
                    "type": "string",
                    "description": "The ID of the topology node to highlight",
                    "required": True,
                },
            },
            risk_level="low",
            required_role=["all"],
            is_frontend_action=True,
        ))


_registry_instance: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
    return _registry_instance
