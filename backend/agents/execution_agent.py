import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """执行结果"""
    device: str
    success: bool
    commands_executed: List[str] = field(default_factory=list)
    output: str = ""
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class ExecutionAgentConfig:
    """执行Agent配置"""
    dry_run_by_default: bool = True
    command_timeout_seconds: int = 30
    max_retries: int = 2
    batch_size: int = 5
    rollback_on_failure: bool = True


class ExecutionAgent:
    """执行Agent：配置下发、命令执行、结果收集"""

    def __init__(self, config: Optional[ExecutionAgentConfig] = None):
        self.config = config or ExecutionAgentConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._device_connections: Dict[str, Dict[str, Any]] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._simulated_devices = self._init_simulated_devices()

    def _init_simulated_devices(self) -> Dict[str, Dict[str, Any]]:
        """初始化模拟设备"""
        return {
            "Switch-A1": {"status": "online", "type": "switch", "vendor": "华为"},
            "Switch-A2": {"status": "online", "type": "switch", "vendor": "新华三"},
            "Router-C1": {"status": "online", "type": "router", "vendor": "华为"},
            "Router-C2": {"status": "online", "type": "router", "vendor": "中兴"},
            "Firewall-B1": {"status": "online", "type": "firewall", "vendor": "华为"},
            "Firewall-B2": {"status": "maintenance", "type": "firewall", "vendor": "锐捷"},
        }

    async def _connect_device(self, device_name: str) -> bool:
        """连接设备"""
        if device_name in self._device_connections:
            return True

        device = self._simulated_devices.get(device_name)
        if not device or device["status"] != "online":
            self.logger.warning(f"设备不可达: {device_name}")
            return False

        await asyncio.sleep(0.1)
        self._device_connections[device_name] = {
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "device_info": device,
        }
        self.logger.info(f"设备已连接: {device_name}")
        return True

    async def _disconnect_device(self, device_name: str) -> None:
        """断开设备连接"""
        self._device_connections.pop(device_name, None)

    async def _execute_single_command(
        self, device_name: str, command: str, dry_run: bool = False
    ) -> ExecutionResult:
        """执行单条命令"""
        start_time = datetime.now(timezone.utc)

        if dry_run:
            await asyncio.sleep(0.05)
            return ExecutionResult(
                device=device_name,
                success=True,
                commands_executed=[command],
                output=f"[DRY-RUN] {command}",
                duration_ms=50,
            )

        connected = await self._connect_device(device_name)
        if not connected:
            return ExecutionResult(
                device=device_name,
                success=False,
                error=f"无法连接设备: {device_name}",
            )

        await asyncio.sleep(0.2)

        dangerous_keywords = ["delete", "erase", "format", "reload", "reset"]
        is_dangerous = any(kw in command.lower() for kw in dangerous_keywords)

        if is_dangerous:
            self.logger.warning(f"检测到危险命令: {command}")
            return ExecutionResult(
                device=device_name,
                success=False,
                commands_executed=[],
                error=f"危险命令被拦截: {command}",
            )

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        return ExecutionResult(
            device=device_name,
            success=True,
            commands_executed=[command],
            output=f"OK: {command[:50]}...",
            duration_ms=int(elapsed),
        )

    async def _execute_on_device(
        self, device_name: str, commands: List[str], dry_run: bool = False
    ) -> List[ExecutionResult]:
        """在单个设备上执行命令列表"""
        results = []
        for cmd in commands:
            for attempt in range(self.config.max_retries + 1):
                result = await self._execute_single_command(device_name, cmd, dry_run)
                if result.success:
                    results.append(result)
                    break
                elif attempt < self.config.max_retries:
                    self.logger.info(f"重试命令 ({attempt + 1}/{self.config.max_retries}): {cmd}")
                    await asyncio.sleep(1)
                else:
                    results.append(result)
                    if self.config.rollback_on_failure:
                        self.logger.warning(f"命令执行失败，触发回滚: {device_name}")
                        rollback_results = await self._rollback_device(device_name, results)
                        results.extend(rollback_results)
                    break
        return results

    async def _rollback_device(
        self, device_name: str, executed_results: List[ExecutionResult]
    ) -> List[ExecutionResult]:
        """回滚设备配置"""
        rollback_results = []
        successful_cmds = [r for r in executed_results if r.success]

        for result in reversed(successful_cmds):
            for cmd in result.commands_executed:
                rollback_cmd = self._generate_rollback_command(cmd)
                if rollback_cmd:
                    rb_result = await self._execute_single_command(
                        device_name, rollback_cmd, dry_run=False
                    )
                    rollback_results.append(rb_result)

        self.logger.info(f"设备 {device_name} 回滚完成, 回滚命令数: {len(rollback_results)}")
        return rollback_results

    def _generate_rollback_command(self, command: str) -> Optional[str]:
        """生成回滚命令"""
        if command.startswith("no "):
            return command[3:]
        elif "access-list" in command and "permit" in command:
            return command.replace("permit", "deny", 1)
        elif "bandwidth" in command:
            return f"no {command}"
        elif "ip route" in command:
            return f"no {command}"
        elif "policy-map" in command:
            return f"no {command}"
        return f"no {command}"

    async def _batch_execute(
        self, devices: List[str], commands: List[str], dry_run: bool = False
    ) -> Dict[str, List[ExecutionResult]]:
        """批量执行"""
        results = {}
        for i in range(0, len(devices), self.config.batch_size):
            batch = devices[i:i + self.config.batch_size]
            coros = [self._execute_on_device(dev, commands, dry_run) for dev in batch]
            batch_results = await asyncio.gather(*coros, return_exceptions=True)

            for dev, dev_results in zip(batch, batch_results):
                if isinstance(dev_results, Exception):
                    results[dev] = [ExecutionResult(
                        device=dev, success=False, error=str(dev_results)
                    )]
                else:
                    results[dev] = dev_results

        return results

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行配置下发"""
        commands = input_data.get("commands", [])
        devices = input_data.get("devices", list(self._simulated_devices.keys()))
        dry_run = input_data.get("dry_run", self.config.dry_run_by_default)

        if not commands:
            return {
                "status": "failed",
                "error": "无执行命令",
                "results": [],
            }

        self.logger.info(
            f"执行请求: 设备数={len(devices)}, 命令数={len(commands)}, "
            f"dry_run={dry_run}"
        )

        if len(devices) == 1:
            device_results = await self._execute_on_device(devices[0], commands, dry_run)
            all_results = {devices[0]: device_results}
        else:
            all_results = await self._batch_execute(devices, commands, dry_run)

        total_executed = sum(len(r) for r in all_results.values())
        total_success = sum(
            1 for results in all_results.values()
            for r in results if r.success
        )
        total_failed = total_executed - total_success

        execution_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "devices": len(devices),
            "commands": len(commands),
            "dry_run": dry_run,
            "total_executed": total_executed,
            "success_count": total_success,
            "failed_count": total_failed,
        }
        self._execution_history.append(execution_record)

        result = {
            "status": "success" if total_failed == 0 else "partial_failure",
            "dry_run": dry_run,
            "total_executed": total_executed,
            "success_count": total_success,
            "failed_count": total_failed,
            "device_results": {
                dev: [
                    {
                        "success": r.success,
                        "commands": r.commands_executed,
                        "output": r.output,
                        "error": r.error,
                        "duration_ms": r.duration_ms,
                    }
                    for r in results
                ]
                for dev, results in all_results.items()
            },
        }

        return result

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        online_devices = sum(
            1 for d in self._simulated_devices.values() if d["status"] == "online"
        )
        return {
            "status": "healthy",
            "agent": self.__class__.__name__,
            "total_devices": len(self._simulated_devices),
            "online_devices": online_devices,
            "active_connections": len(self._device_connections),
            "execution_history_count": len(self._execution_history),
        }
