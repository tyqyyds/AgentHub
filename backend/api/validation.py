from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from ..database.connection import get_db_session
from ..database.models import Intent, ExecutionStatus, ApprovalStatus, ChangeImpactAnalysis, RiskLevel
from .deps import get_current_user

router = APIRouter()


class ValidationRequest(BaseModel):
    intent_id: int


class ConflictCheckRequest(BaseModel):
    intent_type: str
    device_scope: dict
    structured_params: dict


@router.post("/validate")
async def validate_intent(
    req: ValidationRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Intent).where(Intent.id == req.intent_id))
    intent = result.scalar_one_or_none()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    issues = []
    if intent.execution_status == ExecutionStatus.CONFLICT_DETECTED:
        issues.append({"type": "conflict", "message": "意图存在冲突", "detail": intent.conflict_result})
    if intent.approval_status == ApprovalStatus.REJECTED:
        issues.append({"type": "rejected", "message": "意图已被拒绝"})

    return {"status": "success", "data": {"intent_id": req.intent_id, "valid": len(issues) == 0, "issues": issues}}


@router.post("/conflict-check")
async def conflict_precheck(
    req: ConflictCheckRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(func.count()).select_from(Intent).where(Intent.execution_status == ExecutionStatus.EXECUTING)
    )
    executing_count = result.scalar() or 0

    conflicts = []
    if executing_count > 10:
        conflicts.append({"type": "overload", "message": f"当前有 {executing_count} 个意图正在执行，可能存在资源竞争"})

    return {"status": "success", "data": {"has_conflict": len(conflicts) > 0, "conflicts": conflicts}}


@router.get("/impact/{intent_id}")
async def get_impact_analysis(
    intent_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(ChangeImpactAnalysis).where(ChangeImpactAnalysis.intent_id == intent_id)
    )
    analysis = result.scalars().all()
    return {"status": "success", "data": [{"id": a.id, "risk_level": a.risk_level.value, "impact_score": a.impact_score, "affected_devices": a.affected_devices} for a in analysis]}
