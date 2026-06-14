import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from backend.core.security.rbac import get_current_user
from backend.api.response import success_response

logger = logging.getLogger(__name__)

router = APIRouter()


class ConfigureRequest(BaseModel):
    config: Dict[str, Any] = {}


class CreateResourceRequest(BaseModel):
    config: Dict[str, Any] = Field(..., max_length=10000)

    @field_validator('config')
    @classmethod
    def validate_config_size(cls, v):
        import json
        if len(json.dumps(v)) > 10000:
            raise ValueError('config payload exceeds maximum allowed size')
        return v


class UpdateResourceRequest(BaseModel):
    config: Dict[str, Any] = Field(..., max_length=10000)

    @field_validator('config')
    @classmethod
    def validate_config_size(cls, v):
        import json
        if len(json.dumps(v)) > 10000:
            raise ValueError('config payload exceeds maximum allowed size')
        return v


ALLOWED_RESOURCE_TYPES = [
    "agenthub_intent", "agenthub_device",
    "agenthub_policy_template", "agenthub_work_order", "agenthub_sla_rule"
]


class ImportResourceRequest(BaseModel):
    resource_type: str
    resource_id: str

    @field_validator('resource_type')
    @classmethod
    def validate_resource_type(cls, v):
        if v not in ALLOWED_RESOURCE_TYPES:
            raise ValueError(f'Unsupported resource type: {v}. Allowed: {", ".join(ALLOWED_RESOURCE_TYPES)}')
        return v


class PlanChangesRequest(BaseModel):
    changes: List[Dict[str, Any]]


def _require_admin(current_user):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


@router.post("/configure")
async def configure_provider(
    req: ConfigureRequest,
    current_user=Depends(get_current_user),
):
    _require_admin(current_user)
    try:
        from backend.integrations.terraform_provider import get_terraform_provider
        provider = get_terraform_provider()
        result = provider.configure(req.config)
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Configure terraform provider failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/schema")
async def get_schemas(
    current_user=Depends(get_current_user),
):
    _require_admin(current_user)
    try:
        from backend.integrations.terraform_provider import get_terraform_provider
        provider = get_terraform_provider()
        schemas = provider.get_schemas()
        return success_response(data=schemas)
    except Exception as e:
        logger.error(f"Get terraform schema failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/resources/{resource_type}")
async def list_resources(
    resource_type: str,
    current_user=Depends(get_current_user),
):
    _require_admin(current_user)
    try:
        from backend.integrations.terraform_provider import get_terraform_provider
        provider = get_terraform_provider()
        resources = await provider.list_resources(resource_type)
        return success_response(data={"items": resources, "total": len(resources)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"List terraform resources failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/resources/{resource_type}/{resource_id}")
async def read_resource(
    resource_type: str,
    resource_id: str,
    current_user=Depends(get_current_user),
):
    _require_admin(current_user)
    try:
        from backend.integrations.terraform_provider import get_terraform_provider
        provider = get_terraform_provider()
        resource = await provider.read_resource(resource_type, resource_id)
        return success_response(data=resource)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Read terraform resource failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/resources/{resource_type}")
async def create_resource(
    resource_type: str,
    req: CreateResourceRequest,
    current_user=Depends(get_current_user),
):
    _require_admin(current_user)
    try:
        from backend.integrations.terraform_provider import get_terraform_provider
        provider = get_terraform_provider()
        resource = await provider.create_resource(resource_type, req.config)
        return success_response(data=resource)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Create terraform resource failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/resources/{resource_type}/{resource_id}")
async def update_resource(
    resource_type: str,
    resource_id: str,
    req: UpdateResourceRequest,
    current_user=Depends(get_current_user),
):
    _require_admin(current_user)
    try:
        from backend.integrations.terraform_provider import get_terraform_provider
        provider = get_terraform_provider()
        resource = await provider.update_resource(resource_type, resource_id, req.config)
        return success_response(data=resource)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Update terraform resource failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/resources/{resource_type}/{resource_id}")
async def delete_resource(
    resource_type: str,
    resource_id: str,
    current_user=Depends(get_current_user),
):
    _require_admin(current_user)
    try:
        from backend.integrations.terraform_provider import get_terraform_provider
        provider = get_terraform_provider()
        result = await provider.delete_resource(resource_type, resource_id)
        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Delete terraform resource failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/plan")
async def plan_changes(
    req: PlanChangesRequest,
    current_user=Depends(get_current_user),
):
    _require_admin(current_user)
    try:
        from backend.integrations.terraform_provider import get_terraform_provider
        provider = get_terraform_provider()
        plan = await provider.plan_changes(req.changes)
        return success_response(data=plan)
    except Exception as e:
        logger.error(f"Plan terraform changes failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/import")
async def import_resource(
    req: ImportResourceRequest,
    current_user=Depends(get_current_user),
):
    _require_admin(current_user)
    try:
        from backend.integrations.terraform_provider import get_terraform_provider
        provider = get_terraform_provider()
        result = await provider.import_resource(req.resource_type, req.resource_id)
        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Import terraform resource failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
