from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from .deps import get_current_user

router = APIRouter()

# 内存中的熔断器状态（生产环境应使用Redis）
_fuse_states: dict = {}


class FuseConfig(BaseModel):
    service_name: str
    failure_threshold: int = 5
    recovery_timeout_seconds: int = 60
    half_open_max_calls: int = 3


class FuseConfigUpdate(BaseModel):
    failure_threshold: Optional[int] = None
    recovery_timeout_seconds: Optional[int] = None
    half_open_max_calls: Optional[int] = None


@router.get("/")
async def list_fuses(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    return {"status": "success", "data": list(_fuse_states.values())}


@router.get("/{service_name}")
async def get_fuse_status(
    service_name: str,
    current_user=Depends(get_current_user),
):
    if service_name not in _fuse_states:
        return {"status": "success", "data": {"service_name": service_name, "state": "closed", "failure_count": 0}}
    return {"status": "success", "data": _fuse_states[service_name]}


@router.post("/")
async def create_fuse_config(
    config: FuseConfig,
    current_user=Depends(get_current_user),
):
    _fuse_states[config.service_name] = {
        "service_name": config.service_name,
        "state": "closed",
        "failure_count": 0,
        "failure_threshold": config.failure_threshold,
        "recovery_timeout_seconds": config.recovery_timeout_seconds,
        "half_open_max_calls": config.half_open_max_calls,
    }
    return {"status": "success", "data": _fuse_states[config.service_name]}


@router.put("/{service_name}")
async def update_fuse_config(
    service_name: str,
    req: FuseConfigUpdate,
    current_user=Depends(get_current_user),
):
    if service_name not in _fuse_states:
        raise HTTPException(status_code=404, detail="Fuse config not found")
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    if update_data:
        _fuse_states[service_name].update(update_data)
    return {"status": "success", "data": _fuse_states[service_name]}


@router.put("/{service_name}/reset")
async def reset_fuse(
    service_name: str,
    current_user=Depends(get_current_user),
):
    if service_name in _fuse_states:
        _fuse_states[service_name]["state"] = "closed"
        _fuse_states[service_name]["failure_count"] = 0
    return {"status": "success", "message": f"熔断器 {service_name} 已重置"}


@router.delete("/{service_name}")
async def delete_fuse_config(
    service_name: str,
    current_user=Depends(get_current_user),
):
    if service_name not in _fuse_states:
        raise HTTPException(status_code=404, detail="Fuse config not found")
    del _fuse_states[service_name]
    return {"status": "success"}
