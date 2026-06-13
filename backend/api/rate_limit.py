from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
from ..database.connection import get_db_session
from .deps import get_current_user

router = APIRouter()

# 内存中的限流规则（生产环境应使用Redis）
_rate_limit_rules: dict = {}


class RateLimitRule(BaseModel):
    rule_name: str
    target: str
    requests_per_minute: int = 60
    burst_size: int = 10
    is_active: bool = True


@router.get("/")
async def list_rate_limits(
    current_user=Depends(get_current_user),
):
    return {"status": "success", "data": list(_rate_limit_rules.values())}


@router.get("/{rule_name}")
async def get_rate_limit(
    rule_name: str,
    current_user=Depends(get_current_user),
):
    if rule_name not in _rate_limit_rules:
        raise HTTPException(status_code=404, detail="Rate limit rule not found")
    return {"status": "success", "data": _rate_limit_rules[rule_name]}


@router.post("/")
async def create_rate_limit(
    rule: RateLimitRule,
    current_user=Depends(get_current_user),
):
    _rate_limit_rules[rule.rule_name] = rule.model_dump()
    return {"status": "success", "data": rule.model_dump()}


@router.put("/{rule_name}")
async def update_rate_limit(
    rule_name: str,
    rule: RateLimitRule,
    current_user=Depends(get_current_user),
):
    if rule_name not in _rate_limit_rules:
        raise HTTPException(status_code=404, detail="Rate limit rule not found")
    _rate_limit_rules[rule_name] = rule.model_dump()
    return {"status": "success"}


@router.delete("/{rule_name}")
async def delete_rate_limit(
    rule_name: str,
    current_user=Depends(get_current_user),
):
    if rule_name not in _rate_limit_rules:
        raise HTTPException(status_code=404, detail="Rate limit rule not found")
    del _rate_limit_rules[rule_name]
    return {"status": "success"}


@router.get("/status/{target}")
async def get_rate_limit_status(
    target: str,
    current_user=Depends(get_current_user),
):
    return {"status": "success", "data": {"target": target, "current_usage": 0, "limit": 60, "remaining": 60}}
