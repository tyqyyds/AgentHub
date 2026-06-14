import uuid
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import async_session_maker
from backend.database.models import WorkOrder, WorkOrderSLA, WorkOrderDependency, WorkOrderAutomationRule

logger = logging.getLogger(__name__)


class WorkOrderManager:
    def __init__(self):
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._db_loaded = False

    async def _ensure_db_loaded(self):
        """首次访问时从数据库加载种子数据到内存"""
        if self._db_loaded:
            return
        self._db_loaded = True
        try:
            async with async_session_maker() as session:
                result = await session.execute(select(WorkOrder))
                db_orders = result.scalars().all()
                for o in db_orders:
                    if o.id not in self._orders:
                        chain = o.approval_chain if isinstance(o.approval_chain, list) else []
                        self._orders[o.id] = {
                            "id": o.id,
                            "title": o.title,
                            "description": o.description or "",
                            "status": o.status,
                            "priority": o.priority,
                            "created_by": o.created_by,
                            "assigned_to": o.assigned_to or "",
                            "approval_chain": chain,
                            "current_step": o.current_step or 0,
                            "intent_id": o.intent_id,
                            "result": o.result,
                            "reject_reason": o.reject_reason,
                            "created_at": o.created_at or datetime.now(timezone.utc),
                            "updated_at": o.updated_at or datetime.now(timezone.utc),
                        }
                if db_orders:
                    logger.info(f"Loaded {len(db_orders)} work orders from database")
        except Exception as e:
            logger.warning(f"Failed to load work orders from database: {e}")

    def create_order(
        self,
        title: str,
        description: str,
        priority: str,
        created_by: str,
        intent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        order = {
            "id": order_id,
            "title": title,
            "description": description,
            "status": "pending",
            "priority": priority,
            "created_by": created_by,
            "assigned_to": "",
            "approval_chain": [
                {"role": "operator", "status": "pending"},
                {"role": "admin", "status": "pending"},
            ],
            "current_step": 0,
            "intent_id": intent_id,
            "created_at": now,
            "updated_at": now,
        }
        self._orders[order_id] = order
        logger.info(f"Work order created: {order_id}, title={title}, priority={priority}")
        return order

    async def approve_order(self, order_id: str, approver_role: str) -> Dict[str, Any]:
        await self._ensure_db_loaded()
        order = self._orders.get(order_id)
        if not order:
            raise ValueError(f"Work order not found: {order_id}")
        if order["status"] not in ("pending", "approved"):
            raise ValueError(f"Work order cannot be approved in status: {order['status']}")

        chain = order["approval_chain"]
        current_step = order["current_step"]
        if current_step >= len(chain):
            raise ValueError("All approval steps already completed")

        step = chain[current_step]
        if step["role"] != approver_role and approver_role != "admin":
            raise ValueError(f"Current step requires role '{step['role']}', got '{approver_role}'")

        step["status"] = "approved"
        order["updated_at"] = datetime.now(timezone.utc)

        if approver_role == "admin":
            for remaining_step in chain[current_step + 1:]:
                remaining_step["status"] = "approved"
            order["current_step"] = len(chain)
            order["status"] = "approved"
        else:
            next_step = current_step + 1
            if next_step < len(chain):
                order["current_step"] = next_step
                order["status"] = "approved"
            else:
                order["current_step"] = next_step
                order["status"] = "approved"

        logger.info(f"Work order approved: {order_id}, step={current_step}, by={approver_role}")
        return order

    async def reject_order(self, order_id: str, approver_role: str, reason: str) -> Dict[str, Any]:
        await self._ensure_db_loaded()
        order = self._orders.get(order_id)
        if not order:
            raise ValueError(f"Work order not found: {order_id}")
        if order["status"] not in ("pending", "approved"):
            raise ValueError(f"Work order cannot be rejected in status: {order['status']}")

        chain = order["approval_chain"]
        current_step = order["current_step"]
        if current_step >= len(chain):
            raise ValueError("All approval steps already completed")

        step = chain[current_step]
        if step["role"] != approver_role and approver_role != "admin":
            raise ValueError(f"Current step requires role '{step['role']}', got '{approver_role}'")

        step["status"] = "rejected"
        step["reason"] = reason
        order["status"] = "rejected"
        order["reject_reason"] = reason
        order["updated_at"] = datetime.now(timezone.utc)

        logger.info(f"Work order rejected: {order_id}, step={current_step}, by={approver_role}, reason={reason}")
        return order

    async def execute_order(self, order_id: str) -> Dict[str, Any]:
        await self._ensure_db_loaded()
        order = self._orders.get(order_id)
        if not order:
            raise ValueError(f"Work order not found: {order_id}")

        if order["status"] != "approved":
            raise ValueError(f"Work order must be approved before execution, current status: {order['status']}")

        chain = order["approval_chain"]
        all_approved = all(step["status"] == "approved" for step in chain)
        if not all_approved:
            raise ValueError("Not all approval steps have been approved")

        order["status"] = "executing"
        order["updated_at"] = datetime.now(timezone.utc)
        logger.info(f"Work order executing: {order_id}")
        return order

    async def complete_order(self, order_id: str, result: str) -> Dict[str, Any]:
        await self._ensure_db_loaded()
        order = self._orders.get(order_id)
        if not order:
            raise ValueError(f"Work order not found: {order_id}")
        if order["status"] != "executing":
            raise ValueError(f"Work order must be executing to complete, current status: {order['status']}")

        order["status"] = "completed"
        order["result"] = result
        order["updated_at"] = datetime.now(timezone.utc)
        logger.info(f"Work order completed: {order_id}")
        return order

    async def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_db_loaded()
        return self._orders.get(order_id)

    async def list_orders(
        self,
        status: Optional[str] = None,
        assigned_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        await self._ensure_db_loaded()
        results = list(self._orders.values())
        if status:
            results = [o for o in results if o["status"] == status]
        if assigned_to:
            results = [o for o in results if o["assigned_to"] == assigned_to]
        return results

    async def get_board_summary(self) -> Dict[str, int]:
        await self._ensure_db_loaded()
        counts: Dict[str, int] = {
            "pending": 0,
            "approved": 0,
            "executing": 0,
            "completed": 0,
            "rejected": 0,
        }
        for order in self._orders.values():
            s = order["status"]
            if s in counts:
                counts[s] += 1
        counts["total"] = len(self._orders)
        return counts


work_order_manager = WorkOrderManager()


class EnhancedWorkOrderManager:

    async def add_sla(self, work_order_id: str, sla_type: str, target_duration_minutes: int) -> WorkOrderSLA:
        async with async_session_maker() as session:
            sla = WorkOrderSLA(
                work_order_id=work_order_id,
                sla_type=sla_type,
                target_duration_minutes=target_duration_minutes,
                status="pending",
            )
            session.add(sla)
            await session.commit()
            await session.refresh(sla)
            logger.info(f"SLA added: work_order={work_order_id}, type={sla_type}, target={target_duration_minutes}min")
            return sla

    async def check_sla_status(self, work_order_id: str) -> List[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderSLA).where(WorkOrderSLA.work_order_id == work_order_id)
            )
            slas = result.scalars().all()

        now = datetime.now(timezone.utc)
        status_list = []
        for sla in slas:
            sla_dict = {
                "id": sla.id,
                "work_order_id": sla.work_order_id,
                "sla_type": sla.sla_type,
                "target_duration_minutes": sla.target_duration_minutes,
                "actual_duration_minutes": sla.actual_duration_minutes,
                "status": sla.status,
                "started_at": sla.started_at.isoformat() if sla.started_at else None,
                "deadline": sla.deadline.isoformat() if sla.deadline else None,
                "completed_at": sla.completed_at.isoformat() if sla.completed_at else None,
                "warning_sent": sla.warning_sent,
                "created_at": sla.created_at.isoformat() if sla.created_at else None,
            }

            if sla.status == "pending" and sla.started_at and sla.deadline:
                if now >= sla.deadline:
                    sla_dict["status"] = "breached"
                    async with async_session_maker() as update_session:
                        await update_session.execute(
                            WorkOrderSLA.__table__.update()
                            .where(WorkOrderSLA.id == sla.id)
                            .values(status="breached")
                        )
                        await update_session.commit()
                elif now >= sla.deadline - timedelta(minutes=sla.target_duration_minutes * 0.2):
                    sla_dict["status"] = "at_risk"
                    async with async_session_maker() as update_session:
                        await update_session.execute(
                            WorkOrderSLA.__table__.update()
                            .where(WorkOrderSLA.id == sla.id)
                            .values(status="at_risk")
                        )
                        await update_session.commit()

            status_list.append(sla_dict)
        return status_list

    async def start_sla_timer(self, work_order_id: str, sla_type: str) -> None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderSLA).where(
                    and_(
                        WorkOrderSLA.work_order_id == work_order_id,
                        WorkOrderSLA.sla_type == sla_type,
                        WorkOrderSLA.status == "pending",
                    )
                )
            )
            sla = result.scalar_one_or_none()
            if not sla:
                raise ValueError(f"No pending SLA found for work_order={work_order_id}, type={sla_type}")

            now = datetime.now(timezone.utc)
            sla.started_at = now
            sla.deadline = now + timedelta(minutes=sla.target_duration_minutes)
            await session.commit()
            logger.info(f"SLA timer started: work_order={work_order_id}, type={sla_type}, deadline={sla.deadline}")

    async def complete_sla(self, work_order_id: str, sla_type: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderSLA).where(
                    and_(
                        WorkOrderSLA.work_order_id == work_order_id,
                        WorkOrderSLA.sla_type == sla_type,
                        WorkOrderSLA.status.in_(["pending", "at_risk"]),
                    )
                )
            )
            sla = result.scalar_one_or_none()
            if not sla:
                raise ValueError(f"No active SLA found for work_order={work_order_id}, type={sla_type}")

            now = datetime.now(timezone.utc)
            sla.completed_at = now
            if sla.started_at:
                elapsed = now - sla.started_at
                sla.actual_duration_minutes = int(elapsed.total_seconds() / 60)

            if sla.deadline and now > sla.deadline:
                sla.status = "breached"
            else:
                sla.status = "met"

            await session.commit()
            await session.refresh(sla)

            logger.info(f"SLA completed: work_order={work_order_id}, type={sla_type}, status={sla.status}")
            return {
                "id": sla.id,
                "work_order_id": sla.work_order_id,
                "sla_type": sla.sla_type,
                "target_duration_minutes": sla.target_duration_minutes,
                "actual_duration_minutes": sla.actual_duration_minutes,
                "status": sla.status,
                "started_at": sla.started_at.isoformat() if sla.started_at else None,
                "deadline": sla.deadline.isoformat() if sla.deadline else None,
                "completed_at": sla.completed_at.isoformat() if sla.completed_at else None,
            }

    async def get_at_risk_sla(self) -> List[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderSLA).where(WorkOrderSLA.status == "at_risk")
            )
            slas = result.scalars().all()

        now = datetime.now(timezone.utc)
        at_risk = []
        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderSLA).where(
                    and_(
                        WorkOrderSLA.status == "pending",
                        WorkOrderSLA.started_at.isnot(None),
                        WorkOrderSLA.deadline.isnot(None),
                    )
                )
            )
            active_slas = result.scalars().all()

        for sla in active_slas:
            if sla.deadline and now >= sla.deadline - timedelta(minutes=sla.target_duration_minutes * 0.2):
                if sla.deadline and now < sla.deadline:
                    async with async_session_maker() as update_session:
                        await update_session.execute(
                            WorkOrderSLA.__table__.update()
                            .where(WorkOrderSLA.id == sla.id)
                            .values(status="at_risk")
                        )
                        await update_session.commit()
                    at_risk.append({
                        "id": sla.id,
                        "work_order_id": sla.work_order_id,
                        "sla_type": sla.sla_type,
                        "target_duration_minutes": sla.target_duration_minutes,
                        "deadline": sla.deadline.isoformat() if sla.deadline else None,
                        "status": "at_risk",
                    })

        for sla in slas:
            at_risk.append({
                "id": sla.id,
                "work_order_id": sla.work_order_id,
                "sla_type": sla.sla_type,
                "target_duration_minutes": sla.target_duration_minutes,
                "deadline": sla.deadline.isoformat() if sla.deadline else None,
                "status": "at_risk",
            })

        seen = set()
        unique = []
        for item in at_risk:
            if item["id"] not in seen:
                seen.add(item["id"])
                unique.append(item)
        return unique

    async def get_breached_sla(self) -> List[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderSLA).where(WorkOrderSLA.status == "breached")
            )
            slas = result.scalars().all()

        return [
            {
                "id": sla.id,
                "work_order_id": sla.work_order_id,
                "sla_type": sla.sla_type,
                "target_duration_minutes": sla.target_duration_minutes,
                "actual_duration_minutes": sla.actual_duration_minutes,
                "deadline": sla.deadline.isoformat() if sla.deadline else None,
                "status": "breached",
            }
            for sla in slas
        ]

    async def add_dependency(self, work_order_id: str, depends_on_order_id: str, dependency_type: str = "completion") -> WorkOrderDependency:
        async with async_session_maker() as session:
            dep = WorkOrderDependency(
                work_order_id=work_order_id,
                depends_on_order_id=depends_on_order_id,
                dependency_type=dependency_type,
                status="pending",
            )
            session.add(dep)
            await session.commit()
            await session.refresh(dep)
            logger.info(f"Dependency added: {work_order_id} depends on {depends_on_order_id} ({dependency_type})")
            return dep

    async def check_dependencies(self, work_order_id: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderDependency).where(WorkOrderDependency.work_order_id == work_order_id)
            )
            deps = result.scalars().all()

        if not deps:
            return {"work_order_id": work_order_id, "all_satisfied": True, "dependencies": []}

        all_satisfied = True
        dep_list = []
        for dep in deps:
            if dep.status != "satisfied":
                all_satisfied = False
            dep_list.append({
                "id": dep.id,
                "depends_on_order_id": dep.depends_on_order_id,
                "dependency_type": dep.dependency_type,
                "status": dep.status,
            })

        return {"work_order_id": work_order_id, "all_satisfied": all_satisfied, "dependencies": dep_list}

    async def resolve_dependency(self, work_order_id: str, depends_on_order_id: str) -> None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderDependency).where(
                    and_(
                        WorkOrderDependency.work_order_id == work_order_id,
                        WorkOrderDependency.depends_on_order_id == depends_on_order_id,
                    )
                )
            )
            dep = result.scalar_one_or_none()
            if not dep:
                raise ValueError(f"Dependency not found: {work_order_id} -> {depends_on_order_id}")

            dep.status = "satisfied"
            await session.commit()
            logger.info(f"Dependency resolved: {work_order_id} -> {depends_on_order_id}")

    async def get_blocking_orders(self, work_order_id: str) -> List[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderDependency).where(
                    and_(
                        WorkOrderDependency.work_order_id == work_order_id,
                        WorkOrderDependency.status != "satisfied",
                    )
                )
            )
            deps = result.scalars().all()

        return [
            {
                "id": dep.id,
                "depends_on_order_id": dep.depends_on_order_id,
                "dependency_type": dep.dependency_type,
                "status": dep.status,
            }
            for dep in deps
        ]

    async def create_automation_rule(self, name: str, trigger_condition: dict, action: dict, created_by: str) -> WorkOrderAutomationRule:
        rule_id = f"rule_{uuid.uuid4().hex[:8]}"
        async with async_session_maker() as session:
            rule = WorkOrderAutomationRule(
                rule_id=rule_id,
                name=name,
                trigger_condition=trigger_condition,
                action=action,
                created_by=created_by,
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            logger.info(f"Automation rule created: {rule_id}, name={name}")
            return rule

    async def evaluate_automation_rules(self, context: dict) -> List[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderAutomationRule).where(WorkOrderAutomationRule.is_active == True)
            )
            rules = result.scalars().all()

        matched = []
        for rule in rules:
            condition = rule.trigger_condition if isinstance(rule.trigger_condition, dict) else {}
            if self._match_condition(condition, context):
                async with async_session_maker() as update_session:
                    await update_session.execute(
                        WorkOrderAutomationRule.__table__.update()
                        .where(WorkOrderAutomationRule.id == rule.id)
                        .values(
                            execution_count=rule.execution_count + 1,
                            last_triggered_at=datetime.now(timezone.utc),
                        )
                    )
                    await update_session.commit()

                matched.append({
                    "rule_id": rule.rule_id,
                    "name": rule.name,
                    "trigger_condition": rule.trigger_condition,
                    "action": rule.action,
                })
                logger.info(f"Automation rule matched: {rule.rule_id}")

        return matched

    def _match_condition(self, condition: dict, context: dict) -> bool:
        for key, value in condition.items():
            ctx_value = context.get(key)
            if isinstance(value, list):
                if ctx_value not in value:
                    return False
            elif ctx_value != value:
                return False
        return True

    async def execute_automation_action(self, action: dict, context: dict) -> dict:
        action_type = action.get("type")
        params = action.get("params", {})

        if action_type == "create_work_order":
            order = work_order_manager.create_order(
                title=params.get("title", f"Auto-created: {context.get('intent_type', 'unknown')}"),
                description=params.get("description", "Automatically created by automation rule"),
                priority=params.get("priority", context.get("priority", "medium")),
                created_by=params.get("created_by", "automation"),
                intent_id=context.get("intent_id"),
            )
            if params.get("sla_minutes"):
                await self.add_sla(
                    work_order_id=order["id"],
                    sla_type=params.get("sla_type", "execution"),
                    target_duration_minutes=params["sla_minutes"],
                )
            return {"action": "create_work_order", "order_id": order["id"], "status": "created"}

        elif action_type == "escalate_priority":
            order_id = context.get("work_order_id") or params.get("work_order_id")
            if not order_id:
                return {"action": "escalate_priority", "status": "error", "detail": "No work_order_id in context"}
            order = await work_order_manager.get_order(order_id)
            if order:
                order["priority"] = params.get("priority", "critical")
                order["updated_at"] = datetime.now(timezone.utc)
                return {"action": "escalate_priority", "order_id": order_id, "status": "escalated"}
            return {"action": "escalate_priority", "status": "error", "detail": f"Order {order_id} not found"}

        elif action_type == "notify":
            return {"action": "notify", "status": "sent", "recipients": params.get("recipients", [])}

        return {"action": action_type, "status": "unknown_action"}

    async def toggle_rule(self, rule_id: str, is_active: bool) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(WorkOrderAutomationRule).where(WorkOrderAutomationRule.rule_id == rule_id)
            )
            rule = result.scalar_one_or_none()
            if not rule:
                raise ValueError(f"Automation rule not found: {rule_id}")

            rule.is_active = is_active
            await session.commit()
            await session.refresh(rule)

            logger.info(f"Automation rule toggled: {rule_id}, is_active={is_active}")
            return {
                "rule_id": rule.rule_id,
                "name": rule.name,
                "is_active": rule.is_active,
            }

    async def list_automation_rules(self, is_active: Optional[bool] = None) -> List[dict]:
        async with async_session_maker() as session:
            query = select(WorkOrderAutomationRule)
            if is_active is not None:
                query = query.where(WorkOrderAutomationRule.is_active == is_active)
            query = query.order_by(WorkOrderAutomationRule.created_at.desc())
            result = await session.execute(query)
            rules = result.scalars().all()

        return [
            {
                "id": rule.id,
                "rule_id": rule.rule_id,
                "name": rule.name,
                "description": rule.description,
                "trigger_condition": rule.trigger_condition,
                "action": rule.action,
                "is_active": rule.is_active,
                "execution_count": rule.execution_count,
                "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
                "created_by": rule.created_by,
                "created_at": rule.created_at.isoformat() if rule.created_at else None,
                "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
            }
            for rule in rules
        ]


_enhanced_manager: Optional[EnhancedWorkOrderManager] = None


def get_enhanced_work_order_manager() -> EnhancedWorkOrderManager:
    global _enhanced_manager
    if _enhanced_manager is None:
        _enhanced_manager = EnhancedWorkOrderManager()
    return _enhanced_manager
