from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from backend.core.security.rbac import get_current_user, requires_permission
from backend.integrations.webhook_manager import get_webhook_manager
from backend.api.response import success_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

AVAILABLE_EVENT_TYPES = [
    "intent.created",
    "intent.completed",
    "intent.failed",
    "sla.achieving",
    "sla.deviating",
    "sla.violated",
    "sla.violation_predicted",
    "healing.started",
    "healing.completed",
    "healing.failed",
    "device.alert",
    "device.status_changed",
    "agent.health_changed",
    "workflow.step_completed",
    "workflow.completed",
]


class CreateSubscriptionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=1, max_length=2048)
    event_types: List[str] = Field(..., min_length=1)
    secret: Optional[str] = Field(None, max_length=256)
    headers: Optional[Dict[str, str]] = None
    retry_policy: Optional[Dict[str, Any]] = None


class UpdateSubscriptionRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    url: Optional[str] = Field(None, min_length=1, max_length=2048)
    event_types: Optional[List[str]] = None
    secret: Optional[str] = Field(None, max_length=256)
    headers: Optional[Dict[str, str]] = None
    retry_policy: Optional[Dict[str, Any]] = None


class TestWebhookRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    event_type: str = Field(..., min_length=1)
    secret: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    payload: Dict[str, Any] = Field(default={})


@router.get("/subscriptions")
async def list_subscriptions(
    is_active: Optional[bool] = None,
    event_type: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    try:
        manager = get_webhook_manager()
        subscriptions = await manager.list_subscriptions(is_active=is_active, event_type=event_type)
        return success_response(data={"items": subscriptions, "total": len(subscriptions)})
    except Exception as e:
        logger.error(f"List subscriptions failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/subscriptions")
async def create_subscription(
    req: CreateSubscriptionRequest,
    current_user=Depends(requires_permission("webhook:manage")),
):
    try:
        invalid = [et for et in req.event_types if et not in AVAILABLE_EVENT_TYPES]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid event types: {invalid}")

        manager = get_webhook_manager()
        sub = await manager.create_subscription(
            name=req.name,
            url=req.url,
            event_types=req.event_types,
            created_by=current_user.username,
            secret=req.secret,
            headers=req.headers,
            retry_policy=req.retry_policy,
        )
        return success_response(data=get_webhook_manager()._serialize(sub))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create subscription failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/subscriptions/{subscription_id}")
async def get_subscription(
    subscription_id: str,
    current_user=Depends(get_current_user),
):
    try:
        manager = get_webhook_manager()
        sub = await manager.get_subscription(subscription_id)
        return success_response(data=sub)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Subscription not found: {subscription_id}")
    except Exception as e:
        logger.error(f"Get subscription failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/subscriptions/{subscription_id}")
async def update_subscription(
    subscription_id: str,
    req: UpdateSubscriptionRequest,
    current_user=Depends(requires_permission("webhook:manage")),
):
    try:
        manager = get_webhook_manager()
        update_data = {}
        if req.name is not None:
            update_data["name"] = req.name
        if req.url is not None:
            update_data["url"] = req.url
        if req.event_types is not None:
            invalid = [et for et in req.event_types if et not in AVAILABLE_EVENT_TYPES]
            if invalid:
                raise HTTPException(status_code=400, detail=f"Invalid event types: {invalid}")
            update_data["event_types"] = req.event_types
        if req.secret is not None:
            update_data["secret"] = req.secret
        if req.headers is not None:
            update_data["headers"] = req.headers
        if req.retry_policy is not None:
            update_data["retry_policy"] = req.retry_policy

        result = await manager.update_subscription(subscription_id, **update_data)
        return success_response(data=result)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Subscription not found: {subscription_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update subscription failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: str,
    current_user=Depends(requires_permission("webhook:manage")),
):
    try:
        manager = get_webhook_manager()
        success = await manager.delete_subscription(subscription_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Subscription not found: {subscription_id}")
        return success_response(data={"subscription_id": subscription_id, "deleted": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete subscription failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/subscriptions/{subscription_id}/toggle")
async def toggle_subscription(
    subscription_id: str,
    current_user=Depends(requires_permission("webhook:manage")),
):
    try:
        manager = get_webhook_manager()
        result = await manager.toggle_subscription(subscription_id)
        return success_response(data=result)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Subscription not found: {subscription_id}")
    except Exception as e:
        logger.error(f"Toggle subscription failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/test")
async def test_webhook(
    req: TestWebhookRequest,
    current_user=Depends(requires_permission("webhook:manage")),
):
    try:
        from backend.database.models import WebhookSubscription
        from datetime import datetime, timezone

        mock_sub = WebhookSubscription(
            subscription_id="wh_test",
            name="test",
            url=req.url,
            secret=req.secret,
            event_types=[req.event_type],
            headers=req.headers or {},
            is_active=True,
            retry_policy={"max_retries": 0, "backoff_seconds": []},
            created_by=current_user.username,
        )

        manager = get_webhook_manager()
        delivery = await manager._deliver_webhook(mock_sub, req.event_type, req.payload)
        return success_response(data=delivery)
    except Exception as e:
        logger.error(f"Test webhook failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/subscriptions/{subscription_id}/logs")
async def get_delivery_logs(
    subscription_id: str,
    limit: int = 50,
    current_user=Depends(get_current_user),
):
    try:
        manager = get_webhook_manager()
        logs = manager.get_delivery_log(subscription_id, limit=limit)
        return success_response(data={"items": logs, "total": len(logs)})
    except Exception as e:
        logger.error(f"Get delivery logs failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/events")
async def list_event_types(current_user=Depends(get_current_user)):
    return success_response(data=AVAILABLE_EVENT_TYPES)
