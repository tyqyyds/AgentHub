from typing import Dict, Any, Optional, List
from backend.agents.base import IntentContext, NetworkState


class ConflictDetectorAgent:
    def __init__(self):
        self.conflict_rules = [
            self._detect_bandwidth_conflict,
            self._detect_acl_conflict,
            self._detect_qos_conflict,
            self._detect_device_conflict,
            self._detect_cross_intent_conflict
        ]
        self._pending_intents: List[Dict[str, Any]] = []

    def register_pending_intent(self, intent: Dict[str, Any]):
        self._pending_intents.append(intent)
        if len(self._pending_intents) > 100:
            self._pending_intents = self._pending_intents[-100:]

    def clear_pending_intents(self):
        self._pending_intents = []

    def detect(self, intent_context: IntentContext, network_state: NetworkState) -> Dict[str, Any]:
        conflicts = []

        for rule in self.conflict_rules:
            result = rule(intent_context, network_state)
            if result.get("conflict"):
                conflicts.append(result)

        return {
            "conflict": len(conflicts) > 0,
            "conflicts": conflicts,
            "details": "\n".join([c["message"] for c in conflicts]) if conflicts else None,
            "suggestions": self._generate_suggestions(conflicts)
        }

    def _detect_bandwidth_conflict(self, intent: IntentContext, network: NetworkState) -> Dict[str, Any]:
        if intent.parsed_intent.get("intent_type") != "bandwidth_guarantee":
            return {"conflict": False}

        target_subnet = intent.parsed_intent.get("target_subnet")
        requested_bw = intent.parsed_intent.get("bandwidth", 0)

        for policy in network.qos_policies:
            if policy.get("subnet") == target_subnet:
                existing_bw = policy.get("bandwidth", 0)

                if existing_bw > 0 and requested_bw > existing_bw:
                    return {
                        "conflict": True,
                        "type": "bandwidth_overcommit",
                        "message": f"目标子网 '{target_subnet}' 已有带宽保障 {existing_bw}M，当前请求 {requested_bw}M，可能存在带宽超额"
                    }

                if policy.get("action") == "limit" and intent.parsed_intent.get("priority") == "high":
                    return {
                        "conflict": True,
                        "type": "policy_conflict",
                        "message": f"目标子网 '{target_subnet}' 存在限流策略，与高优先级带宽保障冲突"
                    }

        return {"conflict": False}

    def _detect_acl_conflict(self, intent: IntentContext, network: NetworkState) -> Dict[str, Any]:
        if intent.parsed_intent.get("intent_name") != "access_control":
            return {"conflict": False}

        new_action = intent.parsed_intent.get("action", "permit")
        new_source = intent.parsed_intent.get("source", "any")
        new_destination = intent.parsed_intent.get("destination", "any")
        new_protocol = intent.parsed_intent.get("protocol", "ip")
        target_device = intent.parsed_intent.get("device", "")

        acl_policies = [p for p in network.qos_policies if p.get("policy_type") == "acl"]

        for policy in acl_policies:
            if policy.get("device", "") != target_device:
                continue

            existing_action = policy.get("action", "permit")
            existing_source = policy.get("source", "any")
            existing_destination = policy.get("destination", "any")
            existing_protocol = policy.get("protocol", "ip")

            if self._addresses_overlap(new_source, existing_source) and \
               self._addresses_overlap(new_destination, existing_destination) and \
               (new_protocol == existing_protocol or new_protocol == "ip" or existing_protocol == "ip"):
                if new_action != existing_action:
                    return {
                        "conflict": True,
                        "type": "acl_action_conflict",
                        "message": f"设备 '{target_device}' 上存在冲突的ACL规则：已有 {existing_action} {existing_protocol} {existing_source}->{existing_destination}，新请求 {new_action} {new_protocol} {new_source}->{new_destination}"
                    }

                if existing_action == "deny" and new_action == "deny":
                    return {
                        "conflict": True,
                        "type": "acl_redundant",
                        "message": f"设备 '{target_device}' 上存在重复的ACL拒绝规则：{existing_protocol} {existing_source}->{existing_destination}"
                    }

        if new_action == "deny" and new_source == "any" and new_destination == "any":
            return {
                "conflict": True,
                "type": "acl_overly_broad",
                "message": f"设备 '{target_device}' 上的ACL拒绝规则过于宽泛（any->any），可能阻断所有流量"
            }

        return {"conflict": False}

    def _detect_qos_conflict(self, intent: IntentContext, network: NetworkState) -> Dict[str, Any]:
        intent_type = intent.parsed_intent.get("intent_name")

        if intent_type not in ["bandwidth_guarantee", "qos_policy", "traffic_shaping"]:
            return {"conflict": False}

        target_subnet = intent.parsed_intent.get("target_subnet")
        new_priority = intent.parsed_intent.get("priority", "medium")

        priorities = {"high": 3, "medium": 2, "low": 1}

        for policy in network.qos_policies:
            if policy.get("subnet") == target_subnet:
                existing_priority = policy.get("priority", "medium")

                if priorities.get(new_priority, 2) > priorities.get(existing_priority, 2):
                    return {
                        "conflict": True,
                        "type": "priority_increase",
                        "message": f"目标子网 '{target_subnet}' 将从 {existing_priority} 优先级升级为 {new_priority}，可能影响其他业务"
                    }

            if policy.get("subnet") and target_subnet and self._subnets_overlap(policy.get("subnet", ""), target_subnet):
                if policy.get("action") == "limit" and intent.parsed_intent.get("priority") == "high":
                    return {
                        "conflict": True,
                        "type": "cross_subnet_qos_conflict",
                        "message": f"重叠子网 '{policy.get('subnet')}' 与 '{target_subnet}' 存在QoS策略冲突：限流 vs 高优先级保障"
                    }

        return {"conflict": False}

    def _detect_device_conflict(self, intent: IntentContext, network: NetworkState) -> Dict[str, Any]:
        target_devices = set(intent.target_devices)
        if not target_devices:
            target_devices = {intent.parsed_intent.get("device", "")} if intent.parsed_intent.get("device") else set()

        if not target_devices:
            return {"conflict": False}

        for device_name in target_devices:
            device_info = None
            for device in network.devices:
                if device.name == device_name:
                    device_info = device
                    break

            if device_info and device_info.status == "critical":
                return {
                    "conflict": True,
                    "type": "device_critical",
                    "message": f"设备 '{device_name}' 当前状态为 critical，不建议执行配置变更"
                }

        for pending in self._pending_intents:
            pending_id = pending.get("intent_id", "")
            if pending_id == intent.intent_id:
                continue

            pending_devices = set(pending.get("target_devices", []))
            if not pending_devices:
                pd = pending.get("parsed_intent", {}).get("device", "")
                if pd:
                    pending_devices = {pd}

            overlap = target_devices & pending_devices
            if overlap:
                return {
                    "conflict": True,
                    "type": "concurrent_device_access",
                    "message": f"设备 {overlap} 正在被意图 '{pending_id}' 操作，同时配置可能导致不可预期结果"
                }

        return {"conflict": False}

    def _detect_cross_intent_conflict(self, intent: IntentContext, network: NetworkState) -> Dict[str, Any]:
        intent_type = intent.parsed_intent.get("intent_type")
        target_subnet = intent.parsed_intent.get("target_subnet")

        if not intent_type or not target_subnet:
            return {"conflict": False}

        for pending in self._pending_intents:
            pending_id = pending.get("intent_id", "")
            if pending_id == intent.intent_id:
                continue

            pending_type = pending.get("parsed_intent", {}).get("intent_name", "")
            pending_subnet = pending.get("parsed_intent", {}).get("target_subnet", "")

            if not pending_subnet or not self._subnets_overlap(target_subnet, pending_subnet):
                continue

            conflicting_pairs = {
                ("bandwidth_guarantee", "traffic_shaping"),
                ("traffic_shaping", "bandwidth_guarantee"),
                ("access_control", "bandwidth_guarantee"),
                ("bandwidth_guarantee", "access_control"),
            }

            if (intent_type, pending_type) in conflicting_pairs:
                return {
                    "conflict": True,
                    "type": "cross_intent_conflict",
                    "message": f"意图 '{pending_id}'（{pending_type}）与当前意图（{intent_type}）在子网 '{target_subnet}' 上存在策略冲突"
                }

        return {"conflict": False}

    def _addresses_overlap(self, addr1: str, addr2: str) -> bool:
        if addr1 == "any" or addr2 == "any":
            return True
        if addr1 == addr2:
            return True
        if "/" in addr1 and "/" in addr2:
            return self._subnets_overlap(addr1, addr2)
        return False

    def _subnets_overlap(self, subnet1: str, subnet2: str) -> bool:
        if subnet1 == subnet2:
            return True
        if "any" in (subnet1, subnet2):
            return True
        try:
            import ipaddress
            net1 = ipaddress.ip_network(subnet1, strict=False)
            net2 = ipaddress.ip_network(subnet2, strict=False)
            return net1.overlaps(net2)
        except Exception:
            return subnet1 == subnet2

    def _generate_suggestions(self, conflicts: List[Dict[str, Any]]) -> List[str]:
        suggestions = []

        for conflict in conflicts:
            ctype = conflict.get("type", "")
            if ctype == "bandwidth_overcommit":
                suggestions.append("建议：检查链路实际带宽容量，考虑是否需要扩容")
                suggestions.append("建议：调整保障带宽值，避免超额承诺")
            elif ctype == "policy_conflict":
                suggestions.append("建议：先取消或调整现有限流策略")
                suggestions.append("建议：评估两种策略的优先级关系")
            elif ctype == "priority_increase":
                suggestions.append("建议：通知相关业务方优先级变更")
                suggestions.append("建议：评估高优先级策略的影响范围")
            elif ctype == "acl_action_conflict":
                suggestions.append("建议：检查现有ACL规则，确认是否需要替换或合并")
                suggestions.append("建议：使用更精确的源/目标地址避免冲突")
            elif ctype == "acl_redundant":
                suggestions.append("建议：移除重复的ACL拒绝规则")
            elif ctype == "acl_overly_broad":
                suggestions.append("建议：缩小ACL拒绝规则的地址范围，避免全局阻断")
            elif ctype == "device_critical":
                suggestions.append("建议：等待设备恢复正常后再执行配置变更")
                suggestions.append("建议：联系运维人员检查设备状态")
            elif ctype == "concurrent_device_access":
                suggestions.append("建议：等待其他意图完成后再操作同一设备")
                suggestions.append("建议：将多个意图合并为一个批量操作")
            elif ctype == "cross_subnet_qos_conflict":
                suggestions.append("建议：检查重叠子网的QoS策略一致性")
            elif ctype == "cross_intent_conflict":
                suggestions.append("建议：按顺序执行冲突意图，避免并行操作")
                suggestions.append("建议：调整意图的目标范围，消除重叠")

        return suggestions
