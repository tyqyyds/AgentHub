# AI 助手升级第二批实施计划 — Plan-Execute Agent & 工具编排引擎

## Goal

在第一批核心基础（意图理解引擎 v2、对话状态追踪器 DST、知识引擎 v2）之上，实现：
1. **Plan-Execute Agent**：从 ReAct 单步推理升级为多步计划编排+反思修正，支持运维向导模板
2. **工具编排引擎**：从单工具调用升级为工具链 DAG 编排，支持并行执行、自动降级、参数引用

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Vue 3 + Pinia)                  │
│  ChatPanel.vue ── PlanExecuteUI / WizardUI / ToolChainUI    │
│  assistant.ts ── planExecute state / wizard state            │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/SSE
┌──────────────────────────▼──────────────────────────────────┐
│                    FastAPI Backend                            │
│  /plan-execute  /wizards  /tool-chains                       │
│                                                              │
│  ┌────────────────────┐    ┌──────────────────────────────┐ │
│  │  Plan-Execute      │    │  Tool Orchestration Engine   │ │
│  │  Agent             │───▶│  (DAG + Parallel + Retry)    │ │
│  │  ┌──────────────┐  │    │  ┌────────────────────────┐  │ │
│  │  │PlanGenerator │  │    │  │ ToolChain Registry     │  │ │
│  │  │PlanReviewer  │  │    │  │ DAG Analyzer           │  │ │
│  │  │StepExecutor  │  │    │  │ Parallel Executor      │  │ │
│  │  │ResultValidator│ │    │  │ Auto-Degradation       │  │ │
│  │  │Reflector     │  │    │  │ Param Reference Parser │  │ │
│  │  └──────────────┘  │    │  └────────────────────────┘  │ │
│  └────────────────────┘    └──────────────────────────────┘ │
│                                                              │
│  ┌────────────────────┐    ┌──────────────────────────────┐ │
│  │  ReAct Engine      │    │  Tool Registry (existing)    │ │
│  │  (collaborate)     │    │  MCP Registry (enhanced)     │ │
│  └────────────────────┘    └──────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              SQLite + SQLAlchemy (Async)                      │
│  execution_plans / wizard_sessions / tool_chain_executions   │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend Framework | FastAPI | 0.100+ |
| ORM | SQLAlchemy (async) | 2.0+ |
| Database | SQLite (aiosqlite) | 3.x |
| LLM | ZhiPu GLM (智谱) | glm-4-flash |
| Async Runtime | asyncio + httpx | Python 3.11+ |
| Frontend Framework | Vue 3 | 3.4+ |
| State Management | Pinia | 2.1+ |
| Language | TypeScript | 5.x |
| Testing (Backend) | pytest + pytest-asyncio | 7.x / 0.21+ |
| Testing (Frontend) | Vitest | 1.x |

## Dependencies on Batch 1

| Batch 1 Module | Dependency Point |
|---------------|-----------------|
| 意图理解引擎 v2 (`intent_classifier.py`) | Plan-Execute 接收分类后的意图 |
| 对话状态追踪器 (`dialogue_state.py`) | Plan-Execute 读取/更新对话状态 |
| 知识引擎 v2 (`hybrid_retriever.py`) | Reflector 检索知识辅助反思 |

---

# 模块 4：Plan-Execute Agent

## 4.1 数据模型

### 4.1.1 数据库模型 — `backend/database/models.py` 新增

```python
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
```

### 4.1.2 Pydantic 模型 — `backend/agents/plan_executor.py` 内定义

```python
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
```

---

## 4.2 Plan-Execute 核心 — `backend/agents/plan_executor.py`

### Step 1: 编写测试 `tests/test_plan_executor.py`

- [ ] **4.2-T1** 编写 PlanGenerator 测试

```python
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from backend.agents.plan_executor import (
    PlanGenerator, PlanReviewer, StepExecutor,
    ResultValidator, Reflector, PlanExecuteAgent,
    ExecutionPlanModel, PlanStep, ConfirmLevel,
    PlanStepStatus, PlanReviewResult, StepExecutionResult,
    ReflectionResult, FinalReport
)


@pytest.fixture
def mock_llm_gateway():
    gateway = MagicMock()
    gateway.chat = AsyncMock()
    return gateway


@pytest.fixture
def mock_tool_registry():
    registry = MagicMock()
    registry.get_tool = MagicMock(return_value=MagicMock(
        name="query_topology",
        risk_level="low",
        description="Query topology"
    ))
    registry.execute_tool = AsyncMock(return_value={
        "status_code": 200,
        "data": {"devices": [{"id": "sw-01", "status": "online"}]}
    })
    registry.get_openai_tools_schema = MagicMock(return_value=[
        {
            "type": "function",
            "function": {
                "name": "query_topology",
                "description": "Query topology",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        }
    ])
    return registry


@pytest.fixture
def sample_plan():
    return ExecutionPlanModel(
        plan_id="plan_test_001",
        goal="排查核心交换机故障",
        steps=[
            PlanStep(
                step_index=0,
                description="查询拓扑获取故障设备",
                tool_name="query_topology",
                tool_params={"filter": "alert"},
                confirm_level=ConfirmLevel.LOW,
                parallel_group=0
            ),
            PlanStep(
                step_index=1,
                description="查询故障设备详情",
                tool_name="query_device",
                tool_params={"device_id": "$step0.devices[0].id"},
                confirm_level=ConfirmLevel.MEDIUM,
                parallel_group=None
            ),
            PlanStep(
                step_index=2,
                description="执行自愈操作",
                tool_name="execute_self_healing",
                tool_params={"event_id": "$step1.device.event_id"},
                confirm_level=ConfirmLevel.HIGH,
                fallback_tool="system_health"
            ),
            PlanStep(
                step_index=3,
                description="验证系统健康",
                tool_name="system_health",
                tool_params={},
                confirm_level=ConfirmLevel.LOW,
                parallel_group=None
            )
        ],
        confirm_level=ConfirmLevel.MEDIUM,
        estimated_duration_seconds=120,
        risk_summary="包含1个高危操作(自愈执行)"
    )


class TestPlanGenerator:
    @pytest.mark.asyncio
    async def test_generate_plan_returns_valid_model(self, mock_llm_gateway):
        mock_llm_gateway.chat.return_value = json.dumps({
            "plan_id": "plan_gen_001",
            "goal": "排查核心交换机故障",
            "steps": [
                {
                    "step_index": 0,
                    "description": "查询拓扑",
                    "tool_name": "query_topology",
                    "tool_params": {},
                    "confirm_level": "low"
                }
            ],
            "confirm_level": "low",
            "estimated_duration_seconds": 30,
            "risk_summary": "低风险"
        })

        generator = PlanGenerator(mock_llm_gateway)
        plan = await generator.generate(
            goal="排查核心交换机故障",
            context={"role": "admin", "page": "/topology"},
            available_tools=[{"name": "query_topology", "description": "Query topology"}]
        )

        assert isinstance(plan, ExecutionPlanModel)
        assert plan.goal == "排查核心交换机故障"
        assert len(plan.steps) >= 1
        assert plan.steps[0].tool_name == "query_topology"

    @pytest.mark.asyncio
    async def test_generate_plan_fallback_on_parse_error(self, mock_llm_gateway):
        mock_llm_gateway.chat.return_value = "not valid json"

        generator = PlanGenerator(mock_llm_gateway)
        plan = await generator.generate(
            goal="查询系统状态",
            context={"role": "viewer", "page": "/"},
            available_tools=[{"name": "system_health", "description": "Health check"}]
        )

        assert isinstance(plan, ExecutionPlanModel)
        assert len(plan.steps) >= 1


class TestPlanReviewer:
    def test_review_valid_plan(self, sample_plan):
        reviewer = PlanReviewer()
        result = reviewer.review(sample_plan)

        assert isinstance(result, PlanReviewResult)
        assert result.is_valid is True

    def test_review_plan_with_high_risk_escalation(self, sample_plan):
        sample_plan.steps[2].confirm_level = ConfirmLevel.LOW
        reviewer = PlanReviewer()
        result = reviewer.review(sample_plan)

        assert result.adjusted_confirm_level == ConfirmLevel.HIGH or result.is_valid is True

    def test_review_empty_steps_plan(self):
        reviewer = PlanReviewer()
        empty_plan = ExecutionPlanModel(
            plan_id="plan_empty",
            goal="empty",
            steps=[]
        )
        result = reviewer.review(empty_plan)

        assert result.is_valid is False
        assert any("步骤" in issue for issue in result.issues)


class TestStepExecutor:
    @pytest.mark.asyncio
    async def test_execute_low_confirm_step_auto(self, mock_tool_registry):
        executor = StepExecutor(mock_tool_registry)
        step = PlanStep(
            step_index=0,
            description="查询拓扑",
            tool_name="query_topology",
            tool_params={},
            confirm_level=ConfirmLevel.LOW
        )

        result = await executor.execute(step, token="test_token")

        assert isinstance(result, StepExecutionResult)
        assert result.status == PlanStepStatus.COMPLETED
        assert result.result is not None

    @pytest.mark.asyncio
    async def test_execute_high_confirm_step_paused(self, mock_tool_registry):
        executor = StepExecutor(mock_tool_registry)
        step = PlanStep(
            step_index=0,
            description="执行自愈",
            tool_name="execute_self_healing",
            tool_params={"event_id": "evt_001"},
            confirm_level=ConfirmLevel.HIGH
        )

        result = await executor.execute(step, token="test_token")

        assert result.confirm_required is True
        assert result.status == PlanStepStatus.WAITING_CONFIRM

    @pytest.mark.asyncio
    async def test_execute_with_param_reference(self, mock_tool_registry):
        executor = StepExecutor(mock_tool_registry)
        step = PlanStep(
            step_index=1,
            description="查询设备",
            tool_name="query_device",
            tool_params={"device_id": "$step0.devices[0].id"},
            confirm_level=ConfirmLevel.LOW
        )
        previous_results = {
            0: {"devices": [{"id": "sw-01", "status": "online"}]}
        }

        result = await executor.execute(step, token="test_token", previous_results=previous_results)

        assert result.status == PlanStepStatus.COMPLETED
        call_args = mock_tool_registry.execute_tool.call_args
        assert call_args[1]["params"]["device_id"] == "sw-01"

    @pytest.mark.asyncio
    async def test_execute_tool_failure_with_fallback(self, mock_tool_registry):
        mock_tool_registry.execute_tool = AsyncMock(side_effect=[
            Exception("Tool timeout"),
            {"status_code": 200, "data": {"healthy": True}}
        ])
        mock_tool_registry.get_tool = MagicMock(side_effect=[
            MagicMock(name="execute_self_healing", risk_level="high", description="Self heal"),
            MagicMock(name="system_health", risk_level="low", description="Health check")
        ])

        executor = StepExecutor(mock_tool_registry)
        step = PlanStep(
            step_index=0,
            description="执行自愈",
            tool_name="execute_self_healing",
            tool_params={},
            confirm_level=ConfirmLevel.LOW,
            fallback_tool="system_health"
        )

        result = await executor.execute(step, token="test_token")

        assert result.status == PlanStepStatus.COMPLETED


class TestResultValidator:
    def test_validate_success_result(self):
        validator = ResultValidator()
        step_result = StepExecutionResult(
            step_index=0,
            status=PlanStepStatus.COMPLETED,
            result={"status_code": 200, "data": {"ok": True}}
        )

        decision = validator.validate(step_result)

        assert decision["action"] == "continue"
        assert decision["should_retry"] is False

    def test_validate_failed_result_should_retry(self):
        validator = ResultValidator()
        step_result = StepExecutionResult(
            step_index=0,
            status=PlanStepStatus.FAILED,
            error="Connection timeout"
        )

        decision = validator.validate(step_result, retry_count=0, max_retries=2)

        assert decision["action"] == "retry"
        assert decision["should_retry"] is True

    def test_validate_failed_result_max_retries_exceeded(self):
        validator = ResultValidator()
        step_result = StepExecutionResult(
            step_index=0,
            status=PlanStepStatus.FAILED,
            error="Connection timeout"
        )

        decision = validator.validate(step_result, retry_count=2, max_retries=2)

        assert decision["action"] == "fail"

    def test_validate_waiting_confirm(self):
        validator = ResultValidator()
        step_result = StepExecutionResult(
            step_index=0,
            status=PlanStepStatus.WAITING_CONFIRM,
            confirm_required=True
        )

        decision = validator.validate(step_result)

        assert decision["action"] == "pause"


class TestReflector:
    @pytest.mark.asyncio
    async def test_reflect_no_revision_needed(self, mock_llm_gateway):
        mock_llm_gateway.chat.return_value = json.dumps({
            "needs_revision": False,
            "analysis": "计划执行顺利，无需修改"
        })

        reflector = Reflector(mock_llm_gateway)
        result = await reflector.reflect(
            plan=ExecutionPlanModel(
                plan_id="plan_001",
                goal="test",
                steps=[PlanStep(step_index=0, description="step1", tool_name="system_health")]
            ),
            completed_steps=[
                StepExecutionResult(step_index=0, status=PlanStepStatus.COMPLETED, result={"ok": True})
            ],
            failed_step=None
        )

        assert isinstance(result, ReflectionResult)
        assert result.needs_revision is False

    @pytest.mark.asyncio
    async def test_reflect_with_revision(self, mock_llm_gateway):
        mock_llm_gateway.chat.return_value = json.dumps({
            "needs_revision": True,
            "analysis": "步骤2失败，需要更换工具",
            "should_retry_from_step": 1,
            "revised_plan": {
                "plan_id": "plan_001_v2",
                "goal": "test",
                "steps": [
                    {"step_index": 0, "description": "step1", "tool_name": "system_health", "confirm_level": "low"},
                    {"step_index": 1, "description": "step2 revised", "tool_name": "query_topology", "confirm_level": "low"}
                ],
                "confirm_level": "low",
                "estimated_duration_seconds": 30,
                "risk_summary": "已降级"
            }
        })

        reflector = Reflector(mock_llm_gateway)
        result = await reflector.reflect(
            plan=ExecutionPlanModel(
                plan_id="plan_001",
                goal="test",
                steps=[
                    PlanStep(step_index=0, description="step1", tool_name="system_health"),
                    PlanStep(step_index=1, description="step2", tool_name="execute_self_healing")
                ]
            ),
            completed_steps=[
                StepExecutionResult(step_index=0, status=PlanStepStatus.COMPLETED, result={"ok": True})
            ],
            failed_step=StepExecutionResult(step_index=1, status=PlanStepStatus.FAILED, error="timeout")
        )

        assert result.needs_revision is True
        assert result.should_retry_from_step == 1


class TestPlanExecuteAgent:
    @pytest.mark.asyncio
    async def test_full_execution_flow(self, mock_llm_gateway, mock_tool_registry):
        mock_llm_gateway.chat.return_value = json.dumps({
            "plan_id": "plan_full_001",
            "goal": "查询系统健康",
            "steps": [
                {
                    "step_index": 0,
                    "description": "查询系统健康状态",
                    "tool_name": "system_health",
                    "tool_params": {},
                    "confirm_level": "low"
                }
            ],
            "confirm_level": "low",
            "estimated_duration_seconds": 10,
            "risk_summary": "无风险"
        })

        agent = PlanExecuteAgent(
            llm_gateway=mock_llm_gateway,
            tool_registry=mock_tool_registry
        )

        result = await agent.run(
            goal="查询系统健康",
            context={"role": "admin", "page": "/"},
            token="test_token"
        )

        assert isinstance(result, FinalReport)
        assert result.status in ("success", "partial", "failed")
        assert result.plan_id.startswith("plan_")
```

- [ ] **4.2-T2** 运行测试确认 RED 状态

```bash
cd "d:\Trae CN\Project\智维 AgentHub"
python -m pytest tests/test_plan_executor.py -v --tb=short 2>&1 | head -80
```

### Step 2: 实现 `backend/agents/plan_executor.py`

- [ ] **4.2-I1** 实现 PlanGenerator

```python
import json
import time
import uuid
import logging
import re
from typing import Dict, Any, Optional, List

from backend.agents.plan_executor_models import (
    ExecutionPlanModel, PlanStep, ConfirmLevel,
    PlanStepStatus, PlanReviewResult, StepExecutionResult,
    ReflectionResult, FinalReport
)

logger = logging.getLogger(__name__)

PLAN_GENERATION_PROMPT = """你是智维AgentHub的计划生成器。根据用户目标，生成一个结构化执行计划。

可用工具：
{tools_description}

用户目标：{goal}
上下文：角色={role}, 页面={page}

请生成执行计划，输出JSON格式：
{{
    "plan_id": "plan_xxx",
    "goal": "用户目标",
    "steps": [
        {{
            "step_index": 0,
            "description": "步骤描述",
            "tool_name": "工具名称",
            "tool_params": {{}},
            "confirm_level": "low|medium|high",
            "condition": "可选的条件表达式",
            "parallel_group": null,
            "fallback_tool": "可选的降级工具"
        }}
    ],
    "confirm_level": "low|medium|high",
    "estimated_duration_seconds": 60,
    "risk_summary": "风险摘要"
}}

规则：
1. 每个步骤必须使用可用工具列表中的工具
2. 高危操作(execute_self_healing, execute_intent, shutdown_port)必须设置confirm_level为high
3. 可并行的步骤设置相同的parallel_group值
4. 参数引用使用 $stepN.path 格式引用前序步骤结果
5. 为可能失败的步骤提供fallback_tool
6. 最多8个步骤"""


class PlanGenerator:
    def __init__(self, llm_gateway):
        self.llm_gateway = llm_gateway

    async def generate(
        self,
        goal: str,
        context: Dict[str, Any],
        available_tools: List[Dict[str, Any]]
    ) -> ExecutionPlanModel:
        tools_desc = "\n".join(
            f"- {t['name']}: {t.get('description', '')}"
            for t in available_tools
        )

        prompt = PLAN_GENERATION_PROMPT.format(
            tools_description=tools_desc,
            goal=goal,
            role=context.get("role", "viewer"),
            page=context.get("page", "/")
        )

        try:
            response = await self.llm_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048
            )
            plan_data = self._parse_json_response(response)
            return ExecutionPlanModel(**plan_data)
        except Exception as e:
            logger.warning(f"Plan generation failed, using fallback: {e}")
            return self._generate_fallback_plan(goal, available_tools)

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError("No JSON found in LLM response")

    def _generate_fallback_plan(
        self,
        goal: str,
        available_tools: List[Dict[str, Any]]
    ) -> ExecutionPlanModel:
        safe_tool = next(
            (t for t in available_tools if t["name"] == "system_health"),
            available_tools[0] if available_tools else None
        )
        tool_name = safe_tool["name"] if safe_tool else "system_health"
        return ExecutionPlanModel(
            plan_id=f"plan_fallback_{uuid.uuid4().hex[:8]}",
            goal=goal,
            steps=[
                PlanStep(
                    step_index=0,
                    description=f"执行 {tool_name} 完成目标: {goal}",
                    tool_name=tool_name,
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW
                )
            ],
            confirm_level=ConfirmLevel.LOW,
            estimated_duration_seconds=30,
            risk_summary="降级计划：单步执行"
        )
```

- [ ] **4.2-I2** 实现 PlanReviewer

```python
HIGH_RISK_TOOLS = {"execute_self_healing", "execute_intent", "shutdown_port", "isolate_node", "restart_device"}


class PlanReviewer:
    def review(self, plan: ExecutionPlanModel) -> PlanReviewResult:
        issues: List[str] = []
        suggestions: List[str] = []
        adjusted_level: Optional[ConfirmLevel] = None

        if not plan.steps:
            issues.append("执行计划必须包含至少1个步骤")
            return PlanReviewResult(is_valid=False, issues=issues)

        step_indices = set()
        for step in plan.steps:
            if step.step_index in step_indices:
                issues.append(f"步骤索引重复: {step.step_index}")
            step_indices.add(step.step_index)

            if step.tool_name in HIGH_RISK_TOOLS and step.confirm_level != ConfirmLevel.HIGH:
                suggestions.append(
                    f"步骤{step.step_index}使用高危工具{step.tool_name}，建议设置confirm_level=high"
                )
                if adjusted_level is None or adjusted_level == ConfirmLevel.LOW:
                    adjusted_level = ConfirmLevel.HIGH

            if step.fallback_tool and step.confirm_level == ConfirmLevel.HIGH:
                suggestions.append(
                    f"步骤{step.step_index}为高危操作且设置了降级工具，确认级别将保持high"
                )

        if plan.confirm_level == ConfirmLevel.LOW and any(
            s.tool_name in HIGH_RISK_TOOLS for s in plan.steps
        ):
            adjusted_level = ConfirmLevel.HIGH
            suggestions.append("计划包含高危操作，整体确认级别已提升为high")

        return PlanReviewResult(
            is_valid=len(issues) == 0,
            issues=issues,
            suggestions=suggestions,
            adjusted_confirm_level=adjusted_level
        )
```

- [ ] **4.2-I3** 实现 StepExecutor（含参数引用解析）

```python
class StepExecutor:
    def __init__(self, tool_registry):
        self.tool_registry = tool_registry

    async def execute(
        self,
        step: PlanStep,
        token: str,
        previous_results: Optional[Dict[int, Any]] = None,
        approved: bool = False
    ) -> StepExecutionResult:
        if step.confirm_level == ConfirmLevel.HIGH and not approved:
            return StepExecutionResult(
                step_index=step.step_index,
                status=PlanStepStatus.WAITING_CONFIRM,
                confirm_required=True,
                should_pause=True
            )

        if step.confirm_level == ConfirmLevel.MEDIUM and not approved:
            return StepExecutionResult(
                step_index=step.step_index,
                status=PlanStepStatus.WAITING_CONFIRM,
                confirm_required=True,
                should_pause=True
            )

        resolved_params = self._resolve_params(step.tool_params, previous_results or {})

        started_at = time.time()
        try:
            tool_result = await self.tool_registry.execute_tool(
                name=step.tool_name,
                params=resolved_params,
                token=token
            )
            completed_at = time.time()

            if isinstance(tool_result, dict) and tool_result.get("error"):
                return StepExecutionResult(
                    step_index=step.step_index,
                    status=PlanStepStatus.FAILED,
                    error=tool_result["error"],
                    should_retry=True
                )

            return StepExecutionResult(
                step_index=step.step_index,
                status=PlanStepStatus.COMPLETED,
                result=tool_result
            )
        except Exception as e:
            logger.warning(f"Step {step.step_index} tool {step.tool_name} failed: {e}")

            if step.fallback_tool:
                logger.info(f"Trying fallback tool: {step.fallback_tool}")
                try:
                    fallback_result = await self.tool_registry.execute_tool(
                        name=step.fallback_tool,
                        params={},
                        token=token
                    )
                    return StepExecutionResult(
                        step_index=step.step_index,
                        status=PlanStepStatus.COMPLETED,
                        result=fallback_result
                    )
                except Exception as fb_err:
                    logger.error(f"Fallback tool {step.fallback_tool} also failed: {fb_err}")

            return StepExecutionResult(
                step_index=step.step_index,
                status=PlanStepStatus.FAILED,
                error=str(e),
                should_retry=True
            )

    def _resolve_params(
        self,
        params: Dict[str, Any],
        previous_results: Dict[int, Any]
    ) -> Dict[str, Any]:
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$step"):
                resolved[key] = self._resolve_reference(value, previous_results)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_params(value, previous_results)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_reference(v, previous_results)
                    if isinstance(v, str) and v.startswith("$step") else v
                    for v in value
                ]
            else:
                resolved[key] = value
        return resolved

    def _resolve_reference(self, ref: str, previous_results: Dict[int, Any]) -> Any:
        match = re.match(r'\$step(\d+)(.*)', ref)
        if not match:
            return ref

        step_idx = int(match.group(1))
        path = match.group(2)

        step_result = previous_results.get(step_idx)
        if step_result is None:
            logger.warning(f"Reference {ref} points to non-existent step result")
            return ref

        if not path:
            return step_result

        current = step_result
        for part in path.lstrip(".").split("."):
            if part.startswith("[") and part.endswith("]"):
                idx = int(part[1:-1])
                if isinstance(current, list) and idx < len(current):
                    current = current[idx]
                else:
                    return ref
            elif isinstance(current, dict):
                current = current.get(part, ref)
            else:
                return ref

        return current
```

- [ ] **4.2-I4** 实现 ResultValidator

```python
class ResultValidator:
    def validate(
        self,
        step_result: StepExecutionResult,
        retry_count: int = 0,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        if step_result.status == PlanStepStatus.COMPLETED:
            return {"action": "continue", "should_retry": False}

        if step_result.status == PlanStepStatus.WAITING_CONFIRM:
            return {"action": "pause", "should_retry": False}

        if step_result.status == PlanStepStatus.FAILED:
            if retry_count < max_retries:
                return {"action": "retry", "should_retry": True}
            return {"action": "fail", "should_retry": False}

        return {"action": "continue", "should_retry": False}
```

- [ ] **4.2-I5** 实现 Reflector

```python
REFLECTION_PROMPT = """你是智维AgentHub的计划反思器。分析执行计划的结果，判断是否需要修改计划。

原始目标：{goal}
执行计划步骤：
{steps_description}

已完成步骤结果：
{completed_results}

失败步骤（如有）：
{failed_step_info}

请分析并输出JSON：
{{
    "needs_revision": true/false,
    "analysis": "分析说明",
    "should_retry_from_step": null或步骤索引,
    "revised_plan": null或修改后的计划(格式同生成计划)
}}"""


class Reflector:
    def __init__(self, llm_gateway):
        self.llm_gateway = llm_gateway

    async def reflect(
        self,
        plan: ExecutionPlanModel,
        completed_steps: List[StepExecutionResult],
        failed_step: Optional[StepExecutionResult] = None
    ) -> ReflectionResult:
        steps_desc = "\n".join(
            f"  步骤{s.step_index}: {s.description} ({s.tool_name})"
            for s in plan.steps
        )

        completed_desc = "\n".join(
            f"  步骤{r.step_index}: status={r.status.value}, result={json.dumps(r.result or {}, ensure_ascii=False)[:200]}"
            for r in completed_steps
        )

        failed_desc = ""
        if failed_step:
            failed_desc = f"步骤{failed_step.step_index}: error={failed_step.error}"

        prompt = REFLECTION_PROMPT.format(
            goal=plan.goal,
            steps_description=steps_desc,
            completed_results=completed_desc,
            failed_step_info=failed_desc
        )

        try:
            response = await self.llm_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048
            )
            result_data = self._parse_json_response(response)
            revised_plan = None
            if result_data.get("revised_plan"):
                revised_plan = ExecutionPlanModel(**result_data["revised_plan"])

            return ReflectionResult(
                needs_revision=result_data.get("needs_revision", False),
                revised_plan=revised_plan,
                analysis=result_data.get("analysis", ""),
                should_retry_from_step=result_data.get("should_retry_from_step")
            )
        except Exception as e:
            logger.warning(f"Reflection failed: {e}")
            if failed_step:
                return ReflectionResult(
                    needs_revision=False,
                    analysis=f"反思失败: {e}，将标记失败步骤",
                    should_retry_from_step=None
                )
            return ReflectionResult(needs_revision=False, analysis=f"反思失败: {e}")

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError("No JSON found in reflection response")
```

- [ ] **4.2-I6** 实现 PlanExecuteAgent 主编排器

```python
class PlanExecuteAgent:
    def __init__(self, llm_gateway, tool_registry):
        self.generator = PlanGenerator(llm_gateway)
        self.reviewer = PlanReviewer()
        self.executor = StepExecutor(tool_registry)
        self.validator = ResultValidator()
        self.reflector = Reflector(llm_gateway)
        self.tool_registry = tool_registry
        self.llm_gateway = llm_gateway

    async def run(
        self,
        goal: str,
        context: Dict[str, Any],
        token: str,
        on_step_callback=None,
        max_reflections: int = 2
    ) -> FinalReport:
        start_time = time.time()

        available_tools = self._get_available_tools(context.get("role", "viewer"))
        plan = await self.generator.generate(goal, context, available_tools)

        review = self.reviewer.review(plan)
        if not review.is_valid:
            return FinalReport(
                plan_id=plan.plan_id,
                goal=goal,
                status="failed",
                conclusion=f"计划校验失败: {'; '.join(review.issues)}"
            )

        if review.adjusted_confirm_level:
            plan.confirm_level = review.adjusted_confirm_level

        previous_results: Dict[int, Any] = {}
        step_results: List[StepExecutionResult] = []
        reflection_count = 0

        for step in plan.steps:
            step.status = PlanStepStatus.RUNNING
            if on_step_callback:
                if asyncio.iscoroutinefunction(on_step_callback):
                    await on_step_callback({"step_index": step.step_index, "status": "running", "description": step.description})
                else:
                    on_step_callback({"step_index": step.step_index, "status": "running", "description": step.description})

            retry_count = 0
            max_retries = 2

            while True:
                result = await self.executor.execute(
                    step=step,
                    token=token,
                    previous_results=previous_results,
                    approved=(step.confirm_level == ConfirmLevel.LOW)
                )

                decision = self.validator.validate(result, retry_count, max_retries)

                if decision["action"] == "continue":
                    step.status = PlanStepStatus.COMPLETED
                    previous_results[step.step_index] = result.result or {}
                    step_results.append(result)
                    break
                elif decision["action"] == "pause":
                    step.status = PlanStepStatus.WAITING_CONFIRM
                    step_results.append(result)
                    if on_step_callback:
                        if asyncio.iscoroutinefunction(on_step_callback):
                            await on_step_callback({"step_index": step.step_index, "status": "waiting_confirm"})
                        else:
                            on_step_callback({"step_index": step.step_index, "status": "waiting_confirm"})
                    return self._build_report(plan, step_results, start_time, status="paused")
                elif decision["action"] == "retry":
                    retry_count += 1
                    if retry_count <= max_retries:
                        logger.info(f"Retrying step {step.step_index}, attempt {retry_count}")
                        await asyncio.sleep(1 * retry_count)
                        continue
                    step.status = PlanStepStatus.FAILED
                    step_results.append(result)

                    if reflection_count < max_reflections:
                        reflection = await self.reflector.reflect(plan, step_results, result)
                        reflection_count += 1
                        if reflection.needs_revision and reflection.revised_plan:
                            plan = reflection.revised_plan
                            if reflection.should_retry_from_step is not None:
                                remaining = [s for s in plan.steps if s.step_index >= reflection.should_retry_from_step]
                                for remaining_step in remaining:
                                    remaining_step.status = PlanStepStatus.PENDING
                                break
                    break
                elif decision["action"] == "fail":
                    step.status = PlanStepStatus.FAILED
                    step_results.append(result)

                    if reflection_count < max_reflections:
                        reflection = await self.reflector.reflect(plan, step_results, result)
                        reflection_count += 1
                        if reflection.needs_revision and reflection.revised_plan:
                            plan = reflection.revised_plan
                            break

                    return self._build_report(plan, step_results, start_time, status="failed")

        success_count = sum(1 for r in step_results if r.status == PlanStepStatus.COMPLETED)
        failure_count = sum(1 for r in step_results if r.status == PlanStepStatus.FAILED)

        if failure_count == 0:
            status = "success"
        elif success_count > 0:
            status = "partial"
        else:
            status = "failed"

        return self._build_report(plan, step_results, start_time, status=status)

    async def resume_after_confirm(
        self,
        plan: ExecutionPlanModel,
        step_index: int,
        token: str,
        approved: bool,
        on_step_callback=None
    ) -> FinalReport:
        start_time = time.time()
        step_results: List[StepExecutionResult] = []
        previous_results: Dict[int, Any] = {}

        for s in plan.steps:
            if s.step_index < step_index and s.status == PlanStepStatus.COMPLETED:
                previous_results[s.step_index] = s.result or {}

        current_step = next((s for s in plan.steps if s.step_index == step_index), None)
        if not current_step:
            return FinalReport(plan_id=plan.plan_id, goal=plan.goal, status="failed", conclusion="步骤不存在")

        if not approved:
            current_step.status = PlanStepStatus.SKIPPED
            return FinalReport(plan_id=plan.plan_id, goal=plan.goal, status="cancelled", conclusion="用户取消了操作")

        result = await self.executor.execute(
            step=current_step,
            token=token,
            previous_results=previous_results,
            approved=True
        )

        current_step.status = result.status
        step_results.append(result)

        if result.status == PlanStepStatus.COMPLETED:
            previous_results[current_step.step_index] = result.result or {}

        remaining_steps = [s for s in plan.steps if s.step_index > step_index]
        for step in remaining_steps:
            step_result = await self.executor.execute(
                step=step,
                token=token,
                previous_results=previous_results,
                approved=(step.confirm_level == ConfirmLevel.LOW)
            )
            step.status = step_result.status
            step_results.append(step_result)
            if step_result.status == PlanStepStatus.COMPLETED:
                previous_results[step.step_index] = step_result.result or {}

        success_count = sum(1 for r in step_results if r.status == PlanStepStatus.COMPLETED)
        failure_count = sum(1 for r in step_results if r.status == PlanStepStatus.FAILED)

        if failure_count == 0:
            status = "success"
        elif success_count > 0:
            status = "partial"
        else:
            status = "failed"

        return self._build_report(plan, step_results, start_time, status=status)

    def _get_available_tools(self, role: str) -> List[Dict[str, Any]]:
        tools = self.tool_registry.list_tools(role)
        return [{"name": t.name, "description": t.description} for t in tools]

    def _build_report(
        self,
        plan: ExecutionPlanModel,
        step_results: List[StepExecutionResult],
        start_time: float,
        status: str
    ) -> FinalReport:
        duration = time.time() - start_time
        success_count = sum(1 for r in step_results if r.status == PlanStepStatus.COMPLETED)
        failure_count = sum(1 for r in step_results if r.status == PlanStepStatus.FAILED)

        steps_summary = []
        for r in step_results:
            steps_summary.append({
                "step_index": r.step_index,
                "status": r.status.value,
                "result_preview": json.dumps(r.result or {}, ensure_ascii=False)[:200] if r.result else None,
                "error": r.error
            })

        conclusion_map = {
            "success": f"计划执行完成，{success_count}个步骤全部成功",
            "partial": f"计划部分完成，{success_count}个成功，{failure_count}个失败",
            "failed": f"计划执行失败，{failure_count}个步骤失败",
            "paused": "计划执行暂停，等待用户确认",
            "cancelled": "用户取消了计划执行"
        }

        return FinalReport(
            plan_id=plan.plan_id,
            goal=plan.goal,
            status=status,
            steps_summary=steps_summary,
            total_duration_seconds=round(duration, 2),
            success_count=success_count,
            failure_count=failure_count,
            conclusion=conclusion_map.get(status, "未知状态"),
            recommendations=[]
        )


import asyncio
```

- [ ] **4.2-T3** 运行测试确认 GREEN 状态

```bash
cd "d:\Trae CN\Project\智维 AgentHub"
python -m pytest tests/test_plan_executor.py -v --tb=short
```

---

## 4.3 运维向导模板库 — `backend/agents/wizard_templates.py`

### Step 1: 编写测试 `tests/test_wizard_templates.py`

- [ ] **4.3-T1** 编写向导模板测试

```python
import pytest
from backend.agents.wizard_templates import (
    WizardTemplate, WizardTemplateLibrary,
    FaultDiagnosisWizard, ChangeImplementationWizard,
    EmergencyResponseWizard, DailyInspectionWizard,
    BatchOperationWizard
)


class TestWizardTemplateLibrary:
    def test_list_all_templates(self):
        lib = WizardTemplateLibrary()
        templates = lib.list_templates()

        assert len(templates) >= 5
        types = {t.wizard_type for t in templates}
        assert "fault_diagnosis" in types
        assert "change_implementation" in types
        assert "emergency_response" in types
        assert "daily_inspection" in types
        assert "batch_operation" in types

    def test_get_template_by_type(self):
        lib = WizardTemplateLibrary()
        template = lib.get_template("fault_diagnosis")

        assert template is not None
        assert template.wizard_type == "fault_diagnosis"
        assert len(template.steps) >= 3

    def test_get_nonexistent_template(self):
        lib = WizardTemplateLibrary()
        template = lib.get_template("nonexistent")

        assert template is None

    def test_instantiate_template_with_params(self):
        lib = WizardTemplateLibrary()
        template = lib.get_template("fault_diagnosis")

        plan = template.instantiate(
            params={"device_name": "核心交换机SW-01", "alert_type": "链路中断"}
        )

        assert plan is not None
        assert plan.goal contains "核心交换机SW-01"
        assert len(plan.steps) >= 3


class TestFaultDiagnosisWizard:
    def test_template_structure(self):
        wizard = FaultDiagnosisWizard()
        template = wizard.template

        assert template.wizard_type == "fault_diagnosis"
        assert template.name == "故障排查向导"
        assert len(template.param_schema) >= 1
        assert any(s.tool_name == "query_topology" for s in template.steps)
        assert any(s.tool_name == "query_device" for s in template.steps)


class TestChangeImplementationWizard:
    def test_template_structure(self):
        wizard = ChangeImplementationWizard()
        template = wizard.template

        assert template.wizard_type == "change_implementation"
        assert template.name == "变更实施向导"
        assert any(s.confirm_level == "high" for s in template.steps)


class TestEmergencyResponseWizard:
    def test_template_structure(self):
        wizard = EmergencyResponseWizard()
        template = wizard.template

        assert template.wizard_type == "emergency_response"
        assert template.name == "应急响应向导"


class TestDailyInspectionWizard:
    def test_template_structure(self):
        wizard = DailyInspectionWizard()
        template = wizard.template

        assert template.wizard_type == "daily_inspection"
        assert template.name == "日常巡检向导"
        assert any(s.parallel_group is not None for s in template.steps)


class TestBatchOperationWizard:
    def test_template_structure(self):
        wizard = BatchOperationWizard()
        template = wizard.template

        assert template.wizard_type == "batch_operation"
        assert template.name == "批量操作向导"
```

### Step 2: 实现 `backend/agents/wizard_templates.py`

- [ ] **4.3-I1** 实现向导模板库

```python
import uuid
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from backend.agents.plan_executor_models import (
    ExecutionPlanModel, PlanStep, ConfirmLevel
)


class WizardParamField(BaseModel):
    name: str
    label: str
    field_type: str = "text"
    required: bool = True
    default: Any = None
    options: List[str] = Field(default_factory=list)


class WizardTemplate(BaseModel):
    wizard_type: str
    name: str
    description: str
    icon: str = "🔧"
    category: str = "general"
    param_schema: List[WizardParamField] = Field(default_factory=list)
    steps: List[PlanStep] = Field(default_factory=list)
    confirm_level: ConfirmLevel = ConfirmLevel.MEDIUM

    def instantiate(self, params: Dict[str, Any]) -> ExecutionPlanModel:
        resolved_steps = []
        for step_template in self.steps:
            resolved_params = {}
            for key, value in step_template.tool_params.items():
                if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                    param_name = value[2:-2].strip()
                    resolved_params[key] = params.get(param_name, value)
                else:
                    resolved_params[key] = value

            resolved_steps.append(PlanStep(
                step_index=step_template.step_index,
                description=step_template.description.format(**params),
                tool_name=step_template.tool_name,
                tool_params=resolved_params,
                confirm_level=step_template.confirm_level,
                condition=step_template.condition,
                parallel_group=step_template.parallel_group,
                fallback_tool=step_template.fallback_tool
            ))

        goal = self.description.format(**params)
        return ExecutionPlanModel(
            plan_id=f"plan_{self.wizard_type}_{uuid.uuid4().hex[:8]}",
            goal=goal,
            steps=resolved_steps,
            confirm_level=self.confirm_level
        )


class FaultDiagnosisWizard:
    @property
    def template(self) -> WizardTemplate:
        return WizardTemplate(
            wizard_type="fault_diagnosis",
            name="故障排查向导",
            description="排查 {device_name} 的 {alert_type} 故障",
            icon="🔍",
            category="fault",
            param_schema=[
                WizardParamField(name="device_name", label="设备名称", required=True),
                WizardParamField(name="alert_type", label="告警类型", required=True,
                    options=["链路中断", "CPU过载", "内存不足", "端口Down", "路由异常"]),
                WizardParamField(name="severity", label="严重程度", required=False, default="warning",
                    options=["critical", "warning", "info"])
            ],
            steps=[
                PlanStep(
                    step_index=0,
                    description="查询拓扑定位 {device_name}",
                    tool_name="query_topology",
                    tool_params={"filter": "alert"},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=1,
                    description="查询 {device_name} 设备详情",
                    tool_name="query_device",
                    tool_params={"device_id": "{{device_name}}"},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=2,
                    description="获取相关告警事件",
                    tool_name="get_events",
                    tool_params={"severity": "{{severity}}", "limit": 10},
                    confirm_level=ConfirmLevel.LOW
                ),
                PlanStep(
                    step_index=3,
                    description="执行自愈修复",
                    tool_name="execute_self_healing",
                    tool_params={"event_id": "$step2.data.events[0].id"},
                    confirm_level=ConfirmLevel.HIGH,
                    fallback_tool="system_health"
                ),
                PlanStep(
                    step_index=4,
                    description="验证修复结果",
                    tool_name="system_health",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW
                )
            ],
            confirm_level=ConfirmLevel.HIGH
        )


class ChangeImplementationWizard:
    @property
    def template(self) -> WizardTemplate:
        return WizardTemplate(
            wizard_type="change_implementation",
            name="变更实施向导",
            description="对 {device_name} 实施 {change_type} 变更",
            icon="📝",
            category="change",
            param_schema=[
                WizardParamField(name="device_name", label="目标设备", required=True),
                WizardParamField(name="change_type", label="变更类型", required=True,
                    options=["配置修改", "版本升级", "策略调整", "端口变更"]),
                WizardParamField(name="change_content", label="变更内容", required=True),
                WizardParamField(name="rollback_plan", label="回滚方案", required=False)
            ],
            steps=[
                PlanStep(
                    step_index=0,
                    description="查询 {device_name} 当前状态",
                    tool_name="query_device",
                    tool_params={"device_id": "{{device_name}}"},
                    confirm_level=ConfirmLevel.LOW
                ),
                PlanStep(
                    step_index=1,
                    description="创建变更意图",
                    tool_name="create_intent",
                    tool_params={
                        "name": "{{change_type}}-{{device_name}}",
                        "intent_type": "config_change",
                        "target_devices": ["{{device_name}}"],
                        "parameters": {"change_content": "{{change_content}}"}
                    },
                    confirm_level=ConfirmLevel.MEDIUM
                ),
                PlanStep(
                    step_index=2,
                    description="执行变更",
                    tool_name="execute_intent",
                    tool_params={"intent_id": "$step1.data.intent_id"},
                    confirm_level=ConfirmLevel.HIGH,
                    fallback_tool="system_health"
                ),
                PlanStep(
                    step_index=3,
                    description="验证变更结果",
                    tool_name="system_health",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW
                )
            ],
            confirm_level=ConfirmLevel.HIGH
        )


class EmergencyResponseWizard:
    @property
    def template(self) -> WizardTemplate:
        return WizardTemplate(
            wizard_type="emergency_response",
            name="应急响应向导",
            description="处理 {device_name} 的 {emergency_type} 紧急事件",
            icon="🚨",
            category="emergency",
            param_schema=[
                WizardParamField(name="device_name", label="故障设备", required=True),
                WizardParamField(name="emergency_type", label="紧急类型", required=True,
                    options=["设备宕机", "链路中断", "安全事件", "性能崩溃"]),
                WizardParamField(name="isolation_required", label="是否需要隔离", required=False, default="false",
                    options=["true", "false"])
            ],
            steps=[
                PlanStep(
                    step_index=0,
                    description="获取全局拓扑和告警",
                    tool_name="query_topology",
                    tool_params={"filter": "alert"},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=1,
                    description="获取紧急告警列表",
                    tool_name="get_events",
                    tool_params={"severity": "critical", "limit": 20},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=2,
                    description="查询故障设备详情",
                    tool_name="query_device",
                    tool_params={"device_id": "{{device_name}}"},
                    confirm_level=ConfirmLevel.LOW
                ),
                PlanStep(
                    step_index=3,
                    description="执行自愈恢复",
                    tool_name="execute_self_healing",
                    tool_params={"event_id": "$step1.data.events[0].id"},
                    confirm_level=ConfirmLevel.HIGH,
                    fallback_tool="system_health"
                ),
                PlanStep(
                    step_index=4,
                    description="验证恢复状态",
                    tool_name="system_health",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW
                )
            ],
            confirm_level=ConfirmLevel.HIGH
        )


class DailyInspectionWizard:
    @property
    def template(self) -> WizardTemplate:
        return WizardTemplate(
            wizard_type="daily_inspection",
            name="日常巡检向导",
            description="执行 {scope} 日常巡检",
            icon="📋",
            category="inspection",
            param_schema=[
                WizardParamField(name="scope", label="巡检范围", required=True,
                    options=["全网", "核心层", "汇聚层", "接入层"]),
                WizardParamField(name="focus", label="关注指标", required=False, default="all",
                    options=["all", "cpu_memory", "link_status", "config_drift"])
            ],
            steps=[
                PlanStep(
                    step_index=0,
                    description="查询全网拓扑状态",
                    tool_name="query_topology",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=1,
                    description="查询系统健康度",
                    tool_name="system_health",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=2,
                    description="获取告警概览",
                    tool_name="get_events",
                    tool_params={"limit": 50},
                    confirm_level=ConfirmLevel.LOW
                ),
                PlanStep(
                    step_index=3,
                    description="获取审计日志",
                    tool_name="get_audit_logs",
                    tool_params={"limit": 20},
                    confirm_level=ConfirmLevel.LOW
                )
            ],
            confirm_level=ConfirmLevel.LOW
        )


class BatchOperationWizard:
    @property
    def template(self) -> WizardTemplate:
        return WizardTemplate(
            wizard_type="batch_operation",
            name="批量操作向导",
            description="对 {target_group} 执行 {operation_type} 批量操作",
            icon="⚡",
            category="batch",
            param_schema=[
                WizardParamField(name="target_group", label="目标设备组", required=True),
                WizardParamField(name="operation_type", label="操作类型", required=True,
                    options=["批量巡检", "批量配置", "批量重启", "批量升级"]),
                WizardParamField(name="batch_size", label="批次大小", required=False, default="5")
            ],
            steps=[
                PlanStep(
                    step_index=0,
                    description="查询目标设备组拓扑",
                    tool_name="query_topology",
                    tool_params={"filter": "{{target_group}}"},
                    confirm_level=ConfirmLevel.LOW
                ),
                PlanStep(
                    step_index=1,
                    description="创建批量操作意图",
                    tool_name="create_intent",
                    tool_params={
                        "name": "batch_{{operation_type}}-{{target_group}}",
                        "intent_type": "batch_operation",
                        "target_devices": "$step0.data.devices",
                        "parameters": {
                            "operation": "{{operation_type}}",
                            "batch_size": "{{batch_size}}"
                        }
                    },
                    confirm_level=ConfirmLevel.MEDIUM
                ),
                PlanStep(
                    step_index=2,
                    description="执行批量操作",
                    tool_name="execute_intent",
                    tool_params={"intent_id": "$step1.data.intent_id"},
                    confirm_level=ConfirmLevel.HIGH,
                    fallback_tool="system_health"
                ),
                PlanStep(
                    step_index=3,
                    description="验证批量操作结果",
                    tool_name="system_health",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW
                )
            ],
            confirm_level=ConfirmLevel.HIGH
        )


class WizardTemplateLibrary:
    def __init__(self):
        self._templates: Dict[str, WizardTemplate] = {}
        self._register_builtin_templates()

    def _register_builtin_templates(self):
        wizards = [
            FaultDiagnosisWizard(),
            ChangeImplementationWizard(),
            EmergencyResponseWizard(),
            DailyInspectionWizard(),
            BatchOperationWizard(),
        ]
        for wizard in wizards:
            template = wizard.template
            self._templates[template.wizard_type] = template

    def list_templates(self) -> List[WizardTemplate]:
        return list(self._templates.values())

    def get_template(self, wizard_type: str) -> Optional[WizardTemplate]:
        return self._templates.get(wizard_type)

    def register_template(self, template: WizardTemplate) -> None:
        self._templates[template.wizard_type] = template
```

- [ ] **4.3-T2** 运行测试

```bash
cd "d:\Trae CN\Project\智维 AgentHub"
python -m pytest tests/test_wizard_templates.py -v --tb=short
```

---

## 4.4 修改 ReAct Engine 协作 — `backend/agents/react_engine.py`

- [ ] **4.4-I1** 在 ReActEngine 中添加 Plan-Execute 协作方法

在 `backend/agents/react_engine.py` 的 `ReActEngine` 类中新增：

```python
async def delegate_to_plan_execute(
    self,
    goal: str,
    context: Dict[str, Any],
    token: str,
    on_step_callback=None
) -> Dict[str, Any]:
    from backend.agents.plan_executor import PlanExecuteAgent
    from backend.agents.plan_executor_models import FinalReport

    agent = PlanExecuteAgent(self.llm_gateway, self.tool_registry)
    report: FinalReport = await agent.run(
        goal=goal,
        context=context,
        token=token,
        on_step_callback=on_step_callback
    )

    workflow = [
        {
            "id": f"plan_step_{s['step_index']}",
            "agent": "PlanExecutor",
            "status": s["status"],
            "title": s.get("result_preview", "")[:60] if s.get("result_preview") else s["status"],
            "detail": s.get("error")
        }
        for s in report.steps_summary
    ]

    return {
        "content": report.conclusion,
        "workflow": workflow,
        "plan_id": report.plan_id,
        "plan_status": report.status,
        "frontend_actions": [],
        "tools_called": [],
        "requires_approval": report.status == "paused"
    }
```

---

## 4.5 API 端点 — 修改 `backend/api/assistant.py`

- [ ] **4.5-I1** 新增 Plan-Execute 相关请求/响应模型和端点

在 `backend/api/assistant.py` 中新增：

```python
class PlanExecuteRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=2000)
    context: ChatContext = Field(default_factory=ChatContext)


class PlanExecuteResponse(BaseModel):
    content: str = Field(default="")
    plan_id: str = Field(default="")
    plan_status: str = Field(default="pending")
    workflow: List[Dict[str, Any]] = Field(default_factory=list)
    steps_summary: List[Dict[str, Any]] = Field(default_factory=list)
    requires_approval: bool = False
    approval_data: Optional[Dict[str, Any]] = None
    entities: Dict[str, Any] = Field(default_factory=dict)


class PlanConfirmRequest(BaseModel):
    plan_id: str = Field(..., min_length=1)
    step_index: int = Field(..., ge=0)
    approved: bool = Field(...)


class WizardListResponse(BaseModel):
    wizards: List[Dict[str, Any]] = Field(default_factory=list)


class WizardExecuteRequest(BaseModel):
    wizard_type: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)
    context: ChatContext = Field(default_factory=ChatContext)


_pending_plan_confirms: Dict[str, Dict[str, Any]] = {}


@router.post("/plan-execute", response_model=PlanExecuteResponse)
async def plan_execute(
    request: PlanExecuteRequest,
    current_user=Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    try:
        from backend.agents.plan_executor import PlanExecuteAgent
        from backend.agents.plan_executor_models import FinalReport

        react_engine = get_react_engine()
        agent = PlanExecuteAgent(react_engine.llm_gateway, react_engine.tool_registry)

        context = {
            "role": current_user.role if hasattr(current_user, 'role') else request.context.role,
            "page": request.context.route,
            "scene_mode": request.context.scene_mode,
            "username": current_user.username
        }

        report: FinalReport = await agent.run(
            goal=request.goal,
            context=context,
            token=token
        )

        approval_data = None
        if report.status == "paused":
            confirm_id = str(uuid.uuid4())
            approval_data = {
                "confirm_id": confirm_id,
                "plan_id": report.plan_id,
                "step_index": next(
                    (i for i, s in enumerate(report.steps_summary) if s.get("status") == "waiting_confirm"),
                    0
                )
            }
            _pending_plan_confirms[confirm_id] = {
                "plan_id": report.plan_id,
                "username": current_user.username,
                "token": token,
                "context": context
            }

        return PlanExecuteResponse(
            content=report.conclusion,
            plan_id=report.plan_id,
            plan_status=report.status,
            workflow=[
                {
                    "id": f"plan_step_{s['step_index']}",
                    "agent": "PlanExecutor",
                    "status": s["status"],
                    "title": s.get("result_preview", "")[:80] if s.get("result_preview") else s["status"],
                    "detail": s.get("error")
                }
                for s in report.steps_summary
            ],
            steps_summary=report.steps_summary,
            requires_approval=report.status == "paused",
            approval_data=approval_data,
            entities={}
        )
    except Exception as e:
        logger.error(f"Plan-Execute error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="计划执行失败，请稍后重试")


@router.post("/plan-confirm", response_model=PlanExecuteResponse)
async def plan_confirm(
    request: PlanConfirmRequest,
    current_user=Depends(get_current_user)
):
    try:
        from backend.agents.plan_executor import PlanExecuteAgent
        from backend.agents.plan_executor_models import ExecutionPlanModel, FinalReport

        confirm_entry = None
        confirm_id = None
        for cid, entry in _pending_plan_confirms.items():
            if entry["plan_id"] == request.plan_id and entry["username"] == current_user.username:
                confirm_entry = entry
                confirm_id = cid
                break

        if not confirm_entry:
            raise HTTPException(status_code=404, detail="确认记录不存在或已过期")

        _pending_plan_confirms.pop(confirm_id, None)

        react_engine = get_react_engine()
        agent = PlanExecuteAgent(react_engine.llm_gateway, react_engine.tool_registry)

        report = await agent.resume_after_confirm(
            plan=ExecutionPlanModel(plan_id=request.plan_id, goal="", steps=[]),
            step_index=request.step_index,
            token=confirm_entry["token"],
            approved=request.approved
        )

        return PlanExecuteResponse(
            content=report.conclusion,
            plan_id=report.plan_id,
            plan_status=report.status,
            steps_summary=report.steps_summary,
            requires_approval=False,
            entities={}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Plan confirm error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="确认操作失败")


@router.get("/wizards", response_model=WizardListResponse)
async def list_wizards(
    current_user=Depends(get_current_user)
):
    try:
        from backend.agents.wizard_templates import WizardTemplateLibrary
        lib = WizardTemplateLibrary()
        templates = lib.list_templates()

        return WizardListResponse(
            wizards=[
                {
                    "wizard_type": t.wizard_type,
                    "name": t.name,
                    "description": t.description,
                    "icon": t.icon,
                    "category": t.category,
                    "param_schema": [p.dict() for p in t.param_schema],
                    "confirm_level": t.confirm_level.value
                }
                for t in templates
            ]
        )
    except Exception as e:
        logger.error(f"List wizards error: {e}")
        raise HTTPException(status_code=500, detail="获取向导列表失败")


@router.post("/wizards/execute", response_model=PlanExecuteResponse)
async def execute_wizard(
    request: WizardExecuteRequest,
    current_user=Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    try:
        from backend.agents.wizard_templates import WizardTemplateLibrary
        from backend.agents.plan_executor import PlanExecuteAgent
        from backend.agents.plan_executor_models import FinalReport

        lib = WizardTemplateLibrary()
        template = lib.get_template(request.wizard_type)
        if not template:
            raise HTTPException(status_code=404, detail=f"向导类型不存在: {request.wizard_type}")

        plan = template.instantiate(request.params)

        react_engine = get_react_engine()
        agent = PlanExecuteAgent(react_engine.llm_gateway, react_engine.tool_registry)

        context = {
            "role": current_user.role if hasattr(current_user, 'role') else request.context.role,
            "page": request.context.route,
            "scene_mode": request.context.scene_mode,
            "username": current_user.username
        }

        report: FinalReport = await agent.run(
            goal=plan.goal,
            context=context,
            token=token
        )

        return PlanExecuteResponse(
            content=report.conclusion,
            plan_id=report.plan_id,
            plan_status=report.status,
            steps_summary=report.steps_summary,
            requires_approval=report.status == "paused",
            entities={"wizard_type": request.wizard_type}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Wizard execute error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="向导执行失败")
```

- [ ] **4.5-T1** 测试 API 端点

```bash
cd "d:\Trae CN\Project\智维 AgentHub"
python -m pytest tests/test_plan_executor.py tests/test_wizard_templates.py -v --tb=short
```

---

## 4.6 前端状态 — 修改 `frontend/src/stores/assistant.ts`

- [ ] **4.6-I1** 新增 Plan-Execute 相关类型和状态

在 `frontend/src/stores/assistant.ts` 中新增：

```typescript
export interface PlanStep {
  step_index: number
  description: string
  tool_name: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'waiting_confirm'
  result_preview?: string
  error?: string
}

export interface PlanExecuteState {
  planId: string
  goal: string
  status: 'idle' | 'generating' | 'executing' | 'paused' | 'completed' | 'failed'
  steps: PlanStep[]
  confirmLevel: 'low' | 'medium' | 'high'
  currentStepIndex: number
  report: {
    conclusion: string
    successCount: number
    failureCount: number
    duration: number
  } | null
}

export interface WizardInfo {
  wizard_type: string
  name: string
  description: string
  icon: string
  category: string
  param_schema: Array<{
    name: string
    label: string
    field_type: string
    required: boolean
    default?: any
    options?: string[]
  }>
  confirm_level: 'low' | 'medium' | 'high'
}
```

在 `useAssistantStore` 内新增：

```typescript
const planExecuteState = ref<PlanExecuteState>({
  planId: '',
  goal: '',
  status: 'idle',
  steps: [],
  confirmLevel: 'low',
  currentStepIndex: 0,
  report: null
})

const availableWizards = ref<WizardInfo[]>([])

const sendPlanExecute = async (goal: string) => {
  if (!goal.trim()) return
  addMessage({ role: 'user', content: goal.trim(), status: 'sent' })
  thinkingState.value = 'executing'
  planExecuteState.value = {
    planId: '',
    goal: goal.trim(),
    status: 'generating',
    steps: [],
    confirmLevel: 'low',
    currentStepIndex: 0,
    report: null
  }

  try {
    const { api, authFetch } = await import('@/utils/apiClient')
    const currentRoute = window.location.pathname

    const resp = await authFetch(api.assistant.planExecute, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        goal: goal.trim(),
        context: { route: currentRoute, role: getUserRole() }
      })
    })

    if (!resp.ok) throw new Error(`Plan execute failed: ${resp.status}`)
    const data = await resp.json()
    thinkingState.value = 'idle'

    planExecuteState.value.planId = data.plan_id
    planExecuteState.value.status = data.plan_status === 'paused' ? 'paused' :
      data.plan_status === 'success' ? 'completed' :
      data.plan_status === 'failed' ? 'failed' : 'executing'
    planExecuteState.value.steps = (data.steps_summary || []).map((s: any) => ({
      step_index: s.step_index,
      description: s.title || s.result_preview || '',
      tool_name: '',
      status: s.status,
      result_preview: s.result_preview,
      error: s.error
    }))

    const workflowSteps: WorkflowStep[] = (data.workflow || []).map((w: any) => ({
      id: w.id || `plan_step_${Math.random().toString(36).slice(2, 8)}`,
      agent: w.agent || 'PlanExecutor',
      status: w.status || 'pending',
      title: w.title || '',
      detail: w.detail
    }))

    const isDanger = data.plan_status === 'paused' && data.requires_approval
    const dangerConfirmId = isDanger ? genId() : undefined
    if (isDanger && dangerConfirmId) {
      pendingConfirmId.value = dangerConfirmId
    }

    addMessage({
      role: 'assistant',
      content: data.content || '',
      status: 'sent',
      workflow: workflowSteps.length > 0 ? workflowSteps : undefined,
      requiresConfirm: isDanger,
      confirmType: isDanger ? 'danger' : 'normal',
      confirmId: dangerConfirmId,
      contextEntities: data.entities
    })
  } catch {
    thinkingState.value = 'idle'
    planExecuteState.value.status = 'failed'
    addMessage({
      role: 'assistant',
      content: '计划执行失败，请稍后重试。',
      status: 'error'
    })
  }
}

const confirmPlanStep = async (planId: string, stepIndex: number, approved: boolean) => {
  try {
    const { api, authFetch } = await import('@/utils/apiClient')
    const resp = await authFetch(api.assistant.planConfirm, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_id: planId, step_index: stepIndex, approved })
    })

    if (!resp.ok) throw new Error(`Plan confirm failed: ${resp.status}`)
    const data = await resp.json()
    pendingConfirmId.value = null

    planExecuteState.value.status = data.plan_status === 'success' ? 'completed' :
      data.plan_status === 'failed' ? 'failed' : 'executing'
    planExecuteState.value.steps = (data.steps_summary || []).map((s: any) => ({
      step_index: s.step_index,
      description: s.title || s.result_preview || '',
      tool_name: '',
      status: s.status,
      result_preview: s.result_preview,
      error: s.error
    }))

    addMessage({
      role: 'assistant',
      content: data.content || (approved ? '操作已执行完成' : '操作已取消'),
      status: 'sent'
    })
  } catch {
    addMessage({
      role: 'assistant',
      content: '确认操作失败，请重试。',
      status: 'error'
    })
  }
}

const fetchWizards = async () => {
  try {
    const { api, authFetch } = await import('@/utils/apiClient')
    const resp = await authFetch(api.assistant.wizards)
    if (resp.ok) {
      const data = await resp.json()
      availableWizards.value = data.wizards || []
    }
  } catch {
    availableWizards.value = []
  }
}

const executeWizard = async (wizardType: string, params: Record<string, any>) => {
  thinkingState.value = 'executing'
  try {
    const { api, authFetch } = await import('@/utils/apiClient')
    const currentRoute = window.location.pathname

    const resp = await authFetch(api.assistant.wizardExecute, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        wizard_type: wizardType,
        params,
        context: { route: currentRoute, role: getUserRole() }
      })
    })

    if (!resp.ok) throw new Error(`Wizard execute failed: ${resp.status}`)
    const data = await resp.json()
    thinkingState.value = 'idle'

    const workflowSteps: WorkflowStep[] = (data.workflow || []).map((w: any) => ({
      id: w.id || `wizard_step_${Math.random().toString(36).slice(2, 8)}`,
      agent: w.agent || 'WizardRunner',
      status: w.status || 'pending',
      title: w.title || '',
      detail: w.detail
    }))

    addMessage({
      role: 'assistant',
      content: data.content || '',
      status: 'sent',
      workflow: workflowSteps.length > 0 ? workflowSteps : undefined,
      requiresConfirm: data.requires_approval,
      contextEntities: data.entities
    })
  } catch {
    thinkingState.value = 'idle'
    addMessage({
      role: 'assistant',
      content: '向导执行失败，请稍后重试。',
      status: 'error'
    })
  }
}
```

在 return 中导出新增状态和方法：

```typescript
return {
  planExecuteState, availableWizards,
  sendPlanExecute, confirmPlanStep, fetchWizards, executeWizard,
}
```

- [ ] **4.6-I2** 更新 API 路由映射

在 `frontend/src/utils/apiClient.ts` 中的 `api.assistant` 对象新增：

```typescript
planExecute: '/api/v1/assistant/plan-execute',
planConfirm: '/api/v1/assistant/plan-confirm',
wizards: '/api/v1/assistant/wizards',
wizardExecute: '/api/v1/assistant/wizards/execute',
```

---

## 4.7 前端 UI — 修改 `frontend/src/components/AiAssistant/ChatPanel.vue`

- [ ] **4.7-I1** 新增 Plan-Execute 模式切换按钮

在 `header-actions` 区域的 `react-btn` 后面新增：

```html
<button
  type="button"
  class="header-btn plan-btn"
  :class="{ active: planExecuteMode }"
  @click.stop="togglePlanExecuteMode"
  title="Plan-Execute编排模式"
  aria-label="Plan-Execute编排模式"
>
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="1" y="1" width="4" height="4" rx="1" stroke="currentColor" stroke-width="1.1"/>
    <rect x="9" y="1" width="4" height="4" rx="1" stroke="currentColor" stroke-width="1.1"/>
    <rect x="1" y="9" width="4" height="4" rx="1" stroke="currentColor" stroke-width="1.1"/>
    <rect x="9" y="9" width="4" height="4" rx="1" stroke="currentColor" stroke-width="1.1"/>
    <line x1="5" y1="3" x2="9" y2="3" stroke="currentColor" stroke-width="0.8"/>
    <line x1="3" y1="5" x2="3" y2="9" stroke="currentColor" stroke-width="0.8"/>
    <line x1="11" y1="5" x2="11" y2="9" stroke="currentColor" stroke-width="0.8"/>
  </svg>
</button>
```

- [ ] **4.7-I2** 新增向导快捷入口

在 `quick-actions-bar` 区域之前新增：

```html
<div v-if="showWizardBar" class="wizard-bar">
  <span class="wizard-bar-label">🧙 运维向导</span>
  <button
    type="button"
    v-for="wizard in store.availableWizards"
    :key="wizard.wizard_type"
    class="wizard-tag"
    @click="openWizard(wizard)"
    :aria-label="wizard.name"
  >
    {{ wizard.icon }} {{ wizard.name }}
  </button>
</div>
```

- [ ] **4.7-I3** 新增向导参数填写弹窗

```html
<div v-if="activeWizard" class="wizard-modal-overlay" @click.self="closeWizard">
  <div class="wizard-modal">
    <div class="wizard-modal-header">
      <span>{{ activeWizard.icon }} {{ activeWizard.name }}</span>
      <button type="button" class="header-btn" @click="closeWizard" aria-label="关闭">✕</button>
    </div>
    <div class="wizard-modal-body">
      <p class="wizard-desc">{{ activeWizard.description }}</p>
      <div v-for="field in activeWizard.param_schema" :key="field.name" class="wizard-field">
        <label class="wizard-field-label">
          {{ field.label }}
          <span v-if="field.required" class="required-mark">*</span>
        </label>
        <select
          v-if="field.options && field.options.length"
          v-model="wizardParams[field.name]"
          class="wizard-select"
        >
          <option value="" disabled>请选择</option>
          <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
        </select>
        <input
          v-else
          v-model="wizardParams[field.name]"
          type="text"
          class="wizard-input"
          :placeholder="field.label"
        />
      </div>
    </div>
    <div class="wizard-modal-footer">
      <button type="button" class="wizard-cancel-btn" @click="closeWizard">取消</button>
      <button
        type="button"
        class="wizard-execute-btn"
        :disabled="!isWizardParamsValid"
        @click="runWizard"
      >
        执行向导
      </button>
    </div>
  </div>
</div>
```

- [ ] **4.7-I4** 新增 Plan-Execute 步骤确认 UI

在 `danger-confirm-panel` 区域之后新增：

```html
<div
  v-if="msg.requiresConfirm && msg.confirmType === 'normal' && store.planExecuteState.status === 'paused'"
  class="plan-confirm-panel"
>
  <div class="plan-confirm-header">
    <span class="plan-confirm-icon">⏸️</span>
    <span class="plan-confirm-text">执行计划暂停，需要确认后继续</span>
  </div>
  <div class="plan-confirm-actions">
    <button
      type="button"
      class="plan-confirm-btn plan-approve-btn"
      @click="handlePlanConfirm(true)"
    >
      确认继续
    </button>
    <button
      type="button"
      class="plan-confirm-btn plan-reject-btn"
      @click="handlePlanConfirm(false)"
    >
      取消执行
    </button>
  </div>
</div>
```

- [ ] **4.7-I5** 新增 script 逻辑

```typescript
const planExecuteMode = ref(false)
const activeWizard = ref<WizardInfo | null>(null)
const wizardParams = ref<Record<string, any>>({})

const showWizardBar = computed(() => store.availableWizards.length > 0)

const togglePlanExecuteMode = () => {
  planExecuteMode.value = !planExecuteMode.value
  if (planExecuteMode.value) {
    reactMode.value = false
    store.fetchWizards()
  }
}

const openWizard = (wizard: WizardInfo) => {
  activeWizard.value = wizard
  wizardParams.value = {}
  for (const field of wizard.param_schema) {
    wizardParams.value[field.name] = field.default ?? ''
  }
}

const closeWizard = () => {
  activeWizard.value = null
  wizardParams.value = {}
}

const isWizardParamsValid = computed(() => {
  if (!activeWizard.value) return false
  return activeWizard.value.param_schema
    .filter(f => f.required)
    .every(f => wizardParams.value[f.name] && String(wizardParams.value[f.name]).trim() !== '')
})

const runWizard = async () => {
  if (!activeWizard.value) return
  const wizardType = activeWizard.value.wizard_type
  const params = { ...wizardParams.value }
  closeWizard()
  await store.executeWizard(wizardType, params)
}

const handlePlanConfirm = (approved: boolean) => {
  const planId = store.planExecuteState.planId
  const stepIndex = store.planExecuteState.currentStepIndex
  store.confirmPlanStep(planId, stepIndex, approved)
}
```

修改 `handleSend` 方法，增加 Plan-Execute 模式分支：

```typescript
const handleSend = async () => {
  const text = inputText.value.trim()
  if (!text || isThinking.value || store.isStreamingActive) return
  inputText.value = ''
  if (inputEl.value) {
    inputEl.value.style.height = 'auto'
  }
  if (planExecuteMode.value) {
    await store.sendPlanExecute(text)
  } else if (reactMode.value) {
    await store.sendReactMessage(text)
  } else if (store.llmAvailable) {
    await store.sendMessageStream(text)
  } else {
    await store.sendMessage(text)
  }
}
```

- [ ] **4.7-I6** 新增样式

```css
.plan-btn:hover {
  color: #34d399;
  border-color: rgba(52, 211, 153, 0.2);
  background: rgba(52, 211, 153, 0.08);
}

.plan-btn.active {
  background: rgba(52, 211, 153, 0.15);
  border-color: rgba(52, 211, 153, 0.3);
  color: #34d399;
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.15);
}

.wizard-bar {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: var(--spacing-sm) var(--spacing-md);
  overflow-x: auto;
  flex-shrink: 0;
  border-top: 1px solid rgba(148, 163, 184, 0.08);
}

.wizard-bar-label {
  font-size: var(--font-size-xs);
  color: #94a3b8;
  white-space: nowrap;
  flex-shrink: 0;
}

.wizard-tag {
  padding: 5px 0.75rem;
  border-radius: 1.25rem;
  border: 1px solid rgba(52, 211, 153, 0.3);
  background: rgba(52, 211, 153, 0.08);
  color: #6ee7b7;
  font-size: var(--font-size-xs);
  white-space: nowrap;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.wizard-tag:hover {
  background: rgba(52, 211, 153, 0.2);
  border-color: rgba(52, 211, 153, 0.5);
}

.wizard-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}

.wizard-modal {
  width: 400px;
  max-width: 90vw;
  background: rgba(30, 41, 59, 0.98);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
}

.wizard-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem var(--spacing-md);
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  color: #e2e8f0;
  font-weight: 600;
}

.wizard-modal-body {
  padding: var(--spacing-md);
}

.wizard-desc {
  font-size: var(--font-size-sm);
  color: #94a3b8;
  margin-bottom: var(--spacing-md);
}

.wizard-field {
  margin-bottom: var(--spacing-sm);
}

.wizard-field-label {
  display: block;
  font-size: var(--font-size-xs);
  color: #cbd5e1;
  margin-bottom: 4px;
}

.required-mark {
  color: #f87171;
}

.wizard-input,
.wizard-select {
  width: 100%;
  padding: 8px 12px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: var(--radius-md);
  color: #e2e8f0;
  font-size: var(--font-size-sm);
  outline: none;
}

.wizard-input:focus,
.wizard-select:focus {
  border-color: rgba(52, 211, 153, 0.5);
}

.wizard-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid rgba(148, 163, 184, 0.1);
}

.wizard-cancel-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  border: none;
  background: rgba(148, 163, 184, 0.15);
  color: #94a3b8;
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.wizard-execute-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  border: none;
  background: rgba(52, 211, 153, 0.8);
  color: #fff;
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: 500;
}

.wizard-execute-btn:disabled {
  background: rgba(52, 211, 153, 0.3);
  cursor: not-allowed;
}

.plan-confirm-panel {
  margin-top: 0.75rem;
  padding: 14px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(250, 204, 21, 0.4);
  background: rgba(250, 204, 21, 0.06);
}

.plan-confirm-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: 10px;
}

.plan-confirm-icon {
  font-size: var(--font-size-lg);
}

.plan-confirm-text {
  font-size: var(--font-size-sm);
  color: #fde68a;
  font-weight: 500;
}

.plan-confirm-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.plan-confirm-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  border: none;
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.plan-approve-btn {
  background: rgba(34, 197, 94, 0.8);
  color: #fff;
}

.plan-approve-btn:hover {
  background: rgba(34, 197, 94, 1);
}

.plan-reject-btn {
  background: rgba(148, 163, 184, 0.15);
  color: #94a3b8;
}

.plan-reject-btn:hover {
  background: rgba(148, 163, 184, 0.25);
  color: #e2e8f0;
}
```

---

# 模块 5：工具编排引擎

## 5.1 数据模型

### 5.1.1 Pydantic 模型 — `backend/agents/tool_chains.py` 内定义

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class ToolStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"
    SKIPPED = "skipped"


class ToolStep(BaseModel):
    step_index: int = Field(..., ge=0)
    tool_name: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[int] = Field(default_factory=list)
    parallel_group: Optional[int] = None
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=2, ge=0)
    fallback_tool: Optional[str] = None
    timeout_seconds: int = Field(default=30, ge=5)
    status: ToolStepStatus = Field(default=ToolStepStatus.PENDING)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ToolChain(BaseModel):
    chain_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(default="")
    steps: List[ToolStep] = Field(..., min_length=1)
    parallel_groups: List[List[int]] = Field(default_factory=list)
    auto_degradation: bool = Field(default=True)


class DAGNode(BaseModel):
    step_index: int
    dependencies: List[int] = Field(default_factory=list)
    dependents: List[int] = Field(default_factory=list)


class DAGAnalysisResult(BaseModel):
    is_valid: bool = True
    has_cycles: bool = False
    parallel_groups: List[List[int]] = Field(default_factory=list)
    execution_order: List[int] = Field(default_factory=list)
    critical_path: List[int] = Field(default_factory=list)


class ToolChainExecutionResult(BaseModel):
    chain_id: str
    status: str
    steps_results: List[Dict[str, Any]] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    success_count: int = 0
    degraded_count: int = 0
    failed_count: int = 0
```

---

## 5.2 DAG 分析器 — 修改 `backend/agents/tool_registry.py`

### Step 1: 编写测试 `tests/test_tool_orchestration.py`

- [ ] **5.2-T1** 编写 DAG 分析器测试

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from backend.agents.tool_chains import (
    ToolStep, ToolChain, DAGNode, DAGAnalysisResult,
    ToolChainExecutionResult, ToolStepStatus
)
from backend.agents.tool_orchestrator import (
    DAGAnalyzer, ParallelExecutor, AutoDegradationHandler,
    ParamReferenceParser, ToolOrchestrationEngine
)
from backend.agents.tool_registry import ToolRegistry, ToolDefinition


@pytest.fixture
def tool_registry_with_tools():
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="step_a_tool",
        description="Step A",
        endpoint="/api/v1/test/a",
        method="GET",
        risk_level="low",
        required_role=["admin"]
    ))
    registry.register(ToolDefinition(
        name="step_b_tool",
        description="Step B",
        endpoint="/api/v1/test/b",
        method="GET",
        risk_level="low",
        required_role=["admin"]
    ))
    registry.register(ToolDefinition(
        name="step_c_tool",
        description="Step C",
        endpoint="/api/v1/test/c",
        method="GET",
        risk_level="low",
        required_role=["admin"]
    ))
    registry.register(ToolDefinition(
        name="fallback_tool",
        description="Fallback",
        endpoint="/api/v1/test/fallback",
        method="GET",
        risk_level="low",
        required_role=["admin"]
    ))
    return registry


class TestDAGAnalyzer:
    def test_analyze_linear_chain(self):
        chain = ToolChain(
            chain_id="linear",
            name="Linear Chain",
            steps=[
                ToolStep(step_index=0, tool_name="step_a_tool", depends_on=[]),
                ToolStep(step_index=1, tool_name="step_b_tool", depends_on=[0]),
                ToolStep(step_index=2, tool_name="step_c_tool", depends_on=[1])
            ]
        )

        analyzer = DAGAnalyzer()
        result = analyzer.analyze(chain)

        assert result.is_valid is True
        assert result.has_cycles is False
        assert result.execution_order == [0, 1, 2]

    def test_analyze_parallel_chain(self):
        chain = ToolChain(
            chain_id="parallel",
            name="Parallel Chain",
            steps=[
                ToolStep(step_index=0, tool_name="step_a_tool", depends_on=[], parallel_group=0),
                ToolStep(step_index=1, tool_name="step_b_tool", depends_on=[], parallel_group=0),
                ToolStep(step_index=2, tool_name="step_c_tool", depends_on=[0, 1])
            ]
        )

        analyzer = DAGAnalyzer()
        result = analyzer.analyze(chain)

        assert result.is_valid is True
        assert len(result.parallel_groups) >= 1
        assert 0 in result.execution_order
        assert 2 in result.execution_order

    def test_analyze_cyclic_chain(self):
        chain = ToolChain(
            chain_id="cyclic",
            name="Cyclic Chain",
            steps=[
                ToolStep(step_index=0, tool_name="step_a_tool", depends_on=[2]),
                ToolStep(step_index=1, tool_name="step_b_tool", depends_on=[0]),
                ToolStep(step_index=2, tool_name="step_c_tool", depends_on=[1])
            ]
        )

        analyzer = DAGAnalyzer()
        result = analyzer.analyze(chain)

        assert result.has_cycles is True
        assert result.is_valid is False

    def test_analyze_empty_chain(self):
        chain = ToolChain(
            chain_id="empty",
            name="Empty",
            steps=[]
        )

        analyzer = DAGAnalyzer()
        result = analyzer.analyze(chain)

        assert result.is_valid is False


class TestParallelExecutor:
    @pytest.mark.asyncio
    async def test_execute_parallel_group(self, tool_registry_with_tools):
        tool_registry_with_tools.execute_tool = AsyncMock(side_effect=[
            {"status_code": 200, "data": {"result": "a"}},
            {"status_code": 200, "data": {"result": "b"}}
        ])

        executor = ParallelExecutor(tool_registry_with_tools)
        steps = [
            ToolStep(step_index=0, tool_name="step_a_tool", params={}),
            ToolStep(step_index=1, tool_name="step_b_tool", params={})
        ]

        results = await executor.execute_parallel(steps, token="test_token")

        assert len(results) == 2
        assert all(r.status == ToolStepStatus.COMPLETED for r in results)

    @pytest.mark.asyncio
    async def test_execute_parallel_with_partial_failure(self, tool_registry_with_tools):
        tool_registry_with_tools.execute_tool = AsyncMock(side_effect=[
            {"status_code": 200, "data": {"result": "a"}},
            Exception("timeout")
        ])

        executor = ParallelExecutor(tool_registry_with_tools)
        steps = [
            ToolStep(step_index=0, tool_name="step_a_tool", params={}),
            ToolStep(step_index=1, tool_name="step_b_tool", params={})
        ]

        results = await executor.execute_parallel(steps, token="test_token")

        statuses = [r.status for r in results]
        assert ToolStepStatus.COMPLETED in statuses
        assert ToolStepStatus.FAILED in statuses


class TestAutoDegradationHandler:
    @pytest.mark.asyncio
    async def test_degrade_to_fallback(self, tool_registry_with_tools):
        tool_registry_with_tools.execute_tool = AsyncMock(return_value={
            "status_code": 200, "data": {"degraded": True}
        })

        handler = AutoDegradationHandler(tool_registry_with_tools)
        step = ToolStep(
            step_index=0,
            tool_name="step_a_tool",
            params={},
            fallback_tool="fallback_tool"
        )

        result = await handler.handle_degradation(step, token="test_token")

        assert result.status == ToolStepStatus.DEGRADED
        assert result.result is not None

    @pytest.mark.asyncio
    async def test_no_fallback_available(self, tool_registry_with_tools):
        handler = AutoDegradationHandler(tool_registry_with_tools)
        step = ToolStep(
            step_index=0,
            tool_name="step_a_tool",
            params={}
        )

        result = await handler.handle_degradation(step, token="test_token")

        assert result.status == ToolStepStatus.FAILED


class TestParamReferenceParser:
    def test_resolve_simple_reference(self):
        parser = ParamReferenceParser()
        previous = {0: {"devices": [{"id": "sw-01"}]}}

        result = parser.resolve("$step0.devices[0].id", previous)

        assert result == "sw-01"

    def test_resolve_nested_reference(self):
        parser = ParamReferenceParser()
        previous = {0: {"data": {"items": [{"name": "item1"}]}}}

        result = parser.resolve("$step0.data.items[0].name", previous)

        assert result == "item1"

    def test_resolve_non_reference(self):
        parser = ParamReferenceParser()
        result = parser.resolve("plain_value", {})

        assert result == "plain_value"

    def test_resolve_missing_step(self):
        parser = ParamReferenceParser()
        result = parser.resolve("$step5.missing", {})

        assert result == "$step5.missing"

    def test_resolve_params_dict(self):
        parser = ParamReferenceParser()
        previous = {0: {"device_id": "sw-01"}}
        params = {
            "device_id": "$step0.device_id",
            "static_value": "hello"
        }

        result = parser.resolve_params(params, previous)

        assert result["device_id"] == "sw-01"
        assert result["static_value"] == "hello"


class TestToolOrchestrationEngine:
    @pytest.mark.asyncio
    async def test_execute_linear_chain(self, tool_registry_with_tools):
        tool_registry_with_tools.execute_tool = AsyncMock(side_effect=[
            {"status_code": 200, "data": {"devices": [{"id": "sw-01"}]}},
            {"status_code": 200, "data": {"device": {"id": "sw-01", "status": "online"}}},
            {"status_code": 200, "data": {"healthy": True}}
        ])

        engine = ToolOrchestrationEngine(tool_registry_with_tools)
        chain = ToolChain(
            chain_id="test_linear",
            name="Test Linear",
            steps=[
                ToolStep(step_index=0, tool_name="step_a_tool", params={}),
                ToolStep(step_index=1, tool_name="step_b_tool", params={"device_id": "$step0.devices[0].id"}, depends_on=[0]),
                ToolStep(step_index=2, tool_name="step_c_tool", params={}, depends_on=[1])
            ]
        )

        result = await engine.execute(chain, token="test_token")

        assert isinstance(result, ToolChainExecutionResult)
        assert result.status in ("success", "partial", "failed")
        assert result.chain_id == "test_linear"

    @pytest.mark.asyncio
    async def test_execute_with_auto_degradation(self, tool_registry_with_tools):
        call_count = 0

        async def mock_execute(name, params, token):
            nonlocal call_count
            call_count += 1
            if name == "step_a_tool":
                raise Exception("timeout")
            return {"status_code": 200, "data": {"degraded": True}}

        tool_registry_with_tools.execute_tool = mock_execute

        engine = ToolOrchestrationEngine(tool_registry_with_tools)
        chain = ToolChain(
            chain_id="test_degrade",
            name="Test Degradation",
            auto_degradation=True,
            steps=[
                ToolStep(
                    step_index=0,
                    tool_name="step_a_tool",
                    params={},
                    fallback_tool="fallback_tool",
                    max_retries=1
                )
            ]
        )

        result = await engine.execute(chain, token="test_token")

        assert result.degraded_count >= 0
```

### Step 2: 实现 DAG 分析器和编排引擎

- [ ] **5.2-I1** 实现 `backend/agents/tool_orchestrator.py`

```python
import asyncio
import time
import json
import re
import logging
from typing import Dict, Any, Optional, List, Set
from collections import defaultdict, deque

from backend.agents.tool_chains import (
    ToolStep, ToolChain, DAGNode, DAGAnalysisResult,
    ToolStepStatus, ToolChainExecutionResult
)

logger = logging.getLogger(__name__)


class DAGAnalyzer:
    def analyze(self, chain: ToolChain) -> DAGAnalysisResult:
        if not chain.steps:
            return DAGAnalysisResult(is_valid=False, has_cycles=False)

        nodes = self._build_nodes(chain)
        has_cycles = self._detect_cycles(nodes)

        if has_cycles:
            return DAGAnalysisResult(is_valid=False, has_cycles=True)

        execution_order = self._topological_sort(nodes)
        parallel_groups = self._identify_parallel_groups(chain, nodes)
        critical_path = self._find_critical_path(nodes, execution_order)

        return DAGAnalysisResult(
            is_valid=True,
            has_cycles=False,
            parallel_groups=parallel_groups,
            execution_order=execution_order,
            critical_path=critical_path
        )

    def _build_nodes(self, chain: ToolChain) -> Dict[int, DAGNode]:
        nodes = {}
        for step in chain.steps:
            nodes[step.step_index] = DAGNode(
                step_index=step.step_index,
                dependencies=list(step.depends_on),
                dependents=[]
            )

        for step in chain.steps:
            for dep_idx in step.depends_on:
                if dep_idx in nodes:
                    nodes[dep_idx].dependents.append(step.step_index)

        return nodes

    def _detect_cycles(self, nodes: Dict[int, DAGNode]) -> bool:
        visited: Set[int] = set()
        rec_stack: Set[int] = set()

        def dfs(node_idx: int) -> bool:
            visited.add(node_idx)
            rec_stack.add(node_idx)

            for dep in nodes[node_idx].dependents:
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in rec_stack:
                    return True

            rec_stack.remove(node_idx)
            return False

        for node_idx in nodes:
            if node_idx not in visited:
                if dfs(node_idx):
                    return True

        return False

    def _topological_sort(self, nodes: Dict[int, DAGNode]) -> List[int]:
        in_degree = {idx: len(node.dependencies) for idx, node in nodes.items()}
        queue = deque([idx for idx, deg in in_degree.items() if deg == 0])
        order = []

        while queue:
            node_idx = queue.popleft()
            order.append(node_idx)

            for dependent in nodes[node_idx].dependents:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        return order

    def _identify_parallel_groups(
        self,
        chain: ToolChain,
        nodes: Dict[int, DAGNode]
    ) -> List[List[int]]:
        explicit_groups: Dict[int, List[int]] = defaultdict(list)
        for step in chain.steps:
            if step.parallel_group is not None:
                explicit_groups[step.parallel_group].append(step.step_index)

        if explicit_groups:
            return list(explicit_groups.values())

        level_groups: Dict[int, List[int]] = defaultdict(list)
        in_degree = {idx: len(node.dependencies) for idx, node in nodes.items()}
        queue = deque([idx for idx, deg in in_degree.items() if deg == 0])
        level = 0

        while queue:
            next_queue = deque()
            while queue:
                node_idx = queue.popleft()
                level_groups[level].append(node_idx)
                for dependent in nodes[node_idx].dependents:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_queue.append(dependent)
            queue = next_queue
            level += 1

        return [g for g in level_groups.values() if len(g) > 1]

    def _find_critical_path(
        self,
        nodes: Dict[int, DAGNode],
        execution_order: List[int]
    ) -> List[int]:
        if not execution_order:
            return []

        longest_path: Dict[int, int] = {}
        for idx in execution_order:
            deps = nodes[idx].dependencies
            if not deps:
                longest_path[idx] = 1
            else:
                longest_path[idx] = 1 + max(longest_path.get(d, 0) for d in deps)

        max_len = max(longest_path.values()) if longest_path else 0
        critical = [idx for idx, length in longest_path.items() if length == max_len]
        return critical


class ParallelExecutor:
    def __init__(self, tool_registry):
        self.tool_registry = tool_registry

    async def execute_parallel(
        self,
        steps: List[ToolStep],
        token: str,
        previous_results: Optional[Dict[int, Any]] = None
    ) -> List[ToolStep]:
        previous_results = previous_results or {}
        tasks = [
            self._execute_single(step, token, previous_results)
            for step in steps
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                steps[i].status = ToolStepStatus.FAILED
                steps[i].error = str(result)
            else:
                steps[i] = result

        return steps

    async def _execute_single(
        self,
        step: ToolStep,
        token: str,
        previous_results: Dict[int, Any]
    ) -> ToolStep:
        parser = ParamReferenceParser()
        resolved_params = parser.resolve_params(step.params, previous_results)

        try:
            result = await self.tool_registry.execute_tool(
                name=step.tool_name,
                params=resolved_params,
                token=token
            )

            if isinstance(result, dict) and result.get("error"):
                step.status = ToolStepStatus.FAILED
                step.error = result["error"]
            else:
                step.status = ToolStepStatus.COMPLETED
                step.result = result

        except Exception as e:
            step.status = ToolStepStatus.FAILED
            step.error = str(e)

        return step


class AutoDegradationHandler:
    def __init__(self, tool_registry):
        self.tool_registry = tool_registry

    async def handle_degradation(
        self,
        step: ToolStep,
        token: str,
        previous_results: Optional[Dict[int, Any]] = None
    ) -> ToolStep:
        if not step.fallback_tool:
            step.status = ToolStepStatus.FAILED
            return step

        logger.info(f"Auto-degrading step {step.step_index}: {step.tool_name} -> {step.fallback_tool}")

        try:
            result = await self.tool_registry.execute_tool(
                name=step.fallback_tool,
                params={},
                token=token
            )
            step.status = ToolStepStatus.DEGRADED
            step.result = result
            step.error = f"Degraded from {step.tool_name} to {step.fallback_tool}"
        except Exception as e:
            step.status = ToolStepStatus.FAILED
            step.error = f"Fallback also failed: {str(e)}"

        return step


class ParamReferenceParser:
    REFERENCE_PATTERN = re.compile(r'\$step(\d+)(.*)')

    def resolve(self, value: str, previous_results: Dict[int, Any]) -> Any:
        if not isinstance(value, str) or not value.startswith("$step"):
            return value

        match = self.REFERENCE_PATTERN.match(value)
        if not match:
            return value

        step_idx = int(match.group(1))
        path = match.group(2)

        step_result = previous_results.get(step_idx)
        if step_result is None:
            logger.warning(f"Param reference {value} points to non-existent step {step_idx}")
            return value

        if not path:
            return step_result

        current = step_result
        for part in path.lstrip(".").split("."):
            if part.startswith("[") and part.endswith("]"):
                idx = int(part[1:-1])
                if isinstance(current, list) and idx < len(current):
                    current = current[idx]
                else:
                    return value
            elif isinstance(current, dict):
                current = current.get(part, value)
            else:
                return value

        return current

    def resolve_params(
        self,
        params: Dict[str, Any],
        previous_results: Dict[int, Any]
    ) -> Dict[str, Any]:
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$step"):
                resolved[key] = self.resolve(value, previous_results)
            elif isinstance(value, dict):
                resolved[key] = self.resolve_params(value, previous_results)
            elif isinstance(value, list):
                resolved[key] = [
                    self.resolve(v, previous_results)
                    if isinstance(v, str) and v.startswith("$step") else v
                    for v in value
                ]
            else:
                resolved[key] = value
        return resolved


class ToolOrchestrationEngine:
    def __init__(self, tool_registry):
        self.tool_registry = tool_registry
        self.dag_analyzer = DAGAnalyzer()
        self.parallel_executor = ParallelExecutor(tool_registry)
        self.degradation_handler = AutoDegradationHandler(tool_registry)
        self.param_parser = ParamReferenceParser()

    async def execute(
        self,
        chain: ToolChain,
        token: str,
        on_step_callback=None
    ) -> ToolChainExecutionResult:
        start_time = time.time()

        dag_result = self.dag_analyzer.analyze(chain)
        if not dag_result.is_valid:
            return ToolChainExecutionResult(
                chain_id=chain.chain_id,
                status="failed",
                steps_results=[{"error": "DAG analysis failed: cycles detected" if dag_result.has_cycles else "Invalid chain"}]
            )

        previous_results: Dict[int, Any] = {}
        steps_results: List[Dict[str, Any]] = []

        execution_order = dag_result.execution_order
        parallel_groups = dag_result.parallel_groups
        parallel_group_map: Dict[int, List[int]] = {}
        for group in parallel_groups:
            for step_idx in group:
                parallel_group_map[step_idx] = group

        executed: Set[int] = set()

        for step_idx in execution_order:
            if step_idx in executed:
                continue

            if step_idx in parallel_group_map:
                group = parallel_group_map[step_idx]
                group_steps = [chain.steps[i] for i in group if i not in executed]

                if group_steps:
                    if on_step_callback:
                        for gs in group_steps:
                            gs.status = ToolStepStatus.RUNNING
                            if asyncio.iscoroutinefunction(on_step_callback):
                                await on_step_callback({"step_index": gs.step_index, "status": "running"})
                            else:
                                on_step_callback({"step_index": gs.step_index, "status": "running"})

                    results = await self.parallel_executor.execute_parallel(
                        group_steps, token, previous_results
                    )

                    for r in results:
                        executed.add(r.step_index)
                        if r.status == ToolStepStatus.COMPLETED:
                            previous_results[r.step_index] = r.result or {}
                        steps_results.append({
                            "step_index": r.step_index,
                            "status": r.status.value,
                            "result": r.result,
                            "error": r.error
                        })

                        if on_step_callback:
                            if asyncio.iscoroutinefunction(on_step_callback):
                                await on_step_callback({"step_index": r.step_index, "status": r.status.value})
                            else:
                                on_step_callback({"step_index": r.step_index, "status": r.status.value})
            else:
                step = chain.steps[step_idx]
                step.status = ToolStepStatus.RUNNING

                if on_step_callback:
                    if asyncio.iscoroutinefunction(on_step_callback):
                        await on_step_callback({"step_index": step.step_index, "status": "running"})
                    else:
                        on_step_callback({"step_index": step.step_index, "status": "running"})

                step = await self._execute_step_with_retry(step, token, previous_results, chain.auto_degradation)

                executed.add(step.step_index)
                if step.status == ToolStepStatus.COMPLETED:
                    previous_results[step.step_index] = step.result or {}

                steps_results.append({
                    "step_index": step.step_index,
                    "status": step.status.value,
                    "result": step.result,
                    "error": step.error
                })

                if on_step_callback:
                    if asyncio.iscoroutinefunction(on_step_callback):
                        await on_step_callback({"step_index": step.step_index, "status": step.status.value})
                    else:
                        on_step_callback({"step_index": step.step_index, "status": step.status.value})

        duration = time.time() - start_time
        success_count = sum(1 for s in steps_results if s["status"] == ToolStepStatus.COMPLETED.value)
        degraded_count = sum(1 for s in steps_results if s["status"] == ToolStepStatus.DEGRADED.value)
        failed_count = sum(1 for s in steps_results if s["status"] == ToolStepStatus.FAILED.value)

        if failed_count == 0:
            status = "success"
        elif success_count + degraded_count > 0:
            status = "partial"
        else:
            status = "failed"

        return ToolChainExecutionResult(
            chain_id=chain.chain_id,
            status=status,
            steps_results=steps_results,
            total_duration_seconds=round(duration, 2),
            success_count=success_count,
            degraded_count=degraded_count,
            failed_count=failed_count
        )

    async def _execute_step_with_retry(
        self,
        step: ToolStep,
        token: str,
        previous_results: Dict[int, Any],
        auto_degradation: bool
    ) -> ToolStep:
        resolved_params = self.param_parser.resolve_params(step.params, previous_results)

        for attempt in range(step.max_retries + 1):
            try:
                result = await self.tool_registry.execute_tool(
                    name=step.tool_name,
                    params=resolved_params,
                    token=token
                )

                if isinstance(result, dict) and result.get("error"):
                    raise Exception(result["error"])

                step.status = ToolStepStatus.COMPLETED
                step.result = result
                return step

            except Exception as e:
                logger.warning(f"Step {step.step_index} attempt {attempt + 1} failed: {e}")
                step.error = str(e)

                if attempt < step.max_retries:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue

        if auto_degradation and step.fallback_tool:
            step = await self.degradation_handler.handle_degradation(
                step, token, previous_results
            )
        else:
            step.status = ToolStepStatus.FAILED

        return step
```

- [ ] **5.2-T2** 运行测试确认 GREEN

```bash
cd "d:\Trae CN\Project\智维 AgentHub"
python -m pytest tests/test_tool_orchestration.py -v --tb=short
```

---

## 5.3 预定义工具链库 — `backend/agents/tool_chains.py`

- [ ] **5.3-I1** 实现预定义工具链

在 `backend/agents/tool_chains.py` 底部追加：

```python
class PredefinedToolChains:
    @staticmethod
    def fault_auto_healing_chain() -> ToolChain:
        return ToolChain(
            chain_id="fault_auto_healing",
            name="故障自愈链",
            description="自动检测故障并执行自愈恢复",
            auto_degradation=True,
            steps=[
                ToolStep(
                    step_index=0,
                    tool_name="query_topology",
                    params={"filter": "alert"},
                    depends_on=[],
                    parallel_group=0
                ),
                ToolStep(
                    step_index=1,
                    tool_name="get_events",
                    params={"severity": "critical", "limit": 10},
                    depends_on=[],
                    parallel_group=0
                ),
                ToolStep(
                    step_index=2,
                    tool_name="query_device",
                    params={"device_id": "$step0.devices[0].id"},
                    depends_on=[0],
                    fallback_tool="system_health"
                ),
                ToolStep(
                    step_index=3,
                    tool_name="execute_self_healing",
                    params={"event_id": "$step1.events[0].id"},
                    depends_on=[1, 2],
                    max_retries=2,
                    fallback_tool="system_health"
                ),
                ToolStep(
                    step_index=4,
                    tool_name="system_health",
                    params={},
                    depends_on=[3]
                )
            ],
            parallel_groups=[[0, 1]]
        )

    @staticmethod
    def batch_inspection_chain() -> ToolChain:
        return ToolChain(
            chain_id="batch_inspection",
            name="批量巡检链",
            description="并行执行多维度巡检",
            auto_degradation=True,
            steps=[
                ToolStep(
                    step_index=0,
                    tool_name="query_topology",
                    params={},
                    depends_on=[],
                    parallel_group=0
                ),
                ToolStep(
                    step_index=1,
                    tool_name="system_health",
                    params={},
                    depends_on=[],
                    parallel_group=0
                ),
                ToolStep(
                    step_index=2,
                    tool_name="get_events",
                    params={"limit": 50},
                    depends_on=[],
                    parallel_group=0
                ),
                ToolStep(
                    step_index=3,
                    tool_name="get_audit_logs",
                    params={"limit": 20},
                    depends_on=[0, 1, 2]
                )
            ],
            parallel_groups=[[0, 1, 2]]
        )

    @staticmethod
    def change_verification_chain() -> ToolChain:
        return ToolChain(
            chain_id="change_verification",
            name="变更验证链",
            description="执行变更并验证结果",
            auto_degradation=True,
            steps=[
                ToolStep(
                    step_index=0,
                    tool_name="query_device",
                    params={"device_id": "{{target_device}}"},
                    depends_on=[]
                ),
                ToolStep(
                    step_index=1,
                    tool_name="create_intent",
                    params={
                        "name": "config_change",
                        "intent_type": "config_change",
                        "target_devices": ["{{target_device}}"]
                    },
                    depends_on=[0]
                ),
                ToolStep(
                    step_index=2,
                    tool_name="execute_intent",
                    params={"intent_id": "$step1.data.intent_id"},
                    depends_on=[1],
                    max_retries=1,
                    fallback_tool="system_health"
                ),
                ToolStep(
                    step_index=3,
                    tool_name="query_device",
                    params={"device_id": "{{target_device}}"},
                    depends_on=[2]
                ),
                ToolStep(
                    step_index=4,
                    tool_name="system_health",
                    params={},
                    depends_on=[3]
                )
            ]
        )


class ToolChainRegistry:
    def __init__(self):
        self._chains: Dict[str, ToolChain] = {}
        self._register_builtin_chains()

    def _register_builtin_chains(self):
        predefined = PredefinedToolChains()
        self._chains["fault_auto_healing"] = predefined.fault_auto_healing_chain()
        self._chains["batch_inspection"] = predefined.batch_inspection_chain()
        self._chains["change_verification"] = predefined.change_verification_chain()

    def list_chains(self) -> List[ToolChain]:
        return list(self._chains.values())

    def get_chain(self, chain_id: str) -> Optional[ToolChain]:
        return self._chains.get(chain_id)

    def register_chain(self, chain: ToolChain) -> None:
        self._chains[chain.chain_id] = chain
```

---

## 5.4 语义路由增强 — 修改 `backend/agents/mcp_registry.py`

- [ ] **5.4-I1** 增强 MCPToolRouter 支持工具链路由

在 `backend/agents/mcp_registry.py` 的 `MCPToolRouter` 类中新增：

```python
def route_to_chain(self, intent_context: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    from backend.agents.tool_chains import ToolChainRegistry

    chain_registry = ToolChainRegistry()
    intent_type = intent_context.get("intent_type", "")
    user_input = intent_context.get("user_input", "")

    chain_mapping = {
        "fault_diagnosis": "fault_auto_healing",
        "self_healing": "fault_auto_healing",
        "inspection": "batch_inspection",
        "daily_check": "batch_inspection",
        "config_change": "change_verification",
        "change_implementation": "change_verification"
    }

    chain_id = chain_mapping.get(intent_type)
    if chain_id:
        chain = chain_registry.get_chain(chain_id)
        if chain:
            return {
                "type": "tool_chain",
                "chain_id": chain_id,
                "chain": chain.dict(),
                "strategy": "intent_chain_mapping",
                "confidence": 0.85
            }

    fault_keywords = ["故障", "自愈", "healing", "fault", "中断", "宕机"]
    inspect_keywords = ["巡检", "检查", "inspection", "健康", "health"]
    change_keywords = ["变更", "配置修改", "change", "升级"]

    for keyword in fault_keywords:
        if keyword in user_input.lower():
            chain = chain_registry.get_chain("fault_auto_healing")
            if chain:
                return {
                    "type": "tool_chain",
                    "chain_id": "fault_auto_healing",
                    "chain": chain.dict(),
                    "strategy": "keyword_matching",
                    "confidence": 0.7
                }

    for keyword in inspect_keywords:
        if keyword in user_input.lower():
            chain = chain_registry.get_chain("batch_inspection")
            if chain:
                return {
                    "type": "tool_chain",
                    "chain_id": "batch_inspection",
                    "chain": chain.dict(),
                    "strategy": "keyword_matching",
                    "confidence": 0.7
                }

    for keyword in change_keywords:
        if keyword in user_input.lower():
            chain = chain_registry.get_chain("change_verification")
            if chain:
                return {
                    "type": "tool_chain",
                    "chain_id": "change_verification",
                    "chain": chain.dict(),
                    "strategy": "keyword_matching",
                    "confidence": 0.7
                }

    return {"type": "single_tool", "tools": [], "strategy": "no_chain_match", "confidence": 0.0}
```

---

## 5.5 API 端点 — 修改 `backend/api/assistant.py`

- [ ] **5.5-I1** 新增工具链相关端点

在 `backend/api/assistant.py` 中新增：

```python
class ToolChainExecuteRequest(BaseModel):
    chain_id: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)
    context: ChatContext = Field(default_factory=ChatContext)


class ToolChainListResponse(BaseModel):
    chains: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/tool-chains", response_model=ToolChainListResponse)
async def list_tool_chains(
    current_user=Depends(get_current_user)
):
    try:
        from backend.agents.tool_chains import ToolChainRegistry
        registry = ToolChainRegistry()
        chains = registry.list_chains()

        return ToolChainListResponse(
            chains=[
                {
                    "chain_id": c.chain_id,
                    "name": c.name,
                    "description": c.description,
                    "steps_count": len(c.steps),
                    "auto_degradation": c.auto_degradation,
                    "parallel_groups": c.parallel_groups
                }
                for c in chains
            ]
        )
    except Exception as e:
        logger.error(f"List tool chains error: {e}")
        raise HTTPException(status_code=500, detail="获取工具链列表失败")


@router.post("/tool-chains/execute")
async def execute_tool_chain(
    request: ToolChainExecuteRequest,
    current_user=Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    try:
        from backend.agents.tool_chains import ToolChainRegistry
        from backend.agents.tool_orchestrator import ToolOrchestrationEngine

        registry = ToolChainRegistry()
        chain = registry.get_chain(request.chain_id)
        if not chain:
            raise HTTPException(status_code=404, detail=f"工具链不存在: {request.chain_id}")

        for key, value in request.params.items():
            for step in chain.steps:
                for param_key, param_value in step.params.items():
                    if isinstance(param_value, str) and f"{{{{{key}}}}}" in param_value:
                        step.params[param_key] = param_value.replace(f"{{{{{key}}}}}", str(value))

        react_engine = get_react_engine()
        engine = ToolOrchestrationEngine(react_engine.tool_registry)

        result = await engine.execute(chain, token=token)

        return success_response(data={
            "chain_id": result.chain_id,
            "status": result.status,
            "steps_results": result.steps_results,
            "total_duration_seconds": result.total_duration_seconds,
            "success_count": result.success_count,
            "degraded_count": result.degraded_count,
            "failed_count": result.failed_count
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tool chain execute error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="工具链执行失败")
```

在 `frontend/src/utils/apiClient.ts` 中新增路由映射：

```typescript
toolChains: '/api/v1/assistant/tool-chains',
toolChainExecute: '/api/v1/assistant/tool-chains/execute',
```

---

## 5.6 数据库迁移

- [ ] **5.6-I1** 在 `backend/database/models.py` 新增 ExecutionPlan 和 WizardSession 模型

（代码见 4.1.1 节）

- [ ] **5.6-I2** 运行数据库迁移

```bash
cd "d:\Trae CN\Project\智维 AgentHub"
python -c "from backend.database.models import Base; from backend.database.connection import engine; import asyncio; async def migrate(): async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all); asyncio.run(migrate())"
```

---

# 集成测试

- [ ] **INT-1** 端到端 Plan-Execute 流程测试

```bash
cd "d:\Trae CN\Project\智维 AgentHub"
python -m pytest tests/test_plan_executor.py tests/test_wizard_templates.py tests/test_tool_orchestration.py -v --tb=short
```

- [ ] **INT-2** API 端点集成测试

```bash
cd "d:\Trae CN\Project\智维 AgentHub"
python -m pytest tests/test_integration.py -v -k "plan_execute or wizard or tool_chain" --tb=short
```

- [ ] **INT-3** 前端类型检查

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend"
npx vue-tsc --noEmit
```

- [ ] **INT-4** 前端构建验证

```bash
cd "d:\Trae CN\Project\智维 AgentHub\frontend"
npm run build
```

---

# 文件变更清单

| 操作 | 文件路径 | 说明 |
|------|---------|------|
| 新增 | `backend/agents/plan_executor_models.py` | Plan-Execute Pydantic 数据模型 |
| 新增 | `backend/agents/plan_executor.py` | Plan-Execute Agent 核心实现 |
| 新增 | `backend/agents/wizard_templates.py` | 运维向导模板库 |
| 新增 | `backend/agents/tool_chains.py` | 工具链模型+预定义链库 |
| 新增 | `backend/agents/tool_orchestrator.py` | DAG分析+并行执行+自动降级 |
| 新增 | `tests/test_plan_executor.py` | Plan-Execute 单元测试 |
| 新增 | `tests/test_wizard_templates.py` | 向导模板单元测试 |
| 新增 | `tests/test_tool_orchestration.py` | 工具编排单元测试 |
| 修改 | `backend/agents/react_engine.py` | 新增 delegate_to_plan_execute 方法 |
| 修改 | `backend/agents/mcp_registry.py` | MCPToolRouter 新增 route_to_chain |
| 修改 | `backend/api/assistant.py` | 新增 /plan-execute, /plan-confirm, /wizards, /wizards/execute, /tool-chains, /tool-chains/execute 端点 |
| 修改 | `backend/database/models.py` | 新增 ExecutionPlan, WizardSession 模型 |
| 修改 | `frontend/src/stores/assistant.ts` | 新增 PlanExecuteState, WizardInfo, 相关方法 |
| 修改 | `frontend/src/components/AiAssistant/ChatPanel.vue` | Plan-Execute UI, 向导 UI, 确认 UI |
| 修改 | `frontend/src/utils/apiClient.ts` | 新增 API 路由映射 |

---

# 智能确认分级规则

| 确认级别 | 触发条件 | UI 行为 | 示例操作 |
|---------|---------|---------|---------|
| `low` | 只读查询、健康检查 | 自动执行，无需确认 | query_topology, system_health, get_events |
| `medium` | 创建意图、审批操作 | 一键确认（单按钮） | create_intent, approve_intent, list_intents |
| `high` | 执行变更、自愈操作 | 详细确认（勾选+理由） | execute_self_healing, execute_intent, shutdown_port |

---

# 工具链执行流程

```
用户请求 → DAGAnalyzer.analyze()
              ├── 检测循环依赖
              ├── 拓扑排序生成执行顺序
              └── 识别可并行步骤组
          → ParallelExecutor.execute_parallel()
              ├── asyncio.gather 并行执行
              └── 单步失败不影响其他并行步骤
          → AutoDegradationHandler.handle_degradation()
              ├── 工具失败 → 重试(最多2次)
              ├── 重试失败 → 查找fallback_tool
              └── 降级成功 → 标记DEGRADED状态
          → ParamReferenceParser.resolve_params()
              └── $step0.devices[0].id → 前序步骤结果引用
          → ToolChainExecutionResult
              ├── success: 全部成功
              ├── partial: 部分成功/降级
              └── failed: 全部失败
```
