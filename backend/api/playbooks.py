from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import Playbook, PlaybookExecution, PlaybookExecutionStatus
from .deps import get_current_user

router = APIRouter()


class PlaybookCreate(BaseModel):
    playbook_id: str
    name: str
    description: Optional[str] = None
    steps: list
    trigger_condition: Optional[dict] = None
    created_by: Optional[str] = None


class PlaybookUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[list] = None
    trigger_condition: Optional[dict] = None


@router.get("/")
async def list_playbooks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Playbook).offset(skip).limit(limit))
    playbooks = result.scalars().all()
    return {"status": "success", "data": [{"id": p.id, "playbook_id": p.playbook_id, "name": p.name, "description": p.description, "steps": p.steps, "trigger_condition": p.trigger_condition, "created_by": p.created_by, "created_at": p.created_at.isoformat() if p.created_at else None} for p in playbooks]}


@router.get("/{playbook_id}")
async def get_playbook(
    playbook_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Playbook).where(Playbook.id == playbook_id))
    playbook = result.scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return {"status": "success", "data": {"id": playbook.id, "playbook_id": playbook.playbook_id, "name": playbook.name, "description": playbook.description, "steps": playbook.steps, "trigger_condition": playbook.trigger_condition, "created_by": playbook.created_by}}


@router.post("/")
async def create_playbook(
    req: PlaybookCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    existing = await db.execute(select(Playbook).where(Playbook.playbook_id == req.playbook_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Playbook ID already exists")
    playbook = Playbook(
        playbook_id=req.playbook_id, name=req.name, description=req.description,
        steps=req.steps, trigger_condition=req.trigger_condition, created_by=req.created_by,
    )
    db.add(playbook)
    await db.commit()
    await db.refresh(playbook)
    return {"status": "success", "data": {"id": playbook.id}}


@router.put("/{playbook_id}")
async def update_playbook(
    playbook_id: int,
    req: PlaybookUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Playbook).where(Playbook.id == playbook_id))
    playbook = result.scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    if req.name is not None:
        playbook.name = req.name
    if req.description is not None:
        playbook.description = req.description
    if req.steps is not None:
        playbook.steps = req.steps
    if req.trigger_condition is not None:
        playbook.trigger_condition = req.trigger_condition
    await db.commit()
    return {"status": "success", "data": {"id": playbook.id}}


@router.delete("/{playbook_id}")
async def delete_playbook(
    playbook_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Playbook).where(Playbook.id == playbook_id))
    playbook = result.scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    await db.delete(playbook)
    await db.commit()
    return {"status": "success", "message": "Deleted"}


@router.get("/{playbook_id}/executions")
async def list_playbook_executions(
    playbook_id: int,
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(PlaybookExecution).where(PlaybookExecution.playbook_id == playbook_id)
    if status:
        query = query.where(PlaybookExecution.status == status)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    executions = result.scalars().all()
    return {"status": "success", "data": [{"id": e.id, "playbook_id": e.playbook_id, "triggered_by": e.triggered_by, "status": e.status.value if e.status else None, "result": e.result, "started_at": e.started_at.isoformat() if e.started_at else None, "completed_at": e.completed_at.isoformat() if e.completed_at else None} for e in executions]}


@router.post("/{playbook_id}/execute")
async def execute_playbook(
    playbook_id: int,
    triggered_by: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    pb_result = await db.execute(select(Playbook).where(Playbook.id == playbook_id))
    if not pb_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Playbook not found")
    execution = PlaybookExecution(
        playbook_id=playbook_id,
        triggered_by=triggered_by or current_user.username if hasattr(current_user, 'username') else "system",
        status=PlaybookExecutionStatus.RUNNING,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return {"status": "success", "data": {"id": execution.id, "status": execution.status.value}}
