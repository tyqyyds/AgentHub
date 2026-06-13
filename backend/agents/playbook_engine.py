"""剧本引擎 - 预定义操作剧本的执行引擎"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..core.config import settings
from ..database.models import PlaybookExecutionStatus

logger = logging.getLogger(__name__)


class StepType(Enum):
    """步骤类型"""
    COMMAND = "command"           # 执行命令
    CONDITION = "condition"       # 条件判断
    DELAY = "delay"               # 延时等待
    NOTIFICATION = "notification" # 发送通知
    APPROVAL = "approval"         # 等待审批
    SUB_PLAYBOOK = "sub_playbook" # 子剧本


class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"


@dataclass
class PlaybookStep:
    """剧本步骤"""
    step_id: str
    name: str
    step_type: StepType
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    condition: Optional[str] = None      # 条件表达式
    on_failure: str = "abort"            # abort / skip / continue
    timeout_seconds: int = 60
    retry_count: int = 0
    retry_delay_seconds: int = 5


@dataclass
class PlaybookDefinition:
    """剧本定义"""
    playbook_id: str
    name: str
    description: str
    steps: list[PlaybookStep]
    trigger_condition: Optional[dict[str, Any]] = None
    version: str = "1.0"
    created_by: str = "system"


@dataclass
class ExecutionContext:
    """执行上下文"""
    execution_id: str
    playbook_id: str
    current_step_index: int = 0
    step_results: list[dict[str, Any]] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    status: PlaybookExecutionStatus = PlaybookExecutionStatus.RUNNING


@dataclass
class PlaybookEngineConfig:
    """剧本引擎配置"""
    max_concurrent_executions: int = 10
    default_step_timeout: int = 60
    max_retry_per_step: int = 3
    enable_auto_approval: bool = False
    execution_history_limit: int = 100


# 预定义剧本
BUILTIN_PLAYBOOKS: dict[str, PlaybookDefinition] = {
    "link_failover": PlaybookDefinition(
        playbook_id="link_failover",
        name="链路故障切换",
        description="当主链路故障时自动切换到备用链路",
        steps=[
            PlaybookStep(
                step_id="s1", name="检测链路状态", step_type=StepType.COMMAND,
                action="check_link_status", params={"interface": "{{primary_interface}}"},
                timeout_seconds=10,
            ),
            PlaybookStep(
                step_id="s2", name="确认故障", step_type=StepType.CONDITION,
                action="confirm_failure", condition="link_status == 'down'",
                on_failure="abort",
            ),
            PlaybookStep(
                step_id="s3", name="启用备用链路", step_type=StepType.COMMAND,
                action="enable_backup_link", params={"interface": "{{backup_interface}}"},
                retry_count=2,
            ),
            PlaybookStep(
                step_id="s4", name="验证切换结果", step_type=StepType.COMMAND,
                action="verify_link_status", params={"interface": "{{backup_interface}}"},
            ),
            PlaybookStep(
                step_id="s5", name="发送通知", step_type=StepType.NOTIFICATION,
                action="notify_failover", params={"message": "链路切换完成"},
            ),
        ],
        trigger_condition={"event_type": "link_down"},
    ),
    "device_reboot_recovery": PlaybookDefinition(
        playbook_id="device_reboot_recovery",
        name="设备重启恢复",
        description="设备异常重启后的自动恢复流程",
        steps=[
            PlaybookStep(
                step_id="s1", name="等待设备上线", step_type=StepType.DELAY,
                action="wait", params={"seconds": 30},
            ),
            PlaybookStep(
                step_id="s2", name="检查设备状态", step_type=StepType.COMMAND,
                action="check_device_health", params={"device": "{{device_name}}"},
            ),
            PlaybookStep(
                step_id="s3", name="恢复配置", step_type=StepType.COMMAND,
                action="restore_config", params={"device": "{{device_name}}"},
                retry_count=3, retry_delay_seconds=10,
            ),
            PlaybookStep(
                step_id="s4", name="验证服务", step_type=StepType.COMMAND,
                action="verify_services", params={"device": "{{device_name}}"},
            ),
        ],
        trigger_condition={"event_type": "device_reboot"},
    ),
    "qos_emergency": PlaybookDefinition(
        playbook_id="qos_emergency",
        name="QoS紧急调整",
        description="网络拥塞时紧急调整QoS策略",
        steps=[
            PlaybookStep(
                step_id="s1", name="评估拥塞程度", step_type=StepType.COMMAND,
                action="assess_congestion", params={"threshold": "80%"},
            ),
            PlaybookStep(
                step_id="s2", name="申请审批", step_type=StepType.APPROVAL,
                action="request_approval", params={"risk_level": "high"},
            ),
            PlaybookStep(
                step_id="s3", name="调整QoS策略", step_type=StepType.COMMAND,
                action="adjust_qos", params={"policy": "emergency", "device": "{{device_name}}"},
            ),
            PlaybookStep(
                step_id="s4", name="监控效果", step_type=StepType.DELAY,
                action="wait", params={"seconds": 60},
            ),
            PlaybookStep(
                step_id="s5", name="验证改善", step_type=StepType.COMMAND,
                action="verify_improvement",
            ),
        ],
        trigger_condition={"event_type": "congestion_detected"},
    ),
}


class PlaybookEngine:
    """剧本引擎 - 预定义操作剧本的执行引擎"""

    def __init__(self, config: Optional[PlaybookEngineConfig] = None):
        self.config = config or PlaybookEngineConfig()
        self._playbooks: dict[str, PlaybookDefinition] = dict(BUILTIN_PLAYBOOKS)
        self._active_executions: dict[str, ExecutionContext] = {}
        self._execution_history: list[dict[str, Any]] = []
        self._execution_counter: int = 0
        self._stats: dict[str, int] = {
            "total_executions": 0,
            "completed": 0,
            "failed": 0,
            "aborted": 0,
            "step_timeouts": 0,
            "step_retries": 0,
        }
        logger.info(f"剧本引擎初始化完成, 已加载{len(self._playbooks)}个预定义剧本")

    def _generate_execution_id(self) -> str:
        """生成执行ID"""
        self._execution_counter += 1
        return f"exec_{int(time.time())}_{self._execution_counter}"

    def register_playbook(self, playbook: PlaybookDefinition) -> None:
        """注册剧本"""
        self._playbooks[playbook.playbook_id] = playbook
        logger.info(f"注册剧本: {playbook.playbook_id} ({playbook.name})")

    def unregister_playbook(self, playbook_id: str) -> bool:
        """注销剧本"""
        if playbook_id in self._playbooks:
            del self._playbooks[playbook_id]
            logger.info(f"注销剧本: {playbook_id}")
            return True
        return False

    def list_playbooks(self) -> list[dict[str, Any]]:
        """列出所有剧本"""
        return [
            {
                "playbook_id": p.playbook_id,
                "name": p.name,
                "description": p.description,
                "steps_count": len(p.steps),
                "version": p.version,
            }
            for p in self._playbooks.values()
        ]

    def get_playbook(self, playbook_id: str) -> Optional[PlaybookDefinition]:
        """获取剧本定义"""
        return self._playbooks.get(playbook_id)

    def _resolve_variables(self, text: str, variables: dict[str, Any]) -> str:
        """解析变量引用 {{var_name}}"""
        import re
        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            return str(variables.get(var_name, match.group(0)))
        return re.sub(r"\{\{(\w+)\}\}", replacer, text)

    def _execute_step_action(
        self,
        step: PlaybookStep,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """执行步骤动作（模拟）"""
        resolved_action = self._resolve_variables(step.action, context.variables)
        resolved_params = {
            k: self._resolve_variables(str(v), context.variables) if isinstance(v, str) else v
            for k, v in step.params.items()
        }

        # 模拟不同步骤类型的执行
        if step.step_type == StepType.COMMAND:
            result = {"action": resolved_action, "params": resolved_params, "output": f"模拟执行: {resolved_action}", "success": True}
        elif step.step_type == StepType.CONDITION:
            condition_met = True  # 简化：默认条件满足
            if step.condition:
                condition_met = "down" in step.condition.lower() or "true" in step.condition.lower()
            result = {"action": resolved_action, "condition_met": condition_met, "success": condition_met}
        elif step.step_type == StepType.DELAY:
            delay_secs = resolved_params.get("seconds", 5)
            result = {"action": "delay", "seconds": delay_secs, "success": True}
        elif step.step_type == StepType.NOTIFICATION:
            result = {"action": resolved_action, "message": resolved_params.get("message", ""), "success": True}
        elif step.step_type == StepType.APPROVAL:
            if self.config.enable_auto_approval:
                result = {"action": resolved_action, "approved": True, "success": True}
            else:
                result = {"action": resolved_action, "approved": False, "waiting": True, "success": True}
        elif step.step_type == StepType.SUB_PLAYBOOK:
            result = {"action": resolved_action, "sub_playbook_id": resolved_params.get("playbook_id", ""), "success": True}
        else:
            result = {"action": resolved_action, "success": False, "error": "未知步骤类型"}

        return result

    def start_execution(
        self,
        playbook_id: str,
        variables: Optional[dict[str, Any]] = None,
        triggered_by: str = "manual",
    ) -> dict[str, Any]:
        """启动剧本执行"""
        playbook = self._playbooks.get(playbook_id)
        if not playbook:
            return {"status": "error", "message": f"剧本不存在: {playbook_id}"}

        if len(self._active_executions) >= self.config.max_concurrent_executions:
            return {"status": "error", "message": "并发执行数已达上限"}

        execution_id = self._generate_execution_id()
        context = ExecutionContext(
            execution_id=execution_id,
            playbook_id=playbook_id,
            variables=variables or {},
        )

        self._active_executions[execution_id] = context
        self._stats["total_executions"] += 1

        logger.info(f"启动剧本执行: {playbook.name} (ID: {execution_id})")
        return {
            "status": "started",
            "execution_id": execution_id,
            "playbook_id": playbook_id,
            "total_steps": len(playbook.steps),
        }

    def execute_step(self, execution_id: str) -> dict[str, Any]:
        """执行下一步"""
        context = self._active_executions.get(execution_id)
        if not context:
            return {"status": "error", "message": f"执行不存在: {execution_id}"}

        playbook = self._playbooks.get(context.playbook_id)
        if not playbook:
            return {"status": "error", "message": "剧本定义丢失"}

        if context.current_step_index >= len(playbook.steps):
            context.status = PlaybookExecutionStatus.COMPLETED
            self._stats["completed"] += 1
            self._archive_execution(context)
            return {"status": "completed", "execution_id": execution_id}

        step = playbook.steps[context.current_step_index]
        step_result = self._execute_step_action(step, context)

        # 处理条件步骤失败
        if step.step_type == StepType.CONDITION and not step_result.get("condition_met", True):
            if step.on_failure == "abort":
                context.status = PlaybookExecutionStatus.FAILED
                self._stats["aborted"] += 1
                self._archive_execution(context)
                return {"status": "aborted", "reason": "条件不满足", "step": step.name}

        # 处理审批等待
        if step.step_type == StepType.APPROVAL and step_result.get("waiting"):
            return {
                "status": "waiting_approval",
                "execution_id": execution_id,
                "step": step.name,
                "step_index": context.current_step_index,
            }

        # 记录步骤结果
        context.step_results.append({
            "step_id": step.step_id,
            "step_name": step.name,
            "step_type": step.step_type.value,
            "result": step_result,
            "executed_at": time.time(),
        })

        # 更新变量
        if step_result.get("output"):
            context.variables[f"step_{step.step_id}_output"] = step_result["output"]

        context.current_step_index += 1

        logger.info(f"剧本步骤完成: {step.name} (执行: {execution_id})")

        return {
            "status": "step_completed",
            "execution_id": execution_id,
            "step": step.name,
            "step_index": context.current_step_index,
            "total_steps": len(playbook.steps),
            "step_result": step_result,
        }

    def execute_all(self, execution_id: str) -> dict[str, Any]:
        """执行所有步骤直到完成或失败"""
        results = []
        while True:
            step_result = self.execute_step(execution_id)
            results.append(step_result)
            if step_result["status"] in ("completed", "aborted", "error", "waiting_approval"):
                break
        return {
            "execution_id": execution_id,
            "final_status": results[-1]["status"],
            "steps_executed": len(results),
            "results": results,
        }

    def cancel_execution(self, execution_id: str) -> dict[str, Any]:
        """取消执行"""
        context = self._active_executions.get(execution_id)
        if not context:
            return {"status": "error", "message": f"执行不存在: {execution_id}"}
        context.status = PlaybookExecutionStatus.FAILED
        self._stats["aborted"] += 1
        self._archive_execution(context)
        return {"status": "cancelled", "execution_id": execution_id}

    def _archive_execution(self, context: ExecutionContext) -> None:
        """归档执行记录"""
        record = {
            "execution_id": context.execution_id,
            "playbook_id": context.playbook_id,
            "status": context.status.value,
            "steps_completed": len(context.step_results),
            "started_at": context.started_at,
            "completed_at": time.time(),
            "duration": time.time() - context.started_at,
        }
        self._execution_history.append(record)
        if len(self._execution_history) > self.config.execution_history_limit:
            self._execution_history = self._execution_history[-self.config.execution_history_limit:]
        self._active_executions.pop(context.execution_id, None)

    def get_execution_status(self, execution_id: str) -> Optional[dict[str, Any]]:
        """获取执行状态"""
        context = self._active_executions.get(execution_id)
        if not context:
            for h in self._execution_history:
                if h["execution_id"] == execution_id:
                    return h
            return None

        playbook = self._playbooks.get(context.playbook_id)
        return {
            "execution_id": context.execution_id,
            "playbook_id": context.playbook_id,
            "playbook_name": playbook.name if playbook else "未知",
            "status": context.status.value,
            "current_step": context.current_step_index,
            "total_steps": len(playbook.steps) if playbook else 0,
            "steps_completed": len(context.step_results),
            "started_at": context.started_at,
        }

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return self._stats

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Agent标准处理接口"""
        action = input_data.get("action", "execute")

        if action == "list":
            return {"playbooks": self.list_playbooks()}
        elif action == "start":
            return self.start_execution(
                playbook_id=input_data.get("playbook_id", ""),
                variables=input_data.get("variables"),
                triggered_by=input_data.get("triggered_by", "api"),
            )
        elif action == "step":
            return self.execute_step(execution_id=input_data.get("execution_id", ""))
        elif action == "execute_all":
            return self.execute_all(execution_id=input_data.get("execution_id", ""))
        elif action == "cancel":
            return self.cancel_execution(execution_id=input_data.get("execution_id", ""))
        elif action == "status":
            result = self.get_execution_status(execution_id=input_data.get("execution_id", ""))
            return result or {"status": "error", "message": "执行不存在"}
        elif action == "register":
            pb_data = input_data.get("playbook", {})
            steps = [
                PlaybookStep(
                    step_id=s.get("step_id", f"s{i}"),
                    name=s.get("name", ""),
                    step_type=StepType(s.get("step_type", "command")),
                    action=s.get("action", ""),
                    params=s.get("params", {}),
                )
                for i, s in enumerate(pb_data.get("steps", []))
            ]
            pb = PlaybookDefinition(
                playbook_id=pb_data.get("playbook_id", ""),
                name=pb_data.get("name", ""),
                description=pb_data.get("description", ""),
                steps=steps,
            )
            self.register_playbook(pb)
            return {"status": "registered", "playbook_id": pb.playbook_id}
        else:
            return {"error": f"未知操作: {action}"}

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "playbooks_count": len(self._playbooks),
            "active_executions": len(self._active_executions),
            "history_size": len(self._execution_history),
            "stats": self._stats,
        }
