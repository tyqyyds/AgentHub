from typing import TypedDict, List, Optional, Dict, Any
from pydantic import BaseModel

class DeviceInfo(BaseModel):
    name: str
    ip: str
    type: str
    status: str
    neighbors: List[str] = []

class NetworkState(BaseModel):
    devices: List[DeviceInfo] = []
    links: List[Dict[str, Any]] = []
    qos_policies: List[Dict[str, Any]] = []

class IntentContext(BaseModel):
    intent_id: str
    user_input: str
    parsed_intent: Optional[Dict[str, Any]] = None
    target_devices: List[str] = []
    actions: List[Dict[str, Any]] = []
    conflict_detected: bool = False
    conflict_details: Optional[str] = None

class ExecutionResult(BaseModel):
    status: str
    device: str
    command: str
    output: Optional[str] = None
    error: Optional[str] = None
    timestamp: Optional[str] = None

class TelemetryData(BaseModel):
    device: str
    metric_type: str
    value: float
    timestamp: str

class AgentState(TypedDict):
    messages: List[Any]
    intent_context: IntentContext
    network_state: NetworkState
    execution_results: List[ExecutionResult]
    telemetry_data: List[TelemetryData]
    current_step: str
    next_steps: List[str]
    is_completed: bool
    error: Optional[str]
    reconstruct_count: int

class AgentMetadata(BaseModel):
    agent_id: str
    agent_type: str
    name: str
    description: str
    capabilities: List[str]
    status: str
    last_heartbeat: Optional[str] = None
    endpoint: Optional[str] = None

class A2AMessage(BaseModel):
    message_id: str
    sender_id: str
    receiver_id: Optional[str]
    message_type: str
    content: Dict[str, Any]
    timestamp: str
    reply_to: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ToolDescription(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    supported_devices: List[str]
    requires_context: bool = False

class OrchestratorState(BaseModel):
    workflow_id: str
    tasks: List[Dict[str, Any]]
    status: str
    created_at: str
    completed_at: Optional[str]

class AuditEvent(BaseModel):
    event_id: str
    action: str
    actor: str
    target: Optional[str]
    timestamp: str
    status: str
    details: Optional[Dict[str, Any]]
    trace_id: str
