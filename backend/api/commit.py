from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import get_db_session
from backend.database.models import AuditLog
from backend.utils.commit_confirmed import commit_manager
from backend.core.security.rbac import get_current_user, requires_permission
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class CommitRequest(BaseModel):
    device_id: str
    commands: list[str]
    confirm_timeout_minutes: int = 5

    @field_validator('confirm_timeout_minutes')
    @classmethod
    def validate_timeout(cls, v):
        if v < 0.5:
            raise ValueError('确认超时时间不能小于0.5分钟')
        if v > 60:
            raise ValueError('确认超时时间不能超过60分钟')
        return v

class CommitResponse(BaseModel):
    success: bool
    commit_id: str
    message: str

@router.post("", response_model=CommitResponse)
async def execute_commit_confirmed(request: CommitRequest, background_tasks: BackgroundTasks, current_user=Depends(requires_permission("system:manage"))):
    try:
        timeout = timedelta(minutes=request.confirm_timeout_minutes)
        
        commit_id = commit_manager.generate_commit_id()
        
        commit_manager.create_pending_commit(
            commit_id,
            request.device_id,
            request.commands,
            timeout
        )
        
        background_tasks.add_task(
            commit_manager.execute_with_confirm,
            request.device_id,
            request.commands,
            timeout,
            commit_id
        )
        
        return CommitResponse(
            success=True,
            commit_id=commit_id,
            message=f"命令已发送到设备 {request.device_id}，请在 {request.confirm_timeout_minutes} 分钟内确认"
        )
        
    except Exception as e:
        logger.error(f"Execute commit confirmed failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{commit_id}/confirm")
async def confirm_commit(commit_id: str, current_user=Depends(requires_permission("system:manage")), db: AsyncSession = Depends(get_db_session)):
    commit_manager.confirm_commit(commit_id)
    commits = commit_manager.get_pending_commits()
    commit = next((c for c in commits if c["commit_id"] == commit_id), None)
    device_id = commit.get("device_id", "system") if commit else "system"
    db.add(AuditLog(
        action="commit_confirm",
        user_id=current_user.username,
        target_device=device_id,
        status="success",
        timestamp=datetime.now(timezone.utc)
    ))
    await db.commit()
    return {"status": "success", "message": f"提交 {commit_id} 已确认"}

@router.post("/{commit_id}/cancel")
async def cancel_commit(commit_id: str, current_user=Depends(requires_permission("system:manage")), db: AsyncSession = Depends(get_db_session)):
    success = commit_manager.cancel_commit(commit_id)
    if success:
        db.add(AuditLog(
            action="commit_cancel",
            user_id=current_user.username,
            target_device="system",
            status="success",
            timestamp=datetime.now(timezone.utc)
        ))
        await db.commit()
        return {"status": "success", "message": f"提交 {commit_id} 已取消，将自动回滚"}
    else:
        raise HTTPException(status_code=400, detail="无法取消提交：提交不存在或状态不允许")

@router.get("/pending")
async def get_pending_commits(current_user=Depends(get_current_user)):
    commits = commit_manager.get_pending_commits()
    return {"status": "success", "data": commits}

@router.get("/{commit_id}/status")
async def get_commit_status(commit_id: str, current_user=Depends(get_current_user)):
    commits = commit_manager.get_pending_commits()
    commit = next((c for c in commits if c["commit_id"] == commit_id), None)
    
    if commit:
        return {"status": "success", "data": commit}
    else:
        raise HTTPException(status_code=404, detail="提交不存在或已完成")