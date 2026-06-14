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
        history = []
        for i in range(20):
            history.append({"role": "user", "content": f"message {i}"})
            history.append({"role": "assistant", "content": f"reply {i}"})
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
