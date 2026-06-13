import logging
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ReActStep:
    """ReAct推理步骤"""
    iteration: int
    thought: str
    action: str
    action_input: Dict[str, Any]
    observation: str = ""


@dataclass
class ReActEngineConfig:
    """ReAct引擎配置"""
    max_iterations: int = 5
    high_risk_pause: bool = True
    high_risk_actions: List[str] = field(default_factory=lambda: [
        "delete_config", "reload_device", "reset_interface",
        "erase_startup", "format_flash", "clear_acl",
    ])
    thought_prompt: str = "你是一个网络运维推理引擎。请根据当前观察，推理下一步操作。"


class ReActEngine:
    """ReAct推理引擎：智谱GLM Function Calling，最多5轮推理循环，高危操作暂停等审批"""

    def __init__(self, config: Optional[ReActEngineConfig] = None):
        self.config = config or ReActEngineConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._reasoning_history: List[ReActStep] = []
        self._paused_for_approval: bool = False

    def register_tool(self, name: str, description: str, parameters: Dict[str, Any],
                      handler: Any = None) -> None:
        """注册可用工具"""
        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "handler": handler,
        }
        self.logger.info(f"工具已注册: {name}")

    def _is_high_risk(self, action: str) -> bool:
        """判断是否为高危操作"""
        return action.lower() in [a.lower() for a in self.config.high_risk_actions]

    def _build_thought_prompt(self, query: str, history: List[ReActStep]) -> str:
        """构建推理提示"""
        history_text = ""
        for step in history:
            history_text += (
                f"\n第{step.iteration}轮:\n"
                f"  思考: {step.thought}\n"
                f"  行动: {step.action}({json.dumps(step.action_input, ensure_ascii=False)})\n"
                f"  观察: {step.observation}\n"
            )

        tools_text = "\n".join(
            f"- {name}: {info['description']}"
            for name, info in self._tools.items()
        )

        return (
            f"{self.config.thought_prompt}\n\n"
            f"用户查询: {query}\n\n"
            f"可用工具:\n{tools_text}\n\n"
            f"推理历史:\n{history_text if history_text else '（无）'}\n\n"
            f"请输出下一步的思考和行动。格式:\n"
            f"思考: <你的推理过程>\n"
            f"行动: <工具名称>\n"
            f"参数: <JSON格式参数>"
        )

    def _parse_response(self, response: str) -> Optional[ReActStep]:
        """解析LLM响应为ReAct步骤"""
        thought = ""
        action = ""
        action_input = {}

        lines = response.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("思考:") or line.startswith("Thought:"):
                thought = line.split(":", 1)[1].strip()
            elif line.startswith("行动:") or line.startswith("Action:"):
                action = line.split(":", 1)[1].strip()
            elif line.startswith("参数:") or line.startswith("Input:"):
                params_str = line.split(":", 1)[1].strip()
                try:
                    action_input = json.loads(params_str)
                except json.JSONDecodeError:
                    action_input = {"raw": params_str}

        if not action:
            return None

        return ReActStep(
            iteration=len(self._reasoning_history) + 1,
            thought=thought,
            action=action,
            action_input=action_input,
        )

    async def _execute_tool(self, action: str, action_input: Dict[str, Any]) -> str:
        """执行工具调用"""
        tool = self._tools.get(action)
        if not tool:
            return f"错误: 未知工具 '{action}'"

        handler = tool.get("handler")
        if handler and callable(handler):
            try:
                if hasattr(handler, "__self__"):
                    result = await handler(action_input)
                else:
                    result = handler(action_input)
                return str(result) if result else "执行完成，无输出"
            except Exception as e:
                return f"工具执行错误: {str(e)}"

        return f"工具 '{action}' 已调用（模拟），参数: {json.dumps(action_input, ensure_ascii=False)}"

    async def _call_llm(self, prompt: str) -> str:
        """调用LLM进行推理（通过llm_gateway）"""
        try:
            from .llm_gateway import LLMGateway
            gateway = LLMGateway()
            response = await gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                task_type="fault_diagnose",
            )
            return response.get("content", "")
        except ImportError:
            self.logger.warning("LLM网关不可用，使用规则推理")
            return self._rule_based_reasoning(prompt)

    def _rule_based_reasoning(self, prompt: str) -> str:
        """规则推理（LLM不可用时的降级方案）"""
        if "带宽" in prompt or "bandwidth" in prompt.lower():
            return "思考: 用户需要带宽相关操作\n行动: check_qos_status\n参数: {}"
        elif "ACL" in prompt or "访问" in prompt:
            return "思考: 用户需要ACL相关操作\n行动: check_acl_status\n参数: {}"
        elif "路由" in prompt or "route" in prompt.lower():
            return "思考: 用户需要路由相关操作\n行动: check_route_table\n参数: {}"
        return "思考: 需要更多信息\n行动: check_device_status\n参数: {}"

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行ReAct推理循环"""
        query = input_data.get("query", input_data.get("user_input", ""))
        context = input_data.get("context", {})

        self._reasoning_history = []
        self._paused_for_approval = False
        final_answer = ""
        iterations_used = 0

        for iteration in range(1, self.config.max_iterations + 1):
            prompt = self._build_thought_prompt(query, self._reasoning_history)
            response = await self._call_llm(prompt)

            step = self._parse_response(response)
            if not step:
                final_answer = "推理失败：无法解析LLM响应"
                break

            step.iteration = iteration

            if self._is_high_risk(step.action):
                if self.config.high_risk_pause:
                    self._paused_for_approval = True
                    step.observation = f"⚠️ 高危操作 '{step.action}' 已暂停，等待审批"
                    self._reasoning_history.append(step)
                    self.logger.warning(f"高危操作暂停: {step.action}")
                    break

            observation = await self._execute_tool(step.action, step.action_input)
            step.observation = observation
            self._reasoning_history.append(step)
            iterations_used = iteration

            if "最终答案" in observation or "FINAL_ANSWER" in observation:
                final_answer = observation
                break

            if "错误" in observation or "error" in observation.lower():
                if iteration >= self.config.max_iterations:
                    final_answer = f"推理达到最大迭代次数，最后观察: {observation}"
                    break

        if not final_answer and self._reasoning_history:
            last_obs = self._reasoning_history[-1].observation
            final_answer = f"推理完成，最终观察: {last_obs}"

        result = {
            "query": query,
            "final_answer": final_answer,
            "iterations_used": iterations_used,
            "max_iterations": self.config.max_iterations,
            "paused_for_approval": self._paused_for_approval,
            "reasoning_steps": [
                {
                    "iteration": s.iteration,
                    "thought": s.thought,
                    "action": s.action,
                    "action_input": s.action_input,
                    "observation": s.observation,
                }
                for s in self._reasoning_history
            ],
            "tools_available": list(self._tools.keys()),
        }

        self.logger.info(
            f"ReAct推理完成: 迭代={iterations_used}, "
            f"暂停={self._paused_for_approval}"
        )
        return result

    async def resume_after_approval(self, approved: bool) -> Dict[str, Any]:
        """审批后恢复推理"""
        if not self._paused_for_approval or not self._reasoning_history:
            return {"status": "no_paused_step"}

        last_step = self._reasoning_history[-1]
        if approved:
            observation = await self._execute_tool(last_step.action, last_step.action_input)
            last_step.observation = observation
            self._paused_for_approval = False

            return {
                "status": "resumed",
                "action": last_step.action,
                "observation": observation,
            }
        else:
            self._paused_for_approval = False
            return {
                "status": "rejected",
                "action": last_step.action,
                "observation": "操作已被审批者拒绝",
            }

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "agent": self.__class__.__name__,
            "registered_tools": len(self._tools),
            "max_iterations": self.config.max_iterations,
            "high_risk_pause": self.config.high_risk_pause,
        }
