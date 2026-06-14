from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from backend.cross_domain.registry import registry_center
from backend.core.security.rbac import create_access_token, decode_token
from backend.core.config import settings
import httpx
import logging
import os

logger = logging.getLogger(__name__)


class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)
    id: Optional[int] = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[int] = None


class JSONRPCError:
    PARSE_ERROR = {"code": -32700, "message": "Parse error"}
    INVALID_REQUEST = {"code": -32600, "message": "Invalid Request"}
    METHOD_NOT_FOUND = {"code": -32601, "message": "Method not found"}
    INVALID_PARAMS = {"code": -32602, "message": "Invalid params"}
    INTERNAL_ERROR = {"code": -32603, "message": "Internal error"}
    AUTH_FAILED = {"code": -32001, "message": "Authentication failed"}


def _generate_agent_token(agent_id: str) -> str:
    token_data = {
        "sub": agent_id,
        "role": "agent",
        "type": "a2a",
    }
    return create_access_token(token_data)


def _verify_agent_token(token: str) -> Optional[dict]:
    payload = decode_token(token)
    if payload is None:
        return None
    if payload.get("type") not in ("access", "a2a"):
        return None
    return payload


class A2AServer:
    def __init__(self):
        self._handlers = {
            "agent.discover": self._handle_discover,
            "agent.call": self._handle_call,
            "agent.status": self._handle_status,
            "agent.heartbeat": self._handle_heartbeat,
        }

    async def handle_request(self, request: JSONRPCRequest, auth_token: Optional[str] = None) -> JSONRPCResponse:
        if auth_token:
            payload = _verify_agent_token(auth_token)
            if payload is None:
                return JSONRPCResponse(
                    error={"code": JSONRPCError.AUTH_FAILED["code"], "message": JSONRPCError.AUTH_FAILED["message"]},
                    id=request.id,
                )

        handler = self._handlers.get(request.method)
        if handler is None:
            return JSONRPCResponse(
                error={"code": JSONRPCError.METHOD_NOT_FOUND["code"], "message": JSONRPCError.METHOD_NOT_FOUND["message"]},
                id=request.id,
            )

        try:
            result = await handler(request.params)
            return JSONRPCResponse(result=result, id=request.id)
        except ValueError as e:
            return JSONRPCResponse(
                error={"code": JSONRPCError.INVALID_PARAMS["code"], "message": str(e)},
                id=request.id,
            )
        except Exception as e:
            logger.error(f"A2A handler error for {request.method}: {e}", exc_info=True)
            return JSONRPCResponse(
                error={"code": JSONRPCError.INTERNAL_ERROR["code"], "message": str(e)},
                id=request.id,
            )

    async def _handle_discover(self, params: dict) -> dict:
        capabilities = params.get("capabilities")
        tags = params.get("tags")
        agents = registry_center.discover(capabilities=capabilities, tags=tags)
        return {
            "agents": [a.model_dump() for a in agents],
            "count": len(agents),
        }

    async def _handle_call(self, params: dict) -> dict:
        target_agent_id = params.get("agent_id")
        if not target_agent_id:
            raise ValueError("agent_id is required for agent.call")
        intent = params.get("intent", {})
        agent = registry_center.get_agent(target_agent_id)
        if agent is None:
            raise ValueError(f"Agent not found: {target_agent_id}")
        if agent.status != "online":
            raise ValueError(f"Agent is offline: {target_agent_id}")
        return {
            "status": "dispatched",
            "agent_id": target_agent_id,
            "intent": intent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _handle_status(self, params: dict) -> dict:
        agent_id = params.get("agent_id")
        if agent_id:
            agent = registry_center.get_agent(agent_id)
            if agent is None:
                raise ValueError(f"Agent not found: {agent_id}")
            return agent.model_dump()
        agents = registry_center.list_all()
        return {
            "agents": [a.model_dump() for a in agents],
            "total": len(agents),
            "online": sum(1 for a in agents if a.status == "online"),
        }

    async def _handle_heartbeat(self, params: dict) -> dict:
        agent_id = params.get("agent_id")
        if not agent_id:
            raise ValueError("agent_id is required for agent.heartbeat")
        success = registry_center.heartbeat(agent_id)
        if not success:
            raise ValueError(f"Agent not found: {agent_id}")
        cpu_load = params.get("cpu_load")
        memory_free = params.get("memory_free")
        if cpu_load is not None and memory_free is not None:
            registry_center.update_load(agent_id, float(cpu_load), float(memory_free))
        return {"status": "ok", "agent_id": agent_id, "timestamp": datetime.now(timezone.utc).isoformat()}


class A2AClient:
    def __init__(self, psk: Optional[str] = None):
        self._psk = psk or os.getenv("A2A_PSK", settings.secret_key)

    def _get_auth_token(self, agent_id: str = "agenthub-local") -> str:
        return _generate_agent_token(agent_id)

    async def call_remote(self, endpoint: str, method: str, params: dict, request_id: int = 1) -> JSONRPCResponse:
        request = JSONRPCRequest(method=method, params=params, id=request_id)
        token = self._get_auth_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    endpoint,
                    json=request.model_dump(),
                    headers=headers,
                )
                response.raise_for_status()
                return JSONRPCResponse(**response.json())
            except httpx.HTTPStatusError as e:
                logger.error(f"A2A call HTTP error: {e}")
                return JSONRPCResponse(
                    error={"code": -32000, "message": f"HTTP error: {e.response.status_code}"},
                    id=request_id,
                )
            except httpx.RequestError as e:
                logger.error(f"A2A call request error: {e}")
                return JSONRPCResponse(
                    error={"code": -32000, "message": f"Request error: {str(e)}"},
                    id=request_id,
                )

    async def discover(self, endpoint: str, capabilities: list = None, tags: dict = None) -> JSONRPCResponse:
        params = {}
        if capabilities:
            params["capabilities"] = capabilities
        if tags:
            params["tags"] = tags
        return await self.call_remote(endpoint, "agent.discover", params)

    async def call_agent(self, endpoint: str, agent_id: str, intent: dict) -> JSONRPCResponse:
        return await self.call_remote(endpoint, "agent.call", {"agent_id": agent_id, "intent": intent})

    async def check_status(self, endpoint: str, agent_id: str = None) -> JSONRPCResponse:
        params = {}
        if agent_id:
            params["agent_id"] = agent_id
        return await self.call_remote(endpoint, "agent.status", params)

    async def send_heartbeat(self, endpoint: str, agent_id: str, cpu_load: float = None, memory_free: float = None) -> JSONRPCResponse:
        params = {"agent_id": agent_id}
        if cpu_load is not None:
            params["cpu_load"] = cpu_load
        if memory_free is not None:
            params["memory_free"] = memory_free
        return await self.call_remote(endpoint, "agent.heartbeat", params)


a2a_server = A2AServer()
a2a_client = A2AClient()
