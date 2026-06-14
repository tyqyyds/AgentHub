from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
from backend.core.security.rbac import get_current_user, requires_permission
from backend.agents.intent_scheduler import get_intent_scheduler
from backend.api.response import success_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class EnqueueRequest(BaseModel):
    intent_id: int
    priority: int = 5
    resource_requirements: Optional[Dict] = None


class PreemptRequest(BaseModel):
    reason: str = ""


class FailRequest(BaseModel):
    reason: str = ""


class UpdateResourcesRequest(BaseModel):
    max_device_slots: Optional[int] = None
    max_bandwidth_mbps: Optional[int] = None
    max_concurrent: Optional[int] = None


@router.get("/queue")
async def get_queue_status(current_user=Depends(get_current_user)):
    import datetime
    scheduler = get_intent_scheduler()
    status = await scheduler.get_queue_status()
    # 同时返回队列记录列表
    from backend.database.models import IntentScheduleRecord
    from backend.database.connection import async_session_maker
    from sqlalchemy import select
    async with async_session_maker() as session:
        result = await session.execute(
            select(IntentScheduleRecord).order_by(IntentScheduleRecord.id.desc()).limit(50)
        )
        records = result.scalars().all()
        items = []
        for r in records:
            wait_time = 0
            if r.scheduled_at:
                end_time = r.started_at or datetime.datetime.utcnow()
                wait_time = max(0, int((end_time - r.scheduled_at).total_seconds()))
            items.append({
                "id": r.id,
                "intent_id": r.intent_id,
                "priority": r.priority,
                "queue_position": r.queue_position,
                "status": r.status,
                "resource_requirements": r.resource_quota,
                "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "wait_time": wait_time,
            })
        status["items"] = items
    return success_response(data=status)


@router.post("/enqueue")
async def enqueue_intent(
    req: EnqueueRequest,
    current_user=Depends(requires_permission("intent:execute")),
):
    scheduler = get_intent_scheduler()
    record = await scheduler.enqueue(
        intent_id=req.intent_id,
        priority=req.priority,
        resource_requirements=req.resource_requirements,
    )
    return success_response(data={
            "id": record.id,
            "intent_id": record.intent_id,
            "priority": record.priority,
            "queue_position": record.queue_position,
            "status": record.status,
            "scheduled_at": record.scheduled_at.isoformat() if record.scheduled_at else None,
        })


@router.post("/dequeue")
async def dequeue_intent(
    current_user=Depends(requires_permission("intent:execute")),
):
    scheduler = get_intent_scheduler()
    record = await scheduler.dequeue()
    if not record:
        return success_response(data=None, message="No available intent to dequeue")
    return success_response(data={
            "id": record.id,
            "intent_id": record.intent_id,
            "priority": record.priority,
            "status": record.status,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "wait_time_ms": record.wait_time_ms,
            "resource_quota": record.resource_quota,
        })


@router.post("/preempt/{intent_id}")
async def preempt_intent(
    intent_id: int,
    req: PreemptRequest,
    current_user=Depends(requires_permission("intent:execute")),
):
    scheduler = get_intent_scheduler()
    success = await scheduler.preempt(intent_id, reason=req.reason)
    if not success:
        raise HTTPException(status_code=400, detail="无法抢占该意图：意图未在运行中")
    return success_response(data={"intent_id": intent_id, "preempted": True})


@router.post("/resume/{intent_id}")
async def resume_intent(
    intent_id: int,
    current_user=Depends(requires_permission("intent:execute")),
):
    scheduler = get_intent_scheduler()
    success = await scheduler.resume(intent_id)
    if not success:
        raise HTTPException(status_code=400, detail="无法恢复该意图：意图未被抢占")
    return success_response(data={"intent_id": intent_id, "resumed": True})


@router.post("/complete/{intent_id}")
async def complete_intent(
    intent_id: int,
    current_user=Depends(requires_permission("intent:execute")),
):
    scheduler = get_intent_scheduler()
    success = await scheduler.complete(intent_id)
    if not success:
        raise HTTPException(status_code=400, detail="无法完成该意图：意图未在运行中")
    return success_response(data={"intent_id": intent_id, "completed": True})


@router.post("/fail/{intent_id}")
async def fail_intent(
    intent_id: int,
    req: FailRequest,
    current_user=Depends(requires_permission("intent:execute")),
):
    scheduler = get_intent_scheduler()
    success = await scheduler.fail(intent_id, reason=req.reason)
    if not success:
        raise HTTPException(status_code=400, detail="无法标记该意图为失败：意图未在活跃状态")
    return success_response(data={"intent_id": intent_id, "failed": True})


@router.get("/position/{intent_id}")
async def get_intent_position(
    intent_id: int,
    current_user=Depends(get_current_user),
):
    scheduler = get_intent_scheduler()
    position = await scheduler.get_intent_position(intent_id)
    return success_response(data={"intent_id": intent_id, "position": position})


@router.post("/rebalance")
async def rebalance_queue(
    current_user=Depends(requires_permission("system:manage")),
):
    scheduler = get_intent_scheduler()
    updated = await scheduler.rebalance_queue()
    return success_response(data={
            "rebalanced_count": len(updated),
            "records": [
                {
                    "intent_id": r.intent_id,
                    "priority": r.priority,
                    "queue_position": r.queue_position,
                }
                for r in updated
            ],
        })


@router.get("/resources")
async def get_resource_status(current_user=Depends(get_current_user)):
    scheduler = get_intent_scheduler()
    return success_response(data=scheduler.resource_pool.status())


@router.put("/resources")
async def update_resource_limits(
    req: UpdateResourcesRequest,
    current_user=Depends(requires_permission("system:manage")),
):
    scheduler = get_intent_scheduler()
    scheduler.update_resource_limits(
        max_device_slots=req.max_device_slots,
        max_bandwidth_mbps=req.max_bandwidth_mbps,
        max_concurrent=req.max_concurrent,
    )
    return success_response(data=scheduler.resource_pool.status())
