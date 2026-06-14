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
