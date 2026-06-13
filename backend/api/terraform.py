from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from .deps import get_current_user

router = APIRouter()

# 生产环境应使用数据库持久化，此处使用内存存储作为演示
_terraform_stacks: dict[str, dict] = {}
_terraform_plans: dict[str, dict] = {}


class TerraformStackCreate(BaseModel):
    name: str
    description: Optional[str] = None
    content: str  # HCL内容
    variables: Optional[dict] = None


class TerraformStackUpdate(BaseModel):
    description: Optional[str] = None
    content: Optional[str] = None
    variables: Optional[dict] = None


class TerraformPlanRequest(BaseModel):
    stack_name: str
    action: str  # plan | apply | destroy


# ──────────────── Stack CRUD ────────────────


@router.get("/stacks")
async def list_stacks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    stacks = list(_terraform_stacks.values())[skip:skip + limit]
    return {"status": "success", "data": stacks}


@router.get("/stacks/{stack_name}")
async def get_stack(
    stack_name: str,
    current_user=Depends(get_current_user),
):
    if stack_name not in _terraform_stacks:
        raise HTTPException(status_code=404, detail="Stack not found")
    return {"status": "success", "data": _terraform_stacks[stack_name]}


@router.post("/stacks")
async def create_stack(
    req: TerraformStackCreate,
    current_user=Depends(get_current_user),
):
    if req.name in _terraform_stacks:
        raise HTTPException(status_code=400, detail="Stack already exists")
    stack = {
        "name": req.name, "description": req.description,
        "content": req.content, "variables": req.variables or {},
        "created_at": datetime.now().isoformat(), "updated_at": None, "status": "draft",
    }
    _terraform_stacks[req.name] = stack
    return {"status": "success", "data": {"name": req.name}}


@router.put("/stacks/{stack_name}")
async def update_stack(
    stack_name: str,
    req: TerraformStackUpdate,
    current_user=Depends(get_current_user),
):
    if stack_name not in _terraform_stacks:
        raise HTTPException(status_code=404, detail="Stack not found")
    stack = _terraform_stacks[stack_name]
    if req.description is not None:
        stack["description"] = req.description
    if req.content is not None:
        stack["content"] = req.content
    if req.variables is not None:
        stack["variables"] = req.variables
    stack["updated_at"] = datetime.now().isoformat()
    return {"status": "success", "data": {"name": stack_name}}


@router.delete("/stacks/{stack_name}")
async def delete_stack(
    stack_name: str,
    current_user=Depends(get_current_user),
):
    if stack_name not in _terraform_stacks:
        raise HTTPException(status_code=404, detail="Stack not found")
    del _terraform_stacks[stack_name]
    return {"status": "success", "message": "Deleted"}


# ──────────────── Plan / Apply / Destroy ────────────────


@router.post("/plan")
async def terraform_plan(
    req: TerraformPlanRequest,
    current_user=Depends(get_current_user),
):
    if req.stack_name not in _terraform_stacks:
        raise HTTPException(status_code=404, detail="Stack not found")
    plan_id = f"plan-{req.stack_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    plan = {
        "plan_id": plan_id, "stack_name": req.stack_name,
        "action": req.action, "status": "completed",
        "created_at": datetime.now().isoformat(),
        "changes": {"add": 2, "change": 1, "destroy": 0},
    }
    _terraform_plans[plan_id] = plan
    return {"status": "success", "data": plan}


@router.post("/apply")
async def terraform_apply(
    req: TerraformPlanRequest,
    current_user=Depends(get_current_user),
):
    if req.stack_name not in _terraform_stacks:
        raise HTTPException(status_code=404, detail="Stack not found")
    _terraform_stacks[req.stack_name]["status"] = "applied"
    _terraform_stacks[req.stack_name]["updated_at"] = datetime.now().isoformat()
    return {"status": "success", "data": {
        "stack_name": req.stack_name, "action": "apply",
        "status": "applied", "applied_at": datetime.now().isoformat(),
    }}


@router.post("/destroy")
async def terraform_destroy(
    req: TerraformPlanRequest,
    current_user=Depends(get_current_user),
):
    if req.stack_name not in _terraform_stacks:
        raise HTTPException(status_code=404, detail="Stack not found")
    _terraform_stacks[req.stack_name]["status"] = "destroyed"
    _terraform_stacks[req.stack_name]["updated_at"] = datetime.now().isoformat()
    return {"status": "success", "data": {
        "stack_name": req.stack_name, "action": "destroy",
        "status": "destroyed", "destroyed_at": datetime.now().isoformat(),
    }}


# ──────────────── Plan 历史 ────────────────


@router.get("/plans")
async def list_plans(
    stack_name: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    plans = list(_terraform_plans.values())
    if stack_name:
        plans = [p for p in plans if p["stack_name"] == stack_name]
    return {"status": "success", "data": plans[skip:skip + limit]}


@router.get("/plans/{plan_id}")
async def get_plan(
    plan_id: str,
    current_user=Depends(get_current_user),
):
    if plan_id not in _terraform_plans:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"status": "success", "data": _terraform_plans[plan_id]}
