from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from backend.core.security.rbac import get_current_user, requires_permission
from backend.agents.agent_scorer import get_agent_scorer
from backend.agents.agent_hot_upgrade import get_hot_upgrade_manager
from backend.api.response import success_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class UpgradeRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    new_version: str = Field(..., min_length=1)
    strategy: str = Field(default="rolling")


class RegisterVersionRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    config: dict
    capabilities: list = Field(default=[])


@router.get("/scores")
async def list_agent_scores(current_user=Depends(get_current_user)):
    scorer = get_agent_scorer()
    top_agents = await scorer.get_top_agents(limit=100)
    return success_response(data=top_agents)


@router.get("/scores/{agent_id}")
async def get_agent_score(agent_id: str, current_user=Depends(get_current_user)):
    scorer = get_agent_scorer()
    score = await scorer.get_agent_score(agent_id)
    return success_response(data=score)


@router.post("/scores/recalculate")
async def recalculate_scores(current_user=Depends(get_current_user), _: None = Depends(requires_permission("agent:upgrade"))):
    scorer = get_agent_scorer()
    result = await scorer.recalculate_all_scores()
    return success_response(data=result)


@router.get("/recommendations/{task_type}")
async def get_agent_recommendations(task_type: str, current_user=Depends(get_current_user)):
    scorer = get_agent_scorer()
    recommendations = await scorer.get_agent_recommendations(task_type)
    return success_response(data=recommendations)


@router.post("/upgrade")
async def upgrade_agent(request: UpgradeRequest, current_user=Depends(get_current_user), _: None = Depends(requires_permission("agent:upgrade"))):
    manager = get_hot_upgrade_manager()
    result = await manager.upgrade_agent(
        agent_id=request.agent_id,
        new_version=request.new_version,
        strategy=request.strategy,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Upgrade failed"))
    return success_response(data=result)


@router.get("/upgrade/history")
async def get_upgrade_history(current_user=Depends(get_current_user)):
    manager = get_hot_upgrade_manager()
    result = await manager.get_upgrade_history()
    return success_response(data=result)


@router.get("/upgrade/{agent_id}/status")
async def get_upgrade_status(agent_id: str, current_user=Depends(get_current_user)):
    manager = get_hot_upgrade_manager()
    result = await manager.get_upgrade_status(agent_id)
    return success_response(data=result)


@router.post("/upgrade/{agent_id}/rollback")
async def rollback_upgrade(agent_id: str, current_user=Depends(get_current_user), _: None = Depends(requires_permission("agent:upgrade"))):
    manager = get_hot_upgrade_manager()
    result = await manager.rollback_upgrade(agent_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Rollback failed"))
    return success_response(data=result)
