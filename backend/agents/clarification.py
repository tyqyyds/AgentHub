"""澄清Agent - 当用户意图不明确时，主动提问澄清"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


class ClarificationType(Enum):
    """澄清类型"""
    INTENT_AMBIGUOUS = "intent_ambiguous"       # 意图模糊
    PARAMETER_MISSING = "parameter_missing"       # 参数缺失
    SCOPE_UNCLEAR = "scope_unclear"               # 范围不清
    DEVICE_UNSPECIFIED = "device_unspecified"     # 设备未指定
    PRIORITY_UNCLEAR = "priority_unclear"         # 优先级不清
    ACTION_CONFLICT = "action_conflict"           # 操作冲突


class QuestionStyle(Enum):
    """提问风格"""
    OPEN_ENDED = "open_ended"       # 开放式
    CHOICE_BASED = "choice_based"   # 选择式
    CONFIRMATION = "confirmation"   # 确认式


@dataclass
class ClarificationQuestion:
    """澄清问题"""
    question_id: str
    question_type: ClarificationType
    style: QuestionStyle
    question_text: str
    options: list[str] = field(default_factory=list)
    required: bool = True
    context_hint: str = ""


@dataclass
class ClarificationResult:
    """澄清结果"""
    needs_clarification: bool
    questions: list[ClarificationQuestion] = field(default_factory=list)
    confidence: float = 0.0
    original_input: str = ""
    clarification_reason: str = ""


@dataclass
class ClarificationConfig:
    """澄清Agent配置"""
    confidence_threshold: float = 0.6
    max_questions_per_round: int = 3
    enable_auto_suggestion: bool = True
    max_history_rounds: int = 5


# 意图关键词映射（用于判断意图类型）
INTENT_KEYWORD_MAP: dict[str, list[str]] = {
    "bandwidth": ["带宽", "速率", "吞吐", "流量控制", "限速"],
    "qos": ["QoS", "服务质量", "优先级", "队列", "调度"],
    "acl": ["ACL", "访问控制", "过滤", "白名单", "黑名单"],
    "route": ["路由", "静态路由", "动态路由", "BGP", "OSPF"],
    "vlan": ["VLAN", "虚拟局域网", "隔离", "Trunk", "Access"],
    "security": ["安全", "防火墙", "攻击防护", "DDoS", "IPS"],
    "healing": ["故障", "自愈", "恢复", "切换", "冗余"],
}

# 常见缺失参数模板
MISSING_PARAM_TEMPLATES: dict[str, ClarificationQuestion] = {
    "target_device": ClarificationQuestion(
        question_id="q_device",
        question_type=ClarificationType.DEVICE_UNSPECIFIED,
        style=QuestionStyle.CHOICE_BASED,
        question_text="请指定需要操作的目标设备",
        options=["核心交换机", "汇聚交换机", "接入交换机", "路由器", "防火墙"],
        required=True,
    ),
    "bandwidth_value": ClarificationQuestion(
        question_id="q_bandwidth",
        question_type=ClarificationType.PARAMETER_MISSING,
        style=QuestionStyle.OPEN_ENDED,
        question_text="请指定带宽大小（如：100Mbps、1Gbps）",
        required=True,
    ),
    "vlan_id": ClarificationQuestion(
        question_id="q_vlan",
        question_type=ClarificationType.PARAMETER_MISSING,
        style=QuestionStyle.OPEN_ENDED,
        question_text="请指定VLAN ID（1-4094）",
        required=True,
    ),
    "priority_level": ClarificationQuestion(
        question_id="q_priority",
        question_type=ClarificationType.PRIORITY_UNCLEAR,
        style=QuestionStyle.CHOICE_BASED,
        question_text="请选择优先级",
        options=["紧急", "高", "中", "低"],
        required=False,
    ),
    "scope": ClarificationQuestion(
        question_id="q_scope",
        question_type=ClarificationType.SCOPE_UNCLEAR,
        style=QuestionStyle.CHOICE_BASED,
        question_text="请选择操作范围",
        options=["单台设备", "指定设备组", "全网"],
        required=True,
    ),
}


class ClarificationAgent:
    """澄清Agent - 主动提问澄清模糊意图"""

    def __init__(self, config: Optional[ClarificationConfig] = None):
        self.config = config or ClarificationConfig()
        self._history: list[dict[str, Any]] = []
        self._stats: dict[str, int] = {
            "total_clarifications": 0,
            "intent_ambiguous": 0,
            "parameter_missing": 0,
            "device_unspecified": 0,
            "scope_unclear": 0,
            "auto_resolved": 0,
        }
        logger.info("澄清Agent初始化完成")

    def _detect_intent_type(self, user_input: str) -> Optional[str]:
        """检测意图类型"""
        scores: dict[str, int] = {}
        for intent_type, keywords in INTENT_KEYWORD_MAP.items():
            score = sum(1 for kw in keywords if kw in user_input)
            if score > 0:
                scores[intent_type] = score

        if not scores:
            return None
        return max(scores, key=scores.get)

    def _estimate_confidence(self, user_input: str) -> float:
        """估算意图置信度"""
        confidence = 0.3  # 基础置信度

        # 有明确意图关键词
        intent_type = self._detect_intent_type(user_input)
        if intent_type:
            confidence += 0.25

        # 有设备信息（IP地址模式）
        import re
        if re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", user_input):
            confidence += 0.15

        # 有具体数值
        if re.search(r"\d+\s*(Mbps|Gbps|Kbps|%)", user_input):
            confidence += 0.15

        # 有明确动作词
        action_words = ["配置", "修改", "创建", "删除", "查看", "启用", "禁用", "调整"]
        if any(w in user_input for w in action_words):
            confidence += 0.1

        # 输入过短
        if len(user_input) < 5:
            confidence -= 0.2

        return min(max(confidence, 0.0), 1.0)

    def _check_missing_params(self, user_input: str, intent_type: Optional[str]) -> list[ClarificationQuestion]:
        """检查缺失参数"""
        questions = []

        # 设备未指定
        import re
        has_device = bool(re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", user_input))
        device_keywords = ["交换机", "路由器", "防火墙", "设备", "核心", "汇聚", "接入"]
        has_device_kw = any(kw in user_input for kw in device_keywords)
        if not has_device and not has_device_kw:
            questions.append(MISSING_PARAM_TEMPLATES["target_device"])

        # 根据意图类型检查特定参数
        if intent_type == "bandwidth":
            if not re.search(r"\d+\s*(Mbps|Gbps|Kbps)", user_input):
                questions.append(MISSING_PARAM_TEMPLATES["bandwidth_value"])
        elif intent_type == "vlan":
            if not re.search(r"VLAN\s*\d+", user_input, re.IGNORECASE):
                questions.append(MISSING_PARAM_TEMPLATES["vlan_id"])

        # 范围检查
        scope_keywords = ["全网", "所有", "单台", "设备组", "区域"]
        if not any(kw in user_input for kw in scope_keywords) and intent_type is not None:
            questions.append(MISSING_PARAM_TEMPLATES["scope"])

        return questions[:self.config.max_questions_per_round]

    def _check_intent_ambiguity(self, user_input: str) -> Optional[ClarificationQuestion]:
        """检查意图模糊性"""
        detected_intents = []
        for intent_type, keywords in INTENT_KEYWORD_MAP.items():
            if any(kw in user_input for kw in keywords):
                detected_intents.append(intent_type)

        if len(detected_intents) > 2:
            intent_names = [INTENT_KEYWORD_MAP[it][0] for it in detected_intents[:3]]
            return ClarificationQuestion(
                question_id="q_ambiguous",
                question_type=ClarificationType.INTENT_AMBIGUOUS,
                style=QuestionStyle.CHOICE_BASED,
                question_text=f"您的需求涉及多个方面，请确认主要意图",
                options=intent_names,
                required=True,
                context_hint=f"检测到意图: {', '.join(detected_intents)}",
            )
        return None

    def clarify(self, user_input: str, context: Optional[dict] = None) -> ClarificationResult:
        """执行澄清分析"""
        self._stats["total_clarifications"] += 1
        questions: list[ClarificationQuestion] = []

        # 1. 估算置信度
        confidence = self._estimate_confidence(user_input)
        intent_type = self._detect_intent_type(user_input)

        # 2. 高置信度，无需澄清
        if confidence >= self.config.confidence_threshold:
            self._stats["auto_resolved"] += 1
            return ClarificationResult(
                needs_clarification=False,
                confidence=confidence,
                original_input=user_input,
                clarification_reason="置信度足够，无需澄清",
            )

        # 3. 检查意图模糊性
        ambiguity_q = self._check_intent_ambiguity(user_input)
        if ambiguity_q:
            questions.append(ambiguity_q)
            self._stats["intent_ambiguous"] += 1

        # 4. 检查缺失参数
        missing_qs = self._check_missing_params(user_input, intent_type)
        questions.extend(missing_qs)
        if missing_qs:
            for q in missing_qs:
                type_key = q.question_type.value
                if type_key in self._stats:
                    self._stats[type_key] += 1

        # 5. 限制问题数量
        questions = questions[:self.config.max_questions_per_round]

        # 6. 记录历史
        self._history.append({
            "user_input": user_input[:100],
            "confidence": confidence,
            "intent_type": intent_type,
            "question_count": len(questions),
        })
        if len(self._history) > self.config.max_history_rounds * 10:
            self._history = self._history[-self.config.max_history_rounds * 10:]

        reason = f"置信度={confidence:.2f} < 阈值={self.config.confidence_threshold}"
        if intent_type is None:
            reason += ", 无法识别意图类型"

        logger.info(f"澄清分析: '{user_input[:30]}...' 置信度={confidence:.2f}, 生成{len(questions)}个问题")

        return ClarificationResult(
            needs_clarification=len(questions) > 0,
            questions=questions,
            confidence=confidence,
            original_input=user_input,
            clarification_reason=reason,
        )

    def process_answer(self, question_id: str, answer: str) -> dict[str, Any]:
        """处理用户对澄清问题的回答"""
        result: dict[str, Any] = {
            "question_id": question_id,
            "answer": answer,
            "parsed": {},
        }

        if question_id == "q_device":
            result["parsed"]["target_device_type"] = answer
        elif question_id == "q_bandwidth":
            import re
            match = re.search(r"(\d+)\s*(Mbps|Gbps|Kbps)", answer, re.IGNORECASE)
            if match:
                result["parsed"]["bandwidth_value"] = int(match.group(1))
                result["parsed"]["bandwidth_unit"] = match.group(2).upper()
        elif question_id == "q_vlan":
            import re
            match = re.search(r"(\d+)", answer)
            if match:
                vlan_id = int(match.group(1))
                if 1 <= vlan_id <= 4094:
                    result["parsed"]["vlan_id"] = vlan_id
        elif question_id == "q_priority":
            priority_map = {"紧急": "urgent", "高": "high", "中": "medium", "低": "low"}
            result["parsed"]["priority"] = priority_map.get(answer, "medium")
        elif question_id == "q_scope":
            scope_map = {"单台设备": "single", "指定设备组": "group", "全网": "global"}
            result["parsed"]["scope"] = scope_map.get(answer, "single")
        elif question_id == "q_ambiguous":
            result["parsed"]["confirmed_intent"] = answer

        return result

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return self._stats

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Agent标准处理接口"""
        action = input_data.get("action", "clarify")

        if action == "clarify":
            user_input = input_data.get("user_input", "")
            context = input_data.get("context")
            result = self.clarify(user_input, context)
            return {
                "needs_clarification": result.needs_clarification,
                "questions": [
                    {
                        "question_id": q.question_id,
                        "type": q.question_type.value,
                        "style": q.style.value,
                        "text": q.question_text,
                        "options": q.options,
                        "required": q.required,
                    }
                    for q in result.questions
                ],
                "confidence": result.confidence,
                "reason": result.clarification_reason,
            }
        elif action == "answer":
            question_id = input_data.get("question_id", "")
            answer = input_data.get("answer", "")
            return self.process_answer(question_id, answer)
        else:
            return {"error": f"未知操作: {action}"}

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "confidence_threshold": self.config.confidence_threshold,
            "intent_types_tracked": len(INTENT_KEYWORD_MAP),
            "param_templates": len(MISSING_PARAM_TEMPLATES),
            "history_size": len(self._history),
            "stats": self._stats,
        }
