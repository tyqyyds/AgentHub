from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, Boolean, Enum, Float, ForeignKey
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timezone
from enum import Enum as PyEnum


class Base(DeclarativeBase):
    pass


def _utcnow():
    return datetime.now(timezone.utc)


# ──────────────────────── 枚举定义 ────────────────────────


class ApprovalStatus(PyEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class HealingMode(PyEnum):
    AUTO = "auto"
    SUGGESTED = "suggested"
    ALERT_ONLY = "alert_only"


class UserRole(PyEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class IntentType(PyEnum):
    BANDWIDTH_GUARANTEE = "带宽保障"
    TRAFFIC_SCHEDULING = "流量调度"
    SELF_HEALING = "故障自愈"
    SECURITY_POLICY = "安全策略"
    QOS_OPTIMIZATION = "QoS优化"
    LINK_PROTECTION = "链路保护"
    LOAD_BALANCE = "负载均衡"
    ACCESS_CONTROL = "访问控制"
    ROUTE_OPTIMIZATION = "路由优化"


class ExecutionStatus(PyEnum):
    PENDING = "pending"
    CONFLICT_DETECTED = "conflict_detected"
    POLICY_GENERATED = "policy_generated"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class DeviceVendor(PyEnum):
    HUAWEI = "华为"
    ZTE = "中兴"
    H3C = "新华三"
    RUIJIE = "锐捷"
    OTHER = "其他"


class DeviceType(PyEnum):
    ROUTER = "路由器"
    SWITCH = "交换机"
    FIREWALL = "防火墙"
    LOAD_BALANCER = "负载均衡"
    OPTICAL_TRANSPORT = "光传输"
    WIRELESS_AC = "无线AC"


class DeviceStatus(PyEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class LinkType(PyEnum):
    FIBER = "光纤"
    COPPER = "铜缆"
    WIRELESS = "无线"


class LinkStatus(PyEnum):
    UP = "up"
    DOWN = "down"


class WorkOrderPriority(PyEnum):
    URGENT = "紧急"
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class WorkOrderStatus(PyEnum):
    PENDING = "待处理"
    IN_PROGRESS = "处理中"
    COMPLETED = "已完成"
    CLOSED = "已关闭"


class AnomalySeverity(PyEnum):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"
    CRITICAL = "紧急"


class RiskLevel(PyEnum):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"
    VERY_HIGH = "极高"


class NotificationPriority(PyEnum):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"
    URGENT = "紧急"


class PlaybookExecutionStatus(PyEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GrayscalePhase(PyEnum):
    CANARY = "canary"
    BATCH = "batch"
    ROLLBACK = "rollback"


class HealingEvaluationType(PyEnum):
    PRE = "pre"
    POST = "post"


class DependencyType(PyEnum):
    BLOCKS = "blocks"
    RELATES_TO = "relates_to"


class MCPToolStatus(PyEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class IntentTemplateType(PyEnum):
    BANDWIDTH_GUARANTEE = "带宽保障"
    TRAFFIC_SCHEDULING = "流量调度"
    SELF_HEALING = "故障自愈"
    SECURITY_POLICY = "安全策略"
    QOS_OPTIMIZATION = "QoS优化"
    LINK_PROTECTION = "链路保护"
    LOAD_BALANCE = "负载均衡"
    ACCESS_CONTROL = "访问控制"
    ROUTE_OPTIMIZATION = "路由优化"


class GrayscaleTaskStatus(PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class MCPServerStatus(PyEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class FailureStage(PyEnum):
    PARSING = "解析"
    CONFLICT_DETECTION = "冲突检测"
    POLICY_GENERATION = "策略生成"
    APPROVAL = "审批"
    EXECUTION = "执行"


class RecurrenceType(PyEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class AgentHealthStatus(PyEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class LLMProvider(PyEnum):
    DEEPSEEK = "deepseek"
    ZHIPU = "zhipu"


# ──────────────────────── 数据模型 ────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.VIEWER)
    is_active = Column(Boolean, default=True)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class Intent(Base):
    __tablename__ = "intents"

    id = Column(Integer, primary_key=True, index=True)
    intent_name = Column(String, nullable=False)
    user_input = Column(Text, nullable=False)
    structured_params = Column(JSON, nullable=False)
    intent_type = Column(Enum(IntentType), nullable=True)
    execution_status = Column(Enum(ExecutionStatus), default=ExecutionStatus.PENDING)
    conflict_result = Column(JSON, nullable=True)
    generated_policy = Column(JSON, nullable=True)
    sla_conditions = Column(JSON, nullable=True)
    device_scope = Column(JSON, nullable=True)
    approval_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    prompt_tokens_usage = Column(Integer)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class SelfHealingEvent(Base):
    __tablename__ = "self_healing_events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    suggested_action = Column(Text)
    healing_mode = Column(Enum(HealingMode), default=HealingMode.SUGGESTED)
    requires_approval = Column(Boolean, default=True)
    status = Column(String, default="pending")
    target_device = Column(String)
    executed_by = Column(String)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class PolicyTemplate(Base):
    __tablename__ = "policy_templates"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(String, unique=True, nullable=False)
    vendor = Column(String, nullable=False)
    device_type = Column(String, nullable=False)
    function = Column(String, nullable=False)
    template_content = Column(Text, nullable=False)
    parameters_schema = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


class AgentRegistry(Base):
    __tablename__ = "agent_registry"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String, unique=True, nullable=False)
    domain = Column(String, nullable=False)
    ip = Column(String)
    a2a_endpoint = Column(String, nullable=False)
    capabilities = Column(JSON)
    status = Column(String, default="online")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    target_device = Column(String)
    commands = Column(JSON)
    timestamp = Column(DateTime, default=_utcnow)
    approval_id = Column(String)
    status = Column(String, default="success")


# ──────────────────────── 新增模型 ────────────────────────


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    vendor = Column(Enum(DeviceVendor), nullable=False)
    device_type = Column(Enum(DeviceType), nullable=False)
    status = Column(Enum(DeviceStatus), default=DeviceStatus.ONLINE)
    location = Column(String, nullable=True)
    snmp_community = Column(String, nullable=True)
    ssh_port = Column(Integer, default=22)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class DeviceLink(Base):
    __tablename__ = "device_links"

    id = Column(Integer, primary_key=True, index=True)
    source_device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    target_device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    link_type = Column(Enum(LinkType), nullable=False)
    bandwidth = Column(String, nullable=True)
    status = Column(Enum(LinkStatus), default=LinkStatus.UP)
    latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class MCPTool(Base):
    __tablename__ = "mcp_tools"

    id = Column(Integer, primary_key=True, index=True)
    tool_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    input_schema = Column(JSON, nullable=True)
    output_schema = Column(JSON, nullable=True)
    endpoint_url = Column(String, nullable=True)
    status = Column(Enum(MCPToolStatus), default=MCPToolStatus.ACTIVE)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class IntentTemplate(Base):
    __tablename__ = "intent_templates"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(String, unique=True, nullable=False)
    intent_type = Column(Enum(IntentTemplateType), nullable=False)
    description = Column(Text, nullable=True)
    param_schema = Column(JSON, nullable=True)
    example_utterances = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class SLAEvaluationResult(Base):
    __tablename__ = "sla_evaluation_results"

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(Integer, ForeignKey("intents.id"), nullable=False)
    metric_name = Column(String, nullable=False)
    target_value = Column(Float, nullable=False)
    actual_value = Column(Float, nullable=False)
    unit = Column(String, nullable=True)
    compliance = Column(Boolean, nullable=False)
    evaluated_at = Column(DateTime, default=_utcnow)


class SLAPrediction(Base):
    __tablename__ = "sla_predictions"

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(Integer, ForeignKey("intents.id"), nullable=False)
    predicted_metric = Column(String, nullable=False)
    predicted_value = Column(Float, nullable=False)
    confidence = Column(Float, nullable=True)
    prediction_horizon_hours = Column(Integer, nullable=True)
    model_version = Column(String, nullable=True)
    predicted_at = Column(DateTime, default=_utcnow)


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    intent_id = Column(Integer, ForeignKey("intents.id"), nullable=True)
    assigned_to = Column(String, nullable=True)
    priority = Column(Enum(WorkOrderPriority), default=WorkOrderPriority.MEDIUM)
    status = Column(Enum(WorkOrderStatus), default=WorkOrderStatus.PENDING)
    sla_deadline = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    closed_at = Column(DateTime, nullable=True)


class Playbook(Base):
    __tablename__ = "playbooks"

    id = Column(Integer, primary_key=True, index=True)
    playbook_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    steps = Column(JSON, nullable=False)
    trigger_condition = Column(JSON, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class PlaybookExecution(Base):
    __tablename__ = "playbook_executions"

    id = Column(Integer, primary_key=True, index=True)
    playbook_id = Column(Integer, ForeignKey("playbooks.id"), nullable=False)
    triggered_by = Column(String, nullable=True)
    status = Column(Enum(PlaybookExecutionStatus), default=PlaybookExecutionStatus.RUNNING)
    result = Column(JSON, nullable=True)
    started_at = Column(DateTime, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)


class TraceSpan(Base):
    __tablename__ = "trace_spans"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String, nullable=False, index=True)
    span_id = Column(String, nullable=False)
    parent_span_id = Column(String, nullable=True)
    operation_name = Column(String, nullable=False)
    service_name = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    status_code = Column(String, nullable=True)
    attributes = Column(JSON, nullable=True)


class AgentHealthRecord(Base):
    __tablename__ = "agent_health_records"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String, nullable=False, index=True)
    health_status = Column(Enum(AgentHealthStatus), nullable=False)
    cpu_usage = Column(Float, nullable=True)
    memory_usage = Column(Float, nullable=True)
    last_heartbeat = Column(DateTime, nullable=True)
    checked_at = Column(DateTime, default=_utcnow)


class FailedIntentCase(Base):
    __tablename__ = "failed_intent_cases"

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(Integer, ForeignKey("intents.id"), nullable=False)
    failure_reason = Column(Text, nullable=True)
    failure_stage = Column(Enum(FailureStage), nullable=False)
    root_cause = Column(Text, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class IntentScheduleRecord(Base):
    __tablename__ = "intent_schedule_records"

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(Integer, ForeignKey("intents.id"), nullable=False)
    scheduled_time = Column(DateTime, nullable=False)
    recurrence = Column(Enum(RecurrenceType), default=RecurrenceType.ONCE)
    is_active = Column(Boolean, default=True)
    last_executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class GrayscaleHealingTask(Base):
    __tablename__ = "grayscale_healing_tasks"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("self_healing_events.id"), nullable=False)
    phase = Column(Enum(GrayscalePhase), nullable=False)
    target_devices = Column(JSON, nullable=True)
    canary_result = Column(JSON, nullable=True)
    batch_result = Column(JSON, nullable=True)
    status = Column(Enum(GrayscaleTaskStatus), default=GrayscaleTaskStatus.PENDING)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class HealingEvaluation(Base):
    __tablename__ = "healing_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("self_healing_events.id"), nullable=False)
    evaluation_type = Column(Enum(HealingEvaluationType), nullable=False)
    metrics_before = Column(JSON, nullable=True)
    metrics_after = Column(JSON, nullable=True)
    success = Column(Boolean, nullable=False)
    evaluation_notes = Column(Text, nullable=True)
    evaluated_at = Column(DateTime, default=_utcnow)


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False)
    callback_url = Column(String, nullable=False)
    secret = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class BehaviorAnomaly(Base):
    __tablename__ = "behavior_anomalies"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    anomaly_type = Column(String, nullable=False)
    severity = Column(Enum(AnomalySeverity), nullable=False)
    description = Column(Text, nullable=True)
    detected_at = Column(DateTime, default=_utcnow)
    resolved = Column(Boolean, default=False)


class ChangeImpactAnalysis(Base):
    __tablename__ = "change_impact_analyses"

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(Integer, ForeignKey("intents.id"), nullable=False)
    affected_devices = Column(JSON, nullable=True)
    risk_level = Column(Enum(RiskLevel), nullable=False)
    impact_score = Column(Float, nullable=True)
    analysis_result = Column(JSON, nullable=True)
    analyzed_at = Column(DateTime, default=_utcnow)


class ExecutionPlan(Base):
    __tablename__ = "execution_plans"

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(Integer, ForeignKey("intents.id"), nullable=False)
    plan_steps = Column(JSON, nullable=False)
    estimated_duration_minutes = Column(Integer, nullable=True)
    requires_approval = Column(Boolean, default=True)
    approval_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    created_at = Column(DateTime, default=_utcnow)


class WizardSession(Base):
    __tablename__ = "wizard_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, nullable=False)
    wizard_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class KnowledgeDocumentVersion(Base):
    __tablename__ = "knowledge_document_versions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class QuickCommand(Base):
    __tablename__ = "quick_commands"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    command_template = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String, nullable=True)
    parameters_schema = Column(JSON, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class ProactiveNotification(Base):
    __tablename__ = "proactive_notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notification_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    priority = Column(Enum(NotificationPriority), default=NotificationPriority.MEDIUM)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)


class RemoteMCPServer(Base):
    __tablename__ = "remote_mcp_servers"

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    endpoint_url = Column(String, nullable=False)
    api_key = Column(String, nullable=True)
    status = Column(Enum(MCPServerStatus), default=MCPServerStatus.DISCONNECTED)
    capabilities = Column(JSON, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class WorkOrderSLA(Base):
    __tablename__ = "work_order_slas"

    id = Column(Integer, primary_key=True, index=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=False)
    response_deadline = Column(DateTime, nullable=False)
    resolution_deadline = Column(DateTime, nullable=False)
    actual_response_at = Column(DateTime, nullable=True)
    actual_resolution_at = Column(DateTime, nullable=True)
    is_breached = Column(Boolean, default=False)


class WorkOrderDependency(Base):
    __tablename__ = "work_order_dependencies"

    id = Column(Integer, primary_key=True, index=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=False)
    depends_on_id = Column(Integer, ForeignKey("work_orders.id"), nullable=False)
    dependency_type = Column(Enum(DependencyType), nullable=False)


class WorkOrderAutomationRule(Base):
    __tablename__ = "work_order_automation_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_name = Column(String, nullable=False)
    trigger_condition = Column(JSON, nullable=False)
    action = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)


class AgentCapabilityScore(Base):
    __tablename__ = "agent_capability_scores"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agent_registry.id"), nullable=False)
    capability_name = Column(String, nullable=False)
    score = Column(Float, nullable=False)
    evaluated_at = Column(DateTime, default=_utcnow)


class LLMRouterConfig(Base):
    __tablename__ = "llm_router_configs"

    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String, nullable=False)
    primary_provider = Column(Enum(LLMProvider), nullable=False)
    fallback_provider = Column(Enum(LLMProvider), nullable=True)
    primary_model = Column(String, nullable=False)
    fallback_model = Column(String, nullable=True)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2048)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
