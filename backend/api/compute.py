from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from backend.core.security.rbac import get_current_user, requires_permission
from backend.compute.task_scheduler import task_scheduler
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class SubmitTaskRequest(BaseModel):
    task_type: str
    params: Dict[str, Any] = {}
    priority: str = "medium"


def _serialize_task(task: dict) -> dict:
    result = dict(task)
    if "created_at" in result and hasattr(result["created_at"], "isoformat"):
        result["created_at"] = result["created_at"].isoformat()
    if "updated_at" in result and hasattr(result["updated_at"], "isoformat"):
        result["updated_at"] = result["updated_at"].isoformat()
    return result


@router.post("/tasks")
async def submit_task(req: SubmitTaskRequest, current_user=Depends(get_current_user), _: None = Depends(requires_permission("system:manage"))):
    try:
        task = await task_scheduler.submit_task(
            task_type=req.task_type,
            params=req.params,
            priority=req.priority,
        )
        return {"status": "success", "data": _serialize_task(task)}
    except Exception as e:
        logger.error(f"Submit compute task failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tasks")
async def list_tasks(current_user=Depends(get_current_user)):
    try:
        tasks = task_scheduler.list_tasks()
        return {"status": "success", "data": [_serialize_task(t) for t in tasks], "total": len(tasks)}
    except Exception as e:
        logger.error(f"List compute tasks failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, current_user=Depends(get_current_user)):
    task = task_scheduler.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return {"status": "success", "data": _serialize_task(task)}


@router.get("/nodes")
async def list_compute_nodes(current_user=Depends(get_current_user)):
    try:
        nodes = task_scheduler.get_compute_nodes()
        return {"status": "success", "data": nodes, "total": len(nodes)}
    except Exception as e:
        logger.error(f"List compute nodes failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: str, current_user=Depends(get_current_user), _: None = Depends(requires_permission("system:manage"))):
    task = task_scheduler.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    if task.get("status") in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel task in {task['status']} status")
    cancelled = await task_scheduler.cancel_task(task_id)
    return {"status": "success", "data": _serialize_task(cancelled)}


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str, current_user=Depends(get_current_user), _: None = Depends(requires_permission("system:manage"))):
    task = task_scheduler.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    if task.get("status") not in ("failed", "cancelled"):
        raise HTTPException(status_code=400, detail="Can only retry failed or cancelled tasks")
    new_task = await task_scheduler.submit_task(
        task_type=task["task_type"],
        params=task.get("params", {}),
        priority=task.get("priority", "medium"),
    )
    return {"status": "success", "data": _serialize_task(new_task), "message": f"Task retried as new task {new_task['task_id']}"}


@router.get("/system-stats")
async def system_stats(current_user=Depends(get_current_user)):
    try:
        stats = task_scheduler.get_system_stats()
        return {"status": "success", "data": stats}
    except Exception as e:
        logger.error(f"Get system stats failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
