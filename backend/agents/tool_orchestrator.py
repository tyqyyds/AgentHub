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
        path = path.lstrip(".")
        tokens = re.split(r'\.(?![^\[]*\])', path)
        for token in tokens:
            key_match = re.match(r'^([^\[]+)(?:\[(\d+)\])?$', token)
            if key_match:
                key = key_match.group(1)
                idx_str = key_match.group(2)
                if isinstance(current, dict) and key in current:
                    current = current[key]
                    if idx_str is not None:
                        idx = int(idx_str)
                        if isinstance(current, list) and idx < len(current):
                            current = current[idx]
                        else:
                            return value
                else:
                    return value
            elif token.startswith("[") and token.endswith("]"):
                idx = int(token[1:-1])
                if isinstance(current, list) and idx < len(current):
                    current = current[idx]
                else:
                    return value
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
            else:
                step = chain.steps[step_idx]
                step.status = ToolStepStatus.RUNNING

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
