from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import async_session_maker
from backend.database.models import BehaviorAnomaly
from datetime import datetime, timezone
from typing import Optional, Dict, List
from collections import deque
import uuid
import logging

logger = logging.getLogger(__name__)

MAX_ACTIONS_PER_USER = 1000


class BehaviorAnomalyDetector:

    def __init__(self):
        self._user_actions: Dict[str, deque] = {}
        self._user_device_access: Dict[str, set] = {}
        self._user_approval_counts: Dict[str, deque] = {}
        self._user_config_changes: Dict[str, deque] = {}

    def record_user_action(self, user_id: str, action: str, target: str = None, metadata: dict = None) -> None:
        if user_id not in self._user_actions:
            self._user_actions[user_id] = deque(maxlen=MAX_ACTIONS_PER_USER)

        self._user_actions[user_id].append({
            "action": action,
            "target": target,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if target and action in ("access", "connect", "ssh", "netconf"):
            if user_id not in self._user_device_access:
                self._user_device_access[user_id] = set()
            self._user_device_access[user_id].add(target)

        if action in ("approve", "reject"):
            if user_id not in self._user_approval_counts:
                self._user_approval_counts[user_id] = deque(maxlen=MAX_ACTIONS_PER_USER)
            self._user_approval_counts[user_id].append({
                "action": action,
                "target": target,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        if action in ("config_change", "apply_config", "modify_config"):
            if user_id not in self._user_config_changes:
                self._user_config_changes[user_id] = deque(maxlen=MAX_ACTIONS_PER_USER)
            self._user_config_changes[user_id].append({
                "action": action,
                "target": target,
                "metadata": metadata or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    async def detect_high_frequency_commands(self, user_id: str, time_window_minutes: int = 5, threshold: int = 20) -> Optional[dict]:
        actions = self._user_actions.get(user_id, deque())
        if len(actions) < threshold:
            return None

        now = datetime.now(timezone.utc)
        window_start = now.timestamp() - (time_window_minutes * 60)
        recent_count = 0

        for action in reversed(actions):
            try:
                action_time = datetime.fromisoformat(action["timestamp"]).timestamp()
                if action_time < window_start:
                    break
                recent_count += 1
            except (ValueError, KeyError):
                continue

        if recent_count >= threshold:
            anomaly = await self._create_anomaly(
                user_id=user_id,
                anomaly_type="high_frequency_commands",
                severity="high",
                description=f"User {user_id} issued {recent_count} commands within {time_window_minutes} minutes (threshold: {threshold})",
                evidence={
                    "command_count": recent_count,
                    "time_window_minutes": time_window_minutes,
                    "threshold": threshold,
                    "recent_actions": list(actions)[-10:] if len(actions) > 10 else list(actions),
                },
            )
            return anomaly
        return None

    async def detect_unusual_device_access(self, user_id: str, device_id: str) -> Optional[dict]:
        accessed_devices = self._user_device_access.get(user_id, set())

        if device_id not in accessed_devices:
            anomaly = await self._create_anomaly(
                user_id=user_id,
                anomaly_type="unusual_device_access",
                severity="medium",
                description=f"User {user_id} accessed device {device_id} outside their normal pattern",
                evidence={
                    "accessed_device": device_id,
                    "known_devices": list(accessed_devices),
                    "is_new_device": True,
                },
            )
            return anomaly
        return None

    async def detect_abnormal_approval_pattern(self, user_id: str) -> Optional[dict]:
        approvals = self._user_approval_counts.get(user_id, deque())
        if len(approvals) < 5:
            return None

        now = datetime.now(timezone.utc)
        one_hour_ago = now.timestamp() - 3600
        recent_approvals = []
        recent_rejections = []

        for a in reversed(approvals):
            try:
                action_time = datetime.fromisoformat(a["timestamp"]).timestamp()
                if action_time < one_hour_ago:
                    break
                if a["action"] == "approve":
                    recent_approvals.append(a)
                else:
                    recent_rejections.append(a)
            except (ValueError, KeyError):
                continue

        total = len(recent_approvals) + len(recent_rejections)
        if total >= 10:
            approval_rate = len(recent_approvals) / total if total > 0 else 0
            if approval_rate > 0.95 or approval_rate < 0.05:
                anomaly = await self._create_anomaly(
                    user_id=user_id,
                    anomaly_type="abnormal_approval_pattern",
                    severity="medium",
                    description=f"User {user_id} has abnormal approval pattern: {len(recent_approvals)} approvals, {len(recent_rejections)} rejections in last hour",
                    evidence={
                        "approval_rate": approval_rate,
                        "recent_approvals": len(recent_approvals),
                        "recent_rejections": len(recent_rejections),
                        "total_actions": total,
                    },
                )
                return anomaly
        return None

    async def detect_suspicious_config_changes(self, user_id: str, changes: list) -> Optional[dict]:
        if not changes:
            return None

        suspicious_keywords = ["acl", "firewall", "routing", "password", "admin", "privilege", "enable"]
        suspicious_changes = []

        for change in changes:
            change_str = str(change).lower()
            for keyword in suspicious_keywords:
                if keyword in change_str:
                    suspicious_changes.append({"change": change, "keyword": keyword})
                    break

        if suspicious_changes:
            severity = "critical" if len(suspicious_changes) >= 3 else "high"
            anomaly = await self._create_anomaly(
                user_id=user_id,
                anomaly_type="suspicious_config_change",
                severity=severity,
                description=f"User {user_id} made {len(suspicious_changes)} suspicious configuration changes",
                evidence={
                    "suspicious_changes": suspicious_changes,
                    "total_changes": len(changes),
                    "keywords_matched": list(set(sc["keyword"] for sc in suspicious_changes)),
                },
            )
            return anomaly
        return None

    async def _create_anomaly(self, user_id: str, anomaly_type: str, severity: str, description: str, evidence: dict) -> dict:
        anomaly_id = f"ano_{uuid.uuid4().hex[:8]}"

        async with async_session_maker() as session:
            anomaly = BehaviorAnomaly(
                anomaly_id=anomaly_id,
                user_id=user_id,
                anomaly_type=anomaly_type,
                severity=severity,
                description=description,
                evidence=evidence,
                status="detected",
            )
            session.add(anomaly)
            await session.commit()

        return {
            "anomaly_id": anomaly_id,
            "user_id": user_id,
            "anomaly_type": anomaly_type,
            "severity": severity,
            "description": description,
            "evidence": evidence,
            "status": "detected",
        }

    async def get_user_baseline(self, user_id: str) -> dict:
        actions = self._user_actions.get(user_id, deque())
        devices = self._user_device_access.get(user_id, set())
        approvals = self._user_approval_counts.get(user_id, deque())
        config_changes = self._user_config_changes.get(user_id, deque())

        return {
            "user_id": user_id,
            "total_actions_recorded": len(actions),
            "devices_accessed": list(devices),
            "device_count": len(devices),
            "approval_actions": len(approvals),
            "config_change_actions": len(config_changes),
        }

    async def list_anomalies(self, status: str = None, severity: str = None, limit: int = 20) -> list:
        async with async_session_maker() as session:
            query = select(BehaviorAnomaly).order_by(desc(BehaviorAnomaly.detected_at))
            if status:
                query = query.where(BehaviorAnomaly.status == status)
            if severity:
                query = query.where(BehaviorAnomaly.severity == severity)
            query = query.limit(limit)

            result = await session.execute(query)
            anomalies = result.scalars().all()

            return [
                {
                    "anomaly_id": a.anomaly_id,
                    "user_id": a.user_id,
                    "anomaly_type": a.anomaly_type,
                    "severity": a.severity,
                    "description": a.description,
                    "evidence": a.evidence,
                    "status": a.status,
                    "investigated_by": a.investigated_by,
                    "resolution_notes": a.resolution_notes,
                    "detected_at": a.detected_at.isoformat() if a.detected_at else None,
                    "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                }
                for a in anomalies
            ]

    async def resolve_anomaly(self, anomaly_id: str, resolution_notes: str, investigated_by: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(BehaviorAnomaly).where(BehaviorAnomaly.anomaly_id == anomaly_id)
            )
            anomaly = result.scalars().first()
            if not anomaly:
                return {"status": "error", "message": f"Anomaly {anomaly_id} not found"}

            anomaly.status = "resolved"
            anomaly.resolution_notes = resolution_notes
            anomaly.investigated_by = investigated_by
            anomaly.resolved_at = datetime.now(timezone.utc)
            await session.commit()

            return {
                "status": "success",
                "anomaly_id": anomaly_id,
                "new_status": "resolved",
                "investigated_by": investigated_by,
            }

    async def mark_false_positive(self, anomaly_id: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(BehaviorAnomaly).where(BehaviorAnomaly.anomaly_id == anomaly_id)
            )
            anomaly = result.scalars().first()
            if not anomaly:
                return {"status": "error", "message": f"Anomaly {anomaly_id} not found"}

            anomaly.status = "false_positive"
            anomaly.resolved_at = datetime.now(timezone.utc)
            await session.commit()

            return {
                "status": "success",
                "anomaly_id": anomaly_id,
                "new_status": "false_positive",
            }


_behavior_anomaly_detector_instance = None


def get_behavior_anomaly_detector() -> BehaviorAnomalyDetector:
    global _behavior_anomaly_detector_instance
    if _behavior_anomaly_detector_instance is None:
        _behavior_anomaly_detector_instance = BehaviorAnomalyDetector()
    return _behavior_anomaly_detector_instance
