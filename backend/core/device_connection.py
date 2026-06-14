import asyncio
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ConnectionType(Enum):
    NETCONF = "netconf"
    SSH = "ssh"
    MOCK = "mock"


@dataclass
class DeviceConnection:
    device_id: str
    ip_address: str
    vendor: str
    port: int = 22
    username: str = "admin"
    password: str = ""
    connection_type: ConnectionType = ConnectionType.MOCK
    connected: bool = False
    last_used: Optional[datetime] = None

    def __repr__(self):
        return f"DeviceConnection(device_id={self.device_id!r}, ip_address={self.ip_address!r}, vendor={self.vendor!r}, connection_type={self.connection_type!r})"


class DeviceConnectionPool:
    def __init__(self):
        self._connections: Dict[str, DeviceConnection] = {}
        self._lock = asyncio.Lock()
        self._mock_mode = True

    def register_device(self, device_id: str, ip_address: str, vendor: str,
                        port: int = 22, username: str = "admin",
                        password: str = "", connection_type: str = "mock"):
        conn_type = ConnectionType(connection_type)
        self._connections[device_id] = DeviceConnection(
            device_id=device_id,
            ip_address=ip_address,
            vendor=vendor,
            port=port,
            username=username,
            password=password,
            connection_type=conn_type
        )
        logger.info(f"Registered device {device_id} at {ip_address}:{port} ({conn_type.value})")

    def set_mock_mode(self, enabled: bool):
        self._mock_mode = enabled
        logger.info(f"Mock mode {'enabled' if enabled else 'disabled'}")

    async def execute_command(self, device_id: str, commands: List[str],
                              timeout: int = 30) -> Dict[str, Any]:
        conn = self._connections.get(device_id)
        if not conn:
            return {"success": False, "error": f"Device {device_id} not registered",
                    "output": "", "device_id": device_id}

        if self._mock_mode or conn.connection_type == ConnectionType.MOCK:
            return await self._execute_mock(conn, commands)

        try:
            if conn.connection_type == ConnectionType.NETCONF:
                return await self._execute_netconf(conn, commands, timeout)
            elif conn.connection_type == ConnectionType.SSH:
                return await self._execute_ssh(conn, commands, timeout)
        except Exception as e:
            logger.warning(f"Connection failed for {device_id}, falling back to mock: {e}")
            return await self._execute_mock(conn, commands)

        return {"success": False, "error": "Unknown connection type", "output": "",
                "device_id": device_id}

    async def _execute_mock(self, conn: DeviceConnection,
                            commands: List[str]) -> Dict[str, Any]:
        await asyncio.sleep(0.3)
        outputs = []
        for cmd in commands:
            if "show interface" in cmd.lower() or "display interface" in cmd.lower():
                outputs.append(self._mock_interface_output(conn))
            elif "show version" in cmd.lower() or "display version" in cmd.lower():
                outputs.append(self._mock_version_output(conn))
            elif "show ip route" in cmd.lower() or "display ip routing" in cmd.lower():
                outputs.append(self._mock_route_output(conn))
            elif "ping" in cmd.lower():
                outputs.append(self._mock_ping_output(conn))
            else:
                outputs.append(f"[Mock] Command executed on {conn.device_id} ({conn.ip_address}): {cmd}\nOK")

        return {
            "success": True,
            "output": "\n".join(outputs),
            "device_id": conn.device_id,
            "mode": "mock",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def _execute_netconf(self, conn: DeviceConnection,
                                commands: List[str], timeout: int) -> Dict[str, Any]:
        try:
            from ncclient import manager
            hostkey_verify = not self._mock_mode
            with manager.connect(
                host=conn.ip_address,
                port=conn.port if conn.port != 22 else 830,
                username=conn.username,
                password=conn.password,
                hostkey_verify=hostkey_verify,
                timeout=timeout,
                device_params={"name": conn.vendor}
            ) as m:
                outputs = []
                for cmd in commands:
                    if cmd.strip().startswith("<"):
                        result = m.edit_config(target="running", config=cmd)
                        outputs.append(str(result))
                    else:
                        result = m.get(filter=cmd)
                        outputs.append(str(result))
                return {
                    "success": True,
                    "output": "\n".join(outputs),
                    "device_id": conn.device_id,
                    "mode": "netconf",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
        except ImportError:
            raise RuntimeError("ncclient not installed. Install with: pip install ncclient")
        except Exception as e:
            raise RuntimeError(f"NETCONF connection failed: {str(e)}")

    async def _execute_ssh(self, conn: DeviceConnection,
                            commands: List[str], timeout: int) -> Dict[str, Any]:
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.WarningPolicy())
            try:
                client.connect(
                    hostname=conn.ip_address,
                    port=conn.port,
                    username=conn.username,
                    password=conn.password,
                    timeout=timeout,
                    look_for_keys=False,
                    allow_agent=False
                )
                outputs = []
                for cmd in commands:
                    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
                    out = stdout.read().decode("utf-8", errors="replace")
                    err = stderr.read().decode("utf-8", errors="replace")
                    outputs.append(out if out else err)
                return {
                    "success": True,
                    "output": "\n".join(outputs),
                    "device_id": conn.device_id,
                    "mode": "ssh",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            finally:
                client.close()
        except ImportError:
            raise RuntimeError("paramiko not installed. Install with: pip install paramiko")
        except Exception as e:
            raise RuntimeError(f"SSH connection failed: {str(e)}")

    async def get_device_status(self, device_id: str) -> Dict[str, Any]:
        conn = self._connections.get(device_id)
        if not conn:
            return {"online": False, "error": "Device not registered"}

        if self._mock_mode or conn.connection_type == ConnectionType.MOCK:
            return {
                "online": True,
                "cpu_usage": 25.0 + (hash(device_id) % 40),
                "memory_usage": 30.0 + (hash(device_id) % 35),
                "uptime": "Mock uptime",
                "mode": "mock"
            }

        result = await self.execute_command(device_id, ["show version"])
        return {
            "online": result["success"],
            "mode": result.get("mode", "unknown"),
            "last_output": result.get("output", "")[:200]
        }

    def _mock_interface_output(self, conn: DeviceConnection) -> str:
        return f"""Interface List for {conn.device_id} ({conn.ip_address}):
GigabitEthernet0/0/1  up    up    10.0.0.1/24
GigabitEthernet0/0/2  up    up    10.0.1.1/24
GigabitEthernet0/0/3  down  down  unassigned
Loopback0             up    up    1.1.1.1/32"""

    def _mock_version_output(self, conn: DeviceConnection) -> str:
        vendor_os = {"huawei": "VRP", "cisco": "IOS-XE", "h3c": "Comware"}
        os_name = vendor_os.get(conn.vendor, "Unknown")
        return f"""{conn.device_id} ({conn.ip_address})
{os_name} Software, Version 8.1.0
Copyright (c) {conn.vendor.capitalize()}
Uptime: 45 days, 12 hours, 30 minutes"""

    def _mock_route_output(self, conn: DeviceConnection) -> str:
        return f"""Routing Table for {conn.device_id}:
10.0.0.0/24    Direct  GigabitEthernet0/0/1
10.0.1.0/24    Direct  GigabitEthernet0/0/2
0.0.0.0/0      Static  10.0.0.254"""

    def _mock_ping_output(self, conn: DeviceConnection) -> str:
        return f"""PING 10.0.0.1: 56 data bytes
Reply from 10.0.0.1: bytes=56 time=1ms TTL=255
Reply from 10.0.0.1: bytes=56 time=1ms TTL=255
--- 10.0.0.1 ping statistics ---
2 packets transmitted, 2 received, 0% packet loss"""


device_pool = DeviceConnectionPool()
