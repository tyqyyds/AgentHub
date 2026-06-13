from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from ..database.connection import get_db_session
from ..database.models import Device, BehaviorAnomaly, AnomalySeverity
from .deps import get_current_user

router = APIRouter()


class TelemetryQuery(BaseModel):
    device_id: int
    metrics: List[str]
    time_range_minutes: int = 60


@router.get("/devices/{device_id}")
async def get_device_telemetry(
    device_id: int,
    metrics: str = Query("cpu,memory,bandwidth"),
    minutes: int = Query(60, ge=1, le=1440),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    metric_list = metrics.split(",")
    telemetry = {m: {"current": 0.0, "avg": 0.0, "max": 0.0, "unit": "%"} for m in metric_list}
    return {"status": "success", "data": {"device_id": device_id, "device_name": device.name, "telemetry": telemetry, "time_range_minutes": minutes}}


@router.get("/anomalies")
async def list_anomalies(
    device_id: Optional[int] = Query(None),
    severity: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(BehaviorAnomaly)
    if device_id:
        query = query.where(BehaviorAnomaly.device_id == device_id)
    if severity:
        try:
            query = query.where(BehaviorAnomaly.severity == AnomalySeverity(severity))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid severity")
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    anomalies = result.scalars().all()
    return {"status": "success", "data": [{"id": a.id, "device_id": a.device_id, "anomaly_type": a.anomaly_type, "severity": a.severity.value, "description": a.description, "detected_at": a.detected_at.isoformat() if a.detected_at else None, "resolved": a.resolved} for a in anomalies]}


@router.post("/collect")
async def collect_telemetry(
    req: TelemetryQuery,
    current_user=Depends(get_current_user),
):
    return {"status": "success", "data": {"device_id": req.device_id, "message": "Telemetry collection initiated", "metrics": req.metrics}}
