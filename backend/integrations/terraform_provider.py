import uuid
import hashlib
import logging
from typing import Optional, Dict, List, Any

from sqlalchemy import select
from backend.database.connection import async_session_maker
from backend.database.models import Intent, Device, PolicyTemplate, WorkOrder, WorkOrderSLA

logger = logging.getLogger(__name__)

RESOURCE_SCHEMAS = {
    "agenthub_intent": {
        "version": 1,
        "block": {
            "attributes": {
                "intent_name": {"type": "string", "description": "Name of the intent", "required": True},
                "user_input": {"type": "string", "description": "User input text", "required": True},
                "structured_params": {"type": "object", "description": "Structured parameters", "required": True},
                "approval_status": {"type": "string", "description": "Approval status", "optional": True, "default": "pending"},
                "execution_status": {"type": "string", "description": "Execution status", "optional": True, "default": "not_started"},
                "sla_conditions": {"type": "object", "description": "SLA conditions", "optional": True},
            },
        },
    },
    "agenthub_device": {
        "version": 1,
        "block": {
            "attributes": {
                "device_id": {"type": "string", "description": "Unique device identifier", "required": True},
                "name": {"type": "string", "description": "Device name", "required": True},
                "device_type": {"type": "string", "description": "Device type", "required": True},
                "vendor": {"type": "string", "description": "Device vendor", "required": True},
                "ip_address": {"type": "string", "description": "IP address", "required": True},
                "status": {"type": "string", "description": "Device status", "optional": True, "default": "healthy"},
                "os_type": {"type": "string", "description": "OS type", "optional": True},
                "ssh_port": {"type": "integer", "description": "SSH port", "optional": True, "default": 22},
                "netconf_port": {"type": "integer", "description": "NETCONF port", "optional": True, "default": 830},
                "location": {"type": "string", "description": "Device location", "optional": True},
            },
        },
    },
    "agenthub_policy_template": {
        "version": 1,
        "block": {
            "attributes": {
                "template_id": {"type": "string", "description": "Unique template identifier", "required": True},
                "vendor": {"type": "string", "description": "Vendor name", "required": True},
                "device_type": {"type": "string", "description": "Device type", "required": True},
                "function": {"type": "string", "description": "Policy function", "required": True},
                "template_content": {"type": "string", "description": "Template content", "required": True},
                "parameters_schema": {"type": "object", "description": "Parameters JSON schema", "required": True},
            },
        },
    },
    "agenthub_work_order": {
        "version": 1,
        "block": {
            "attributes": {
                "id": {"type": "string", "description": "Work order ID", "required": True},
                "title": {"type": "string", "description": "Work order title", "required": True},
                "description": {"type": "string", "description": "Work order description", "required": True},
                "priority": {"type": "string", "description": "Priority level", "required": True},
                "created_by": {"type": "string", "description": "Creator username", "required": True},
                "status": {"type": "string", "description": "Work order status", "optional": True, "default": "pending"},
                "assigned_to": {"type": "string", "description": "Assignee", "optional": True},
                "approval_chain": {"type": "array", "description": "Approval chain", "optional": True},
                "intent_id": {"type": "string", "description": "Related intent ID", "optional": True},
            },
        },
    },
    "agenthub_sla_rule": {
        "version": 1,
        "block": {
            "attributes": {
                "work_order_id": {"type": "string", "description": "Related work order ID", "required": True},
                "sla_type": {"type": "string", "description": "SLA type", "required": True},
                "target_duration_minutes": {"type": "integer", "description": "Target duration in minutes", "required": True},
                "status": {"type": "string", "description": "SLA status", "optional": True, "default": "pending"},
                "deadline": {"type": "string", "description": "SLA deadline", "optional": True},
            },
        },
    },
}

MODEL_MAP = {
    "agenthub_intent": Intent,
    "agenthub_device": Device,
    "agenthub_policy_template": PolicyTemplate,
    "agenthub_work_order": WorkOrder,
    "agenthub_sla_rule": WorkOrderSLA,
}


def _model_to_dict(instance) -> dict:
    if instance is None:
        return {}
    result = {}
    for col in instance.__table__.columns:
        val = getattr(instance, col.name, None)
        if val is not None and hasattr(val, "isoformat"):
            val = val.isoformat()
        result[col.name] = val
    return result


class TerraformProvider:
    def __init__(self):
        self._configured = False
        self._config: Dict[str, Any] = {}

    def configure(self, config: Dict[str, Any]) -> dict:
        self._config = config
        self._configured = True
        return {"status": "configured", "provider": "agenthub", "version": "1.0.0"}

    def get_schemas(self) -> dict:
        return RESOURCE_SCHEMAS

    async def read_resource(self, resource_type: str, resource_id: str) -> dict:
        model = MODEL_MAP.get(resource_type)
        if model is None:
            raise ValueError(f"Unsupported resource type: {resource_type}")

        async with async_session_maker() as session:
            if resource_type == "agenthub_intent":
                stmt = select(model).where(model.id == int(resource_id))
            elif resource_type == "agenthub_device":
                stmt = select(model).where(model.device_id == resource_id)
            elif resource_type == "agenthub_policy_template":
                stmt = select(model).where(model.template_id == resource_id)
            elif resource_type == "agenthub_work_order":
                stmt = select(model).where(model.id == resource_id)
            elif resource_type == "agenthub_sla_rule":
                stmt = select(model).where(model.id == int(resource_id))
            else:
                raise ValueError(f"Unsupported resource type: {resource_type}")

            result = await session.execute(stmt)
            instance = result.scalar_one_or_none()
            if instance is None:
                raise ValueError(f"Resource not found: {resource_type}/{resource_id}")
            return _model_to_dict(instance)

    async def create_resource(self, resource_type: str, config: dict) -> dict:
        model = MODEL_MAP.get(resource_type)
        if model is None:
            raise ValueError(f"Unsupported resource type: {resource_type}")

        async with async_session_maker() as session:
            instance = model(**config)
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            return _model_to_dict(instance)

    async def update_resource(self, resource_type: str, resource_id: str, config: dict) -> dict:
        model = MODEL_MAP.get(resource_type)
        if model is None:
            raise ValueError(f"Unsupported resource type: {resource_type}")

        async with async_session_maker() as session:
            if resource_type == "agenthub_intent":
                stmt = select(model).where(model.id == int(resource_id))
            elif resource_type == "agenthub_device":
                stmt = select(model).where(model.device_id == resource_id)
            elif resource_type == "agenthub_policy_template":
                stmt = select(model).where(model.template_id == resource_id)
            elif resource_type == "agenthub_work_order":
                stmt = select(model).where(model.id == resource_id)
            elif resource_type == "agenthub_sla_rule":
                stmt = select(model).where(model.id == int(resource_id))
            else:
                raise ValueError(f"Unsupported resource type: {resource_type}")

            result = await session.execute(stmt)
            instance = result.scalar_one_or_none()
            if instance is None:
                raise ValueError(f"Resource not found: {resource_type}/{resource_id}")

            for key, value in config.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)

            await session.commit()
            await session.refresh(instance)
            return _model_to_dict(instance)

    async def delete_resource(self, resource_type: str, resource_id: str) -> dict:
        model = MODEL_MAP.get(resource_type)
        if model is None:
            raise ValueError(f"Unsupported resource type: {resource_type}")

        async with async_session_maker() as session:
            if resource_type == "agenthub_intent":
                stmt = select(model).where(model.id == int(resource_id))
            elif resource_type == "agenthub_device":
                stmt = select(model).where(model.device_id == resource_id)
            elif resource_type == "agenthub_policy_template":
                stmt = select(model).where(model.template_id == resource_id)
            elif resource_type == "agenthub_work_order":
                stmt = select(model).where(model.id == resource_id)
            elif resource_type == "agenthub_sla_rule":
                stmt = select(model).where(model.id == int(resource_id))
            else:
                raise ValueError(f"Unsupported resource type: {resource_type}")

            result = await session.execute(stmt)
            instance = result.scalar_one_or_none()
            if instance is None:
                raise ValueError(f"Resource not found: {resource_type}/{resource_id}")

            await session.delete(instance)
            await session.commit()
            return {"resource_type": resource_type, "resource_id": resource_id, "deleted": True}

    async def list_resources(self, resource_type: str) -> List[dict]:
        model = MODEL_MAP.get(resource_type)
        if model is None:
            raise ValueError(f"Unsupported resource type: {resource_type}")

        async with async_session_maker() as session:
            stmt = select(model)
            result = await session.execute(stmt)
            instances = result.scalars().all()
            return [_model_to_dict(inst) for inst in instances]

    async def import_resource(self, resource_type: str, resource_id: str) -> dict:
        resource_data = await self.read_resource(resource_type, resource_id)
        return {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "imported": True,
            "state": resource_data,
        }

    async def plan_changes(self, changes: List[dict]) -> dict:
        plan = {
            "id": f"plan_{uuid.uuid4().hex[:8]}",
            "creates": [],
            "updates": [],
            "deletes": [],
            "no_changes": [],
        }

        for change in changes:
            action = change.get("action")
            resource_type = change.get("resource_type")
            resource_id = change.get("resource_id")
            config = change.get("config", {})

            if resource_type not in MODEL_MAP:
                plan["no_changes"].append({
                    "resource_type": resource_type,
                    "reason": "unsupported_resource_type",
                })
                continue

            try:
                if action == "create":
                    plan["creates"].append({
                        "resource_type": resource_type,
                        "config": config,
                    })
                elif action == "update":
                    current = await self.read_resource(resource_type, resource_id)
                    diff = {}
                    for key, new_val in config.items():
                        old_val = current.get(key)
                        if old_val != new_val:
                            diff[key] = {"old": old_val, "new": new_val}
                    plan["updates"].append({
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "diff": diff,
                    })
                elif action == "delete":
                    plan["deletes"].append({
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                    })
                else:
                    plan["no_changes"].append({
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "reason": f"unknown_action: {action}",
                    })
            except ValueError:
                plan["no_changes"].append({
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "reason": "resource_not_found",
                })

        plan["summary"] = {
            "create": len(plan["creates"]),
            "update": len(plan["updates"]),
            "delete": len(plan["deletes"]),
            "no_change": len(plan["no_changes"]),
        }
        return plan


_terraform_provider: Optional[TerraformProvider] = None


def get_terraform_provider() -> TerraformProvider:
    global _terraform_provider
    if _terraform_provider is None:
        _terraform_provider = TerraformProvider()
    return _terraform_provider
