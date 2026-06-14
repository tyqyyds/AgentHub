import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from backend.core.device_connection import DeviceConnectionPool

logger = logging.getLogger(__name__)


class ToolExecutor:
    def __init__(self, device_pool: DeviceConnectionPool):
        self.device_pool = device_pool
        self._execution_history: List[Dict[str, Any]] = []
        self._max_history = 1000

    def _record_execution(self, result: Dict[str, Any]):
        self._execution_history.append(result)
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]

    def get_execution_history(self, tool_name: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        history = self._execution_history
        if tool_name:
            history = [h for h in history if h.get("tool_name") == tool_name]
        return history[-limit:]

    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        executor_map = {
            "show_interface": self._execute_show_interface,
            "config_qos": self._execute_config_qos,
            "ping": self._execute_ping,
            "config_acl": self._execute_config_acl,
            "get_device_status": self._execute_get_device_status,
            "optimize_route": self._execute_optimize_route,
            "failover_interface": self._execute_failover_interface,
            "config_load_balance": self._execute_config_load_balance,
            "optimize_resources": self._execute_optimize_resources,
        }

        handler = executor_map.get(tool_name)
        if handler:
            result = await handler(params)
        else:
            result = await self._execute_custom_tool(tool_name, params)

        result["tool_name"] = tool_name
        result["timestamp"] = datetime.now().isoformat()
        self._record_execution(result)
        return result

    async def _execute_show_interface(self, params: Dict[str, Any]) -> Dict[str, Any]:
        device = params.get("device", "")
        interface = params.get("interface", "")
        commands = [f"show interface {interface}".strip()] if interface else ["show interface"]
        try:
            exec_result = await self.device_pool.execute_command(device, commands)
            return {
                "status": "success",
                "device": device,
                "output": exec_result.get("outputs", []),
                "raw": exec_result
            }
        except Exception as e:
            return {"status": "error", "device": device, "error": str(e)}

    async def _execute_config_qos(self, params: Dict[str, Any]) -> Dict[str, Any]:
        device = params.get("device", "")
        class_name = params.get("class_name", "")
        bandwidth_percent = params.get("bandwidth_percent", "10")
        commands = [
            f"traffic-policy {class_name}",
            f"qos car cir {bandwidth_percent} pir {int(bandwidth_percent) * 2 if bandwidth_percent.isdigit() else 20}"
        ]
        try:
            exec_result = await self.device_pool.execute_command(device, commands)
            return {
                "status": "success",
                "device": device,
                "commands_sent": commands,
                "output": exec_result.get("outputs", []),
                "raw": exec_result
            }
        except Exception as e:
            return {"status": "error", "device": device, "error": str(e)}

    async def _execute_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        target = params.get("target", "")
        count = params.get("count", "4")
        commands = [f"ping {target} count {count}"]
        try:
            exec_result = await self.device_pool.execute_command("local", commands)
            return {
                "status": "success",
                "target": target,
                "output": exec_result.get("outputs", []),
                "raw": exec_result
            }
        except Exception as e:
            return {"status": "error", "target": target, "error": str(e)}

    async def _execute_config_acl(self, params: Dict[str, Any]) -> Dict[str, Any]:
        device = params.get("device", "")
        acl_name = params.get("acl_name", "")
        action = params.get("action", "permit")
        protocol = params.get("protocol", "ip")
        source = params.get("source", "any")
        destination = params.get("destination", "any")
        commands = [
            f"acl {acl_name}",
            f"rule {action} {protocol} source {source} destination {destination}"
        ]
        try:
            exec_result = await self.device_pool.execute_command(device, commands)
            return {
                "status": "success",
                "device": device,
                "commands_sent": commands,
                "output": exec_result.get("outputs", []),
                "raw": exec_result
            }
        except Exception as e:
            return {"status": "error", "device": device, "error": str(e)}

    async def _execute_get_device_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        device = params.get("device", "")
        commands = ["show version", "show cpu", "show memory"]
        try:
            exec_result = await self.device_pool.execute_command(device, commands)
            return {
                "status": "success",
                "device": device,
                "output": exec_result.get("outputs", []),
                "raw": exec_result
            }
        except Exception as e:
            return {"status": "error", "device": device, "error": str(e)}

    async def _execute_custom_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        device = params.get("device", "")
        commands = params.get("commands", [])
        if not commands:
            return {"status": "error", "error": f"工具 '{tool_name}' 未注册，且未提供 commands 参数"}
        try:
            exec_result = await self.device_pool.execute_command(device, commands)
            return {
                "status": "success",
                "device": device,
                "tool_name": tool_name,
                "commands_sent": commands,
                "output": exec_result.get("outputs", []),
                "raw": exec_result
            }
        except Exception as e:
            return {"status": "error", "device": device, "tool_name": tool_name, "error": str(e)}

    async def _execute_optimize_route(self, params: Dict[str, Any]) -> Dict[str, Any]:
        device = params.get("device", "")
        destination = params.get("destination", "")
        metric = params.get("metric", "10")
        commands = [
            f"ip route {destination} metric {metric}" if destination else "show ip route",
            "clear ip route *"
        ]
        try:
            exec_result = await self.device_pool.execute_command(device, commands)
            return {
                "status": "success",
                "device": device,
                "action": "route_optimization",
                "commands_sent": commands,
                "output": exec_result.get("outputs", []),
                "raw": exec_result
            }
        except Exception as e:
            return {"status": "error", "device": device, "action": "route_optimization", "error": str(e)}

    async def _execute_failover_interface(self, params: Dict[str, Any]) -> Dict[str, Any]:
        device = params.get("device", "")
        primary_interface = params.get("primary_interface", "")
        backup_interface = params.get("backup_interface", "")
        commands = []
        if primary_interface and backup_interface:
            commands = [
                f"interface {primary_interface}",
                "shutdown",
                f"interface {backup_interface}",
                "no shutdown"
            ]
        else:
            commands = ["show interface brief"]
        try:
            exec_result = await self.device_pool.execute_command(device, commands)
            return {
                "status": "success",
                "device": device,
                "action": "interface_failover",
                "primary": primary_interface,
                "backup": backup_interface,
                "commands_sent": commands,
                "output": exec_result.get("outputs", []),
                "raw": exec_result
            }
        except Exception as e:
            return {"status": "error", "device": device, "action": "interface_failover", "error": str(e)}

    async def _execute_config_load_balance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        device = params.get("device", "")
        algorithm = params.get("algorithm", "per-destination")
        interfaces = params.get("interfaces", [])
        commands = [
            f"ip load-sharing {algorithm}",
        ]
        if interfaces:
            for iface in interfaces:
                commands.append(f"interface {iface}")
                commands.append("no shutdown")
        try:
            exec_result = await self.device_pool.execute_command(device, commands)
            return {
                "status": "success",
                "device": device,
                "action": "load_balancing",
                "algorithm": algorithm,
                "commands_sent": commands,
                "output": exec_result.get("outputs", []),
                "raw": exec_result
            }
        except Exception as e:
            return {"status": "error", "device": device, "action": "load_balancing", "error": str(e)}

    async def _execute_optimize_resources(self, params: Dict[str, Any]) -> Dict[str, Any]:
        device = params.get("device", "")
        action = params.get("resource_action", "cleanup")
        commands = []
        if action == "cleanup":
            commands = [
                "clear arp-cache",
                "clear ip cache",
                "clear logging"
            ]
        elif action == "adjust":
            cpu_threshold = params.get("cpu_threshold", "80")
            mem_threshold = params.get("mem_threshold", "80")
            commands = [
                f"process cpu threshold {cpu_threshold}",
                f"memory reserve critical {mem_threshold}"
            ]
        else:
            commands = ["show resource"]
        try:
            exec_result = await self.device_pool.execute_command(device, commands)
            return {
                "status": "success",
                "device": device,
                "action": f"resource_{action}",
                "commands_sent": commands,
                "output": exec_result.get("outputs", []),
                "raw": exec_result
            }
        except Exception as e:
            return {"status": "error", "device": device, "action": f"resource_{action}", "error": str(e)}


tool_executor: Optional[ToolExecutor] = None


def get_tool_executor() -> ToolExecutor:
    global tool_executor
    if tool_executor is None:
        device_pool = DeviceConnectionPool()
        tool_executor = ToolExecutor(device_pool)
    return tool_executor
