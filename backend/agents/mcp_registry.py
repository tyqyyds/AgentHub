from typing import Dict, Any, List, Optional, Callable
from backend.agents.base import ToolDescription, A2AMessage
from datetime import datetime
import json
import os
from collections import defaultdict

class MCPRegistry:
    def __init__(self):
        self.tools: Dict[str, ToolDescription] = {}
        self.capability_index: Dict[str, List[str]] = defaultdict(list)
        self.semantic_index: Dict[str, List[Dict[str, Any]]] = {}
        self._load_tools()
    
    def _load_tools(self):
        if os.path.exists("data/mcp_tools.json"):
            with open("data/mcp_tools.json", "r") as f:
                data = json.load(f)
                for tool_name, tool_data in data.items():
                    self.tools[tool_name] = ToolDescription(**tool_data)
    
    def _save_tools(self):
        os.makedirs("data", exist_ok=True)
        with open("data/mcp_tools.json", "w") as f:
            data = {k: v.dict() for k, v in self.tools.items()}
            json.dump(data, f, indent=2)
    
    def register_tool(self, tool: ToolDescription) -> bool:
        if tool.name in self.tools:
            raise ValueError(f"工具 {tool.name} 已存在")
        
        self.tools[tool.name] = tool
        
        description = tool.description.lower()
        for word in description.split():
            if len(word) > 2:
                self.semantic_index[word].append({
                    "tool_name": tool.name,
                    "score": 1.0
                })
        
        for device in tool.supported_devices:
            self.capability_index[device.lower()].append(tool.name)
        
        self._save_tools()
        return True
    
    def unregister_tool(self, tool_name: str) -> bool:
        if tool_name not in self.tools:
            return False
        
        tool = self.tools.pop(tool_name)
        
        description = tool.description.lower()
        for word in description.split():
            if len(word) > 2:
                self.semantic_index[word] = [
                    t for t in self.semantic_index[word]
                    if t["tool_name"] != tool_name
                ]
        
        self._save_tools()
        return True
    
    def semantic_search(self, query: str) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        results = {}
        
        for word in query_lower.split():
            if len(word) > 1 and word in self.semantic_index:
                for tool_entry in self.semantic_index[word]:
                    tool_name = tool_entry["tool_name"]
                    if tool_name not in results:
                        results[tool_name] = 0
                    results[tool_name] += 1
        
        sorted_results = sorted(
            results.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        final_results = []
        for tool_name, score in sorted_results[:10]:
            tool = self.tools.get(tool_name)
            if tool:
                final_results.append({
                    "tool": tool.dict(),
                    "similarity_score": min(score / len(query_lower.split()), 1.0)
                })
        
        return final_results
    
    def get_tool(self, tool_name: str) -> Optional[ToolDescription]:
        return self.tools.get(tool_name)
    
    def list_tools(self) -> List[ToolDescription]:
        return list(self.tools.values())
    
    def get_tools_by_device(self, device_type: str) -> List[ToolDescription]:
        tool_names = self.capability_index.get(device_type.lower(), [])
        return [self.tools.get(name) for name in tool_names if self.tools.get(name)]

class MCPToolRouter:
    def __init__(self, mcp_registry: MCPRegistry, a2a_bus):
        self.mcp_registry = mcp_registry
        self.a2a_bus = a2a_bus
        self.routing_rules = [
            self._route_by_intent_type,
            self._route_by_device_type,
            self._route_by_semantic
        ]
    
    def route(self, intent_context: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        for rule in self.routing_rules:
            result = rule(intent_context, context)
            if result.get("tools"):
                return result
        
        return self._route_by_semantic(intent_context, context)
    
    def _route_by_intent_type(self, intent: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        intent_type = intent.get("intent_type")
        
        type_mapping = {
            "bandwidth_guarantee": ["qos_config", "bandwidth_manager"],
            "access_control": ["acl_config", "firewall_manager"],
            "link_management": ["link_status", "route_config"],
            "fault_diagnosis": ["ping", "traceroute", "show_interface"]
        }
        
        tools = type_mapping.get(intent_type, [])
        tool_objects = []
        
        for tool_name in tools:
            tool = self.mcp_registry.get_tool(tool_name)
            if tool:
                tool_objects.append(tool.dict())
        
        return {
            "tools": tool_objects,
            "strategy": "intent_type",
            "confidence": 0.8
        }
    
    def _route_by_device_type(self, intent: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        device_type = context.get("device_type") if context else None
        
        if not device_type:
            return {"tools": []}
        
        tools = self.mcp_registry.get_tools_by_device(device_type)
        
        return {
            "tools": [t.dict() for t in tools],
            "strategy": "device_type",
            "confidence": 0.7
        }
    
    def _route_by_semantic(self, intent: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        user_input = intent.get("user_input", "")
        
        results = self.mcp_registry.semantic_search(user_input)
        
        return {
            "tools": [r["tool"] for r in results],
            "strategy": "semantic",
            "confidence": results[0]["similarity_score"] if results else 0.0
        }
    
    def route_to_chain(self, intent_context: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        from backend.agents.tool_chains import ToolChainRegistry

        chain_registry = ToolChainRegistry()
        intent_type = intent_context.get("intent_type", "")
        user_input = intent_context.get("user_input", "")

        chain_mapping = {
            "fault_diagnosis": "fault_auto_healing",
            "self_healing": "fault_auto_healing",
            "inspection": "batch_inspection",
            "daily_check": "batch_inspection",
            "config_change": "change_verification",
            "change_implementation": "change_verification"
        }

        chain_id = chain_mapping.get(intent_type)
        if chain_id:
            chain = chain_registry.get_chain(chain_id)
            if chain:
                return {
                    "type": "tool_chain",
                    "chain_id": chain_id,
                    "chain": chain.model_dump(),
                    "strategy": "intent_chain_mapping",
                    "confidence": 0.85
                }

        fault_keywords = ["故障", "自愈", "healing", "fault", "中断", "宕机"]
        inspect_keywords = ["巡检", "检查", "inspection", "健康", "health"]
        change_keywords = ["变更", "配置修改", "change", "升级"]

        for keyword in fault_keywords:
            if keyword in user_input.lower():
                chain = chain_registry.get_chain("fault_auto_healing")
                if chain:
                    return {"type": "tool_chain", "chain_id": "fault_auto_healing", "chain": chain.model_dump(), "strategy": "keyword_matching", "confidence": 0.7}

        for keyword in inspect_keywords:
            if keyword in user_input.lower():
                chain = chain_registry.get_chain("batch_inspection")
                if chain:
                    return {"type": "tool_chain", "chain_id": "batch_inspection", "chain": chain.model_dump(), "strategy": "keyword_matching", "confidence": 0.7}

        for keyword in change_keywords:
            if keyword in user_input.lower():
                chain = chain_registry.get_chain("change_verification")
                if chain:
                    return {"type": "tool_chain", "chain_id": "change_verification", "chain": chain.model_dump(), "strategy": "keyword_matching", "confidence": 0.7}

        return {"type": "single_tool", "tools": [], "strategy": "no_chain_match", "confidence": 0.0}

    async def execute_routed_tool(self, tool_name: str, params: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        tool = self.mcp_registry.get_tool(tool_name)
        if not tool:
            return {"error": f"工具 {tool_name} 不存在"}
        
        if tool.requires_context and context:
            params["context"] = context
        
        message = A2AMessage(
            message_id=f"req_{datetime.now().timestamp()}",
            sender_id="mcp_tool_router",
            receiver_id=None,
            message_type="tool_execution",
            content={
                "tool_name": tool_name,
                "params": params,
                "context": context
            },
            timestamp=datetime.now().isoformat()
        )
        
        self.a2a_bus.publish("tool_execution", message.dict())
        
        return {"status": "executing", "tool_name": tool_name}
