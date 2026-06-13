from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import FailedIntentCase, FailureStage, Intent
from .deps import get_current_user

router = APIRouter()


class FailedIntentCreate(BaseModel):
    intent_id: int
    failure_reason: Optional[str] = None
    failure_stage: str
    root_cause: Optional[str] = None
    resolution_notes: Optional[str] = None


class FailedIntentUpdate(BaseModel):
    failure_reason: Optional[str] = None
    root_cause: Optional[str] = None
    resolution_notes: Optional[str] = None


@router.get("/")
async def list_failed_intents(
    failure_stage: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(FailedIntentCase)
    if failure_stage:
        query = query.where(FailedIntentCase.failure_stage == failure_stage)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    cases = result.scalars().all()
    return {"status": "success", "data": [{"id": c.id, "intent_id": c.intent_id, "failure_reason": c.failure_reason, "failure_stage": c.failure_stage.value if c.failure_stage else None, "root_cause": c.root_cause, "resolution_notes": c.resolution_notes, "created_at": c.created_at.isoformat() if c.created_at else None} for c in cases]}


@router.get("/{case_id}")
async def get_failed_intent(
    case_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(FailedIntentCase).where(FailedIntentCase.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Failed intent case not found")
    return {"status": "success", "data": {"id": case.id, "intent_id": case.intent_id, "failure_reason": case.failure_reason, "failure_stage": case.failure_stage.value if case.failure_stage else None, "root_cause": case.root_cause, "resolution_notes": case.resolution_notes, "created_at": case.created_at.isoformat() if case.created_at else None}}


@router.post("/")
async def create_failed_intent(
    req: FailedIntentCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    intent_result = await db.execute(select(Intent).where(Intent.id == req.intent_id))
    if not intent_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Intent not found")
    case = FailedIntentCase(
        intent_id=req.intent_id,
        failure_reason=req.failure_reason,
        failure_stage=FailureStage(req.failure_stage),
        root_cause=req.root_cause,
        resolution_notes=req.resolution_notes,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return {"status": "success", "data": {"id": case.id}}


@router.put("/{case_id}")
async def update_failed_intent(
    case_id: int,
    req: FailedIntentUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(FailedIntentCase).where(FailedIntentCase.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Failed intent case not found")
    if req.failure_reason is not None:
        case.failure_reason = req.failure_reason
    if req.root_cause is not None:
        case.root_cause = req.root_cause
    if req.resolution_notes is not None:
        case.resolution_notes = req.resolution_notes
    await db.commit()
    return {"status": "success", "data": {"id": case.id}}


@router.delete("/{case_id}")
async def delete_failed_intent(
    case_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(FailedIntentCase).where(FailedIntentCase.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Failed intent case not found")
    await db.delete(case)
    await db.commit()
    return {"status": "success", "message": "Deleted"}


@router.get("/stats/summary")
async def failed_intents_stats(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    from sqlalchemy import func
    result = await db.execute(select(func.count()).select_from(FailedIntentCase))
    total = result.scalar() or 0
    stage_result = await db.execute(
        select(FailedIntentCase.failure_stage, func.count()).group_by(FailedIntentCase.failure_stage)
    )
    by_stage = {str(row[0].value) if row[0] else "unknown": row[1] for row in stage_result.all()}
    return {"status": "success", "data": {"total": total, "by_stage": by_stage}}
