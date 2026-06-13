from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import SLAEvaluationResult, SLAPrediction, Intent
from .deps import get_current_user

router = APIRouter()


class SLAEvaluationCreate(BaseModel):
    intent_id: int
    metric_name: str
    target_value: float
    actual_value: float
    unit: Optional[str] = None
    compliance: bool


class SLAPredictionCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    intent_id: int
    predicted_metric: str
    predicted_value: float
    confidence: Optional[float] = None
    prediction_horizon_hours: Optional[int] = None
    model_version: Optional[str] = None


@router.get("/evaluations")
async def list_sla_evaluations(
    intent_id: Optional[int] = Query(None),
    compliance: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(SLAEvaluationResult)
    if intent_id is not None:
        query = query.where(SLAEvaluationResult.intent_id == intent_id)
    if compliance is not None:
        query = query.where(SLAEvaluationResult.compliance == compliance)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    evaluations = result.scalars().all()
    return {"status": "success", "data": [{"id": e.id, "intent_id": e.intent_id, "metric_name": e.metric_name, "target_value": e.target_value, "actual_value": e.actual_value, "unit": e.unit, "compliance": e.compliance, "evaluated_at": e.evaluated_at.isoformat() if e.evaluated_at else None} for e in evaluations]}


@router.get("/predictions")
async def list_sla_predictions(
    intent_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(SLAPrediction)
    if intent_id is not None:
        query = query.where(SLAPrediction.intent_id == intent_id)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    predictions = result.scalars().all()
    return {"status": "success", "data": [{"id": p.id, "intent_id": p.intent_id, "predicted_metric": p.predicted_metric, "predicted_value": p.predicted_value, "confidence": p.confidence, "prediction_horizon_hours": p.prediction_horizon_hours, "model_version": p.model_version, "predicted_at": p.predicted_at.isoformat() if p.predicted_at else None} for p in predictions]}


@router.post("/evaluations")
async def create_sla_evaluation(
    req: SLAEvaluationCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    intent_result = await db.execute(select(Intent).where(Intent.id == req.intent_id))
    if not intent_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Intent not found")
    evaluation = SLAEvaluationResult(
        intent_id=req.intent_id, metric_name=req.metric_name,
        target_value=req.target_value, actual_value=req.actual_value,
        unit=req.unit, compliance=req.compliance,
    )
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)
    return {"status": "success", "data": {"id": evaluation.id}}


@router.post("/predictions")
async def create_sla_prediction(
    req: SLAPredictionCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    intent_result = await db.execute(select(Intent).where(Intent.id == req.intent_id))
    if not intent_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Intent not found")
    prediction = SLAPrediction(
        intent_id=req.intent_id, predicted_metric=req.predicted_metric,
        predicted_value=req.predicted_value, confidence=req.confidence,
        prediction_horizon_hours=req.prediction_horizon_hours, model_version=req.model_version,
    )
    db.add(prediction)
    await db.commit()
    await db.refresh(prediction)
    return {"status": "success", "data": {"id": prediction.id}}


@router.get("/dashboard")
async def sla_dashboard(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    total_result = await db.execute(select(func.count()).select_from(SLAEvaluationResult))
    total = total_result.scalar() or 0
    compliant_result = await db.execute(select(func.count()).select_from(SLAEvaluationResult).where(SLAEvaluationResult.compliance == True))
    compliant = compliant_result.scalar() or 0
    compliance_rate = round(compliant / max(total, 1) * 100, 2)
    return {"status": "success", "data": {"total_evaluations": total, "compliant": compliant, "non_compliant": total - compliant, "compliance_rate": compliance_rate}}
