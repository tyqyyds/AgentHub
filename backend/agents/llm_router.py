import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from backend.core.config import settings

logger = logging.getLogger(__name__)

WEIGHT_SUCCESS_RATE = 0.4
WEIGHT_LATENCY = 0.3
WEIGHT_COST = 0.2
WEIGHT_FEATURE = 0.1

DEFAULT_MAX_LATENCY_MS = 30000.0
DEFAULT_COST_PER_1K = 0.01

TASK_TYPE_DEFAULTS = {
    "intent_parse": {"prefer_low_cost": True, "prefer_low_latency": True, "require_function_calling": False},
    "copilot_chat": {"prefer_low_cost": False, "prefer_low_latency": False, "require_function_calling": False},
    "copilot_stream": {"prefer_low_cost": False, "prefer_low_latency": True, "require_function_calling": False},
    "config_generate": {"prefer_low_cost": False, "prefer_low_latency": False, "require_function_calling": False},
    "fault_diagnose": {"prefer_low_cost": False, "prefer_low_latency": False, "require_function_calling": False},
    "clarification": {"prefer_low_cost": True, "prefer_low_latency": True, "require_function_calling": False},
}


@dataclass
class ProviderConfig:
    name: str
    api_url: str
    api_key: str
    model: str
    max_tokens: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    supports_streaming: bool = True
    supports_function_calling: bool = False
    enabled: bool = True

    @property
    def cost_per_1k_tokens(self) -> float:
        return (self.cost_per_1k_input + self.cost_per_1k_output) / 2

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.api_key)


@dataclass
class ProviderMetrics:
    total_requests: int = 0
    success_count: int = 0
    avg_latency_ms: float = 0.0
    total_tokens: int = 0
    total_cost: float = 0.0
    last_used: Optional[float] = None

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.5
        return self.success_count / self.total_requests


@dataclass
class TaskMetrics:
    total_requests: int = 0
    success_count: int = 0
    total_latency_ms: float = 0.0
    total_tokens: int = 0

    @property
    def avg_latency_ms(self) -> float:
        if self.success_count == 0:
            return DEFAULT_MAX_LATENCY_MS
        return self.total_latency_ms / self.success_count

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.5
        return self.success_count / self.total_requests


def _build_builtin_providers() -> Dict[str, ProviderConfig]:
    providers = {}

    providers["zhipu"] = ProviderConfig(
        name="zhipu",
        api_url=settings.zhipu_api_url,
        api_key=settings.zhipu_api_key,
        model=settings.zhipu_model,
        max_tokens=4096,
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0001,
        supports_streaming=True,
        supports_function_calling=True,
        enabled=True,
    )

    providers["deepseek"] = ProviderConfig(
        name="deepseek",
        api_url=settings.deepseek_api_url,
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        max_tokens=4096,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.002,
        supports_streaming=True,
        supports_function_calling=True,
        enabled=True,
    )

    providers["openai"] = ProviderConfig(
        name="openai",
        api_url="https://api.openai.com/v1/chat/completions",
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        max_tokens=4096,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
        supports_streaming=True,
        supports_function_calling=True,
        enabled=False,
    )

    providers["qwen"] = ProviderConfig(
        name="qwen",
        api_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        api_key="",
        model="qwen-max",
        max_tokens=4096,
        cost_per_1k_input=0.004,
        cost_per_1k_output=0.012,
        supports_streaming=True,
        supports_function_calling=True,
        enabled=False,
    )

    if settings.openai_compatible_api_url and settings.openai_compatible_api_key:
        providers["custom"] = ProviderConfig(
            name="custom",
            api_url=settings.openai_compatible_api_url,
            api_key=settings.openai_compatible_api_key,
            model=settings.openai_compatible_model or "default",
            max_tokens=4096,
            cost_per_1k_input=0.001,
            cost_per_1k_output=0.002,
            supports_streaming=True,
            supports_function_calling=False,
            enabled=True,
        )

    return providers


class LLMRouter:
    def __init__(self):
        self._providers: Dict[str, ProviderConfig] = _build_builtin_providers()
        self._metrics: Dict[str, ProviderMetrics] = {
            name: ProviderMetrics() for name in self._providers
        }
        self._task_metrics: Dict[str, Dict[str, TaskMetrics]] = {}
        self._enabled = settings.llm_router_enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def register_provider(self, provider_config: dict) -> ProviderConfig:
        name = provider_config.get("name")
        if not name:
            raise ValueError("provider_config 必须包含 name 字段")

        config = ProviderConfig(
            name=name,
            api_url=provider_config.get("api_url", ""),
            api_key=provider_config.get("api_key", ""),
            model=provider_config.get("model", ""),
            max_tokens=provider_config.get("max_tokens", 4096),
            cost_per_1k_input=provider_config.get("cost_per_1k_input", 0.0),
            cost_per_1k_output=provider_config.get("cost_per_1k_output", 0.0),
            supports_streaming=provider_config.get("supports_streaming", True),
            supports_function_calling=provider_config.get("supports_function_calling", False),
            enabled=provider_config.get("enabled", True),
        )

        self._providers[name] = config
        if name not in self._metrics:
            self._metrics[name] = ProviderMetrics()

        logger.info(f"LLM Router: 注册 provider '{name}' (model={config.model})")
        return config

    def update_provider(self, name: str, updates: dict) -> Optional[ProviderConfig]:
        if name not in self._providers:
            return None

        config = self._providers[name]
        for key, value in updates.items():
            if hasattr(config, key) and key != "name":
                setattr(config, key, value)

        logger.info(f"LLM Router: 更新 provider '{name}'")
        return config

    def remove_provider(self, name: str) -> bool:
        if name not in self._providers:
            return False

        del self._providers[name]
        self._metrics.pop(name, None)
        for task_metrics in self._task_metrics.values():
            task_metrics.pop(name, None)

        logger.info(f"LLM Router: 移除 provider '{name}'")
        return True

    def toggle_provider(self, name: str) -> Optional[ProviderConfig]:
        if name not in self._providers:
            return None

        config = self._providers[name]
        config.enabled = not config.enabled
        status = "启用" if config.enabled else "禁用"
        logger.info(f"LLM Router: {status} provider '{name}'")
        return config

    def select_model(self, task_type: str, preferences: dict = None) -> str:
        if not self._enabled:
            return self._fallback_select(task_type)

        prefs = dict(TASK_TYPE_DEFAULTS.get(task_type, {}))
        if preferences:
            prefs.update(preferences)

        candidates = []
        for name, config in self._providers.items():
            if not config.available:
                continue
            if prefs.get("require_function_calling") and not config.supports_function_calling:
                continue

            metrics = self._metrics.get(name, ProviderMetrics())
            task_m = self._get_task_metrics(name, task_type)

            score = self._calculate_score(config, metrics, task_m, prefs)
            candidates.append((name, score))

        if not candidates:
            fallback = self._fallback_select(task_type)
            if fallback is not None:
                return fallback
            logger.warning(f"No available LLM provider for task type '{task_type}'")
            return None

        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = candidates[0][0]
        logger.debug(f"LLM Router: 为任务 '{task_type}' 选择 provider '{selected}' (score={candidates[0][1]:.4f})")
        return selected

    def _calculate_score(
        self,
        config: ProviderConfig,
        metrics: ProviderMetrics,
        task_metrics: TaskMetrics,
        preferences: dict,
    ) -> float:
        success_rate = task_metrics.success_rate
        success_score = success_rate

        avg_latency = task_metrics.avg_latency_ms
        latency_score = max(0.0, 1.0 - avg_latency / DEFAULT_MAX_LATENCY_MS)

        cost = config.cost_per_1k_tokens
        max_cost = 0.05
        cost_score = max(0.0, 1.0 - cost / max_cost)

        feature_score = 0.5
        if config.supports_streaming:
            feature_score += 0.25
        if config.supports_function_calling:
            feature_score += 0.25

        if preferences.get("prefer_low_cost"):
            cost_score *= 1.5
        if preferences.get("prefer_low_latency"):
            latency_score *= 1.5
        if preferences.get("require_function_calling") and config.supports_function_calling:
            feature_score *= 1.5

        total = (
            WEIGHT_SUCCESS_RATE * success_score
            + WEIGHT_LATENCY * latency_score
            + WEIGHT_COST * cost_score
            + WEIGHT_FEATURE * feature_score
        )

        return total

    def _fallback_select(self, task_type: str) -> Optional[str]:
        for name in ["zhipu", "deepseek"]:
            if name in self._providers and self._providers[name].available:
                return name
        for name, config in self._providers.items():
            if config.available:
                return name
        logger.warning(f"No available LLM provider for task type '{task_type}'")
        return None

    def record_result(
        self,
        provider: str,
        task_type: str,
        latency_ms: int,
        success: bool,
        tokens_used: int,
    ):
        if provider not in self._providers:
            return

        metrics = self._metrics.get(provider)
        if metrics is None:
            metrics = ProviderMetrics()
            self._metrics[provider] = metrics

        metrics.total_requests += 1
        if success:
            metrics.success_count += 1
            current_avg = metrics.avg_latency_ms
            total_success = metrics.success_count
            metrics.avg_latency_ms = (
                (current_avg * (total_success - 1) + latency_ms) / total_success
            )
        metrics.total_tokens += tokens_used
        config = self._providers[provider]
        metrics.total_cost += (tokens_used / 1000.0) * config.cost_per_1k_tokens
        metrics.last_used = time.time()

        task_m = self._get_task_metrics(provider, task_type)
        task_m.total_requests += 1
        if success:
            task_m.success_count += 1
            task_m.total_latency_ms += latency_ms
        task_m.total_tokens += tokens_used

    def _get_task_metrics(self, provider: str, task_type: str) -> TaskMetrics:
        if task_type not in self._task_metrics:
            self._task_metrics[task_type] = {}
        task_map = self._task_metrics[task_type]
        if provider not in task_map:
            task_map[provider] = TaskMetrics()
        return task_map[provider]

    def get_provider_status(self) -> Dict[str, Any]:
        result = {}
        for name, config in self._providers.items():
            metrics = self._metrics.get(name, ProviderMetrics())
            result[name] = {
                "name": config.name,
                "model": config.model,
                "api_url": config.api_url,
                "enabled": config.enabled,
                "available": config.available,
                "supports_streaming": config.supports_streaming,
                "supports_function_calling": config.supports_function_calling,
                "cost_per_1k_input": config.cost_per_1k_input,
                "cost_per_1k_output": config.cost_per_1k_output,
                "max_tokens": config.max_tokens,
                "metrics": {
                    "total_requests": metrics.total_requests,
                    "success_count": metrics.success_count,
                    "success_rate": round(metrics.success_rate, 4),
                    "avg_latency_ms": round(metrics.avg_latency_ms, 1),
                    "total_tokens": metrics.total_tokens,
                    "total_cost": round(metrics.total_cost, 6),
                    "last_used": metrics.last_used,
                },
            }
        return result

    def get_recommendations(self, task_type: str) -> Dict[str, Any]:
        prefs = TASK_TYPE_DEFAULTS.get(task_type, {})
        candidates = []

        for name, config in self._providers.items():
            if not config.available:
                continue

            metrics = self._metrics.get(name, ProviderMetrics())
            task_m = self._get_task_metrics(name, task_type)
            score = self._calculate_score(config, metrics, task_m, prefs)

            candidates.append({
                "provider": name,
                "model": config.model,
                "score": round(score, 4),
                "success_rate": round(task_m.success_rate, 4),
                "avg_latency_ms": round(task_m.avg_latency_ms, 1),
                "cost_per_1k_tokens": config.cost_per_1k_tokens,
                "supports_function_calling": config.supports_function_calling,
                "supports_streaming": config.supports_streaming,
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)

        return {
            "task_type": task_type,
            "preferences": prefs,
            "recommendations": candidates,
            "best_choice": candidates[0]["provider"] if candidates else None,
        }

    def get_metrics(self) -> Dict[str, Any]:
        total_requests = sum(m.total_requests for m in self._metrics.values())
        total_success = sum(m.success_count for m in self._metrics.values())
        total_cost = sum(m.total_cost for m in self._metrics.values())
        total_tokens = sum(m.total_tokens for m in self._metrics.values())

        provider_summaries = {}
        for name, metrics in self._metrics.items():
            config = self._providers.get(name)
            provider_summaries[name] = {
                "model": config.model if config else "unknown",
                "total_requests": metrics.total_requests,
                "success_rate": round(metrics.success_rate, 4),
                "avg_latency_ms": round(metrics.avg_latency_ms, 1),
                "total_cost": round(metrics.total_cost, 6),
            }

        task_summaries = {}
        for task_type, task_map in self._task_metrics.items():
            task_summaries[task_type] = {
                provider: {
                    "total_requests": tm.total_requests,
                    "success_rate": round(tm.success_rate, 4),
                    "avg_latency_ms": round(tm.avg_latency_ms, 1),
                }
                for provider, tm in task_map.items()
            }

        return {
            "router_enabled": self._enabled,
            "total_requests": total_requests,
            "total_success_rate": round(total_success / total_requests, 4) if total_requests > 0 else 0.0,
            "total_cost": round(total_cost, 6),
            "total_tokens": total_tokens,
            "registered_providers": len(self._providers),
            "available_providers": sum(1 for c in self._providers.values() if c.available),
            "provider_summaries": provider_summaries,
            "task_summaries": task_summaries,
        }

    def get_provider_config(self, name: str) -> Optional[ProviderConfig]:
        return self._providers.get(name)


_llm_router_instance: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    global _llm_router_instance
    if _llm_router_instance is None:
        _llm_router_instance = LLMRouter()
    return _llm_router_instance
