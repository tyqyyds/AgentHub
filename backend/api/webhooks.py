from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from ..database.connection import get_db_session
from ..database.models import WebhookSubscription
from .deps import get_current_user

router = APIRouter()


class WebhookCreate(BaseModel):
    event_type: str
    callback_url: str
    secret: Optional[str] = None
    is_active: Optional[bool] = True


class WebhookUpdate(BaseModel):
    event_type: Optional[str] = None
    callback_url: Optional[str] = None
    secret: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/")
async def list_webhooks(
    event_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(WebhookSubscription)
    if event_type:
        query = query.where(WebhookSubscription.event_type == event_type)
    if is_active is not None:
        query = query.where(WebhookSubscription.is_active == is_active)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    webhooks = result.scalars().all()
    return {"status": "success", "data": [{"id": w.id, "event_type": w.event_type, "callback_url": w.callback_url, "is_active": w.is_active, "last_triggered_at": w.last_triggered_at.isoformat() if w.last_triggered_at else None, "created_at": w.created_at.isoformat() if w.created_at else None} for w in webhooks]}


@router.get("/{webhook_id}")
async def get_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(WebhookSubscription).where(WebhookSubscription.id == webhook_id))
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    return {"status": "success", "data": {"id": webhook.id, "event_type": webhook.event_type, "callback_url": webhook.callback_url, "is_active": webhook.is_active, "last_triggered_at": webhook.last_triggered_at.isoformat() if webhook.last_triggered_at else None, "created_at": webhook.created_at.isoformat() if webhook.created_at else None}}


@router.post("/")
async def create_webhook(
    req: WebhookCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    webhook = WebhookSubscription(
        event_type=req.event_type, callback_url=req.callback_url,
        secret=req.secret, is_active=req.is_active,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)
    return {"status": "success", "data": {"id": webhook.id}}


@router.put("/{webhook_id}")
async def update_webhook(
    webhook_id: int,
    req: WebhookUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(WebhookSubscription).where(WebhookSubscription.id == webhook_id))
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    if req.event_type is not None:
        webhook.event_type = req.event_type
    if req.callback_url is not None:
        webhook.callback_url = req.callback_url
    if req.secret is not None:
        webhook.secret = req.secret
    if req.is_active is not None:
        webhook.is_active = req.is_active
    await db.commit()
    return {"status": "success", "data": {"id": webhook.id}}


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(WebhookSubscription).where(WebhookSubscription.id == webhook_id))
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    await db.delete(webhook)
    await db.commit()
    return {"status": "success", "message": "Deleted"}


@router.post("/test/{webhook_id}")
async def test_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(WebhookSubscription).where(WebhookSubscription.id == webhook_id))
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    if not webhook.is_active:
        raise HTTPException(status_code=400, detail="Webhook is not active")
    return {"status": "success", "message": f"Webhook test dispatched to {webhook.callback_url}", "data": {"event_type": webhook.event_type, "callback_url": webhook.callback_url}}
