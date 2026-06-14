import asyncio
import websockets
import json
import paramiko
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EdgeAgent")

class EdgeAgent:
    def __init__(self, agent_id: str, server_url: str = "ws://localhost:8000/ws", token: str = ""):
        self.agent_id = agent_id
        self.server_url = server_url
        self.token = token
        self.websocket = None
        self.device_connections: Dict[str, paramiko.SSHClient] = {}
        self.running = False
        self.reconnect_delay = 5

    async def connect(self):
        while self.running:
            try:
                ws_url = f"{self.server_url}?token={self.token}" if self.token else self.server_url
                async with websockets.connect(ws_url) as websocket:
                    self.websocket = websocket
                    logger.info(f"Edge Agent {self.agent_id} 已连接到中心端")
                    
                    await self.send_hello()
                    
                    async for message in websocket:
                        await self.handle_message(message)
                    
            except websockets.exceptions.ConnectionClosed:
                logger.warning("连接断开，准备重连")
            except Exception as e:
                logger.error(f"连接错误: {e}")
            
            await asyncio.sleep(self.reconnect_delay)

    async def send_hello(self):
        hello_msg = {
            "type": "agent_hello",
            "agent_id": self.agent_id,
            "capabilities": ["ssh", "netconf", "telnet"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.websocket.send(json.dumps(hello_msg))

    async def handle_message(self, message: str):
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "execute_command":
                await self.execute_command(data)
            elif message_type == "get_device_info":
                await self.get_device_info(data)
            elif message_type == "health_check":
                await self.send_health_check()
            else:
                logger.warning(f"未知消息类型: {message_type}")
                
        except json.JSONDecodeError:
            logger.error("无法解析消息")

    async def execute_command(self, data: Dict[str, Any]):
        device_id = data.get("device_id")
        commands = data.get("commands", [])
        task_id = data.get("task_id")
        
        result = {
            "type": "command_result",
            "task_id": task_id,
            "device_id": device_id,
            "agent_id": self.agent_id,
            "results": [],
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        try:
            ssh_client = await self.get_ssh_connection(device_id)
            
            for cmd in commands:
                try:
                    stdin, stdout, stderr = ssh_client.exec_command(cmd)
                    output = stdout.read().decode("utf-8")
                    error = stderr.read().decode("utf-8")
                    
                    result["results"].append({
                        "command": cmd,
                        "output": output,
                        "error": error,
                        "success": not error
                    })
                    
                    if error:
                        result["success"] = False
                        
                except Exception as e:
                    result["results"].append({
                        "command": cmd,
                        "output": "",
                        "error": str(e),
                        "success": False
                    })
                    result["success"] = False

        except Exception as e:
            result["success"] = False
            result["results"].append({
                "command": "",
                "output": "",
                "error": f"连接设备失败: {e}",
                "success": False
            })

        await self.send_message(result)

    async def get_ssh_connection(self, device_id: str) -> paramiko.SSHClient:
        if device_id in self.device_connections:
            return self.device_connections[device_id]

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        device_config = self.get_device_config(device_id)
        
        ssh.connect(
            hostname=device_config["host"],
            port=device_config.get("port", 22),
            username=device_config["username"],
            password=device_config.get("password"),
            key_filename=device_config.get("key_filename"),
            timeout=10
        )
        
        self.device_connections[device_id] = ssh
        return ssh

    def get_device_config(self, device_id: str) -> Dict[str, Any]:
        return {
            "host": device_id,
            "username": "admin",
            "password": "password",
            "port": 22
        }

    async def get_device_info(self, data: Dict[str, Any]):
        device_id = data.get("device_id")
        task_id = data.get("task_id")

        result = {
            "type": "device_info",
            "task_id": task_id,
            "device_id": device_id,
            "agent_id": self.agent_id,
            "info": {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        try:
            ssh = await self.get_ssh_connection(device_id)
            stdin, stdout, stderr = ssh.exec_command("show version")
            version_info = stdout.read().decode("utf-8")
            
            stdin, stdout, stderr = ssh.exec_command("show ip interface brief")
            interface_info = stdout.read().decode("utf-8")

            result["info"] = {
                "version": version_info[:500],
                "interfaces": interface_info[:1000]
            }

        except Exception as e:
            result["info"] = {"error": str(e)}

        await self.send_message(result)

    async def send_health_check(self):
        health = {
            "type": "agent_health",
            "agent_id": self.agent_id,
            "status": "healthy",
            "active_connections": len(self.device_connections),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.send_message(health)

    async def send_message(self, message: Dict[str, Any]):
        if self.websocket:
            await self.websocket.send(json.dumps(message))

    async def start(self):
        self.running = True
        await self.connect()

    async def stop(self):
        self.running = False
        for conn in self.device_connections.values():
            conn.close()
        self.device_connections.clear()

if __name__ == "__main__":
    agent = EdgeAgent(agent_id="edge-agent-001")
    asyncio.run(agent.start())