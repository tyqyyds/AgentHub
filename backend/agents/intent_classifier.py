from __future__ import annotations

import re
import json
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

try:
    from backend.agents.llm_gateway import get_llm_gateway, LLMGateway, TaskType, LLMProvider
    _llm_available = True
except ImportError:
    _llm_available = False
    logger.warning("LLMGateway不可用，意图分类器仅使用正则路径")


class IntentType(str, Enum):
    NAVIGATION = "navigation"
    QUERY = "query"
    CONTROL = "control"
    SCENE_MODE = "scene_mode"
    GENERAL = "general"
    PLAN_EXECUTE = "plan_execute"
    PROACTIVE_QUERY = "proactive_query"
    WIZARD = "wizard"
    FEEDBACK = "feedback"
    MULTIMODAL = "multimodal"


@dataclass
class IntentResult:
    intent_type: IntentType
    confidence: float
    entities: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    path: str = "regex"
    metadata: Dict[str, Any] = field(default_factory=dict)


_REGEX_PATTERNS: Dict[IntentType, List[str]] = {
    IntentType.NAVIGATION: [
        r'(?:去|打开|查看|跳转|导航|我要看).*(?:指挥舱|首页|仪表盘|dashboard)',
        r'(?:去|打开|查看|跳转|导航|我要看).*(?:意图|intent)',
        r'(?:去|打开|查看|跳转|导航|我要看).*(?:拓扑|topology)',
        r'(?:去|打开|查看|跳转|导航|我要看).*(?:自愈|故障|healing)',
        r'(?:去|打开|查看|跳转|导航|我要看).*(?:审计|日志|audit)',
        r'(?:去|打开|查看|跳转|导航|我要看).*(?:mcp|工具)',
        r'(?:去|打开|查看|跳转|导航|我要看).*(?:地图|agent.?map)',
        r'(?:去|打开|查看|跳转|导航|我要看).*(?:知识|问答|knowledge)',
        r'(?:去|打开|查看|跳转|导航|我要看).*(?:工单|workflow)',
    ],
    IntentType.QUERY: [
        r'(?:健康|状态|运行).*(?:如何|怎样|怎么样)',
        r'(?:有多少|有哪些|未处理).*(?:告警|报警|alert)|(?:告警|报警|alert).*(?:多少|有哪些|未处理)',
        r'(?:审批|待办|approve).*(?:多少|有哪些)',
        r'(?:故障|fault).*(?:根因|原因|reason)',
        r'(?:高危|危险).*(?:操作|变更)',
        r'(?:防火墙|firewall).*(?:修改|变更|策略)',
        r'(?:流量|traffic).*(?:趋势|统计)',
        r'(?:智能体|agent).*(?:分布|状态|多少)',
        r'(?:工单|order).*(?:待审批|有哪些|多少)',
        r'(?:工具|tool).*(?:可用|有哪些|列表)',
        r'(?:查看|检查|查询|显示|看看).*(?:路由器|交换机|设备|节点|防火墙|服务器).*(?:状态|信息|详情)',
    ],
    IntentType.CONTROL: [
        r'(?:重启|restart).*(?:路由器|设备|switch|router)',
        r'(?:隔离|isolate).*(?:节点|设备|node)',
        r'(?:创建|新建|提交).*(?:意图|intent)',
        r'(?:优化|optimize).*(?:带宽|qos|网络)',
        r'(?:执行|run).*(?:ping|测试)',
        r'(?:重试|retry).*(?:修复|healing)',
        r'(?:删除|delete|移除).*(?:意图|intent)',
        r'(?:关闭|shutdown).*(?:端口|接口|port|interface)',
        r'(?:切断|断开).*(?:端口|接口|连接)',
    ],
    IntentType.SCENE_MODE: [
        r'(?:开启|切换|进入).*(?:应急|紧急|emergency).*(?:模式)?',
        r'(?:开启|切换|进入).*(?:日常|巡检|daily|normal).*(?:模式)?',
        r'(?:开启|切换|进入).*(?:冻结|变更冻结|freeze).*(?:模式)?',
    ],
    IntentType.PLAN_EXECUTE: [
        r'(?:帮我|请|给我).*(?:规划|制定|设计).*(?:方案|计划|策略)',
        r'(?:制定|规划|设计).*(?:网络|运维|优化).*(?:方案|计划)',
        r'(?:分步|步骤|流程).*(?:执行|实施|完成)',
        r'(?:先.*再.*然后|第一步|第二步)',
    ],
    IntentType.PROACTIVE_QUERY: [
        r'(?:主动|自动|定时).*(?:检查|巡检|监控|扫描|检测)',
        r'(?:帮我|请).*(?:巡检|检查|扫描).*(?:网络|设备|系统)',
        r'(?:有没有|是否).*(?:异常|问题|风险|隐患)',
    ],
    IntentType.WIZARD: [
        r'(?:引导|指导|教|帮我).*(?:配置|设置|创建|部署)',
        r'(?:怎么|如何).*(?:配置|设置|创建|部署).*(?:QoS|策略|VLAN|ACL|防火墙)',
        r'(?:向导|wizard|步骤引导)',
    ],
    IntentType.FEEDBACK: [
        r'(?:这个|你).*(?:回答|结果|答案).*(?:不对|错误|不好|不满意)',
        r'(?:不对|错了|不准确|不正确)',
        r'(?:换一个|重新|再来).*(?:答案|回答|方案)',
        r'(?:👍|👎|好评|差评)',
    ],
    IntentType.MULTIMODAL: [
        r'(?:分析|识别|解读|看看).*(?:截图|图片|照片|图像|拓扑图)',
        r'(?:上传|发送).*(?:图片|截图|文件|日志)',
        r'(?:这张|这个).*(?:图|截图|拓扑)',
    ],
}

_INTENT_CLASSIFY_PROMPT = """你是智维AgentHub的意图分类引擎。根据用户输入，判断意图类型并提取实体。

## 意图类型列表:
1. navigation — 页面导航（跳转到某个页面）
2. query — 信息查询（查询系统状态、设备信息等）
3. control — 操作控制（执行重启、隔离、优化等操作）
4. scene_mode — 场景切换（日常/应急/冻结模式）
5. general — 通用对话（闲聊、模糊问题）
6. plan_execute — 规划执行（需要多步骤规划后执行）
7. proactive_query — 主动查询（主动巡检、自动检测）
8. wizard — 向导引导（引导用户完成配置流程）
9. feedback — 反馈评价（对回答的反馈）
10. multimodal — 多模态（涉及图片、截图、文件分析）

## 输出格式（纯JSON，不要markdown代码块）:
{
  "intent_type": "意图类型",
  "confidence": 0.0,
  "entities": {"提取的实体键值对"},
  "reasoning": "分类理由"
}

请只输出JSON，不要其他文字。"""

_IMPLICIT_INTENT_PROMPT = """你是隐含意图推断引擎。用户表达模糊，需要根据上下文推断真实意图。

## 上下文信息:
- 当前页面: {route}
- 最近查询: {recent_queries}
- 已知实体: {entities}

## 用户输入:
{user_input}

## 可能的隐含意图:
1. 用户说"网络慢" → 可能想查询流量统计或优化带宽
2. 用户说"有问题" → 可能想查看告警或启动故障诊断
3. 用户说"帮我看看" → 根据当前页面推断查询类型
4. 用户说"不对" → 可能是对上次回答的反馈

## 输出格式（纯JSON）:
{
  "inferred_intent": "推断的意图类型",
  "confidence": 0.0,
  "reasoning": "推断理由",
  "suggested_action": "建议的下一步操作"
}

请只输出JSON，不要其他文字。"""


class IntentClassifier:
    def __init__(self):
        self._llm: Optional[LLMGateway] = None
        if _llm_available:
            try:
                self._llm = get_llm_gateway()
            except Exception as e:
                logger.warning(f"LLMGateway初始化失败: {e}")
                self._llm = None
        self._compiled_patterns: Dict[IntentType, List[re.Pattern]] = {}
        for intent_type, patterns in _REGEX_PATTERNS.items():
            self._compiled_patterns[intent_type] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def classify_regex(self, text: str) -> Optional[IntentResult]:
        for intent_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    confidence = 0.9 if intent_type in (
                        IntentType.NAVIGATION, IntentType.QUERY,
                        IntentType.CONTROL, IntentType.SCENE_MODE,
                    ) else 0.8
                    entities = self._extract_entities(text)
                    return IntentResult(
                        intent_type=intent_type,
                        confidence=confidence,
                        entities=entities,
                        raw_text=text,
                        path="regex",
                    )
        return None

    async def classify_llm(self, text: str, context: Dict[str, Any] = None) -> IntentResult:
        if not self._llm:
            return IntentResult(
                intent_type=IntentType.GENERAL,
                confidence=0.3,
                entities={},
                raw_text=text,
                path="fallback",
            )

        context_str = ""
        if context:
            context_str = f"\n\n## 当前上下文:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

        messages = [
            {"role": "system", "content": _INTENT_CLASSIFY_PROMPT + context_str},
            {"role": "user", "content": f"请分类以下用户输入:\n{text}"},
        ]

        try:
            result = await self._llm.chat(
                messages,
                task_type=TaskType.INTENT_PARSE,
                temperature=0.1,
                max_tokens=256,
                preferred=LLMProvider.ZHIPU,
            )
            content = result.get("content", "")
            parsed = self._parse_llm_json(content)
            intent_str = parsed.get("intent_type", "general")
            try:
                intent_type = IntentType(intent_str)
            except ValueError:
                intent_type = IntentType.GENERAL
            return IntentResult(
                intent_type=intent_type,
                confidence=parsed.get("confidence", 0.5),
                entities=parsed.get("entities", {}),
                raw_text=text,
                path="llm",
                metadata={"provider": result.get("provider"), "reasoning": parsed.get("reasoning", "")},
            )
        except Exception as e:
            logger.warning(f"LLM意图分类失败: {e}")
            return IntentResult(
                intent_type=IntentType.GENERAL,
                confidence=0.3,
                entities={},
                raw_text=text,
                path="llm_fallback",
            )

    async def classify(self, text: str, context: Dict[str, Any] = None) -> IntentResult:
        regex_result = self.classify_regex(text)
        if regex_result and regex_result.confidence >= 0.8:
            return regex_result

        llm_result = await self.classify_llm(text, context)

        if regex_result and llm_result.confidence < regex_result.confidence:
            return regex_result
        return llm_result

    def infer_implicit_intent(
        self,
        text: str,
        context: Dict[str, Any] = None,
    ) -> Optional[IntentResult]:
        vague_patterns = [
            (r'(?:有点|稍微).*(?:慢|卡|延迟)', IntentType.QUERY, {"query_type": "performance"}),
            (r'(?:有问题|不对劲|异常)', IntentType.QUERY, {"query_type": "anomaly"}),
            (r'(?:帮我|看看|查查)$', IntentType.QUERY, {"query_type": "general_check"}),
            (r'(?:不好|不行|不满意)', IntentType.FEEDBACK, {"feedback_type": "negative"}),
        ]
        for pattern, intent_type, extra_entities in vague_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                entities = self._extract_entities(text)
                entities.update(extra_entities)
                if context:
                    route = context.get("route", "")
                    if "/topology" in route:
                        entities["inferred_scope"] = "topology"
                    elif "/self-healing" in route:
                        entities["inferred_scope"] = "fault"
                    elif "/audit" in route:
                        entities["inferred_scope"] = "audit"
                return IntentResult(
                    intent_type=intent_type,
                    confidence=0.6,
                    entities=entities,
                    raw_text=text,
                    path="implicit",
                    metadata={"context": context or {}},
                )
        return None

    def _extract_entities(self, text: str) -> Dict[str, str]:
        entities = {}
        device_match = re.search(
            r'((?:路由器|交换机|防火墙|服务器|设备)\s*[A-Za-z0-9\-_]+)', text, re.IGNORECASE
        )
        if device_match:
            entities["device"] = device_match.group(1)
        subnet_match = re.search(r'([\u4e00-\u9fa5]+子网)', text)
        if subnet_match:
            entities["subnet"] = subnet_match.group(1)
        bw_match = re.search(r'(\d+)\s*[MmGg]', text)
        if bw_match:
            entities["bandwidth"] = bw_match.group(0)
        port_match = re.search(r'((?:端口|接口|port|interface)\s*[A-Za-z0-9\/\-_]+)', text, re.IGNORECASE)
        if port_match:
            entities["port"] = port_match.group(1)
        return entities

    def _parse_llm_json(self, content: str) -> Dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r'^```\w*\n?', '', content)
            content = re.sub(r'\n?```$', '', content)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            try:
                from backend.agents.llm_utils import parse_llm_json
                return parse_llm_json(content)
            except Exception:
                return {"intent_type": "general", "confidence": 0.3, "entities": {}}


_classifier: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier


async def classify_intent(text: str, context: Dict[str, Any] = None) -> IntentResult:
    classifier = get_intent_classifier()
    return await classifier.classify(text, context)
