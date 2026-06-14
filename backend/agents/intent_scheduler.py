from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import async_session_maker
from backend.database.models import IntentScheduleRecord
from backend.core.config import settings
from collections import defaultdict
import asyncio
import logging

logger = logging.getLogger(__name__)

PRIORITY_LEVELS = {
    "critical": (9, 10),
    "high": (7, 8),
    "medium": (4, 6),
    "low": (1, 3),
}


def _priority_level(priority: int) -> str:
    for level, (lo, hi) in PRIORITY_LEVELS.items():
        if lo <= priority <= hi:
            return level
    return "medium"


class ResourcePool:
    def __init__(
        self,
        max_device_slots: int = 10,
        max_bandwidth_mbps: int = 10000,
        max_concurrent: int = 5,
    ):
        self.max_device_slots = max_device_slots
        self.max_bandwidth_mbps = max_bandwidth_mbps
        self.max_concurrent = max_concurrent
        self.used_device_slots = 0
        self.used_bandwidth_mbps = 0
        self.running_count = 0
        self._allocations: Dict[int, Dict] = {}

    def available_device_slots(self) -> int:
        return self.max_device_slots - self.used_device_slots

    def available_bandwidth_mbps(self) -> int:
        return self.max_bandwidth_mbps - self.used_bandwidth_mbps

    def available_concurrent(self) -> int:
        return self.max_concurrent - self.running_count

    def check_availability(self, requirements: Dict) -> bool:
        if not requirements:
            return self.available_concurrent() > 0
        device_slots = requirements.get("device_slots", 0)
        bandwidth_mbps = requirements.get("bandwidth_mbps", 0)
        if device_slots > self.available_device_slots():
            return False
        if bandwidth_mbps > self.available_bandwidth_mbps():
            return False
        if self.available_concurrent() <= 0:
            return False
        return True

    def allocate(self, intent_id: int, requirements: Dict) -> bool:
        if not self.check_availability(requirements):
            return False
        device_slots = requirements.get("device_slots", 0)
        bandwidth_mbps = requirements.get("bandwidth_mbps", 0)
        self.used_device_slots += device_slots
        self.used_bandwidth_mbps += bandwidth_mbps
        self.running_count += 1
        self._allocations[intent_id] = {
            "device_slots": device_slots,
            "bandwidth_mbps": bandwidth_mbps,
        }
        return True

    def release(self, intent_id: int) -> bool:
        alloc = self._allocations.pop(intent_id, None)
        if alloc is None:
            return False
        self.used_device_slots -= alloc["device_slots"]
        self.used_bandwidth_mbps -= alloc["bandwidth_mbps"]
        self.running_count -= 1
        return True

    def status(self) -> Dict:
        return {
            "max_device_slots": self.max_device_slots,
            "used_device_slots": self.used_device_slots,
            "available_device_slots": self.available_device_slots(),
            "max_bandwidth_mbps": self.max_bandwidth_mbps,
            "used_bandwidth_mbps": self.used_bandwidth_mbps,
            "available_bandwidth_mbps": self.available_bandwidth_mbps(),
            "max_concurrent": self.max_concurrent,
            "running_count": self.running_count,
            "available_concurrent": self.available_concurrent(),
        }


class IntentScheduler:
    def __init__(self):
        self.resource_pool = ResourcePool(
            max_device_slots=settings.scheduler_max_device_slots,
            max_bandwidth_mbps=settings.scheduler_max_bandwidth_mbps,
            max_concurrent=settings.scheduler_max_concurrent,
        )
        self._aging_interval = settings.scheduler_priority_aging_interval
        self._aging_threshold = settings.scheduler_priority_aging_threshold
        self._rate_limit_per_type = settings.scheduler_rate_limit_per_type
        self._execution_rates: Dict[str, List[datetime]] = defaultdict(list)
        self._aging_task: Optional[asyncio.Task] = None

    async def start_aging(self):
        if self._aging_task is None or self._aging_task.done():
            self._aging_task = asyncio.create_task(self._aging_loop())

    async def stop_aging(self):
        if self._aging_task and not self._aging_task.done():
            self._aging_task.cancel()
            try:
                await self._aging_task
            except asyncio.CancelledError:
                pass

    async def _aging_loop(self):
        while True:
            try:
                await asyncio.sleep(self._aging_interval)
                await self.rebalance_queue()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Priority aging loop error: {e}")

    def _check_rate_limit(self, intent_type: str) -> bool:
        now = datetime.utcnow()
        cutoff = now.replace(minute=now.minute - 1) if now.minute > 0 else now
        self._execution_rates[intent_type] = [
            t for t in self._execution_rates[intent_type]
            if (now - t).total_seconds() < 60
        ]
        if len(self._execution_rates[intent_type]) >= self._rate_limit_per_type:
            return False
        return True

    def _record_execution(self, intent_type: str):
        self._execution_rates[intent_type].append(datetime.utcnow())

    async def enqueue(
        self,
        intent_id: int,
        priority: int = 5,
        resource_requirements: Optional[Dict] = None,
    ) -> IntentScheduleRecord:
        priority = max(1, min(10, priority))
        async with async_session_maker() as session:
            count_result = await session.execute(
                select(func.count(IntentScheduleRecord.id)).where(
                    IntentScheduleRecord.status.in_(["queued", "running"])
                )
            )
            queue_position = count_result.scalar() or 0

            record = IntentScheduleRecord(
                intent_id=intent_id,
                priority=priority,
                queue_position=queue_position,
                resource_quota=resource_requirements,
                status="queued",
                scheduled_at=datetime.utcnow(),
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            logger.info(
                f"Enqueued intent {intent_id} with priority {priority} "
                f"(level={_priority_level(priority)}, position={queue_position})"
            )
            return record

    async def dequeue(self) -> Optional[IntentScheduleRecord]:
        async with async_session_maker() as session:
            queued = await session.execute(
                select(IntentScheduleRecord)
                .where(IntentScheduleRecord.status == "queued")
                .order_by(
                    IntentScheduleRecord.priority.desc(),
                    IntentScheduleRecord.scheduled_at.asc(),
                )
            )
            candidates = list(queued.scalars().all())

            for candidate in candidates:
                requirements = candidate.resource_quota or {}
                if not self.resource_pool.check_availability(requirements):
                    continue
                if not self.resource_pool.allocate(candidate.intent_id, requirements):
                    continue

                now = datetime.utcnow()
                candidate.status = "running"
                candidate.started_at = now
                if candidate.scheduled_at:
                    delta = now - candidate.scheduled_at
                    candidate.wait_time_ms = int(delta.total_seconds() * 1000)
                candidate.queue_position = 0
                await session.commit()
                await session.refresh(candidate)
                logger.info(
                    f"Dequeued intent {candidate.intent_id} (priority={candidate.priority})"
                )
                return candidate

            return None

    async def peek(self) -> Optional[IntentScheduleRecord]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentScheduleRecord)
                .where(IntentScheduleRecord.status == "queued")
                .order_by(
                    IntentScheduleRecord.priority.desc(),
                    IntentScheduleRecord.scheduled_at.asc(),
                )
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def preempt(self, intent_id: int, reason: str = "") -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentScheduleRecord)
                .where(
                    IntentScheduleRecord.intent_id == intent_id,
                    IntentScheduleRecord.status == "running",
                )
                .order_by(IntentScheduleRecord.id.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()
            if not record:
                logger.warning(f"Cannot preempt intent {intent_id}: not running")
                return False

            now = datetime.utcnow()
            record.status = "preempted"
            record.preempt_count += 1
            if record.started_at:
                delta = now - record.started_at
                record.execution_time_ms = int(delta.total_seconds() * 1000)
            self.resource_pool.release(intent_id)
            await session.commit()
            logger.info(
                f"Preempted intent {intent_id}: {reason} "
                f"(preempt_count={record.preempt_count})"
            )
            return True

    async def resume(self, intent_id: int) -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentScheduleRecord)
                .where(
                    IntentScheduleRecord.intent_id == intent_id,
                    IntentScheduleRecord.status == "preempted",
                )
                .order_by(IntentScheduleRecord.id.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()
            if not record:
                logger.warning(f"Cannot resume intent {intent_id}: not preempted")
                return False

            requirements = record.resource_quota or {}
            if not self.resource_pool.check_availability(requirements):
                record.status = "queued"
                record.scheduled_at = datetime.utcnow()
                await session.commit()
                logger.info(
                    f"Intent {intent_id} re-queued (resources unavailable for resume)"
                )
                return True

            self.resource_pool.allocate(intent_id, requirements)
            record.status = "running"
            record.started_at = datetime.utcnow()
            await session.commit()
            logger.info(f"Resumed intent {intent_id}")
            return True

    async def complete(self, intent_id: int) -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentScheduleRecord)
                .where(
                    IntentScheduleRecord.intent_id == intent_id,
                    IntentScheduleRecord.status == "running",
                )
                .order_by(IntentScheduleRecord.id.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()
            if not record:
                logger.warning(f"Cannot complete intent {intent_id}: not running")
                return False

            now = datetime.utcnow()
            record.status = "completed"
            record.completed_at = now
            if record.started_at:
                delta = now - record.started_at
                record.execution_time_ms = int(delta.total_seconds() * 1000)
            self.resource_pool.release(intent_id)
            await session.commit()
            logger.info(f"Completed intent {intent_id}")
            return True

    async def fail(self, intent_id: int, reason: str = "") -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentScheduleRecord)
                .where(
                    IntentScheduleRecord.intent_id == intent_id,
                    IntentScheduleRecord.status.in_(["running", "queued", "preempted"]),
                )
                .order_by(IntentScheduleRecord.id.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()
            if not record:
                logger.warning(f"Cannot fail intent {intent_id}: not found in active state")
                return False

            now = datetime.utcnow()
            previous_status = record.status
            if record.started_at and previous_status == "running":
                delta = now - record.started_at
                record.execution_time_ms = int(delta.total_seconds() * 1000)
            record.status = "failed"
            record.completed_at = now
            if previous_status == "running" or record.intent_id in self.resource_pool._allocations:
                self.resource_pool.release(intent_id)
            await session.commit()
            logger.info(f"Failed intent {intent_id}: {reason}")
            return True

    async def get_queue_status(self) -> Dict:
        async with async_session_maker() as session:
            status_counts = {}
            for status_val in ["queued", "running", "completed", "preempted", "failed"]:
                result = await session.execute(
                    select(func.count(IntentScheduleRecord.id)).where(
                        IntentScheduleRecord.status == status_val
                    )
                )
                status_counts[status_val] = result.scalar() or 0

            queued_result = await session.execute(
                select(IntentScheduleRecord.priority, func.count(IntentScheduleRecord.id))
                .where(IntentScheduleRecord.status == "queued")
                .group_by(IntentScheduleRecord.priority)
            )
            by_priority = {}
            for priority, count in queued_result.all():
                level = _priority_level(priority)
                by_priority[level] = by_priority.get(level, 0) + count

            return {
                "pending_by_priority": by_priority,
                "queued_count": status_counts.get("queued", 0),
                "running_count": status_counts.get("running", 0),
                "completed_count": status_counts.get("completed", 0),
                "preempted_count": status_counts.get("preempted", 0),
                "failed_count": status_counts.get("failed", 0),
                "resources": self.resource_pool.status(),
            }

    async def get_intent_position(self, intent_id: int) -> int:
        async with async_session_maker() as session:
            running_result = await session.execute(
                select(IntentScheduleRecord)
                .where(
                    IntentScheduleRecord.intent_id == intent_id,
                    IntentScheduleRecord.status == "running",
                )
            )
            if running_result.scalar_one_or_none():
                return 0

            target_result = await session.execute(
                select(IntentScheduleRecord)
                .where(
                    IntentScheduleRecord.intent_id == intent_id,
                    IntentScheduleRecord.status == "queued",
                )
                .order_by(IntentScheduleRecord.id.desc())
                .limit(1)
            )
            target = target_result.scalar_one_or_none()
            if not target:
                return -1

            ahead_result = await session.execute(
                select(func.count(IntentScheduleRecord.id)).where(
                    IntentScheduleRecord.status == "queued",
                    IntentScheduleRecord.priority > target.priority,
                )
            )
            ahead_higher = ahead_result.scalar() or 0

            same_priority_ahead = await session.execute(
                select(func.count(IntentScheduleRecord.id)).where(
                    IntentScheduleRecord.status == "queued",
                    IntentScheduleRecord.priority == target.priority,
                    IntentScheduleRecord.scheduled_at < target.scheduled_at,
                )
            )
            ahead_same = same_priority_ahead.scalar() or 0

            return ahead_higher + ahead_same + 1

    async def rebalance_queue(self) -> List[IntentScheduleRecord]:
        async with async_session_maker() as session:
            now = datetime.utcnow()
            threshold_seconds = self._aging_threshold

            queued_result = await session.execute(
                select(IntentScheduleRecord).where(
                    IntentScheduleRecord.status == "queued"
                )
            )
            queued = list(queued_result.scalars().all())

            updated = []
            for record in queued:
                if record.scheduled_at:
                    wait_seconds = (now - record.scheduled_at).total_seconds()
                    if wait_seconds > threshold_seconds and record.priority < 10:
                        record.priority = min(10, record.priority + 1)
                        logger.info(
                            f"Priority aging: intent {record.intent_id} "
                            f"priority raised to {record.priority}"
                        )

            queued.sort(
                key=lambda r: (-r.priority, r.scheduled_at or now)
            )

            for idx, record in enumerate(queued):
                record.queue_position = idx
                updated.append(record)

            await session.commit()
            for record in updated:
                await session.refresh(record)

            logger.info(f"Rebalanced queue: {len(updated)} intents reordered")
            return updated

    def check_resource_availability(self, requirements: Dict) -> bool:
        return self.resource_pool.check_availability(requirements)

    def allocate_resources(self, intent_id: int, requirements: Dict) -> bool:
        return self.resource_pool.allocate(intent_id, requirements)

    def release_resources(self, intent_id: int) -> bool:
        return self.resource_pool.release(intent_id)

    def update_resource_limits(
        self,
        max_device_slots: Optional[int] = None,
        max_bandwidth_mbps: Optional[int] = None,
        max_concurrent: Optional[int] = None,
    ):
        if max_device_slots is not None:
            self.resource_pool.max_device_slots = max_device_slots
        if max_bandwidth_mbps is not None:
            self.resource_pool.max_bandwidth_mbps = max_bandwidth_mbps
        if max_concurrent is not None:
            self.resource_pool.max_concurrent = max_concurrent
        logger.info(
            f"Resource limits updated: slots={self.resource_pool.max_device_slots}, "
            f"bandwidth={self.resource_pool.max_bandwidth_mbps}, "
            f"concurrent={self.resource_pool.max_concurrent}"
        )


_intent_scheduler: Optional[IntentScheduler] = None


def get_intent_scheduler() -> IntentScheduler:
    global _intent_scheduler
    if _intent_scheduler is None:
        _intent_scheduler = IntentScheduler()
    return _intent_scheduler
