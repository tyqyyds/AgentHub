from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from ..database.connection import get_db_session
from ..database.models import MCPTool, MCPToolStatus, RemoteMCPServer, MCPServerStatus
from .deps import get_current_user

router = APIRouter()


class MCPToolCreate(BaseModel):
    tool_id: str
    name: str
    description: Optional[str] = None
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    endpoint_url: Optional[str] = None


class MCPToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    endpoint_url: Optional[str] = None


class MCPToolCallRequest(BaseModel):
    tool_id: str
    arguments: dict


@router.get("/")
async def list_mcp_tools(
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(MCPTool)
    if status:
        try:
            query = query.where(MCPTool.status == MCPToolStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    tools = result.scalars().all()
    return {"status": "success", "data": [{"id": t.id, "tool_id": t.tool_id, "name": t.name, "status": t.status.value} for t in tools]}


@router.get("/{tool_id}")
async def get_mcp_tool(
    tool_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(MCPTool).where(MCPTool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="MCP Tool not found")
    return {"status": "success", "data": {"id": tool.id, "tool_id": tool.tool_id, "name": tool.name, "description": tool.description, "input_schema": tool.input_schema, "output_schema": tool.output_schema, "endpoint_url": tool.endpoint_url, "status": tool.status.value}}


@router.post("/")
async def create_mcp_tool(
    req: MCPToolCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    tool = MCPTool(
        tool_id=req.tool_id, name=req.name, description=req.description,
        input_schema=req.input_schema, output_schema=req.output_schema, endpoint_url=req.endpoint_url,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return {"status": "success", "data": {"id": tool.id, "tool_id": tool.tool_id}}


@router.put("/{tool_id}")
async def update_mcp_tool(
    tool_id: int,
    req: MCPToolUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(MCPTool).where(MCPTool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="MCP Tool not found")
    if req.name is not None:
        tool.name = req.name
    if req.description is not None:
        tool.description = req.description
    if req.endpoint_url is not None:
        tool.endpoint_url = req.endpoint_url
    if req.status is not None:
        try:
            tool.status = MCPToolStatus(req.status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
    await db.commit()
    return {"status": "success"}


@router.delete("/{tool_id}")
async def delete_mcp_tool(
    tool_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(MCPTool).where(MCPTool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="MCP Tool not found")
    await db.delete(tool)
    await db.commit()
    return {"status": "success"}


@router.post("/call")
async def call_mcp_tool(
    req: MCPToolCallRequest,
    current_user=Depends(get_current_user),
):
    return {"status": "success", "data": {"tool_id": req.tool_id, "result": "Tool call placeholder - integrate with actual MCP runtime"}}


@router.get("/servers/")
async def list_mcp_servers(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(RemoteMCPServer))
    servers = result.scalars().all()
    return {"status": "success", "data": [{"id": s.id, "server_id": s.server_id, "name": s.name, "status": s.status.value, "endpoint_url": s.endpoint_url} for s in servers]}
