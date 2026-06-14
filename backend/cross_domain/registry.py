from typing import Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import asyncio
import logging
import threading

logger = logging.getLogger(__name__)


class AgentRegistration(BaseModel):
    agent_id: str
    capabilities: List[str] = []
    endpoint: str = ""
    ws_endpoint: str = ""
    tags: Dict[str, str] = Field(default_factory=dict)
    status: str = "online"
    last_heartbeat: float = Field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    cpu_load: float = 0.0
    memory_free: float = 100.0


class AgentRegistryCenter:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._agents: Dict[str, AgentRegistration] = {}
        self._ttl_seconds: int = 60
        self._cleanup_task: Optional[asyncio.Task] = None
        self._auto_register_local()

    def _auto_register_local(self):
        local_agent = AgentRegistration(
            agent_id="agenthub-local",
            capabilities=["intent_parsing", "qos_config", "event_diagnosis", "policy_planning", "execution"],
            endpoint="http://localhost:8000/api/v1",
            ws_endpoint="ws://localhost:8000/ws",
            tags={"domain": "local", "type": "agenthub"},
            status="online",
            cpu_load=0.0,
            memory_free=100.0,
        )
        self._agents[local_agent.agent_id] = local_agent
        logger.info("Auto-registered local AgentHub node: agenthub-local")

        # Auto-register 12 domain agents from seed data
        domain_agents = [
            ("agent_bandwidth_guarantor", ["qos_config", "intent_parsing"], "北京", 12.5),
            ("agent_fault_diagnostician", ["event_diagnosis", "intent_parsing"], "上海", 28.3),
            ("agent_config_generator", ["execution", "policy_planning"], "广州", 45.7),
            ("agent_security_scanner", ["event_diagnosis", "execution"], "深圳", 33.2),
            ("agent_healing_executor", ["execution", "event_diagnosis"], "成都", 21.8),
            ("agent_topology_analyzer", ["policy_planning", "intent_parsing"], "武汉", 15.6),
            ("agent_sla_predictor", ["qos_config", "policy_planning"], "南京", 38.4),
            ("agent_intent_parser", ["intent_parsing", "qos_config"], "杭州", 9.2),
            ("agent_traffic_shaper", ["qos_config", "execution"], "西安", 52.1),
            ("agent_link_manager", ["policy_planning", "execution"], "重庆", 27.9),
            ("agent_performance_monitor", ["qos_config", "event_diagnosis"], "长沙", 18.5),
            ("agent_access_controller", ["execution", "policy_planning"], "贵阳", 41.3),
        ]
        for agent_id, caps, city, cpu in domain_agents:
            self._agents[agent_id] = AgentRegistration(
                agent_id=agent_id,
                capabilities=caps,
                endpoint=f"http://localhost:8000/api/v1/agents/{agent_id}",
                ws_endpoint=f"ws://localhost:8000/ws/{agent_id}",
                tags={"domain": "network_ops", "city": city, "type": "domain_agent"},
                status="online",
                cpu_load=cpu,
                memory_free=round(100.0 - cpu * 0.8, 1),
            )
        logger.info(f"Auto-registered {len(domain_agents)} domain agents")

    def register(self, agent_info: dict) -> AgentRegistration:
        agent_id = agent_info.get("agent_id")
        if not agent_id:
            raise ValueError("agent_id is required")
        registration = AgentRegistration(
            agent_id=agent_id,
            capabilities=agent_info.get("capabilities", []),
            endpoint=agent_info.get("endpoint", ""),
            ws_endpoint=agent_info.get("ws_endpoint", ""),
            tags=agent_info.get("tags", {}),
            status="online",
            last_heartbeat=datetime.now(timezone.utc).timestamp(),
            cpu_load=agent_info.get("cpu_load", 0.0),
            memory_free=agent_info.get("memory_free", 100.0),
        )
        self._agents[agent_id] = registration
        logger.info(f"Agent registered: {agent_id}")
        return registration

    def deregister(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        logger.info(f"Agent deregistered: {agent_id}")
        return True

    def heartbeat(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        self._agents[agent_id].last_heartbeat = datetime.now(timezone.utc).timestamp()
        self._agents[agent_id].status = "online"
        return True

    def update_load(self, agent_id: str, cpu_load: float, memory_free: float) -> bool:
        if agent_id not in self._agents:
            return False
        self._agents[agent_id].cpu_load = cpu_load
        self._agents[agent_id].memory_free = memory_free
        return True

    def discover(self, capabilities: Optional[List[str]] = None, tags: Optional[Dict[str, str]] = None) -> List[AgentRegistration]:
        results = []
        for agent in self._agents.values():
            if agent.status != "online":
                continue
            if capabilities:
                if not any(cap in agent.capabilities for cap in capabilities):
                    continue
            if tags:
                if not all(agent.tags.get(k) == v for k, v in tags.items()):
                    continue
            results.append(agent)
        return results

    def get_agent(self, agent_id: str) -> Optional[AgentRegistration]:
        return self._agents.get(agent_id)

    def list_all(self) -> List[AgentRegistration]:
        return list(self._agents.values())

    def get_least_loaded(self, capability: Optional[str] = None) -> Optional[AgentRegistration]:
        candidates = []
        for agent in self._agents.values():
            if agent.status != "online":
                continue
            if capability and capability not in agent.capabilities:
                continue
            candidates.append(agent)
        if not candidates:
            return None
        return min(candidates, key=lambda a: a.cpu_load)

    async def cleanup_expired(self):
        now = datetime.now(timezone.utc).timestamp()
        expired_ids = []
        for agent_id, agent in self._agents.items():
            if agent_id == "agenthub-local":
                continue
            if now - agent.last_heartbeat > self._ttl_seconds:
                expired_ids.append(agent_id)
        for agent_id in expired_ids:
            self._agents[agent_id].status = "offline"
            logger.info(f"Agent heartbeat expired, set offline: {agent_id}")
        return expired_ids

    def start_cleanup_loop(self):
        async def _loop():
            while True:
                try:
                    await self.cleanup_expired()
                except Exception as e:
                    logger.error(f"Cleanup loop error: {e}")
                await asyncio.sleep(10)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._cleanup_task = asyncio.ensure_future(_loop())
            else:
                self._cleanup_task = loop.create_task(_loop())
        except RuntimeError:
            pass

    def stop_cleanup_loop(self):
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

    def get_topology(self) -> dict:
        nodes = []
        edges = []
        for agent in self._agents.values():
            is_local = "agenthub-local" in agent.agent_id
            nodes.append({
                "id": agent.agent_id,
                "label": agent.agent_id,
                "type": "local" if is_local else "remote",
                "capabilities": agent.capabilities,
                "status": agent.status,
                "cpu_load": agent.cpu_load,
                "memory_free": agent.memory_free,
                "tags": agent.tags,
                "endpoint": agent.endpoint,
            })
            if not is_local:
                edges.append({
                    "source": "agenthub-local",
                    "target": agent.agent_id,
                    "label": "A2A",
                    "type": "a2a",
                    "status": agent.status,
                })
        return {"nodes": nodes, "edges": edges}


registry_center = AgentRegistryCenter()
