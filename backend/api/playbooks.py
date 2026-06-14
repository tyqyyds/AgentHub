from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from backend.core.security.rbac import get_current_user, requires_permission
from backend.agents.playbook_engine import get_playbook_engine
from backend.api.response import success_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class StepDefinition(BaseModel):
    id: str
    type: str = Field(..., description="intent/approval/tool_call/wait/condition/notification")
    name: str
    params: Dict[str, Any] = Field(default={})
    next_step: Optional[str] = None
    condition: Optional[Dict[str, Any]] = None


class CreatePlaybookRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    category: str = Field(..., min_length=1)
    steps: List[StepDefinition] = Field(..., min_length=1)
    parameters_schema: Optional[Dict[str, Any]] = None
    is_public: bool = True
    tags: List[str] = []


class UpdatePlaybookRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1, max_length=2000)
    category: Optional[str] = None
    steps: Optional[List[StepDefinition]] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


class ExecutePlaybookRequest(BaseModel):
    parameter_values: Dict[str, Any] = {}


class ApproveStepRequest(BaseModel):
    approver: str


@router.get("")
async def list_playbooks(
    category: Optional[str] = None,
    is_public: Optional[bool] = None,
    author: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    current_user=Depends(get_current_user),
):
    try:
        engine = get_playbook_engine()
        playbooks = await engine.list_playbooks(
            category=category,
            is_public=is_public,
            author=author,
            search=search,
            limit=limit,
            offset=offset,
        )
        return success_response(data={"items": playbooks, "total": len(playbooks)})
    except Exception as e:
        logger.error(f"List playbooks failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/executions")
async def list_executions(
    playbook_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    current_user=Depends(get_current_user),
):
    try:
        engine = get_playbook_engine()
        executions = await engine.list_executions(
            playbook_id=playbook_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return success_response(data={"items": executions, "total": len(executions)})
    except Exception as e:
        logger.error(f"List executions failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str, current_user=Depends(get_current_user)):
    try:
        engine = get_playbook_engine()
        execution = await engine.get_execution_status(execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}")
        return success_response(data=execution)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/executions/{execution_id}/approve")
async def approve_step(
    execution_id: str,
    req: ApproveStepRequest,
    current_user=Depends(requires_permission("playbook:approve")),
):
    try:
        engine = get_playbook_engine()
        result = await engine.approve_step(execution_id, approver=req.approver)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}")
        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approve step failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    current_user=Depends(requires_permission("playbook:execute")),
):
    try:
        engine = get_playbook_engine()
        success = await engine.cancel_execution(execution_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot cancel execution: not found or already completed")
        return success_response(data={"execution_id": execution_id, "cancelled": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{playbook_id}")
async def get_playbook(playbook_id: str, current_user=Depends(get_current_user)):
    try:
        engine = get_playbook_engine()
        playbook = await engine.get_playbook(playbook_id)
        if playbook is None:
            raise HTTPException(status_code=404, detail=f"Playbook not found: {playbook_id}")
        return success_response(data=playbook)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get playbook failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("")
async def create_playbook(
    req: CreatePlaybookRequest,
    current_user=Depends(requires_permission("playbook:create")),
):
    try:
        engine = get_playbook_engine()
        steps_data = [s.model_dump() for s in req.steps]
        playbook = await engine.create_playbook(
            name=req.name,
            description=req.description,
            category=req.category,
            steps=steps_data,
            author=current_user.username,
            parameters_schema=req.parameters_schema,
            is_public=req.is_public,
            tags=req.tags,
        )
        from backend.agents.playbook_engine import _serialize_playbook
        return success_response(data=_serialize_playbook(playbook))
    except Exception as e:
        logger.error(f"Create playbook failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{playbook_id}")
async def update_playbook(
    playbook_id: str,
    req: UpdatePlaybookRequest,
    current_user=Depends(requires_permission("playbook:manage")),
):
    try:
        engine = get_playbook_engine()
        update_data = {}
        if req.name is not None:
            update_data["name"] = req.name
        if req.description is not None:
            update_data["description"] = req.description
        if req.category is not None:
            update_data["category"] = req.category
        if req.steps is not None:
            update_data["steps"] = [s.model_dump() for s in req.steps]
        if req.parameters_schema is not None:
            update_data["parameters_schema"] = req.parameters_schema
        if req.is_public is not None:
            update_data["is_public"] = req.is_public
        if req.tags is not None:
            update_data["tags"] = req.tags

        result = await engine.update_playbook(playbook_id, **update_data)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Playbook not found: {playbook_id}")
        return success_response(data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update playbook failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{playbook_id}")
async def delete_playbook(
    playbook_id: str,
    current_user=Depends(requires_permission("playbook:manage")),
):
    try:
        engine = get_playbook_engine()
        success = await engine.delete_playbook(playbook_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Playbook not found: {playbook_id}")
        return success_response(data={"playbook_id": playbook_id, "deleted": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete playbook failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{playbook_id}/execute")
async def execute_playbook(
    playbook_id: str,
    req: ExecutePlaybookRequest,
    current_user=Depends(requires_permission("playbook:execute")),
):
    try:
        engine = get_playbook_engine()
        execution = await engine.execute_playbook(
            playbook_id=playbook_id,
            parameter_values=req.parameter_values,
            triggered_by=current_user.username,
        )
        from backend.agents.playbook_engine import _serialize_execution
        return success_response(data=_serialize_execution(execution))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Execute playbook failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
