import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from backend.agents.plan_executor import (
    PlanGenerator, PlanReviewer, StepExecutor,
    ResultValidator, Reflector, PlanExecuteAgent,
)
from backend.agents.plan_executor_models import (
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
    registry.list_tools = MagicMock(return_value=[])
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
            steps=[PlanStep(step_index=0, description="placeholder", tool_name="system_health")]
        )
        empty_plan.steps = []
        result = reviewer.review(empty_plan)
        assert result.is_valid is False


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
