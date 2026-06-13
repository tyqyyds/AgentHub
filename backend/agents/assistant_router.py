"""助手路由Agent - 根据用户输入类型路由到合适的LLM和Agent"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


class InputType(Enum):
    """输入类型"""
    NETWORK_CONFIG = "network_config"
    FAULT_DIAGNOSIS = "fault_diagnosis"
    COPILOT_CHAT = "copilot_chat"
    INTENT_PARSE = "intent_parse"
    KNOWLEDGE_QUERY = "knowledge_query"
    UNKNOWN = "unknown"


class RouteTarget(Enum):
    """路由目标"""
    INTENT_PARSER = "intent_parser"
    COORDINATOR = "coordinator"
    REACT_ENGINE = "react_engine"
    CLARIFICATION = "clarification"
    DIRECT_LLM = "direct_llm"


@dataclass
class RouteDecision:
    """路由决策"""
    input_type: InputType
    target: RouteTarget
    llm_provider: str
    confidence: float
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantRouterConfig:
    """助手路由配置"""
    enable_intent_classification: bool = True
    confidence_threshold: float = 0.7
    fallback_target: RouteTarget = RouteTarget.CLARIFICATION
    max_history_context: int = 10


# 关键词路由规则
KEYWORD_RULES: list[dict[str, Any]] = [
    {
        "keywords": ["配置", "修改", "调整", "带宽", "QoS", "ACL", "路由", "接口", "VLAN", "策略"],
        "input_type": InputType.NETWORK_CONFIG,
        "target": RouteTarget.INTENT_PARSER,
        "llm_provider": "zhipu",
    },
    {
        "keywords": ["故障", "断网", "不通", "慢", "丢包", "延迟", "告警", "异常", "宕机", "超时"],
        "input_type": InputType.FAULT_DIAGNOSIS,
        "target": RouteTarget.REACT_ENGINE,
        "llm_provider": "zhipu",
    },
    {
        "keywords": ["帮我", "如何", "怎么", "什么是", "解释", "推荐", "建议", "分析"],
        "input_type": InputType.COPILOT_CHAT,
        "target": RouteTarget.DIRECT_LLM,
        "llm_provider": "deepseek",
    },
    {
        "keywords": ["查询", "查看", "状态", "信息", "列表", "统计"],
        "input_type": InputType.KNOWLEDGE_QUERY,
        "target": RouteTarget.COORDINATOR,
        "llm_provider": "deepseek",
    },
]


class AssistantRouter:
    """助手路由Agent - 智能路由用户输入"""

    def __init__(self, config: Optional[AssistantRouterConfig] = None):
        self.config = config or AssistantRouterConfig()
        self._conversation_history: list[dict[str, Any]] = []
        self._stats: dict[str, int] = {
            "total_routed": 0,
            "network_config_routed": 0,
            "fault_diagnosis_routed": 0,
            "copilot_chat_routed": 0,
            "intent_parse_routed": 0,
            "knowledge_query_routed": 0,
            "unknown_routed": 0,
            "fallback_triggered": 0,
        }
        logger.info("助手路由Agent初始化完成")

    def _classify_by_keywords(self, user_input: str) -> tuple[InputType, RouteTarget, str, float]:
        """基于关键词分类"""
        best_match = None
        best_score = 0

        for rule in KEYWORD_RULES:
            score = sum(1 for kw in rule["keywords"] if kw in user_input)
            if score > best_score:
                best_score = score
                best_match = rule

        if best_match and best_score > 0:
            confidence = min(best_score / 3.0, 1.0)
            return (
                best_match["input_type"],
                best_match["target"],
                best_match["llm_provider"],
                confidence,
            )

        return InputType.UNKNOWN, self.config.fallback_target, "deepseek", 0.3

    def _classify_by_pattern(self, user_input: str) -> tuple[InputType, float]:
        """基于模式分类"""
        import re

        config_patterns = [
            r"(配置|修改|调整|设置).*(带宽|QoS|ACL|路由|接口|VLAN)",
            r"(增加|减少|开启|关闭).*(策略|规则|限制)",
            r"(创建|删除|更新).*(VLAN|接口|路由)",
        ]
        for pattern in config_patterns:
            if re.search(pattern, user_input):
                return InputType.NETWORK_CONFIG, 0.85

        fault_patterns = [
            r"(无法|不能|失败).*(连接|访问|通信|ping)",
            r"(故障|异常|错误|告警).*(设备|链路|接口|协议)",
            r"(丢包|延迟|抖动|超时).*(严重|过高|异常)",
        ]
        for pattern in fault_patterns:
            if re.search(pattern, user_input):
                return InputType.FAULT_DIAGNOSIS, 0.85

        chat_patterns = [
            r"(什么是|解释|帮我|如何|怎么).*(?!(配置|修改|调整))",
            r"(推荐|建议|分析|评估)",
        ]
        for pattern in chat_patterns:
            if re.search(pattern, user_input):
                return InputType.COPILOT_CHAT, 0.8

        return InputType.UNKNOWN, 0.3

    def _consider_context(self, input_type: InputType, user_input: str) -> InputType:
        """考虑上下文修正分类"""
        if not self._conversation_history:
            return input_type

        recent = self._conversation_history[-3:]
        recent_types = [h.get("input_type") for h in recent if h.get("input_type")]

        if input_type == InputType.UNKNOWN and recent_types:
            most_common = max(set(recent_types), key=recent_types.count)
            if recent_types.count(most_common) >= 2:
                logger.debug(f"上下文修正: {input_type.value} -> {most_common}")
                return InputType(most_common)

        return input_type

    def route(self, user_input: str, context: Optional[dict] = None) -> RouteDecision:
        """路由用户输入"""
        self._stats["total_routed"] += 1

        kw_type, kw_target, kw_llm, kw_conf = self._classify_by_keywords(user_input)
        pattern_type, pattern_conf = self._classify_by_pattern(user_input)

        if pattern_conf > kw_conf:
            input_type = pattern_type
            confidence = pattern_conf
            if input_type == InputType.NETWORK_CONFIG:
                target = RouteTarget.INTENT_PARSER
                llm = "zhipu"
            elif input_type == InputType.FAULT_DIAGNOSIS:
                target = RouteTarget.REACT_ENGINE
                llm = "zhipu"
            elif input_type == InputType.COPILOT_CHAT:
                target = RouteTarget.DIRECT_LLM
                llm = "deepseek"
            else:
                target = self.config.fallback_target
                llm = "deepseek"
        else:
            input_type = kw_type
            target = kw_target
            llm = kw_llm
            confidence = kw_conf

        input_type = self._consider_context(input_type, user_input)

        if confidence < self.config.confidence_threshold:
            target = RouteTarget.CLARIFICATION
            self._stats["fallback_triggered"] += 1

        type_stats_key = f"{input_type.value}_routed"
        if type_stats_key in self._stats:
            self._stats[type_stats_key] += 1
        else:
            self._stats["unknown_routed"] += 1

        self._conversation_history.append({
            "user_input": user_input[:100],
            "input_type": input_type.value,
            "target": target.value,
            "timestamp": __import__("time").time(),
        })
        if len(self._conversation_history) > self.config.max_history_context:
            self._conversation_history = self._conversation_history[-self.config.max_history_context:]

        decision = RouteDecision(
            input_type=input_type,
            target=target,
            llm_provider=llm,
            confidence=confidence,
            reasoning=f"关键词匹配={kw_conf:.2f}, 模式匹配={pattern_conf:.2f}, 最终={confidence:.2f}",
        )

        logger.info(f"路由决策: {user_input[:30]}... -> {target.value} (LLM: {llm}, 置信度: {confidence:.2f})")
        return decision

    def get_stats(self) -> dict[str, Any]:
        """获取路由统计"""
        return self._stats

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Agent标准处理接口"""
        user_input = input_data.get("user_input", "")
        context = input_data.get("context")
        decision = self.route(user_input, context)

        return {
            "input_type": decision.input_type.value,
            "target": decision.target.value,
            "llm_provider": decision.llm_provider,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
        }

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "rules_count": len(KEYWORD_RULES),
            "history_size": len(self._conversation_history),
            "stats": self._stats,
        }
