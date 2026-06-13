from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from ..database.connection import get_db_session
from .deps import get_current_user

router = APIRouter()

# 内存中的分布式锁状态（生产环境应使用Redis + Redlock）
_locks: dict = {}


class LockRequest(BaseModel):
    resource_key: str
    holder_id: str
    ttl_seconds: int = 300
    metadata: Optional[dict] = None


@router.get("/")
async def list_locks(
    current_user=Depends(get_current_user),
):
    return {"status": "success", "data": list(_locks.values())}


@router.get("/{resource_key}")
async def get_lock(
    resource_key: str,
    current_user=Depends(get_current_user),
):
    if resource_key not in _locks:
        raise HTTPException(status_code=404, detail="Lock not found")
    return {"status": "success", "data": _locks[resource_key]}


@router.post("/acquire")
async def acquire_lock(
    req: LockRequest,
    current_user=Depends(get_current_user),
):
    if req.resource_key in _locks:
        existing = _locks[req.resource_key]
        if existing["expires_at"] > datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="Resource is already locked", headers={"holder": existing["holder_id"]})
    _locks[req.resource_key] = {
        "resource_key": req.resource_key,
        "holder_id": req.holder_id,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": req.ttl_seconds,
        "metadata": req.metadata,
    }
    return {"status": "success", "data": {"resource_key": req.resource_key, "holder_id": req.holder_id}}


@router.post("/release")
async def release_lock(
    req: LockRequest,
    current_user=Depends(get_current_user),
):
    if req.resource_key not in _locks:
        raise HTTPException(status_code=404, detail="Lock not found")
    if _locks[req.resource_key]["holder_id"] != req.holder_id:
        raise HTTPException(status_code=403, detail="Not the lock holder")
    del _locks[req.resource_key]
    return {"status": "success", "message": f"锁 {req.resource_key} 已释放"}
