"""对话状态管理：多轮对话上下文维护

负责管理用户与系统之间的多轮对话状态，包括：
- 会话创建/恢复/销毁
- 对话上下文追踪（意图槽位填充进度）
- 话题切换检测
- 上下文窗口管理（防止超出LLM上下文限制）
- 对话历史摘要
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import asyncio

from ..core.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────── 内部枚举与数据类 ────────────────────────


class DialoguePhase(str, Enum):
    """对话阶段"""
    GREETING = "greeting"
    INTENT_COLLECTION = "intent_collection"
    SLOT_FILLING = "slot_filling"
    CONFIRMATION = "confirmation"
    EXECUTION = "execution"
    RESULT_FEEDBACK = "result_feedback"
    FOLLOW_UP = "follow_up"
    CLOSING = "closing"


class SlotStatus(str, Enum):
    """槽位填充状态"""
    EMPTY = "empty"
    PARTIAL = "partial"
    FILLED = "filled"
    CONFIRMED = "confirmed"


class TopicChangeType(str, Enum):
    """话题切换类型"""
    NONE = "none"
    SHIFT = "shift"          # 话题转移
    RETURN = "return"        # 回到之前话题
    ABANDON = "abandon"      # 放弃当前话题
    NESTED = "nested"        # 嵌套子话题


@dataclass
class SlotDefinition:
    """槽位定义"""
    name: str
    display_name: str
    required: bool = True
    slot_type: str = "string"
    enum_values: List[str] = field(default_factory=list)
    default_value: Optional[str] = None
    clarification_prompt: str = ""


@dataclass
class SlotValue:
    """槽位值"""
    name: str
    value: Optional[Any] = None
    status: SlotStatus = SlotStatus.EMPTY
    source: str = "user"  # user / system / inferred
    confidence: float = 0.0
    updated_at: Optional[datetime] = None


@dataclass
class DialogueTurn:
    """对话轮次"""
    turn_id: int
    role: str  # user / assistant / system
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    intent_detected: Optional[str] = None
    slots_extracted: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DialogueSession:
    """对话会话"""
    session_id: str
    user_id: int
    phase: DialoguePhase = DialoguePhase.GREETING
    current_intent: Optional[str] = None
    slots: Dict[str, SlotValue] = field(default_factory=dict)
    turns: List[DialogueTurn] = field(default_factory=list)
    topic_stack: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DialogueStateConfig:
    """对话状态管理配置"""
    max_turns_per_session: int = 100
    session_timeout_minutes: int = 30
    max_context_tokens: int = 4000
    summary_trigger_turns: int = 20
    max_topic_stack_depth: int = 5
    slot_confirmation_threshold: float = 0.85
    enable_auto_summary: bool = True


# ──────────────────────── 意图槽位模板 ────────────────────────

INTENT_SLOT_TEMPLATES: Dict[str, List[SlotDefinition]] = {
    "带宽保障": [
        SlotDefinition(name="target_device", display_name="目标设备", required=True,
                       clarification_prompt="请指定需要保障带宽的设备名称"),
        SlotDefinition(name="bandwidth_mbps", display_name="带宽大小(Mbps)", required=True,
                       slot_type="integer", clarification_prompt="请指定需要保障的带宽大小(Mbps)"),
        SlotDefinition(name="direction", display_name="方向", required=False,
                       enum_values=["上行", "下行", "双向"], default_value="双向"),
        SlotDefinition(name="priority", display_name="优先级", required=False,
                       enum_values=["高", "中", "低"], default_value="中"),
    ],
    "故障自愈": [
        SlotDefinition(name="fault_device", display_name="故障设备", required=True,
                       clarification_prompt="请指定故障设备名称或IP"),
        SlotDefinition(name="fault_type", display_name="故障类型", required=True,
                       enum_values=["链路中断", "设备宕机", "性能劣化", "配置异常"],
                       clarification_prompt="请选择故障类型：链路中断/设备宕机/性能劣化/配置异常"),
        SlotDefinition(name="healing_mode", display_name="自愈模式", required=False,
                       enum_values=["auto", "suggested", "alert_only"], default_value="suggested"),
    ],
    "流量调度": [
        SlotDefinition(name="source_device", display_name="源设备", required=True,
                       clarification_prompt="请指定流量源设备"),
        SlotDefinition(name="destination_device", display_name="目的设备", required=True,
                       clarification_prompt="请指定流量目的设备"),
        SlotDefinition(name="scheduling_policy", display_name="调度策略", required=False,
                       enum_values=["负载均衡", "主备切换", "按比例分流"], default_value="负载均衡"),
    ],
    "安全策略": [
        SlotDefinition(name="policy_type", display_name="策略类型", required=True,
                       enum_values=["ACL", "防火墙规则", "流量过滤", "访问控制"],
                       clarification_prompt="请选择安全策略类型"),
        SlotDefinition(name="target_zone", display_name="目标区域", required=True,
                       clarification_prompt="请指定策略应用的目标区域"),
        SlotDefinition(name="action", display_name="动作", required=False,
                       enum_values=["允许", "拒绝", "限速", "告警"], default_value="拒绝"),
    ],
}


# ──────────────────────── 对话状态管理器 ────────────────────────


class DialogueStateManager:
    """对话状态管理器

    核心职责：
    1. 多轮对话会话生命周期管理
    2. 意图槽位填充状态追踪
    3. 话题切换检测与上下文恢复
    4. 对话历史摘要（防止上下文溢出）
    5. 对话阶段状态机
    """

    def __init__(self, config: Optional[DialogueStateConfig] = None):
        self.config = config or DialogueStateConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._sessions: Dict[str, DialogueSession] = {}
        self._summaries: Dict[str, str] = {}

    # ──────────── 会话管理 ────────────

    def create_session(self, session_id: str, user_id: int) -> DialogueSession:
        """创建新会话"""
        if session_id in self._sessions:
            self.logger.warning("会话已存在，将恢复: session_id=%s", session_id)
            return self._sessions[session_id]

        session = DialogueSession(session_id=session_id, user_id=user_id)
        self._sessions[session_id] = session
        self.logger.info("创建对话会话: session_id=%s, user_id=%d", session_id, user_id)
        return session

    def get_session(self, session_id: str) -> Optional[DialogueSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        session = self._sessions.pop(session_id, None)
        if session:
            self._summaries.pop(session_id, None)
            self.logger.info("关闭对话会话: session_id=%s", session_id)
            return True
        return False

    def _cleanup_expired_sessions(self) -> int:
        """清理过期会话"""
        now = datetime.now(timezone.utc)
        timeout = timedelta(minutes=self.config.session_timeout_minutes)
        expired_ids = [
            sid
            for sid, session in self._sessions.items()
            if now - session.last_active_at > timeout
        ]
        for sid in expired_ids:
            self.close_session(sid)

        if expired_ids:
            self.logger.info("清理 %d 个过期对话会话", len(expired_ids))
        return len(expired_ids)

    # ──────────── 对话轮次管理 ────────────

    def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        intent_detected: Optional[str] = None,
        slots_extracted: Optional[Dict[str, Any]] = None,
    ) -> Optional[DialogueTurn]:
        """添加对话轮次"""
        session = self._sessions.get(session_id)
        if not session:
            self.logger.warning("会话不存在: session_id=%s", session_id)
            return None

        # 检查轮次上限
        if len(session.turns) >= self.config.max_turns_per_session:
            self.logger.warning("会话轮次已达上限: session_id=%s", session_id)
            return None

        turn = DialogueTurn(
            turn_id=len(session.turns) + 1,
            role=role,
            content=content,
            intent_detected=intent_detected,
            slots_extracted=slots_extracted or {},
        )
        session.turns.append(turn)
        session.last_active_at = datetime.now(timezone.utc)

        # 自动摘要触发
        if (
            self.config.enable_auto_summary
            and len(session.turns) % self.config.summary_trigger_turns == 0
        ):
            self._generate_summary(session_id)

        return turn

    # ──────────── 槽位管理 ────────────

    def initialize_slots(self, session_id: str, intent: str) -> bool:
        """根据意图初始化槽位"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        slot_defs = INTENT_SLOT_TEMPLATES.get(intent, [])
        session.current_intent = intent
        session.phase = DialoguePhase.SLOT_FILLING
        session.slots = {
            sd.name: SlotValue(name=sd.name, default_value=sd.default_value)
            for sd in slot_defs
        }

        # 填入默认值
        for sd in slot_defs:
            if sd.default_value is not None:
                session.slots[sd.name].value = sd.default_value
                session.slots[sd.name].status = SlotStatus.FILLED
                session.slots[sd.name].confidence = 1.0
                session.slots[sd.name].source = "system"
                session.slots[sd.name].updated_at = datetime.now(timezone.utc)

        self.logger.info(
            "初始化意图槽位: session_id=%s, intent=%s, slots=%d",
            session_id,
            intent,
            len(session.slots),
        )
        return True

    def fill_slot(
        self,
        session_id: str,
        slot_name: str,
        value: Any,
        confidence: float = 1.0,
        source: str = "user",
    ) -> bool:
        """填充槽位值"""
        session = self._sessions.get(session_id)
        if not session or slot_name not in session.slots:
            return False

        slot = session.slots[slot_name]
        slot.value = value
        slot.confidence = confidence
        slot.source = source
        slot.updated_at = datetime.now(timezone.utc)

        if confidence >= self.config.slot_confirmation_threshold:
            slot.status = SlotStatus.FILLED
        else:
            slot.status = SlotStatus.PARTIAL

        self.logger.debug(
            "填充槽位: session_id=%s, slot=%s, value=%s, confidence=%.2f",
            session_id,
            slot_name,
            str(value),
            confidence,
        )
        return True

    def get_missing_slots(self, session_id: str) -> List[SlotDefinition]:
        """获取未填充的必填槽位"""
        session = self._sessions.get(session_id)
        if not session or not session.current_intent:
            return []

        slot_defs = INTENT_SLOT_TEMPLATES.get(session.current_intent, [])
        missing = []
        for sd in slot_defs:
            if not sd.required:
                continue
            slot_value = session.slots.get(sd.name)
            if not slot_value or slot_value.status in (SlotStatus.EMPTY, SlotStatus.PARTIAL):
                missing.append(sd)

        return missing

    def get_slot_values(self, session_id: str) -> Dict[str, Any]:
        """获取所有已填充的槽位值"""
        session = self._sessions.get(session_id)
        if not session:
            return {}

        return {
            name: sv.value
            for name, sv in session.slots.items()
            if sv.status in (SlotStatus.FILLED, SlotStatus.CONFIRMED) and sv.value is not None
        }

    def confirm_slots(self, session_id: str) -> bool:
        """确认所有槽位"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        for slot in session.slots.values():
            if slot.status == SlotStatus.FILLED:
                slot.status = SlotStatus.CONFIRMED

        session.phase = DialoguePhase.CONFIRMATION
        return True

    # ──────────── 话题切换检测 ────────────

    def detect_topic_change(
        self, session_id: str, new_intent: str
    ) -> TopicChangeType:
        """检测话题切换类型"""
        session = self._sessions.get(session_id)
        if not session:
            return TopicChangeType.NONE

        current_intent = session.current_intent

        if not current_intent:
            return TopicChangeType.NONE

        if new_intent == current_intent:
            return TopicChangeType.NONE

        # 检查是否回到之前的话题
        if new_intent in session.topic_stack:
            return TopicChangeType.RETURN

        # 检查是否所有必填槽位已填充（当前话题已完成）
        missing = self.get_missing_slots(session_id)
        if not missing:
            return TopicChangeType.SHIFT

        # 当前话题未完成但用户切换了话题
        return TopicChangeType.ABANDON

    def handle_topic_change(
        self, session_id: str, new_intent: str, change_type: TopicChangeType
    ) -> bool:
        """处理话题切换"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        if change_type == TopicChangeType.SHIFT:
            # 保存当前话题到栈
            if session.current_intent:
                session.topic_stack.append(session.current_intent)
                if len(session.topic_stack) > self.config.max_topic_stack_depth:
                    session.topic_stack.pop(0)

        elif change_type == TopicChangeType.RETURN:
            # 从栈中恢复话题
            while session.topic_stack and session.topic_stack[-1] != new_intent:
                session.topic_stack.pop()
            if session.topic_stack:
                session.topic_stack.pop()

        elif change_type == TopicChangeType.ABANDON:
            # 放弃当前话题，压栈保存
            if session.current_intent:
                session.topic_stack.append(session.current_intent)

        self.logger.info(
            "话题切换: session_id=%s, from=%s, to=%s, type=%s",
            session_id,
            session.current_intent,
            new_intent,
            change_type.value,
        )

        self.initialize_slots(session_id, new_intent)
        return True

    # ──────────── 对话阶段状态机 ────────────

    def advance_phase(self, session_id: str) -> Optional[DialoguePhase]:
        """推进对话阶段"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        phase_transitions = {
            DialoguePhase.GREETING: DialoguePhase.INTENT_COLLECTION,
            DialoguePhase.INTENT_COLLECTION: DialoguePhase.SLOT_FILLING,
            DialoguePhase.SLOT_FILLING: DialoguePhase.CONFIRMATION,
            DialoguePhase.CONFIRMATION: DialoguePhase.EXECUTION,
            DialoguePhase.EXECUTION: DialoguePhase.RESULT_FEEDBACK,
            DialoguePhase.RESULT_FEEDBACK: DialoguePhase.FOLLOW_UP,
            DialoguePhase.FOLLOW_UP: DialoguePhase.CLOSING,
        }

        next_phase = phase_transitions.get(session.phase)
        if next_phase:
            session.phase = next_phase
            self.logger.info(
                "对话阶段推进: session_id=%s, phase=%s", session_id, next_phase.value
            )
        return next_phase

    # ──────────── 上下文摘要 ────────────

    def _generate_summary(self, session_id: str) -> Optional[str]:
        """生成对话摘要（模拟实现）

        实际实现应调用 LLM 生成摘要。
        """
        session = self._sessions.get(session_id)
        if not session or not session.turns:
            return None

        # 简单摘要：提取关键信息
        user_turns = [t for t in session.turns if t.role == "user"]
        assistant_turns = [t for t in session.turns if t.role == "assistant"]

        summary_parts = [
            f"对话轮次: {len(session.turns)}",
            f"当前意图: {session.current_intent or '未确定'}",
            f"当前阶段: {session.phase.value}",
        ]

        if session.slots:
            filled_slots = {
                k: v.value
                for k, v in session.slots.items()
                if v.status in (SlotStatus.FILLED, SlotStatus.CONFIRMED)
            }
            summary_parts.append(f"已填充槽位: {filled_slots}")

        if session.topic_stack:
            summary_parts.append(f"话题栈: {' → '.join(session.topic_stack)}")

        summary = " | ".join(summary_parts)
        self._summaries[session_id] = summary

        self.logger.info("生成对话摘要: session_id=%s", session_id)
        return summary

    def get_context_window(self, session_id: str, max_tokens: int = 0) -> List[DialogueTurn]:
        """获取适合上下文窗口的对话轮次

        从最近的轮次开始，逐步加入直到预估token数接近上限。
        """
        session = self._sessions.get(session_id)
        if not session:
            return []

        token_limit = max_tokens or self.config.max_context_tokens
        # 粗略估算：1个中文字≈2个token，1个英文词≈1.3个token
        estimated_tokens = 0
        selected_turns: List[DialogueTurn] = []

        for turn in reversed(session.turns):
            turn_tokens = len(turn.content) * 1.5  # 粗略估算
            if estimated_tokens + turn_tokens > token_limit:
                break
            selected_turns.insert(0, turn)
            estimated_tokens += turn_tokens

        return selected_turns

    # ──────────── Agent 标准接口 ────────────

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """处理对话状态管理任务

        支持的 action:
        - create_session: 创建会话
        - close_session: 关闭会话
        - add_turn: 添加对话轮次
        - init_slots: 初始化意图槽位
        - fill_slot: 填充槽位
        - get_missing_slots: 获取缺失槽位
        - get_slot_values: 获取槽位值
        - detect_topic: 检测话题切换
        - get_context: 获取上下文窗口
        - get_state: 获取完整会话状态
        - cleanup: 清理过期会话
        """
        action = task.get("action", "get_state")
        session_id = task.get("session_id", "")

        if action == "create_session":
            user_id = task.get("user_id", 0)
            session = self.create_session(session_id, user_id)
            return {
                "action": "create_session",
                "session_id": session.session_id,
                "phase": session.phase.value,
            }

        if action == "close_session":
            success = self.close_session(session_id)
            return {"action": "close_session", "success": success}

        if action == "add_turn":
            role = task.get("role", "user")
            content = task.get("content", "")
            intent_detected = task.get("intent_detected")
            slots_extracted = task.get("slots_extracted")
            turn = self.add_turn(
                session_id, role, content, intent_detected, slots_extracted
            )
            if not turn:
                return {"action": "add_turn", "success": False, "error": "会话不存在或轮次达上限"}
            return {
                "action": "add_turn",
                "success": True,
                "turn_id": turn.turn_id,
                "phase": self._sessions[session_id].phase.value
                if session_id in self._sessions
                else None,
            }

        if action == "init_slots":
            intent = task.get("intent", "")
            success = self.initialize_slots(session_id, intent)
            return {"action": "init_slots", "success": success, "intent": intent}

        if action == "fill_slot":
            slot_name = task.get("slot_name", "")
            value = task.get("value")
            confidence = task.get("confidence", 1.0)
            source = task.get("source", "user")
            success = self.fill_slot(session_id, slot_name, value, confidence, source)
            return {"action": "fill_slot", "success": success, "slot_name": slot_name}

        if action == "get_missing_slots":
            missing = self.get_missing_slots(session_id)
            return {
                "action": "get_missing_slots",
                "count": len(missing),
                "slots": [
                    {
                        "name": sd.name,
                        "display_name": sd.display_name,
                        "type": sd.slot_type,
                        "clarification_prompt": sd.clarification_prompt,
                        "enum_values": sd.enum_values,
                    }
                    for sd in missing
                ],
            }

        if action == "get_slot_values":
            values = self.get_slot_values(session_id)
            return {"action": "get_slot_values", "values": values}

        if action == "detect_topic":
            new_intent = task.get("new_intent", "")
            change_type = self.detect_topic_change(session_id, new_intent)
            return {
                "action": "detect_topic",
                "change_type": change_type.value,
                "new_intent": new_intent,
            }

        if action == "get_context":
            max_tokens = task.get("max_tokens", 0)
            turns = self.get_context_window(session_id, max_tokens)
            return {
                "action": "get_context",
                "turn_count": len(turns),
                "turns": [
                    {
                        "turn_id": t.turn_id,
                        "role": t.role,
                        "content": t.content,
                        "intent_detected": t.intent_detected,
                    }
                    for t in turns
                ],
                "summary": self._summaries.get(session_id),
            }

        if action == "get_state":
            session = self._sessions.get(session_id)
            if not session:
                return {"action": "get_state", "exists": False}
            return {
                "action": "get_state",
                "exists": True,
                "session_id": session.session_id,
                "user_id": session.user_id,
                "phase": session.phase.value,
                "current_intent": session.current_intent,
                "turn_count": len(session.turns),
                "slots": {
                    name: {
                        "value": sv.value,
                        "status": sv.status.value,
                        "confidence": sv.confidence,
                    }
                    for name, sv in session.slots.items()
                },
                "topic_stack": session.topic_stack,
                "last_active_at": session.last_active_at.isoformat(),
            }

        if action == "cleanup":
            count = self._cleanup_expired_sessions()
            return {"action": "cleanup", "cleaned_count": count}

        return {"error": f"未知 action: {action}"}

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        active_sessions = len(self._sessions)
        total_turns = sum(len(s.turns) for s in self._sessions.values())
        sessions_with_intent = sum(
            1 for s in self._sessions.values() if s.current_intent is not None
        )

        is_healthy = active_sessions < 1000  # 会话数上限

        return {
            "status": "healthy" if is_healthy else "degraded",
            "active_sessions": active_sessions,
            "sessions_with_intent": sessions_with_intent,
            "total_turns": total_turns,
            "summaries_cached": len(self._summaries),
            "session_timeout_minutes": self.config.session_timeout_minutes,
        }
