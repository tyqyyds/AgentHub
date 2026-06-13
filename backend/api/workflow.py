from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from ..database.connection import get_db_session
from ..database.models import ExecutionPlan, ApprovalStatus, Playbook, PlaybookExecution, PlaybookExecutionStatus
from .deps import get_current_user

router = APIRouter()


class WorkflowCreate(BaseModel):
    intent_id: int
    plan_steps: List[dict]
    estimated_duration_minutes: Optional[int] = None
    requires_approval: bool = True


class WorkflowExecuteRequest(BaseModel):
    plan_id: int
    triggered_by: Optional[str] = None

class WorkflowUpdate(BaseModel):
    plan_steps: Optional[List[dict]] = None
    estimated_duration_minutes: Optional[int] = None
    requires_approval: Optional[bool] = None


@router.get("/")
async def list_workflows(
    intent_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(ExecutionPlan)
    if intent_id:
        query = query.where(ExecutionPlan.intent_id == intent_id)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    plans = result.scalars().all()
    return {"status": "success", "data": [{"id": p.id, "intent_id": p.intent_id, "requires_approval": p.requires_approval, "approval_status": p.approval_status.value, "created_at": p.created_at.isoformat() if p.created_at else None} for p in plans]}


@router.get("/{plan_id}")
async def get_workflow(
    plan_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(ExecutionPlan).where(ExecutionPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"status": "success", "data": {"id": plan.id, "intent_id": plan.intent_id, "plan_steps": plan.plan_steps, "estimated_duration_minutes": plan.estimated_duration_minutes, "requires_approval": plan.requires_approval, "approval_status": plan.approval_status.value}}


@router.post("/")
async def create_workflow(
    req: WorkflowCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    plan = ExecutionPlan(intent_id=req.intent_id, plan_steps=req.plan_steps, estimated_duration_minutes=req.estimated_duration_minutes, requires_approval=req.requires_approval)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return {"status": "success", "data": {"id": plan.id}}


@router.put("/{plan_id}")
async def update_workflow(
    plan_id: int,
    req: WorkflowUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(ExecutionPlan).where(ExecutionPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if req.plan_steps is not None:
        plan.plan_steps = req.plan_steps
    if req.estimated_duration_minutes is not None:
        plan.estimated_duration_minutes = req.estimated_duration_minutes
    if req.requires_approval is not None:
        plan.requires_approval = req.requires_approval
    await db.commit()
    return {"status": "success", "data": {"id": plan.id}}

@router.post("/{plan_id}/approve")
async def approve_workflow(
    plan_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(ExecutionPlan).where(ExecutionPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Workflow not found")
    plan.approval_status = ApprovalStatus.APPROVED
    await db.commit()
    return {"status": "success"}


@router.post("/execute")
async def execute_workflow(
    req: WorkflowExecuteRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(ExecutionPlan).where(ExecutionPlan.id == req.plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if plan.approval_status != ApprovalStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Workflow not approved")

    execution = PlaybookExecution(playbook_id=req.plan_id, triggered_by=req.triggered_by or current_user.username, status=PlaybookExecutionStatus.RUNNING)
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return {"status": "success", "data": {"execution_id": execution.id, "status": execution.status.value}}


@router.delete("/{plan_id}")
async def delete_workflow(
    plan_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(ExecutionPlan).where(ExecutionPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await db.delete(plan)
    await db.commit()
    return {"status": "success"}
