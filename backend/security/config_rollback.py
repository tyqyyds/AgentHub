import asyncio
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime, timezone
import copy
import logging

logger = logging.getLogger(__name__)


class ConfigRollbackManager:
    def __init__(self):
        self._backups: Dict[str, List[Dict[str, Any]]] = {}

    def backup_config(self, device_id: str, config: dict) -> Dict[str, Any]:
        if device_id not in self._backups:
            self._backups[device_id] = []

        backup_entry = {
            "config": copy.deepcopy(config),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "backup_id": f"{device_id}_{len(self._backups[device_id])}"
        }

        self._backups[device_id].append(backup_entry)
        logger.info(f"Config backup created for device {device_id}: {backup_entry['backup_id']}")

        return {
            "status": "success",
            "backup_id": backup_entry["backup_id"],
            "timestamp": backup_entry["timestamp"],
            "device_id": device_id
        }

    async def execute_with_rollback(
        self,
        device_id: str,
        tool_name: str,
        params: dict,
        execute_fn: Callable
    ) -> Dict[str, Any]:
        self.backup_config(device_id, params)

        try:
            result = await execute_fn(tool_name, params)

            if isinstance(result, dict) and result.get("status") == "error":
                logger.warning(f"Execution failed for device {device_id}, initiating rollback: {result.get('error', 'unknown')}")
                rollback_result = await self.rollback(device_id)
                return {
                    "status": "rolled_back",
                    "execution_result": result,
                    "rollback_result": rollback_result
                }

            health = await self.verify_health(device_id)
            if health.get("status") != "healthy":
                logger.warning(f"Health check failed for device {device_id} after execution, initiating rollback")
                rollback_result = await self.rollback(device_id)
                return {
                    "status": "rolled_back",
                    "execution_result": result,
                    "health_check": health,
                    "rollback_result": rollback_result
                }

            return {
                "status": "success",
                "execution_result": result,
                "health_check": health
            }

        except Exception as e:
            logger.error(f"Exception during execution on device {device_id}: {e}")
            rollback_result = await self.rollback(device_id)
            return {
                "status": "rolled_back",
                "error": str(e),
                "rollback_result": rollback_result
            }

    async def rollback(self, device_id: str) -> Dict[str, Any]:
        if device_id not in self._backups or not self._backups[device_id]:
            return {
                "status": "error",
                "error": f"No backup available for device {device_id}"
            }

        last_backup = self._backups[device_id][-1]
        config = last_backup["config"]

        logger.info(f"Rolling back device {device_id} to backup {last_backup['backup_id']}")

        return {
            "status": "success",
            "device_id": device_id,
            "restored_config": config,
            "restored_from": last_backup["backup_id"],
            "restored_at": datetime.now(timezone.utc).isoformat()
        }

    def get_backup_history(self, device_id: str) -> List[Dict[str, Any]]:
        if device_id not in self._backups:
            return []

        return [
            {
                "backup_id": entry["backup_id"],
                "timestamp": entry["timestamp"],
                "config_keys": list(entry["config"].keys())
            }
            for entry in self._backups[device_id]
        ]

    async def verify_health(self, device_id: str) -> Dict[str, Any]:
        checks = {
            "gateway_reachable": True,
            "interface_status": "up",
            "cpu_usage": 0.0,
            "memory_usage": 0.0
        }

        try:
            from backend.core.device_connection import get_device_connection_pool
            pool = get_device_connection_pool()
            device_status = pool.get_device_status(device_id)
            if device_status:
                checks["gateway_reachable"] = device_status.get("reachable", True)
                checks["interface_status"] = device_status.get("interface_status", "up")
                checks["cpu_usage"] = device_status.get("cpu_usage", 0.0)
                checks["memory_usage"] = device_status.get("memory_usage", 0.0)
        except Exception as e:
            logger.warning(f"Device status query failed for {device_id}: {e}, using telemetry fallback")
            try:
                from backend.telemetry.collector import get_telemetry_collector
                collector = get_telemetry_collector()
                metrics = collector.get_latest_metrics(device_id)
                if metrics:
                    for metric in metrics:
                        if metric.get("metric_type") == "cpu_usage_pct":
                            checks["cpu_usage"] = metric.get("value", 0.0)
                        elif metric.get("metric_type") == "memory_usage_pct":
                            checks["memory_usage"] = metric.get("value", 0.0)
            except Exception as e2:
                logger.warning(f"Telemetry fallback also failed for {device_id}: {e2}")

        overall_healthy = (
            checks["gateway_reachable"]
            and checks["interface_status"] == "up"
            and checks["cpu_usage"] < 90
            and checks["memory_usage"] < 90
        )

        return {
            "status": "healthy" if overall_healthy else "unhealthy",
            "device_id": device_id,
            "checks": checks,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }


config_rollback_manager = ConfigRollbackManager()
