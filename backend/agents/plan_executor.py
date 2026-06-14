import asyncio
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

HIGH_RISK_TOOLS = {"execute_self_healing", "execute_intent", "shutdown_port", "isolate_node", "restart_device"}

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
            if isinstance(response, dict):
                response = response.get("content", str(response))
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

        try:
            tool_result = await self.tool_registry.execute_tool(
                name=step.tool_name,
                params=resolved_params,
                token=token
            )

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
                            return ref
                else:
                    return ref
            elif token.startswith("[") and token.endswith("]"):
                idx = int(token[1:-1])
                if isinstance(current, list) and idx < len(current):
                    current = current[idx]
                else:
                    return ref
            else:
                return ref

        return current


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
            if isinstance(response, dict):
                response = response.get("content", str(response))
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
        try:
            tools = self.tool_registry.list_tools(role)
            return [{"name": t.name, "description": t.description} for t in tools]
        except Exception:
            return [{"name": "system_health", "description": "Health check"}]

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
