from __future__ import annotations

import re
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
