from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import AuditLog, ApprovalStatus, Intent
from .deps import get_current_user

router = APIRouter()


class CommitRequest(BaseModel):
    intent_id: int
    config_changes: dict
    description: Optional[str] = None


class ApprovalRequest(BaseModel):
    intent_id: int
    approved: bool
    comment: Optional[str] = None


@router.post("/")
async def create_commit(
    req: CommitRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Intent).where(Intent.id == req.intent_id))
    intent = result.scalar_one_or_none()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    audit = AuditLog(
        user_id=str(current_user.id),
        action="config_commit",
        target_device=str(req.config_changes.get("target_device", "")),
        commands=req.config_changes,
        status="pending",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(audit)
    return {"status": "success", "data": {"commit_id": audit.id, "intent_id": req.intent_id}}


@router.post("/approve")
async def approve_commit(
    req: ApprovalRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Intent).where(Intent.id == req.intent_id))
    intent = result.scalar_one_or_none()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    intent.approval_status = ApprovalStatus.APPROVED if req.approved else ApprovalStatus.REJECTED
    await db.commit()
    return {"status": "success", "data": {"intent_id": req.intent_id, "approved": req.approved}}


@router.get("/pending")
async def list_pending_commits(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(AuditLog).where(AuditLog.status == "pending")
    )
    commits = result.scalars().all()
    return {"status": "success", "data": [{"id": c.id, "user_id": c.user_id, "action": c.action, "timestamp": c.timestamp.isoformat() if c.timestamp else None} for c in commits]}
