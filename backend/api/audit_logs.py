from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, case
from pydantic import BaseModel
from backend.database.connection import get_db_session
from backend.core.cache import api_cache
from backend.database.models import AuditLog
from backend.core.security.rbac import get_current_user, requires_permission
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class AuditLogResponse(BaseModel):
    id: int
    user_id: str
    action: str
    target_device: Optional[str] = None
    commands: Optional[list] = None
    timestamp: Optional[str] = None
    approval_id: Optional[str] = None
    status: Optional[str] = None
    security_type: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    raw_prompt: Optional[str] = None
    raw_response: Optional[str] = None

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    data: list[AuditLogResponse]
    total: int
    page: int
    limit: int


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    security_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(requires_permission("audit:read")),
):
    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))

    if user:
        query = query.where(AuditLog.user_id == user)
        count_query = count_query.where(AuditLog.user_id == user)
    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if status:
        query = query.where(AuditLog.status == status)
        count_query = count_query.where(AuditLog.status == status)
    if security_type:
        query = query.where(AuditLog.security_type == security_type)
        count_query = count_query.where(AuditLog.security_type == security_type)
    if start_date:
        query = query.where(AuditLog.timestamp >= start_date)
        count_query = count_query.where(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.where(AuditLog.timestamp <= end_date + " 23:59:59")
        count_query = count_query.where(AuditLog.timestamp <= end_date + " 23:59:59")

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * limit
    query = query.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return AuditLogListResponse(
        data=[AuditLogResponse(
            id=log.id,
            user_id=log.user_id,
            action=log.action,
            target_device=log.target_device,
            commands=log.commands,
            timestamp=log.timestamp.isoformat() if log.timestamp else None,
            approval_id=log.approval_id,
            status=log.status,
            security_type=log.security_type,
            prompt_tokens=log.prompt_tokens,
            completion_tokens=log.completion_tokens,
            latency_ms=log.latency_ms,
            raw_prompt=log.raw_prompt,
            raw_response=log.raw_response,
        ) for log in logs],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/stats")
async def get_audit_stats(
    db: AsyncSession = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(requires_permission("audit:read")),
):
    # Check cache first (30s TTL for stats)
    cached_stats = api_cache.get("audit_stats")
    if cached_stats is not None:
        return cached_stats

    # Single aggregated query instead of 5 separate COUNT queries
    stmt = select(
        func.count(AuditLog.id).label("total"),
        func.sum(case((AuditLog.security_type == "critical", 1), else_=0)).label("critical"),
        func.sum(case((AuditLog.security_type == "warning", 1), else_=0)).label("warning"),
        func.sum(case((AuditLog.status == "success", 1), else_=0)).label("success"),
        func.sum(case((AuditLog.status == "failed", 1), else_=0)).label("failed"),
    )
    row = (await db.execute(stmt)).one()

    result = {
        "total": row.total or 0,
        "critical": row.critical or 0,
        "warning": row.warning or 0,
        "success": row.success or 0,
        "failed": row.failed or 0,
    }

    api_cache.set("audit_stats", result, ttl_seconds=30)
    return result


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(requires_permission("audit:read")),
):
    result = await db.execute(select(AuditLog).where(AuditLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")

    return AuditLogResponse(
        id=log.id,
        user_id=log.user_id,
        action=log.action,
        target_device=log.target_device,
        commands=log.commands,
        timestamp=log.timestamp.isoformat() if log.timestamp else None,
        approval_id=log.approval_id,
        status=log.status,
        security_type=log.security_type,
        prompt_tokens=log.prompt_tokens,
        completion_tokens=log.completion_tokens,
        latency_ms=log.latency_ms,
        raw_prompt=log.raw_prompt,
        raw_response=log.raw_response,
    )
