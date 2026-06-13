import logging
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ConflictRule:
    """冲突检测规则"""
    rule_id: str
    conflict_type: str  # intent / resource / policy / temporal / dependency
    pattern: str
    severity: str = "medium"
    description: str = ""


@dataclass
class ConflictDetectorConfig:
    """冲突检测配置"""
    check_intent_conflict: bool = True
    check_resource_conflict: bool = True
    check_policy_conflict: bool = True
    check_temporal_conflict: bool = True
    check_dependency_conflict: bool = True
    max_conflict_depth: int = 5


class ConflictDetectorAgent:
    """冲突检测Agent：意图冲突识别、资源冲突检测、策略冲突分析"""

    def __init__(self, config: Optional[ConflictDetectorConfig] = None):
        self.config = config or ConflictDetectorConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._active_intents: List[Dict[str, Any]] = []
        self._resource_locks: Dict[str, Dict[str, Any]] = {}
        self._policy_rules: List[ConflictRule] = self._init_default_rules()

    def _init_default_rules(self) -> List[ConflictRule]:
        """初始化默认冲突检测规则"""
        return [
            ConflictRule(
                rule_id="CR001",
                conflict_type="intent",
                pattern=r"bandwidth.*(?:guarantee|limit).*bandwidth.*(?:guarantee|limit)",
                severity="high",
                description="同一目标上存在多个带宽策略冲突",
            ),
            ConflictRule(
                rule_id="CR002",
                conflict_type="intent",
                pattern=r"permit.*deny|deny.*permit",
                severity="high",
                description="ACL规则存在允许/拒绝冲突",
            ),
            ConflictRule(
                rule_id="CR003",
                conflict_type="resource",
                pattern=r"interface.*(?:shutdown|no shutdown)",
                severity="medium",
                description="接口状态操作冲突",
            ),
            ConflictRule(
                rule_id="CR004",
                conflict_type="policy",
                pattern=r"route.*(?:add|delete).*route.*(?:add|delete)",
                severity="medium",
                description="路由策略操作冲突",
            ),
            ConflictRule(
                rule_id="CR005",
                conflict_type="intent",
                pattern=r"qos.*priority.*qos.*priority",
                severity="high",
                description="QoS优先级策略冲突",
            ),
            ConflictRule(
                rule_id="CR006",
                conflict_type="temporal",
                pattern=r"maintenance.*window|scheduled.*change",
                severity="high",
                description="变更操作与维护窗口时间冲突",
            ),
            ConflictRule(
                rule_id="CR007",
                conflict_type="dependency",
                pattern=r"upstream.*downstream|depends.*on",
                severity="medium",
                description="意图依赖链存在循环或缺失依赖",
            ),
        ]

    def register_active_intent(self, intent: Dict[str, Any]) -> None:
        """注册活跃意图"""
        self._active_intents.append({
            **intent,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        })

    def remove_active_intent(self, intent_name: str) -> None:
        """移除活跃意图"""
        self._active_intents = [
            i for i in self._active_intents
            if i.get("intent_name") != intent_name
        ]

    def _check_intent_conflict(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检测意图冲突"""
        conflicts = []
        intent_name = intent.get("intent_name", "")
        targets = intent.get("targets", [])
        actions = intent.get("actions", [])

        for active in self._active_intents:
            active_targets = active.get("targets", [])
            active_actions = active.get("actions", [])

            target_overlap = set(map(str, targets)) & set(map(str, active_targets))
            if not target_overlap:
                continue

            for new_action in actions:
                for active_action in active_actions:
                    if new_action.get("type") == active_action.get("type"):
                        new_params = new_action.get("params", {})
                        active_params = active_action.get("params", {})

                        if new_action.get("type") == "qos":
                            new_bw = new_params.get("min_bw") or new_params.get("max_bw")
                            active_bw = active_params.get("min_bw") or active_params.get("max_bw")
                            if new_bw and active_bw and new_bw != active_bw:
                                conflicts.append({
                                    "type": "intent",
                                    "severity": "high",
                                    "description": f"目标 {target_overlap} 上带宽策略冲突: "
                                                  f"新请求={new_bw}, 已存在={active_bw}",
                                    "conflicting_intent": active.get("intent_name"),
                                    "rule_id": "CR001",
                                })

                        if new_action.get("type") == "acl":
                            new_effect = new_params.get("effect", "permit")
                            active_effect = active_params.get("effect", "permit")
                            if new_effect != active_effect:
                                conflicts.append({
                                    "type": "intent",
                                    "severity": "high",
                                    "description": f"目标 {target_overlap} 上ACL规则冲突: "
                                                  f"新请求={new_effect}, 已存在={active_effect}",
                                    "conflicting_intent": active.get("intent_name"),
                                    "rule_id": "CR002",
                                })

        return conflicts

    def _check_resource_conflict(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检测资源冲突"""
        conflicts = []
        targets = intent.get("targets", [])

        for target in targets:
            target_str = str(target)
            if target_str in self._resource_locks:
                lock_info = self._resource_locks[target_str]
                conflicts.append({
                    "type": "resource",
                    "severity": "medium",
                    "description": f"资源 {target_str} 正在被 {lock_info.get('locked_by', 'unknown')} 锁定",
                    "target": target_str,
                    "lock_info": lock_info,
                    "rule_id": "CR003",
                })

        return conflicts

    def _check_policy_conflict(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检测策略冲突"""
        conflicts = []
        actions = intent.get("actions", [])

        for rule in self._policy_rules:
            if rule.conflict_type != "policy":
                continue

            action_text = " ".join(
                f"{a.get('type')} {a.get('params')}" for a in actions
            )

            if re.search(rule.pattern, action_text, re.IGNORECASE):
                conflicts.append({
                    "type": "policy",
                    "severity": rule.severity,
                    "description": rule.description,
                    "rule_id": rule.rule_id,
                })

        return conflicts

    def _check_temporal_conflict(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检测时序冲突：变更操作与维护窗口或已有调度冲突"""
        conflicts = []
        actions = intent.get("actions", [])
        scheduled_time = intent.get("scheduled_time")
        targets = intent.get("targets", [])

        # 检查是否在维护窗口内
        for rule in self._policy_rules:
            if rule.conflict_type != "temporal":
                continue
            action_text = " ".join(
                f"{a.get('type')} {a.get('params')}" for a in actions
            )
            if scheduled_time and re.search(rule.pattern, action_text, re.IGNORECASE):
                conflicts.append({
                    "type": "temporal",
                    "severity": rule.severity,
                    "description": rule.description,
                    "scheduled_time": scheduled_time,
                    "targets": [str(t) for t in targets],
                    "rule_id": rule.rule_id,
                })

        # 检查活跃意图的时间重叠
        if scheduled_time:
            for active in self._active_intents:
                active_time = active.get("scheduled_time")
                active_targets = set(map(str, active.get("targets", [])))
                current_targets = set(map(str, targets))
                if active_time and active_targets & current_targets:
                    conflicts.append({
                        "type": "temporal",
                        "severity": "medium",
                        "description": f"目标 {active_targets & current_targets} 在 {active_time} 已有调度",
                        "conflicting_intent": active.get("intent_name"),
                        "rule_id": "CR006",
                    })

        return conflicts

    def _check_dependency_conflict(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检测依赖冲突：意图依赖链循环或缺失上游依赖"""
        conflicts = []
        dependencies = intent.get("dependencies", [])
        intent_name = intent.get("intent_name", "")

        # 检查循环依赖
        if dependencies:
            dep_names = set(d if isinstance(d, str) else d.get("name", "") for d in dependencies)
            active_names = {a.get("intent_name", "") for a in self._active_intents}
            if intent_name in dep_names:
                conflicts.append({
                    "type": "dependency",
                    "severity": "high",
                    "description": f"意图 {intent_name} 存在自依赖循环",
                    "rule_id": "CR007",
                })
            # 检查上游意图是否已完成
            for dep in dependencies:
                dep_name = dep if isinstance(dep, str) else dep.get("name", "")
                if dep_name and dep_name not in active_names:
                    # 上游意图不在活跃列表中，可能已完成或不存在
                    pass  # 非阻塞，仅记录

        # 检查策略规则匹配
        actions = intent.get("actions", [])
        for rule in self._policy_rules:
            if rule.conflict_type != "dependency":
                continue
            action_text = " ".join(
                f"{a.get('type')} {a.get('params')}" for a in actions
            )
            if re.search(rule.pattern, action_text, re.IGNORECASE):
                conflicts.append({
                    "type": "dependency",
                    "severity": rule.severity,
                    "description": rule.description,
                    "rule_id": rule.rule_id,
                })

        return conflicts

    def lock_resource(self, target: str, locked_by: str, ttl_seconds: int = 300) -> None:
        """锁定资源"""
        self._resource_locks[target] = {
            "locked_by": locked_by,
            "locked_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": ttl_seconds,
        }
        self.logger.info(f"资源已锁定: {target}, 锁定者: {locked_by}")

    def unlock_resource(self, target: str) -> None:
        """解锁资源"""
        self._resource_locks.pop(target, None)
        self.logger.info(f"资源已解锁: {target}")

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行冲突检测"""
        intent = input_data.get("intent", input_data)
        all_conflicts = []

        if self.config.check_intent_conflict:
            intent_conflicts = self._check_intent_conflict(intent)
            all_conflicts.extend(intent_conflicts)

        if self.config.check_resource_conflict:
            resource_conflicts = self._check_resource_conflict(intent)
            all_conflicts.extend(resource_conflicts)

        if self.config.check_policy_conflict:
            policy_conflicts = self._check_policy_conflict(intent)
            all_conflicts.extend(policy_conflicts)

        if self.config.check_temporal_conflict:
            temporal_conflicts = self._check_temporal_conflict(intent)
            all_conflicts.extend(temporal_conflicts)

        if self.config.check_dependency_conflict:
            dependency_conflicts = self._check_dependency_conflict(intent)
            all_conflicts.extend(dependency_conflicts)

        high_severity = [c for c in all_conflicts if c.get("severity") == "high"]
        has_blocking = len(high_severity) > 0

        result = {
            "has_conflict": len(all_conflicts) > 0,
            "is_blocking": has_blocking,
            "total_conflicts": len(all_conflicts),
            "high_severity_count": len(high_severity),
            "conflicts": all_conflicts,
            "recommendation": "需要人工审批" if has_blocking else "可自动执行",
        }

        self.logger.info(
            f"冲突检测完成: 发现{len(all_conflicts)}个冲突, "
            f"其中高危{len(high_severity)}个"
        )

        return result

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "agent": self.__class__.__name__,
            "active_intents": len(self._active_intents),
            "resource_locks": len(self._resource_locks),
            "policy_rules": len(self._policy_rules),
        }
