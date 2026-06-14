import uuid
import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

try:
    from backend.agents.llm_gateway import get_llm_gateway, LLMGateway
except ImportError:
    get_llm_gateway = None
    LLMGateway = None

logger = logging.getLogger(__name__)

MAX_CLARIFICATION_ROUNDS = 3
SESSION_MAX_AGE_SECONDS = 1800

REQUIRED_FIELDS_MAP = {
    "bandwidth_guarantee": ["target_subnet", "bandwidth"],
    "access_control": ["target_subnet"],
    "qos_policy": ["target_subnet", "bandwidth"],
    "link_management": ["target_device"],
    "device_config": ["target_device"],
    "traffic_shaping": ["target_subnet", "bandwidth"],
    "fault_diagnosis": ["target_device"],
    "performance_monitoring": ["target_device"],
}

FIELD_DISPLAY_NAMES = {
    "target_subnet": "目标子网",
    "target_device": "目标设备",
    "bandwidth": "带宽值",
    "duration": "持续时间",
    "priority": "优先级",
}


@dataclass
class ClarificationSession:
    session_id: str
    original_input: str
    original_parsed: Dict[str, Any]
    missing_fields: List[str]
    questions: List[str]
    round: int = 1
    resolved: bool = False
    final_parsed: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    clarification_history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ClarificationResult:
    needs_clarification: bool
    confidence: float
    missing_fields: List[str]
    questions: List[str]
    session_id: Optional[str] = None


class ClarificationAgent:
    def __init__(self):
        self._gateway: Optional[LLMGateway] = None
        self._sessions: Dict[str, ClarificationSession] = {}

    @property
    def gateway(self):
        if self._gateway is None:
            if get_llm_gateway is None:
                return None
            try:
                self._gateway = get_llm_gateway()
            except Exception as e:
                logger.warning(f"Failed to initialize LLM gateway: {e}")
                return None
        return self._gateway

    def _cleanup_stale_sessions(self):
        now = time.time()
        stale = [
            sid for sid, sess in self._sessions.items()
            if now - sess.last_active > SESSION_MAX_AGE_SECONDS
        ]
        for sid in stale:
            del self._sessions[sid]

    def analyze_confidence(self, parsed_intent: Dict[str, Any]) -> ClarificationResult:
        intent_type = parsed_intent.get("intent_type", "unknown")
        confidence = parsed_intent.get("confidence", 1.0)

        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                confidence = 0.0

        needs_clarification = intent_type == "unknown" or confidence < 0.5

        if not needs_clarification:
            return ClarificationResult(
                needs_clarification=False,
                confidence=confidence,
                missing_fields=[],
                questions=[]
            )

        missing_fields = self._identify_missing_fields(parsed_intent)
        questions = self._generate_static_questions(missing_fields, parsed_intent)

        return ClarificationResult(
            needs_clarification=True,
            confidence=confidence,
            missing_fields=missing_fields,
            questions=questions
        )

    def _identify_missing_fields(self, parsed_intent: Dict[str, Any]) -> List[str]:
        intent_type = parsed_intent.get("intent_type", "unknown")
        missing = []

        required = REQUIRED_FIELDS_MAP.get(intent_type, [])
        for f in required:
            val = parsed_intent.get(f)
            if val is None or val == "" or val == "null":
                missing.append(f)

        if intent_type == "unknown":
            for f in ["target_subnet", "target_device", "bandwidth"]:
                val = parsed_intent.get(f)
                if val is None or val == "" or val == "null":
                    missing.append(f)

        return list(dict.fromkeys(missing))

    def _generate_static_questions(self, missing_fields: List[str], parsed_intent: Dict[str, Any]) -> List[str]:
        questions = []
        for f in missing_fields:
            display = FIELD_DISPLAY_NAMES.get(f, f)
            if f == "target_subnet":
                questions.append("请问需要操作哪个子网？（如：研发子网、生产子网、办公子网）")
            elif f == "target_device":
                questions.append("请问需要操作哪台设备？（如：core-switch-01、access-02）")
            elif f == "bandwidth":
                questions.append("请问需要保障/限制的带宽是多少？（如：500M、1G）")
            elif f == "duration":
                questions.append("请问策略需要持续多长时间？（如：1天、持续）")
            elif f == "priority":
                questions.append("请问优先级如何？（紧急/一般/低）")
            else:
                questions.append(f"请提供{display}信息")

        if parsed_intent.get("intent_type") == "unknown":
            questions.insert(0, "请问您想执行什么类型的操作？（如：带宽保障、访问控制、故障诊断等）")

        return questions

    async def generate_clarification_questions(
        self,
        user_input: str,
        parsed_intent: Dict[str, Any],
        missing_fields: List[str]
    ) -> List[str]:
        try:
            gateway = self.gateway
            if gateway is None:
                return self._generate_static_questions(missing_fields, parsed_intent)
            result = await gateway.generate_clarification_questions(
                intent_data=parsed_intent,
                user_input=user_input
            )

            clarification_questions = result.get("clarification_questions", [])
            questions = []
            for q in clarification_questions:
                question_text = q.get("question", "")
                options = q.get("options", [])
                if question_text:
                    if options:
                        options_str = "、".join(options)
                        questions.append(f"{question_text}（可选：{options_str}）")
                    else:
                        questions.append(question_text)

            if not questions:
                return self._generate_static_questions(missing_fields, parsed_intent)

            return questions
        except Exception as e:
            logger.warning(f"LLM生成澄清问题失败，回退到静态问题: {e}")
            return self._generate_static_questions(missing_fields, parsed_intent)

    def create_clarification_session(
        self,
        user_input: str,
        parsed_intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        self._cleanup_stale_sessions()

        session_id = f"clarify_{uuid.uuid4().hex[:12]}"
        clarification_result = self.analyze_confidence(parsed_intent)

        session = ClarificationSession(
            session_id=session_id,
            original_input=user_input,
            original_parsed=parsed_intent,
            missing_fields=clarification_result.missing_fields,
            questions=clarification_result.questions,
            round=1,
            resolved=False,
            final_parsed=None,
            created_at=time.time(),
            last_active=time.time(),
            clarification_history=[]
        )

        self._sessions[session_id] = session

        return {
            "session_id": session_id,
            "needs_clarification": clarification_result.needs_clarification,
            "confidence": clarification_result.confidence,
            "missing_fields": clarification_result.missing_fields,
            "questions": clarification_result.questions,
            "round": 1
        }

    async def process_clarification_response(
        self,
        session_id: str,
        user_response: str
    ) -> Dict[str, Any]:
        self._cleanup_stale_sessions()

        session = self._sessions.get(session_id)
        if not session:
            return {
                "resolved": False,
                "error": "会话不存在或已过期",
                "needs_more_clarification": False,
                "questions": []
            }

        session.last_active = time.time()
        session.clarification_history.append({
            "round": session.round,
            "question": session.questions,
            "user_response": user_response,
            "timestamp": time.time()
        })

        updated_parsed = self._merge_clarification_response(
            session.original_parsed,
            session.missing_fields,
            user_response
        )

        session.round += 1

        new_analysis = self.analyze_confidence(updated_parsed)

        if not new_analysis.needs_clarification or session.round > MAX_CLARIFICATION_ROUNDS:
            session.resolved = True
            session.final_parsed = updated_parsed
            del self._sessions[session_id]

            return {
                "resolved": True,
                "parsed_intent": updated_parsed,
                "needs_more_clarification": False,
                "questions": [],
                "round": session.round
            }

        session.original_parsed = updated_parsed
        session.missing_fields = new_analysis.missing_fields

        dynamic_questions = await self.generate_clarification_questions(
            session.original_input,
            updated_parsed,
            new_analysis.missing_fields
        )
        session.questions = dynamic_questions

        return {
            "resolved": False,
            "parsed_intent": updated_parsed,
            "needs_more_clarification": True,
            "questions": dynamic_questions,
            "round": session.round,
            "missing_fields": new_analysis.missing_fields
        }

    def _merge_clarification_response(
        self,
        original_parsed: Dict[str, Any],
        missing_fields: List[str],
        user_response: str
    ) -> Dict[str, Any]:
        import re

        updated = dict(original_parsed)

        if "target_subnet" in missing_fields:
            subnet_match = re.search(r"([\u4e00-\u9fa5]+子网)", user_response)
            if subnet_match:
                updated["target_subnet"] = subnet_match.group(1)
            elif any(kw in user_response for kw in ["研发", "生产", "办公", "测试"]):
                for label in ["研发子网", "生产子网", "办公子网", "测试子网"]:
                    if label[:2] in user_response:
                        updated["target_subnet"] = label
                        break

        if "target_device" in missing_fields:
            device_match = re.search(r"([\w]+-[\w]+-\d+)", user_response)
            if device_match:
                updated["target_device"] = device_match.group(1)
            else:
                for keyword in ["核心交换机", "接入交换机", "防火墙", "路由器"]:
                    if keyword in user_response:
                        device_map = {
                            "核心交换机": "core-switch-01",
                            "接入交换机": "access-02",
                            "防火墙": "firewall-01",
                            "路由器": "router-01"
                        }
                        updated["target_device"] = device_map.get(keyword, user_response.strip())
                        break

        if "bandwidth" in missing_fields:
            bw_match = re.search(r"(\d+)\s*[MmGg]", user_response)
            if bw_match:
                val = int(bw_match.group(1))
                unit = "M" if "g" not in bw_match.group(0).lower() else "G"
                updated["bandwidth"] = val * 1000 if unit == "G" else val
            else:
                bw_num = re.search(r"(\d+)", user_response)
                if bw_num:
                    updated["bandwidth"] = int(bw_num.group(1))

        if "duration" in missing_fields:
            time_match = re.search(r"(\d+)\s*(天|小时|分钟)", user_response)
            if time_match:
                updated["duration"] = time_match.group(0)
            elif "持续" in user_response or "永久" in user_response:
                updated["duration"] = "持续"

        if "priority" in missing_fields:
            if any(kw in user_response for kw in ["紧急", "关键", "高"]):
                updated["priority"] = "high"
            elif any(kw in user_response for kw in ["低", "最低"]):
                updated["priority"] = "low"
            elif any(kw in user_response for kw in ["一般", "中等", "中"]):
                updated["priority"] = "medium"

        intent_keywords = {
            "bandwidth_guarantee": ["带宽保障", "保障带宽", "带宽保证"],
            "access_control": ["访问控制", "权限控制", "ACL"],
            "qos_policy": ["QoS", "服务质量", "策略配置"],
            "link_management": ["链路管理", "链路切换", "负载均衡"],
            "device_config": ["设备配置", "配置修改", "接口配置"],
            "traffic_shaping": ["流量整形", "限速", "流量控制"],
            "fault_diagnosis": ["故障诊断", "故障排查", "问题诊断"],
            "performance_monitoring": ["性能监控", "监控指标", "监控"],
        }

        if updated.get("intent_type") == "unknown":
            for itype, keywords in intent_keywords.items():
                if any(kw in user_response for kw in keywords):
                    updated["intent_type"] = itype
                    break

        if updated.get("intent_type") != "unknown":
            new_confidence = updated.get("confidence", 0.3)
            filled_count = sum(1 for f in missing_fields if updated.get(f) is not None and updated.get(f) != "")
            if filled_count > 0:
                new_confidence = min(new_confidence + filled_count * 0.2, 0.95)
            updated["confidence"] = new_confidence
            updated["clarification_needed"] = new_confidence < 0.5

        return updated

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        return {
            "session_id": session.session_id,
            "original_input": session.original_input,
            "missing_fields": session.missing_fields,
            "questions": session.questions,
            "round": session.round,
            "resolved": session.resolved,
            "created_at": session.created_at,
            "last_active": session.last_active
        }

    def cancel_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False


_clarification_agent: Optional[ClarificationAgent] = None


def get_clarification_agent() -> ClarificationAgent:
    global _clarification_agent
    if _clarification_agent is None:
        _clarification_agent = ClarificationAgent()
    return _clarification_agent
