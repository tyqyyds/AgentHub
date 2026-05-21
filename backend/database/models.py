from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, Boolean, Enum
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from enum import Enum as PyEnum

Base = declarative_base()


class ApprovalStatus(PyEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class HealingMode(PyEnum):
    AUTO = "auto"
    SUGGESTED = "suggested"
    ALERT_ONLY = "alert_only"


class Intent(Base):
    __tablename__ = "intents"
    
    id = Column(Integer, primary_key=True, index=True)
    intent_name = Column(String, nullable=False)
    user_input = Column(Text, nullable=False)
    structured_params = Column(JSON, nullable=False)
    approval_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    prompt_tokens_usage = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PolicyTemplate(Base):
    __tablename__ = "policy_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(String, unique=True, nullable=False)
    vendor = Column(String, nullable=False)
    device_type = Column(String, nullable=False)
    function = Column(String, nullable=False)
    template_content = Column(Text, nullable=False)
    parameters_schema = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentRegistry(Base):
    __tablename__ = "agent_registry"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String, unique=True, nullable=False)
    domain = Column(String, nullable=False)
    ip = Column(String)
    a2a_endpoint = Column(String, nullable=False)
    capabilities = Column(JSON)
    status = Column(String, default="online")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    target_device = Column(String)
    commands = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)
    approval_id = Column(String)
    status = Column(String, default="success")