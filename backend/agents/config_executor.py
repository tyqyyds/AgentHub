from typing import List
import asyncio

class ConfigExecutorAgent:
    def __init__(self):
        self.simulated_devices = {
            "Switch-A1": {"status": "online", "type": "switch"},
            "Switch-A2": {"status": "online", "type": "switch"},
            "Router-C1": {"status": "online", "type": "router"},
            "Firewall-B1": {"status": "online", "type": "firewall"}
        }
    
    async def _send_commands(self, device: str, commands: List[str]) -> bool:
        await asyncio.sleep(1)
        
        if device not in self.simulated_devices:
            return False
        
        if self.simulated_devices[device]["status"] != "online":
            return False
        
        return True
    
    async def _execute_dry_run(self, commands: List[str]) -> dict:
        await asyncio.sleep(0.5)
        return {
            "success": True,
            "warnings": [],
            "errors": []
        }
    
    async def execute(self, commands: List[str]) -> str:
        if not commands:
            return "failed"
        
        dry_run_result = await self._execute_dry_run(commands)
        if not dry_run_result["success"]:
            return "dry_run_failed"
        
        for device in self.simulated_devices.keys():
            success = await self._send_commands(device, commands)
            if not success:
                return "partial_failure"
        
        return "success"