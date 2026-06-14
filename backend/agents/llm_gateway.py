import json
import time
import logging
from typing import Dict, Any, Optional, List, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum

from backend.agents.deepseek_service import DeepSeekMessage, get_deepseek_service
from backend.agents.zhipu_service import ZhiPuMessage, get_zhipu_service
from backend.agents.llm_router import get_llm_router
from backend.agents.prompts import INTENT_PARSE_PROMPT, COPILOT_SYSTEM_PROMPT, CLARIFICATION_PROMPT
from backend.agents.llm_utils import parse_llm_json
from backend.agents.dialogue_state import ContextCompressor
from backend.core.config import settings

logger = logging.getLogger(__name__)

MAX_CONTEXT_MESSAGES = 30
MAX_CONTEXT_CHARS = 12000
INTENT_PARSE_MAX_CHARS = 6000


class LLMProvider(str, Enum):
    DEEPSEEK = "deepseek"
    ZHIPU = "zhipu"
    AUTO = "auto"


class TaskType(str, Enum):
    INTENT_PARSE = "intent_parse"
    COPILOT_CHAT = "copilot_chat"
    COPILOT_STREAM = "copilot_stream"
    CONFIG_GENERATE = "config_generate"
    FAULT_DIAGNOSE = "fault_diagnose"
    CLARIFICATION = "clarification"


TASK_PROVIDER_MAP = {
    TaskType.INTENT_PARSE: LLMProvider.ZHIPU,
    TaskType.COPILOT_CHAT: LLMProvider.DEEPSEEK,
    TaskType.COPILOT_STREAM: LLMProvider.DEEPSEEK,
    TaskType.CONFIG_GENERATE: LLMProvider.ZHIPU,
    TaskType.FAULT_DIAGNOSE: LLMProvider.ZHIPU,
    TaskType.CLARIFICATION: LLMProvider.ZHIPU,
}


@dataclass
class ConversationContext:
    messages: List[Dict[str, str]] = field(default_factory=list)
    summary: str = ""
    entities: Dict[str, str] = field(default_factory=dict)
    intent_history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    _compressor: ContextCompressor = field(default_factory=ContextCompressor)

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self.last_active = time.time()
        if len(self.messages) > MAX_CONTEXT_MESSAGES * 2:
            self._compress()

    def _compress(self):
        system_msgs = [m for m in self.messages if m["role"] == "system"]
        other_msgs = [m for m in self.messages if m["role"] != "system"]
        if len(other_msgs) > MAX_CONTEXT_MESSAGES:
            kept = other_msgs[-MAX_CONTEXT_MESSAGES:]
            compressed_summary = self._compressor.compress(other_msgs[:-MAX_CONTEXT_MESSAGES])
            self.summary += "\n" + compressed_summary
            self.messages = system_msgs + kept

    def get_trimmed_messages(self, max_chars: int = MAX_CONTEXT_CHARS) -> List[Dict[str, str]]:
        result = list(self.messages)
        total = sum(len(m["content"]) for m in result)
        while total > max_chars and len(result) > 2:
            for i, m in enumerate(result):
                if m["role"] != "system":
                    total -= len(m["content"])
                    result.pop(i)
                    break
            else:
                break
        return result


@dataclass
class GatewayStats:
    total_requests: int = 0
    deepseek_calls: int = 0
    zhipu_calls: int = 0
    fallback_calls: int = 0
    failed_calls: int = 0


class LLMGateway:
    def __init__(self):
        self.deepseek = get_deepseek_service()
        self.zhipu = get_zhipu_service()
        self.stats = GatewayStats()
        self._conversations: Dict[str, ConversationContext] = {}
        self._provider_priority: List[LLMProvider] = self._init_priority()

    def _init_priority(self) -> List[LLMProvider]:
        priority_str = settings.llm_provider_priority
        providers = []
        for p in priority_str.split(","):
            p = p.strip().lower()
            if p == "zhipu":
                providers.append(LLMProvider.ZHIPU)
            elif p == "deepseek":
                providers.append(LLMProvider.DEEPSEEK)
        if not providers:
            providers = [LLMProvider.ZHIPU, LLMProvider.DEEPSEEK]
        return providers

    def _select_provider(self, task_type: TaskType, preferred: LLMProvider = LLMProvider.AUTO) -> str:
        if preferred != LLMProvider.AUTO:
            if preferred == LLMProvider.DEEPSEEK and self.deepseek.available:
                return "deepseek"
            if preferred == LLMProvider.ZHIPU and self.zhipu.available:
                return "zhipu"

        router = get_llm_router()
        if router.enabled:
            selected = router.select_model(task_type.value)
            if selected is not None:
                return selected

        preferred_for_task = TASK_PROVIDER_MAP.get(task_type)
        if preferred_for_task == LLMProvider.ZHIPU and self.zhipu.available:
            return "zhipu"
        if preferred_for_task == LLMProvider.DEEPSEEK and self.deepseek.available:
            return "deepseek"

        for provider in self._provider_priority:
            if provider == LLMProvider.ZHIPU and self.zhipu.available:
                return "zhipu"
            if provider == LLMProvider.DEEPSEEK and self.deepseek.available:
                return "deepseek"

        if self.deepseek.available:
            return "deepseek"
        if self.zhipu.available:
            return "zhipu"
        return None

    def get_or_create_conversation(self, session_id: str) -> ConversationContext:
        self.cleanup_stale_conversations()
        if session_id not in self._conversations:
            self._conversations[session_id] = ConversationContext()
        ctx = self._conversations[session_id]
        ctx.last_active = time.time()
        return ctx

    def cleanup_stale_conversations(self, max_age_seconds: int = 3600):
        now = time.time()
        stale = [sid for sid, ctx in self._conversations.items()
                 if now - ctx.last_active > max_age_seconds]
        for sid in stale:
            del self._conversations[sid]

    def _to_deepseek_messages(self, messages: List[Dict[str, str]]) -> List[DeepSeekMessage]:
        return [DeepSeekMessage(role=m["role"], content=m["content"]) for m in messages]

    def _to_zhipu_messages(self, messages: List[Dict[str, str]]) -> List[ZhiPuMessage]:
        return [ZhiPuMessage(role=m["role"], content=m["content"]) for m in messages]

    def _get_provider_instance(self, name: str):
        if name == "deepseek":
            return self.deepseek
        elif name == "zhipu":
            return self.zhipu
        return None

    async def _call_provider(self, provider_name: str, messages: List[Dict[str, str]],
                              temperature: float, max_tokens: int, stream: bool = False,
                              task_type: TaskType = None):
        provider = self._get_provider_instance(provider_name)
        if not provider or not provider.available:
            raise RuntimeError(f"Provider {provider_name} 不可用")

        if provider_name == "deepseek":
            provider_messages = self._to_deepseek_messages(messages)
        else:
            provider_messages = self._to_zhipu_messages(messages)

        start_time = time.time()
        try:
            if stream:
                return provider.chat_stream(provider_messages, temperature, max_tokens)
            else:
                content = await provider.chat(provider_messages, temperature, max_tokens)
                latency_ms = int((time.time() - start_time) * 1000)
                if task_type:
                    self._record_router_result(provider_name, task_type.value, latency_ms, True, max_tokens)
                return {"content": content, "provider": provider_name, "model": provider.model}
        except Exception:
            latency_ms = int((time.time() - start_time) * 1000)
            if task_type:
                self._record_router_result(provider_name, task_type.value, latency_ms, False, 0)
            raise

    async def chat(
        self,
        messages: List[Dict[str, str]],
        task_type: TaskType = TaskType.COPILOT_CHAT,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        preferred: LLMProvider = LLMProvider.AUTO
    ) -> Dict[str, Any]:
        self.stats.total_requests += 1
        provider = self._select_provider(task_type, preferred)

        if provider is None:
            raise RuntimeError("无可用的LLM服务，请配置DEEPSEEK_API_KEY或ZHIPU_API_KEY")

        try:
            if provider == "deepseek":
                self.stats.deepseek_calls += 1
            else:
                self.stats.zhipu_calls += 1
            return await self._call_provider(provider, messages, temperature, max_tokens, task_type=task_type)
        except Exception as e:
            logger.warning(f"LLM {provider} 调用失败: {e}, 尝试故障转移")
            fallback = "zhipu" if provider == "deepseek" else "deepseek"
            fallback_provider = self._get_provider_instance(fallback)
            if fallback_provider and fallback_provider.available:
                try:
                    self.stats.fallback_calls += 1
                    if fallback == "deepseek":
                        self.stats.deepseek_calls += 1
                    else:
                        self.stats.zhipu_calls += 1
                    return await self._call_provider(fallback, messages, temperature, max_tokens, task_type=task_type)
                except Exception as fallback_err:
                    self.stats.failed_calls += 1
                    raise RuntimeError(f"所有LLM服务均不可用: {provider}={e}, {fallback}={fallback_err}")

            self.stats.failed_calls += 1
            raise

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        task_type: TaskType = TaskType.COPILOT_STREAM,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        preferred: LLMProvider = LLMProvider.AUTO
    ) -> AsyncGenerator[Dict[str, Any], None]:
        self.stats.total_requests += 1
        provider = self._select_provider(task_type, preferred)

        if provider is None:
            yield {"error": "无可用的LLM服务"}
            return

        try:
            if provider == "deepseek":
                self.stats.deepseek_calls += 1
                ds_messages = self._to_deepseek_messages(messages)
                async for chunk in self.deepseek.chat_stream(ds_messages, temperature, max_tokens):
                    yield {"content": chunk, "provider": "deepseek"}
            else:
                self.stats.zhipu_calls += 1
                zp_messages = self._to_zhipu_messages(messages)
                async for chunk in self.zhipu.chat_stream(zp_messages, temperature, max_tokens):
                    yield {"content": chunk, "provider": "zhipu"}
        except Exception as e:
            logger.warning(f"LLM {provider} 流式调用失败: {e}, 尝试故障转移")
            fallback = "zhipu" if provider == "deepseek" else "deepseek"
            fallback_provider = self._get_provider_instance(fallback)
            if fallback_provider and fallback_provider.available:
                try:
                    self.stats.fallback_calls += 1
                    if fallback == "deepseek":
                        self.stats.deepseek_calls += 1
                        ds_messages = self._to_deepseek_messages(messages)
                        async for chunk in self.deepseek.chat_stream(ds_messages, temperature, max_tokens):
                            yield {"content": chunk, "provider": "deepseek"}
                    else:
                        self.stats.zhipu_calls += 1
                        zp_messages = self._to_zhipu_messages(messages)
                        async for chunk in self.zhipu.chat_stream(zp_messages, temperature, max_tokens):
                            yield {"content": chunk, "provider": "zhipu"}
                except Exception as fallback_err:
                    self.stats.failed_calls += 1
                    yield {"error": f"所有LLM服务均不可用: {str(fallback_err)}"}
            else:
                self.stats.failed_calls += 1
                yield {"error": f"LLM {provider} 流式调用失败: {str(e)}，无可用的备用服务"}

    async def parse_intent(self, user_input: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        env_context = ""
        if context:
            env_context = f"\n\n## 当前网络状态:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
        else:
            env_context = f"\n\n## 当前网络环境:\n{json.dumps(settings.network_env, ensure_ascii=False, indent=2)}"

        messages = [
            {"role": "system", "content": INTENT_PARSE_PROMPT + env_context},
            {"role": "user", "content": f"请解析以下运维意图:\n{user_input}"}
        ]

        result = await self.chat(
            messages,
            task_type=TaskType.INTENT_PARSE,
            temperature=0.1,
            max_tokens=1024
        )

        content = result["content"]
        parsed = parse_llm_json(content)
        parsed["_provider"] = result["provider"]
        parsed["_model"] = result["model"]
        return parsed

    def _build_copilot_system_prompt(self, context: Dict[str, Any] = None, session_context: ConversationContext = None) -> str:
        prompt = COPILOT_SYSTEM_PROMPT

        env_info = f"\n\n## 当前网络环境:\n{json.dumps(settings.network_env, ensure_ascii=False, indent=2)}"
        prompt += env_info

        if context:
            prompt += f"\n\n## 实时上下文:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

        if session_context and session_context.summary:
            prompt += f"\n\n## 对话历史摘要:\n{session_context.summary}"

        if session_context and session_context.entities:
            prompt += f"\n\n## 已识别实体:\n{json.dumps(session_context.entities, ensure_ascii=False, indent=2)}"

        return prompt

    def _build_clarification_prompt(self, intent_data: Dict[str, Any], user_input: str) -> str:
        prompt = f"""{CLARIFICATION_PROMPT}

## 用户原始输入:
{user_input}

## 意图解析结果:
{json.dumps(intent_data, ensure_ascii=False, indent=2)}

## 当前网络环境:
{json.dumps(settings.network_env, ensure_ascii=False, indent=2)}"""
        return prompt

    async def generate_clarification_questions(
        self,
        intent_data: Dict[str, Any],
        user_input: str,
        preferred: LLMProvider = LLMProvider.AUTO
    ) -> Dict[str, Any]:
        prompt = self._build_clarification_prompt(intent_data, user_input)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "请生成澄清问题"}
        ]

        result = await self.chat(
            messages,
            task_type=TaskType.CLARIFICATION,
            temperature=0.3,
            max_tokens=1024,
            preferred=preferred
        )

        content = result["content"]
        fallback = {
            "clarification_questions": [
                {
                    "field": "unknown",
                    "question": intent_data.get("clarification_question", "请更详细地描述您的需求"),
                    "options": [],
                    "default": None
                }
            ],
            "suggested_intent": {
                "intent_type": intent_data.get("intent_type", "unknown"),
                "confidence": intent_data.get("confidence", 0.0)
            }
        }
        parsed = parse_llm_json(content, fallback=fallback)
        parsed["_provider"] = result["provider"]
        parsed["_model"] = result["model"]
        return parsed

    async def copilot_chat(
        self,
        user_message: str,
        session_id: str = "default",
        conversation_history: List[Dict[str, str]] = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        ctx = self.get_or_create_conversation(session_id)
        system_prompt = self._build_copilot_system_prompt(context, ctx)

        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            for msg in conversation_history[-MAX_CONTEXT_MESSAGES:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": user_message})

        # 多模型协同策略：先用GLM判断问题复杂度，再决定用哪个模型
        is_complex = self._is_complex_query(user_message)

        if is_complex:
            # 复杂问题：先用GLM整理问题要点，再用DeepSeek深度分析
            try:
                # Step 1: GLM整理问题要点
                classify_prompt = "请用1-2句话概括以下运维问题的核心要点，包括：故障现象、涉及设备、关键参数。只输出要点，不要解答。"
                classify_messages = [
                    {"role": "system", "content": classify_prompt},
                    {"role": "user", "content": user_message}
                ]
                classify_result = await self.chat(
                    classify_messages,
                    task_type=TaskType.COPILOT_CHAT,
                    temperature=0.3,
                    max_tokens=256,
                    preferred=LLMProvider.ZHIPU
                )
                problem_summary = classify_result.get("content", user_message)

                # Step 2: DeepSeek深度分析
                enhanced_messages = messages.copy()
                # 在system prompt中注入问题要点
                enhanced_messages[0]["content"] += f"\n\n## 问题要点分析（GLM预分析）:\n{problem_summary}"

                result = await self.chat(
                    enhanced_messages,
                    task_type=TaskType.COPILOT_CHAT,
                    temperature=0.7,
                    max_tokens=4096,
                    preferred=LLMProvider.DEEPSEEK
                )
                result["provider"] = "deepseek+glm"
                result["complexity"] = "complex"
            except Exception as e:
                logger.warning(f"DeepSeek深度分析失败，降级到GLM: {e}")
                result = await self.chat(
                    messages,
                    task_type=TaskType.COPILOT_CHAT,
                    temperature=0.7,
                    max_tokens=2048,
                    preferred=LLMProvider.ZHIPU
                )
                result["complexity"] = "complex_fallback"
        else:
            # 简单问题：直接用GLM快速响应
            result = await self.chat(
                messages,
                task_type=TaskType.COPILOT_CHAT,
                temperature=0.7,
                max_tokens=2048,
                preferred=LLMProvider.ZHIPU
            )
            result["complexity"] = "simple"

        ctx.add_message("user", user_message)
        ctx.add_message("assistant", result["content"])

        self._extract_entities(user_message, ctx)

        return result

    def _is_complex_query(self, message: str) -> bool:
        """判断问题是否需要DeepSeek深度推理"""
        complex_keywords = [
            '故障', '排查', '诊断', '丢包', '延迟', '不通', '中断', '宕机',
            '频繁', '间歇性', '不稳定', '根因', '为什么',
            '配置', '部署', '迁移', '切换', '升级',
            '深度', '详细', '完整', '全面', '方案',
            'ospf', 'bgp', 'vpn', 'vlan', 'qos', 'acl',
            '路由', '交换', '防火墙', '负载均衡',
        ]
        msg_lower = message.lower()
        complex_count = sum(1 for kw in complex_keywords if kw in msg_lower)
        # 超过15个字或包含2个以上复杂关键词视为复杂问题
        return len(message) > 15 or complex_count >= 2

    async def copilot_chat_stream(
        self,
        user_message: str,
        session_id: str = "default",
        conversation_history: List[Dict[str, str]] = None,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        ctx = self.get_or_create_conversation(session_id)
        system_prompt = self._build_copilot_system_prompt(context, ctx)

        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            for msg in conversation_history[-MAX_CONTEXT_MESSAGES:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": user_message})

        ctx.add_message("user", user_message)
        self._extract_entities(user_message, ctx)

        full_content = ""
        async for chunk in self.chat_stream(
            messages,
            task_type=TaskType.COPILOT_STREAM,
            temperature=0.7,
            max_tokens=2048
        ):
            if "content" in chunk:
                full_content += chunk["content"]
            yield chunk

        ctx.add_message("assistant", full_content)

    def _extract_entities(self, text: str, ctx: ConversationContext):
        import re
        subnet_match = re.search(r"([\u4e00-\u9fa5]+子网)", text)
        if subnet_match:
            ctx.entities["目标子网"] = subnet_match.group(1)
        bw_match = re.search(r"(\d+)\s*[MmGg]", text)
        if bw_match:
            ctx.entities["带宽"] = bw_match.group(0)
        device_match = re.search(r"([\w]+-[\w]+-\d+)", text)
        if device_match:
            ctx.entities["目标设备"] = device_match.group(1)

    def _record_router_result(self, provider: str, task_type: str, latency_ms: int, success: bool, tokens_used: int):
        try:
            router = get_llm_router()
            router.record_result(provider, task_type, latency_ms, success, tokens_used)
        except Exception:
            pass

    def register_llm_provider(self, provider_config: dict):
        router = get_llm_router()
        return router.register_provider(provider_config)

    def get_status(self) -> Dict[str, Any]:
        return {
            "deepseek": self.deepseek.get_stats(),
            "zhipu": self.zhipu.get_stats(),
            "gateway": {
                "total_requests": self.stats.total_requests,
                "deepseek_calls": self.stats.deepseek_calls,
                "zhipu_calls": self.stats.zhipu_calls,
                "fallback_calls": self.stats.fallback_calls,
                "failed_calls": self.stats.failed_calls,
                "active_conversations": len(self._conversations),
                "provider_priority": [p.value for p in self._provider_priority]
            }
        }

    async def close(self):
        await self.deepseek.close()
        await self.zhipu.close()

    async def execute_mcp_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from backend.mcp.executor import get_tool_executor
            executor = get_tool_executor()
            execution_result = await executor.execute_tool(tool_name, params)
            return {
                "status": "success",
                "tool": tool_name,
                "params": params,
                "result": execution_result
            }
        except Exception as e:
            try:
                from backend.agents.mcp_registry import get_mcp_registry
                registry = get_mcp_registry()
                tool = registry.get_tool(tool_name)
                if not tool:
                    return {"status": "error", "message": f"工具 {tool_name} 不存在"}
                return {
                    "status": "success",
                    "tool": tool_name,
                    "params": params,
                    "result": {
                        "message": f"工具 {tool_name} 调用已受理（执行器不可用，返回工具信息）",
                        "tool_info": {
                            "name": tool.get("name", tool_name),
                            "description": tool.get("description", ""),
                            "supported_devices": tool.get("supported_devices", [])
                        },
                        "simulated": True
                    }
                }
            except Exception as e2:
                return {"status": "error", "message": str(e2)}

    async def create_copilot_ticket(self, title: str, description: str, intent_data: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            from backend.agents.orchestrator import MultiAgentOrchestrator, CollaborationMode
            orchestrator = get_orchestrator()
            ticket = orchestrator.create_ticket(
                title=title,
                description=description,
                mode=CollaborationMode.SUPERVISOR,
                requires_approval=True
            )
            return {
                "status": "success",
                "ticket_id": ticket.ticket_id,
                "title": ticket.title,
                "message": f"工单 {ticket.ticket_id} 已创建，等待审批"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_system_context(self) -> Dict[str, Any]:
        context = {
            "network_env": settings.network_env,
            "llm_status": self.get_status()
        }
        try:
            from backend.agents.registry import get_agent_registry
            registry = get_agent_registry()
            agents = registry.list_agents()
            context["active_agents"] = [
                {"id": a.agent_id, "type": a.agent_type, "status": a.status}
                for a in agents[:10]
            ]
        except Exception:
            context["active_agents"] = []

        try:
            from backend.agents.mcp_registry import get_mcp_registry
            mcp = get_mcp_registry()
            tools = mcp.list_tools()
            context["mcp_tools"] = [
                {"name": t.get("name", ""), "description": t.get("description", "")}
                for t in tools[:10]
            ]
        except Exception:
            context["mcp_tools"] = []

        return context


_gateway_instance: Optional[LLMGateway] = None


def get_llm_gateway() -> LLMGateway:
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = LLMGateway()
    return _gateway_instance
