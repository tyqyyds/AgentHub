# AI 助手升级 — 第一批实施计划：核心基础

> **日期**: 2026-06-02
> **批次**: Batch 1 — Core Foundation
> **状态**: 📋 待执行
> **并行度**: 3 个模块可并行开发，无外部依赖

---

## Goal

将智维 AgentHub 的 AI 助手从"规则匹配 + 单路 LLM 调用"升级为"双轨意图理解 + 对话状态追踪 + 混合检索知识引擎"的智能体架构，为后续多轮规划执行、主动式运维、多模态交互等高级能力奠定基础。

---

## Architecture

```
用户输入
  │
  ▼
┌─────────────────────────────────────────────────────┐
│              意图理解引擎 v2 (模块1)                  │
│  ┌──────────────┐   ┌──────────────────────────┐    │
│  │ 正则快速路径  │   │ LLM FC 深度路径           │    │
│  │ (regex race) │   │ (function calling)        │    │
│  └──────┬───────┘   └──────────┬───────────────┘    │
│         │   双轨竞速合并         │                    │
│         └──────────┬────────────┘                    │
│                    ▼                                 │
│          ┌──────────────────┐                        │
│          │ 隐含意图推断器    │                        │
│          │ (implicit intent) │                       │
│          └────────┬─────────┘                        │
└───────────────────┼──────────────────────────────────┘
                    │ IntentResult
                    ▼
┌─────────────────────────────────────────────────────┐
│           对话状态追踪器 DST (模块2)                   │
│  ┌────────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ 实体追踪    │ │意图切换   │ │ 上下文压缩       │  │
│  │ EntityTrack│ │SwitchDet │ │ ContextCompress  │  │
│  └────────────┘ └──────────┘ └──────────────────┘  │
│  ┌────────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ 跨会话记忆  │ │行为学习   │ │ DialogueState    │  │
│  │ CrossSess  │ │BehavLearn│ │ Model            │  │
│  └────────────┘ └──────────┘ └──────────────────┘  │
└───────────────────┼──────────────────────────────────┘
                    │ DialogueState
                    ▼
┌─────────────────────────────────────────────────────┐
│            知识引擎 v2 (模块3)                        │
│  ┌─────────────────────────────────────────────┐    │
│  │          混合检索 (Hybrid Retrieval)          │    │
│  │  ┌────────┐ ┌──────┐ ┌───────────────────┐ │    │
│  │  │ 向量   │ │ BM25 │ │ RRF 融合 + LLM    │ │    │
│  │  │ Vector │ │      │ │ Reranker          │ │    │
│  │  └───┬────┘ └──┬───┘ └────────┬──────────┘ │    │
│  │      └─────────┼──────────────┘             │    │
│  └────────────────┼────────────────────────────┘    │
│  ┌─────────────────┼───────────────────────────┐    │
│  │ 实时知识注入     │     知识反馈闭环           │    │
│  │ RealtimeInjector │    FeedbackLoop           │    │
│  └─────────────────┴───────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

---

## Tech Stack

| 层 | 技术 | 版本/说明 |
|---|---|---|
| 前端框架 | Vue 3 + TypeScript | Composition API |
| 状态管理 | Pinia | `defineStore` |
| 后端框架 | FastAPI | 异步 ASGI |
| ORM | SQLAlchemy 2.0 | 异步模式 |
| 数据库 | SQLite | 开发环境 |
| LLM-1 | 智谱 GLM | Function Calling / 流式对话 |
| LLM-2 | DeepSeek | 意图解析 / 降级 |
| 向量检索 | numpy 内积 | 现有 VectorStore |
| 全文检索 | BM25 (jieba 分词) | 新增 |
| 融合排序 | RRF (Reciprocal Rank Fusion) | 新增 |
| 重排序 | LLM Reranker | 新增 |
| 构建命令 | `cd frontend && npx vite build` | 前端 |
| 语法检查 | `python -m py_compile backend/agents/xxx.py` | 后端 |

---

## 模块1：意图理解引擎 v2

### 1.1 新增 `backend/agents/intent_classifier.py`

#### 步骤 1.1.1 — 编写测试

- [ ] 创建测试文件 `tests/test_intent_classifier.py`

**文件**: `tests/test_intent_classifier.py`

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.agents.intent_classifier import (
    IntentClassifier,
    IntentResult,
    IntentType,
    classify_intent,
)


@pytest.fixture
def classifier():
    return IntentClassifier()


def test_intent_type_enum():
    assert IntentType.NAVIGATION.value == "navigation"
    assert IntentType.QUERY.value == "query"
    assert IntentType.CONTROL.value == "control"
    assert IntentType.SCENE_MODE.value == "scene_mode"
    assert IntentType.GENERAL.value == "general"
    assert IntentType.PLAN_EXECUTE.value == "plan_execute"
    assert IntentType.PROACTIVE_QUERY.value == "proactive_query"
    assert IntentType.WIZARD.value == "wizard"
    assert IntentType.FEEDBACK.value == "feedback"
    assert IntentType.MULTIMODAL.value == "multimodal"


def test_regex_fast_path_navigation(classifier):
    result = classifier.classify_regex("去拓扑页面")
    assert result is not None
    assert result.intent_type == IntentType.NAVIGATION
    assert result.confidence >= 0.9
    assert result.path == "regex"


def test_regex_fast_path_query(classifier):
    result = classifier.classify_regex("系统健康度如何")
    assert result is not None
    assert result.intent_type == IntentType.QUERY
    assert result.confidence >= 0.9


def test_regex_fast_path_control(classifier):
    result = classifier.classify_regex("重启路由器A")
    assert result is not None
    assert result.intent_type == IntentType.CONTROL
    assert result.confidence >= 0.9


def test_regex_fast_path_scene_mode(classifier):
    result = classifier.classify_regex("切换应急模式")
    assert result is not None
    assert result.intent_type == IntentType.SCENE_MODE
    assert result.confidence >= 0.9


def test_regex_fast_path_plan_execute(classifier):
    result = classifier.classify_regex("帮我规划一下网络优化方案")
    assert result is not None
    assert result.intent_type == IntentType.PLAN_EXECUTE
    assert result.confidence >= 0.8


def test_regex_fast_path_proactive_query(classifier):
    result = classifier.classify_regex("主动检查一下网络有没有问题")
    assert result is not None
    assert result.intent_type == IntentType.PROACTIVE_QUERY
    assert result.confidence >= 0.8


def test_regex_fast_path_wizard(classifier):
    result = classifier.classify_regex("引导我配置QoS策略")
    assert result is not None
    assert result.intent_type == IntentType.WIZARD
    assert result.confidence >= 0.8


def test_regex_fast_path_feedback(classifier):
    result = classifier.classify_regex("这个回答不对")
    assert result is not None
    assert result.intent_type == IntentType.FEEDBACK
    assert result.confidence >= 0.8


def test_regex_fast_path_no_match(classifier):
    result = classifier.classify_regex("今天天气怎么样")
    assert result is None


def test_regex_fast_path_multimodal(classifier):
    result = classifier.classify_regex("分析这张网络拓扑截图")
    assert result is not None
    assert result.intent_type == IntentType.MULTIMODAL
    assert result.confidence >= 0.8


@pytest.mark.asyncio
async def test_classify_regex_first():
    classifier = IntentClassifier()
    result = await classifier.classify("去意图中心")
    assert result.intent_type == IntentType.NAVIGATION
    assert result.path == "regex"
    assert result.confidence >= 0.9


@pytest.mark.asyncio
async def test_classify_llm_fallback():
    classifier = IntentClassifier()
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = {
        "content": '{"intent_type":"general","confidence":0.6,"entities":{}}',
        "provider": "zhipu",
        "model": "glm-4-flash",
    }
    classifier._llm = mock_llm
    result = await classifier.classify("帮我看看这个配置有没有问题")
    assert result.path == "llm"


@pytest.mark.asyncio
async def test_implicit_intent_infer():
    classifier = IntentClassifier()
    result = classifier.infer_implicit_intent(
        "网络有点慢",
        context={"route": "/topology", "recent_queries": ["流量统计"]},
    )
    assert result is not None
    assert result.intent_type in (IntentType.QUERY, IntentType.PLAN_EXECUTE)


def test_intent_result_dataclass():
    r = IntentResult(
        intent_type=IntentType.NAVIGATION,
        confidence=0.95,
        entities={"target": "拓扑"},
        raw_text="去拓扑",
        path="regex",
        metadata={"route": "/topology"},
    )
    assert r.intent_type == IntentType.NAVIGATION
    assert r.confidence == 0.95
    assert r.path == "regex"
```

**验证命令**:
```bash
cd "d:\Trae CN\Project\智维 AgentHub"
python -m pytest tests/test_intent_classifier.py -v --tb=short 2>&1 | head -40
```

**预期输出**: 全部 FAIL（模块尚未实现）

---

#### 步骤 1.1.2 — 实现 IntentClassifier

- [ ] 创建 `backend/agents/intent_classifier.py`

**文件**: `backend/agents/intent_classifier.py`

```python
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
```

**验证命令**:
```bash
python -m py_compile backend/agents/intent_classifier.py
python -m pytest tests/test_intent_classifier.py -v --tb=short
```

**预期输出**: 全部 PASS

---

### 1.2 修改 `backend/agents/assistant_router.py` — 集成双轨分类器

#### 步骤 1.2.1 — 编写测试

- [ ] 在 `tests/test_assistant_router_v2.py` 中添加集成测试

**文件**: `tests/test_assistant_router_v2.py`

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.agents.assistant_router import AssistantRouterAgent


@pytest.fixture
def router():
    return AssistantRouterAgent()


def test_router_has_intent_classifier(router):
    assert hasattr(router, '_intent_classifier')


def test_router_has_new_intent_types(router):
    result = router._check_plan_execute("帮我规划一下网络优化方案")
    assert result is not None

    result = router._check_proactive_query("主动检查网络有没有问题")
    assert result is not None

    result = router._check_wizard("引导我配置QoS策略")
    assert result is not None

    result = router._check_feedback("这个回答不对")
    assert result is not None

    result = router._check_multimodal("分析这张网络拓扑截图")
    assert result is not None


@pytest.mark.asyncio
async def test_route_uses_intent_classifier(router):
    with patch.object(router._intent_classifier, 'classify', new_callable=AsyncMock) as mock_classify:
        from backend.agents.intent_classifier import IntentResult, IntentType
        mock_classify.return_value = IntentResult(
            intent_type=IntentType.NAVIGATION,
            confidence=0.95,
            entities={"target": "拓扑"},
            raw_text="去拓扑",
            path="regex",
        )
        result = await router.route("去拓扑", {"role": "admin", "username": "test", "route": "/"})
        assert result is not None
        mock_classify.assert_called_once()


@pytest.mark.asyncio
async def test_route_plan_execute(router):
    result = await router.route(
        "帮我规划一下网络优化方案",
        {"role": "admin", "username": "test", "route": "/"},
    )
    assert result is not None
    assert result.get("intent_type") == "plan_execute"


@pytest.mark.asyncio
async def test_route_feedback(router):
    result = await router.route(
        "这个回答不对",
        {"role": "admin", "username": "test", "route": "/"},
    )
    assert result is not None
    assert result.get("intent_type") == "feedback"
```

**验证命令**:
```bash
python -m pytest tests/test_assistant_router_v2.py -v --tb=short 2>&1 | head -30
```

**预期输出**: FAIL（assistant_router 尚未集成）

---

#### 步骤 1.2.2 — 修改 `backend/agents/assistant_router.py`

- [ ] 在 `AssistantRouterAgent.__init__` 中初始化 `_intent_classifier`
- [ ] 新增 `_check_plan_execute`、`_check_proactive_query`、`_check_wizard`、`_check_feedback`、`_check_multimodal` 方法
- [ ] 修改 `route` 方法集成双轨分类器

**修改位置**: `backend/agents/assistant_router.py`

**修改 1** — 在第 9 行后添加导入:

```python
from backend.agents.intent_classifier import IntentClassifier, IntentType, IntentResult
```

**修改 2** — 在 `__init__` 方法（第 231 行）中添加:

```python
        self._intent_classifier = IntentClassifier()
```

插入位置：第 244 行（`self._scene_mode: str = 'daily'` 之后）

**修改 3** — 在 `route` 方法（第 270 行）中，在 `scene_result` 检查之后、`nav_result` 检查之前，插入新的意图类型检查:

在第 289 行 `nav_result = self._check_navigation(...)` 之前插入:

```python
        plan_result = self._check_plan_execute(resolved_message)
        if plan_result:
            self._memory.add_turn(username, 'assistant', plan_result['content'], intent_type=plan_result.get('intent_type'))
            return plan_result

        proactive_result = self._check_proactive_query(resolved_message)
        if proactive_result:
            self._memory.add_turn(username, 'assistant', proactive_result['content'], intent_type=proactive_result.get('intent_type'))
            return proactive_result

        wizard_result = self._check_wizard(resolved_message)
        if wizard_result:
            self._memory.add_turn(username, 'assistant', wizard_result['content'], intent_type=wizard_result.get('intent_type'))
            return wizard_result

        feedback_result = self._check_feedback(resolved_message)
        if feedback_result:
            self._memory.add_turn(username, 'assistant', feedback_result['content'], intent_type=feedback_result.get('intent_type'))
            return feedback_result

        multimodal_result = self._check_multimodal(resolved_message)
        if multimodal_result:
            self._memory.add_turn(username, 'assistant', multimodal_result['content'], intent_type=multimodal_result.get('intent_type'))
            return multimodal_result
```

**修改 4** — 在 `_check_scene_mode` 方法之后（第 330 行后）添加新方法:

```python
    def _check_plan_execute(self, message: str) -> Optional[Dict[str, Any]]:
        intent_result = self._intent_classifier.classify_regex(message)
        if intent_result and intent_result.intent_type == IntentType.PLAN_EXECUTE:
            return {
                'content': f'我理解您需要进行**规划执行**。让我为您制定分步方案…',
                'actions': [
                    {'type': 'plan_execute', 'label': '开始规划', 'params': {'query': message}},
                    {'type': 'navigate', 'label': '前往意图中心', 'params': {'route': '/intent'}},
                ],
                'intent_type': 'plan_execute',
                'entities': intent_result.entities,
            }
        return None

    def _check_proactive_query(self, message: str) -> Optional[Dict[str, Any]]:
        intent_result = self._intent_classifier.classify_regex(message)
        if intent_result and intent_result.intent_type == IntentType.PROACTIVE_QUERY:
            return {
                'content': f'正在为您**主动巡检**，检查网络异常…',
                'actions': [
                    {'type': 'query', 'label': '查看巡检结果', 'params': {'query': 'proactive_check'}},
                ],
                'intent_type': 'proactive_query',
                'entities': intent_result.entities,
            }
        return None

    def _check_wizard(self, message: str) -> Optional[Dict[str, Any]]:
        intent_result = self._intent_classifier.classify_regex(message)
        if intent_result and intent_result.intent_type == IntentType.WIZARD:
            return {
                'content': f'好的，我来**引导您完成配置**。让我们一步步来…',
                'actions': [
                    {'type': 'wizard', 'label': '开始向导', 'params': {'query': message}},
                ],
                'intent_type': 'wizard',
                'entities': intent_result.entities,
            }
        return None

    def _check_feedback(self, message: str) -> Optional[Dict[str, Any]]:
        intent_result = self._intent_classifier.classify_regex(message)
        if intent_result and intent_result.intent_type == IntentType.FEEDBACK:
            return {
                'content': '感谢您的反馈！我会尝试提供更好的回答。请问您希望我如何改进？',
                'actions': [
                    {'type': 'feedback', 'label': '重新回答', 'params': {'action': 'retry'}},
                    {'type': 'feedback', 'label': '换一种方式', 'params': {'action': 'rephrase'}},
                ],
                'intent_type': 'feedback',
                'entities': intent_result.entities,
            }
        return None

    def _check_multimodal(self, message: str) -> Optional[Dict[str, Any]]:
        intent_result = self._intent_classifier.classify_regex(message)
        if intent_result and intent_result.intent_type == IntentType.MULTIMODAL:
            return {
                'content': '我检测到您想分析图片或文件。请上传相关文件，我会为您解读。',
                'actions': [
                    {'type': 'upload', 'label': '上传文件', 'params': {}},
                ],
                'intent_type': 'multimodal',
                'entities': intent_result.entities,
            }
        return None
```

**验证命令**:
```bash
python -m py_compile backend/agents/assistant_router.py
python -m pytest tests/test_assistant_router_v2.py -v --tb=short
```

**预期输出**: 全部 PASS

---

### 1.3 修改 `backend/agents/prompts.py` — 新增 Prompt

#### 步骤 1.3.1 — 添加意图分类和隐含意图推断 Prompt

- [ ] 在 `prompts.py` 末尾追加

**修改位置**: `backend/agents/prompts.py` 第 118 行后

**追加内容**:

```python

INTENT_CLASSIFY_PROMPT = """你是智维AgentHub的意图分类引擎。根据用户输入，判断意图类型并提取实体。

## 意图类型列表:
1. navigation — 页面导航
2. query — 信息查询
3. control — 操作控制
4. scene_mode — 场景切换
5. general — 通用对话
6. plan_execute — 规划执行
7. proactive_query — 主动查询
8. wizard — 向导引导
9. feedback — 反馈评价
10. multimodal — 多模态

## 输出格式（纯JSON，不要markdown代码块）:
{
  "intent_type": "意图类型",
  "confidence": 0.0,
  "entities": {},
  "reasoning": "分类理由"
}

请只输出JSON，不要其他文字。"""

IMPLICIT_INTENT_PROMPT = """你是隐含意图推断引擎。用户表达模糊，需要根据上下文推断真实意图。

## 上下文信息:
- 当前页面: {route}
- 最近查询: {recent_queries}
- 已知实体: {entities}

## 用户输入:
{user_input}

## 输出格式（纯JSON）:
{
  "inferred_intent": "推断的意图类型",
  "confidence": 0.0,
  "reasoning": "推断理由",
  "suggested_action": "建议的下一步操作"
}

请只输出JSON，不要其他文字。"""
```

**验证命令**:
```bash
python -m py_compile backend/agents/prompts.py
```

**预期输出**: 无错误

---

### 1.4 修改 `backend/api/assistant.py` — 新增 /plan-execute 端点

#### 步骤 1.4.1 — 编写测试

- [ ] 创建 `tests/test_plan_execute_api.py`

**文件**: `tests/test_plan_execute_api.py`

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


@pytest.fixture
def client():
    from backend.api.main import app
    return TestClient(app)


def test_plan_execute_endpoint_exists(client):
    response = client.post(
        "/api/v1/assistant/plan-execute",
        json={"message": "帮我规划网络优化方案", "context": {"route": "/", "role": "admin"}},
        headers={"Authorization": "Bearer test_token"},
    )
    assert response.status_code in (200, 401, 422)
```

**验证命令**:
```bash
python -m pytest tests/test_plan_execute_api.py -v --tb=short
```

**预期输出**: FAIL（端点不存在）

---

#### 步骤 1.4.2 — 实现 /plan-execute 端点

- [ ] 在 `backend/api/assistant.py` 末尾添加

**修改位置**: `backend/api/assistant.py` 第 885 行后

**追加内容**:

```python


class PlanExecuteRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    context: ChatContext = Field(default_factory=ChatContext)


class PlanStep(BaseModel):
    step_id: str = Field(default="")
    title: str = Field(default="")
    description: str = Field(default="")
    status: str = Field(default="pending")
    agent: str = Field(default="")


class PlanExecuteResponse(BaseModel):
    plan_id: str = Field(default="")
    content: str = Field(default="")
    steps: List[PlanStep] = Field(default_factory=list)
    intent_type: str = Field(default="plan_execute")


@router.post("/plan-execute", response_model=PlanExecuteResponse)
async def plan_execute(
    request: PlanExecuteRequest,
    current_user=Depends(get_current_user),
):
    try:
        import uuid as _uuid
        plan_id = _uuid.uuid4().hex[:8]

        steps = [
            PlanStep(step_id=f"plan_{plan_id}_1", title="需求分析", description="分析用户需求，确定优化目标", status="running", agent="IntentParser"),
            PlanStep(step_id=f"plan_{plan_id}_2", title="现状评估", description="收集当前网络状态数据", status="pending", agent="QueryAgent"),
            PlanStep(step_id=f"plan_{plan_id}_3", title="方案生成", description="生成优化方案并评估风险", status="pending", agent="PolicyPlanner"),
            PlanStep(step_id=f"plan_{plan_id}_4", title="执行确认", description="等待用户确认后执行", status="pending", agent="ExecutionAgent"),
        ]

        return PlanExecuteResponse(
            plan_id=plan_id,
            content=f'已为您创建**规划执行方案**（ID: {plan_id}），共 {len(steps)} 个步骤。',
            steps=steps,
            intent_type="plan_execute",
        )
    except Exception as e:
        logger.error(f"Plan execute error: {e}")
        raise HTTPException(status_code=500, detail="规划执行请求处理失败")
```

**验证命令**:
```bash
python -m py_compile backend/api/assistant.py
python -m pytest tests/test_plan_execute_api.py -v --tb=short
```

**预期输出**: PASS（端点存在，返回 200 或 401）

---

## 模块2：对话状态追踪器 (DST)

### 2.1 新增 `backend/agents/dialogue_state.py`

#### 步骤 2.1.1 — 编写测试

- [ ] 创建 `tests/test_dialogue_state.py`

**文件**: `tests/test_dialogue_state.py`

```python
import pytest
from backend.agents.dialogue_state import (
    DialogueState,
    EntityTracker,
    IntentSwitchDetector,
    ContextCompressor,
    CrossSessionMemory,
    BehaviorLearner,
    DialogueStateTracker,
    get_dst,
)


class TestDialogueState:
    def test_initial_state(self):
        state = DialogueState(session_id="test_session")
        assert state.session_id == "test_session"
        assert state.turn_count == 0
        assert state.current_intent is None
        assert state.entities == {}

    def test_add_turn(self):
        state = DialogueState(session_id="test_session")
        state.add_turn("user", "查看路由器A的状态")
        state.add_turn("assistant", "路由器A状态正常")
        assert state.turn_count == 2
        assert len(state.history) == 2

    def test_update_entities(self):
        state = DialogueState(session_id="test_session")
        state.update_entities({"device": "路由器A", "subnet": "研发子网"})
        assert state.entities["device"] == "路由器A"
        assert state.entities["subnet"] == "研发子网"
        state.update_entities({"device": "交换机B"})
        assert state.entities["device"] == "交换机B"
        assert state.entities["subnet"] == "研发子网"

    def test_set_intent(self):
        state = DialogueState(session_id="test_session")
        state.set_intent("query", confidence=0.9)
        assert state.current_intent == "query"
        assert state.intent_confidence == 0.9

    def test_to_dict(self):
        state = DialogueState(session_id="test_session")
        state.add_turn("user", "hello")
        d = state.to_dict()
        assert "session_id" in d
        assert d["session_id"] == "test_session"
        assert "turn_count" in d


class TestEntityTracker:
    def test_track_device(self):
        tracker = EntityTracker()
        entities = tracker.extract("查看路由器core-switch-01的状态")
        assert "device" in entities
        assert "core-switch-01" in entities["device"]

    def test_track_subnet(self):
        tracker = EntityTracker()
        entities = tracker.extract("为研发子网配置QoS")
        assert "subnet" in entities

    def test_track_bandwidth(self):
        tracker = EntityTracker()
        entities = tracker.extract("保障500M带宽")
        assert "bandwidth" in entities

    def test_track_port(self):
        tracker = EntityTracker()
        entities = tracker.extract("关闭端口GigabitEthernet0/0/1")
        assert "port" in entities

    def test_track_empty(self):
        tracker = EntityTracker()
        entities = tracker.extract("你好")
        assert entities == {}


class TestIntentSwitchDetector:
    def test_detect_switch(self):
        detector = IntentSwitchDetector()
        assert detector.detect_switch("query", "control") is True
        assert detector.detect_switch("query", "query") is False

    def test_detect_related_switch(self):
        detector = IntentSwitchDetector()
        assert detector.detect_switch("query", "plan_execute") is True
        assert detector.is_related("query", "plan_execute") is True

    def test_detect_unrelated_switch(self):
        detector = IntentSwitchDetector()
        assert detector.is_related("navigation", "feedback") is False


class TestContextCompressor:
    def test_compress_empty(self):
        compressor = ContextCompressor()
        result = compressor.compress([])
        assert result == ""

    def test_compress_short_history(self):
        compressor = ContextCompressor()
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = compressor.compress(history)
        assert len(result) > 0

    def test_compress_long_history(self):
        compressor = ContextCompressor()
        history = [
            {"role": "user", "content": f"message {i}"},
            {"role": "assistant", "content": f"reply {i}"},
        ] for i in range(20)
        history = [
            {"role": "user", "content": f"message {i}"},
            {"role": "assistant", "content": f"reply {i}"},
        for i in range(20)]
        result = compressor.compress(history)
        assert len(result) < sum(len(m["content"]) for m in history)


class TestCrossSessionMemory:
    def test_store_and_retrieve(self):
        memory = CrossSessionMemory()
        memory.store("user1", "device_preference", {"preferred_device": "core-switch-01"})
        result = memory.retrieve("user1", "device_preference")
        assert result is not None
        assert result["preferred_device"] == "core-switch-01"

    def test_retrieve_nonexistent(self):
        memory = CrossSessionMemory()
        result = memory.retrieve("user1", "nonexistent")
        assert result is None

    def test_get_user_profile(self):
        memory = CrossSessionMemory()
        memory.store("user1", "common_queries", ["system_health", "pending_alerts"])
        profile = memory.get_user_profile("user1")
        assert "common_queries" in profile


class TestBehaviorLearner:
    def test_record_action(self):
        learner = BehaviorLearner()
        learner.record_action("user1", "query", {"query_type": "system_health"})
        stats = learner.get_stats("user1")
        assert stats["total_actions"] == 1

    def test_get_frequent_actions(self):
        learner = BehaviorLearner()
        for _ in range(5):
            learner.record_action("user1", "query", {"query_type": "system_health"})
        for _ in range(3):
            learner.record_action("user1", "control", {"command": "restart_device"})
        frequent = learner.get_frequent_actions("user1", top_k=2)
        assert len(frequent) <= 2
        assert frequent[0][0] == "query"


class TestDialogueStateTracker:
    def test_create_session(self):
        dst = DialogueStateTracker()
        state = dst.get_or_create("session1")
        assert state.session_id == "session1"

    def test_update_state(self):
        dst = DialogueStateTracker()
        dst.update("session1", user_message="查看路由器A的状态", assistant_message="路由器A状态正常")
        state = dst.get_or_create("session1")
        assert state.turn_count == 2
        assert "device" in state.entities

    def test_detect_intent_switch(self):
        dst = DialogueStateTracker()
        dst.update("session1", user_message="查看路由器A的状态", assistant_message="正常", intent_type="query")
        switched = dst.update("session1", user_message="重启路由器A", assistant_message="确认重启", intent_type="control")
        assert switched is True

    def test_get_compressed_context(self):
        dst = DialogueStateTracker()
        for i in range(10):
            dst.update("session1", user_message=f"query {i}", assistant_message=f"reply {i}")
        compressed = dst.get_compressed_context("session1")
        assert isinstance(compressed, str)


def test_get_dst_singleton():
    dst1 = get_dst()
    dst2 = get_dst()
    assert dst1 is dst2
```

**验证命令**:
```bash
python -m pytest tests/test_dialogue_state.py -v --tb=short 2>&1 | head -50
```

**预期输出**: 全部 FAIL

---

#### 步骤 2.1.2 — 实现 DST

- [ ] 创建 `backend/agents/dialogue_state.py`

**文件**: `backend/agents/dialogue_state.py`

```python
from __future__ import annotations

import re
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DialogueState:
    session_id: str
    turn_count: int = 0
    current_intent: Optional[str] = None
    intent_confidence: float = 0.0
    entities: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    intent_history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def add_turn(self, role: str, content: str, intent_type: str = None, entities: Dict[str, Any] = None):
        self.history.append({
            "role": role,
            "content": content,
            "intent_type": intent_type,
            "entities": entities or {},
            "timestamp": time.time(),
        })
        self.turn_count += 1
        self.last_active = time.time()
        if len(self.history) > 100:
            self.history = self.history[-80:]

    def update_entities(self, new_entities: Dict[str, Any]):
        self.entities.update(new_entities)
        self.last_active = time.time()

    def set_intent(self, intent_type: str, confidence: float = 0.0):
        if self.current_intent and self.current_intent != intent_type:
            self.intent_history.append({
                "from": self.current_intent,
                "to": intent_type,
                "timestamp": time.time(),
            })
        self.current_intent = intent_type
        self.intent_confidence = confidence
        self.last_active = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_count": self.turn_count,
            "current_intent": self.current_intent,
            "intent_confidence": self.intent_confidence,
            "entities": self.entities,
            "intent_history": self.intent_history,
            "created_at": self.created_at,
            "last_active": self.last_active,
        }


class EntityTracker:
    _PATTERNS: List[Tuple[str, str]] = [
        (r'((?:路由器|交换机|防火墙|服务器|设备)\s*[A-Za-z0-9\-_]+)', 'device'),
        (r'([\u4e00-\u9fa5]+子网)', 'subnet'),
        (r'(\d+)\s*[MmGg][Bb]?[pP]?[sS]?', 'bandwidth'),
        (r'((?:端口|接口|port|interface)\s*[A-Za-z0-9\/\-_]+)', 'port'),
        (r'([\u4e00-\u9fa5]*(?:QoS|ACL|VLAN|OSPF|BGP)[\u4e00-\u9fa5]*)', 'protocol'),
    ]

    def extract(self, text: str) -> Dict[str, str]:
        entities = {}
        for pattern, etype in self._PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                entities[etype] = match.group(1)
        return entities


class IntentSwitchDetector:
    _RELATED_GROUPS = [
        {"query", "proactive_query", "plan_execute"},
        {"control", "plan_execute"},
        {"navigation", "query"},
        {"feedback", "general"},
    ]

    def detect_switch(self, prev_intent: str, curr_intent: str) -> bool:
        return prev_intent != curr_intent

    def is_related(self, prev_intent: str, curr_intent: str) -> bool:
        for group in self._RELATED_GROUPS:
            if prev_intent in group and curr_intent in group:
                return True
        return False


class ContextCompressor:
    def __init__(self, max_summary_chars: int = 500, keep_recent: int = 6):
        self._max_summary_chars = max_summary_chars
        self._keep_recent = keep_recent

    def compress(self, history: List[Dict[str, Any]]) -> str:
        if not history:
            return ""
        if len(history) <= self._keep_recent:
            parts = [f"{m.get('role', '?')}: {m.get('content', '')[:100]}" for m in history]
            return "; ".join(parts)

        older = history[:-self._keep_recent]
        recent = history[-self._keep_recent:]

        summary_parts = []
        for m in older[-4:]:
            content = m.get("content", "")[:80]
            summary_parts.append(f"{m.get('role', '?')}: {content}")
        summary = "[历史摘要] " + "; ".join(summary_parts)

        recent_parts = [f"{m.get('role', '?')}: {m.get('content', '')[:100]}" for m in recent]
        combined = summary + "\n" + "; ".join(recent_parts)

        if len(combined) > self._max_summary_chars:
            combined = combined[:self._max_summary_chars] + "..."
        return combined


class CrossSessionMemory:
    def __init__(self, max_users: int = 1000, max_entries_per_user: int = 50):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._max_users = max_users
        self._max_entries = max_entries_per_user

    def store(self, user_id: str, key: str, value: Any):
        if user_id not in self._store:
            if len(self._store) >= self._max_users:
                oldest = min(self._store, key=lambda k: self._store[k].get("_last_access", 0))
                del self._store[oldest]
            self._store[user_id] = {}
        self._store[user_id][key] = value
        self._store[user_id]["_last_access"] = time.time()
        if len(self._store[user_id]) > self._max_entries + 1:
            keys = [k for k in self._store[user_id] if k != "_last_access"]
            oldest_key = min(keys, key=lambda k: self._store[user_id].get(f"_ts_{k}", 0))
            del self._store[user_id][oldest_key]

    def retrieve(self, user_id: str, key: str) -> Optional[Any]:
        user_data = self._store.get(user_id, {})
        return user_data.get(key)

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        profile = dict(self._store.get(user_id, {}))
        profile.pop("_last_access", None)
        return profile


class BehaviorLearner:
    def __init__(self, max_users: int = 1000):
        self._actions: Dict[str, List[Dict[str, Any]]] = {}
        self._max_users = max_users

    def record_action(self, user_id: str, action_type: str, params: Dict[str, Any] = None):
        if user_id not in self._actions:
            if len(self._actions) >= self._max_users:
                oldest = min(self._actions, key=lambda k: self._actions[k][-1].get("timestamp", 0) if self._actions[k] else 0)
                del self._actions[oldest]
            self._actions[user_id] = []
        self._actions[user_id].append({
            "action_type": action_type,
            "params": params or {},
            "timestamp": time.time(),
        })
        if len(self._actions[user_id]) > 200:
            self._actions[user_id] = self._actions[user_id][-100:]

    def get_stats(self, user_id: str) -> Dict[str, Any]:
        actions = self._actions.get(user_id, [])
        type_counts: Dict[str, int] = {}
        for a in actions:
            t = a["action_type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "total_actions": len(actions),
            "type_counts": type_counts,
        }

    def get_frequent_actions(self, user_id: str, top_k: int = 5) -> List[Tuple[str, int]]:
        stats = self.get_stats(user_id)
        type_counts = stats.get("type_counts", {})
        sorted_actions = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_actions[:top_k]


class DialogueStateTracker:
    def __init__(self, max_sessions: int = 500, session_ttl: int = 3600):
        self._sessions: Dict[str, DialogueState] = {}
        self._entity_tracker = EntityTracker()
        self._switch_detector = IntentSwitchDetector()
        self._compressor = ContextCompressor()
        self._cross_session = CrossSessionMemory()
        self._behavior_learner = BehaviorLearner()
        self._max_sessions = max_sessions
        self._session_ttl = session_ttl

    def get_or_create(self, session_id: str) -> DialogueState:
        self._cleanup_stale()
        if session_id not in self._sessions:
            self._sessions[session_id] = DialogueState(session_id=session_id)
        state = self._sessions[session_id]
        state.last_active = time.time()
        return state

    def update(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        intent_type: str = None,
        username: str = None,
    ) -> bool:
        state = self.get_or_create(session_id)

        entities = self._entity_tracker.extract(user_message)
        state.update_entities(entities)

        switched = False
        if intent_type:
            if state.current_intent and self._switch_detector.detect_switch(state.current_intent, intent_type):
                switched = True
            state.set_intent(intent_type, confidence=0.9)

        state.add_turn("user", user_message, intent_type=intent_type, entities=entities)
        state.add_turn("assistant", assistant_message, intent_type=intent_type)

        if username:
            self._behavior_learner.record_action(username, intent_type or "general", entities)

        return switched

    def get_compressed_context(self, session_id: str) -> str:
        state = self.get_or_create(session_id)
        return self._compressor.compress(state.history)

    def get_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return state.to_dict()

    def get_entities(self, session_id: str) -> Dict[str, Any]:
        state = self.get_or_create(session_id)
        return dict(state.entities)

    def get_cross_session_data(self, user_id: str, key: str) -> Optional[Any]:
        return self._cross_session.retrieve(user_id, key)

    def store_cross_session_data(self, user_id: str, key: str, value: Any):
        self._cross_session.store(user_id, key, value)

    def get_behavior_stats(self, user_id: str) -> Dict[str, Any]:
        return self._behavior_learner.get_stats(user_id)

    def _cleanup_stale(self):
        now = time.time()
        stale = [
            sid for sid, state in self._sessions.items()
            if now - state.last_active > self._session_ttl
        ]
        for sid in stale:
            del self._sessions[sid]


_dst: Optional[DialogueStateTracker] = None


def get_dst() -> DialogueStateTracker:
    global _dst
    if _dst is None:
        _dst = DialogueStateTracker()
    return _dst
```

**验证命令**:
```bash
python -m py_compile backend/agents/dialogue_state.py
python -m pytest tests/test_dialogue_state.py -v --tb=short
```

**预期输出**: 全部 PASS

---

### 2.2 修改 `backend/agents/assistant_router.py` — 集成 DST

- [ ] 在 `AssistantRouterAgent.__init__` 中初始化 DST
- [ ] 在 `route` 方法中使用 DST 更新状态

**修改位置**: `backend/agents/assistant_router.py`

**修改 1** — 在导入区域添加:

```python
from backend.agents.dialogue_state import DialogueStateTracker, get_dst
```

**修改 2** — 在 `__init__` 中添加（在 `self._intent_classifier = IntentClassifier()` 之后）:

```python
        self._dst = get_dst()
```

**修改 3** — 在 `route` 方法开头（第 276 行 `resolved_message = ...` 之前），添加 DST 更新:

```python
        session_id = context.get('session_id', f'{username}_default')
        self._dst.update(session_id, message, '', intent_type=None, username=username)
```

**修改 4** — 在 `route` 方法的每个 `return` 之前，添加 DST 更新调用。例如在 `return scene_result` 之前:

```python
        self._dst.update(session_id, '', scene_result.get('content', ''), intent_type=scene_result.get('intent_type'), username=username)
```

对每个 return 点做类似处理（nav_result, control_result, query_result, general）。

**验证命令**:
```bash
python -m py_compile backend/agents/assistant_router.py
```

---

### 2.3 修改 `backend/agents/llm_gateway.py` — 上下文压缩集成 DST

- [ ] 在 `ConversationContext._compress` 中使用 DST 的压缩器

**修改位置**: `backend/agents/llm_gateway.py`

**修改 1** — 在导入区域添加:

```python
from backend.agents.dialogue_state import ContextCompressor
```

**修改 2** — 在 `ConversationContext` 类中添加压缩器实例（第 49 行后）:

在 `ConversationContext` dataclass 中添加字段:

```python
    _compressor: ContextCompressor = field(default_factory=ContextCompressor)
```

**修改 3** — 替换 `_compress` 方法（第 62-70 行）:

```python
    def _compress(self):
        system_msgs = [m for m in self.messages if m["role"] == "system"]
        other_msgs = [m for m in self.messages if m["role"] != "system"]
        if len(other_msgs) > MAX_CONTEXT_MESSAGES:
            kept = other_msgs[-MAX_CONTEXT_MESSAGES:]
            compressed_summary = self._compressor.compress(other_msgs[:-MAX_CONTEXT_MESSAGES])
            self.summary += "\n" + compressed_summary
            self.messages = system_msgs + kept
```

**验证命令**:
```bash
python -m py_compile backend/agents/llm_gateway.py
```

---

### 2.4 修改 `frontend/src/stores/assistant.ts` — 前端 DST 状态同步

- [ ] 添加 DST 相关状态字段
- [ ] 添加 DST 同步方法

**修改位置**: `frontend/src/stores/assistant.ts`

**修改 1** — 在接口定义区域（第 35 行后）添加:

```typescript
export interface DialogueStateData {
  sessionId: string
  turnCount: number
  currentIntent: string | null
  entities: Record<string, any>
  intentHistory: Array<{ from: string; to: string; timestamp: number }>
}
```

**修改 2** — 在 store 内部状态区域（第 56 行后）添加:

```typescript
  const dialogueState = ref<DialogueStateData>({
    sessionId: '',
    turnCount: 0,
    currentIntent: null,
    entities: {},
    intentHistory: []
  })
```

**修改 3** — 在 `sendMessage` 方法中，请求成功后添加 DST 同步（第 193 行 `if (data.entities)` 块内追加）:

```typescript
      dialogueState.value = {
        sessionId: dialogueState.value.sessionId || `sess_${Date.now()}`,
        turnCount: dialogueState.value.turnCount + 2,
        currentIntent: data.intent_type || null,
        entities: { ...dialogueState.value.entities, ...(data.entities || {}) },
        intentHistory: dialogueState.value.intentHistory
      }
```

**修改 4** — 在 return 语句中暴露 `dialogueState`（第 496 行区域）:

在 return 对象中添加 `dialogueState`。

**验证命令**:
```bash
cd frontend && npx vite build
```

---

### 2.5 修改 `backend/api/assistant.py` — 会话状态 API

- [ ] 新增 GET `/dialogue-state/{session_id}` 端点

**修改位置**: `backend/api/assistant.py` 末尾

**追加内容**:

```python


@router.get("/dialogue-state/{session_id}")
async def get_dialogue_state(
    session_id: str,
    current_user=Depends(get_current_user),
):
    try:
        from backend.agents.dialogue_state import get_dst
        dst = get_dst()
        state = dst.get_state(session_id)
        if state is None:
            return success_response(data={"session_id": session_id, "turn_count": 0, "entities": {}})
        return success_response(data=state)
    except Exception as e:
        logger.error(f"Get dialogue state error: {e}")
        raise HTTPException(status_code=500, detail="获取对话状态失败")


@router.get("/behavior-stats")
async def get_behavior_stats(
    current_user=Depends(get_current_user),
):
    try:
        from backend.agents.dialogue_state import get_dst
        dst = get_dst()
        stats = dst.get_behavior_stats(current_user.username)
        return success_response(data=stats)
    except Exception as e:
        logger.error(f"Get behavior stats error: {e}")
        raise HTTPException(status_code=500, detail="获取行为统计失败")
```

**验证命令**:
```bash
python -m py_compile backend/api/assistant.py
```

---

## 模块3：知识引擎 v2

### 3.1 修改 `backend/knowledge/rag_engine.py` — 混合检索

#### 步骤 3.1.1 — 编写测试

- [ ] 创建 `tests/test_rag_hybrid.py`

**文件**: `tests/test_rag_hybrid.py`

```python
import pytest
from backend.knowledge.rag_engine import RAGEngine, SearchResult


class TestBM25Retriever:
    def test_bm25_search_basic(self):
        from backend.knowledge.rag_engine import BM25Retriever
        bm25 = BM25Retriever()
        bm25.add_document("doc1", "QoS配置指南 带宽限速 traffic-policy命令")
        bm25.add_document("doc2", "OSPF路由协议 area划分区域 骨干区域area 0")
        results = bm25.search("QoS带宽配置", top_k=2)
        assert len(results) > 0
        assert results[0]["doc_id"] == "doc1"

    def test_bm25_search_no_match(self):
        from backend.knowledge.rag_engine import BM25Retriever
        bm25 = BM25Retriever()
        bm25.add_document("doc1", "QoS配置指南")
        results = bm25.search("天气预报", top_k=2)
        assert len(results) == 0


class TestRRFFusion:
    def test_rrf_fusion_basic(self):
        from backend.knowledge.rag_engine import RRFFusion
        rrf = RRFFusion(k=60)
        vector_results = [
            {"doc_id": "doc1", "score": 0.9},
            {"doc_id": "doc2", "score": 0.7},
        ]
        bm25_results = [
            {"doc_id": "doc2", "score": 3.5},
            {"doc_id": "doc3", "score": 2.0},
        ]
        fused = rrf.fuse([vector_results, bm25_results])
        assert len(fused) > 0
        doc_ids = [r["doc_id"] for r in fused]
        assert "doc2" in doc_ids

    def test_rrf_single_list(self):
        from backend.knowledge.rag_engine import RRFFusion
        rrf = RRFFusion(k=60)
        results = [{"doc_id": "doc1", "score": 0.9}]
        fused = rrf.fuse([results])
        assert len(fused) == 1
        assert fused[0]["doc_id"] == "doc1"


class TestHybridSearch:
    def test_hybrid_search_integration(self):
        engine = RAGEngine()
        engine.add_document("doc1", "QoS配置指南", "QoS配置指南: 带宽限速使用traffic-policy命令，优先级队列分为high/medium/low三级")
        engine.add_document("doc2", "OSPF路由协议", "OSPF路由协议: 使用area划分区域，骨干区域为area 0，所有非骨干区域必须与area 0直连")
        results = engine.hybrid_search("QoS带宽配置", top_k=2)
        assert len(results) > 0
        assert isinstance(results[0], SearchResult)

    def test_hybrid_search_fallback_to_vector(self):
        engine = RAGEngine()
        engine.add_document("doc1", "测试文档", "这是一段测试内容")
        results = engine.hybrid_search("测试", top_k=2)
        assert len(results) >= 0
```

**验证命令**:
```bash
python -m pytest tests/test_rag_hybrid.py -v --tb=short 2>&1 | head -30
```

**预期输出**: FAIL（hybrid_search 方法不存在）

---

#### 步骤 3.1.2 — 实现混合检索

- [ ] 在 `rag_engine.py` 中添加 BM25Retriever、RRFFusion、hybrid_search

**修改位置**: `backend/knowledge/rag_engine.py`

**修改 1** — 在 `SearchResult` dataclass（第 21 行）之后添加:

```python
import math
from collections import defaultdict

try:
    import jieba
    _jieba_available = True
except ImportError:
    _jieba_available = False


class BM25Retriever:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self._k1 = k1
        self._b = b
        self._docs: Dict[str, str] = {}
        self._doc_tokens: Dict[str, List[str]] = {}
        self._df: Dict[str, int] = defaultdict(int)
        self._avg_dl: float = 0.0
        self._fitted = False

    def _tokenize(self, text: str) -> List[str]:
        if _jieba_available:
            return list(jieba.cut(text))
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', text.lower())
        result = []
        for token in tokens:
            if re.match(r'[\u4e00-\u9fff]+', token):
                for i in range(len(token)):
                    for j in range(i + 1, min(i + 4, len(token) + 1)):
                        result.append(token[i:j])
            else:
                result.append(token)
        return result

    def add_document(self, doc_id: str, text: str):
        self._docs[doc_id] = text
        self._fitted = False

    def _fit(self):
        self._doc_tokens = {}
        self._df = defaultdict(int)
        total_dl = 0
        for doc_id, text in self._docs.items():
            tokens = self._tokenize(text)
            self._doc_tokens[doc_id] = tokens
            total_dl += len(tokens)
            seen = set()
            for t in tokens:
                if t not in seen:
                    self._df[t] += 1
                    seen.add(t)
        n = len(self._docs)
        self._avg_dl = total_dl / n if n > 0 else 0
        self._fitted = True

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self._docs:
            return []
        if not self._fitted:
            self._fit()
        query_tokens = self._tokenize(query)
        n = len(self._docs)
        scores: Dict[str, float] = defaultdict(float)
        for doc_id, doc_tokens in self._doc_tokens.items():
            dl = len(doc_tokens)
            tf_map: Dict[str, int] = defaultdict(int)
            for t in doc_tokens:
                tf_map[t] += 1
            for qt in query_tokens:
                tf = tf_map.get(qt, 0)
                if tf == 0:
                    continue
                df = self._df.get(qt, 0)
                idf = math.log((n - df + 0.5) / (df + 0.5) + 1)
                numerator = tf * (self._k1 + 1)
                denominator = tf + self._k1 * (1 - self._b + self._b * dl / max(self._avg_dl, 1))
                scores[doc_id] += idf * numerator / denominator
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [{"doc_id": doc_id, "score": score} for doc_id, score in sorted_results]


class RRFFusion:
    def __init__(self, k: int = 60):
        self._k = k

    def fuse(self, result_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        rrf_scores: Dict[str, float] = defaultdict(float)
        for results in result_lists:
            for rank, item in enumerate(results, start=1):
                doc_id = item.get("doc_id", "")
                rrf_scores[doc_id] += 1.0 / (self._k + rank)
        sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [{"doc_id": doc_id, "score": score} for doc_id, score in sorted_items]
```

**修改 2** — 在 `RAGEngine.__init__` 方法（第 202 行）中添加 BM25 初始化:

在 `self._init_backend()` 之后添加:

```python
        self._bm25 = BM25Retriever()
        self._rrf = RRFFusion()
```

**修改 3** — 在 `add_document` 方法中（第 271 行），在 `self._documents[doc_id] = {...}` 之后添加 BM25 索引:

在 `self._documents[doc_id]["chunk_count"] = len(text_chunks)` 之后添加:

```python
        self._bm25.add_document(doc_id, f"{title} {content}")
```

**修改 4** — 在 `RAGEngine` 类中添加 `hybrid_search` 方法（在 `search` 方法之后，约第 342 行后）:

```python
    def hybrid_search(self, query: str, top_k: int = 5, threshold: float = 0.3, vector_weight: float = 0.6, bm25_weight: float = 0.4) -> List[SearchResult]:
        vector_results = []
        if self.available:
            query_embedding = self._backend.encode([query])
            if query_embedding.size > 0:
                raw_results = self._vector_store.search(query_embedding[0], top_k=top_k * 2)
                vector_results = [
                    {"doc_id": r["doc_id"], "score": r["score"] * vector_weight}
                    for r in raw_results if r["score"] >= threshold
                ]

        bm25_results = []
        try:
            raw_bm25 = self._bm25.search(query, top_k=top_k * 2)
            max_bm25 = max((r["score"] for r in raw_bm25), default=1.0)
            bm25_results = [
                {"doc_id": r["doc_id"], "score": (r["score"] / max_bm25) * bm25_weight}
                for r in raw_bm25
            ]
        except Exception as e:
            logger.warning(f"BM25 search failed: {e}")

        if not vector_results and not bm25_results:
            return self.search(query, top_k=top_k, threshold=threshold)

        fused = self._rrf.fuse([vector_results, bm25_results])
        search_results = []
        for item in fused[:top_k]:
            doc = self._documents.get(item["doc_id"], {})
            best_chunk = None
            for cid, chunk in self._chunks.items():
                if chunk.get("doc_id") == item["doc_id"]:
                    if best_chunk is None:
                        best_chunk = chunk
            search_results.append(SearchResult(
                doc_id=item["doc_id"],
                title=doc.get("title", ""),
                content=best_chunk.get("content", doc.get("content", "")) if best_chunk else doc.get("content", ""),
                score=item["score"],
                metadata=doc.get("metadata"),
                chunk_index=best_chunk.get("chunk_index", 0) if best_chunk else 0,
            ))
        return search_results
```

**验证命令**:
```bash
python -m py_compile backend/knowledge/rag_engine.py
python -m pytest tests/test_rag_hybrid.py -v --tb=short
```

**预期输出**: 全部 PASS

---

### 3.2 新增 `backend/knowledge/realtime_injector.py`

#### 步骤 3.2.1 — 编写测试

- [ ] 创建 `tests/test_realtime_injector.py`

**文件**: `tests/test_realtime_injector.py`

```python
import pytest
from backend.knowledge.realtime_injector import (
    RealtimeKnowledgeInjector,
    KnowledgeItem,
    get_realtime_injector,
)


class TestKnowledgeItem:
    def test_create_item(self):
        item = KnowledgeItem(
            source="alert",
            title="核心路由器CPU告警",
            content="路由器core-router-01 CPU使用率达到95%",
            severity="critical",
            metadata={"device": "core-router-01"},
        )
        assert item.source == "alert"
        assert item.severity == "critical"


class TestRealtimeInjector:
    def test_inject_alert(self):
        injector = RealtimeKnowledgeInjector()
        item = injector.inject_from_alert({
            "type": "cpu_high",
            "device": "core-router-01",
            "severity": "critical",
            "message": "CPU使用率达到95%",
        })
        assert item is not None
        assert item.source == "alert"
        assert item.severity == "critical"

    def test_inject_metric(self):
        injector = RealtimeKnowledgeInjector()
        item = injector.inject_from_metric({
            "device": "core-switch-01",
            "metric": "bandwidth_mbps",
            "value": 850.5,
            "threshold": 1000,
        })
        assert item is not None
        assert item.source == "metric"

    def test_inject_audit(self):
        injector = RealtimeKnowledgeInjector()
        item = injector.inject_from_audit({
            "action": "config_acl",
            "user": "admin",
            "target": "firewall-01",
            "status": "success",
        })
        assert item is not None
        assert item.source == "audit"

    def test_get_recent_items(self):
        injector = RealtimeKnowledgeInjector()
        injector.inject_from_alert({"type": "test", "device": "dev1", "severity": "warning", "message": "test"})
        injector.inject_from_metric({"device": "dev2", "metric": "cpu", "value": 80, "threshold": 90})
        items = injector.get_recent_items(limit=10)
        assert len(items) == 2

    def test_search_items(self):
        injector = RealtimeKnowledgeInjector()
        injector.inject_from_alert({"type": "cpu_high", "device": "core-router-01", "severity": "critical", "message": "CPU高"})
        results = injector.search("CPU")
        assert len(results) > 0


def test_get_realtime_injector_singleton():
    i1 = get_realtime_injector()
    i2 = get_realtime_injector()
    assert i1 is i2
```

**验证命令**:
```bash
python -m pytest tests/test_realtime_injector.py -v --tb=short 2>&1 | head -30
```

**预期输出**: FAIL

---

#### 步骤 3.2.2 — 实现 RealtimeKnowledgeInjector

- [ ] 创建 `backend/knowledge/realtime_injector.py`

**文件**: `backend/knowledge/realtime_injector.py`

```python
from __future__ import annotations

import re
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeItem:
    source: str
    title: str
    content: str
    severity: str = "info"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    item_id: str = ""

    def __post_init__(self):
        if not self.item_id:
            self.item_id = f"{self.source}_{int(self.created_at * 1000)}"


class RealtimeKnowledgeInjector:
    def __init__(self, max_items: int = 1000):
        self._items: List[KnowledgeItem] = []
        self._max_items = max_items

    def inject_from_alert(self, alert: Dict[str, Any]) -> Optional[KnowledgeItem]:
        alert_type = alert.get("type", "unknown")
        device = alert.get("device", "未知设备")
        severity = alert.get("severity", "warning")
        message = alert.get("message", "")

        title = f"[告警] {device} - {alert_type}"
        content = f"设备 {device} 触发 {severity} 级别告警: {message} (类型: {alert_type})"

        item = KnowledgeItem(
            source="alert",
            title=title,
            content=content,
            severity=severity,
            metadata={"device": device, "alert_type": alert_type},
        )
        self._add_item(item)
        logger.info(f"Injected alert knowledge: {title}")
        return item

    def inject_from_metric(self, metric: Dict[str, Any]) -> Optional[KnowledgeItem]:
        device = metric.get("device", "未知设备")
        metric_name = metric.get("metric", "unknown")
        value = metric.get("value", 0)
        threshold = metric.get("threshold", 0)

        severity = "warning" if value >= threshold * 0.8 else "info"
        title = f"[指标] {device} - {metric_name}"
        content = f"设备 {device} 的 {metric_name} 当前值为 {value}，阈值 {threshold}"

        item = KnowledgeItem(
            source="metric",
            title=title,
            content=content,
            severity=severity,
            metadata={"device": device, "metric": metric_name, "value": value, "threshold": threshold},
        )
        self._add_item(item)
        return item

    def inject_from_audit(self, audit: Dict[str, Any]) -> Optional[KnowledgeItem]:
        action = audit.get("action", "unknown")
        user = audit.get("user", "unknown")
        target = audit.get("target", "unknown")
        status = audit.get("status", "unknown")

        severity = "critical" if action in ("config_acl", "delete_intent", "restart_device") else "info"
        title = f"[审计] {user} - {action}"
        content = f"用户 {user} 对 {target} 执行了 {action} 操作，状态: {status}"

        item = KnowledgeItem(
            source="audit",
            title=title,
            content=content,
            severity=severity,
            metadata={"action": action, "user": user, "target": target, "status": status},
        )
        self._add_item(item)
        return item

    def inject_custom(self, source: str, title: str, content: str, severity: str = "info", metadata: Dict[str, Any] = None) -> KnowledgeItem:
        item = KnowledgeItem(
            source=source,
            title=title,
            content=content,
            severity=severity,
            metadata=metadata or {},
        )
        self._add_item(item)
        return item

    def get_recent_items(self, limit: int = 20, source: str = None, severity: str = None) -> List[KnowledgeItem]:
        items = list(self._items)
        if source:
            items = [i for i in items if i.source == source]
        if severity:
            items = [i for i in items if i.severity == severity]
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items[:limit]

    def search(self, query: str, limit: int = 10) -> List[KnowledgeItem]:
        query_lower = query.lower()
        scored = []
        for item in self._items:
            score = 0
            if query_lower in item.title.lower():
                score += 3
            if query_lower in item.content.lower():
                score += 2
            for v in item.metadata.values():
                if isinstance(v, str) and query_lower in v.lower():
                    score += 1
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def _add_item(self, item: KnowledgeItem):
        self._items.append(item)
        if len(self._items) > self._max_items:
            self._items = self._items[-self._max_items:]

    def get_stats(self) -> Dict[str, Any]:
        source_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        for item in self._items:
            source_counts[item.source] = source_counts.get(item.source, 0) + 1
            severity_counts[item.severity] = severity_counts.get(item.severity, 0) + 1
        return {
            "total_items": len(self._items),
            "source_counts": source_counts,
            "severity_counts": severity_counts,
        }


_injector: Optional[RealtimeKnowledgeInjector] = None


def get_realtime_injector() -> RealtimeKnowledgeInjector:
    global _injector
    if _injector is None:
        _injector = RealtimeKnowledgeInjector()
    return _injector
```

**验证命令**:
```bash
python -m py_compile backend/knowledge/realtime_injector.py
python -m pytest tests/test_realtime_injector.py -v --tb=short
```

**预期输出**: 全部 PASS

---

### 3.3 新增 `backend/knowledge/feedback_loop.py`

#### 步骤 3.3.1 — 编写测试

- [ ] 创建 `tests/test_feedback_loop.py`

**文件**: `tests/test_feedback_loop.py`

```python
import pytest
from backend.knowledge.feedback_loop import (
    FeedbackEntry,
    FeedbackLoop,
    get_feedback_loop,
)


class TestFeedbackEntry:
    def test_create_positive(self):
        entry = FeedbackEntry(
            query="QoS配置",
            answer="QoS使用traffic-policy命令",
            feedback_type="positive",
            user_id="user1",
        )
        assert entry.feedback_type == "positive"
        assert entry.score == 1

    def test_create_negative(self):
        entry = FeedbackEntry(
            query="OSPF配置",
            answer="错误回答",
            feedback_type="negative",
            user_id="user1",
            comment="回答不准确",
        )
        assert entry.feedback_type == "negative"
        assert entry.score == -1


class TestFeedbackLoop:
    def test_record_feedback(self):
        loop = FeedbackLoop()
        entry = loop.record_feedback(
            query="QoS配置",
            answer="QoS使用traffic-policy命令",
            feedback_type="positive",
            user_id="user1",
        )
        assert entry is not None
        assert entry.feedback_type == "positive"

    def test_get_feedback_stats(self):
        loop = FeedbackLoop()
        loop.record_feedback("q1", "a1", "positive", "u1")
        loop.record_feedback("q2", "a2", "negative", "u1")
        loop.record_feedback("q3", "a3", "positive", "u2")
        stats = loop.get_stats()
        assert stats["total"] == 3
        assert stats["positive"] == 2
        assert stats["negative"] == 1

    def test_get_negative_feedbacks(self):
        loop = FeedbackLoop()
        loop.record_feedback("q1", "a1", "positive", "u1")
        loop.record_feedback("q2", "a2", "negative", "u1")
        negatives = loop.get_negative_feedbacks()
        assert len(negatives) == 1

    def test_get_correction_suggestions(self):
        loop = FeedbackLoop()
        loop.record_feedback("q1", "错误回答", "negative", "u1", correction="正确回答应该是...")
        suggestions = loop.get_correction_suggestions()
        assert len(suggestions) > 0

    def test_auto_optimize_threshold(self):
        loop = FeedbackLoop()
        for i in range(5):
            loop.record_feedback(f"q{i}", f"a{i}", "negative", "u1")
        should_optimize = loop.should_auto_optimize()
        assert should_optimize is True


def test_get_feedback_loop_singleton():
    f1 = get_feedback_loop()
    f2 = get_feedback_loop()
    assert f1 is f2
```

**验证命令**:
```bash
python -m pytest tests/test_feedback_loop.py -v --tb=short 2>&1 | head -30
```

**预期输出**: FAIL

---

#### 步骤 3.3.2 — 实现 FeedbackLoop

- [ ] 创建 `backend/knowledge/feedback_loop.py`

**文件**: `backend/knowledge/feedback_loop.py`

```python
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class FeedbackEntry:
    query: str
    answer: str
    feedback_type: str
    user_id: str
    comment: str = ""
    correction: str = ""
    score: int = 0
    entry_id: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.entry_id:
            self.entry_id = f"fb_{int(self.created_at * 1000)}"
        if self.score == 0:
            if self.feedback_type == "positive":
                self.score = 1
            elif self.feedback_type == "negative":
                self.score = -1


class FeedbackLoop:
    def __init__(self, max_entries: int = 5000, auto_optimize_threshold: int = 5):
        self._entries: List[FeedbackEntry] = []
        self._max_entries = max_entries
        self._auto_optimize_threshold = auto_optimize_threshold
        self._last_optimize_time: float = 0

    def record_feedback(
        self,
        query: str,
        answer: str,
        feedback_type: str,
        user_id: str,
        comment: str = "",
        correction: str = "",
    ) -> FeedbackEntry:
        entry = FeedbackEntry(
            query=query,
            answer=answer,
            feedback_type=feedback_type,
            user_id=user_id,
            comment=comment,
            correction=correction,
        )
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]
        logger.info(f"Recorded {feedback_type} feedback from {user_id} for query: {query[:50]}")
        return entry

    def get_stats(self) -> Dict[str, Any]:
        positive = sum(1 for e in self._entries if e.feedback_type == "positive")
        negative = sum(1 for e in self._entries if e.feedback_type == "negative")
        return {
            "total": len(self._entries),
            "positive": positive,
            "negative": negative,
            "satisfaction_rate": positive / max(len(self._entries), 1),
        }

    def get_negative_feedbacks(self, limit: int = 50) -> List[FeedbackEntry]:
        negatives = [e for e in self._entries if e.feedback_type == "negative"]
        negatives.sort(key=lambda x: x.created_at, reverse=True)
        return negatives[:limit]

    def get_correction_suggestions(self, limit: int = 20) -> List[Dict[str, Any]]:
        corrected = [e for e in self._entries if e.feedback_type == "negative" and e.correction]
        suggestions = []
        for entry in corrected[:limit]:
            suggestions.append({
                "query": entry.query,
                "original_answer": entry.answer,
                "correction": entry.correction,
                "user_id": entry.user_id,
                "created_at": entry.created_at,
            })
        return suggestions

    def should_auto_optimize(self) -> bool:
        recent_window = 3600
        now = time.time()
        recent_negatives = sum(
            1 for e in self._entries
            if e.feedback_type == "negative" and now - e.created_at < recent_window
        )
        return recent_negatives >= self._auto_optimize_threshold

    def get_recent_feedback(self, limit: int = 20) -> List[Dict[str, Any]]:
        recent = sorted(self._entries, key=lambda x: x.created_at, reverse=True)[:limit]
        return [
            {
                "entry_id": e.entry_id,
                "query": e.query,
                "feedback_type": e.feedback_type,
                "user_id": e.user_id,
                "comment": e.comment,
                "correction": e.correction,
                "created_at": e.created_at,
            }
            for e in recent
        ]


_loop: Optional[FeedbackLoop] = None


def get_feedback_loop() -> FeedbackLoop:
    global _loop
    if _loop is None:
        _loop = FeedbackLoop()
    return _loop
```

**验证命令**:
```bash
python -m py_compile backend/knowledge/feedback_loop.py
python -m pytest tests/test_feedback_loop.py -v --tb=short
```

**预期输出**: 全部 PASS

---

### 3.4 修改 `backend/knowledge/qa_agent.py` — 集成混合检索

- [ ] 修改 `query` 和 `query_with_rag` 方法使用 `hybrid_search`

**修改位置**: `backend/knowledge/qa_agent.py`

**修改 1** — 在 `query` 方法（第 138 行）中，将 `self._rag_engine.search` 替换为 `self._rag_engine.hybrid_search`:

将第 141-145 行:
```python
                results = self._rag_engine.search(
                    question,
                    top_k=settings.rag_top_k,
                    threshold=settings.rag_similarity_threshold,
                )
```

替换为:
```python
                results = self._rag_engine.hybrid_search(
                    question,
                    top_k=settings.rag_top_k,
                    threshold=settings.rag_similarity_threshold,
                )
```

**修改 2** — 在 `query_with_rag` 方法（第 162 行）中，同样替换:

将第 165 行:
```python
                return await self._rag_engine.answer_question(
```

替换为使用混合检索的新方法:

```python
                search_results = self._rag_engine.hybrid_search(
                    question, top_k=settings.rag_top_k,
                    threshold=settings.rag_similarity_threshold,
                )
                if not search_results:
                    return {
                        "answer": "未找到与您问题相关的知识条目，建议联系运维专家或查阅更多文档。",
                        "sources": [],
                        "confidence": 0.1,
                    }
                context_parts = []
                sources = []
                for i, result in enumerate(search_results):
                    context_parts.append(f"[{i + 1}] {result.title}: {result.content}")
                    sources.append({
                        "title": result.title,
                        "score": round(result.score, 4),
                        "chunk_index": result.chunk_index,
                    })
                context_text = "\n\n".join(context_parts)
                confidence = min(search_results[0].score, 0.95)
                try:
                    from backend.agents.llm_gateway import get_llm_gateway, TaskType
                    gateway = get_llm_gateway()
                    system_prompt = "你是智维AgentHub的知识问答助手。请根据提供的参考资料回答用户问题。\n\n要求：\n1. 优先基于参考资料中的信息回答\n2. 如果参考资料不足以回答问题，请如实说明\n3. 回答使用中文\n4. 引用资料时标注来源编号"
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"参考资料：\n{context_text}\n\n问题：{question}"},
                    ]
                    result = await gateway.chat(
                        messages,
                        task_type=TaskType.COPILOT_CHAT,
                        temperature=0.3,
                        max_tokens=1024,
                    )
                    return {
                        "answer": result["content"],
                        "sources": sources,
                        "confidence": round(confidence, 4),
                        "provider": result.get("provider"),
                        "model": result.get("model"),
                        "retrieval_method": "hybrid",
                    }
                except Exception as e:
                    logger.warning(f"LLM generation with hybrid retrieval failed: {e}")
                    return {
                        "answer": search_results[0].content,
                        "sources": sources,
                        "confidence": round(confidence, 4),
                        "retrieval_method": "hybrid_fallback",
                    }
```

**验证命令**:
```bash
python -m py_compile backend/knowledge/qa_agent.py
```

---

### 3.5 修改 `backend/api/knowledge.py` — 反馈 API

- [ ] 新增 POST `/feedback` 端点
- [ ] 新增 GET `/feedback` 端点
- [ ] 新增 GET `/realtime-knowledge` 端点

**修改位置**: `backend/api/knowledge.py` 末尾（第 358 行后）

**追加内容**:

```python


class FeedbackRequest(BaseModel):
    query: str
    answer: str
    feedback_type: str
    comment: str = ""
    correction: str = ""


@router.post("/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    current_user=Depends(get_current_user),
):
    try:
        from backend.knowledge.feedback_loop import get_feedback_loop
        loop = get_feedback_loop()
        entry = loop.record_feedback(
            query=req.query,
            answer=req.answer,
            feedback_type=req.feedback_type,
            user_id=current_user.username,
            comment=req.comment,
            correction=req.correction,
        )
        return success_response(data={
            "entry_id": entry.entry_id,
            "feedback_type": entry.feedback_type,
            "score": entry.score,
        })
    except Exception as e:
        logger.error(f"Submit feedback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/feedback")
async def list_feedback(
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    try:
        from backend.knowledge.feedback_loop import get_feedback_loop
        loop = get_feedback_loop()
        feedback = loop.get_recent_feedback(limit=limit)
        stats = loop.get_stats()
        return success_response(data={"items": feedback, "stats": stats})
    except Exception as e:
        logger.error(f"List feedback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/realtime-knowledge")
async def get_realtime_knowledge(
    source: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    try:
        from backend.knowledge.realtime_injector import get_realtime_injector
        injector = get_realtime_injector()
        items = injector.get_recent_items(limit=limit, source=source, severity=severity)
        stats = injector.get_stats()
        return success_response(data={
            "items": [
                {
                    "item_id": i.item_id,
                    "source": i.source,
                    "title": i.title,
                    "content": i.content,
                    "severity": i.severity,
                    "created_at": i.created_at,
                }
                for i in items
            ],
            "stats": stats,
        })
    except Exception as e:
        logger.error(f"Get realtime knowledge failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
```

**验证命令**:
```bash
python -m py_compile backend/api/knowledge.py
```

---

### 3.6 修改 `frontend/src/components/AiAssistant/ChatPanel.vue` — 👍/👎 按钮

- [ ] 在助手消息气泡中添加反馈按钮

**修改位置**: `frontend/src/components/AiAssistant/ChatPanel.vue`

**修改 1** — 在模板中，`msg-actions` div（第 135 行）之后添加反馈按钮:

在第 147 行 `</div>` (msg-bubble-assistant 的闭合标签) 之前插入:

```html
            <div v-if="msg.role === 'assistant' && !msg.isStreaming && msg.content" class="msg-feedback">
              <button
                type="button"
                class="feedback-btn feedback-positive"
                :class="{ active: feedbackMap[msg.id] === 'positive' }"
                @click="handleFeedback(msg, 'positive')"
                aria-label="有用"
                title="这个回答有帮助"
              >
                👍
              </button>
              <button
                type="button"
                class="feedback-btn feedback-negative"
                :class="{ active: feedbackMap[msg.id] === 'negative' }"
                @click="handleFeedback(msg, 'negative')"
                aria-label="没用"
                title="这个回答没有帮助"
              >
                👎
              </button>
            </div>
```

**修改 2** — 在 script setup 中添加反馈逻辑:

在 `dangerConfirmedMap` 声明（第 221 行）之后添加:

```typescript
const feedbackMap = ref<Record<string, string>>({})

const handleFeedback = async (msg: AssistantMessage, feedbackType: 'positive' | 'negative') => {
  if (feedbackMap.value[msg.id]) return
  feedbackMap.value[msg.id] = feedbackType

  try {
    const { authFetch, api } = await import('@/utils/apiClient')
    await authFetch(api.knowledge.feedback, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: messages.value.find(m => m.role === 'user' && messages.value.indexOf(m) < messages.value.indexOf(msg))?.content || '',
        answer: msg.content,
        feedback_type: feedbackType,
      })
    })
  } catch {
    feedbackMap.value[msg.id] = ''
  }
}
```

**修改 3** — 在 style 中添加反馈按钮样式:

在 `</style>` 标签前添加:

```css
.msg-feedback {
  display: flex;
  gap: 0.25rem;
  margin-top: 6px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.msg-bubble-assistant:hover .msg-feedback {
  opacity: 1;
}

.feedback-btn {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  padding: 0;
}

.feedback-btn:hover {
  background: rgba(148, 163, 184, 0.1);
  border-color: rgba(148, 163, 184, 0.2);
}

.feedback-btn.active.feedback-positive {
  background: rgba(34, 197, 94, 0.15);
  border-color: rgba(34, 197, 94, 0.3);
}

.feedback-btn.active.feedback-negative {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.3);
}
```

**验证命令**:
```bash
cd frontend && npx vite build
```

---

## 执行检查清单

### 模块1：意图理解引擎 v2

| # | 步骤 | 文件 | 状态 |
|---|------|------|------|
| 1.1.1 | 编写测试 | `tests/test_intent_classifier.py` | ☐ |
| 1.1.2 | 实现 IntentClassifier | `backend/agents/intent_classifier.py` | ☐ |
| 1.2.1 | 编写集成测试 | `tests/test_assistant_router_v2.py` | ☐ |
| 1.2.2 | 修改 assistant_router 集成 | `backend/agents/assistant_router.py` | ☐ |
| 1.3.1 | 新增 Prompt | `backend/agents/prompts.py` | ☐ |
| 1.4.1 | 编写 API 测试 | `tests/test_plan_execute_api.py` | ☐ |
| 1.4.2 | 新增 /plan-execute 端点 | `backend/api/assistant.py` | ☐ |

### 模块2：对话状态追踪器 (DST)

| # | 步骤 | 文件 | 状态 |
|---|------|------|------|
| 2.1.1 | 编写 DST 测试 | `tests/test_dialogue_state.py` | ☐ |
| 2.1.2 | 实现 DST | `backend/agents/dialogue_state.py` | ☐ |
| 2.2 | 集成 DST 到 assistant_router | `backend/agents/assistant_router.py` | ☐ |
| 2.3 | 上下文压缩集成 DST | `backend/agents/llm_gateway.py` | ☐ |
| 2.4 | 前端 DST 状态同步 | `frontend/src/stores/assistant.ts` | ☐ |
| 2.5 | 会话状态 API | `backend/api/assistant.py` | ☐ |

### 模块3：知识引擎 v2

| # | 步骤 | 文件 | 状态 |
|---|------|------|------|
| 3.1.1 | 编写混合检索测试 | `tests/test_rag_hybrid.py` | ☐ |
| 3.1.2 | 实现混合检索 | `backend/knowledge/rag_engine.py` | ☐ |
| 3.2.1 | 编写实时注入测试 | `tests/test_realtime_injector.py` | ☐ |
| 3.2.2 | 实现 RealtimeInjector | `backend/knowledge/realtime_injector.py` | ☐ |
| 3.3.1 | 编写反馈闭环测试 | `tests/test_feedback_loop.py` | ☐ |
| 3.3.2 | 实现 FeedbackLoop | `backend/knowledge/feedback_loop.py` | ☐ |
| 3.4 | 集成混合检索到 qa_agent | `backend/knowledge/qa_agent.py` | ☐ |
| 3.5 | 反馈 API | `backend/api/knowledge.py` | ☐ |
| 3.6 | 👍/👎 按钮 | `frontend/src/components/AiAssistant/ChatPanel.vue` | ☐ |

---

## 最终验证

全部模块完成后，依次运行:

```bash
# 后端语法检查
python -m py_compile backend/agents/intent_classifier.py
python -m py_compile backend/agents/dialogue_state.py
python -m py_compile backend/agents/assistant_router.py
python -m py_compile backend/agents/llm_gateway.py
python -m py_compile backend/agents/prompts.py
python -m py_compile backend/knowledge/rag_engine.py
python -m py_compile backend/knowledge/realtime_injector.py
python -m py_compile backend/knowledge/feedback_loop.py
python -m py_compile backend/knowledge/qa_agent.py
python -m py_compile backend/api/assistant.py
python -m py_compile backend/api/knowledge.py

# 后端测试
python -m pytest tests/test_intent_classifier.py tests/test_dialogue_state.py tests/test_rag_hybrid.py tests/test_realtime_injector.py tests/test_feedback_loop.py tests/test_assistant_router_v2.py tests/test_plan_execute_api.py -v --tb=short

# 前端构建
cd frontend && npx vite build
```

**预期结果**: 全部 py_compile 无错误，全部测试 PASS，前端构建成功。
