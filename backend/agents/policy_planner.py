from typing import Dict, Any, List, Optional
from backend.agents.base import IntentContext, NetworkState, DeviceInfo

class PolicyPlannerAgent:
    def __init__(self, llm=None):
        self.llm = llm
        
        self.config_templates = {
            "huawei": {
                "qos": {
                    "bandwidth_guarantee": """
# 华为设备QoS带宽保障配置
interface {interface}
 qos car inbound cir {cir} cbs {cbs} ebs {ebs} green pass yellow pass red discard
 qos gts outbound cir {cir} cbs {cbs}
""",
                    "traffic_limit": """
# 华为设备流量限制配置
interface {interface}
 qos car inbound cir {cir} cbs {cbs} ebs {ebs} green pass yellow pass red discard
"""
                }
            },
            "cisco": {
                "qos": {
                    "bandwidth_guarantee": """
! 思科设备QoS带宽保障配置
interface {interface}
 class-map match-all {class_name}
  match protocol {protocol}
 policy-map {policy_name}
  class {class_name}
   bandwidth percent {bandwidth_percent}
 service-policy output {policy_name}
""",
                    "traffic_limit": """
! 思科设备流量限制配置
interface {interface}
 rate-limit input {bps} burst-normal {burst} burst-max {burst_max}
"""
                }
            },
            "h3c": {
                "qos": {
                    "bandwidth_guarantee": """
# H3C设备QoS带宽保障配置
interface {interface}
 qos car inbound cir {cir} cbs {cbs} ebs {ebs} green pass yellow pass red discard
 qos gts outbound cir {cir} cbs {cbs}
"""
                }
            }
        }
    
    def generate(self, intent_context: IntentContext, network_state: NetworkState) -> Dict[str, Any]:
        actions = []
        
        intent_type = intent_context.parsed_intent.get("intent_type")
        target_subnet = intent_context.parsed_intent.get("target_subnet")
        bandwidth = intent_context.parsed_intent.get("bandwidth", 100)
        
        target_devices = self._find_target_devices(target_subnet, network_state)
        
        for device in target_devices:
            config = self._generate_device_config(device, intent_type, bandwidth)
            actions.append({
                "type": "config",
                "device": device.name,
                "device_ip": device.ip,
                "device_type": device.type,
                "commands": config,
                "priority": intent_context.parsed_intent.get("priority", "medium")
            })
        
        return {
            "actions": actions,
            "target_devices": [d.name for d in target_devices],
            "estimated_impact": len(target_devices)
        }
    
    def _find_target_devices(self, subnet: str, network_state: NetworkState) -> List[DeviceInfo]:
        if not subnet:
            return network_state.devices[:3]
        
        target_devices = []
        subnet_patterns = {
            "研发子网": ["dev", "研发", "development"],
            "生产子网": ["prod", "生产", "production"],
            "办公子网": ["office", "办公"],
            "测试子网": ["test", "测试"]
        }
        
        keywords = subnet_patterns.get(subnet, [subnet])
        
        for device in network_state.devices:
            device_name_lower = device.name.lower()
            if any(kw.lower() in device_name_lower for kw in keywords):
                target_devices.append(device)
        
        if not target_devices:
            target_devices = network_state.devices[:3]
        
        return target_devices
    
    def _generate_device_config(self, device: DeviceInfo, intent_type: str, bandwidth: int) -> List[str]:
        vendor = self._identify_vendor(device.type)
        
        if vendor not in self.config_templates:
            vendor = "huawei"
        
        template_key = self._get_template_key(intent_type)
        if not template_key:
            return []
        
        template = self.config_templates[vendor]["qos"].get(template_key, "")
        
        if not template:
            return self._generate_default_config(device, bandwidth)
        
        cir = bandwidth * 1000000
        cbs = cir * 2
        ebs = cir
        
        commands = template.format(
            interface="GigabitEthernet0/0/1",
            cir=cir,
            cbs=cbs,
            ebs=ebs,
            class_name=f"qos_{bandwidth}m",
            policy_name=f"policy_{bandwidth}m",
            bandwidth_percent=min(bandwidth, 50),
            protocol="tcp",
            bps=bandwidth * 1000000,
            burst=bandwidth * 1000,
            burst_max=bandwidth * 2000
        )
        
        return [line.strip() for line in commands.strip().split("\n") if line.strip()]
    
    def _identify_vendor(self, device_type: str) -> str:
        device_type = device_type.lower()
        if "huawei" in device_type or "huawei" in device_type:
            return "huawei"
        elif "cisco" in device_type:
            return "cisco"
        elif "h3c" in device_type or "h3c" in device_type:
            return "h3c"
        else:
            return "huawei"
    
    def _get_template_key(self, intent_type: str) -> Optional[str]:
        mapping = {
            "bandwidth_guarantee": "bandwidth_guarantee",
            "traffic_shaping": "traffic_limit",
            "qos_policy": "bandwidth_guarantee"
        }
        return mapping.get(intent_type)
    
    def _generate_default_config(self, device: DeviceInfo, bandwidth: int) -> List[str]:
        return [
            f"# 配置带宽保障 {bandwidth}M",
            f"interface GigabitEthernet0/0/1",
            f"qos cir {bandwidth}M",
            "commit"
        ]
    
    def adjust(self, intent_context: IntentContext, execution_results: List[Dict], network_state: NetworkState) -> Dict[str, Any]:
        failed_devices = [r["device"] for r in execution_results if r.get("status") == "failed"]
        
        original_plan = self.generate(intent_context, network_state)
        
        adjusted_actions = [
            action for action in original_plan["actions"]
            if action["device"] not in failed_devices
        ]
        
        for failed_device in failed_devices:
            adjusted_actions.append({
                "type": "config",
                "device": failed_device,
                "commands": ["# Fallback: 使用简化配置", "interface GigabitEthernet0/0/1", "qos enable"],
                "priority": "low"
            })
        
        return {
            "actions": adjusted_actions,
            "adjusted": len(failed_devices) > 0,
            "failed_devices": failed_devices
        }
