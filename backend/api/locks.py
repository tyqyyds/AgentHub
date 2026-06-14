from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import get_db_session
from backend.database.models import AuditLog
from backend.utils.lock_manager import lock_manager
from backend.core.security.rbac import get_current_user
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class LockRequest(BaseModel):
    device_id: str
    owner: str = "system"
    wait_timeout: int = 0

class UnlockRequest(BaseModel):
    device_id: str
    token: str

class ExtendLockRequest(BaseModel):
    device_id: str
    token: str

class LockResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: str = ""
    locked_by: Optional[str] = None

@router.post("/lock", response_model=LockResponse)
async def acquire_device_lock(request: LockRequest, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    device_id = request.device_id
    owner = current_user.username
    wait_timeout = request.wait_timeout

    if wait_timeout > 0:
        token = await lock_manager.acquire_lock_with_wait(device_id, owner, wait_timeout)
    else:
        token = await lock_manager.acquire_lock(device_id, owner)

    if token:
        db.add(AuditLog(
            action="lock_acquire",
            user_id=current_user.username,
            target_device=request.device_id,
            status="success",
            timestamp=datetime.now(timezone.utc)
        ))
        await db.commit()
        return LockResponse(
            success=True,
            token=token,
            message=f"成功获取设备 {device_id} 的配置锁"
        )
    else:
        lock_info = await lock_manager.get_lock_info(device_id)
        return LockResponse(
            success=False,
            message=f"无法获取设备 {device_id} 的配置锁",
            locked_by=lock_info.get("owner") if lock_info else None
        )

@router.post("/unlock")
async def release_device_lock(request: UnlockRequest, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    success = await lock_manager.release_lock(request.device_id, request.token)
    
    if success:
        db.add(AuditLog(
            action="lock_release",
            user_id=current_user.username,
            target_device=request.device_id,
            status="success",
            timestamp=datetime.now(timezone.utc)
        ))
        await db.commit()
        return {"status": "success", "message": f"成功释放设备 {request.device_id} 的配置锁"}
    else:
        raise HTTPException(status_code=400, detail="释放锁失败：无效的token或设备未被锁定")

@router.get("/lock/status/{device_id}")
async def check_lock_status(device_id: str, current_user=Depends(get_current_user)):
    is_locked = await lock_manager.is_locked(device_id)
    lock_info = await lock_manager.get_lock_info(device_id)
    
    if is_locked and lock_info:
        return {
            "status": "locked",
            "device_id": device_id,
            "owner": lock_info["owner"],
            "ttl_seconds": lock_info["ttl"]
        }
    else:
        return {"status": "unlocked", "device_id": device_id}

@router.get("")
async def get_all_locks(current_user=Depends(get_current_user)):
    locks = await lock_manager.get_all_locks()
    return {"status": "success", "data": locks}

@router.post("/lock/extend")
async def extend_lock(request: ExtendLockRequest, current_user=Depends(get_current_user)):
    success = await lock_manager.extend_lock(request.device_id, request.token)
    
    if success:
        return {"status": "success", "message": "锁有效期已延长"}
    else:
        raise HTTPException(status_code=400, detail="延长锁失败：无效的token或设备未被锁定")