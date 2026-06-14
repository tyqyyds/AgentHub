import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from backend.observability.metrics import get_metrics_collector

logger = logging.getLogger(__name__)


class AgentHealthMonitor:
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

    def __init__(self, check_interval: int = 60):
        self._check_interval = check_interval
        self._agent_status: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._alert_callbacks: list = []

    def register_alert_callback(self, callback):
        self._alert_callbacks.append(callback)

    def _fire_alert(self, agent_id: str, old_status: str, new_status: str, details: dict):
        for cb in self._alert_callbacks:
            try:
                cb(agent_id, old_status, new_status, details)
            except Exception as e:
                logger.warning(f"Alert callback error: {e}")

    def _determine_status(self, health_data: dict) -> str:
        error_rate = health_data.get("error_rate", 0)
        latency_p95 = health_data.get("latency_p95", 0)
        total_calls = health_data.get("total_calls", 0)

        if total_calls == 0:
            return self.UNKNOWN

        if error_rate > 20 or latency_p95 > 10000:
            return self.UNHEALTHY

        if error_rate > 5 or latency_p95 > 5000:
            return self.DEGRADED

        return self.HEALTHY

    async def check_agent_health(self, agent_id: str) -> dict:
        collector = get_metrics_collector()
        health_data = collector.get_agent_health(agent_id)
        status = self._determine_status(health_data)
        health_data["status"] = status
        health_data["last_check_time"] = datetime.now(timezone.utc).isoformat()

        with self._lock:
            old_status = self._agent_status.get(agent_id, {}).get("status", self.UNKNOWN)
            self._agent_status[agent_id] = health_data

            if old_status != status and status != self.UNKNOWN:
                self._fire_alert(agent_id, old_status, status, health_data)

        return health_data

    async def check_all_agents(self) -> dict[str, dict]:
        collector = get_metrics_collector()
        all_health = collector.get_all_agents_health()
        results = {}

        for agent_id in all_health:
            results[agent_id] = await self.check_agent_health(agent_id)

        return results

    def get_agent_status(self, agent_id: str) -> dict:
        with self._lock:
            return self._agent_status.get(agent_id, {"agent_id": agent_id, "status": self.UNKNOWN})

    def get_all_status(self) -> dict[str, dict]:
        with self._lock:
            return dict(self._agent_status)

    async def start_periodic_check(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._periodic_loop())
        logger.info(f"Agent health monitor started, interval: {self._check_interval}s")

    async def _periodic_loop(self):
        while self._running:
            try:
                await self.check_all_agents()
            except Exception as e:
                logger.warning(f"Health check error: {e}")
            await asyncio.sleep(self._check_interval)

    async def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Agent health monitor stopped")


_health_monitor: Optional[AgentHealthMonitor] = None


def get_health_monitor() -> AgentHealthMonitor:
    global _health_monitor
    if _health_monitor is None:
        from backend.core.config import settings
        _health_monitor = AgentHealthMonitor(check_interval=settings.health_check_interval)
    return _health_monitor
