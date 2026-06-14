from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, List
from backend.core.security.rbac import get_current_user, requires_permission
from backend.core.cache import api_cache
from backend.api.fuse import check_fuse
from backend.workflow.work_order import work_order_manager, get_enhanced_work_order_manager
from backend.api.response import success_response
from backend.database.models import AuditLog
from backend.database.connection import async_session_maker
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateOrderRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    intent_id: Optional[str] = None


class ApproveRequest(BaseModel):
    pass


class RejectRequest(BaseModel):
    reason: str


class CompleteRequest(BaseModel):
    result: str


class AddSLARequest(BaseModel):
    sla_type: str = Field(..., min_length=1)
    target_duration_minutes: int = Field(..., gt=0)


class StartSLARequest(BaseModel):
    sla_type: str = Field(..., min_length=1)


class CompleteSLARequest(BaseModel):
    sla_type: str = Field(..., min_length=1)


class AddDependencyRequest(BaseModel):
    depends_on_order_id: str = Field(..., min_length=1)
    dependency_type: str = "completion"


class CreateAutomationRuleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    trigger_condition: Dict = Field(...)
    action: Dict = Field(...)


class ToggleRuleRequest(BaseModel):
    is_active: bool


class EvaluateRulesRequest(BaseModel):
    context: Dict


def _serialize_order(order: dict) -> dict:
    result = dict(order)
    if "created_at" in result and isinstance(result["created_at"], object):
        result["created_at"] = result["created_at"].isoformat()
    if "updated_at" in result and isinstance(result["updated_at"], object):
        result["updated_at"] = result["updated_at"].isoformat()
    return result


# ---- 工单 CRUD ----

@router.post("/orders")
async def create_order(req: CreateOrderRequest, current_user=Depends(requires_permission("workflow:create")), _fuse=Depends(check_fuse)):
    try:
        order = work_order_manager.create_order(
            title=req.title,
            description=req.description,
            priority=req.priority,
            created_by=current_user.username,
            intent_id=req.intent_id,
        )
        return {"status": "success", "data": _serialize_order(order)}
    except Exception as e:
        logger.error(f"Create work order failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/orders")
async def list_orders(
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    try:
        orders = await work_order_manager.list_orders(status=status, assigned_to=assigned_to)
        return {"status": "success", "data": [_serialize_order(o) for o in orders], "total": len(orders)}
    except Exception as e:
        logger.error(f"List work orders failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/orders/{order_id}")
async def get_order(order_id: str, current_user=Depends(get_current_user)):
    order = await work_order_manager.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Work order not found: {order_id}")
    return {"status": "success", "data": _serialize_order(order)}


@router.post("/orders/{order_id}/approve")
async def approve_order(order_id: str, current_user=Depends(requires_permission("workflow:manage")), _fuse=Depends(check_fuse)):
    try:
        order = await work_order_manager.approve_order(order_id, approver_role=current_user.role)
        # 记录审计日志
        try:
            async with async_session_maker() as session:
                session.add(AuditLog(
                    user_id=current_user.username,
                    action="approve_work_order",
                    target_device=order.get("target_device", "system"),
                    commands=[f"Approve work order #{order_id}"],
                    status="success",
                    timestamp=datetime.now(timezone.utc)
                ))
                await session.commit()
                api_cache.invalidate("audit_stats")
        except Exception as e:
            logger.warning(f"Failed to write audit log for order approval: {e}")
        return {"status": "success", "data": _serialize_order(order)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Approve work order failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/orders/{order_id}/reject")
async def reject_order(order_id: str, req: RejectRequest, current_user=Depends(requires_permission("workflow:manage")), _fuse=Depends(check_fuse)):
    try:
        order = await work_order_manager.reject_order(order_id, approver_role=current_user.role, reason=req.reason)
        try:
            async with async_session_maker() as session:
                session.add(AuditLog(
                    user_id=current_user.username,
                    action="reject_work_order",
                    target_device=order.get("target_device", "system"),
                    commands=[f"Reject work order #{order_id}: {req.reason}"],
                    status="success",
                    timestamp=datetime.now(timezone.utc)
                ))
                await session.commit()
                api_cache.invalidate("audit_stats")
        except Exception as e:
            logger.warning(f"Failed to write audit log for order rejection: {e}")
        return {"status": "success", "data": _serialize_order(order)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Reject work order failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/orders/{order_id}/execute")
async def execute_order(order_id: str, current_user=Depends(requires_permission("workflow:manage")), _fuse=Depends(check_fuse)):
    try:
        order = await work_order_manager.execute_order(order_id)
        try:
            async with async_session_maker() as session:
                session.add(AuditLog(
                    user_id=current_user.username,
                    action="execute_work_order",
                    target_device=order.get("target_device", "system"),
                    commands=[f"Execute work order #{order_id}"],
                    status="success",
                    timestamp=datetime.now(timezone.utc)
                ))
                await session.commit()
                api_cache.invalidate("audit_stats")
        except Exception as e:
            logger.warning(f"Failed to write audit log for order execution: {e}")
        return {"status": "success", "data": _serialize_order(order)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Execute work order failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/orders/{order_id}/complete")
async def complete_order(order_id: str, req: CompleteRequest, current_user=Depends(requires_permission("workflow:manage")), _fuse=Depends(check_fuse)):
    try:
        order = await work_order_manager.complete_order(order_id, result=req.result)
        try:
            async with async_session_maker() as session:
                session.add(AuditLog(
                    user_id=current_user.username,
                    action="complete_work_order",
                    target_device=order.get("target_device", "system"),
                    commands=[f"Complete work order #{order_id}"],
                    status="success",
                    timestamp=datetime.now(timezone.utc)
                ))
                await session.commit()
                api_cache.invalidate("audit_stats")
        except Exception as e:
            logger.warning(f"Failed to write audit log for order completion: {e}")
        return {"status": "success", "data": _serialize_order(order)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Complete work order failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/board")
async def get_board_summary(current_user=Depends(get_current_user)):
    try:
        summary = await work_order_manager.get_board_summary()
        return {"status": "success", "data": summary}
    except Exception as e:
        logger.error(f"Get board summary failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---- SLA 管理 ----

@router.get("/orders/{order_id}/sla")
async def get_sla_status(order_id: str, current_user=Depends(get_current_user)):
    try:
        manager = get_enhanced_work_order_manager()
        sla_status = await manager.check_sla_status(order_id)
        return success_response(data=sla_status)
    except Exception as e:
        logger.error(f"Get SLA status failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/orders/{order_id}/sla")
async def add_sla(order_id: str, req: AddSLARequest, current_user=Depends(requires_permission("workflow:manage"))):
    try:
        manager = get_enhanced_work_order_manager()
        sla = await manager.add_sla(
            work_order_id=order_id,
            sla_type=req.sla_type,
            target_duration_minutes=req.target_duration_minutes,
        )
        return success_response(data={
                "id": sla.id,
                "work_order_id": sla.work_order_id,
                "sla_type": sla.sla_type,
                "target_duration_minutes": sla.target_duration_minutes,
                "status": sla.status,
                "created_at": sla.created_at.isoformat() if sla.created_at else None,
            })
    except Exception as e:
        logger.error(f"Add SLA failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sla/at-risk")
async def get_at_risk_sla(current_user=Depends(get_current_user)):
    try:
        manager = get_enhanced_work_order_manager()
        at_risk = await manager.get_at_risk_sla()
        return success_response(data={"items": at_risk, "total": len(at_risk)})
    except Exception as e:
        logger.error(f"Get at-risk SLA failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sla/breached")
async def get_breached_sla(current_user=Depends(get_current_user)):
    try:
        manager = get_enhanced_work_order_manager()
        breached = await manager.get_breached_sla()
        return success_response(data={"items": breached, "total": len(breached)})
    except Exception as e:
        logger.error(f"Get breached SLA failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---- 依赖管理 ----

@router.post("/orders/{order_id}/dependencies")
async def add_dependency(order_id: str, req: AddDependencyRequest, current_user=Depends(requires_permission("workflow:manage"))):
    try:
        manager = get_enhanced_work_order_manager()
        dep = await manager.add_dependency(
            work_order_id=order_id,
            depends_on_order_id=req.depends_on_order_id,
            dependency_type=req.dependency_type,
        )
        return success_response(data={
                "id": dep.id,
                "work_order_id": dep.work_order_id,
                "depends_on_order_id": dep.depends_on_order_id,
                "dependency_type": dep.dependency_type,
                "status": dep.status,
                "created_at": dep.created_at.isoformat() if dep.created_at else None,
            })
    except Exception as e:
        logger.error(f"Add dependency failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/orders/{order_id}/dependencies")
async def get_dependencies(order_id: str, current_user=Depends(get_current_user)):
    try:
        manager = get_enhanced_work_order_manager()
        result = await manager.check_dependencies(order_id)
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Get dependencies failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/orders/{order_id}/blocking")
async def get_blocking_orders(order_id: str, current_user=Depends(get_current_user)):
    try:
        manager = get_enhanced_work_order_manager()
        blocking = await manager.get_blocking_orders(order_id)
        return success_response(data={"items": blocking, "total": len(blocking)})
    except Exception as e:
        logger.error(f"Get blocking orders failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---- 自动化规则 ----

@router.get("/automation/rules")
async def list_automation_rules(is_active: Optional[bool] = None, current_user=Depends(get_current_user)):
    try:
        manager = get_enhanced_work_order_manager()
        rules = await manager.list_automation_rules(is_active=is_active)
        return success_response(data={"items": rules, "total": len(rules)})
    except Exception as e:
        logger.error(f"List automation rules failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/automation/rules")
async def create_automation_rule(req: CreateAutomationRuleRequest, current_user=Depends(requires_permission("workflow:manage"))):
    try:
        manager = get_enhanced_work_order_manager()
        rule = await manager.create_automation_rule(
            name=req.name,
            trigger_condition=req.trigger_condition,
            action=req.action,
            created_by=current_user.username,
        )
        return success_response(data={
                "id": rule.id,
                "rule_id": rule.rule_id,
                "name": rule.name,
                "description": rule.description,
                "trigger_condition": rule.trigger_condition,
                "action": rule.action,
                "is_active": rule.is_active,
                "created_by": rule.created_by,
                "created_at": rule.created_at.isoformat() if rule.created_at else None,
            })
    except Exception as e:
        logger.error(f"Create automation rule failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/automation/rules/{rule_id}")
async def update_automation_rule(rule_id: str, req: CreateAutomationRuleRequest, current_user=Depends(requires_permission("workflow:manage"))):
    try:
        from sqlalchemy import select
        from backend.database.connection import async_session_maker
        from backend.database.models import WorkOrderAutomationRule

        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderAutomationRule).where(WorkOrderAutomationRule.rule_id == rule_id)
            )
            rule = result.scalar_one_or_none()
            if not rule:
                raise HTTPException(status_code=404, detail=f"Automation rule not found: {rule_id}")

            rule.name = req.name
            rule.description = req.description
            rule.trigger_condition = req.trigger_condition
            rule.action = req.action
            await session.commit()
            await session.refresh(rule)

        return success_response(data={
                "rule_id": rule.rule_id,
                "name": rule.name,
                "description": rule.description,
                "trigger_condition": rule.trigger_condition,
                "action": rule.action,
                "is_active": rule.is_active,
            })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update automation rule failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/automation/rules/{rule_id}")
async def delete_automation_rule(rule_id: str, current_user=Depends(requires_permission("workflow:manage"))):
    try:
        from sqlalchemy import select
        from backend.database.connection import async_session_maker
        from backend.database.models import WorkOrderAutomationRule

        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderAutomationRule).where(WorkOrderAutomationRule.rule_id == rule_id)
            )
            rule = result.scalar_one_or_none()
            if not rule:
                raise HTTPException(status_code=404, detail=f"Automation rule not found: {rule_id}")

            await session.delete(rule)
            await session.commit()

        return success_response(data={"rule_id": rule_id, "deleted": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete automation rule failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/automation/rules/{rule_id}/toggle")
async def toggle_automation_rule(rule_id: str, req: ToggleRuleRequest, current_user=Depends(requires_permission("workflow:manage"))):
    try:
        manager = get_enhanced_work_order_manager()
        result = await manager.toggle_rule(rule_id, is_active=req.is_active)
        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Toggle automation rule failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/automation/evaluate")
async def evaluate_automation_rules(req: EvaluateRulesRequest, current_user=Depends(get_current_user)):
    try:
        manager = get_enhanced_work_order_manager()
        matched = await manager.evaluate_automation_rules(req.context)
        results = []
        for rule in matched:
            action_result = await manager.execute_automation_action(rule["action"], req.context)
            results.append({
                "rule_id": rule["rule_id"],
                "name": rule["name"],
                "action_result": action_result,
            })
        return success_response(data={"items": results, "total": len(results)})
    except Exception as e:
        logger.error(f"Evaluate automation rules failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
