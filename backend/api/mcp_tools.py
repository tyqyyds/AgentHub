from fastapi import APIRouter, Query, Body, Depends, HTTPException
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field, field_validator
from backend.mcp.tools import (
    get_mcp_tools,
    search_tools,
    add_custom_tool,
    delete_custom_tool,
    check_name_available
)
from backend.mcp.executor import get_tool_executor
from backend.core.security.rbac import get_current_user, requires_permission
import logging
import uuid
import httpx
import json
import ipaddress
from urllib.parse import urlparse


class ToolConfigRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    category: str = Field(default="custom", max_length=50)
    args_schema: Dict[str, Any] = Field(default_factory=dict)
    endpoint: Optional[str] = Field(default=None, max_length=500)

logger = logging.getLogger(__name__)

router = APIRouter()

_remote_servers: Dict[str, Dict[str, Any]] = {}
_REMOTE_SERVERS_FILE = "data/remote_servers.json"
import os


def _load_remote_servers():
    global _remote_servers
    if os.path.exists(_REMOTE_SERVERS_FILE):
        try:
            with open(_REMOTE_SERVERS_FILE, "r") as f:
                _remote_servers = json.load(f)
        except Exception:
            _remote_servers = {}


def _validate_endpoint_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https protocols are allowed")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: no hostname")
    if hostname in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Localhost addresses are not allowed")
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Private/internal IP addresses are not allowed")
    except ValueError:
        if hostname == "localhost":
            raise ValueError("Localhost is not allowed")
    return url


def _save_remote_servers():
    os.makedirs(os.path.dirname(_REMOTE_SERVERS_FILE), exist_ok=True)
    with open(_REMOTE_SERVERS_FILE, "w") as f:
        json.dump(_remote_servers, f, indent=2)


_load_remote_servers()


class ToolExecuteRequest(BaseModel):
    tool_name: str
    params: Dict[str, Any] = {}

    @field_validator('params')
    @classmethod
    def validate_params_size(cls, v):
        if len(json.dumps(v)) > 10000:
            raise ValueError('params payload exceeds maximum allowed size')
        return v


class StandardExecuteRequest(BaseModel):
    tool: str
    params: Dict[str, Any] = {}

    @field_validator('params')
    @classmethod
    def validate_params_size(cls, v):
        if len(json.dumps(v)) > 10000:
            raise ValueError('params payload exceeds maximum allowed size')
        return v


class RemoteServerAddRequest(BaseModel):
    name: str
    endpoint: str
    description: str = ""

    @field_validator('endpoint')
    @classmethod
    def validate_endpoint(cls, v):
        _validate_endpoint_url(v)
        return v


@router.get("")
async def list_mcp_tools(
    q: str = Query(None, description="搜索关键词"),
    current_user=Depends(get_current_user)
):
    if q:
        tools = search_tools(q)
    else:
        tools = get_mcp_tools()

    tool_list = []
    for tool in tools:
        tool_info = {
            "name": tool["name"],
            "description": tool["description"],
            "args_schema": tool.get("args_schema", {}),
            "is_custom": tool.get("is_custom", False)
        }
        tool_list.append(tool_info)

    return {
        "status": "success",
        "data": tool_list
    }


@router.get("/describe")
async def describe_tools(current_user=Depends(get_current_user)):
    local_tools = get_mcp_tools()
    tools_schema = []
    for tool in local_tools:
        args_schema = tool.get("args_schema", {})
        properties = {}
        required = []
        for param_name, param_desc in args_schema.items():
            properties[param_name] = {
                "type": "string",
                "description": param_desc
            }
            required.append(param_name)

        input_schema = {
            "type": "object",
            "properties": properties,
            "required": required
        }

        tools_schema.append({
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": input_schema,
            "output_schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["success", "error"]},
                    "output": {"type": "array", "items": {"type": "string"}}
                }
            },
            "source": "local"
        })

    for server_id, server_info in _remote_servers.items():
        remote_tools = await _fetch_remote_tools(server_info["endpoint"])
        for rt in remote_tools:
            rt["source"] = "remote"
            rt["server_id"] = server_id
            tools_schema.append(rt)

    return {
        "status": "success",
        "data": {"tools": tools_schema}
    }


@router.post("/execute")
async def standard_execute_tool(
    request: StandardExecuteRequest,
    current_user=Depends(requires_permission("agents:manage"))
):
    local_tools = get_mcp_tools()
    local_tool_names = [t["name"] for t in local_tools]

    if request.tool in local_tool_names:
        executor = get_tool_executor()
        result = await executor.execute_tool(request.tool, request.params)
        return {"status": "success", "data": result}

    for server_id, server_info in _remote_servers.items():
        remote_tools = await _fetch_remote_tools(server_info["endpoint"])
        remote_tool_names = [t["name"] for t in remote_tools]
        if request.tool in remote_tool_names:
            result = await _execute_remote_tool(
                server_info["endpoint"], request.tool, request.params
            )
            return {"status": "success", "data": result}

    raise HTTPException(status_code=404, detail=f"Tool '{request.tool}' not found in local or remote tools")


@router.post("/remote")
async def add_remote_server(
    request: RemoteServerAddRequest,
    current_user=Depends(requires_permission("agents:manage"))
):
    server_id = str(uuid.uuid4())
    _remote_servers[server_id] = {
        "id": server_id,
        "name": request.name,
        "endpoint": request.endpoint,
        "description": request.description
    }
    _save_remote_servers()
    return {
        "status": "success",
        "data": {
            "id": server_id,
            "name": request.name,
            "endpoint": request.endpoint,
            "description": request.description
        }
    }


@router.delete("/remote/{server_id}")
async def remove_remote_server(
    server_id: str,
    current_user=Depends(requires_permission("agents:manage"))
):
    if server_id not in _remote_servers:
        raise HTTPException(status_code=404, detail=f"Remote server '{server_id}' not found")
    removed = _remote_servers.pop(server_id)
    _save_remote_servers()
    return {
        "status": "success",
        "data": {"removed": removed["name"], "id": server_id}
    }


@router.get("/remote")
async def list_remote_servers(current_user=Depends(get_current_user)):
    servers = list(_remote_servers.values())
    return {
        "status": "success",
        "data": servers
    }


@router.get("/check-name")
async def check_tool_name(
    name: str = Query(..., description="要检查的工具名称"),
    current_user=Depends(get_current_user)
):
    available = check_name_available(name)
    return {
        "status": "success",
        "available": available
    }


@router.get("/execution-history")
async def get_execution_history(
    tool_name: str = Query(None, description="按工具名过滤"),
    limit: int = Query(50, description="返回数量限制"),
    current_user=Depends(get_current_user)
):
    executor = get_tool_executor()
    history = executor.get_execution_history(tool_name=tool_name, limit=limit)
    return {"status": "success", "data": history, "total": len(history)}


@router.get("/{tool_name}")
async def get_tool_details(tool_name: str, current_user=Depends(get_current_user)):
    tools = get_mcp_tools()

    for tool in tools:
        if tool["name"] == tool_name:
            return {
                "status": "success",
                "data": tool
            }

    raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")


@router.post("/add")
async def add_tool(
    tool_config: ToolConfigRequest,
    current_user=Depends(requires_permission("agents:manage"))
):
    config_dict = tool_config.model_dump()
    success, error_msg = add_custom_tool(config_dict)

    if success:
        return {
            "status": "success",
            "message": "工具添加成功",
            "data": config_dict
        }
    else:
        raise HTTPException(status_code=400, detail=error_msg)


@router.delete("/delete/{tool_name}")
async def delete_tool(tool_name: str, current_user=Depends(requires_permission("agents:manage"))):
    success, error_msg = delete_custom_tool(tool_name)

    if success:
        return {
            "status": "success",
            "message": "工具删除成功"
        }
    else:
        raise HTTPException(status_code=400, detail=error_msg)


async def _fetch_remote_tools(endpoint: str) -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{endpoint.rstrip('/')}/tools")
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "tools" in data:
                    return data["tools"]
                if isinstance(data, dict) and "data" in data:
                    inner = data["data"]
                    if isinstance(inner, list):
                        return inner
                    if isinstance(inner, dict) and "tools" in inner:
                        return inner["tools"]
            return []
    except Exception as e:
        logger.error(f"Failed to fetch remote tools from {endpoint}: {e}")
        return []


async def _execute_remote_tool(
    endpoint: str, tool_name: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{endpoint.rstrip('/')}/execute",
                json={"tool": tool_name, "params": params}
            )
            if resp.status_code == 200:
                return resp.json()
            return {"status": "error", "error": f"Remote execution failed: HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "error": f"Remote execution error: {str(e)}"}


# --- Tool Reviews (in-memory, persisted via JSON file) ---
import os as _os

_REVIEWS_FILE = "data/tool_reviews.json"
_tool_reviews: Dict[str, List[Dict[str, Any]]] = {}


def _load_reviews():
    global _tool_reviews
    if _os.path.exists(_REVIEWS_FILE):
        try:
            with open(_REVIEWS_FILE, "r", encoding="utf-8") as f:
                _tool_reviews = json.load(f)
        except Exception:
            _tool_reviews = {}


def _save_reviews():
    _os.makedirs(_os.path.dirname(_REVIEWS_FILE), exist_ok=True)
    with open(_REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(_tool_reviews, f, ensure_ascii=False, indent=2)


_load_reviews()


class ReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(default="", max_length=500)


@router.get("/{tool_name}/reviews")
async def get_tool_reviews(tool_name: str, current_user=Depends(get_current_user)):
    reviews = _tool_reviews.get(tool_name, [])
    return {"status": "success", "data": reviews}


@router.post("/{tool_name}/reviews")
async def submit_tool_review(
    tool_name: str,
    request: ReviewRequest,
    current_user=Depends(get_current_user),
):
    if tool_name not in _tool_reviews:
        _tool_reviews[tool_name] = []
    review = {
        "id": f"review-{uuid.uuid4().hex[:8]}",
        "user": current_user.username if hasattr(current_user, "username") else "unknown",
        "rating": request.rating,
        "comment": request.comment,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }
    _tool_reviews[tool_name].append(review)
    _save_reviews()
    return {"status": "success", "data": review}
