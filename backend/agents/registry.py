"""Agent注册中心 - Agent生命周期管理、能力发现、健康监控"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent状态"""
    INITIALIZING = "initializing"
    ACTIVE = "active"
    BUSY = "busy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"


@dataclass
class AgentInfo:
    """Agent信息"""
    agent_id: str
    agent_type: str
    capabilities: list[str]
    status: AgentStatus = AgentStatus.INITIALIZING
    version: str = "1.0.0"
    host: str = "localhost"
    port: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at: float = 0.0
    last_heartbeat: float = 0.0
    health_score: float = 1.0
    total_tasks: int = 0
    success_tasks: int = 0
    failed_tasks: int = 0
    avg_latency_ms: float = 0.0

    def __post_init__(self):
        if not self.registered_at:
            self.registered_at = time.time()
        if not self.last_heartbeat:
            self.last_heartbeat = time.time()


@dataclass
class RegistryConfig:
    """注册中心配置"""
    heartbeat_timeout_seconds: int = 30
    health_check_interval_seconds: int = 60
    max_agents: int = 100
    enable_auto_deregistration: bool = True
    auto_deregistration_timeout_seconds: int = 120


class AgentRegistry:
    """Agent注册中心"""

    def __init__(self, config: Optional[RegistryConfig] = None):
        self.config = config or RegistryConfig()
        self._agents: dict[str, AgentInfo] = {}
        self._capability_index: dict[str, list[str]] = {}
        self._stats: dict[str, int] = {
            "total_registrations": 0,
            "total_deregistrations": 0,
            "capability_queries": 0,
            "health_checks": 0,
        }
        logger.info("Agent注册中心初始化完成")

    def register(self, agent_info: AgentInfo) -> bool:
        """注册Agent"""
        if len(self._agents) >= self.config.max_agents and agent_info.agent_id not in self._agents:
            logger.warning(f"注册中心已满，无法注册: {agent_info.agent_id}")
            return False

        agent_info.status = AgentStatus.ACTIVE
        agent_info.registered_at = time.time()
        agent_info.last_heartbeat = time.time()
        self._agents[agent_info.agent_id] = agent_info

        for cap in agent_info.capabilities:
            if cap not in self._capability_index:
                self._capability_index[cap] = []
            if agent_info.agent_id not in self._capability_index[cap]:
                self._capability_index[cap].append(agent_info.agent_id)

        self._stats["total_registrations"] += 1
        logger.info(f"Agent注册: {agent_info.agent_id}, 类型: {agent_info.agent_type}, 能力: {agent_info.capabilities}")
        return True

    def deregister(self, agent_id: str) -> bool:
        """注销Agent"""
        if agent_id not in self._agents:
            return False

        agent_info = self._agents.pop(agent_id)
        for cap in agent_info.capabilities:
            if cap in self._capability_index:
                self._capability_index[cap] = [
                    aid for aid in self._capability_index[cap] if aid != agent_id
                ]
                if not self._capability_index[cap]:
                    del self._capability_index[cap]

        self._stats["total_deregistrations"] += 1
        logger.info(f"Agent注销: {agent_id}")
        return True

    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """获取Agent信息"""
        return self._agents.get(agent_id)

    def update_heartbeat(self, agent_id: str) -> bool:
        """更新心跳"""
        agent = self._agents.get(agent_id)
        if agent:
            agent.last_heartbeat = time.time()
            if agent.status == AgentStatus.OFFLINE:
                agent.status = AgentStatus.ACTIVE
            return True
        return False

    def update_status(self, agent_id: str, status: AgentStatus) -> bool:
        """更新Agent状态"""
        agent = self._agents.get(agent_id)
        if agent:
            agent.status = status
            logger.info(f"Agent状态更新: {agent_id} -> {status.value}")
            return True
        return False

    def update_task_result(
        self,
        agent_id: str,
        success: bool,
        latency_ms: float = 0.0,
    ):
        """更新任务执行结果"""
        agent = self._agents.get(agent_id)
        if agent:
            agent.total_tasks += 1
            if success:
                agent.success_tasks += 1
            else:
                agent.failed_tasks += 1
            if latency_ms > 0:
                total = agent.total_tasks
                agent.avg_latency_ms = (
                    (agent.avg_latency_ms * (total - 1) + latency_ms) / total
                )

    def discover_by_capability(self, capability: str, status_filter: Optional[AgentStatus] = None) -> list[AgentInfo]:
        """按能力发现Agent"""
        self._stats["capability_queries"] += 1
        agent_ids = self._capability_index.get(capability, [])
        agents = [self._agents[aid] for aid in agent_ids if aid in self._agents]

        if status_filter:
            agents = [a for a in agents if a.status == status_filter]
        else:
            agents = [a for a in agents if a.status in (AgentStatus.ACTIVE, AgentStatus.BUSY)]

        agents.sort(key=lambda a: a.health_score, reverse=True)
        return agents

    def discover_by_type(self, agent_type: str) -> list[AgentInfo]:
        """按类型发现Agent"""
        return [
            a for a in self._agents.values()
            if a.agent_type == agent_type and a.status in (AgentStatus.ACTIVE, AgentStatus.BUSY)
        ]

    def get_all_agents(self, status_filter: Optional[AgentStatus] = None) -> list[AgentInfo]:
        """获取所有Agent"""
        agents = list(self._agents.values())
        if status_filter:
            agents = [a for a in agents if a.status == status_filter]
        return agents

    def check_health(self) -> dict[str, Any]:
        """健康检查所有Agent"""
        self._stats["health_checks"] += 1
        now = time.time()
        unhealthy_agents = []

        for agent_id, agent in list(self._agents.items()):
            if agent.status in (AgentStatus.ACTIVE, AgentStatus.BUSY, AgentStatus.DEGRADED):
                elapsed = now - agent.last_heartbeat
                if elapsed > self.config.heartbeat_timeout_seconds:
                    agent.status = AgentStatus.OFFLINE
                    unhealthy_agents.append(agent_id)
                    logger.warning(f"Agent心跳超时: {agent_id}, 超时 {elapsed:.0f}s")

                if self.config.enable_auto_deregistration:
                    if elapsed > self.config.auto_deregistration_timeout_seconds:
                        self.deregister(agent_id)
                        logger.warning(f"Agent自动注销: {agent_id}")

            if agent.total_tasks > 0:
                success_rate = agent.success_tasks / agent.total_tasks
                if success_rate < 0.5:
                    agent.health_score = max(0.1, success_rate)
                    agent.status = AgentStatus.DEGRADED
                else:
                    agent.health_score = min(1.0, success_rate)

        return {
            "total_agents": len(self._agents),
            "unhealthy_agents": unhealthy_agents,
            "active_agents": sum(1 for a in self._agents.values() if a.status == AgentStatus.ACTIVE),
            "degraded_agents": sum(1 for a in self._agents.values() if a.status == AgentStatus.DEGRADED),
            "offline_agents": sum(1 for a in self._agents.values() if a.status == AgentStatus.OFFLINE),
        }

    def get_stats(self) -> dict[str, Any]:
        """获取注册中心统计"""
        return {
            **self._stats,
            "registered_agents": len(self._agents),
            "capabilities": list(self._capability_index.keys()),
        }

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Agent标准处理接口"""
        action = input_data.get("action", "discover")

        if action == "register":
            info = AgentInfo(**input_data.get("agent_info", {}))
            success = self.register(info)
            return {"action": "register", "success": success}

        elif action == "deregister":
            success = self.deregister(input_data.get("agent_id", ""))
            return {"action": "deregister", "success": success}

        elif action == "discover":
            capability = input_data.get("capability", "")
            agents = self.discover_by_capability(capability)
            return {
                "action": "discover",
                "agents": [
                    {"agent_id": a.agent_id, "type": a.agent_type, "status": a.status.value, "health_score": a.health_score}
                    for a in agents
                ],
            }

        elif action == "heartbeat":
            success = self.update_heartbeat(input_data.get("agent_id", ""))
            return {"action": "heartbeat", "success": success}

        elif action == "health_check":
            result = self.check_health()
            return {"action": "health_check", "result": result}

        else:
            return {"action": action, "error": "未知操作"}

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        health_result = self.check_health()
        return {
            "status": "healthy" if not health_result["unhealthy_agents"] else "degraded",
            "registered_agents": len(self._agents),
            "health_result": health_result,
        }
