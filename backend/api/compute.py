from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from .deps import get_current_user

router = APIRouter()

# 内存中的计算资源状态（生产环境应对接实际调度器）
_compute_resources: dict = {}


class ComputeResourceCreate(BaseModel):
    resource_id: str
    name: str
    resource_type: str
    capacity: dict
    endpoint: Optional[str] = None


class ComputeScheduleRequest(BaseModel):
    task_type: str
    requirements: dict
    priority: Optional[str] = "normal"


class ComputeResourceUpdate(BaseModel):
    name: Optional[str] = None
    resource_type: Optional[str] = None
    capacity: Optional[dict] = None
    endpoint: Optional[str] = None


@router.get("/")
async def list_compute_resources(
    current_user=Depends(get_current_user),
):
    return {"status": "success", "data": list(_compute_resources.values())}


@router.get("/{resource_id}")
async def get_compute_resource(
    resource_id: str,
    current_user=Depends(get_current_user),
):
    if resource_id not in _compute_resources:
        raise HTTPException(status_code=404, detail="Compute resource not found")
    return {"status": "success", "data": _compute_resources[resource_id]}


@router.post("/")
async def create_compute_resource(
    req: ComputeResourceCreate,
    current_user=Depends(get_current_user),
):
    _compute_resources[req.resource_id] = {**req.model_dump(), "status": "available", "current_load": 0.0}
    return {"status": "success", "data": _compute_resources[req.resource_id]}


@router.put("/{resource_id}")
async def update_compute_resource(
    resource_id: str,
    req: ComputeResourceUpdate,
    current_user=Depends(get_current_user),
):
    if resource_id not in _compute_resources:
        raise HTTPException(status_code=404, detail="Compute resource not found")
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    if update_data:
        _compute_resources[resource_id].update(update_data)
    return {"status": "success", "data": _compute_resources[resource_id]}


@router.post("/schedule")
async def schedule_task(
    req: ComputeScheduleRequest,
    current_user=Depends(get_current_user),
):
    return {"status": "success", "data": {"task_id": "placeholder", "task_type": req.task_type, "assigned_resource": None, "status": "queued"}}


@router.delete("/{resource_id}")
async def delete_compute_resource(
    resource_id: str,
    current_user=Depends(get_current_user),
):
    if resource_id not in _compute_resources:
        raise HTTPException(status_code=404, detail="Compute resource not found")
    del _compute_resources[resource_id]
    return {"status": "success"}
