from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from ..database.connection import get_db_session
from ..database.models import Device
from .deps import get_current_user

router = APIRouter()

# 内存中的地图标注数据
_map_annotations: list = []


class MapAnnotation(BaseModel):
    id: Optional[int] = None
    name: str
    latitude: float
    longitude: float
    annotation_type: str
    device_id: Optional[int] = None
    metadata: Optional[dict] = None


class MapAnnotationUpdate(BaseModel):
    name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    annotation_type: Optional[str] = None
    device_id: Optional[int] = None
    metadata: Optional[dict] = None


@router.get("/devices")
async def get_device_locations(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Device))
    devices = result.scalars().all()
    locations = [{"id": d.id, "name": d.name, "ip": d.ip, "location": d.location, "status": d.status.value} for d in devices if d.location]
    return {"status": "success", "data": locations}


@router.get("/annotations")
async def list_annotations(
    annotation_type: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
):
    filtered = _map_annotations
    if annotation_type:
        filtered = [a for a in _map_annotations if a.get("annotation_type") == annotation_type]
    return {"status": "success", "data": filtered}


@router.post("/annotations")
async def create_annotation(
    req: MapAnnotation,
    current_user=Depends(get_current_user),
):
    annotation = req.model_dump()
    annotation["id"] = len(_map_annotations) + 1
    _map_annotations.append(annotation)
    return {"status": "success", "data": annotation}


@router.get("/annotations/{annotation_id}")
async def get_annotation(
    annotation_id: int,
    current_user=Depends(get_current_user),
):
    for a in _map_annotations:
        if a.get("id") == annotation_id:
            return {"status": "success", "data": a}
    raise HTTPException(status_code=404, detail="Annotation not found")


@router.put("/annotations/{annotation_id}")
async def update_annotation(
    annotation_id: int,
    req: MapAnnotationUpdate,
    current_user=Depends(get_current_user),
):
    for i, a in enumerate(_map_annotations):
        if a.get("id") == annotation_id:
            update_data = {k: v for k, v in req.model_dump().items() if v is not None}
            _map_annotations[i].update(update_data)
            return {"status": "success", "data": _map_annotations[i]}
    raise HTTPException(status_code=404, detail="Annotation not found")


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(
    annotation_id: int,
    current_user=Depends(get_current_user),
):
    global _map_annotations
    _map_annotations = [a for a in _map_annotations if a.get("id") != annotation_id]
    return {"status": "success"}
