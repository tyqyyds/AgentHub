from jinja2 import Environment, BaseLoader
from typing import List, Dict
import json

class ConfigGeneratorAgent:
    def __init__(self):
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, str]:
        return {
            "qos_bandwidth": """class-map match-any {{class_name}}
  match protocol video
policy-map {{policy_name}}
  class {{class_name}}
    bandwidth percent {{bandwidth_percent}}""",
            
            "acl_allow": """ip access-list extended {{acl_name}}
  permit ip {{source}} {{source_mask}} {{destination}} {{destination_mask}}""",
            
            "interface_config": """interface {{interface}}
  ip address {{ip_address}} {{subnet_mask}}
  no shutdown""",
            
            "route_static": """ip route {{destination}} {{mask}} {{next_hop}}"""
        }
    
    def _match_template(self, intent: Dict) -> str:
        intent_name = intent.get("intent_name", "")
        
        if "bandwidth" in intent_name.lower():
            return "qos_bandwidth"
        elif "access" in intent_name.lower() or "acl" in intent_name.lower():
            return "acl_allow"
        elif "interface" in intent_name.lower():
            return "interface_config"
        elif "route" in intent_name.lower():
            return "route_static"
        
        return "qos_bandwidth"
    
    def _extract_params(self, intent: Dict) -> Dict:
        params = {}
        
        if intent.get("targets"):
            params["target"] = intent["targets"][0]
        
        for action in intent.get("actions", []):
            params.update(action.get("params", {}))
        
        return params
    
    async def generate(self, intent: Dict) -> List[str]:
        template_name = self._match_template(intent)
        template_content = self.templates.get(template_name, "")
        
        if not template_content:
            return []
        
        params = self._extract_params(intent)
        params.setdefault("class_name", "VIDEO_TRAFFIC")
        params.setdefault("policy_name", "QOS_POLICY")
        params.setdefault("bandwidth_percent", "20")
        params.setdefault("acl_name", "ALLOW_ACCESS")
        params.setdefault("source", "192.168.1.0")
        params.setdefault("source_mask", "0.0.0.255")
        params.setdefault("destination", "10.0.0.0")
        params.setdefault("destination_mask", "0.255.255.255")
        
        env = Environment(loader=BaseLoader())
        template = env.from_string(template_content)
        config = template.render(params)
        
        return [line.strip() for line in config.split("\n") if line.strip()]
