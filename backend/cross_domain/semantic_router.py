from typing import Dict, List, Optional
from pydantic import BaseModel
from backend.cross_domain.registry import registry_center, AgentRegistration
import logging

logger = logging.getLogger(__name__)

KEYWORD_CAPABILITY_MAP = {
    "qos_config": ["QoS", "带宽", "流量", "限速", "队列", "调度", "bandwidth", "traffic", "rate"],
    "event_diagnosis": ["故障", "诊断", "自愈", "告警", "异常", "中断", "fault", "diagnosis", "alert", "healing"],
    "policy_planning": ["路由", "策略", "规划", "优化", "负载均衡", "routing", "policy", "optimization"],
    "execution": ["配置", "执行", "下发", "部署", "变更", "commit", "deploy", "execute", "configure"],
    "intent_parsing": ["意图", "解析", "理解", "转换", "intent", "parse", "understand"],
}


class RoutingDecision(BaseModel):
    selected_agent: Optional[AgentRegistration] = None
    matched_capabilities: List[str] = []
    capability_scores: Dict[str, float] = {}
    load_score: float = 0.0
    total_score: float = 0.0
    explanation: str = ""
    candidates_count: int = 0


class SemanticRouter:
    def __init__(self):
        self._keyword_map = KEYWORD_CAPABILITY_MAP

    def _extract_capabilities(self, intent_text: str) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        intent_lower = intent_text.lower()
        for capability, keywords in self._keyword_map.items():
            match_count = 0
            for keyword in keywords:
                if keyword.lower() in intent_lower:
                    match_count += 1
            if match_count > 0:
                scores[capability] = min(match_count / len(keywords) + 0.3 * match_count, 1.0)
        return scores

    def route_intent(self, intent_text: str, required_capabilities: Optional[List[str]] = None) -> Optional[AgentRegistration]:
        capability_scores = self._extract_capabilities(intent_text)

        if required_capabilities:
            for cap in required_capabilities:
                if cap not in capability_scores:
                    capability_scores[cap] = 0.5

        if not capability_scores:
            return registry_center.get_least_loaded()

        target_capability = max(capability_scores, key=capability_scores.get)
        agents = registry_center.discover(capabilities=[target_capability])

        if not agents:
            all_agents = registry_center.discover()
            if all_agents:
                return min(all_agents, key=lambda a: a.cpu_load)
            return None

        best_agent = None
        best_score = -1.0
        for agent in agents:
            cap_score = sum(capability_scores.get(c, 0.0) for c in agent.capabilities) / max(len(agent.capabilities), 1)
            load_score = max(0.0, 1.0 - agent.cpu_load / 100.0)
            total_score = cap_score * 0.7 + load_score * 0.3
            if total_score > best_score:
                best_score = total_score
                best_agent = agent

        return best_agent

    def explain_routing(self, intent_text: str, required_capabilities: Optional[List[str]] = None) -> RoutingDecision:
        capability_scores = self._extract_capabilities(intent_text)

        if required_capabilities:
            for cap in required_capabilities:
                if cap not in capability_scores:
                    capability_scores[cap] = 0.5

        matched_capabilities = sorted(capability_scores.keys(), key=lambda k: capability_scores[k], reverse=True)

        selected_agent = self.route_intent(intent_text, required_capabilities)
        candidates_count = 0
        load_score = 0.0
        total_score = 0.0

        if selected_agent:
            cap_score = sum(capability_scores.get(c, 0.0) for c in selected_agent.capabilities) / max(len(selected_agent.capabilities), 1)
            load_score = max(0.0, 1.0 - selected_agent.cpu_load / 100.0)
            total_score = cap_score * 0.7 + load_score * 0.3
            target_cap = matched_capabilities[0] if matched_capabilities else None
            if target_cap:
                candidates = registry_center.discover(capabilities=[target_cap])
                candidates_count = len(candidates)

        explanation_parts = []
        if matched_capabilities:
            explanation_parts.append(f"意图文本匹配到能力: {', '.join(matched_capabilities)}")
        else:
            explanation_parts.append("意图文本未匹配到特定能力，将按负载均衡选择")

        if selected_agent:
            explanation_parts.append(f"选择Agent: {selected_agent.agent_id}")
            explanation_parts.append(f"能力匹配分数: {total_score:.2f} (能力权重0.7, 负载权重0.3)")
            explanation_parts.append(f"负载评分: {load_score:.2f} (CPU: {selected_agent.cpu_load}%)")
            explanation_parts.append(f"候选Agent数: {candidates_count}")
        else:
            explanation_parts.append("未找到可用Agent")

        return RoutingDecision(
            selected_agent=selected_agent,
            matched_capabilities=matched_capabilities,
            capability_scores=capability_scores,
            load_score=load_score,
            total_score=total_score,
            explanation="; ".join(explanation_parts),
            candidates_count=candidates_count,
        )


semantic_router = SemanticRouter()
