from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from backend.core.security.rbac import get_current_user, requires_permission
from backend.agents.intent_template_manager import get_intent_template_manager
from backend.api.response import success_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    intent_type: str = Field(..., min_length=1)
    template_content: str = Field(..., min_length=1)
    parameters_schema: List[Dict[str, Any]] = Field(...)
    example_values: Optional[Dict[str, Any]] = None
    sla_template: Optional[Dict[str, Any]] = None
    priority: str = "medium"
    is_public: bool = True
    tags: List[str] = []


class UpdateTemplateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1)
    category: Optional[str] = Field(None, min_length=1)
    intent_type: Optional[str] = Field(None, min_length=1)
    template_content: Optional[str] = Field(None, min_length=1)
    parameters_schema: Optional[List[Dict[str, Any]]] = None
    example_values: Optional[Dict[str, Any]] = None
    sla_template: Optional[Dict[str, Any]] = None
    priority: Optional[str] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


class InstantiateRequest(BaseModel):
    parameter_values: Dict[str, Any] = Field(default_factory=dict)


class RateRequest(BaseModel):
    rating: float = Field(..., ge=0.0, le=5.0)


class CloneRequest(BaseModel):
    pass


@router.get("")
async def list_templates(
    category: Optional[str] = Query(None),
    intent_type: Optional[str] = Query(None),
    is_public: Optional[bool] = Query(None),
    author: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
):
    manager = get_intent_template_manager()
    templates = await manager.list_templates(
        category=category,
        intent_type=intent_type,
        is_public=is_public,
        author=author,
        search=search,
        limit=limit,
        offset=offset,
    )
    return success_response(data=templates)


@router.get("/categories")
async def get_categories(current_user=Depends(get_current_user)):
    manager = get_intent_template_manager()
    categories = await manager.get_categories()
    return success_response(data=categories)


@router.get("/popular")
async def get_popular_templates(
    limit: int = Query(10, ge=1, le=50),
    current_user=Depends(get_current_user),
):
    manager = get_intent_template_manager()
    templates = await manager.get_popular_templates(limit=limit)
    return success_response(data=templates)


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    current_user=Depends(get_current_user),
):
    manager = get_intent_template_manager()
    template = await manager.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    return success_response(data=template)


@router.post("")
async def create_template(
    req: CreateTemplateRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("playbook:create")),
):
    manager = get_intent_template_manager()
    template = await manager.create_template(
        name=req.name,
        description=req.description,
        category=req.category,
        intent_type=req.intent_type,
        template_content=req.template_content,
        parameters_schema=req.parameters_schema,
        author=current_user.username,
        example_values=req.example_values,
        sla_template=req.sla_template,
        priority=req.priority,
        is_public=req.is_public,
        tags=req.tags,
    )
    from backend.agents.intent_template_manager import _template_to_dict
    return success_response(data=_template_to_dict(template))


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    req: UpdateTemplateRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("playbook:manage")),
):
    manager = get_intent_template_manager()
    existing = await manager.get_template(template_id)
    if not existing:
        raise HTTPException(status_code=404, detail="模板不存在")
    if existing["author"] != current_user.username and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权修改此模板")
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    result = await manager.update_template(template_id, **update_data)
    return success_response(data=result)


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("playbook:manage")),
):
    manager = get_intent_template_manager()
    existing = await manager.get_template(template_id)
    if not existing:
        raise HTTPException(status_code=404, detail="模板不存在")
    if existing["author"] != current_user.username and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权删除此模板")
    success = await manager.delete_template(template_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除模板失败")
    return success_response(data={"template_id": template_id, "deleted": True})


@router.post("/{template_id}/instantiate")
async def instantiate_template(
    template_id: str,
    req: InstantiateRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("intents:execute")),
):
    manager = get_intent_template_manager()
    result = await manager.instantiate_template(template_id, req.parameter_values)
    if result is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return success_response(data=result)


@router.post("/{template_id}/rate")
async def rate_template(
    template_id: str,
    req: RateRequest,
    current_user=Depends(get_current_user),
):
    manager = get_intent_template_manager()
    result = await manager.rate_template(template_id, req.rating)
    if result is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    return success_response(data=result)


@router.post("/{template_id}/clone")
async def clone_template(
    template_id: str,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("playbook:create")),
):
    manager = get_intent_template_manager()
    existing = await manager.get_template(template_id)
    if not existing:
        raise HTTPException(status_code=404, detail="模板不存在")
    if not existing["is_public"] and existing["author"] != current_user.username and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权克隆此私有模板")
    cloned = await manager.clone_template(template_id, current_user.username)
    if cloned is None:
        raise HTTPException(status_code=500, detail="克隆模板失败")
    from backend.agents.intent_template_manager import _template_to_dict
    return success_response(data=_template_to_dict(cloned))
