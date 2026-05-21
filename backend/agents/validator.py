from typing import List, Dict
import re

class ValidatorAgent:
    def __init__(self):
        self.patterns = {
            "ip_address": r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$",
            "subnet_mask": r"^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$",
            "bandwidth": r"^\d+[kmgKMG]?$",
            "interface": r"^[A-Za-z]+\d+(/\d+)?(/\d+)?$"
        }
    
    def _validate_ip(self, ip: str) -> bool:
        if not re.match(self.patterns["ip_address"], ip):
            return False
        
        parts = list(map(int, ip.split(".")))
        return all(0 <= part <= 255 for part in parts)
    
    def _validate_subnet_mask(self, mask: str) -> bool:
        if not self._validate_ip(mask):
            return False
        
        binary = "".join(f"{int(octet):08b}" for octet in mask.split("."))
        return binary.count("0") == binary.count("0", binary.find("0")) if "0" in binary else True
    
    def _validate_command_syntax(self, command: str) -> bool:
        valid_commands = [
            "class-map", "policy-map", "bandwidth", "ip access-list",
            "permit", "deny", "interface", "ip address", "ip route"
        ]
        
        return any(cmd.lower() in command.lower() for cmd in valid_commands)
    
    def _check_conflicts(self, commands: List[str], intent: Dict) -> List[str]:
        conflicts = []
        
        if "acl" in intent.get("intent_name", "").lower():
            for cmd in commands:
                if "permit" in cmd.lower() and "any" in cmd.lower():
                    conflicts.append("检测到允许所有流量的ACL规则，存在安全风险")
        
        return conflicts
    
    async def validate(self, commands: List[str], intent: Dict) -> Dict:
        errors = []
        warnings = []
        requires_approval = True
        
        for cmd in commands:
            if not self._validate_command_syntax(cmd):
                errors.append(f"命令语法无效: {cmd}")
            
            for part in cmd.split():
                if self._validate_ip(part):
                    if not self._validate_ip(part):
                        errors.append(f"无效的IP地址: {part}")
                elif "/" in part:
                    parts = part.split("/")
                    if len(parts) == 2 and parts[1].isdigit():
                        if not (0 <= int(parts[1]) <= 32):
                            errors.append(f"无效的子网掩码位数: {part}")
        
        conflicts = self._check_conflicts(commands, intent)
        warnings.extend(conflicts)
        
        if errors:
            return {
                "status": "error",
                "requires_approval": False,
                "errors": errors,
                "warnings": warnings
            }
        
        if warnings:
            return {
                "status": "warning",
                "requires_approval": True,
                "errors": errors,
                "warnings": warnings
            }
        
        if intent.get("intent_name") in ["bandwidth_guarantee", "simple_config"]:
            return {
                "status": "auto_approve",
                "requires_approval": False,
                "errors": errors,
                "warnings": warnings
            }
        
        return {
            "status": "success",
            "requires_approval": True,
            "errors": errors,
            "warnings": warnings
        }