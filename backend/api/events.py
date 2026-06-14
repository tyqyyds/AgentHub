from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from pydantic import BaseModel, field_validator
from backend.database.connection import get_db_session
from backend.database.models import SelfHealingEvent, AuditLog
from datetime import datetime, timezone
from backend.core.security.rbac import get_current_user, requires_permission
from backend.agents.proactive_notifier import ProactiveNotifier
import logging

logger = logging.getLogger(__name__)
_notifier = ProactiveNotifier()

router = APIRouter()


class EventCreate(BaseModel):
    event_type: str
    severity: str
    description: str
    suggested_action: str = None
    target_device: str = None

    @field_validator('event_type')
    @classmethod
    def event_type_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('event_type cannot be empty')
        return v

    @field_validator('severity')
    @classmethod
    def severity_valid(cls, v):
        valid_severities = ['low', 'medium', 'high', 'critical']
        if v not in valid_severities:
            raise ValueError(f'severity must be one of: {valid_severities}')
        return v

    @field_validator('description')
    @classmethod
    def description_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('description cannot be empty')
        return v


@router.post("")
async def create_event(event: EventCreate, db: AsyncSession = Depends(get_db_session), current_user=Depends(requires_permission("events:create"))):
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Create event failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{event_id}/rollback")
async def rollback_event(event_id: int, db: AsyncSession = Depends(get_db_session), current_user=Depends(requires_permission("events:rollback"))):
    result = await db.execute(SelfHealingEvent.__table__.select().where(SelfHealingEvent.id == event_id))
    event = result.first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status != "completed":
        raise HTTPException(status_code=400, detail="Can only rollback completed events")

    try:
        await db.execute(
            SelfHealingEvent.__table__.update()
            .where(SelfHealingEvent.id == event_id)
            .values(status="rolled_back")
        )
        audit_log = AuditLog(
            user_id=current_user.username,
            action="rollback_healing",
            target_device=event.target_device,
            commands=[event.suggested_action or event.description],
            status="success",
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.commit()
        return {"status": "success", "data": {"id": event_id, "status": "rolled_back"}}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Rollback event failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rollback")
async def rollback_all_events(db: AsyncSession = Depends(get_db_session), current_user=Depends(requires_permission("system:manage"))):
    try:
        result = await db.execute(
            SelfHealingEvent.__table__.update()
            .where(SelfHealingEvent.status == "completed")
            .values(status="rolled_back")
        )
        audit_log = AuditLog(
            user_id=current_user.username,
            action="rollback_all_healing",
            target_device="system",
            commands=["ROLLBACK_ALL"],
            status="success",
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.commit()
        rolled_back = result.rowcount if hasattr(result, 'rowcount') else 0
        return {"status": "success", "data": {"rolled_back_count": rolled_back}}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Rollback all events failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("")
async def get_events(
    status: str = None,
    severity: str = None,
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user)
):
    query = SelfHealingEvent.__table__.select().order_by(SelfHealingEvent.created_at.desc())
    if status:
        query = query.where(SelfHealingEvent.status == status)
    if severity:
        query = query.where(SelfHealingEvent.severity == severity)

    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    events = result.fetchall()

    count_query = select(func.count(SelfHealingEvent.id))
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return {
        "status": "success",
        "data": [dict(row._mapping) for row in events],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }


@router.get("/{event_id}")
async def get_event(event_id: int, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user)):
    result = await db.execute(SelfHealingEvent.__table__.select().where(SelfHealingEvent.id == event_id))
    event = result.first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "success", "data": dict(event._mapping)}


@router.put("/{event_id}/execute")
async def execute_event(event_id: int, db: AsyncSession = Depends(get_db_session), current_user=Depends(requires_permission("events:execute"))):
    result = await db.execute(SelfHealingEvent.__table__.select().where(SelfHealingEvent.id == event_id))
    event = result.first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status in ("completed", "executing"):
        raise HTTPException(status_code=400, detail=f"Cannot execute event in '{event.status}' status")

    try:
        await db.execute(
            SelfHealingEvent.__table__.update()
            .where(SelfHealingEvent.id == event_id)
            .values(status="completed", executed_by=current_user.username)
        )
        
        audit_log = AuditLog(
            user_id=current_user.username,
            action="execute_healing",
            target_device=event.target_device,
            commands=[event.suggested_action],
            status="success",
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.commit()
        # 发送自愈完成通知
        try:
            await _notifier.notify_healing_completed(
                event_id=event_id,
                result={"success": True, "action": event.suggested_action},
            )
        except Exception as e:
            logger.warning(f"Failed to send healing notification: {e}")
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Execute event failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{event_id}/reject")
async def reject_event(event_id: int, db: AsyncSession = Depends(get_db_session), current_user=Depends(requires_permission("events:execute"))):
    result = await db.execute(SelfHealingEvent.__table__.select().where(SelfHealingEvent.id == event_id))
    event = result.first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status in ("completed", "rejected"):
        raise HTTPException(status_code=400, detail=f"Cannot reject event in '{event.status}' status")

    try:
        await db.execute(
            SelfHealingEvent.__table__.update()
            .where(SelfHealingEvent.id == event_id)
            .values(status="rejected")
        )
        
        audit_log = AuditLog(
            user_id=current_user.username,
            action="reject_healing",
            target_device=event.target_device,
            commands=[event.description],
            status="success",
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.commit()
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Reject event failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")