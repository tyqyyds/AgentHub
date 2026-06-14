from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from backend.core.security.rbac import get_current_user, requires_permission
from backend.cross_domain.registry import registry_center
from backend.cross_domain.a2a_protocol import a2a_server, JSONRPCRequest
from backend.cross_domain.semantic_router import semantic_router
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentRegisterRequest(BaseModel):
    agent_id: str
    capabilities: List[str] = []
    endpoint: str = ""
    ws_endpoint: str = ""
    tags: Dict[str, str] = Field(default_factory=dict)
    cpu_load: float = 0.0
    memory_free: float = 100.0


class DiscoverRequest(BaseModel):
    capabilities: Optional[List[str]] = None
    tags: Optional[Dict[str, str]] = None


class RouteRequest(BaseModel):
    intent_text: str
    required_capabilities: Optional[List[str]] = None


@router.post("/register")
async def register_agent(req: AgentRegisterRequest, current_user=Depends(requires_permission("system:manage"))):
    try:
        agent = registry_center.register(req.model_dump())
        return {"status": "success", "data": agent.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Register agent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/agents/{agent_id}")
async def deregister_agent(agent_id: str, current_user=Depends(requires_permission("system:manage"))):
    success = registry_center.deregister(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return {"status": "success", "data": {"agent_id": agent_id}}


@router.get("/agents")
async def list_agents(current_user=Depends(get_current_user)):
    agents = registry_center.list_all()
    return {
        "status": "success",
        "data": [a.model_dump() for a in agents],
        "total": len(agents),
    }


@router.post("/discover")
async def discover_agents(req: DiscoverRequest, current_user=Depends(get_current_user)):
    agents = registry_center.discover(capabilities=req.capabilities, tags=req.tags)
    return {
        "status": "success",
        "data": [a.model_dump() for a in agents],
        "count": len(agents),
    }


@router.post("/route")
async def route_intent(req: RouteRequest, current_user=Depends(get_current_user)):
    decision = semantic_router.explain_routing(req.intent_text, req.required_capabilities)
    result = decision.model_dump()
    if decision.selected_agent:
        result["selected_agent"] = decision.selected_agent.model_dump()
    return {"status": "success", "data": result}


@router.post("/a2a")
async def a2a_endpoint(request: JSONRPCRequest, current_user=Depends(get_current_user)):
    auth_header = f"Bearer {current_user.username}"
    response = await a2a_server.handle_request(request, auth_token=auth_header)
    return response.model_dump(exclude_none=True)


@router.get("/topology")
async def get_topology(current_user=Depends(get_current_user)):
    topology = registry_center.get_topology()
    return {"status": "success", "data": topology}
