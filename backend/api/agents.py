from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from pydantic import BaseModel, field_validator
from backend.database.connection import get_db_session
from backend.database.models import AgentRegistry
from backend.core.security.rbac import get_current_user, requires_permission
from backend.api.response import success_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentCreate(BaseModel):
    agent_id: str
    domain: str
    ip: str = None
    a2a_endpoint: str
    capabilities: list = None

    @field_validator('agent_id')
    @classmethod
    def agent_id_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('agent_id cannot be empty')
        return v

    @field_validator('domain')
    @classmethod
    def domain_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('domain cannot be empty')
        return v

    @field_validator('a2a_endpoint')
    @classmethod
    def a2a_endpoint_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('a2a_endpoint cannot be empty')
        return v


@router.post("")
async def register_agent(agent: AgentCreate, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user), _: None = Depends(requires_permission("agents:manage"))):
    try:
        existing = await db.execute(select(AgentRegistry).where(AgentRegistry.agent_id == agent.agent_id))
        if existing.scalars().first():
            raise HTTPException(status_code=409, detail=f"Agent with ID '{agent.agent_id}' already exists")

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
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Register agent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("")
async def get_agents(
    domain: str = None,
    status: str = None,
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user)
):
    query = select(AgentRegistry).order_by(AgentRegistry.domain)
    if domain:
        query = query.where(AgentRegistry.domain == domain)
    if status:
        query = query.where(AgentRegistry.status == status)

    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    agents = result.scalars().all()

    count_query = select(func.count()).select_from(AgentRegistry)
    if domain:
        count_query = count_query.where(AgentRegistry.domain == domain)
    if status:
        count_query = count_query.where(AgentRegistry.status == status)
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return {
        "status": "success",
        "data": [{"id": a.id, "agent_id": a.agent_id, "domain": a.domain, "status": a.status, "ip": a.ip, "a2a_endpoint": a.a2a_endpoint, "capabilities": a.capabilities} for a in agents],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user)):
    result = await db.execute(select(AgentRegistry).where(AgentRegistry.agent_id == agent_id))
    agent = result.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "success", "data": {"id": agent.id, "agent_id": agent.agent_id, "domain": agent.domain, "status": agent.status, "ip": agent.ip, "a2a_endpoint": agent.a2a_endpoint, "capabilities": agent.capabilities}}


@router.put("/{agent_id}")
async def update_agent(agent_id: str, agent: AgentCreate, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user), _: None = Depends(requires_permission("agents:manage"))):
    result = await db.execute(select(AgentRegistry).where(AgentRegistry.agent_id == agent_id))
    existing = result.scalars().first()
    if not existing:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        existing.domain = agent.domain
        existing.ip = agent.ip
        existing.a2a_endpoint = agent.a2a_endpoint
        existing.capabilities = agent.capabilities
        await db.commit()
        return {"status": "success"}
    except Exception as e:
        await db.rollback()
        logger.error(f"Update agent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user), _: None = Depends(requires_permission("agents:manage"))):
    result = await db.execute(select(AgentRegistry).where(AgentRegistry.agent_id == agent_id))
    agent = result.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        await db.delete(agent)
        await db.commit()
        return {"status": "success"}
    except Exception as e:
        await db.rollback()
        logger.error(f"Delete agent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


class UpgradeRequest(BaseModel):
    version: str


@router.post("/{agent_id}/upgrade")
async def upgrade_agent(
    agent_id: str,
    req: UpgradeRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("agent:upgrade")),
):
    result = await db.execute(select(AgentRegistry).where(AgentRegistry.agent_id == agent_id))
    agent = result.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        old_version = agent.status or "v1.0"
        agent.status = f"v{req.version}"
        await db.commit()
        return success_response(data={
            "agent_id": agent_id,
            "old_version": old_version,
            "new_version": f"v{req.version}",
            "upgraded": True,
        })
    except Exception as e:
        await db.rollback()
        logger.error(f"Upgrade agent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{agent_id}/rollback")
async def rollback_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("agent:upgrade")),
):
    result = await db.execute(select(AgentRegistry).where(AgentRegistry.agent_id == agent_id))
    agent = result.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        current_version = agent.status or "v2.0"
        agent.status = "v1.0"
        await db.commit()
        return success_response(data={
            "agent_id": agent_id,
            "rolled_back_from": current_version,
            "rolled_back_to": "v1.0",
            "rolled_back": True,
        })
    except Exception as e:
        await db.rollback()
        logger.error(f"Rollback agent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")