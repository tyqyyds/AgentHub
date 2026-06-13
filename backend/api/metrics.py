from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import (
    Intent, ExecutionStatus, SelfHealingEvent, Device, DeviceStatus,
    AgentRegistry, TraceSpan, BehaviorAnomaly, AuditLog, PlaybookExecution,
)
from .deps import get_current_user

router = APIRouter()


@router.get("/overview")
async def metrics_overview(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    intent_count = (await db.execute(select(func.count()).select_from(Intent))).scalar() or 0
    event_count = (await db.execute(select(func.count()).select_from(SelfHealingEvent))).scalar() or 0
    device_count = (await db.execute(select(func.count()).select_from(Device))).scalar() or 0
    online_devices = (await db.execute(select(func.count()).select_from(Device).where(Device.status == DeviceStatus.ONLINE))).scalar() or 0
    agent_count = (await db.execute(select(func.count()).select_from(AgentRegistry))).scalar() or 0
    return {"status": "success", "data": {"total_intents": intent_count, "total_events": event_count, "total_devices": device_count, "online_devices": online_devices, "device_online_rate": round(online_devices / max(device_count, 1) * 100, 2), "total_agents": agent_count}}


@router.get("/intents")
async def intent_metrics(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(days=days)
    total = (await db.execute(select(func.count()).select_from(Intent).where(Intent.created_at >= since))).scalar() or 0
    completed = (await db.execute(select(func.count()).select_from(Intent).where(Intent.execution_status == ExecutionStatus.COMPLETED, Intent.created_at >= since))).scalar() or 0
    failed = (await db.execute(select(func.count()).select_from(Intent).where(Intent.execution_status == ExecutionStatus.FAILED, Intent.created_at >= since))).scalar() or 0
    return {"status": "success", "data": {"period_days": days, "total": total, "completed": completed, "failed": failed, "success_rate": round(completed / max(total, 1) * 100, 2)}}


@router.get("/devices")
async def device_metrics(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    total = (await db.execute(select(func.count()).select_from(Device))).scalar() or 0
    online = (await db.execute(select(func.count()).select_from(Device).where(Device.status == DeviceStatus.ONLINE))).scalar() or 0
    offline = (await db.execute(select(func.count()).select_from(Device).where(Device.status == DeviceStatus.OFFLINE))).scalar() or 0
    maintenance = (await db.execute(select(func.count()).select_from(Device).where(Device.status == DeviceStatus.MAINTENANCE))).scalar() or 0
    anomaly_count = (await db.execute(select(func.count()).select_from(BehaviorAnomaly).where(BehaviorAnomaly.resolved == False))).scalar() or 0
    return {"status": "success", "data": {"total": total, "online": online, "offline": offline, "maintenance": maintenance, "unresolved_anomalies": anomaly_count}}


@router.get("/agents")
async def agent_metrics(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    total = (await db.execute(select(func.count()).select_from(AgentRegistry))).scalar() or 0
    online = (await db.execute(select(func.count()).select_from(AgentRegistry).where(AgentRegistry.status == "online"))).scalar() or 0
    return {"status": "success", "data": {"total": total, "online": online, "online_rate": round(online / max(total, 1) * 100, 2)}}


@router.get("/traces")
async def trace_metrics(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    total = (await db.execute(select(func.count()).select_from(TraceSpan))).scalar() or 0
    errors = (await db.execute(select(func.count()).select_from(TraceSpan).where(TraceSpan.status_code == "ERROR"))).scalar() or 0
    return {"status": "success", "data": {"total_spans": total, "error_spans": errors, "error_rate": round(errors / max(total, 1) * 100, 2)}}


@router.get("/audit")
async def audit_metrics(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(days=days)
    total = (await db.execute(select(func.count()).select_from(AuditLog).where(AuditLog.timestamp >= since))).scalar() or 0
    return {"status": "success", "data": {"period_days": days, "total_audit_entries": total}}
