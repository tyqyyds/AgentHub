from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from backend.core.config import settings
from backend.core.security.rbac import get_current_user, requires_permission
from backend.core.cache import api_cache
from backend.database.connection import get_db_session
from backend.database.models import Intent, SLAPrediction
from backend.telemetry.sla_evaluator import get_sla_evaluator
from backend.telemetry.sla_predictor import get_sla_predictor
from backend.api.response import success_response

router = APIRouter()
logger = logging.getLogger(__name__)


class IntervalUpdate(BaseModel):
    intent_id: int
    interval_seconds: int


class BulkIntervalUpdate(BaseModel):
    intervals: list[IntervalUpdate]


@router.get("/predictions")
async def list_predictions(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    predictor = get_sla_predictor()
    cached = predictor.get_all_predictions()

    result = await db.execute(
        select(SLAPrediction).order_by(SLAPrediction.created_at.desc()).limit(100)
    )
    db_predictions = result.scalars().all()

    predictions_by_intent = {}
    for p in cached:
        predictions_by_intent[p.intent_id] = {
            "intent_id": p.intent_id,
            "predicted_violation": p.predicted_violation,
            "violation_probability": p.violation_probability,
            "predicted_time": p.predicted_time.isoformat() if p.predicted_time else None,
            "prediction_model": p.prediction_model,
            "confidence": p.confidence,
            "metrics_forecast": p.metrics_forecast,
            "source": "cache",
        }

    for db_p in db_predictions:
        if db_p.intent_id not in predictions_by_intent:
            predictions_by_intent[db_p.intent_id] = {
                "intent_id": db_p.intent_id,
                "predicted_violation": db_p.predicted_violation,
                "violation_probability": db_p.violation_probability,
                "predicted_time": db_p.predicted_time.isoformat() if db_p.predicted_time else None,
                "prediction_model": db_p.prediction_model,
                "confidence": db_p.confidence,
                "metrics_forecast": db_p.metrics_forecast,
                "source": "database",
                "created_at": db_p.created_at.isoformat() if db_p.created_at else None,
            }

    return success_response(data=list(predictions_by_intent.values()))


@router.get("/predictions/{intent_id}")
async def get_prediction(
    intent_id: int,
    current_user=Depends(get_current_user),
):
    predictor = get_sla_predictor()
    prediction = predictor.get_prediction(intent_id)

    if prediction:
        return success_response(data={
                "intent_id": prediction.intent_id,
                "predicted_violation": prediction.predicted_violation,
                "violation_probability": prediction.violation_probability,
                "predicted_time": prediction.predicted_time.isoformat() if prediction.predicted_time else None,
                "prediction_model": prediction.prediction_model,
                "confidence": prediction.confidence,
                "metrics_forecast": prediction.metrics_forecast,
                "source": "cache",
            })

    from backend.database.connection import async_session_maker
    async with async_session_maker() as session:
        result = await session.execute(
            select(SLAPrediction)
            .where(SLAPrediction.intent_id == intent_id)
            .order_by(SLAPrediction.created_at.desc())
            .limit(1)
        )
        db_prediction = result.scalar_one_or_none()

    if db_prediction:
        return success_response(data={
                "intent_id": db_prediction.intent_id,
                "predicted_violation": db_prediction.predicted_violation,
                "violation_probability": db_prediction.violation_probability,
                "predicted_time": db_prediction.predicted_time.isoformat() if db_prediction.predicted_time else None,
                "prediction_model": db_prediction.prediction_model,
                "confidence": db_prediction.confidence,
                "metrics_forecast": db_prediction.metrics_forecast,
                "source": "database",
                "created_at": db_prediction.created_at.isoformat() if db_prediction.created_at else None,
            })

    raise HTTPException(status_code=404, detail=f"No prediction found for intent {intent_id}")


@router.post("/predict/{intent_id}")
async def trigger_prediction(
    intent_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("sla:read")),
):
    if not settings.sla_prediction_enabled:
        raise HTTPException(status_code=400, detail="SLA prediction is disabled")

    result = await db.execute(
        select(Intent).where(Intent.id == intent_id)
    )
    intent = result.scalar_one_or_none()

    if intent is None:
        raise HTTPException(status_code=404, detail=f"Intent {intent_id} not found")

    sla_conditions = intent.sla_conditions
    if not sla_conditions:
        raise HTTPException(status_code=400, detail=f"Intent {intent_id} has no SLA conditions")

    evaluator = get_sla_evaluator()
    historical = evaluator.get_historical_metrics(intent_id)

    predictor = get_sla_predictor()
    prediction = await predictor.predict_violation(
        intent_id=intent_id,
        sla_conditions=sla_conditions,
        historical_metrics=historical,
    )

    return success_response(data={
            "intent_id": prediction.intent_id,
            "predicted_violation": prediction.predicted_violation,
            "violation_probability": prediction.violation_probability,
            "predicted_time": prediction.predicted_time.isoformat() if prediction.predicted_time else None,
            "prediction_model": prediction.prediction_model,
            "confidence": prediction.confidence,
            "metrics_forecast": prediction.metrics_forecast,
        })


@router.get("/alerts")
async def get_sla_alerts(
    current_user=Depends(get_current_user),
):
    predictor = get_sla_predictor()
    alerts = predictor.generate_alerts()
    return success_response(data=alerts)


@router.get("/dynamic-intervals")
async def get_dynamic_intervals(
    current_user=Depends(get_current_user),
):
    evaluator = get_sla_evaluator()
    intervals = evaluator.get_dynamic_intervals()
    return success_response(data={
            "default_intervals": {
                "high": settings.sla_default_interval_high,
                "medium": settings.sla_default_interval_medium,
                "low": settings.sla_default_interval_low,
            },
            "per_intent": intervals,
        })


@router.put("/intervals")
async def update_intervals(
    update: BulkIntervalUpdate,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("system:manage")),
):
    evaluator = get_sla_evaluator()
    updated = []

    for item in update.intervals:
        if item.interval_seconds < 5:
            raise HTTPException(
                status_code=400,
                detail=f"Interval for intent {item.intent_id} must be at least 5 seconds",
            )
        evaluator.set_intent_interval(item.intent_id, item.interval_seconds)
        updated.append({
            "intent_id": item.intent_id,
            "interval_seconds": item.interval_seconds,
        })

    return success_response(data=updated)


@router.get("/dashboard")
async def sla_dashboard(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    # Check cache first (30s TTL for dashboard data)
    cached_dashboard = api_cache.get("sla_dashboard")
    if cached_dashboard is not None:
        logger.info("SLA Dashboard cache hit")
        return success_response(data=cached_dashboard)

    evaluator = get_sla_evaluator()
    predictor = get_sla_predictor()

    evaluation_results = evaluator.get_evaluation_results()
    predictions = predictor.get_all_predictions()
    alerts = predictor.generate_alerts()
    intervals = evaluator.get_dynamic_intervals()

    result = await db.execute(
        select(Intent).where(
            Intent.execution_status.in_(["completed", "running", "executed", "approved_pending_execution"]),
            Intent.sla_conditions.isnot(None),
        )
    )
    intents = result.scalars().all()

    dashboard_items = []
    for intent in intents:
        intent_id = intent.id
        evaluation = evaluation_results.get(intent_id, {})
        prediction = next((p for p in predictions if p.intent_id == intent_id), None)
        interval_info = intervals.get(intent_id, {})

        prediction_data = None
        if prediction:
            try:
                prediction_data = {
                    "predicted_violation": getattr(prediction, "predicted_violation", None),
                    "violation_probability": getattr(prediction, "violation_probability", None),
                    "predicted_time": prediction.predicted_time.isoformat() if hasattr(prediction, "predicted_time") and prediction.predicted_time else None,
                    "prediction_model": getattr(prediction, "prediction_model", None),
                    "confidence": getattr(prediction, "confidence", None),
                }
            except Exception:
                prediction_data = None

        dashboard_items.append({
            "intent_id": intent_id,
            "intent_name": intent.intent_name,
            "sla_status": evaluation.get("sla_status", intent.sla_status or "UNKNOWN"),
            "violations": evaluation.get("violations", []),
            "evaluated_at": evaluation.get("evaluated_at"),
            "prediction": prediction_data,
            "interval": interval_info,
        })

    achieving = sum(1 for item in dashboard_items if item["sla_status"] == "ACHIEVING")
    deviating = sum(1 for item in dashboard_items if item["sla_status"] == "DEVIATING")
    predicted_violations = sum(
        1 for item in dashboard_items
        if item.get("prediction") and item["prediction"]["predicted_violation"]
    )

    dashboard_data = {
            "summary": {
                "total_intents": len(dashboard_items),
                "achieving": achieving,
                "deviating": deviating,
                "predicted_violations": predicted_violations,
                "active_alerts": len(alerts),
            },
            "default_intervals": {
                "high": settings.sla_default_interval_high,
                "medium": settings.sla_default_interval_medium,
                "low": settings.sla_default_interval_low,
            },
            "alerts": alerts,
            "intents": dashboard_items,
        }

    # Cache the dashboard data for 30 seconds
    api_cache.set("sla_dashboard", dashboard_data, ttl_seconds=30)
    logger.info(f"SLA Dashboard cached, cache size={api_cache.size}")
    return success_response(data=dashboard_data)
