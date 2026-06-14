import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

VIOLATION_ACTION_MAP = {
    "bandwidth_mbps": {
        "action_type": "qos_adjustment",
        "tool": "config_qos",
        "description": "QoS bandwidth adjustment required",
        "parameters": {"action": "adjust_bandwidth", "priority": "high"},
    },
    "latency_ms": {
        "action_type": "route_optimization",
        "tool": "optimize_route",
        "description": "Route optimization required to reduce latency",
        "parameters": {"action": "optimize_path", "metric": "latency"},
    },
    "packet_loss_pct": {
        "action_type": "interface_failover",
        "tool": "failover_interface",
        "description": "Interface failover required due to packet loss",
        "parameters": {"action": "switch_backup_link", "failover_mode": "auto"},
    },
    "cpu_usage_pct": {
        "action_type": "load_balancing",
        "tool": "config_load_balance",
        "description": "Load balancing adjustment required due to high CPU",
        "parameters": {"action": "redistribute_load", "threshold": 80},
    },
    "memory_usage_pct": {
        "action_type": "resource_optimization",
        "tool": "optimize_resources",
        "description": "Resource optimization required due to high memory usage",
        "parameters": {"action": "clear_caches", "threshold": 80},
    },
}


class PolicyReconstructor:
    def __init__(self):
        self._reconstruction_history: list[dict] = []

    async def reconstruct_policy(
        self,
        intent_id: int,
        violations: list[dict],
        current_metrics: dict[str, dict],
    ) -> dict:
        if not violations:
            return {
                "adjustment_plan": {},
                "tool_calls": [],
                "reasoning": "No violations detected, no policy reconstruction needed.",
            }

        tool_calls = []
        reasoning_parts = []
        adjustment_plan = {
            "intent_id": intent_id,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "violation_count": len(violations),
            "actions": [],
        }

        seen_actions = set()

        for violation in violations:
            condition = violation.get("condition", {})
            metric = condition.get("metric", "")
            device = condition.get("device", "")
            actual_value = violation.get("actual_value")
            threshold = violation.get("threshold")
            op = condition.get("op", ">=")

            action_def = VIOLATION_ACTION_MAP.get(metric)
            if not action_def:
                reasoning_parts.append(
                    f"Metric '{metric}' on device '{device}': no automated action defined."
                )
                continue

            action_key = f"{action_def['action_type']}:{device}"
            if action_key in seen_actions:
                continue
            seen_actions.add(action_key)

            tool_call = {
                "tool": action_def["tool"],
                "device": device,
                "parameters": {
                    **action_def["parameters"],
                    "device": device,
                    "metric": metric,
                    "current_value": actual_value,
                    "target_value": threshold,
                },
                "reason": action_def["description"],
            }
            tool_calls.append(tool_call)

            adjustment_plan["actions"].append({
                "device": device,
                "metric": metric,
                "action_type": action_def["action_type"],
                "current_value": actual_value,
                "target_value": threshold,
                "operator": op,
            })

            reasoning_parts.append(
                f"Device '{device}' metric '{metric}' current={actual_value}, "
                f"expected {op} {threshold}. "
                f"Action: {action_def['description']}."
            )

        reasoning = " ".join(reasoning_parts) if reasoning_parts else "No actionable violations found."

        result = {
            "adjustment_plan": adjustment_plan,
            "tool_calls": tool_calls,
            "reasoning": reasoning,
        }

        self._reconstruction_history.append({
            "intent_id": intent_id,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return result

    def get_reconstruction_history(self, intent_id: Optional[int] = None) -> list[dict]:
        if intent_id is not None:
            return [h for h in self._reconstruction_history if h["intent_id"] == intent_id]
        return list(self._reconstruction_history)

    async def execute_reconstruction(self, intent_id: int, violations: list, current_metrics: dict) -> dict:
        reconstruction = await self.reconstruct_policy(intent_id, violations, current_metrics)
        tool_calls = reconstruction.get("tool_calls", [])
        execution_results = []
        if tool_calls:
            try:
                from backend.mcp.executor import get_tool_executor
                executor = get_tool_executor()
                for tc in tool_calls:
                    tool_name = tc.get("tool", "")
                    params = tc.get("params", {})
                    try:
                        result = await executor.execute_tool(tool_name, params)
                        execution_results.append({
                            "tool": tool_name,
                            "status": result.get("status", "unknown"),
                            "output": result.get("output", result.get("error", "")),
                        })
                    except Exception as e:
                        execution_results.append({
                            "tool": tool_name,
                            "status": "error",
                            "output": str(e),
                        })
            except Exception as e:
                logger.error(f"Failed to execute reconstruction tools: {e}")
        reconstruction["execution_results"] = execution_results
        return reconstruction


_reconstructor_instance: Optional[PolicyReconstructor] = None


def get_policy_reconstructor() -> PolicyReconstructor:
    global _reconstructor_instance
    if _reconstructor_instance is None:
        _reconstructor_instance = PolicyReconstructor()
    return _reconstructor_instance
