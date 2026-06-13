"""LLM网关 - 统一LLM调用接口，支持DeepSeek和智谱GLM双网关"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """LLM提供商"""
    DEEPSEEK = "deepseek"
    ZHIPU = "zhipu"


class LLMTaskType(Enum):
    """LLM任务类型"""
    INTENT_PARSE = "intent_parse"
    COPILOT_CHAT = "copilot_chat"
    COPILOT_STREAM = "copilot_stream"
    CONFIG_GENERATE = "config_generate"
    FAULT_DIAGNOSE = "fault_diagnose"
    GENERAL = "general"


@dataclass
class LLMRequest:
    """LLM请求"""
    messages: list[dict[str, str]]
    task_type: LLMTaskType = LLMTaskType.GENERAL
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False
    tools: Optional[list[dict]] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """LLM响应"""
    content: str
    provider: LLMProvider
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    tool_calls: Optional[list[dict]] = None
    success: bool = True
    error: Optional[str] = None


@dataclass
class LLMGatewayConfig:
    """LLM网关配置"""
    max_retries: int = 2
    retry_delay_ms: int = 500
    timeout_seconds: int = 30
    enable_fallback: bool = True
    enable_circuit_breaker: bool = True
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_seconds: int = 60
    rate_limit_per_minute: int = 60


class CircuitBreaker:
    """熔断器"""

    def __init__(self, threshold: int = 5, reset_seconds: int = 60):
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.is_open = False

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.threshold:
            self.is_open = True
            logger.warning(f"熔断器打开，失败次数: {self.failure_count}")

    def record_success(self):
        self.failure_count = 0
        self.is_open = False

    def can_execute(self) -> bool:
        if not self.is_open:
            return True
        if self.last_failure_time and (time.time() - self.last_failure_time) > self.reset_seconds:
            self.is_open = False
            self.failure_count = 0
            logger.info("熔断器重置，尝试恢复")
            return True
        return False


class LLMGateway:
    """LLM网关 - 统一LLM调用接口"""

    def __init__(self, config: Optional[LLMGatewayConfig] = None):
        self.config = config or LLMGatewayConfig()
        self._deepseek_client = None
        self._zhipu_client = None
        self._circuit_breakers: dict[LLMProvider, CircuitBreaker] = {
            LLMProvider.DEEPSEEK: CircuitBreaker(
                threshold=self.config.circuit_breaker_threshold,
                reset_seconds=self.config.circuit_breaker_reset_seconds,
            ),
            LLMProvider.ZHIPU: CircuitBreaker(
                threshold=self.config.circuit_breaker_threshold,
                reset_seconds=self.config.circuit_breaker_reset_seconds,
            ),
        }
        self._call_timestamps: list[float] = []
        self._stats: dict[str, int] = {
            "total_calls": 0,
            "deepseek_calls": 0,
            "zhipu_calls": 0,
            "fallback_calls": 0,
            "failed_calls": 0,
        }
        logger.info("LLM网关初始化完成")

    def _check_rate_limit(self) -> bool:
        now = time.time()
        self._call_timestamps = [t for t in self._call_timestamps if now - t < 60]
        if len(self._call_timestamps) >= self.config.rate_limit_per_minute:
            logger.warning("LLM调用触发限流")
            return False
        self._call_timestamps.append(now)
        return True

    def _get_route_order(self, task_type: LLMTaskType) -> list[LLMProvider]:
        """根据任务类型获取LLM路由顺序"""
        route_map = {
            LLMTaskType.INTENT_PARSE: [LLMProvider.ZHIPU, LLMProvider.DEEPSEEK],
            LLMTaskType.COPILOT_CHAT: [LLMProvider.DEEPSEEK, LLMProvider.ZHIPU],
            LLMTaskType.COPILOT_STREAM: [LLMProvider.DEEPSEEK, LLMProvider.ZHIPU],
            LLMTaskType.CONFIG_GENERATE: [LLMProvider.ZHIPU, LLMProvider.DEEPSEEK],
            LLMTaskType.FAULT_DIAGNOSE: [LLMProvider.ZHIPU, LLMProvider.DEEPSEEK],
            LLMTaskType.GENERAL: [LLMProvider.DEEPSEEK, LLMProvider.ZHIPU],
        }
        return route_map.get(task_type, [LLMProvider.DEEPSEEK, LLMProvider.ZHIPU])

    async def _call_deepseek(self, request: LLMRequest) -> LLMResponse:
        """调用DeepSeek API"""
        start_time = time.time()
        try:
            from langchain_community.chat_models import ChatOpenAI

            if self._deepseek_client is None:
                self._deepseek_client = ChatOpenAI(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                    model=settings.deepseek_model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    timeout=self.config.timeout_seconds,
                )

            from langchain_core.messages import HumanMessage, SystemMessage

            lc_messages = []
            for msg in request.messages:
                if msg.get("role") == "system":
                    lc_messages.append(SystemMessage(content=msg["content"]))
                else:
                    lc_messages.append(HumanMessage(content=msg["content"]))

            response = await self._deepseek_client.ainvoke(lc_messages)
            latency_ms = (time.time() - start_time) * 1000

            self._circuit_breakers[LLMProvider.DEEPSEEK].record_success()
            self._stats["deepseek_calls"] += 1

            return LLMResponse(
                content=response.content,
                provider=LLMProvider.DEEPSEEK,
                model=settings.deepseek_model,
                latency_ms=latency_ms,
                success=True,
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._circuit_breakers[LLMProvider.DEEPSEEK].record_failure()
            logger.error(f"DeepSeek调用失败: {e}")
            return LLMResponse(
                content="",
                provider=LLMProvider.DEEPSEEK,
                model=settings.deepseek_model,
                latency_ms=latency_ms,
                success=False,
                error=str(e),
            )

    async def _call_zhipu(self, request: LLMRequest) -> LLMResponse:
        """调用智谱GLM API"""
        start_time = time.time()
        try:
            import httpx

            if self._zhipu_client is None:
                self._zhipu_client = httpx.AsyncClient(timeout=self.config.timeout_seconds)

            url = f"{settings.zhipu_base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.zhipu_api_key}",
                "Content-Type": "application/json",
            }
            payload: dict[str, Any] = {
                "model": settings.zhipu_model,
                "messages": request.messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "stream": False,
            }
            if request.tools:
                payload["tools"] = request.tools

            resp = await self._zhipu_client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            latency_ms = (time.time() - start_time) * 1000
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            tool_calls = data.get("choices", [{}])[0].get("message", {}).get("tool_calls")
            usage = data.get("usage", {})

            self._circuit_breakers[LLMProvider.ZHIPU].record_success()
            self._stats["zhipu_calls"] += 1

            return LLMResponse(
                content=content,
                provider=LLMProvider.ZHIPU,
                model=settings.zhipu_model,
                usage=usage,
                latency_ms=latency_ms,
                tool_calls=tool_calls,
                success=True,
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._circuit_breakers[LLMProvider.ZHIPU].record_failure()
            logger.error(f"智谱GLM调用失败: {e}")
            return LLMResponse(
                content="",
                provider=LLMProvider.ZHIPU,
                model=settings.zhipu_model,
                latency_ms=latency_ms,
                success=False,
                error=str(e),
            )

    async def _call_provider(self, provider: LLMProvider, request: LLMRequest) -> LLMResponse:
        """调用指定LLM提供商"""
        if provider == LLMProvider.DEEPSEEK:
            return await self._call_deepseek(request)
        elif provider == LLMProvider.ZHIPU:
            return await self._call_zhipu(request)
        else:
            return LLMResponse(
                content="",
                provider=provider,
                model="unknown",
                success=False,
                error=f"不支持的LLM提供商: {provider}",
            )

    async def call(self, request: LLMRequest) -> LLMResponse:
        """统一LLM调用入口，支持自动路由和降级"""
        self._stats["total_calls"] += 1

        if not self._check_rate_limit():
            return LLMResponse(
                content="",
                provider=LLMProvider.DEEPSEEK,
                model="",
                success=False,
                error="LLM调用触发限流，请稍后重试",
            )

        route_order = self._get_route_order(request.task_type)

        for i, provider in enumerate(route_order):
            cb = self._circuit_breakers.get(provider)
            if cb and not cb.can_execute():
                logger.warning(f"LLM提供商 {provider.value} 熔断中，跳过")
                continue

            response = await self._call_provider(provider, request)

            if response.success:
                return response

            if i < len(route_order) - 1 and self.config.enable_fallback:
                next_provider = route_order[i + 1]
                logger.warning(
                    f"LLM {provider.value} 调用失败，降级到 {next_provider.value}"
                )
                self._stats["fallback_calls"] += 1
                continue
            else:
                self._stats["failed_calls"] += 1
                return response

        self._stats["failed_calls"] += 1
        return LLMResponse(
            content="",
            provider=LLMProvider.DEEPSEEK,
            model="",
            success=False,
            error="所有LLM提供商均不可用",
        )

    async def call_stream(self, request: LLMRequest):
        """流式调用LLM"""
        provider = self._get_route_order(request.task_type)[0]
        cb = self._circuit_breakers.get(provider)
        if cb and not cb.can_execute():
            provider = self._get_route_order(request.task_type)[1]

        try:
            if provider == LLMProvider.DEEPSEEK:
                from langchain_community.chat_models import ChatOpenAI

                client = ChatOpenAI(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                    model=settings.deepseek_model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    streaming=True,
                )
                from langchain_core.messages import HumanMessage, SystemMessage

                lc_messages = []
                for msg in request.messages:
                    if msg.get("role") == "system":
                        lc_messages.append(SystemMessage(content=msg["content"]))
                    else:
                        lc_messages.append(HumanMessage(content=msg["content"]))

                async for chunk in client.astream(lc_messages):
                    yield chunk.content
            else:
                import httpx

                async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                    url = f"{settings.zhipu_base_url}/chat/completions"
                    headers = {
                        "Authorization": f"Bearer {settings.zhipu_api_key}",
                        "Content-Type": "application/json",
                    }
                    payload = {
                        "model": settings.zhipu_model,
                        "messages": request.messages,
                        "temperature": request.temperature,
                        "max_tokens": request.max_tokens,
                        "stream": True,
                    }
                    async with client.stream("POST", url, json=payload, headers=headers) as resp:
                        async for line in resp.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str.strip() == "[DONE]":
                                    break
                                import json
                                try:
                                    data = json.loads(data_str)
                                    delta = data.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                                except json.JSONDecodeError:
                                    continue
        except Exception as e:
            logger.error(f"流式调用失败: {e}")
            yield f"[错误] LLM流式调用失败: {str(e)}"

    def get_stats(self) -> dict[str, Any]:
        """获取网关统计信息"""
        return {
            **self._stats,
            "circuit_breakers": {
                p.value: {"is_open": cb.is_open, "failure_count": cb.failure_count}
                for p, cb in self._circuit_breakers.items()
            },
        }

    async def process(self, request: LLMRequest) -> LLMResponse:
        """Agent标准处理接口"""
        return await self.call(request)

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        providers_status = {}
        for provider in LLMProvider:
            cb = self._circuit_breakers.get(provider)
            providers_status[provider.value] = {
                "circuit_open": cb.is_open if cb else False,
                "failure_count": cb.failure_count if cb else 0,
            }

        return {
            "status": "healthy" if not any(
                cb.is_open for cb in self._circuit_breakers.values()
            ) else "degraded",
            "providers": providers_status,
            "stats": self._stats,
        }
