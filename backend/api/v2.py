from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..database.connection import get_db_session
from ..database.models import (
    Intent, ExecutionStatus, SelfHealingEvent, Device, DeviceStatus,
    AgentRegistry, AgentHealthRecord, AgentHealthStatus,
    AuditLog, TraceSpan, BehaviorAnomaly,
)
from .deps import get_current_user

router = APIRouter()


# ──────────────── V2 意图全生命周期 ────────────────


@router.get("/intents/{intent_id}/lifecycle")
async def get_intent_lifecycle(
    intent_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    intent_result = await db.execute(select(Intent).where(Intent.id == intent_id))
    intent = intent_result.scalar_one_or_none()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    event_result = await db.execute(
        select(SelfHealingEvent).where(SelfHealingEvent.intent_id == intent_id)
    )
    events = event_result.scalars().all()
    return {"status": "success", "data": {
        "intent": {
            "id": intent.id, "intent_type": intent.intent_type.value if intent.intent_type else None,
            "description": intent.description, "status": intent.status.value if intent.status else None,
            "created_at": intent.created_at.isoformat() if intent.created_at else None,
        },
        "events": [
            {"id": e.id, "event_type": e.event_type, "status": e.status,
             "created_at": e.created_at.isoformat() if e.created_at else None}
            for e in events
        ],
        "event_count": len(events),
    }}


# ──────────────── V2 聚合仪表盘 ────────────────


@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    intent_count = (await db.execute(select(func.count(Intent.id)))).scalar() or 0
    device_count = (await db.execute(select(func.count(Device.id)))).scalar() or 0
    agent_count = (await db.execute(select(func.count(AgentRegistry.id)))).scalar() or 0
    event_count = (await db.execute(select(func.count(SelfHealingEvent.id)))).scalar() or 0
    pending_intents = (await db.execute(
        select(func.count(Intent.id)).where(Intent.status == ExecutionStatus.PENDING)
    )).scalar() or 0
    online_devices = (await db.execute(
        select(func.count(Device.id)).where(Device.status == DeviceStatus.ONLINE)
    )).scalar() or 0
    healthy_agents = (await db.execute(
        select(func.count(AgentHealthRecord.id)).where(
            AgentHealthRecord.health_status == AgentHealthStatus.HEALTHY
        )
    )).scalar() or 0
    recent_anomalies = (await db.execute(
        select(func.count(BehaviorAnomaly.id))
    )).scalar() or 0
    return {"status": "success", "data": {
        "intents": {"total": intent_count, "pending": pending_intents},
        "devices": {"total": device_count, "online": online_devices},
        "agents": {"total": agent_count, "healthy": healthy_agents},
        "events": {"total": event_count},
        "anomalies": {"total": recent_anomalies},
    }}


# ──────────────── V2 搜索 ────────────────


class SearchRequest(BaseModel):
    query: str
    scope: Optional[str] = "all"  # all | intents | devices | agents | events | audit


@router.post("/search")
async def global_search(
    req: SearchRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    results = {}
    q = f"%{req.query}%"
    if req.scope in ("all", "intents"):
        intent_result = await db.execute(
            select(Intent).where(Intent.description.ilike(q)).limit(10)
        )
        intents = intent_result.scalars().all()
        results["intents"] = [
            {"id": i.id, "intent_type": i.intent_type.value if i.intent_type else None,
             "description": i.description, "status": i.status.value if i.status else None}
            for i in intents
        ]
    if req.scope in ("all", "devices"):
        device_result = await db.execute(
            select(Device).where(Device.name.ilike(q)).limit(10)
        )
        devices = device_result.scalars().all()
        results["devices"] = [
            {"id": d.id, "name": d.name, "device_type": d.device_type,
             "status": d.status.value if d.status else None}
            for d in devices
        ]
    if req.scope in ("all", "agents"):
        agent_result = await db.execute(
            select(AgentRegistry).where(AgentRegistry.domain.ilike(q)).limit(10)
        )
        agents = agent_result.scalars().all()
        results["agents"] = [
            {"id": a.id, "agent_id": a.agent_id, "domain": a.domain, "status": a.status}
            for a in agents
        ]
    if req.scope in ("all", "events"):
        event_result = await db.execute(
            select(SelfHealingEvent).where(SelfHealingEvent.event_type.ilike(q)).limit(10)
        )
        events = event_result.scalars().all()
        results["events"] = [
            {"id": e.id, "event_type": e.event_type, "status": e.status}
            for e in events
        ]
    if req.scope in ("all", "audit"):
        audit_result = await db.execute(
            select(AuditLog).where(AuditLog.action.ilike(q)).limit(10)
        )
        audits = audit_result.scalars().all()
        results["audit"] = [
            {"id": a.id, "user_id": a.user_id, "action": a.action,
             "timestamp": a.timestamp.isoformat() if a.timestamp else None}
            for a in audits
        ]
    return {"status": "success", "data": results}


# ──────────────── V2 批量操作 ────────────────


class BatchIntentAction(BaseModel):
    intent_ids: list[int]
    action: str  # approve | reject | cancel | retry


@router.post("/intents/batch")
async def batch_intent_action(
    req: BatchIntentAction,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    status_map = {
        "approve": ExecutionStatus.APPROVED,
        "reject": ExecutionStatus.REJECTED,
        "cancel": ExecutionStatus.CANCELLED,
        "retry": ExecutionStatus.PENDING,
    }
    if req.action not in status_map:
        raise HTTPException(status_code=400, detail=f"Invalid action: {req.action}")
    new_status = status_map[req.action]
    updated = 0
    for iid in req.intent_ids:
        result = await db.execute(select(Intent).where(Intent.id == iid))
        intent = result.scalar_one_or_none()
        if intent:
            intent.status = new_status
            updated += 1
    await db.commit()
    return {"status": "success", "data": {"updated": updated, "action": req.action}}


# ──────────────── V2 系统状态 ────────────────


@router.get("/system/status")
async def system_status(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    intent_result = await db.execute(
        select(Intent.status, func.count(Intent.id)).group_by(Intent.status)
    )
    intent_by_status = {row[0].value if row[0] else "unknown": row[1] for row in intent_result.all()}
    device_result = await db.execute(
        select(Device.status, func.count(Device.id)).group_by(Device.status)
    )
    device_by_status = {row[0].value if row[0] else "unknown": row[1] for row in device_result.all()}
    return {"status": "success", "data": {
        "intents_by_status": intent_by_status,
        "devices_by_status": device_by_status,
        "timestamp": datetime.now().isoformat(),
    }}
