from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class ConfirmLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlanStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_CONFIRM = "waiting_confirm"


class PlanStep(BaseModel):
    step_index: int = Field(..., ge=0)
    description: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    tool_params: Dict[str, Any] = Field(default_factory=dict)
    confirm_level: ConfirmLevel = Field(default=ConfirmLevel.LOW)
    condition: Optional[str] = None
    parallel_group: Optional[int] = None
    fallback_tool: Optional[str] = None
    status: PlanStepStatus = Field(default=PlanStepStatus.PENDING)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class ExecutionPlanModel(BaseModel):
    plan_id: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    steps: List[PlanStep] = Field(..., min_length=1)
    confirm_level: ConfirmLevel = Field(default=ConfirmLevel.MEDIUM)
    estimated_duration_seconds: int = Field(default=60)
    risk_summary: str = Field(default="")


class PlanReviewResult(BaseModel):
    is_valid: bool = True
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    adjusted_confirm_level: Optional[ConfirmLevel] = None


class StepExecutionResult(BaseModel):
    step_index: int
    status: PlanStepStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    should_retry: bool = False
    should_pause: bool = False
    confirm_required: bool = False


class ReflectionResult(BaseModel):
    needs_revision: bool = False
    revised_plan: Optional[ExecutionPlanModel] = None
    analysis: str = ""
    should_retry_from_step: Optional[int] = None


class FinalReport(BaseModel):
    plan_id: str
    goal: str
    status: str
    steps_summary: List[Dict[str, Any]] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    conclusion: str = ""
    recommendations: List[str] = Field(default_factory=list)
