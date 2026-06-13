import logging
import asyncio
import random
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum as PyEnum

from ..core.config import settings
from ..database.models import GrayscalePhase, GrayscaleTaskStatus

logger = logging.getLogger(__name__)


class CanaryCheckResult(PyEnum):
    """金丝雀检查结果"""
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class RollbackReason(PyEnum):
    """回滚原因"""
    CANARY_FAILED = "canary_failed"
    METRICS_DEGRADED = "metrics_degraded"
    MANUAL_TRIGGER = "manual_trigger"
    TIMEOUT = "timeout"


@dataclass
class CanaryMetrics:
    """金丝雀验证指标"""
    latency_p50_ms: float = 0.0
    latency_p99_ms: float = 0.0
    packet_loss_rate: float = 0.0
    cpu_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0
    error_rate: float = 0.0


@dataclass
class GrayscaleStepResult:
    """灰度步骤结果"""
    phase: GrayscalePhase = GrayscalePhase.CANARY
    device: str = ""
    success: bool = False
    metrics_before: Optional[CanaryMetrics] = None
    metrics_after: Optional[CanaryMetrics] = None
    duration_ms: int = 0
    error: Optional[str] = None


@dataclass
class GrayscaleHealingConfig:
    """灰度自愈Agent配置"""
    canary_percentage: float = field(
        default_factory=lambda: settings.grayscale_canary_percentage
    )
    batch_size: int = field(
        default_factory=lambda: settings.grayscale_batch_size
    )
    observation_period_seconds: int = field(
        default_factory=lambda: settings.grayscale_observation_period_seconds
    )
    auto_rollback_enabled: bool = field(
        default_factory=lambda: settings.auto_rollback_enabled
    )
    max_canary_retries: int = 2
    metrics_degradation_threshold: float = 0.3
    latency_increase_threshold_percent: float = 50.0
    error_rate_threshold: float = 0.05


# ── 金丝雀验证指标基线 ──
BASELINE_METRICS = CanaryMetrics(
    latency_p50_ms=15.0,
    latency_p99_ms=45.0,
    packet_loss_rate=0.001,
    cpu_usage_percent=35.0,
    memory_usage_percent=40.0,
    error_rate=0.002,
)


class GrayscaleHealingAgent:
    """灰度自愈Agent：金丝雀验证 → 批量执行 → 自动回滚

    核心流程：
    1. 金丝雀阶段(canary)：选取少量设备执行变更，观察指标
    2. 批量阶段(batch)：金丝雀通过后，分批对剩余设备执行变更
    3. 回滚阶段(rollback)：任一阶段指标异常，自动回滚已变更设备
    """

    def __init__(self, config: Optional[GrayscaleHealingConfig] = None):
        self.config = config or GrayscaleHealingConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._active_tasks: Dict[str, Dict[str, Any]] = {}
        self._rollback_history: List[Dict[str, Any]] = []

    def _select_canary_devices(
        self, all_devices: List[str], percentage: Optional[float] = None
    ) -> List[str]:
        """选择金丝雀设备"""
        pct = percentage or self.config.canary_percentage
        count = max(1, int(len(all_devices) * pct))
        return random.sample(all_devices, min(count, len(all_devices)))

    def _select_batch_devices(
        self,
        all_devices: List[str],
        canary_devices: List[str],
        batch_index: int,
    ) -> List[str]:
        """选择批量执行设备"""
        remaining = [d for d in all_devices if d not in canary_devices]
        start = batch_index * self.config.batch_size
        end = start + self.config.batch_size
        return remaining[start:end]

    async def _collect_metrics(self, device: str) -> CanaryMetrics:
        """采集设备指标（模拟）"""
        await asyncio.sleep(0.1)
        jitter = random.uniform(-0.1, 0.1)
        return CanaryMetrics(
            latency_p50_ms=BASELINE_METRICS.latency_p50_ms * (1 + jitter),
            latency_p99_ms=BASELINE_METRICS.latency_p99_ms * (1 + jitter),
            packet_loss_rate=max(0, BASELINE_METRICS.packet_loss_rate * (1 + jitter * 5)),
            cpu_usage_percent=BASELINE_METRICS.cpu_usage_percent * (1 + jitter),
            memory_usage_percent=BASELINE_METRICS.memory_usage_percent * (1 + jitter),
            error_rate=max(0, BASELINE_METRICS.error_rate * (1 + jitter * 3)),
        )

    def _evaluate_canary(
        self, before: CanaryMetrics, after: CanaryMetrics
    ) -> CanaryCheckResult:
        """评估金丝雀结果"""
        latency_increase = (
            (after.latency_p99_ms - before.latency_p99_ms) / before.latency_p99_ms * 100
            if before.latency_p99_ms > 0 else 0
        )
        if latency_increase > self.config.latency_increase_threshold_percent:
            self.logger.warning(
                f"金丝雀验证失败: 延迟增长 {latency_increase:.1f}% "
                f"超过阈值 {self.config.latency_increase_threshold_percent}%"
            )
            return CanaryCheckResult.FAILED

        if after.error_rate > self.config.error_rate_threshold:
            self.logger.warning(
                f"金丝雀验证失败: 错误率 {after.error_rate:.4f} "
                f"超过阈值 {self.config.error_rate_threshold}"
            )
            return CanaryCheckResult.FAILED

        if after.packet_loss_rate > before.packet_loss_rate * (
            1 + self.config.metrics_degradation_threshold
        ):
            self.logger.warning("金丝雀验证失败: 丢包率显著上升")
            return CanaryCheckResult.FAILED

        return CanaryCheckResult.PASSED

    async def _execute_on_device(
        self, device: str, commands: List[str]
    ) -> GrayscaleStepResult:
        """在设备上执行命令"""
        start_time = datetime.now(timezone.utc)
        metrics_before = await self._collect_metrics(device)

        await asyncio.sleep(0.15)

        success = random.random() > 0.05
        metrics_after = await self._collect_metrics(device)

        if not success:
            metrics_after.error_rate = metrics_after.error_rate + 0.1

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        return GrayscaleStepResult(
            phase=GrayscalePhase.CANARY,
            device=device,
            success=success,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            duration_ms=int(elapsed),
            error=None if success else "命令执行失败",
        )

    async def _rollback_devices(
        self, devices: List[str], reason: RollbackReason
    ) -> List[GrayscaleStepResult]:
        """回滚设备"""
        results = []
        for device in devices:
            await asyncio.sleep(0.1)
            results.append(GrayscaleStepResult(
                phase=GrayscalePhase.ROLLBACK,
                device=device,
                success=True,
                duration_ms=100,
            ))
            self.logger.info(f"设备 {device} 已回滚 (原因: {reason.value})")

        rollback_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason.value,
            "devices_count": len(devices),
            "devices": devices,
        }
        self._rollback_history.append(rollback_record)
        return results

    async def _run_canary_phase(
        self, devices: List[str], commands: List[str]
    ) -> Dict[str, Any]:
        """执行金丝雀阶段"""
        canary_devices = self._select_canary_devices(devices)
        self.logger.info(
            f"金丝雀阶段: 选取 {len(canary_devices)}/{len(devices)} 台设备"
        )

        canary_results = []
        for device in canary_devices:
            result = await self._execute_on_device(device, commands)
            result.phase = GrayscalePhase.CANARY
            canary_results.append(result)

        all_success = all(r.success for r in canary_results)
        metrics_ok = True
        if all_success:
            for r in canary_results:
                if r.metrics_before and r.metrics_after:
                    check = self._evaluate_canary(r.metrics_before, r.metrics_after)
                    if check != CanaryCheckResult.PASSED:
                        metrics_ok = False
                        break

        passed = all_success and metrics_ok
        return {
            "phase": GrayscalePhase.CANARY.value,
            "canary_devices": canary_devices,
            "passed": passed,
            "results": [
                {
                    "device": r.device,
                    "success": r.success,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                }
                for r in canary_results
            ],
        }

    async def _run_batch_phase(
        self,
        all_devices: List[str],
        canary_devices: List[str],
        commands: List[str],
    ) -> Dict[str, Any]:
        """执行批量阶段"""
        remaining = [d for d in all_devices if d not in canary_devices]
        batch_index = 0
        all_batch_results = []
        completed_devices = []

        while remaining:
            batch = self._select_batch_devices(
                all_devices, canary_devices, batch_index
            )
            if not batch:
                break

            self.logger.info(
                f"批量阶段 (批次 {batch_index + 1}): "
                f"执行 {len(batch)} 台设备"
            )

            coros = [self._execute_on_device(dev, commands) for dev in batch]
            batch_results = await asyncio.gather(*coros, return_exceptions=True)

            batch_failed = False
            for dev, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    all_batch_results.append({
                        "device": dev,
                        "success": False,
                        "error": str(result),
                    })
                    batch_failed = True
                else:
                    all_batch_results.append({
                        "device": dev,
                        "success": result.success,
                        "duration_ms": result.duration_ms,
                        "error": result.error,
                    })
                    if result.success:
                        completed_devices.append(dev)
                    else:
                        batch_failed = True

            if batch_failed and self.config.auto_rollback_enabled:
                self.logger.warning("批量阶段检测到失败，触发自动回滚")
                rollback_results = await self._rollback_devices(
                    canary_devices + completed_devices,
                    RollbackReason.METRICS_DEGRADED,
                )
                return {
                    "phase": GrayscalePhase.BATCH.value,
                    "status": "rolled_back",
                    "batch_results": all_batch_results,
                    "rollback_results": [
                        {"device": r.device, "success": r.success}
                        for r in rollback_results
                    ],
                }

            remaining = [d for d in remaining if d not in batch]
            batch_index += 1

            if self.config.observation_period_seconds > 0:
                self.logger.info(
                    f"观察期: 等待 {self.config.observation_period_seconds}s"
                )
                await asyncio.sleep(min(1.0, self.config.observation_period_seconds * 0.01))

        return {
            "phase": GrayscalePhase.BATCH.value,
            "status": "completed",
            "batch_results": all_batch_results,
        }

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行灰度自愈流程

        输入:
            event_id: 自愈事件ID
            devices: 目标设备列表
            commands: 执行命令列表
            skip_canary: 是否跳过金丝雀阶段
        """
        event_id = input_data.get("event_id")
        devices = input_data.get("devices", [])
        commands = input_data.get("commands", [])
        skip_canary = input_data.get("skip_canary", False)

        if not devices or not commands:
            return {
                "status": "failed",
                "error": "缺少设备列表或执行命令",
                "phase": None,
            }

        task_id = f"gs-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self._active_tasks[task_id] = {
            "event_id": event_id,
            "devices": devices,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": GrayscaleTaskStatus.RUNNING.value,
        }

        self.logger.info(
            f"灰度自愈任务 {task_id} 启动: "
            f"设备数={len(devices)}, 命令数={len(commands)}"
        )

        canary_devices = []

        # ── 金丝雀阶段 ──
        if not skip_canary:
            canary_result = await self._run_canary_phase(devices, commands)
            canary_devices = canary_result.get("canary_devices", [])

            if not canary_result["passed"]:
                if self.config.auto_rollback_enabled:
                    rollback_results = await self._rollback_devices(
                        canary_devices, RollbackReason.CANARY_FAILED
                    )
                    self._active_tasks[task_id]["status"] = (
                        GrayscaleTaskStatus.ROLLED_BACK.value
                    )
                    return {
                        "task_id": task_id,
                        "status": "rolled_back",
                        "reason": "canary_failed",
                        "canary_result": canary_result,
                        "rollback_results": [
                            {"device": r.device, "success": r.success}
                            for r in rollback_results
                        ],
                    }
                else:
                    self._active_tasks[task_id]["status"] = (
                        GrayscaleTaskStatus.FAILED.value
                    )
                    return {
                        "task_id": task_id,
                        "status": "failed",
                        "reason": "canary_failed_no_rollback",
                        "canary_result": canary_result,
                    }
        else:
            canary_devices = devices[:1]
            canary_result = {"phase": "canary", "passed": True, "skipped": True}

        # ── 批量阶段 ──
        batch_result = await self._run_batch_phase(
            devices, canary_devices, commands
        )

        final_status = batch_result.get("status", "completed")
        self._active_tasks[task_id]["status"] = (
            GrayscaleTaskStatus.ROLLED_BACK.value
            if final_status == "rolled_back"
            else GrayscaleTaskStatus.COMPLETED.value
        )

        return {
            "task_id": task_id,
            "status": final_status,
            "canary_percentage": self.config.canary_percentage,
            "batch_size": self.config.batch_size,
            "auto_rollback": self.config.auto_rollback_enabled,
            "canary_result": canary_result,
            "batch_result": batch_result,
        }

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        active_count = sum(
            1 for t in self._active_tasks.values()
            if t["status"] == GrayscaleTaskStatus.RUNNING.value
        )
        return {
            "status": "healthy",
            "agent": self.__class__.__name__,
            "config": {
                "canary_percentage": self.config.canary_percentage,
                "batch_size": self.config.batch_size,
                "observation_period_seconds": self.config.observation_period_seconds,
                "auto_rollback_enabled": self.config.auto_rollback_enabled,
            },
            "active_tasks": active_count,
            "total_tasks": len(self._active_tasks),
            "rollback_history_count": len(self._rollback_history),
        }
