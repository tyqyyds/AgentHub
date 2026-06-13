from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import LLMRouterConfig, LLMProvider
from .deps import get_current_user

router = APIRouter()


class LLMRouterCreate(BaseModel):
    task_type: str
    primary_provider: str
    fallback_provider: Optional[str] = None
    primary_model: str
    fallback_model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048


class LLMRouterUpdate(BaseModel):
    task_type: Optional[str] = None
    primary_provider: Optional[str] = None
    fallback_provider: Optional[str] = None
    primary_model: Optional[str] = None
    fallback_model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("/")
async def list_llm_configs(
    task_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(LLMRouterConfig)
    if task_type:
        query = query.where(LLMRouterConfig.task_type == task_type)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    configs = result.scalars().all()
    return {"status": "success", "data": [{"id": c.id, "task_type": c.task_type, "primary_provider": c.primary_provider.value if c.primary_provider else None, "fallback_provider": c.fallback_provider.value if c.fallback_provider else None, "primary_model": c.primary_model, "fallback_model": c.fallback_model, "temperature": c.temperature, "max_tokens": c.max_tokens, "is_active": c.is_active} for c in configs]}


@router.get("/{config_id}")
async def get_llm_config(
    config_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(LLMRouterConfig).where(LLMRouterConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="LLM router config not found")
    return {"status": "success", "data": {"id": config.id, "task_type": config.task_type, "primary_provider": config.primary_provider.value if config.primary_provider else None, "fallback_provider": config.fallback_provider.value if config.fallback_provider else None, "primary_model": config.primary_model, "fallback_model": config.fallback_model, "temperature": config.temperature, "max_tokens": config.max_tokens, "is_active": config.is_active}}


@router.post("/")
async def create_llm_config(
    req: LLMRouterCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    config = LLMRouterConfig(
        task_type=req.task_type,
        primary_provider=LLMProvider(req.primary_provider),
        fallback_provider=LLMProvider(req.fallback_provider) if req.fallback_provider else None,
        primary_model=req.primary_model,
        fallback_model=req.fallback_model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return {"status": "success", "data": {"id": config.id}}


@router.put("/{config_id}")
async def update_llm_config(
    config_id: int,
    req: LLMRouterUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(LLMRouterConfig).where(LLMRouterConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="LLM router config not found")
    if req.task_type is not None:
        config.task_type = req.task_type
    if req.primary_provider is not None:
        config.primary_provider = LLMProvider(req.primary_provider)
    if req.fallback_provider is not None:
        config.fallback_provider = LLMProvider(req.fallback_provider)
    if req.primary_model is not None:
        config.primary_model = req.primary_model
    if req.fallback_model is not None:
        config.fallback_model = req.fallback_model
    if req.temperature is not None:
        config.temperature = req.temperature
    if req.max_tokens is not None:
        config.max_tokens = req.max_tokens
    if req.is_active is not None:
        config.is_active = req.is_active
    await db.commit()
    return {"status": "success", "data": {"id": config.id}}


@router.delete("/{config_id}")
async def delete_llm_config(
    config_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(LLMRouterConfig).where(LLMRouterConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="LLM router config not found")
    await db.delete(config)
    await db.commit()
    return {"status": "success", "message": "Deleted"}


@router.post("/route")
async def route_llm_request(
    task_type: str = Query(..., description="Task type to route"),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(LLMRouterConfig).where(LLMRouterConfig.task_type == task_type, LLMRouterConfig.is_active == True)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail=f"No active LLM router config for task type: {task_type}")
    return {"status": "success", "data": {"primary_provider": config.primary_provider.value, "primary_model": config.primary_model, "fallback_provider": config.fallback_provider.value if config.fallback_provider else None, "fallback_model": config.fallback_model, "temperature": config.temperature, "max_tokens": config.max_tokens}}
