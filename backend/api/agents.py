from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from ..database.connection import get_db_session
from ..database.models import AgentRegistry

router = APIRouter()


class AgentCreate(BaseModel):
    agent_id: str
    domain: str
    ip: Optional[str] = None
    a2a_endpoint: str
    capabilities: Optional[list] = None


@router.post("/")
async def register_agent(agent: AgentCreate, db: AsyncSession = Depends(get_db_session)):
    new_agent = AgentRegistry(
        agent_id=agent.agent_id,
        domain=agent.domain,
        ip=agent.ip,
        a2a_endpoint=agent.a2a_endpoint,
        capabilities=agent.capabilities or []
    )
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)
    return {"status": "success", "data": {"id": new_agent.id}}


@router.get("/")
async def get_agents(domain: Optional[str] = None, status: Optional[str] = None, db: AsyncSession = Depends(get_db_session)):
    query = AgentRegistry.__table__.select()
    if domain:
        query = query.where(AgentRegistry.domain == domain)
    if status:
        query = query.where(AgentRegistry.status == status)
    
    result = await db.execute(query)
    agents = result.fetchall()
    return {"status": "success", "data": [dict(row._mapping) for row in agents]}


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(AgentRegistry.__table__.select().where(AgentRegistry.agent_id == agent_id))
    agent = result.first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "success", "data": dict(agent._mapping)}


@router.put("/{agent_id}")
async def update_agent(agent_id: str, agent: AgentCreate, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(AgentRegistry.__table__.select().where(AgentRegistry.agent_id == agent_id))
    existing = result.first()
    if not existing:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    await db.execute(
        AgentRegistry.__table__.update()
        .where(AgentRegistry.agent_id == agent_id)
        .values(
            domain=agent.domain,
            ip=agent.ip,
            a2a_endpoint=agent.a2a_endpoint,
            capabilities=agent.capabilities
        )
    )
    await db.commit()
    return {"status": "success"}


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(AgentRegistry.__table__.select().where(AgentRegistry.agent_id == agent_id))
    agent = result.first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    await db.execute(AgentRegistry.__table__.delete().where(AgentRegistry.agent_id == agent_id))
    await db.commit()
    return {"status": "success"}