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
    result = await classifier.classify("今天天气怎么样啊")
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
