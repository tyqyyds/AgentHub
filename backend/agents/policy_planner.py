import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..core.config import settings
from ..database.models import RiskLevel, ExecutionStatus

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """执行步骤"""
    step_id: int
    name: str
    agent: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"
    estimated_duration_seconds: int = 60
    requires_approval: bool = False
    rollback_action: Optional[str] = None
    dependencies: List[int] = field(default_factory=list)


@dataclass
class PolicyPlannerConfig:
    """策略规划配置"""
    max_steps: int = 20
    default_risk_tolerance: str = "medium"
    enable_auto_approval_low_risk: bool = True
    change_window_check: bool = True


class PolicyPlannerAgent:
    """策略规划Agent：根据意图生成执行策略、步骤编排、风险评估"""

    def __init__(self, config: Optional[PolicyPlannerConfig] = None):
        self.config = config or PolicyPlannerConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._step_templates = self._init_step_templates()

    def _init_step_templates(self) -> Dict[str, List[Dict[str, Any]]]:
        """初始化步骤模板"""
        return {
            "bandwidth_guarantee": [
                {"name": "验证目标设备可达性", "agent": "execution_agent", "action": "ping_check", "risk_level": "low"},
                {"name": "备份当前QoS配置", "agent": "execution_agent", "action": "backup_config", "risk_level": "low"},
                {"name": "创建流量分类", "agent": "config_generator", "action": "create_class_map", "risk_level": "medium"},
                {"name": "创建QoS策略", "agent": "config_generator", "action": "create_policy_map", "risk_level": "medium"},
                {"name": "应用QoS策略到接口", "agent": "execution_agent", "action": "apply_policy", "risk_level": "high", "requires_approval": True},
                {"name": "验证QoS策略生效", "agent": "validator", "action": "verify_qos", "risk_level": "low"},
            ],
            "access_control": [
                {"name": "验证目标设备可达性", "agent": "execution_agent", "action": "ping_check", "risk_level": "low"},
                {"name": "备份当前ACL配置", "agent": "execution_agent", "action": "backup_config", "risk_level": "low"},
                {"name": "创建ACL规则", "agent": "config_generator", "action": "create_acl", "risk_level": "medium"},
                {"name": "应用ACL到接口", "agent": "execution_agent", "action": "apply_acl", "risk_level": "high", "requires_approval": True},
                {"name": "验证ACL规则生效", "agent": "validator", "action": "verify_acl", "risk_level": "low"},
            ],
            "route_optimization": [
                {"name": "验证目标设备可达性", "agent": "execution_agent", "action": "ping_check", "risk_level": "low"},
                {"name": "备份当前路由表", "agent": "execution_agent", "action": "backup_config", "risk_level": "low"},
                {"name": "添加静态路由", "agent": "config_generator", "action": "add_static_route", "risk_level": "high", "requires_approval": True},
                {"name": "验证路由可达性", "agent": "validator", "action": "verify_route", "risk_level": "medium"},
            ],
            "default": [
                {"name": "验证目标设备可达性", "agent": "execution_agent", "action": "ping_check", "risk_level": "low"},
                {"name": "备份当前配置", "agent": "execution_agent", "action": "backup_config", "risk_level": "low"},
                {"name": "生成配置命令", "agent": "config_generator", "action": "generate_config", "risk_level": "medium"},
                {"name": "执行配置变更", "agent": "execution_agent", "action": "apply_config", "risk_level": "high", "requires_approval": True},
                {"name": "验证配置生效", "agent": "validator", "action": "verify_config", "risk_level": "low"},
            ],
        }

    def _match_template(self, intent_name: str) -> str:
        """匹配意图到步骤模板"""
        name_lower = intent_name.lower()
        if "bandwidth" in name_lower or "qos" in name_lower:
            return "bandwidth_guarantee"
        elif "access" in name_lower or "acl" in name_lower:
            return "access_control"
        elif "route" in name_lower:
            return "route_optimization"
        return "default"

    def _assess_risk(self, steps: List[PlanStep], intent: Dict[str, Any]) -> Dict[str, Any]:
        """评估执行风险"""
        high_risk_count = sum(1 for s in steps if s.risk_level == "high")
        medium_risk_count = sum(1 for s in steps if s.risk_level == "medium")

        if high_risk_count >= 2:
            overall_risk = RiskLevel.VERY_HIGH
        elif high_risk_count >= 1:
            overall_risk = RiskLevel.HIGH
        elif medium_risk_count >= 2:
            overall_risk = RiskLevel.MEDIUM
        else:
            overall_risk = RiskLevel.LOW

        targets = intent.get("targets", [])
        impact_score = min(1.0, len(targets) * 0.2 + high_risk_count * 0.3)

        return {
            "overall_risk": overall_risk.value,
            "impact_score": round(impact_score, 2),
            "high_risk_steps": high_risk_count,
            "medium_risk_steps": medium_risk_count,
            "affected_targets": len(targets),
            "recommendation": self._risk_recommendation(overall_risk),
        }

    def _risk_recommendation(self, risk_level: RiskLevel) -> str:
        """根据风险等级给出建议"""
        recommendations = {
            RiskLevel.LOW: "低风险，可自动执行",
            RiskLevel.MEDIUM: "中等风险，建议审批后执行",
            RiskLevel.HIGH: "高风险，必须审批，建议在变更窗口内执行",
            RiskLevel.VERY_HIGH: "极高风险，需多级审批，建议分步执行并实时监控",
        }
        return recommendations.get(risk_level, "建议审批后执行")

    def _check_change_window(self) -> Dict[str, Any]:
        """检查是否在变更窗口内"""
        now = datetime.now(timezone.utc)
        current_hour = now.hour
        start = int(settings.change_window_start.split(":")[0])
        end = int(settings.change_window_end.split(":")[0])

        in_window = start <= current_hour < end
        return {
            "in_change_window": in_window,
            "current_time": now.isoformat(),
            "window_start": settings.change_window_start,
            "window_end": settings.change_window_end,
        }

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成执行策略"""
        intent = input_data.get("intent", input_data)
        intent_name = intent.get("intent_name", "unknown")

        template_name = self._match_template(intent_name)
        template_steps = self._step_templates.get(template_name, self._step_templates["default"])

        steps = []
        for idx, tmpl in enumerate(template_steps[:self.config.max_steps]):
            step = PlanStep(
                step_id=idx,
                name=tmpl["name"],
                agent=tmpl["agent"],
                action=tmpl["action"],
                params=intent.get("actions", [{}])[0].get("params", {}) if intent.get("actions") else {},
                risk_level=tmpl.get("risk_level", "low"),
                requires_approval=tmpl.get("requires_approval", False),
                rollback_action=tmpl.get("rollback_action"),
                dependencies=[idx - 1] if idx > 0 else [],
            )
            steps.append(step)

        risk_assessment = self._assess_risk(steps, intent)

        change_window = {}
        if self.config.change_window_check:
            change_window = self._check_change_window()

        requires_approval = (
            risk_assessment["overall_risk"] in ("高", "极高")
            or any(s.requires_approval for s in steps)
            or not change_window.get("in_change_window", True)
        )

        if self.config.enable_auto_approval_low_risk and risk_assessment["overall_risk"] == "低":
            requires_approval = False

        plan = {
            "intent_name": intent_name,
            "template_used": template_name,
            "steps": [
                {
                    "step_id": s.step_id,
                    "name": s.name,
                    "agent": s.agent,
                    "action": s.action,
                    "risk_level": s.risk_level,
                    "requires_approval": s.requires_approval,
                    "dependencies": s.dependencies,
                }
                for s in steps
            ],
            "risk_assessment": risk_assessment,
            "change_window": change_window,
            "requires_approval": requires_approval,
            "estimated_total_duration": sum(s.estimated_duration_seconds for s in steps),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self.logger.info(f"策略规划完成: {intent_name}, 风险={risk_assessment['overall_risk']}, 步骤={len(steps)}")
        return plan

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "agent": self.__class__.__name__,
            "available_templates": list(self._step_templates.keys()),
        }
