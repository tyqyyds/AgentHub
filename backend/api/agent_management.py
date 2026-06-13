from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import AgentRegistry, AgentHealthRecord, AgentHealthStatus, AgentCapabilityScore
from .deps import get_current_user

router = APIRouter()


class AgentCreate(BaseModel):
    agent_id: str
    domain: str
    ip: Optional[str] = None
    a2a_endpoint: str
    capabilities: Optional[dict] = None


class AgentUpdate(BaseModel):
    domain: Optional[str] = None
    ip: Optional[str] = None
    a2a_endpoint: Optional[str] = None
    capabilities: Optional[dict] = None
    status: Optional[str] = None


class HealthRecordCreate(BaseModel):
    agent_id: str
    health_status: str
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None


class CapabilityScoreCreate(BaseModel):
    agent_id: int
    capability_name: str
    score: float


@router.get("/")
async def list_agents(
    domain: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(AgentRegistry)
    if domain:
        query = query.where(AgentRegistry.domain == domain)
    if status:
        query = query.where(AgentRegistry.status == status)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    agents = result.scalars().all()
    return {"status": "success", "data": [{"id": a.id, "agent_id": a.agent_id, "domain": a.domain, "ip": a.ip, "a2a_endpoint": a.a2a_endpoint, "capabilities": a.capabilities, "status": a.status, "created_at": a.created_at.isoformat() if a.created_at else None} for a in agents]}


@router.get("/{agent_db_id}")
async def get_agent(
    agent_db_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(AgentRegistry).where(AgentRegistry.id == agent_db_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "success", "data": {"id": agent.id, "agent_id": agent.agent_id, "domain": agent.domain, "ip": agent.ip, "a2a_endpoint": agent.a2a_endpoint, "capabilities": agent.capabilities, "status": agent.status}}


@router.post("/")
async def create_agent(
    req: AgentCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    existing = await db.execute(select(AgentRegistry).where(AgentRegistry.agent_id == req.agent_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Agent ID already exists")
    agent = AgentRegistry(
        agent_id=req.agent_id, domain=req.domain, ip=req.ip,
        a2a_endpoint=req.a2a_endpoint, capabilities=req.capabilities,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return {"status": "success", "data": {"id": agent.id}}


@router.put("/{agent_db_id}")
async def update_agent(
    agent_db_id: int,
    req: AgentUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(AgentRegistry).where(AgentRegistry.id == agent_db_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if req.domain is not None:
        agent.domain = req.domain
    if req.ip is not None:
        agent.ip = req.ip
    if req.a2a_endpoint is not None:
        agent.a2a_endpoint = req.a2a_endpoint
    if req.capabilities is not None:
        agent.capabilities = req.capabilities
    if req.status is not None:
        agent.status = req.status
    await db.commit()
    return {"status": "success", "data": {"id": agent.id}}


@router.delete("/{agent_db_id}")
async def delete_agent(
    agent_db_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(AgentRegistry).where(AgentRegistry.id == agent_db_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()
    return {"status": "success", "message": "Deleted"}


@router.get("/health/records")
async def list_health_records(
    agent_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(AgentHealthRecord)
    if agent_id:
        query = query.where(AgentHealthRecord.agent_id == agent_id)
    query = query.order_by(AgentHealthRecord.checked_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    records = result.scalars().all()
    return {"status": "success", "data": [{"id": r.id, "agent_id": r.agent_id, "health_status": r.health_status.value if r.health_status else None, "cpu_usage": r.cpu_usage, "memory_usage": r.memory_usage, "last_heartbeat": r.last_heartbeat.isoformat() if r.last_heartbeat else None, "checked_at": r.checked_at.isoformat() if r.checked_at else None} for r in records]}


@router.post("/health")
async def create_health_record(
    req: HealthRecordCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    record = AgentHealthRecord(
        agent_id=req.agent_id,
        health_status=AgentHealthStatus(req.health_status),
        cpu_usage=req.cpu_usage,
        memory_usage=req.memory_usage,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"status": "success", "data": {"id": record.id}}


@router.get("/capabilities")
async def list_capability_scores(
    agent_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(AgentCapabilityScore)
    if agent_id:
        query = query.where(AgentCapabilityScore.agent_id == agent_id)
    result = await db.execute(query.limit(50))
    scores = result.scalars().all()
    return {"status": "success", "data": [{"id": s.id, "agent_id": s.agent_id, "capability_name": s.capability_name, "score": s.score, "evaluated_at": s.evaluated_at.isoformat() if s.evaluated_at else None} for s in scores]}


@router.post("/capabilities")
async def create_capability_score(
    req: CapabilityScoreCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    score = AgentCapabilityScore(
        agent_id=req.agent_id, capability_name=req.capability_name, score=req.score,
    )
    db.add(score)
    await db.commit()
    await db.refresh(score)
    return {"status": "success", "data": {"id": score.id}}
