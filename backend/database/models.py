from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, Boolean, Float, Index
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timezone


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="viewer")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, nullable=True)


class Intent(Base):
    __tablename__ = "intents"
    __table_args__ = (
        Index("ix_intents_approval_status", "approval_status"),
        Index("ix_intents_execution_status", "execution_status"),
        Index("ix_intents_sla_status", "sla_status"),
        Index("ix_intents_created_at", "created_at"),
        Index("ix_intents_intent_name", "intent_name"),
        Index("ix_intents_exec_sla", "execution_status", "sla_conditions"),
    )

    id = Column(Integer, primary_key=True, index=True)
    intent_name = Column(String, nullable=False)
    user_input = Column(Text, nullable=False)
    structured_params = Column(JSON, nullable=False)
    approval_status = Column(String, default="pending")
    execution_status = Column(String, default="not_started")
    execution_result = Column(JSON, nullable=True)
    conflict_detected = Column(Boolean, default=False)
    conflict_details = Column(Text, nullable=True)
    prompt_tokens_usage = Column(Integer)
    sla_conditions = Column(JSON, nullable=True)
    sla_status = Column(String, default="UNKNOWN")
    last_evaluation_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SelfHealingEvent(Base):
    __tablename__ = "self_healing_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    suggested_action = Column(Text)
    healing_mode = Column(String, default="suggested")
    requires_approval = Column(Boolean, default=True)
    status = Column(String, default="pending")
    target_device = Column(String)
    executed_by = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class PolicyTemplate(Base):
    __tablename__ = "policy_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(String, unique=True, nullable=False)
    vendor = Column(String, nullable=False)
    device_type = Column(String, nullable=False)
    function = Column(String, nullable=False)
    template_content = Column(Text, nullable=False)
    parameters_schema = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentRegistry(Base):
    __tablename__ = "agent_registry"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String, unique=True, nullable=False)
    domain = Column(String, nullable=False)
    ip = Column(String)
    a2a_endpoint = Column(String, nullable=False)
    capabilities = Column(JSON)
    status = Column(String, default="online")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    device_type = Column(String, nullable=False)
    vendor = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    status = Column(String, default="healthy")
    os_type = Column(String)
    ssh_port = Column(Integer, default=22)
    netconf_port = Column(Integer, default=830)
    credentials_encrypted = Column(Text, nullable=True)
    cpu_usage = Column(Float, default=0.0)
    memory_usage = Column(Float, default=0.0)
    uptime = Column(String, nullable=True)
    location = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class DeviceLink(Base):
    __tablename__ = "device_links"

    id = Column(Integer, primary_key=True, index=True)
    source_device_id = Column(String, nullable=False, index=True)
    target_device_id = Column(String, nullable=False, index=True)
    status = Column(String, default="active")
    bandwidth = Column(String, nullable=True)
    current_load = Column(Float, default=0.0)
    latency = Column(Float, nullable=True, comment="链路延迟(ms)")
    link_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_user_id", "user_id"),
        Index("ix_audit_action", "action"),
        Index("ix_audit_status", "status"),
        Index("ix_audit_security_type", "security_type"),
        Index("ix_audit_timestamp", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    target_device = Column(String)
    commands = Column(JSON)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    approval_id = Column(String)
    status = Column(String, default="success")
    security_type = Column(String)
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    latency_ms = Column(Integer)
    raw_prompt = Column(Text)
    raw_response = Column(Text)


class MCPTool(Base):
    __tablename__ = "mcp_tools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    input_schema = Column(JSON, nullable=False)
    output_schema = Column(JSON, nullable=True)
    source = Column(String, default="local")
    endpoint = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class IntentTemplate(Base):
    __tablename__ = "intent_templates"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    intent_type = Column(String, nullable=False)
    template_content = Column(Text, nullable=False)
    parameters_schema = Column(JSON, nullable=False)
    example_values = Column(JSON, nullable=True)
    sla_template = Column(JSON, nullable=True)
    priority = Column(String, default="medium")
    is_public = Column(Boolean, default=True)
    author = Column(String, nullable=False)
    usage_count = Column(Integer, default=0)
    rating = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)
    tags = Column(JSON, default=[])
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SLAEvaluationResult(Base):
    __tablename__ = "sla_evaluation_results"

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(Integer, nullable=False, index=True)
    sla_status = Column(String, nullable=False)
    violations = Column(JSON, default=[])
    metrics_snapshot = Column(JSON, nullable=True)
    evaluated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SLAPrediction(Base):
    __tablename__ = "sla_predictions"

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(Integer, nullable=False, index=True)
    predicted_violation = Column(Boolean, nullable=False)
    violation_probability = Column(Float, default=0.0)
    predicted_time = Column(DateTime, nullable=True)
    prediction_model = Column(String, default="statistical")
    confidence = Column(Float, default=0.0)
    metrics_forecast = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String, default="pending")
    priority = Column(String, nullable=False)
    created_by = Column(String, nullable=False)
    assigned_to = Column(String, default="")
    approval_chain = Column(JSON, default=[])
    current_step = Column(Integer, default=0)
    intent_id = Column(String, nullable=True)
    result = Column(Text, nullable=True)
    reject_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RemoteMCPServer(Base):
    __tablename__ = "remote_mcp_servers"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    auth_type = Column(String, default="none")
    auth_token = Column(Text, nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TraceSpan(Base):
    __tablename__ = "trace_spans"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String, nullable=False, index=True)
    span_id = Column(String, nullable=False, unique=True)
    parent_span_id = Column(String, nullable=True)
    agent_id = Column(String, nullable=False, index=True)
    operation = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    status = Column(String, default="ok")
    attributes = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentHealthRecord(Base):
    __tablename__ = "agent_health_records"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False)
    latency_p50 = Column(Float, default=0.0)
    latency_p95 = Column(Float, default=0.0)
    latency_p99 = Column(Float, default=0.0)
    error_rate = Column(Float, default=0.0)
    qps = Column(Float, default=0.0)
    reasoning_rounds_avg = Column(Float, nullable=True)
    last_check_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class FailedIntentCase(Base):
    __tablename__ = "failed_intent_cases"

    id = Column(Integer, primary_key=True, index=True)
    user_input = Column(Text, nullable=False)
    parse_method = Column(String, nullable=False)
    failure_reason = Column(Text, nullable=False)
    raw_response = Column(Text, nullable=True)
    intent_type_attempted = Column(String, nullable=True)
    clarification_question = Column(Text, nullable=True)
    user_clarification = Column(Text, nullable=True)
    resolved = Column(Boolean, default=False)
    resolution_notes = Column(Text, nullable=True)
    meta_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class IntentScheduleRecord(Base):
    __tablename__ = "intent_schedule_records"

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(Integer, nullable=False, index=True)
    priority = Column(Integer, default=5)
    queue_position = Column(Integer, default=0)
    resource_quota = Column(JSON, nullable=True)
    status = Column(String, default="queued")
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    preempted_by = Column(Integer, nullable=True)
    preempt_count = Column(Integer, default=0)
    wait_time_ms = Column(Integer, default=0)
    execution_time_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WorkOrderSLA(Base):
    __tablename__ = "work_order_sla"

    id = Column(Integer, primary_key=True, index=True)
    work_order_id = Column(String, nullable=False, index=True)
    sla_type = Column(String, nullable=False)
    target_duration_minutes = Column(Integer, nullable=False)
    actual_duration_minutes = Column(Integer, nullable=True)
    status = Column(String, default="pending")
    started_at = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    warning_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WorkOrderDependency(Base):
    __tablename__ = "work_order_dependencies"

    id = Column(Integer, primary_key=True, index=True)
    work_order_id = Column(String, nullable=False, index=True)
    depends_on_order_id = Column(String, nullable=False, index=True)
    dependency_type = Column(String, default="completion")
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WorkOrderAutomationRule(Base):
    __tablename__ = "work_order_automation_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    trigger_condition = Column(JSON, nullable=False)
    action = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    execution_count = Column(Integer, default=0)
    last_triggered_at = Column(DateTime, nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Playbook(Base):
    __tablename__ = "playbooks"

    id = Column(Integer, primary_key=True, index=True)
    playbook_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    steps = Column(JSON, nullable=False)
    parameters_schema = Column(JSON, nullable=True)
    is_public = Column(Boolean, default=True)
    author = Column(String, nullable=False)
    version = Column(Integer, default=1)
    execution_count = Column(Integer, default=0)
    last_execution_status = Column(String, nullable=True)
    tags = Column(JSON, default=[])
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class PlaybookExecution(Base):
    __tablename__ = "playbook_executions"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(String, unique=True, nullable=False, index=True)
    playbook_id = Column(String, nullable=False, index=True)
    status = Column(String, default="pending")
    current_step_index = Column(Integer, default=0)
    parameter_values = Column(JSON, nullable=True)
    step_results = Column(JSON, default=[])
    triggered_by = Column(String, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentCapabilityScore(Base):
    __tablename__ = "agent_capability_scores"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String, nullable=False, index=True)
    success_rate = Column(Float, default=0.0)
    avg_execution_time_ms = Column(Float, default=0.0)
    resource_efficiency = Column(Float, default=0.0)
    total_tasks = Column(Integer, default=0)
    successful_tasks = Column(Integer, default=0)
    failed_tasks = Column(Integer, default=0)
    capability_tags = Column(JSON, default=[])
    performance_trend = Column(String, default="stable")
    last_scored_at = Column(DateTime, nullable=True)
    score_version = Column(Integer, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class BehaviorAnomaly(Base):
    __tablename__ = "behavior_anomalies"

    id = Column(Integer, primary_key=True, index=True)
    anomaly_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    anomaly_type = Column(String, nullable=False)
    severity = Column(String, default="medium")
    description = Column(Text, nullable=False)
    evidence = Column(JSON, nullable=False)
    status = Column(String, default="detected")
    investigated_by = Column(String, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)


class ChangeImpactAnalysis(Base):
    __tablename__ = "change_impact_analyses"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(String, unique=True, nullable=False, index=True)
    intent_id = Column(Integer, nullable=False, index=True)
    target_devices = Column(JSON, nullable=False)
    proposed_changes = Column(JSON, nullable=False)
    simulated_impact = Column(JSON, nullable=True)
    affected_services = Column(JSON, default=[])
    risk_level = Column(String, default="medium")
    risk_factors = Column(JSON, default=[])
    mitigation_suggestions = Column(JSON, default=[])
    analyzed_by = Column(String, default="llm")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    secret = Column(String, nullable=True)
    event_types = Column(JSON, nullable=False)
    headers = Column(JSON, default={})
    is_active = Column(Boolean, default=True)
    retry_policy = Column(JSON, default={"max_retries": 3, "backoff_seconds": [5, 30, 120]})
    last_triggered_at = Column(DateTime, nullable=True)
    last_status = Column(String, nullable=True)
    failure_count = Column(Integer, default=0)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class GrayscaleHealingTask(Base):
    __tablename__ = "grayscale_healing_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, unique=True, nullable=False, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    target_devices = Column(JSON, nullable=False)
    canary_device = Column(String, nullable=False)
    canary_status = Column(String, default="pending")
    canary_result = Column(JSON, nullable=True)
    canary_started_at = Column(DateTime, nullable=True)
    canary_completed_at = Column(DateTime, nullable=True)
    batch_status = Column(String, default="pending")
    batch_progress = Column(Integer, default=0)
    batch_completed_devices = Column(JSON, default=[])
    batch_failed_devices = Column(JSON, default=[])
    batch_started_at = Column(DateTime, nullable=True)
    batch_completed_at = Column(DateTime, nullable=True)
    rollback_triggered = Column(Boolean, default=False)
    rollback_reason = Column(Text, nullable=True)
    overall_status = Column(String, default="canary_pending")
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class HealingEvaluation(Base):
    __tablename__ = "healing_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    evaluation_id = Column(String, unique=True, nullable=False, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    task_id = Column(String, nullable=True, index=True)
    metrics_before = Column(JSON, nullable=False)
    metrics_after = Column(JSON, nullable=True)
    healing_action = Column(Text, nullable=False)
    effectiveness_score = Column(Float, nullable=True)
    root_cause_analysis = Column(Text, nullable=True)
    side_effects = Column(JSON, default=[])
    recommendation = Column(Text, nullable=True)
    evaluated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class QuickCommand(Base):
    __tablename__ = "quick_commands"

    id = Column(Integer, primary_key=True, index=True)
    command_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    shortcut = Column(String, nullable=False)
    template = Column(String, nullable=False)
    parameters = Column(JSON, default=[])
    category = Column(String, default="custom")
    is_public = Column(Boolean, default=False)
    created_by = Column(String, nullable=False)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ProactiveNotification(Base):
    __tablename__ = "proactive_notifications"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(String, unique=True, nullable=False, index=True)
    notification_type = Column(String, nullable=False)
    severity = Column(String, default="info")
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    suggested_action = Column(Text, nullable=True)
    target_users = Column(JSON, default=[])
    source_data = Column(JSON, nullable=True)
    is_read = Column(Boolean, default=False)
    read_by = Column(JSON, default=[])
    dismissed_by = Column(JSON, default=[])
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class KnowledgeDocumentVersion(Base):
    __tablename__ = "knowledge_document_versions"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(String, unique=True, nullable=False, index=True)
    document_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    version_number = Column(Integer, nullable=False)
    change_type = Column(String, nullable=False)
    change_summary = Column(Text, nullable=True)
    contributor = Column(String, nullable=False)
    content_hash = Column(String, nullable=False)
    meta_data = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ExecutionPlan(Base):
    __tablename__ = "execution_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(String, unique=True, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    goal = Column(Text, nullable=False)
    plan_json = Column(JSON, nullable=False)
    status = Column(String, default="pending")
    current_step_index = Column(Integer, default=0)
    result_json = Column(JSON, nullable=True)
    reflection_json = Column(JSON, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=2)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class WizardSession(Base):
    __tablename__ = "wizard_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    wizard_type = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    params_json = Column(JSON, nullable=False)
    plan_id = Column(String, nullable=True, index=True)
    status = Column(String, default="pending")
    step_results = Column(JSON, default=[])
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))