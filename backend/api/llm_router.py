from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from backend.agents.llm_router import get_llm_router
from backend.core.security.rbac import get_current_user, requires_permission
from backend.api.response import success_response
from fastapi import Depends
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class ProviderCreateRequest(BaseModel):
    name: str
    api_url: str
    api_key: str
    model: str
    max_tokens: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    supports_streaming: bool = True
    supports_function_calling: bool = False
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("name cannot be empty")
        return v

    @field_validator("api_url")
    @classmethod
    def api_url_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("api_url cannot be empty")
        return v

    @field_validator("model")
    @classmethod
    def model_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("model cannot be empty")
        return v


class ProviderUpdateRequest(BaseModel):
    api_url: str = None
    api_key: str = None
    model: str = None
    max_tokens: int = None
    cost_per_1k_input: float = None
    cost_per_1k_output: float = None
    supports_streaming: bool = None
    supports_function_calling: bool = None
    enabled: bool = None


@router.get("/providers")
async def list_providers(current_user=Depends(get_current_user)):
    llm_router = get_llm_router()
    return success_response(data=llm_router.get_provider_status())


@router.post("/providers")
async def register_provider(
    provider: ProviderCreateRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("llm-router:manage")),
):
    llm_router = get_llm_router()
    try:
        config = llm_router.register_provider(provider.model_dump())
        return success_response(data={
                "name": config.name,
                "model": config.model,
                "enabled": config.enabled,
                "available": config.available,
            })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Register provider failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/providers/{name}")
async def update_provider(
    name: str,
    provider: ProviderUpdateRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("llm-router:manage")),
):
    llm_router = get_llm_router()
    updates = {k: v for k, v in provider.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    config = llm_router.update_provider(name, updates)
    if not config:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    return success_response(data={
            "name": config.name,
            "model": config.model,
            "enabled": config.enabled,
            "available": config.available,
        })


@router.delete("/providers/{name}")
async def delete_provider(
    name: str,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("llm-router:manage")),
):
    llm_router = get_llm_router()
    removed = llm_router.remove_provider(name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    return success_response()


@router.post("/providers/{name}/toggle")
async def toggle_provider(
    name: str,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("llm-router:manage")),
):
    llm_router = get_llm_router()
    config = llm_router.toggle_provider(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    return success_response(data={
            "name": config.name,
            "enabled": config.enabled,
            "available": config.available,
        })


@router.get("/recommendations/{task_type}")
async def get_recommendations(
    task_type: str,
    current_user=Depends(get_current_user),
):
    llm_router = get_llm_router()
    return success_response(data=llm_router.get_recommendations(task_type))


@router.get("/metrics")
async def get_metrics(current_user=Depends(get_current_user)):
    llm_router = get_llm_router()
    return success_response(data=llm_router.get_metrics())
