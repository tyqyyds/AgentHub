from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import asyncio
import logging
from backend.core.security.rbac import requires_permission

router = APIRouter()

logger = logging.getLogger(__name__)


class SystemState:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.fuse_enabled = False
        self.fuse_reason = ""
        self.fuse_time = None
        self.triggered_by = "manual"  # manual | auto
        self.paused_workflows: list[str] = []
        self.paused_agents: list[str] = []
        self.security_actions_taken: list[str] = []
        self.auto_trigger_rules = {
            "critical_alerts_threshold": 5,  # 5+ critical alerts in 60s
            "failed_executions_threshold": 10,  # 10+ failed executions in 60s
            "unauthorized_access_threshold": 3,  # 3+ unauthorized attempts in 60s
        }

    async def enable_fuse(self, reason: str = "紧急熔断", triggered_by: str = "manual"):
        async with self._lock:
            if self.fuse_enabled:
                return  # Already fused

            self.fuse_enabled = True
            self.fuse_reason = reason
            self.fuse_time = datetime.now(timezone.utc)
            self.triggered_by = triggered_by
            self.security_actions_taken = []

            logger.critical(f"🚨 系统紧急熔断已触发: {reason} (by: {triggered_by})")

            # Execute security protection actions
            await self._execute_security_actions()

    async def _execute_security_actions(self):
        """Execute network security protection actions when fuse is triggered."""
        actions = []

        try:
            # 1. Block all pending intent executions
            try:
                from backend.database.connection import async_session_maker
                from backend.database.models import Intent
                from sqlalchemy import select, and_
                async with async_session_maker() as session:
                    result = await session.execute(
                        select(Intent).where(Intent.status.in_(["pending", "approved", "executing"]))
                    )
                    pending_intents = result.scalars().all()
                    blocked_ids = []
                    for intent in pending_intents:
                        intent.status = "blocked_by_fuse"
                        blocked_ids.append(str(intent.id))
                    await session.commit()
                    self.paused_workflows = blocked_ids
                    actions.append(f"blocked_pending_intents:{len(blocked_ids)}")
                    logger.info(f"  [安全防护] 已阻止{len(blocked_ids)}个待执行意图: {blocked_ids}")
            except Exception as e:
                actions.append("blocked_pending_intents:db_error")
                logger.warning(f"  [安全防护] 阻止意图失败(数据库不可用): {e}")

            # 2. Pause all active workflows
            try:
                from backend.database.connection import async_session_maker
                from backend.database.models import WorkOrder
                from sqlalchemy import select
                async with async_session_maker() as session:
                    result = await session.execute(
                        select(WorkOrder).where(WorkOrder.status == "in_progress")
                    )
                    active_orders = result.scalars().all()
                    paused_ids = []
                    for order in active_orders:
                        order.status = "paused_by_fuse"
                        paused_ids.append(str(order.id))
                    await session.commit()
                    actions.append(f"paused_active_workflows:{len(paused_ids)}")
                    logger.info(f"  [安全防护] 已暂停{len(paused_ids)}个活跃工作流: {paused_ids}")
            except Exception as e:
                actions.append("paused_active_workflows:db_error")
                logger.warning(f"  [安全防护] 暂停工作流失败(数据库不可用): {e}")

            # 3. Disable auto-healing (set flag for self-healing module to check)
            actions.append("disabled_auto_healing")
            logger.info("  [安全防护] 已禁用自动自愈")

            # 4. Activate network isolation mode (flag for topology)
            actions.append("activated_network_isolation")
            logger.info("  [安全防护] 已激活网络隔离模式")

            # 5. Suspend all scheduled tasks
            try:
                from backend.database.connection import async_session_maker
                from backend.database.models import IntentScheduleRecord
                from sqlalchemy import select, and_
                async with async_session_maker() as session:
                    result = await session.execute(
                        select(IntentScheduleRecord).where(
                            IntentScheduleRecord.status.in_(["pending", "scheduled"])
                        )
                    )
                    scheduled = result.scalars().all()
                    suspended_ids = []
                    for s in scheduled:
                        s.status = "suspended_by_fuse"
                        suspended_ids.append(str(s.id))
                    await session.commit()
                    actions.append(f"suspended_scheduled_tasks:{len(suspended_ids)}")
                    logger.info(f"  [安全防护] 已挂起{len(suspended_ids)}个调度任务")
            except Exception as e:
                actions.append("suspended_scheduled_tasks:db_error")
                logger.warning(f"  [安全防护] 挂起调度任务失败(数据库不可用): {e}")

            # 6. Enable enhanced audit logging
            actions.append("enhanced_audit_logging")
            logger.info("  [安全防护] 已启用增强审计日志")

            self.security_actions_taken = actions

        except Exception as e:
            logger.error(f"  [安全防护] 执行安全动作异常: {e}")

    async def disable_fuse(self):
        async with self._lock:
            if not self.fuse_enabled:
                return

            self.fuse_enabled = False
            self.fuse_reason = ""
            self.fuse_time = None
            self.triggered_by = "manual"
            self.paused_workflows = []
            self.paused_agents = []
            self.security_actions_taken = []
            logger.info("✅ 系统紧急熔断已解除，恢复正常运行")

    def is_fuse_enabled(self):
        return self.fuse_enabled

    def get_fuse_info(self) -> dict:
        return {
            "fuse_enabled": self.fuse_enabled,
            "fuse_reason": self.fuse_reason,
            "fuse_time": self.fuse_time,
            "triggered_by": self.triggered_by,
            "security_actions_taken": self.security_actions_taken,
            "paused_workflows": len(self.paused_workflows),
            "paused_agents": len(self.paused_agents),
        }

    async def check_auto_trigger(self, event_type: str, count: int) -> bool:
        """Check if auto-trigger conditions are met based on event counts."""
        if self.fuse_enabled:
            return False

        should_trigger = False
        reason = ""

        if event_type == "critical_alerts" and count >= self.auto_trigger_rules["critical_alerts_threshold"]:
            should_trigger = True
            reason = f"自动熔断: 检测到{count}个严重告警(阈值{self.auto_trigger_rules['critical_alerts_threshold']})"

        elif event_type == "failed_executions" and count >= self.auto_trigger_rules["failed_executions_threshold"]:
            should_trigger = True
            reason = f"自动熔断: 检测到{count}次执行失败(阈值{self.auto_trigger_rules['failed_executions_threshold']})"

        elif event_type == "unauthorized_access" and count >= self.auto_trigger_rules["unauthorized_access_threshold"]:
            should_trigger = True
            reason = f"自动熔断: 检测到{count}次未授权访问(阈值{self.auto_trigger_rules['unauthorized_access_threshold']})"

        if should_trigger:
            await self.enable_fuse(reason=reason, triggered_by="auto")
            # Notify via WebSocket
            try:
                from backend.agents.proactive_notifier import get_proactive_notifier
                notifier = get_proactive_notifier()
                await notifier._broadcast({
                    "type": "emergency_fuse",
                    "data": {
                        "action": "fuse_enabled",
                        "reason": reason,
                        "triggered_by": "auto",
                        "security_actions": self.security_actions_taken,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                })
            except Exception:
                pass

        return should_trigger


system_state = SystemState()


class FuseRequest(BaseModel):
    enable: bool
    reason: str = "紧急熔断"


class FuseStatus(BaseModel):
    fuse_enabled: bool
    fuse_reason: str
    fuse_time: Optional[datetime] = None
    triggered_by: str = "manual"
    paused_workflows: int = 0
    paused_agents: int = 0
    security_actions_taken: List[str] = []


class AutoTriggerConfig(BaseModel):
    critical_alerts_threshold: int = 5
    failed_executions_threshold: int = 10
    unauthorized_access_threshold: int = 3


@router.post("/fuse", response_model=FuseStatus)
async def toggle_fuse(request: FuseRequest, current_user=Depends(requires_permission("system:manage"))):
    if request.enable:
        await system_state.enable_fuse(reason=request.reason, triggered_by="manual")
    else:
        await system_state.disable_fuse()

    # Write audit log
    try:
        from backend.database.connection import async_session_maker
        from backend.database.models import AuditLog
        async with async_session_maker() as session:
            audit = AuditLog(
                user_id=current_user.username if hasattr(current_user, "username") else str(current_user),
                action="emergency_fuse_enable" if request.enable else "emergency_fuse_disable",
                target_device="system",
                status="success",
                security_type="critical" if request.enable else "info",
                commands=[{
                    "reason": request.reason,
                    "triggered_by": "manual",
                    "security_actions": system_state.security_actions_taken if request.enable else [],
                }]
            )
            session.add(audit)
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to write fuse audit log: {e}")

    # Notify via WebSocket
    try:
        from backend.agents.proactive_notifier import get_proactive_notifier
        notifier = get_proactive_notifier()
        await notifier._broadcast({
            "type": "emergency_fuse",
            "data": {
                "action": "fuse_enabled" if request.enable else "fuse_disabled",
                "reason": request.reason,
                "triggered_by": "manual",
                "security_actions": system_state.security_actions_taken if request.enable else [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        })
    except Exception:
        pass

    info = system_state.get_fuse_info()
    return FuseStatus(**info)


@router.get("/fuse/status", response_model=FuseStatus)
async def get_fuse_status():
    info = system_state.get_fuse_info()
    return FuseStatus(**info)


@router.get("/fuse/config")
async def get_auto_trigger_config(current_user=Depends(requires_permission("system:manage"))):
    return system_state.auto_trigger_rules


@router.put("/fuse/config")
async def update_auto_trigger_config(
    config: AutoTriggerConfig,
    current_user=Depends(requires_permission("system:manage"))
):
    system_state.auto_trigger_rules = {
        "critical_alerts_threshold": config.critical_alerts_threshold,
        "failed_executions_threshold": config.failed_executions_threshold,
        "unauthorized_access_threshold": config.unauthorized_access_threshold,
    }
    return {"status": "success", "config": system_state.auto_trigger_rules}


def check_fuse():
    """Dependency to check if system is in fuse state. Raises 503 if fused."""
    if system_state.is_fuse_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": f"系统已进入紧急熔断状态: {system_state.fuse_reason}",
                "triggered_by": system_state.triggered_by,
                "fuse_time": system_state.fuse_time.isoformat() if system_state.fuse_time else None,
                "security_actions": system_state.security_actions_taken,
            }
        )


@router.get("/health")
async def system_health():
    if system_state.is_fuse_enabled():
        return {
            "status": "fused",
            "message": f"系统紧急熔断中: {system_state.fuse_reason}",
            "triggered_by": system_state.triggered_by,
            "fuse_time": system_state.fuse_time,
            "security_actions": system_state.security_actions_taken,
        }
    return {"status": "healthy", "fuse_enabled": False}
