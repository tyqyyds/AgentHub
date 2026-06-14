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
