from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import IntentTemplate, IntentTemplateType
from .deps import get_current_user

router = APIRouter()


class TemplateCreate(BaseModel):
    template_id: str
    intent_type: str
    description: Optional[str] = None
    param_schema: Optional[dict] = None
    example_utterances: Optional[list] = None


class TemplateUpdate(BaseModel):
    intent_type: Optional[str] = None
    description: Optional[str] = None
    param_schema: Optional[dict] = None
    example_utterances: Optional[list] = None


@router.get("/")
async def list_templates(
    intent_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(IntentTemplate)
    if intent_type:
        query = query.where(IntentTemplate.intent_type == intent_type)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    templates = result.scalars().all()
    return {"status": "success", "data": [{"id": t.id, "template_id": t.template_id, "intent_type": t.intent_type.value if t.intent_type else None, "description": t.description, "param_schema": t.param_schema, "example_utterances": t.example_utterances, "created_at": t.created_at.isoformat() if t.created_at else None} for t in templates]}


@router.get("/{template_id}")
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(IntentTemplate).where(IntentTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Intent template not found")
    return {"status": "success", "data": {"id": template.id, "template_id": template.template_id, "intent_type": template.intent_type.value if template.intent_type else None, "description": template.description, "param_schema": template.param_schema, "example_utterances": template.example_utterances, "created_at": template.created_at.isoformat() if template.created_at else None}}


@router.post("/")
async def create_template(
    req: TemplateCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    existing = await db.execute(select(IntentTemplate).where(IntentTemplate.template_id == req.template_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Template ID already exists")
    template = IntentTemplate(
        template_id=req.template_id,
        intent_type=IntentTemplateType(req.intent_type),
        description=req.description,
        param_schema=req.param_schema,
        example_utterances=req.example_utterances,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return {"status": "success", "data": {"id": template.id}}


@router.put("/{template_id}")
async def update_template(
    template_id: int,
    req: TemplateUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(IntentTemplate).where(IntentTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Intent template not found")
    if req.intent_type is not None:
        template.intent_type = IntentTemplateType(req.intent_type)
    if req.description is not None:
        template.description = req.description
    if req.param_schema is not None:
        template.param_schema = req.param_schema
    if req.example_utterances is not None:
        template.example_utterances = req.example_utterances
    await db.commit()
    return {"status": "success", "data": {"id": template.id}}


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(IntentTemplate).where(IntentTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Intent template not found")
    await db.delete(template)
    await db.commit()
    return {"status": "success", "message": "Deleted"}


@router.post("/render")
async def render_template(
    template_id: str = Query(..., description="Template string ID to render"),
    params: Optional[dict] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(IntentTemplate).where(IntentTemplate.template_id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "success", "data": {"template_id": template.template_id, "intent_type": template.intent_type.value if template.intent_type else None, "param_schema": template.param_schema, "provided_params": params or {}}}
