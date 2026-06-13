from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import TraceSpan
from .deps import get_current_user

router = APIRouter()


class SpanCreate(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    operation_name: str
    service_name: str
    start_time: str
    status_code: Optional[str] = None
    attributes: Optional[dict] = None


@router.get("/traces")
async def list_traces(
    service_name: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(TraceSpan)
    if service_name:
        query = query.where(TraceSpan.service_name == service_name)
    if status_code:
        query = query.where(TraceSpan.status_code == status_code)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    spans = result.scalars().all()
    return {"status": "success", "data": [{"id": s.id, "trace_id": s.trace_id, "span_id": s.span_id, "operation_name": s.operation_name, "service_name": s.service_name, "status_code": s.status_code} for s in spans]}


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(TraceSpan).where(TraceSpan.trace_id == trace_id))
    spans = result.scalars().all()
    if not spans:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {"status": "success", "data": [{"id": s.id, "span_id": s.span_id, "parent_span_id": s.parent_span_id, "operation_name": s.operation_name, "service_name": s.service_name, "start_time": s.start_time.isoformat() if s.start_time else None, "end_time": s.end_time.isoformat() if s.end_time else None, "status_code": s.status_code, "attributes": s.attributes} for s in spans]}


@router.post("/spans")
async def create_span(
    req: SpanCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    from datetime import datetime
    span = TraceSpan(
        trace_id=req.trace_id, span_id=req.span_id, parent_span_id=req.parent_span_id,
        operation_name=req.operation_name, service_name=req.service_name,
        start_time=datetime.fromisoformat(req.start_time), status_code=req.status_code, attributes=req.attributes,
    )
    db.add(span)
    await db.commit()
    await db.refresh(span)
    return {"status": "success", "data": {"id": span.id}}


@router.get("/metrics")
async def get_metrics_summary(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(func.count()).select_from(TraceSpan))
    total_spans = result.scalar() or 0
    error_result = await db.execute(select(func.count()).select_from(TraceSpan).where(TraceSpan.status_code == "ERROR"))
    error_spans = error_result.scalar() or 0
    return {"status": "success", "data": {"total_spans": total_spans, "error_spans": error_spans, "error_rate": round(error_spans / max(total_spans, 1) * 100, 2)}}
