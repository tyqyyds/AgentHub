import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import asyncio

from ..core.config import settings

logger = logging.getLogger(__name__)


class CollaborationMode(str, Enum):
    """协作模式"""
    SUPERVISOR = "supervisor"
    PARALLEL = "parallel"
    DEBATE = "debate"


@dataclass
class TaskNode:
    """任务节点"""
    task_id: str
    agent_name: str
    input_data: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None


@dataclass
class OrchestratorConfig:
    """编排器配置"""
    default_mode: CollaborationMode = CollaborationMode.SUPERVISOR
    max_parallel_tasks: int = 10
    debate_rounds: int = 3
    debate_consensus_threshold: float = 0.7
    task_timeout_seconds: int = 300


class OrchestratorAgent:
    """编排器Agent：Supervisor/Parallel/Debate三种协作模式调度，任务分解与结果聚合"""

    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._agent_pool: Dict[str, Any] = {}
        self._task_graph: Dict[str, TaskNode] = {}

    def register_agent(self, name: str, agent: Any) -> None:
        """注册Agent到编排池"""
        self._agent_pool[name] = agent
        self.logger.info(f"Agent已注册: {name}")

    def _decompose_task(self, intent: Dict[str, Any]) -> List[TaskNode]:
        """将意图分解为子任务"""
        actions = intent.get("actions", [])
        targets = intent.get("targets", [])
        nodes = []

        for idx, action in enumerate(actions):
            task_id = f"task_{idx}"
            node = TaskNode(
                task_id=task_id,
                agent_name=action.get("type", "config_generator"),
                input_data={
                    "action": action,
                    "targets": targets,
                    "intent_name": intent.get("intent_name", ""),
                },
                dependencies=[f"task_{i}" for i in range(idx) if idx > 0] if idx > 0 else [],
            )
            nodes.append(node)

        if not nodes:
            nodes.append(TaskNode(
                task_id="task_0",
                agent_name="intent_parser",
                input_data=intent,
            ))

        return nodes

    async def _execute_supervisor(self, tasks: List[TaskNode]) -> Dict[str, Any]:
        """Supervisor模式：串行编排，监督执行"""
        results = {}
        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id in results:
                    task.input_data["dependency_result"] = results[dep_id]

            agent = self._agent_pool.get(task.agent_name)
            if agent and hasattr(agent, "process"):
                try:
                    task.result = await asyncio.wait_for(
                        agent.process(task.input_data),
                        timeout=self.config.task_timeout_seconds,
                    )
                    task.status = "completed"
                except asyncio.TimeoutError:
                    task.status = "timeout"
                    task.result = {"error": "任务执行超时"}
                    self.logger.warning(f"任务超时: {task.task_id}")
                except Exception as e:
                    task.status = "failed"
                    task.result = {"error": str(e)}
                    self.logger.error(f"任务执行失败: {task.task_id}, 错误: {e}")
            else:
                task.status = "skipped"
                task.result = {"error": f"Agent未注册: {task.agent_name}"}

            results[task.task_id] = task.result

        return self._aggregate_results(tasks, results)

    async def _execute_parallel(self, tasks: List[TaskNode]) -> Dict[str, Any]:
        """Parallel模式：并行执行无依赖任务"""
        results = {}
        pending = list(tasks)
        completed_ids = set()

        while pending:
            ready = [
                t for t in pending
                if all(d in completed_ids for d in t.dependencies)
            ]
            if not ready:
                break

            coros = []
            for task in ready:
                agent = self._agent_pool.get(task.agent_name)
                if agent and hasattr(agent, "process"):
                    coros.append(self._safe_process(agent, task))
                else:
                    task.status = "skipped"
                    task.result = {"error": f"Agent未注册: {task.agent_name}"}
                    coros.append(asyncio.coroutine(lambda t=task: t.result)())

            batch_results = await asyncio.gather(*coros, return_exceptions=True)
            for task, result in zip(ready, batch_results):
                if isinstance(result, Exception):
                    task.status = "failed"
                    task.result = {"error": str(result)}
                else:
                    task.status = "completed"
                    task.result = result
                results[task.task_id] = task.result
                completed_ids.add(task.task_id)
                pending.remove(task)

        return self._aggregate_results(tasks, results)

    async def _execute_debate(self, tasks: List[TaskNode]) -> Dict[str, Any]:
        """Debate模式：多Agent辩论决策"""
        candidates = list(self._agent_pool.keys())
        if len(candidates) < 2:
            self.logger.warning("辩论模式需要至少2个Agent，降级为Supervisor模式")
            return await self._execute_supervisor(tasks)

        all_proposals = []
        for round_num in range(self.config.debate_rounds):
            round_proposals = []
            for candidate_name in candidates:
                agent = self._agent_pool[candidate_name]
                if hasattr(agent, "process"):
                    try:
                        result = await agent.process({
                            **(tasks[0].input_data if tasks else {}),
                            "debate_round": round_num,
                            "previous_proposals": all_proposals,
                        })
                        round_proposals.append({
                            "agent": candidate_name,
                            "proposal": result,
                            "round": round_num,
                        })
                    except Exception as e:
                        self.logger.error(f"辩论Agent {candidate_name} 异常: {e}")

            all_proposals.extend(round_proposals)

        return self._consensus_vote(all_proposals)

    def _consensus_vote(self, proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """共识投票"""
        if not proposals:
            return {"status": "no_consensus", "result": None}

        scored = []
        for proposal in proposals:
            result = proposal.get("proposal", {})
            confidence = result.get("confidence", 0.5) if isinstance(result, dict) else 0.5
            scored.append((proposal, confidence))

        scored.sort(key=lambda x: x[1], reverse=True)
        best = scored[0]

        if best[1] >= self.config.debate_consensus_threshold:
            return {
                "status": "consensus_reached",
                "winner": best[0]["agent"],
                "result": best[0]["proposal"],
                "confidence": best[1],
                "total_proposals": len(proposals),
            }

        return {
            "status": "no_consensus",
            "best_proposal": best[0]["proposal"],
            "confidence": best[1],
            "total_proposals": len(proposals),
        }

    async def _safe_process(self, agent: Any, task: TaskNode) -> Dict[str, Any]:
        """安全执行Agent处理"""
        try:
            return await asyncio.wait_for(
                agent.process(task.input_data),
                timeout=self.config.task_timeout_seconds,
            )
        except asyncio.TimeoutError:
            return {"error": "任务执行超时"}
        except Exception as e:
            return {"error": str(e)}

    def _aggregate_results(self, tasks: List[TaskNode], results: Dict[str, Any]) -> Dict[str, Any]:
        """聚合所有子任务结果"""
        completed = sum(1 for t in tasks if t.status == "completed")
        failed = sum(1 for t in tasks if t.status in ("failed", "timeout", "skipped"))

        aggregated = {
            "total_tasks": len(tasks),
            "completed": completed,
            "failed": failed,
            "results": results,
            "status": "completed" if failed == 0 else "partial_failure",
        }

        if failed > 0 and completed == 0:
            aggregated["status"] = "failed"

        return aggregated

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理编排请求"""
        mode_str = input_data.get("mode", self.config.default_mode.value)
        try:
            mode = CollaborationMode(mode_str)
        except ValueError:
            mode = self.config.default_mode
            self.logger.warning(f"未知协作模式 {mode_str}，使用默认模式 {mode.value}")

        intent = input_data.get("intent", input_data)
        tasks = self._decompose_task(intent)
        self._task_graph = {t.task_id: t for t in tasks}

        self.logger.info(f"编排启动: 模式={mode.value}, 任务数={len(tasks)}")

        if mode == CollaborationMode.SUPERVISOR:
            result = await self._execute_supervisor(tasks)
        elif mode == CollaborationMode.PARALLEL:
            result = await self._execute_parallel(tasks)
        elif mode == CollaborationMode.DEBATE:
            result = await self._execute_debate(tasks)
        else:
            result = await self._execute_supervisor(tasks)

        result["collaboration_mode"] = mode.value
        return result

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        agent_status = {}
        for name, agent in self._agent_pool.items():
            if hasattr(agent, "health_check"):
                try:
                    agent_status[name] = await agent.health_check()
                except Exception:
                    agent_status[name] = {"status": "unhealthy"}
            else:
                agent_status[name] = {"status": "unknown"}

        return {
            "status": "healthy",
            "agent": self.__class__.__name__,
            "registered_agents": len(self._agent_pool),
            "agent_status": agent_status,
        }
