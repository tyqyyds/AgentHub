from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from ..database.connection import get_db_session
from ..database.models import SelfHealingEvent

router = APIRouter()


class EventCreate(BaseModel):
    event_type: str
    severity: str
    description: str
    suggested_action: Optional[str] = None
    target_device: Optional[str] = None

class EventUpdate(BaseModel):
    event_type: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    suggested_action: Optional[str] = None
    target_device: Optional[str] = None
    status: Optional[str] = None


@router.post("/")
async def create_event(event: EventCreate, db: AsyncSession = Depends(get_db_session)):
    new_event = SelfHealingEvent(
        event_type=event.event_type,
        severity=event.severity,
        description=event.description,
        suggested_action=event.suggested_action,
        target_device=event.target_device
    )
    db.add(new_event)
    await db.commit()
    await db.refresh(new_event)
    return {"status": "success", "data": {"id": new_event.id}}


@router.get("/")
async def get_events(status: Optional[str] = None, db: AsyncSession = Depends(get_db_session)):
    query = SelfHealingEvent.__table__.select()
    if status:
        query = query.where(SelfHealingEvent.status == status)
    
    result = await db.execute(query)
    events = result.fetchall()
    return {"status": "success", "data": [dict(row._mapping) for row in events]}


@router.get("/{event_id}")
async def get_event(event_id: int, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(SelfHealingEvent.__table__.select().where(SelfHealingEvent.id == event_id))
    event = result.first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "success", "data": dict(event._mapping)}


@router.put("/{event_id}")
async def update_event(event_id: int, req: EventUpdate, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(SelfHealingEvent.__table__.select().where(SelfHealingEvent.id == event_id))
    event = result.first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    if update_data:
        await db.execute(
            SelfHealingEvent.__table__.update()
            .where(SelfHealingEvent.id == event_id)
            .values(**update_data)
        )
        await db.commit()
    return {"status": "success"}

@router.delete("/{event_id}")
async def delete_event(event_id: int, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(SelfHealingEvent.__table__.select().where(SelfHealingEvent.id == event_id))
    event = result.first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.execute(SelfHealingEvent.__table__.delete().where(SelfHealingEvent.id == event_id))
    await db.commit()
    return {"status": "success"}

@router.put("/{event_id}/execute")
async def execute_event(event_id: int, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(SelfHealingEvent.__table__.select().where(SelfHealingEvent.id == event_id))
    event = result.first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    await db.execute(
        SelfHealingEvent.__table__.update()
        .where(SelfHealingEvent.id == event_id)
        .values(status="completed", executed_by="system")
    )
    await db.commit()
    return {"status": "success"}


@router.put("/{event_id}/reject")
async def reject_event(event_id: int, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(SelfHealingEvent.__table__.select().where(SelfHealingEvent.id == event_id))
    event = result.first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    await db.execute(
        SelfHealingEvent.__table__.update()
        .where(SelfHealingEvent.id == event_id)
        .values(status="rejected")
    )
    await db.commit()
    return {"status": "success"}