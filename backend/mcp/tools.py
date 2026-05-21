from typing import Any, Dict, List
from langchain.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

class ShowInterfaceInput(BaseModel):
    device: str = Field(description="目标设备名称")
    interface: str = Field(description="接口名称")

class ShowInterfaceTool(BaseTool):
    name = "show_interface"
    description = "显示网络设备接口状态"
    args_schema = ShowInterfaceInput
    
    def _run(self, device: str, interface: str) -> Dict:
        return {
            "device": device,
            "interface": interface,
            "status": "up",
            "protocol": "up",
            "ip_address": "192.168.1.1",
            "subnet_mask": "255.255.255.0",
            "bandwidth": "10000000",
            "input_errors": 0,
            "output_errors": 0
        }

class ConfigQoSInput(BaseModel):
    device: str = Field(description="目标设备名称")
    class_name: str = Field(description="QoS类名")
    bandwidth_percent: int = Field(description="带宽百分比")

class ConfigQoSTool(BaseTool):
    name = "config_qos"
    description = "配置QoS策略"
    args_schema = ConfigQoSInput
    
    def _run(self, device: str, class_name: str, bandwidth_percent: int) -> Dict:
        return {
            "status": "success",
            "device": device,
            "message": f"QoS策略 {class_name} 配置成功，带宽百分比: {bandwidth_percent}%"
        }

class PingInput(BaseModel):
    target: str = Field(description="目标IP地址或主机名")
    count: int = Field(description="ping次数", default=4)

class PingTool(BaseTool):
    name = "ping"
    description = "执行网络连通性测试"
    args_schema = PingInput
    
    def _run(self, target: str, count: int = 4) -> Dict:
        return {
            "target": target,
            "count": count,
            "packets_sent": count,
            "packets_received": count,
            "packet_loss": 0,
            "rtt_min": 1,
            "rtt_avg": 3,
            "rtt_max": 5
        }

class ConfigACLInput(BaseModel):
    device: str = Field(description="目标设备名称")
    acl_name: str = Field(description="ACL名称")
    action: str = Field(description="动作: permit或deny")
    protocol: str = Field(description="协议")
    source: str = Field(description="源地址")
    destination: str = Field(description="目标地址")

class ConfigACLTool(BaseTool):
    name = "config_acl"
    description = "配置ACL规则"
    args_schema = ConfigACLInput
    
    def _run(self, device: str, acl_name: str, action: str, protocol: str, source: str, destination: str) -> Dict:
        return {
            "status": "success",
            "device": device,
            "message": f"ACL规则 {acl_name} 配置成功"
        }

class GetDeviceStatusInput(BaseModel):
    device: str = Field(description="目标设备名称")

class GetDeviceStatusTool(BaseTool):
    name = "get_device_status"
    description = "获取设备状态"
    args_schema = GetDeviceStatusInput
    
    def _run(self, device: str) -> Dict:
        return {
            "device": device,
            "status": "online",
            "cpu_usage": 45,
            "memory_usage": 62,
            "uptime": "5 days, 12 hours",
            "last_reboot": "2026-05-15 08:00:00"
        }

def get_mcp_tools() -> List[BaseTool]:
    return [
        ShowInterfaceTool(),
        ConfigQoSTool(),
        PingTool(),
        ConfigACLTool(),
        GetDeviceStatusTool()
    ]