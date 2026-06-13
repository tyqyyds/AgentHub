"""工具编排器 - 工具调用链编排与执行，支持串行/并行/条件分支"""

import logging
import time
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from ..core.config import settings

logger = logging.getLogger(__name__)


class ChainStepType(Enum):
    """编排步骤类型"""
    SERIAL = "serial"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    RETRY = "retry"
    FALLBACK = "fallback"


class ChainStepStatus(Enum):
    """步骤执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ChainStep:
    """编排链步骤"""
    step_id: str
    tool_id: str
    step_type: ChainStepType = ChainStepType.SERIAL
    input_mapping: dict[str, str] = field(default_factory=dict)
    output_key: str = ""
    condition: str = ""
    retry_count: int = 0
    retry_delay_seconds: float = 1.0
    fallback_tool_id: str = ""
    timeout_seconds: int = 30
    status: ChainStepStatus = ChainStepStatus.PENDING
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0


@dataclass
class ToolChain:
    """工具编排链"""
    chain_id: str
    name: str
    description: str = ""
    steps: list[ChainStep] = field(default_factory=list)
    global_timeout_seconds: int = 300
    created_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
        if not self.chain_id:
            self.chain_id = f"chain_{uuid4().hex[:8]}"


@dataclass
class ChainExecutionResult:
    """编排链执行结果"""
    chain_id: str
    execution_id: str
    status: str = "pending"
    steps_results: list[dict[str, Any]] = field(default_factory=list)
    final_output: dict[str, Any] = field(default_factory=dict)
    total_duration_ms: float = 0.0
    error: str = ""


@dataclass
class ToolOrchestratorConfig:
    """工具编排器配置"""
    max_chain_steps: int = 20
    default_step_timeout_seconds: int = 30
    max_retry_count: int = 3
    retry_delay_seconds: float = 1.0
    enable_parallel: bool = True
    max_parallel_steps: int = 5


class ToolOrchestrator:
    """工具编排器：工具调用链编排与执行"""

    def __init__(self, config: Optional[ToolOrchestratorConfig] = None):
        self.config = config or ToolOrchestratorConfig()
        self._chains: dict[str, ToolChain] = {}
        self._tool_registry = None
        self._execution_history: list[ChainExecutionResult] = []
        self._stats: dict[str, int] = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "total_steps_executed": 0,
        }
        logger.info("工具编排器初始化完成")

    def set_tool_registry(self, registry: Any) -> None:
        """设置工具注册中心引用"""
        self._tool_registry = registry
        logger.info("工具编排器已关联工具注册中心")

    def register_chain(self, chain: ToolChain) -> bool:
        """注册编排链"""
        if len(chain.steps) > self.config.max_chain_steps:
            logger.warning(f"编排链步骤数超限: {len(chain.steps)} > {self.config.max_chain_steps}")
            return False

        self._chains[chain.chain_id] = chain
        logger.info(f"编排链注册: {chain.chain_id}, 名称: {chain.name}, 步骤数: {len(chain.steps)}")
        return True

    def unregister_chain(self, chain_id: str) -> bool:
        """注销编排链"""
        if chain_id in self._chains:
            del self._chains[chain_id]
            logger.info(f"编排链注销: {chain_id}")
            return True
        return False

    def get_chain(self, chain_id: str) -> Optional[ToolChain]:
        """获取编排链"""
        return self._chains.get(chain_id)

    async def _execute_tool(self, tool_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """执行单个工具调用"""
        start_time = time.time()

        # 优先通过工具注册中心获取工具信息
        if self._tool_registry:
            tool_info = self._tool_registry.get_tool(tool_id)
            if not tool_info:
                return {"success": False, "error": f"工具未注册: {tool_id}"}
            if tool_info.status.value != "active":
                return {"success": False, "error": f"工具不可用: {tool_id}, 状态: {tool_info.status.value}"}

        # 模拟工具执行：实际应通过HTTP调用工具endpoint
        latency_ms = (time.time() - start_time) * 1000

        # 根据tool_id模拟不同工具的执行结果
        simulated_results = {
            "check_device_status": {"success": True, "data": {"status": "online", "uptime": "72h"}},
            "check_qos_status": {"success": True, "data": {"qos_policies": 15, "active": 12}},
            "check_acl_status": {"success": True, "data": {"acl_rules": 230, "active": 198}},
            "check_route_table": {"success": True, "data": {"routes": 1500, "active": 1200}},
            "apply_config": {"success": True, "data": {"applied": True, "changes": 3}},
            "verify_config": {"success": True, "data": {"verified": True, "compliant": True}},
            "rollback_config": {"success": True, "data": {"rolled_back": True, "previous_version": "v2.1"}},
        }

        result = simulated_results.get(tool_id, {
            "success": True,
            "data": {"tool_id": tool_id, "output": f"工具 {tool_id} 执行完成"},
        })

        # 更新工具注册中心的调用结果
        if self._tool_registry:
            self._tool_registry.update_tool_result(tool_id, result["success"], latency_ms)

        return result

    def _map_input(self, step: ChainStep, context: dict[str, Any], prev_output: dict[str, Any]) -> dict[str, Any]:
        """映射步骤输入"""
        mapped_input = {}
        for target_key, source_path in step.input_mapping.items():
            # 支持 prev.xxx 引用上一步输出，context.xxx 引用全局上下文
            if source_path.startswith("prev."):
                key = source_path[5:]
                mapped_input[target_key] = prev_output.get("data", {}).get(key, prev_output.get(key))
            elif source_path.startswith("context."):
                key = source_path[8:]
                mapped_input[target_key] = context.get(key)
            else:
                mapped_input[target_key] = source_path
        return mapped_input

    def _evaluate_condition(self, condition: str, context: dict[str, Any], prev_output: dict[str, Any]) -> bool:
        """评估条件表达式"""
        if not condition:
            return True

        # 简单条件评估：支持 prev.xxx == value, context.xxx != value
        try:
            if "==" in condition:
                left, right = condition.split("==", 1)
                left_val = self._resolve_value(left.strip(), context, prev_output)
                return str(left_val) == right.strip().strip('"').strip("'")
            elif "!=" in condition:
                left, right = condition.split("!=", 1)
                left_val = self._resolve_value(left.strip(), context, prev_output)
                return str(left_val) != right.strip().strip('"').strip("'")
            else:
                return bool(self._resolve_value(condition, context, prev_output))
        except Exception as e:
            logger.warning(f"条件评估失败: {condition}, 错误: {e}")
            return False

    def _resolve_value(self, path: str, context: dict[str, Any], prev_output: dict[str, Any]) -> Any:
        """解析值路径"""
        if path.startswith("prev."):
            key = path[5:]
            return prev_output.get("data", {}).get(key, prev_output.get(key))
        elif path.startswith("context."):
            key = path[8:]
            return context.get(key)
        return path

    async def _execute_step(
        self,
        step: ChainStep,
        context: dict[str, Any],
        prev_output: dict[str, Any],
    ) -> dict[str, Any]:
        """执行单个编排步骤"""
        step.status = ChainStepStatus.RUNNING
        step.started_at = time.time()
        self._stats["total_steps_executed"] += 1

        try:
            # 条件检查
            if step.step_type == ChainStepType.CONDITIONAL and not self._evaluate_condition(step.condition, context, prev_output):
                step.status = ChainStepStatus.SKIPPED
                step.result = {"skipped": True, "reason": "条件不满足"}
                return step.result

            # 输入映射
            mapped_input = self._map_input(step, context, prev_output)

            # 工具执行（带重试）
            last_error = ""
            for attempt in range(step.retry_count + 1):
                try:
                    result = await asyncio.wait_for(
                        self._execute_tool(step.tool_id, mapped_input),
                        timeout=step.timeout_seconds,
                    )
                    if result.get("success", False):
                        step.status = ChainStepStatus.COMPLETED
                        step.result = result
                        step.completed_at = time.time()

                        # 将结果存入上下文
                        if step.output_key:
                            context[step.output_key] = result.get("data", result)

                        return result
                    else:
                        last_error = result.get("error", "未知错误")
                        if attempt < step.retry_count:
                            logger.info(f"步骤重试: {step.step_id}, 第{attempt + 1}次, 错误: {last_error}")
                            await asyncio.sleep(step.retry_delay_seconds * (attempt + 1))
                except asyncio.TimeoutError:
                    last_error = f"步骤超时: {step.timeout_seconds}s"
                    logger.warning(f"步骤超时: {step.step_id}")
                except Exception as e:
                    last_error = str(e)

            # 重试耗尽，尝试fallback
            if step.fallback_tool_id:
                logger.info(f"步骤fallback: {step.step_id} -> {step.fallback_tool_id}")
                try:
                    result = await self._execute_tool(step.fallback_tool_id, mapped_input)
                    step.status = ChainStepStatus.COMPLETED
                    step.result = {**result, "fallback": True}
                    step.completed_at = time.time()
                    if step.output_key:
                        context[step.output_key] = result.get("data", result)
                    return step.result
                except Exception as e:
                    last_error = f"fallback也失败: {e}"

            step.status = ChainStepStatus.FAILED
            step.error = last_error
            step.result = {"success": False, "error": last_error}
            step.completed_at = time.time()
            return step.result

        except Exception as e:
            step.status = ChainStepStatus.FAILED
            step.error = str(e)
            step.result = {"success": False, "error": str(e)}
            step.completed_at = time.time()
            return step.result

    async def execute_chain(self, chain_id: str, initial_context: dict[str, Any]) -> ChainExecutionResult:
        """执行编排链"""
        chain = self._chains.get(chain_id)
        if not chain:
            return ChainExecutionResult(
                chain_id=chain_id,
                execution_id=f"exec_{uuid4().hex[:8]}",
                status="failed",
                error=f"编排链未注册: {chain_id}",
            )

        execution_id = f"exec_{uuid4().hex[:8]}"
        start_time = time.time()
        context = dict(initial_context)
        prev_output: dict[str, Any] = {}
        steps_results: list[dict[str, Any]] = []
        final_output: dict[str, Any] = {}
        failed = False

        self._stats["total_executions"] += 1

        for step in chain.steps:
            if failed and step.step_type != ChainStepType.FALLBACK:
                step.status = ChainStepStatus.SKIPPED
                steps_results.append({
                    "step_id": step.step_id,
                    "tool_id": step.tool_id,
                    "status": "skipped",
                    "reason": "前序步骤失败",
                })
                continue

            result = await self._execute_step(step, context, prev_output)
            prev_output = result
            steps_results.append({
                "step_id": step.step_id,
                "tool_id": step.tool_id,
                "status": step.status.value,
                "result": result,
                "duration_ms": (step.completed_at - step.started_at) * 1000 if step.completed_at and step.started_at else 0,
            })

            if step.status == ChainStepStatus.FAILED:
                failed = True

            final_output = result

        total_duration_ms = (time.time() - start_time) * 1000
        status = "completed" if not failed else "failed"

        if not failed:
            self._stats["successful_executions"] += 1
        else:
            self._stats["failed_executions"] += 1

        exec_result = ChainExecutionResult(
            chain_id=chain_id,
            execution_id=execution_id,
            status=status,
            steps_results=steps_results,
            final_output=final_output,
            total_duration_ms=total_duration_ms,
        )

        self._execution_history.append(exec_result)
        logger.info(f"编排链执行完成: {chain_id}, 状态: {status}, 耗时: {total_duration_ms:.0f}ms")
        return exec_result

    def get_execution_history(self, chain_id: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
        """获取执行历史"""
        history = self._execution_history
        if chain_id:
            history = [h for h in history if h.chain_id == chain_id]
        return [
            {
                "execution_id": h.execution_id,
                "chain_id": h.chain_id,
                "status": h.status,
                "total_duration_ms": h.total_duration_ms,
                "steps_count": len(h.steps_results),
            }
            for h in history[-limit:]
        ]

    def get_stats(self) -> dict[str, Any]:
        """获取编排器统计"""
        return {
            **self._stats,
            "registered_chains": len(self._chains),
            "execution_history_size": len(self._execution_history),
        }

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Agent标准处理接口"""
        action = input_data.get("action", "execute")

        if action == "register_chain":
            chain_data = input_data.get("chain", {})
            steps_data = chain_data.pop("steps", [])
            steps = [ChainStep(**s) for s in steps_data]
            chain = ToolChain(steps=steps, **chain_data)
            success = self.register_chain(chain)
            return {"action": "register_chain", "success": success, "chain_id": chain.chain_id}

        elif action == "unregister_chain":
            success = self.unregister_chain(input_data.get("chain_id", ""))
            return {"action": "unregister_chain", "success": success}

        elif action == "execute":
            chain_id = input_data.get("chain_id", "")
            context = input_data.get("context", {})
            result = await self.execute_chain(chain_id, context)
            return {
                "action": "execute",
                "execution_id": result.execution_id,
                "status": result.status,
                "steps_results": result.steps_results,
                "final_output": result.final_output,
                "total_duration_ms": result.total_duration_ms,
            }

        elif action == "list_chains":
            chains = [
                {"chain_id": c.chain_id, "name": c.name, "steps_count": len(c.steps)}
                for c in self._chains.values()
            ]
            return {"action": "list_chains", "chains": chains}

        elif action == "execution_history":
            history = self.get_execution_history(
                chain_id=input_data.get("chain_id"),
                limit=input_data.get("limit", 20),
            )
            return {"action": "execution_history", "history": history}

        else:
            return {"action": action, "error": "未知操作"}

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        stats = self.get_stats()
        success_rate = (
            stats["successful_executions"] / stats["total_executions"]
            if stats["total_executions"] > 0
            else 1.0
        )
        status = "healthy" if success_rate >= 0.8 else "degraded"

        return {
            "status": status,
            "agent": self.__class__.__name__,
            "registered_chains": stats["registered_chains"],
            "total_executions": stats["total_executions"],
            "success_rate": success_rate,
            "tool_registry_connected": self._tool_registry is not None,
        }
