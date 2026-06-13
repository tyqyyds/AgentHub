from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..database.connection import get_db_session
from ..database.models import AuditLog
from .deps import get_current_user

router = APIRouter()


class AuditLogCreate(BaseModel):
    user_id: str
    action: str
    target_device: Optional[str] = None
    commands: Optional[dict] = None
    approval_id: Optional[str] = None
    status: Optional[str] = "success"


class AuditLogUpdate(BaseModel):
    action: Optional[str] = None
    target_device: Optional[str] = None
    commands: Optional[dict] = None
    approval_id: Optional[str] = None
    status: Optional[str] = None


@router.get("/")
async def list_audit_logs(
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    target_device: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None, description="ISO格式开始时间"),
    end_time: Optional[str] = Query(None, description="ISO格式结束时间"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(AuditLog)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    if target_device:
        query = query.where(AuditLog.target_device == target_device)
    if status:
        query = query.where(AuditLog.status == status)
    if start_time:
        query = query.where(AuditLog.timestamp >= datetime.fromisoformat(start_time))
    if end_time:
        query = query.where(AuditLog.timestamp <= datetime.fromisoformat(end_time))
    query = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()
    return {"status": "success", "data": [
        {"id": l.id, "user_id": l.user_id, "action": l.action,
         "target_device": l.target_device, "commands": l.commands,
         "timestamp": l.timestamp.isoformat() if l.timestamp else None,
         "approval_id": l.approval_id, "status": l.status}
        for l in logs
    ]}


@router.get("/{log_id}")
async def get_audit_log(
    log_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(AuditLog).where(AuditLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return {"status": "success", "data": {
        "id": log.id, "user_id": log.user_id, "action": log.action,
        "target_device": log.target_device, "commands": log.commands,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "approval_id": log.approval_id, "status": log.status,
    }}


@router.post("/")
async def create_audit_log(
    req: AuditLogCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    log = AuditLog(
        user_id=req.user_id, action=req.action,
        target_device=req.target_device, commands=req.commands,
        approval_id=req.approval_id, status=req.status,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return {"status": "success", "data": {"id": log.id}}


@router.put("/{log_id}")
async def update_audit_log(
    log_id: int,
    req: AuditLogUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(AuditLog).where(AuditLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")
    if req.action is not None:
        log.action = req.action
    if req.target_device is not None:
        log.target_device = req.target_device
    if req.commands is not None:
        log.commands = req.commands
    if req.approval_id is not None:
        log.approval_id = req.approval_id
    if req.status is not None:
        log.status = req.status
    await db.commit()
    return {"status": "success", "data": {"id": log.id}}


@router.delete("/{log_id}")
async def delete_audit_log(
    log_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(AuditLog).where(AuditLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")
    await db.delete(log)
    await db.commit()
    return {"status": "success", "message": "Deleted"}


@router.get("/stats/summary")
async def audit_stats(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    total_result = await db.execute(select(func.count(AuditLog.id)))
    total = total_result.scalar() or 0
    by_action_result = await db.execute(
        select(AuditLog.action, func.count(AuditLog.id)).group_by(AuditLog.action)
    )
    by_action = {row[0]: row[1] for row in by_action_result.all()}
    by_status_result = await db.execute(
        select(AuditLog.status, func.count(AuditLog.id)).group_by(AuditLog.status)
    )
    by_status = {row[0]: row[1] for row in by_status_result.all()}
    return {"status": "success", "data": {
        "total": total, "by_action": by_action, "by_status": by_status,
    }}


@router.get("/export/csv")
async def export_audit_logs(
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(AuditLog)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    if start_time:
        query = query.where(AuditLog.timestamp >= datetime.fromisoformat(start_time))
    if end_time:
        query = query.where(AuditLog.timestamp <= datetime.fromisoformat(end_time))
    query = query.order_by(AuditLog.timestamp.desc()).limit(1000)
    result = await db.execute(query)
    logs = result.scalars().all()
    lines = ["id,user_id,action,target_device,timestamp,approval_id,status"]
    for l in logs:
        lines.append(f'{l.id},{l.user_id},{l.action},{l.target_device or ""},{l.timestamp.isoformat() if l.timestamp else ""},{l.approval_id or ""},{l.status}')
    csv_content = "\n".join(lines)
    return {"status": "success", "data": {"csv": csv_content, "count": len(logs)}}
