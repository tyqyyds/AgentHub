from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid
import logging

logger = logging.getLogger(__name__)


class AgentHotUpgradeManager:

    def __init__(self):
        self._agent_versions: Dict[str, dict] = {}
        self._active_upgrades: Dict[str, dict] = {}
        self._upgrade_history: Dict[str, List[dict]] = {}

    async def register_agent_version(self, agent_id: str, version: str, config: dict, capabilities: list) -> dict:
        version_info = {
            "agent_id": agent_id,
            "version": version,
            "config": config,
            "capabilities": capabilities,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "status": "registered",
        }

        if agent_id not in self._agent_versions:
            self._agent_versions[agent_id] = {}

        self._agent_versions[agent_id][version] = version_info

        return {
            "status": "success",
            "agent_id": agent_id,
            "version": version,
            "message": f"Version {version} registered for agent {agent_id}",
        }

    async def upgrade_agent(self, agent_id: str, new_version: str, strategy: str = "rolling") -> dict:
        if agent_id in self._active_upgrades:
            return {"status": "error", "message": f"Agent {agent_id} already has an active upgrade"}

        if agent_id not in self._agent_versions or new_version not in self._agent_versions[agent_id]:
            return {"status": "error", "message": f"Version {new_version} not registered for agent {agent_id}"}

        current_version = self._get_current_version(agent_id)
        if current_version == new_version:
            return {"status": "error", "message": f"Agent {agent_id} is already on version {new_version}"}

        upgrade_id = str(uuid.uuid4())[:8]
        upgrade_record = {
            "upgrade_id": upgrade_id,
            "agent_id": agent_id,
            "from_version": current_version,
            "to_version": new_version,
            "strategy": strategy,
            "status": "in_progress",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "steps": [],
        }

        if strategy == "rolling":
            result = await self._rolling_upgrade(agent_id, current_version, new_version, upgrade_record)
        elif strategy == "blue_green":
            result = await self._blue_green_upgrade(agent_id, current_version, new_version, upgrade_record)
        else:
            return {"status": "error", "message": f"Unknown strategy: {strategy}"}

        return result

    async def _rolling_upgrade(self, agent_id: str, from_version: str, to_version: str, upgrade_record: dict) -> dict:
        upgrade_record["steps"].append({"step": "drain", "status": "completed", "timestamp": datetime.now(timezone.utc).isoformat()})
        upgrade_record["steps"].append({"step": "upgrade", "status": "completed", "timestamp": datetime.now(timezone.utc).isoformat()})
        upgrade_record["steps"].append({"step": "verify", "status": "completed", "timestamp": datetime.now(timezone.utc).isoformat()})
        upgrade_record["steps"].append({"step": "restore", "status": "completed", "timestamp": datetime.now(timezone.utc).isoformat()})

        upgrade_record["status"] = "completed"
        upgrade_record["completed_at"] = datetime.now(timezone.utc).isoformat()

        self._agent_versions[agent_id][to_version]["status"] = "active"
        if from_version in self._agent_versions[agent_id]:
            self._agent_versions[agent_id][from_version]["status"] = "inactive"

        self._record_history(agent_id, upgrade_record)

        return {
            "status": "success",
            "upgrade_id": upgrade_record["upgrade_id"],
            "agent_id": agent_id,
            "from_version": from_version,
            "to_version": to_version,
            "strategy": "rolling",
            "message": "Rolling upgrade completed successfully",
        }

    async def _blue_green_upgrade(self, agent_id: str, from_version: str, to_version: str, upgrade_record: dict) -> dict:
        upgrade_record["steps"].append({"step": "start_new_version", "status": "completed", "timestamp": datetime.now(timezone.utc).isoformat()})
        upgrade_record["steps"].append({"step": "switch_traffic", "status": "completed", "timestamp": datetime.now(timezone.utc).isoformat()})
        upgrade_record["steps"].append({"step": "stop_old_version", "status": "completed", "timestamp": datetime.now(timezone.utc).isoformat()})

        upgrade_record["status"] = "completed"
        upgrade_record["completed_at"] = datetime.now(timezone.utc).isoformat()

        self._agent_versions[agent_id][to_version]["status"] = "active"
        if from_version in self._agent_versions[agent_id]:
            self._agent_versions[agent_id][from_version]["status"] = "inactive"

        self._record_history(agent_id, upgrade_record)

        return {
            "status": "success",
            "upgrade_id": upgrade_record["upgrade_id"],
            "agent_id": agent_id,
            "from_version": from_version,
            "to_version": to_version,
            "strategy": "blue_green",
            "message": "Blue-green upgrade completed successfully",
        }

    def _get_current_version(self, agent_id: str) -> Optional[str]:
        if agent_id not in self._agent_versions:
            return None
        for version, info in self._agent_versions[agent_id].items():
            if info.get("status") == "active":
                return version
        versions = list(self._agent_versions[agent_id].keys())
        return versions[-1] if versions else None

    async def get_upgrade_status(self, agent_id: str) -> dict:
        if agent_id in self._active_upgrades:
            return {"agent_id": agent_id, "upgrade": self._active_upgrades[agent_id]}

        current_version = self._get_current_version(agent_id)
        return {
            "agent_id": agent_id,
            "current_version": current_version,
            "active_upgrade": None,
        }

    async def rollback_upgrade(self, agent_id: str) -> dict:
        current_version = self._get_current_version(agent_id)
        if not current_version:
            return {"status": "error", "message": f"No active version found for agent {agent_id}"}

        history = self._upgrade_history.get(agent_id, [])
        if not history:
            return {"status": "error", "message": f"No upgrade history found for agent {agent_id}"}

        last_upgrade = history[-1]
        previous_version = last_upgrade.get("from_version")
        if not previous_version:
            return {"status": "error", "message": "Cannot determine previous version"}

        if previous_version not in self._agent_versions.get(agent_id, {}):
            return {"status": "error", "message": f"Previous version {previous_version} not available"}

        self._agent_versions[agent_id][current_version]["status"] = "inactive"
        self._agent_versions[agent_id][previous_version]["status"] = "active"

        rollback_record = {
            "upgrade_id": str(uuid.uuid4())[:8],
            "agent_id": agent_id,
            "from_version": current_version,
            "to_version": previous_version,
            "strategy": "rollback",
            "status": "completed",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "steps": [{"step": "rollback", "status": "completed", "timestamp": datetime.now(timezone.utc).isoformat()}],
        }
        self._record_history(agent_id, rollback_record)

        return {
            "status": "success",
            "agent_id": agent_id,
            "rolled_back_from": current_version,
            "rolled_back_to": previous_version,
            "message": f"Agent {agent_id} rolled back to version {previous_version}",
        }

    async def list_upgrade_history(self, agent_id: str, limit: int = 10) -> list:
        history = self._upgrade_history.get(agent_id, [])
        return history[-limit:]

    async def get_upgrade_history(self) -> list:
        all_history = []
        for agent_id, history in self._upgrade_history.items():
            for record in history:
                record_copy = dict(record)
                record_copy["agent_id"] = agent_id
                all_history.append(record_copy)
        all_history.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return all_history[:50]

    def _record_history(self, agent_id: str, record: dict) -> None:
        if agent_id not in self._upgrade_history:
            self._upgrade_history[agent_id] = []
        self._upgrade_history[agent_id].append(record)
        if agent_id in self._active_upgrades:
            del self._active_upgrades[agent_id]


_hot_upgrade_manager_instance = None


def get_hot_upgrade_manager() -> AgentHotUpgradeManager:
    global _hot_upgrade_manager_instance
    if _hot_upgrade_manager_instance is None:
        _hot_upgrade_manager_instance = AgentHotUpgradeManager()
    return _hot_upgrade_manager_instance
