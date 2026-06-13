from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import AgentRegistry
from .deps import get_current_user

router = APIRouter()


class CrossDomainMessage(BaseModel):
    source_agent_id: str
    target_agent_id: str
    message_type: str
    payload: dict
    priority: Optional[str] = "normal"


@router.post("/send")
async def send_cross_domain_message(
    msg: CrossDomainMessage,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(AgentRegistry).where(AgentRegistry.agent_id == msg.target_agent_id))
    target_agent = result.scalar_one_or_none()
    if not target_agent:
        raise HTTPException(status_code=404, detail=f"Target agent {msg.target_agent_id} not found")

    return {"status": "success", "data": {"message_id": "placeholder", "source": msg.source_agent_id, "target": msg.target_agent_id, "status": "delivered"}}


@router.get("/agents")
async def list_a2a_agents(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(AgentRegistry))
    agents = result.scalars().all()
    return {"status": "success", "data": [{"id": a.id, "agent_id": a.agent_id, "domain": a.domain, "a2a_endpoint": a.a2a_endpoint, "status": a.status} for a in agents]}


@router.get("/status/{agent_id}")
async def get_agent_status(
    agent_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(AgentRegistry).where(AgentRegistry.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "success", "data": {"agent_id": agent.agent_id, "domain": agent.domain, "status": agent.status, "capabilities": agent.capabilities}}
