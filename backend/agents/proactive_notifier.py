from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import async_session_maker
from backend.database.models import ProactiveNotification
import uuid
import logging

logger = logging.getLogger(__name__)


def _generate_notification_id() -> str:
    return f"pn_{uuid.uuid4().hex[:4]}"


def _notification_to_dict(n: ProactiveNotification) -> dict:
    return {
        "id": n.id,
        "notification_id": n.notification_id,
        "notification_type": n.notification_type,
        "severity": n.severity,
        "title": n.title,
        "message": n.message,
        "suggested_action": n.suggested_action,
        "target_users": n.target_users or [],
        "source_data": n.source_data,
        "is_read": n.is_read,
        "read_by": n.read_by or [],
        "dismissed_by": n.dismissed_by or [],
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


class ProactiveNotifier:
    def __init__(self):
        self._ws_manager = None

    def set_ws_manager(self, manager):
        self._ws_manager = manager

    async def _create_notification(
        self,
        notification_type: str,
        severity: str,
        title: str,
        message: str,
        suggested_action: Optional[str] = None,
        target_users: Optional[list] = None,
        source_data: Optional[dict] = None,
    ) -> ProactiveNotification:
        notification_id = _generate_notification_id()
        async with async_session_maker() as session:
            notification = ProactiveNotification(
                notification_id=notification_id,
                notification_type=notification_type,
                severity=severity,
                title=title,
                message=message,
                suggested_action=suggested_action,
                target_users=target_users or [],
                source_data=source_data,
            )
            session.add(notification)
            await session.commit()
            await session.refresh(notification)
            logger.info(f"Created notification {notification_id}: {title}")
            return notification

    async def notify_sla_warning(
        self,
        intent_id: int,
        violation_probability: float,
        predicted_time: Optional[str] = None,
    ) -> ProactiveNotification:
        severity = "critical" if violation_probability >= 0.8 else "warning"
        title = f"SLA违规预警 - 意图#{intent_id}"
        message = (
            f"意图 #{intent_id} 存在SLA违规风险。\n"
            f"违规概率：{violation_probability:.1%}\n"
        )
        if predicted_time:
            message += f"预计违规时间：{predicted_time}\n"
        suggested_action = "建议立即检查意图执行状态并采取纠正措施"
        source_data = {
            "intent_id": intent_id,
            "violation_probability": violation_probability,
            "predicted_time": predicted_time,
        }
        notification = await self._create_notification(
            notification_type="sla_warning",
            severity=severity,
            title=title,
            message=message,
            suggested_action=suggested_action,
            source_data=source_data,
        )
        await self.send_notification(notification)
        return notification

    async def notify_device_anomaly(
        self,
        device_id: str,
        anomaly_type: str,
        details: Optional[dict] = None,
    ) -> ProactiveNotification:
        severity = "critical" if anomaly_type in ("link_down", "cpu_overload", "memory_leak") else "warning"
        title = f"设备异常 - {device_id}"
        message = (
            f"设备 {device_id} 检测到异常。\n"
            f"异常类型：{anomaly_type}\n"
        )
        if details:
            for k, v in details.items():
                message += f"{k}：{v}\n"
        suggested_action = "建议检查设备状态并启动自愈流程"
        source_data = {
            "device_id": device_id,
            "anomaly_type": anomaly_type,
            "details": details,
        }
        notification = await self._create_notification(
            notification_type="device_anomaly",
            severity=severity,
            title=title,
            message=message,
            suggested_action=suggested_action,
            source_data=source_data,
        )
        await self.send_notification(notification)
        return notification

    async def notify_healing_completed(
        self,
        event_id: int,
        result: Optional[dict] = None,
    ) -> ProactiveNotification:
        status = "成功" if result and result.get("success") else "失败"
        severity = "info" if status == "成功" else "warning"
        title = f"自愈完成 - 事件#{event_id}"
        message = f"事件 #{event_id} 自愈流程已{status}。\n"
        if result:
            for k, v in result.items():
                message += f"{k}：{v}\n"
        suggested_action = "建议验证修复效果" if status == "成功" else "建议手动介入处理"
        source_data = {
            "event_id": event_id,
            "result": result,
        }
        notification = await self._create_notification(
            notification_type="healing_completed",
            severity=severity,
            title=title,
            message=message,
            suggested_action=suggested_action,
            source_data=source_data,
        )
        await self.send_notification(notification)
        return notification

    async def notify_intent_status_change(
        self,
        intent_id: int,
        old_status: str,
        new_status: str,
    ) -> ProactiveNotification:
        severity = "info"
        if new_status in ("failed", "conflict"):
            severity = "critical"
        elif new_status in ("executing", "approved"):
            severity = "info"
        title = f"意图状态变更 - 意图#{intent_id}"
        message = (
            f"意图 #{intent_id} 状态已变更。\n"
            f"原状态：{old_status}\n"
            f"新状态：{new_status}\n"
        )
        suggested_action = None
        if new_status == "failed":
            suggested_action = "建议检查失败原因并重新提交"
        elif new_status == "conflict":
            suggested_action = "建议查看冲突详情并调整意图参数"
        source_data = {
            "intent_id": intent_id,
            "old_status": old_status,
            "new_status": new_status,
        }
        notification = await self._create_notification(
            notification_type="intent_status_change",
            severity=severity,
            title=title,
            message=message,
            suggested_action=suggested_action,
            source_data=source_data,
        )
        await self.send_notification(notification)
        return notification

    async def send_notification(self, notification: ProactiveNotification) -> None:
        if not self._ws_manager:
            try:
                from backend.api.websocket import manager as ws_manager
                self._ws_manager = ws_manager
            except (ImportError, Exception):
                logger.debug("WebSocket manager not available, notification stored in DB only")
                return
        payload = _notification_to_dict(notification)
        target_users = notification.target_users or []
        ws_message = {
            "type": "proactive_notification",
            "data": payload,
        }
        if target_users:
            for username in target_users:
                try:
                    await self._ws_manager.send_to_user(username, ws_message)
                except Exception as e:
                    logger.warning(f"Failed to send notification to {username}: {e}")
        else:
            try:
                await self._ws_manager.broadcast(ws_message)
            except Exception as e:
                logger.warning(f"Failed to broadcast notification: {e}")

    async def get_unread_notifications(self, username: str) -> List[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(ProactiveNotification)
                .where(
                    and_(
                        ProactiveNotification.is_read == False,
                    )
                )
                .order_by(ProactiveNotification.created_at.desc())
            )
            notifications = result.scalars().all()
            unread = []
            for n in notifications:
                if username not in (n.dismissed_by or []):
                    target_users = n.target_users or []
                    if not target_users or username in target_users:
                        unread.append(_notification_to_dict(n))
            return unread

    async def mark_as_read(self, notification_id: str, username: str) -> None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(ProactiveNotification).where(
                    ProactiveNotification.notification_id == notification_id
                )
            )
            notification = result.scalar_one_or_none()
            if not notification:
                return
            read_by = notification.read_by or []
            if username not in read_by:
                read_by.append(username)
                notification.read_by = read_by
            target_users = notification.target_users or []
            if not target_users:
                all_read = True
            else:
                all_read = all(u in read_by for u in target_users)
            if all_read:
                notification.is_read = True
            await session.commit()

    async def mark_all_as_read(self, username: str) -> int:
        async with async_session_maker() as session:
            result = await session.execute(
                select(ProactiveNotification).where(
                    and_(
                        ProactiveNotification.is_read == False,
                    )
                )
            )
            notifications = result.scalars().all()
            count = 0
            for n in notifications:
                if username in (n.dismissed_by or []):
                    continue
                target_users = n.target_users or []
                if target_users and username not in target_users:
                    continue
                read_by = n.read_by or []
                if username not in read_by:
                    read_by.append(username)
                    n.read_by = read_by
                if not target_users:
                    n.is_read = True
                elif all(u in read_by for u in target_users):
                    n.is_read = True
                count += 1
            await session.commit()
            return count

    async def dismiss_notification(self, notification_id: str, username: str) -> None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(ProactiveNotification).where(
                    ProactiveNotification.notification_id == notification_id
                )
            )
            notification = result.scalar_one_or_none()
            if not notification:
                return
            dismissed_by = notification.dismissed_by or []
            if username not in dismissed_by:
                dismissed_by.append(username)
                notification.dismissed_by = dismissed_by
            await session.commit()

    async def list_notifications(
        self,
        username: Optional[str] = None,
        notification_type: Optional[str] = None,
        is_read: Optional[bool] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with async_session_maker() as session:
            query = select(ProactiveNotification)
            conditions = []
            if notification_type is not None:
                conditions.append(ProactiveNotification.notification_type == notification_type)
            if is_read is not None:
                conditions.append(ProactiveNotification.is_read == is_read)
            if conditions:
                query = query.where(*conditions)
            query = query.order_by(ProactiveNotification.created_at.desc()).limit(limit)
            result = await session.execute(query)
            notifications = result.scalars().all()
            items = []
            for n in notifications:
                if username:
                    if username in (n.dismissed_by or []):
                        continue
                    target_users = n.target_users or []
                    if target_users and username not in target_users:
                        continue
                items.append(_notification_to_dict(n))
            return items


_proactive_notifier: Optional[ProactiveNotifier] = None


def get_proactive_notifier() -> ProactiveNotifier:
    global _proactive_notifier
    if _proactive_notifier is None:
        _proactive_notifier = ProactiveNotifier()
    return _proactive_notifier
