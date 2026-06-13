from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import GrayscaleHealingTask, GrayscalePhase, GrayscaleTaskStatus, HealingEvaluation, HealingEvaluationType, SelfHealingEvent
from .deps import get_current_user

router = APIRouter()


class GrayscaleTaskCreate(BaseModel):
    event_id: int
    phase: str
    target_devices: Optional[list] = None


class GrayscaleTaskUpdate(BaseModel):
    phase: Optional[str] = None
    target_devices: Optional[list] = None
    canary_result: Optional[dict] = None
    batch_result: Optional[dict] = None
    status: Optional[str] = None


class HealingEvaluationCreate(BaseModel):
    event_id: int
    evaluation_type: str
    metrics_before: Optional[dict] = None
    metrics_after: Optional[dict] = None
    success: bool
    evaluation_notes: Optional[str] = None


@router.get("/tasks")
async def list_grayscale_tasks(
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(GrayscaleHealingTask)
    if status:
        query = query.where(GrayscaleHealingTask.status == status)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    tasks = result.scalars().all()
    return {"status": "success", "data": [{"id": t.id, "event_id": t.event_id, "phase": t.phase.value if t.phase else None, "target_devices": t.target_devices, "canary_result": t.canary_result, "batch_result": t.batch_result, "status": t.status.value if t.status else None, "created_at": t.created_at.isoformat() if t.created_at else None} for t in tasks]}


@router.get("/tasks/{task_id}")
async def get_grayscale_task(
    task_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(GrayscaleHealingTask).where(GrayscaleHealingTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Grayscale task not found")
    return {"status": "success", "data": {"id": task.id, "event_id": task.event_id, "phase": task.phase.value if task.phase else None, "target_devices": task.target_devices, "canary_result": task.canary_result, "batch_result": task.batch_result, "status": task.status.value if task.status else None}}


@router.post("/tasks")
async def create_grayscale_task(
    req: GrayscaleTaskCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    event_result = await db.execute(select(SelfHealingEvent).where(SelfHealingEvent.id == req.event_id))
    if not event_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Self healing event not found")
    task = GrayscaleHealingTask(
        event_id=req.event_id,
        phase=GrayscalePhase(req.phase),
        target_devices=req.target_devices,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return {"status": "success", "data": {"id": task.id}}


@router.put("/tasks/{task_id}")
async def update_grayscale_task(
    task_id: int,
    req: GrayscaleTaskUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(GrayscaleHealingTask).where(GrayscaleHealingTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Grayscale task not found")
    if req.phase is not None:
        task.phase = GrayscalePhase(req.phase)
    if req.target_devices is not None:
        task.target_devices = req.target_devices
    if req.canary_result is not None:
        task.canary_result = req.canary_result
    if req.batch_result is not None:
        task.batch_result = req.batch_result
    if req.status is not None:
        task.status = GrayscaleTaskStatus(req.status)
    await db.commit()
    return {"status": "success", "data": {"id": task.id}}


@router.delete("/tasks/{task_id}")
async def delete_grayscale_task(
    task_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(GrayscaleHealingTask).where(GrayscaleHealingTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Grayscale task not found")
    await db.delete(task)
    await db.commit()
    return {"status": "success"}

@router.post("/tasks/{task_id}/advance")
async def advance_grayscale_phase(
    task_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(GrayscaleHealingTask).where(GrayscaleHealingTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Grayscale task not found")
    phase_order = [GrayscalePhase.CANARY, GrayscalePhase.BATCH, GrayscalePhase.ROLLBACK]
    current_idx = phase_order.index(task.phase) if task.phase in phase_order else -1
    if current_idx >= len(phase_order) - 1:
        task.status = GrayscaleTaskStatus.COMPLETED
    else:
        task.phase = phase_order[current_idx + 1]
    await db.commit()
    return {"status": "success", "data": {"id": task.id, "phase": task.phase.value, "status": task.status.value if task.status else None}}


@router.get("/evaluations")
async def list_healing_evaluations(
    event_id: Optional[int] = Query(None),
    evaluation_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(HealingEvaluation)
    if event_id is not None:
        query = query.where(HealingEvaluation.event_id == event_id)
    if evaluation_type:
        query = query.where(HealingEvaluation.evaluation_type == evaluation_type)
    result = await db.execute(query.limit(50))
    evaluations = result.scalars().all()
    return {"status": "success", "data": [{"id": e.id, "event_id": e.event_id, "evaluation_type": e.evaluation_type.value if e.evaluation_type else None, "metrics_before": e.metrics_before, "metrics_after": e.metrics_after, "success": e.success, "evaluation_notes": e.evaluation_notes, "evaluated_at": e.evaluated_at.isoformat() if e.evaluated_at else None} for e in evaluations]}


@router.post("/evaluations")
async def create_healing_evaluation(
    req: HealingEvaluationCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    evaluation = HealingEvaluation(
        event_id=req.event_id,
        evaluation_type=HealingEvaluationType(req.evaluation_type),
        metrics_before=req.metrics_before,
        metrics_after=req.metrics_after,
        success=req.success,
        evaluation_notes=req.evaluation_notes,
    )
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)
    return {"status": "success", "data": {"id": evaluation.id}}
