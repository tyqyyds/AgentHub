from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import get_db_session
from backend.database.models import Intent
from backend.telemetry.collector import get_telemetry_collector
from backend.telemetry.sla_evaluator import get_sla_evaluator
from backend.telemetry.policy_reconstructor import get_policy_reconstructor
from backend.core.security.rbac import get_current_user

router = APIRouter()


@router.get("/devices/{device_id}")
async def get_device_metrics(device_id: str, current_user=Depends(get_current_user)):
    collector = get_telemetry_collector()
    metrics = await collector.collect_device_metrics(device_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found in telemetry")
    return {"status": "success", "data": metrics}


@router.get("/devices")
async def get_all_device_metrics(current_user=Depends(get_current_user)):
    collector = get_telemetry_collector()
    metrics = await collector.collect_all_devices()
    return {"status": "success", "data": metrics}


@router.get("/devices/{device_id}/history")
async def get_metric_history(
    device_id: str,
    metric_name: str = Query(..., description="Metric name to retrieve history for"),
    minutes: int = Query(30, ge=1, le=1440, description="Number of minutes of history"),
    current_user=Depends(get_current_user),
):
    collector = get_telemetry_collector()
    history = await collector.get_metric_history(device_id, metric_name, minutes)
    return {"status": "success", "data": history}


@router.get("/sla/status")
async def get_sla_status(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    evaluator = get_sla_evaluator()
    cached_results = evaluator.get_evaluation_results()

    result = await db.execute(
        select(Intent).where(
            Intent.execution_status.in_(["executed", "approved_pending_execution"]),
            Intent.sla_conditions.isnot(None),
        )
    )
    intents = result.scalars().all()

    sla_statuses = []
    for intent in intents:
        intent_result = cached_results.get(intent.id, {
            "sla_status": intent.sla_status or "UNKNOWN",
            "violations": [],
            "evaluated_at": intent.last_evaluation_time.isoformat() if intent.last_evaluation_time else None,
        })
        sla_statuses.append({
            "intent_id": intent.id,
            "intent_name": intent.intent_name,
            "sla_status": intent_result.get("sla_status", intent.sla_status or "UNKNOWN"),
            "violations": intent_result.get("violations", []),
            "evaluated_at": intent_result.get("evaluated_at"),
            "last_evaluation_time": intent.last_evaluation_time.isoformat() if intent.last_evaluation_time else None,
        })

    return {"status": "success", "data": sla_statuses}


@router.post("/sla/evaluate")
async def trigger_sla_evaluation(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    evaluator = get_sla_evaluator()
    reconstructor = get_policy_reconstructor()

    evaluation_results = await evaluator.evaluate_all_intents()

    reconstruction_results = {}
    for intent_id, evaluation in evaluation_results.items():
        if evaluation.get("sla_status") == "DEVIATING":
            collector = get_telemetry_collector()
            current_metrics = await collector.collect_all_devices()
            reconstruction = await reconstructor.reconstruct_policy(
                intent_id=intent_id,
                violations=evaluation.get("violations", []),
                current_metrics=current_metrics,
            )
            reconstruction_results[intent_id] = reconstruction

    return {
        "status": "success",
        "data": {
            "evaluation_results": {str(k): v for k, v in evaluation_results.items()},
            "reconstruction_results": {str(k): v for k, v in reconstruction_results.items()},
        },
    }
