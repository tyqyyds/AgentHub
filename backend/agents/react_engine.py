import json
import time
import httpx
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field

from backend.agents.llm_gateway import get_llm_gateway, TaskType, LLMProvider
from backend.agents.tool_registry import get_tool_registry
from backend.core.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 60.0


@dataclass
class ReActStep:
    step_number: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    status: str = "thinking"


@dataclass
class ReActResult:
    steps: List[ReActStep] = field(default_factory=list)
    final_answer: str = ""
    tools_called: List[str] = field(default_factory=list)
    requires_approval: bool = False
    approval_data: Optional[Dict[str, Any]] = None
    frontend_actions: List[Dict[str, Any]] = field(default_factory=list)


class ReActEngine:
    def __init__(self) -> None:
        self.llm_gateway = get_llm_gateway()
        self.tool_registry = get_tool_registry()
        self.max_iterations: int = 5
        self.model: str = settings.zhipu_model
        self.api_url: str = settings.zhipu_api_url
        self.api_key: str = settings.zhipu_api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=30.0, pool=30.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
            )
        return self._client

    async def _call_llm_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("ZhiPu API Key 未配置，无法调用 ReAct 引擎")

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools_schema,
            "tool_choice": "auto",
            "temperature": 0.3,
            "max_tokens": 2048
        }

        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        last_error: Optional[str] = None
        for attempt in range(MAX_RETRIES):
            start_time = time.time()
            try:
                client = await self._get_client()
                response = await client.post(
                    self.api_url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                latency = (time.time() - start_time) * 1000
                logger.info(f"ReAct LLM调用成功, 延迟: {latency:.0f}ms")
                return data

            except httpx.TimeoutException as e:
                last_error = f"ReAct LLM请求超时: {str(e)}"
                logger.warning(last_error)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)] * 2
                    last_error = f"ReAct LLM速率限制，等待{wait}秒后重试"
                    logger.warning(last_error)
                    await asyncio.sleep(wait)
                    continue
                elif e.response.status_code >= 500:
                    last_error = f"ReAct LLM服务端错误: {e.response.status_code}"
                    logger.warning(last_error)
                else:
                    last_error = f"ReAct LLM HTTP错误: {e.response.status_code}"
                    logger.error(last_error)
                    break
            except Exception as e:
                last_error = f"ReAct LLM请求异常: {str(e)}"
                logger.warning(last_error)

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])

        raise RuntimeError(f"ReAct LLM调用失败(重试{MAX_RETRIES}次): {last_error}")

    def _build_system_prompt(self, role: str, page: str, scene_mode: str) -> str:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        cn_hour = (now.hour + 8) % 24
        is_weekday = now.weekday() < 5
        is_off_hours = (is_weekday and (cn_hour >= 18 or cn_hour < 9)) or not is_weekday
        time_info = f"当前时间：北京时间{cn_hour:02d}:{now.minute:02d}"
        off_hours_note = "\n注意：当前为非工作时间，可适当调整交互语气，但专业度不得降低。" if is_off_hours else ""

        return f"""你是智维AgentHub的专业智能运维助手，专注于协助运维人员高效完成日常运维工作。

## 角色定义
你是智维运维平台的专业智能助手，回答必须保持高度的准确性、专业性和严谨性。

## 核心职责
1. **运维查询响应**：对服务器状态、监控告警、日志分析、故障排查等运维相关查询提供快速、精准的响应
2. **运维操作协助**：支持重启服务、修改配置、创建工单等运维操作的执行，确保操作指令清晰可执行
3. **运维知识支持**：基于平台知识库内容，提供专业的运维知识解答
4. **非运维问题处理**：对非运维类问题可提供简洁回答，但不得偏离运维主题

## 输出规范
1. **结构化输出**：优先采用表格、列表等结构化形式
2. **关键信息强调**：使用**加粗**格式突出告警级别、操作风险、重要参数
3. **操作步骤规范**：采用编号形式（1. 2. 3.）分步骤说明
4. **内容简洁**：直击问题核心，避免冗余

## 行为规则
1. **操作确认机制**：执行任何运维操作前，必须确认用户意图
2. **风险提示要求**：涉及系统重启、配置修改等高风险操作时，必须醒目提醒注意事项、潜在风险及回滚方案
3. **故障处理规范**：工具调用失败时，需告知具体失败原因、影响范围及建议解决措施
4. **不编造数据**：通过工具获取实时信息，不要编造数据

## 推理规则
1. 当需要查询系统数据或执行操作时，必须通过工具调用(function call)完成，不要在文本中描述工具调用
2. 如果只需回答问题而无需工具，直接用中文回复即可
3. 最多进行5轮推理
4. 高危操作需要用户确认后才能执行
5. 回复使用中文，使用Markdown格式

当前上下文：
- 用户角色：{role}
- 当前页面：{page}
- 场景模式：{'日常巡检' if scene_mode == 'daily' else '应急响应' if scene_mode == 'emergency' else '变更冻结'}
- {time_info}
{off_hours_note}"""

    async def run(
        self,
        user_message: str,
        context: Dict[str, Any],
        token: str,
        on_step_callback: Optional[Callable] = None
    ) -> ReActResult:
        role: str = context.get("role", "viewer")
        page: str = context.get("page", "")
        scene_mode: str = context.get("scene_mode", "daily")

        tools_schema: List[Dict[str, Any]] = self.tool_registry.get_openai_tools_schema(role)

        system_prompt: str = self._build_system_prompt(role, page, scene_mode)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        steps: List[ReActStep] = []
        tools_called: List[str] = []
        frontend_actions: List[Dict[str, Any]] = []
        final_answer: str = ""
        requires_approval: bool = False
        approval_data: Optional[Dict[str, Any]] = None

        for iteration in range(self.max_iterations):
            logger.info(f"ReAct迭代 {iteration + 1}/{self.max_iterations}")

            try:
                response_data: Dict[str, Any] = await self._call_llm_with_tools(messages, tools_schema)
            except RuntimeError as e:
                logger.error(f"ReAct LLM调用失败: {e}")
                error_step = ReActStep(
                    step_number=iteration + 1,
                    thought=f"LLM调用失败: {str(e)}",
                    status="failed"
                )
                steps.append(error_step)
                if on_step_callback:
                    if asyncio.iscoroutinefunction(on_step_callback):
                        await on_step_callback(error_step.__dict__)
                    else:
                        on_step_callback(error_step.__dict__)
                final_answer = f"推理引擎调用失败: {str(e)}"
                break

            choice = response_data.get("choices", [{}])[0]
            message = choice.get("message", {})

            tool_calls = message.get("tool_calls")

            if tool_calls and len(tool_calls) > 0:
                tool_call = tool_calls[0]
                function_info = tool_call.get("function", {})
                tool_name: str = function_info.get("name", "")
                tool_args_str: str = function_info.get("arguments", "{}")

                try:
                    tool_args: Dict[str, Any] = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    tool_args = {}

                thought_content: str = message.get("content", "") or f"调用工具 {tool_name}"

                tool_def = self.tool_registry.get_tool(tool_name)
                risk_level: str = tool_def.risk_level if tool_def else "low"

                step = ReActStep(
                    step_number=iteration + 1,
                    thought=thought_content,
                    action=tool_name,
                    action_input=tool_args,
                    status="acting"
                )
                steps.append(step)

                if on_step_callback:
                    if asyncio.iscoroutinefunction(on_step_callback):
                        await on_step_callback(step.__dict__)
                    else:
                        on_step_callback(step.__dict__)

                if risk_level == "high":
                    requires_approval = True
                    approval_data = {
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "risk_level": risk_level,
                        "thought": thought_content,
                        "step_number": iteration + 1,
                        "description": tool_def.description if tool_def else ""
                    }
                    step.status = "waiting_approval"
                    if on_step_callback:
                        if asyncio.iscoroutinefunction(on_step_callback):
                            await on_step_callback(step.__dict__)
                        else:
                            on_step_callback(step.__dict__)
                    logger.info(f"高危工具 {tool_name} 需要用户确认，暂停推理")
                    break

                try:
                    tool_result: Dict[str, Any] = await self.tool_registry.execute_tool(
                        tool_name=tool_name,
                        params=tool_args,
                        token=token
                    )
                    observation_str: str = json.dumps(tool_result, ensure_ascii=False)
                except Exception as e:
                    tool_result = {"status": "error", "message": f"工具执行失败: {str(e)}"}
                    observation_str = json.dumps(tool_result, ensure_ascii=False)
                    logger.warning(f"工具 {tool_name} 执行失败: {e}")

                step.observation = observation_str
                step.status = "observing"
                tools_called.append(tool_name)

                if on_step_callback:
                    if asyncio.iscoroutinefunction(on_step_callback):
                        await on_step_callback(step.__dict__)
                    else:
                        on_step_callback(step.__dict__)

                if tool_result.get("type") == "frontend_action":
                    frontend_actions.append(tool_result)

                if tool_result.get("frontend_actions"):
                    frontend_actions.extend(tool_result["frontend_actions"])

                messages.append({"role": "assistant", "content": thought_content, "tool_calls": tool_calls})
                messages.append({
                    "role": "tool",
                    "content": observation_str,
                    "tool_call_id": tool_call.get("id", "")
                })

            else:
                final_answer = message.get("content", "")

                step = ReActStep(
                    step_number=iteration + 1,
                    thought=final_answer,
                    status="completed"
                )
                steps.append(step)

                if on_step_callback:
                    if asyncio.iscoroutinefunction(on_step_callback):
                        await on_step_callback(step.__dict__)
                    else:
                        on_step_callback(step.__dict__)

                logger.info(f"ReAct推理完成，共{iteration + 1}轮")
                break
        else:
            if not final_answer and steps:
                final_answer = "已达最大推理轮次，当前分析结论：\n" + "\n".join(
                    f"- 第{s.step_number}轮: {s.thought}" for s in steps if s.thought
                )
            elif not final_answer:
                final_answer = "推理引擎未能在最大轮次内得出结论"

            logger.info(f"ReAct达到最大迭代次数 {self.max_iterations}")

        return ReActResult(
            steps=steps,
            final_answer=final_answer,
            tools_called=tools_called,
            requires_approval=requires_approval,
            approval_data=approval_data,
            frontend_actions=frontend_actions
        )

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

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


_engine_instance: Optional[ReActEngine] = None


def get_react_engine() -> ReActEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ReActEngine()
    return _engine_instance
