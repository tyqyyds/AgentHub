from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..database.connection import get_db_session
from ..database.models import IntentScheduleRecord, RecurrenceType, Intent
from .deps import get_current_user

router = APIRouter()


class ScheduleCreate(BaseModel):
    intent_id: int
    scheduled_time: str
    recurrence: Optional[str] = "once"


class ScheduleUpdate(BaseModel):
    scheduled_time: Optional[str] = None
    recurrence: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/")
async def list_schedules(
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(IntentScheduleRecord)
    if is_active is not None:
        query = query.where(IntentScheduleRecord.is_active == is_active)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    records = result.scalars().all()
    return {"status": "success", "data": [{"id": r.id, "intent_id": r.intent_id, "scheduled_time": r.scheduled_time.isoformat() if r.scheduled_time else None, "recurrence": r.recurrence.value if r.recurrence else None, "is_active": r.is_active, "last_executed_at": r.last_executed_at.isoformat() if r.last_executed_at else None, "created_at": r.created_at.isoformat() if r.created_at else None} for r in records]}


@router.get("/{schedule_id}")
async def get_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(IntentScheduleRecord).where(IntentScheduleRecord.id == schedule_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "success", "data": {"id": record.id, "intent_id": record.intent_id, "scheduled_time": record.scheduled_time.isoformat() if record.scheduled_time else None, "recurrence": record.recurrence.value if record.recurrence else None, "is_active": record.is_active, "last_executed_at": record.last_executed_at.isoformat() if record.last_executed_at else None}}


@router.post("/")
async def create_schedule(
    req: ScheduleCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    intent_result = await db.execute(select(Intent).where(Intent.id == req.intent_id))
    if not intent_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Intent not found")
    record = IntentScheduleRecord(
        intent_id=req.intent_id,
        scheduled_time=datetime.fromisoformat(req.scheduled_time),
        recurrence=RecurrenceType(req.recurrence) if req.recurrence else RecurrenceType.ONCE,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"status": "success", "data": {"id": record.id}}


@router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    req: ScheduleUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(IntentScheduleRecord).where(IntentScheduleRecord.id == schedule_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if req.scheduled_time is not None:
        record.scheduled_time = datetime.fromisoformat(req.scheduled_time)
    if req.recurrence is not None:
        record.recurrence = RecurrenceType(req.recurrence)
    if req.is_active is not None:
        record.is_active = req.is_active
    await db.commit()
    return {"status": "success", "data": {"id": record.id}}


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(IntentScheduleRecord).where(IntentScheduleRecord.id == schedule_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(record)
    await db.commit()
    return {"status": "success", "message": "Deleted"}


@router.post("/{schedule_id}/execute")
async def execute_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(IntentScheduleRecord).where(IntentScheduleRecord.id == schedule_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if not record.is_active:
        raise HTTPException(status_code=400, detail="Schedule is not active")
    record.last_executed_at = datetime.now()
    await db.commit()
    return {"status": "success", "data": {"id": record.id, "last_executed_at": record.last_executed_at.isoformat()}}
