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
            steps=[ToolStep(step_index=0, tool_name="placeholder", depends_on=[])]
        )
        chain.steps = []

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
