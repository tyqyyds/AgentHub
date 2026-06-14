import hashlib
import hmac
import json
import logging
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

try:
    import httpx
    _httpx_available = True
except ImportError:
    _httpx_available = False
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import async_session_maker
from backend.database.models import WebhookSubscription
from backend.core.config import settings

logger = logging.getLogger(__name__)

MAX_DELIVERY_LOG_PER_SUBSCRIPTION = 1000


class WebhookManager:
    def __init__(self):
        self._delivery_logs: dict[str, list[dict]] = {}
        self._start_time = datetime.now(timezone.utc)

    async def create_subscription(
        self,
        name: str,
        url: str,
        event_types: list[str],
        created_by: str,
        secret: Optional[str] = None,
        headers: Optional[dict] = None,
        retry_policy: Optional[dict] = None,
    ) -> WebhookSubscription:
        subscription_id = f"wh_{uuid.uuid4().hex[:8]}"
        async with async_session_maker() as session:
            sub = WebhookSubscription(
                subscription_id=subscription_id,
                name=name,
                url=url,
                secret=secret,
                event_types=event_types,
                headers=headers or {},
                is_active=True,
                retry_policy=retry_policy or {"max_retries": settings.webhook_max_retries, "backoff_seconds": [5, 30, 120]},
                created_by=created_by,
            )
            session.add(sub)
            await session.commit()
            await session.refresh(sub)
            return sub

    async def update_subscription(self, subscription_id: str, **kwargs) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WebhookSubscription).where(WebhookSubscription.subscription_id == subscription_id)
            )
            sub = result.scalars().first()
            if not sub:
                raise ValueError(f"Subscription not found: {subscription_id}")

            allowed_fields = {"name", "url", "secret", "event_types", "headers", "is_active", "retry_policy"}
            for key, value in kwargs.items():
                if key in allowed_fields and value is not None:
                    setattr(sub, key, value)

            sub.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(sub)
            return self._serialize(sub)

    async def delete_subscription(self, subscription_id: str) -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WebhookSubscription).where(WebhookSubscription.subscription_id == subscription_id)
            )
            sub = result.scalars().first()
            if not sub:
                return False
            await session.delete(sub)
            await session.commit()
            self._delivery_logs.pop(subscription_id, None)
            return True

    async def list_subscriptions(
        self, is_active: Optional[bool] = None, event_type: Optional[str] = None
    ) -> list[dict]:
        async with async_session_maker() as session:
            query = select(WebhookSubscription)
            if is_active is not None:
                query = query.where(WebhookSubscription.is_active == is_active)
            result = await session.execute(query)
            subs = result.scalars().all()

            items = [self._serialize(s) for s in subs]
            if event_type:
                items = [i for i in items if event_type in i.get("event_types", [])]
            return items

    async def get_subscription(self, subscription_id: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WebhookSubscription).where(WebhookSubscription.subscription_id == subscription_id)
            )
            sub = result.scalars().first()
            if not sub:
                raise ValueError(f"Subscription not found: {subscription_id}")
            return self._serialize(sub)

    async def toggle_subscription(self, subscription_id: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WebhookSubscription).where(WebhookSubscription.subscription_id == subscription_id)
            )
            sub = result.scalars().first()
            if not sub:
                raise ValueError(f"Subscription not found: {subscription_id}")
            sub.is_active = not sub.is_active
            sub.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(sub)
            return self._serialize(sub)

    async def emit_event(self, event_type: str, payload: dict) -> None:
        if not settings.webhook_enabled:
            return

        async with async_session_maker() as session:
            result = await session.execute(
                select(WebhookSubscription).where(WebhookSubscription.is_active == True)
            )
            subs = result.scalars().all()

        matching = [s for s in subs if event_type in (s.event_types or [])]
        for sub in matching:
            try:
                delivery = await self._deliver_webhook(sub, event_type, payload)
                self._log_delivery(sub.subscription_id, delivery)

                async with async_session_maker() as session:
                    await session.execute(
                        update(WebhookSubscription)
                        .where(WebhookSubscription.subscription_id == sub.subscription_id)
                        .values(
                            last_triggered_at=datetime.now(timezone.utc),
                            last_status=delivery["status"],
                            failure_count=sub.failure_count + (1 if delivery["status"] == "failed" else 0),
                        )
                    )
                    await session.commit()

                if delivery["status"] == "failed":
                    await self._retry_delivery(sub, event_type, payload, attempt=1)
            except Exception as e:
                logger.error(f"Error emitting event {event_type} to {sub.subscription_id}: {e}")

    async def _deliver_webhook(self, subscription: WebhookSubscription, event_type: str, payload: dict) -> dict:
        body = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subscription_id": subscription.subscription_id,
            "data": payload,
        }
        body_json = json.dumps(body, ensure_ascii=False)

        headers = dict(subscription.headers or {})
        headers["Content-Type"] = "application/json"
        headers["X-Webhook-Event"] = event_type
        headers["X-Webhook-ID"] = subscription.subscription_id

        if subscription.secret:
            signature = hmac.new(
                subscription.secret.encode("utf-8"),
                body_json.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        delivery = {
            "subscription_id": subscription.subscription_id,
            "event_type": event_type,
            "url": subscription.url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "status_code": None,
            "error": None,
            "attempt": 1,
        }

        if not _httpx_available:
            delivery["status"] = "failed"
            delivery["error"] = "httpx not installed"
            logger.warning("httpx not installed, webhook delivery skipped")
            return delivery

        try:
            async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
                response = await client.post(subscription.url, content=body_json, headers=headers)
                delivery["status_code"] = response.status_code
                if response.status_code >= 400:
                    delivery["status"] = "failed"
                    delivery["error"] = f"HTTP {response.status_code}"
        except httpx.TimeoutException:
            delivery["status"] = "failed"
            delivery["error"] = "timeout"
        except Exception as e:
            delivery["status"] = "failed"
            delivery["error"] = str(e)

        return delivery

    async def _retry_delivery(self, subscription: WebhookSubscription, event_type: str, payload: dict, attempt: int) -> None:
        retry_policy = subscription.retry_policy or {"max_retries": settings.webhook_max_retries, "backoff_seconds": [5, 30, 120]}
        max_retries = retry_policy.get("max_retries", settings.webhook_max_retries)
        backoff_seconds = retry_policy.get("backoff_seconds", [5, 30, 120])

        if attempt > max_retries:
            return

        backoff = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
        await asyncio.sleep(backoff)

        delivery = await self._deliver_webhook(subscription, event_type, payload)
        delivery["attempt"] = attempt + 1
        self._log_delivery(subscription.subscription_id, delivery)

        if delivery["status"] == "failed" and attempt < max_retries:
            await self._retry_delivery(subscription, event_type, payload, attempt + 1)

    def get_delivery_log(self, subscription_id: str, limit: int = 50) -> list[dict]:
        logs = self._delivery_logs.get(subscription_id, [])
        return logs[-limit:]

    def _log_delivery(self, subscription_id: str, delivery: dict) -> None:
        if subscription_id not in self._delivery_logs:
            self._delivery_logs[subscription_id] = []
        self._delivery_logs[subscription_id].append(delivery)
        if len(self._delivery_logs[subscription_id]) > MAX_DELIVERY_LOG_PER_SUBSCRIPTION:
            self._delivery_logs[subscription_id] = self._delivery_logs[subscription_id][-MAX_DELIVERY_LOG_PER_SUBSCRIPTION:]

    @staticmethod
    def _serialize(sub: WebhookSubscription) -> dict:
        return {
            "id": sub.id,
            "subscription_id": sub.subscription_id,
            "name": sub.name,
            "url": sub.url,
            "secret": "***" if sub.secret else None,
            "event_types": sub.event_types,
            "headers": sub.headers,
            "is_active": sub.is_active,
            "retry_policy": sub.retry_policy,
            "last_triggered_at": sub.last_triggered_at.isoformat() if sub.last_triggered_at else None,
            "last_status": sub.last_status,
            "failure_count": sub.failure_count,
            "created_by": sub.created_by,
            "created_at": sub.created_at.isoformat() if sub.created_at else None,
            "updated_at": sub.updated_at.isoformat() if sub.updated_at else None,
        }


_webhook_manager: Optional[WebhookManager] = None


def get_webhook_manager() -> WebhookManager:
    global _webhook_manager
    if _webhook_manager is None:
        _webhook_manager = WebhookManager()
    return _webhook_manager
