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
