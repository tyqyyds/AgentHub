from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from functools import lru_cache
from backend.agents.base import AgentMetadata, ToolDescription, IntentContext, NetworkState, DeviceInfo
from backend.core.security.rbac import get_current_user, requires_permission, User
from backend.database.connection import get_db_session
from backend.database.models import Device
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2")

@lru_cache(maxsize=1)
def get_workflow():
    from backend.agents.workflow import IntentWorkflow
    return IntentWorkflow()

@lru_cache(maxsize=1)
def get_agent_registry():
    from backend.agents.registry import AgentRegistry
    return AgentRegistry()

@lru_cache(maxsize=1)
def get_a2a_bus():
    from backend.agents.a2a_bus import A2ABus
    return A2ABus()

@lru_cache(maxsize=1)
def get_mcp_registry():
    from backend.agents.mcp_registry import MCPRegistry
    return MCPRegistry()

@lru_cache(maxsize=1)
def get_semantic_router():
    from backend.agents.mcp_registry import MCPToolRouter
    return MCPToolRouter(get_mcp_registry(), get_a2a_bus())

@lru_cache(maxsize=1)
def get_orchestrator():
    from backend.agents.orchestrator import MultiAgentOrchestrator
    return MultiAgentOrchestrator(get_agent_registry(), get_a2a_bus())

@lru_cache(maxsize=1)
def get_security_sandbox():
    from backend.agents.security import SecuritySandbox
    return SecuritySandbox()

@lru_cache(maxsize=1)
def get_gateway():
    from backend.agents.llm_gateway import get_llm_gateway
    return get_llm_gateway()

class IntentRequest(BaseModel):
    user_input: str
    context: Optional[Dict[str, Any]] = None

class AgentRegistrationRequest(BaseModel):
    agent_id: str
    agent_type: str
    name: str
    description: str
    capabilities: List[str]
    endpoint: Optional[str] = None

class ToolRegistrationRequest(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    supported_devices: List[str]
    requires_context: bool = False

class TicketCreateRequest(BaseModel):
    title: str
    description: str
    mode: str
    subtasks: List[Dict[str, Any]]
    requires_approval: bool = False

class SecurityScanRequest(BaseModel):
    content: str
    scan_type: str = "command"

class A2AMessageRequest(BaseModel):
    topic: str = "general"
    content: Dict[str, Any] = Field(default_factory=dict)
    sender_id: str = "api"

class CopilotQuickActionRequest(BaseModel):
    type: str = ""
    action: str = ""

class ApprovalRequest(BaseModel):
    ticket_id: str
    action: str
    reason: Optional[str] = None

@router.post("/intents/execute")
async def execute_intent(request: IntentRequest, user: User = Depends(get_current_user)):
    try:
        sandbox = get_security_sandbox()
        scan_result = sandbox.scan_natural_language(request.user_input)
        
        if not scan_result.is_safe:
            raise HTTPException(
                status_code=403,
                detail={
                    "status": "blocked",
                    "reason": "安全检测拦截",
                    "threat_level": scan_result.threat_level.value if hasattr(scan_result.threat_level, 'value') else str(scan_result.threat_level),
                    "threats": scan_result.threats
                }
            )
        
        workflow = get_workflow()
        
        network_state = NetworkState(devices=[], qos_policies=[])
        try:
            async for db in get_db_session():
                devices_result = await db.execute(Device.__table__.select())
                device_rows = devices_result.fetchall()
                devices = []
                for row in device_rows:
                    row_data = dict(row._mapping)
                    devices.append(DeviceInfo(
                        name=row_data.get("name", ""),
                        ip=row_data.get("ip_address", ""),
                        type=row_data.get("device_type", ""),
                        status=row_data.get("status", "healthy")
                    ))
                network_state = NetworkState(devices=devices, qos_policies=[])
                break
        except Exception as e:
            logger.warning(f"Failed to load network state from DB: {e}, using empty state")
        
        result = await workflow.run(request.user_input, network_state)
        
        intent_context = result.get("intent_context")
        intent_id = "unknown"
        if isinstance(intent_context, IntentContext):
            intent_id = intent_context.intent_id
        elif isinstance(intent_context, dict):
            intent_id = intent_context.get("intent_id", "unknown")
        
        return {
            "intent_id": intent_id,
            "user_input": request.user_input,
            "status": "completed",
            "current_step": result.get("current_step", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"V2 intent execute failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"status": "error", "message": "处理请求失败，请稍后重试"})

@router.post("/agents/register")
async def register_agent(request: AgentRegistrationRequest, current_user=Depends(requires_permission("agents:manage"))):
    from backend.agents.registry import AgentRegistryError
    registry = get_agent_registry()
    bus = get_a2a_bus()
    
    metadata = AgentMetadata(
        agent_id=request.agent_id,
        agent_type=request.agent_type,
        name=request.name,
        description=request.description,
        capabilities=request.capabilities,
        endpoint=request.endpoint,
        status="online"
    )
    
    try:
        registry.register_agent(metadata)
    except AgentRegistryError:
        raise HTTPException(status_code=409, detail="Agent 注册冲突，该 ID 可能已存在")
    bus.publish("agent_registered", {"agent_id": request.agent_id, "agent_type": request.agent_type})
    
    return {"status": "success", "message": f"Agent {request.agent_id} 注册成功"}

@router.delete("/agents/{agent_id}")
async def unregister_agent(agent_id: str, current_user=Depends(requires_permission("agents:manage"))):
    from backend.agents.registry import AgentRegistryError
    registry = get_agent_registry()
    try:
        registry.unregister_agent(agent_id)
    except AgentRegistryError:
        raise HTTPException(status_code=404, detail="Agent 不存在或已注销")
    return {"status": "success", "message": f"Agent {agent_id} 注销成功"}

@router.get("/agents")
async def list_agents(current_user=Depends(get_current_user)):
    registry = get_agent_registry()
    agents = registry.list_agents()
    return {"agents": [a.model_dump() for a in agents]}

@router.get("/agents/discover")
async def discover_agents(capability: Optional[str] = None, query: Optional[str] = None, current_user=Depends(get_current_user)):
    registry = get_agent_registry()
    if capability:
        agents = registry.discover_by_capability(capability)
        return {"agents": [a.model_dump() for a in agents]}
    if query:
        results = registry.semantic_discover(query)
        return results
    return {"agents": [a.model_dump() for a in registry.list_agents()]}

@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, current_user=Depends(get_current_user)):
    registry = get_agent_registry()
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} 不存在")
    return agent.model_dump()

@router.post("/mcp/tools")
async def register_tool(request: ToolRegistrationRequest, current_user=Depends(requires_permission("agents:manage"))):
    mcp = get_mcp_registry()
    tool = ToolDescription(
        name=request.name, description=request.description,
        input_schema=request.input_schema, output_schema=request.output_schema,
        supported_devices=request.supported_devices, requires_context=request.requires_context
    )
    mcp.register_tool(tool)
    return {"status": "success", "message": f"工具 {request.name} 注册成功"}

@router.delete("/mcp/tools/{tool_name}")
async def unregister_tool(tool_name: str, current_user=Depends(requires_permission("agents:manage"))):
    mcp = get_mcp_registry()
    success = mcp.unregister_tool(tool_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"工具 {tool_name} 不存在")
    return {"status": "success", "message": f"工具 {tool_name} 注销成功"}

@router.get("/mcp/tools")
async def list_tools(current_user=Depends(get_current_user)):
    mcp = get_mcp_registry()
    tools = mcp.list_tools()
    return {"tools": [t.model_dump() for t in tools]}

@router.get("/mcp/tools/search")
async def search_tools(query: str, current_user=Depends(get_current_user)):
    mcp = get_mcp_registry()
    results = mcp.semantic_search(query)
    return results

@router.post("/mcp/route")
async def route_tool(request: IntentRequest, current_user=Depends(get_current_user)):
    router_ = get_semantic_router()
    result = router_.route({
        "intent_type": request.context.get("intent_type") if request.context else None,
        "user_input": request.user_input
    }, request.context)
    return result

@router.post("/tickets")
async def create_ticket(request: TicketCreateRequest, current_user=Depends(requires_permission("system:manage"))):
    from backend.agents.orchestrator import CollaborationMode
    orchestrator = get_orchestrator()
    
    mode_map = {
        "supervisor": CollaborationMode.SUPERVISOR,
        "parallel": CollaborationMode.PARALLEL,
        "debate": CollaborationMode.DEBATE
    }
    mode = mode_map.get(request.mode, CollaborationMode.SUPERVISOR)
    
    ticket = orchestrator.create_ticket(
        title=request.title,
        description=request.description,
        mode=mode,
        subtask_defs=request.subtasks,
        requires_approval=request.requires_approval
    )
    
    return {
        "status": "created",
        "ticket_id": ticket.ticket_id,
        "mode": request.mode,
        "subtask_count": len(ticket.subtasks),
        "requires_approval": ticket.requires_approval
    }

@router.post("/tickets/{ticket_id}/execute")
async def execute_ticket(ticket_id: str, current_user=Depends(requires_permission("system:manage"))):
    orchestrator = get_orchestrator()
    result = await orchestrator.execute_ticket(ticket_id)
    return result

@router.post("/tickets/{ticket_id}/approve")
async def approve_ticket(ticket_id: str, request: ApprovalRequest, current_user=Depends(get_current_user)):
    orchestrator = get_orchestrator()
    if request.action == "approve":
        result = orchestrator.approve_ticket(ticket_id)
    else:
        result = orchestrator.reject_ticket(ticket_id, request.reason or "")
    return result

@router.get("/tickets")
async def list_tickets(status: Optional[str] = None, current_user=Depends(get_current_user)):
    orchestrator = get_orchestrator()
    return {"tickets": orchestrator.list_tickets(status)}

@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, current_user=Depends(get_current_user)):
    orchestrator = get_orchestrator()
    result = orchestrator.get_ticket(ticket_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"工单 {ticket_id} 不存在")
    return result

@router.post("/security/scan")
async def security_scan(request: SecurityScanRequest, current_user=Depends(get_current_user)):
    sandbox = get_security_sandbox()
    
    if request.scan_type == "command":
        commands = request.content.strip().split("\n")
        result = sandbox.scan_commands(commands)
    else:
        result = sandbox.scan_natural_language(request.content)
    
    return {
        "is_safe": result.is_safe,
        "threat_level": result.threat_level.value,
        "threats": result.threats,
        "sanitized_commands": result.sanitized_commands,
        "scan_time": result.scan_time
    }

@router.post("/a2a/message")
async def send_a2a_message(request: A2AMessageRequest, current_user=Depends(requires_permission("agents:manage"))):
    bus = get_a2a_bus()
    message_id = bus.publish(
        request.topic,
        request.content,
        request.sender_id
    )
    return {"status": "success", "message_id": message_id}

@router.get("/a2a/history")
async def get_a2a_history(limit: int = 100, current_user=Depends(get_current_user)):
    bus = get_a2a_bus()
    history = bus.get_history(limit)
    return {"messages": [m.model_dump() for m in history]}

@router.get("/a2a/stats")
async def get_a2a_stats(current_user=Depends(get_current_user)):
    bus = get_a2a_bus()
    stats = bus.get_topic_stats()
    return stats

class CopilotChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = None
    context: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = "default"


def _copilot_fallback_response(user_message: str) -> str:
    import re
    msg = user_message.lower()
    if any(kw in msg for kw in ['带宽', '扩容', '保障']):
        return "我理解您需要处理带宽相关的需求。您可以通过意图中心创建带宽扩容意图，系统将自动进行安全校验和冲突检测后执行。需要我帮您创建一个带宽保障意图吗？"
    if any(kw in msg for kw in ['故障', '诊断', '排查', '异常']):
        return "检测到您在排查故障。建议您：1) 在网络拓扑页面查看设备状态；2) 使用故障自愈模块让AI自动诊断；3) 查看可观测性模块的链路追踪定位问题根因。需要我帮您执行哪项操作？"
    if any(kw in msg for kw in ['健康', '状态', '监控']):
        return "系统当前运行正常。您可以在可观测性模块查看详细的Agent健康状态和系统指标，或在指挥舱查看全局概览。需要我为您展示具体数据吗？"
    if any(kw in msg for kw in ['意图', '创建', '提交']):
        return "您可以在意图中心通过自然语言描述需求来创建意图。系统支持带宽保障、故障诊断、性能监控、QoS策略等多种意图类型。创建后会自动进行安全校验和审批流程。"
    if any(kw in msg for kw in ['剧本', '自动化', '编排']):
        return "运维剧本模块支持多步骤自动化编排，包含意图执行、MCP工具调用、审批、通知等步骤类型。您可以在剧本管理页面创建或执行剧本。"
    return f"收到您的消息：「{user_message}」。我是智维AgentHub智能副驾，可以帮您处理网络运维相关任务，包括意图创建、故障诊断、带宽管理、自愈操作等。请告诉我您需要什么帮助？"

class DeepSeekParseRequest(BaseModel):
    user_input: str

@router.post("/copilot/chat")
async def copilot_chat(request: CopilotChatRequest, current_user=Depends(get_current_user)):
    gateway = get_gateway()
    try:
        result = await gateway.copilot_chat(
            user_message=request.message,
            session_id=request.session_id or "default",
            conversation_history=request.conversation_history,
            context=request.context
        )
        return {
            "status": "success",
            "response": result["content"],
            "provider": result["provider"],
            "model": result.get("model", "")
        }
    except Exception as e:
        logger.error(f"Copilot chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/copilot/chat/stream")
async def copilot_chat_stream(request: CopilotChatRequest, current_user=Depends(get_current_user)):
    gateway = get_gateway()

    async def generate():
        try:
            has_content = False
            async for chunk in gateway.copilot_chat_stream(
                user_message=request.message,
                session_id=request.session_id or "default",
                conversation_history=request.conversation_history,
                context=request.context
            ):
                if "error" in chunk:
                    fallback_msg = _copilot_fallback_response(request.message)
                    yield f"data: {json.dumps({'content': fallback_msg, 'provider': 'fallback'}, ensure_ascii=False)}\n\n"
                    has_content = True
                    break
                else:
                    yield f"data: {json.dumps({'content': chunk['content'], 'provider': chunk.get('provider', '')}, ensure_ascii=False)}\n\n"
                    has_content = True
            if not has_content:
                fallback_msg = _copilot_fallback_response(request.message)
                yield f"data: {json.dumps({'content': fallback_msg, 'provider': 'fallback'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Copilot chat stream failed: {e}", exc_info=True)
            fallback_msg = _copilot_fallback_response(request.message)
            yield f"data: {json.dumps({'content': fallback_msg, 'provider': 'fallback'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@router.post("/deepseek/parse")
async def deepseek_parse_intent(request: DeepSeekParseRequest, current_user=Depends(get_current_user)):
    gateway = get_gateway()
    try:
        parsed = await gateway.parse_intent(request.user_input)
        return {
            "status": "success",
            "parsed": parsed,
            "model": parsed.get("_model", ""),
            "provider": parsed.get("_provider", "")
        }
    except Exception as e:
        logger.error(f"Deepseek parse intent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/deepseek/status", deprecated=True)
async def deepseek_status(current_user=Depends(get_current_user)):
    gateway = get_gateway()
    from starlette.responses import JSONResponse
    result = gateway.get_status()
    response = JSONResponse(content=result)
    response.headers["X-Deprecated-Endpoint"] = "/api/v1/knowledge/llm-status"
    response.headers["Deprecation"] = "true"
    return response

@router.get("/copilot/suggestions")
async def copilot_suggestions(context: Optional[str] = None, current_user=Depends(get_current_user)):
    from backend.core.config import settings

    suggestions = []

    for device in settings.network_env["devices"]:
        if device["status"] == "warning":
            suggestions.append({
                "type": "warning",
                "icon": "⚠️",
                "title": f"{device['name']} 状态异常",
                "description": f"设备 {device['name']} ({device['ip']}) 当前状态为 warning，建议检查",
                "action": f"诊断 {device['name']} 的故障原因",
                "priority": "high"
            })

    for policy in settings.network_env["active_policies"]:
        if policy["type"] == "acl" and policy.get("action") == "deny":
            suggestions.append({
                "type": "info",
                "icon": "🔒",
                "title": f"{policy['source']} → {policy['dest']} 访问受限",
                "description": f"当前ACL策略禁止 {policy['source']} 访问 {policy['dest']}",
                "action": f"开放 {policy['source']} 到 {policy['dest']} 的访问",
                "priority": "medium"
            })

    suggestions.append({
        "type": "tip",
        "icon": "💡",
        "title": "网络健康检查",
        "description": "定期检查网络设备状态和链路质量",
        "action": "执行全网健康检查",
        "priority": "low"
    })

    return {"suggestions": suggestions}

@router.post("/copilot/quick-action")
async def copilot_quick_action(request: CopilotQuickActionRequest, current_user=Depends(get_current_user)):
    gateway = get_gateway()
    action_type = request.type
    action_text = request.action

    if action_text:
        try:
            parsed = await gateway.parse_intent(action_text)
            return {
                "status": "success",
                "action_type": action_type,
                "parsed_intent": parsed,
                "original_text": action_text,
                "provider": parsed.get("_provider", "")
            }
        except Exception as e:
            logger.error(f"Copilot quick action failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    return {"status": "success", "action_type": action_type, "original_text": action_text}

@router.get("/copilot/status")
async def copilot_status(current_user=Depends(get_current_user)):
    gateway = get_gateway()
    return gateway.get_status()

class MCPToolCallRequest(BaseModel):
    tool_name: str
    params: Dict[str, Any] = {}

@router.post("/copilot/mcp-call")
async def copilot_mcp_call(request: MCPToolCallRequest, current_user=Depends(get_current_user)):
    gateway = get_gateway()
    return await gateway.execute_mcp_tool(request.tool_name, request.params)

class CopilotTicketRequest(BaseModel):
    title: str
    description: str
    intent_data: Optional[Dict[str, Any]] = None

@router.post("/copilot/create-ticket")
async def copilot_create_ticket(request: CopilotTicketRequest, current_user=Depends(get_current_user)):
    gateway = get_gateway()
    return await gateway.create_copilot_ticket(
        title=request.title,
        description=request.description,
        intent_data=request.intent_data
    )

@router.get("/copilot/system-context")
async def copilot_system_context(current_user=Depends(get_current_user)):
    gateway = get_gateway()
    return await gateway.get_system_context()
