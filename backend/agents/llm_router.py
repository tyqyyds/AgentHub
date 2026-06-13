"""LLM路由 - 按任务类型路由到不同LLM，支持动态路由规则和优先级调整"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..core.config import settings
from .llm_gateway import LLMGateway, LLMProvider, LLMRequest, LLMResponse, LLMTaskType

logger = logging.getLogger(__name__)


class RouteStrategy(Enum):
    """路由策略"""
    PRIORITY = "priority"
    ROUND_ROBIN = "round_robin"
    LEAST_LATENCY = "least_latency"
    COST_OPTIMIZED = "cost_optimized"


@dataclass
class RouteRule:
    """路由规则"""
    task_type: LLMTaskType
    primary_provider: LLMProvider
    fallback_provider: LLMProvider
    priority: int = 1
    enabled: bool = True
    conditions: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMRouterConfig:
    """LLM路由配置"""
    default_strategy: RouteStrategy = RouteStrategy.PRIORITY
    enable_dynamic_routing: bool = True
    latency_window_seconds: int = 300
    cost_weights: dict[str, float] = field(default_factory=lambda: {
        "deepseek": 0.3,
        "zhipu": 0.7,
    })


class LatencyTracker:
    """延迟追踪器"""

    def __init__(self, window_seconds: int = 300):
        self.window_seconds = window_seconds
        self._records: dict[LLMProvider, list[tuple[float, float]]] = {
            LLMProvider.DEEPSEEK: [],
            LLMProvider.ZHIPU: [],
        }

    def record(self, provider: LLMProvider, latency_ms: float):
        now = time.time()
        self._records[provider].append((now, latency_ms))
        self._cleanup(provider)

    def get_avg_latency(self, provider: LLMProvider) -> float:
        self._cleanup(provider)
        records = self._records.get(provider, [])
        if not records:
            return 0.0
        return sum(r[1] for r in records) / len(records)

    def _cleanup(self, provider: LLMProvider):
        now = time.time()
        cutoff = now - self.window_seconds
        self._records[provider] = [
            r for r in self._records[provider] if r[0] > cutoff
        ]


class LLMRouter:
    """LLM路由 - 按任务类型智能路由到不同LLM"""

    def __init__(
        self,
        gateway: Optional[LLMGateway] = None,
        config: Optional[LLMRouterConfig] = None,
    ):
        self.config = config or LLMRouterConfig()
        self.gateway = gateway or LLMGateway()
        self._rules: dict[LLMTaskType, RouteRule] = {}
        self._latency_tracker = LatencyTracker(self.config.latency_window_seconds)
        self._round_robin_index = 0
        self._stats: dict[str, int] = {
            "total_routed": 0,
            "deepseek_routed": 0,
            "zhipu_routed": 0,
            "fallback_triggered": 0,
        }
        self._init_default_rules()
        logger.info("LLM路由初始化完成")

    def _init_default_rules(self):
        """初始化默认路由规则"""
        default_rules = [
            RouteRule(
                task_type=LLMTaskType.INTENT_PARSE,
                primary_provider=LLMProvider.ZHIPU,
                fallback_provider=LLMProvider.DEEPSEEK,
                priority=1,
                conditions={"requires_function_calling": True},
            ),
            RouteRule(
                task_type=LLMTaskType.COPILOT_CHAT,
                primary_provider=LLMProvider.DEEPSEEK,
                fallback_provider=LLMProvider.ZHIPU,
                priority=1,
                conditions={"requires_long_context": True},
            ),
            RouteRule(
                task_type=LLMTaskType.CONFIG_GENERATE,
                primary_provider=LLMProvider.ZHIPU,
                fallback_provider=LLMProvider.DEEPSEEK,
                priority=1,
                conditions={"requires_structured_output": True},
            ),
            RouteRule(
                task_type=LLMTaskType.FAULT_DIAGNOSE,
                primary_provider=LLMProvider.ZHIPU,
                fallback_provider=LLMProvider.DEEPSEEK,
                priority=1,
                conditions={"requires_reasoning": True},
            ),
            RouteRule(
                task_type=LLMTaskType.COPILOT_STREAM,
                primary_provider=LLMProvider.DEEPSEEK,
                fallback_provider=LLMProvider.ZHIPU,
                priority=1,
                conditions={"requires_streaming": True},
            ),
            RouteRule(
                task_type=LLMTaskType.GENERAL,
                primary_provider=LLMProvider.DEEPSEEK,
                fallback_provider=LLMProvider.ZHIPU,
                priority=2,
            ),
        ]
        for rule in default_rules:
            self._rules[rule.task_type] = rule

    def add_rule(self, rule: RouteRule):
        """添加路由规则"""
        self._rules[rule.task_type] = rule
        logger.info(f"添加路由规则: {rule.task_type.value} -> {rule.primary_provider.value}")

    def remove_rule(self, task_type: LLMTaskType):
        """移除路由规则"""
        if task_type in self._rules:
            del self._rules[task_type]
            logger.info(f"移除路由规则: {task_type.value}")

    def _route_by_priority(self, task_type: LLMTaskType) -> LLMProvider:
        """按优先级路由"""
        rule = self._rules.get(task_type)
        if rule and rule.enabled:
            return rule.primary_provider
        return LLMProvider.DEEPSEEK

    def _route_by_round_robin(self) -> LLMProvider:
        """轮询路由"""
        providers = list(LLMProvider)
        provider = providers[self._round_robin_index % len(providers)]
        self._round_robin_index += 1
        return provider

    def _route_by_least_latency(self, task_type: LLMTaskType) -> LLMProvider:
        """按最低延迟路由"""
        deepseek_latency = self._latency_tracker.get_avg_latency(LLMProvider.DEEPSEEK)
        zhipu_latency = self._latency_tracker.get_avg_latency(LLMProvider.ZHIPU)

        if deepseek_latency == 0 and zhipu_latency == 0:
            return self._route_by_priority(task_type)

        if deepseek_latency <= zhipu_latency:
            return LLMProvider.DEEPSEEK
        return LLMProvider.ZHIPU

    def _route_by_cost(self, task_type: LLMTaskType) -> LLMProvider:
        """按成本优化路由"""
        rule = self._rules.get(task_type)
        if rule and rule.conditions.get("requires_function_calling"):
            return LLMProvider.ZHIPU
        if rule and rule.conditions.get("requires_long_context"):
            return LLMProvider.DEEPSEEK
        return LLMProvider.DEEPSEEK

    def route(self, task_type: LLMTaskType) -> LLMProvider:
        """根据策略路由到LLM提供商"""
        strategy_map = {
            RouteStrategy.PRIORITY: self._route_by_priority,
            RouteStrategy.ROUND_ROBIN: lambda _: self._route_by_round_robin(),
            RouteStrategy.LEAST_LATENCY: self._route_by_least_latency,
            RouteStrategy.COST_OPTIMIZED: self._route_by_cost,
        }
        router = strategy_map.get(self.config.default_strategy, self._route_by_priority)
        provider = router(task_type)

        self._stats["total_routed"] += 1
        if provider == LLMProvider.DEEPSEEK:
            self._stats["deepseek_routed"] += 1
        else:
            self._stats["zhipu_routed"] += 1

        logger.debug(f"路由决策: {task_type.value} -> {provider.value} (策略: {self.config.default_strategy.value})")
        return provider

    async def route_and_call(self, request: LLMRequest) -> LLMResponse:
        """路由并调用LLM"""
        provider = self.route(request.task_type)
        request.metadata["routed_provider"] = provider.value

        response = await self.gateway.call(request)

        if response.success:
            self._latency_tracker.record(response.provider, response.latency_ms)
        else:
            rule = self._rules.get(request.task_type)
            if rule and rule.enabled:
                fallback = rule.fallback_provider
                logger.warning(f"主提供商 {provider.value} 失败，降级到 {fallback.value}")
                self._stats["fallback_triggered"] += 1
                request.metadata["fallback_from"] = provider.value
                response = await self.gateway.call(request)

        return response

    def get_routing_stats(self) -> dict[str, Any]:
        """获取路由统计"""
        return {
            "stats": self._stats,
            "latency": {
                "deepseek_avg_ms": self._latency_tracker.get_avg_latency(LLMProvider.DEEPSEEK),
                "zhipu_avg_ms": self._latency_tracker.get_avg_latency(LLMProvider.ZHIPU),
            },
            "rules": {
                tt.value: {
                    "primary": r.primary_provider.value,
                    "fallback": r.fallback_provider.value,
                    "enabled": r.enabled,
                }
                for tt, r in self._rules.items()
            },
            "strategy": self.config.default_strategy.value,
        }

    async def process(self, request: LLMRequest) -> LLMResponse:
        """Agent标准处理接口"""
        return await self.route_and_call(request)

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        gateway_health = await self.gateway.health_check()
        return {
            "status": gateway_health.get("status", "unknown"),
            "routing_strategy": self.config.default_strategy.value,
            "rules_count": len(self._rules),
            "stats": self._stats,
            "gateway": gateway_health,
        }
