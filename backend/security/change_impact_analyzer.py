from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import async_session_maker
from backend.database.models import ChangeImpactAnalysis
from datetime import datetime, timezone
import uuid
import json
import logging

logger = logging.getLogger(__name__)

HIGH_RISK_OPERATIONS = ["acl", "firewall", "routing", "bgp", "ospf", "interface shutdown", "vlan"]
CRITICAL_DEVICES_KEYWORDS = ["core", "backbone", "gateway", "border"]


class ChangeImpactAnalyzer:

    async def analyze_impact(self, intent_id: int, target_devices: list, proposed_changes: list) -> dict:
        simulation_result = await self.simulate_execution(target_devices, proposed_changes)

        affected_services = self._identify_affected_services(target_devices, proposed_changes)
        risk_factors = self._calculate_risk_factors(target_devices, proposed_changes, simulation_result)
        risk_level = self._determine_risk_level(risk_factors)
        mitigation_suggestions = await self._generate_mitigation_suggestions(
            target_devices, proposed_changes, risk_factors, risk_level
        )

        analysis_id = f"cia_{uuid.uuid4().hex[:8]}"

        async with async_session_maker() as session:
            analysis = ChangeImpactAnalysis(
                analysis_id=analysis_id,
                intent_id=intent_id,
                target_devices=target_devices,
                proposed_changes=proposed_changes,
                simulated_impact=simulation_result,
                affected_services=affected_services,
                risk_level=risk_level,
                risk_factors=risk_factors,
                mitigation_suggestions=mitigation_suggestions,
                analyzed_by="llm",
            )
            session.add(analysis)
            await session.commit()

        return {
            "analysis_id": analysis_id,
            "intent_id": intent_id,
            "target_devices": target_devices,
            "proposed_changes": proposed_changes,
            "simulated_impact": simulation_result,
            "affected_services": affected_services,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "mitigation_suggestions": mitigation_suggestions,
            "analyzed_by": "llm",
        }

    async def simulate_execution(self, target_devices: list, changes: list) -> dict:
        device_impacts = []
        for device in target_devices:
            device_impact = {
                "device": device,
                "status": "simulated",
                "estimated_downtime_seconds": 0,
                "affected_interfaces": [],
                "config_changes_count": len(changes),
            }

            for change in changes:
                change_str = str(change).lower()
                if any(kw in change_str for kw in HIGH_RISK_OPERATIONS):
                    device_impact["estimated_downtime_seconds"] += 30
                if "interface" in change_str:
                    device_impact["affected_interfaces"].append("affected_interface")
                if "shutdown" in change_str:
                    device_impact["estimated_downtime_seconds"] += 120

            is_critical = any(kw in str(device).lower() for kw in CRITICAL_DEVICES_KEYWORDS)
            if is_critical:
                device_impact["estimated_downtime_seconds"] *= 2

            device_impacts.append(device_impact)

        total_downtime = max(d["estimated_downtime_seconds"] for d in device_impacts) if device_impacts else 0

        return {
            "simulation_status": "completed",
            "device_impacts": device_impacts,
            "total_estimated_downtime_seconds": total_downtime,
            "simulation_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _identify_affected_services(self, target_devices: list, changes: list) -> list:
        services = set()
        for change in changes:
            change_str = str(change).lower()
            if "bgp" in change_str:
                services.add("bgp_routing")
            if "ospf" in change_str:
                services.add("ospf_routing")
            if "acl" in change_str or "firewall" in change_str:
                services.add("security_policy")
            if "vlan" in change_str:
                services.add("vlan_service")
            if "qos" in change_str:
                services.add("qos_policy")
            if "interface" in change_str:
                services.add("interface_connectivity")
            if "snmp" in change_str:
                services.add("monitoring")
            if "ntp" in change_str:
                services.add("time_sync")

        for device in target_devices:
            if any(kw in str(device).lower() for kw in CRITICAL_DEVICES_KEYWORDS):
                services.add("core_infrastructure")

        return list(services)

    def _calculate_risk_factors(self, target_devices: list, changes: list, simulation: dict) -> list:
        factors = []

        if len(target_devices) > 5:
            factors.append({"factor": "large_scope", "description": f"Changes affect {len(target_devices)} devices", "severity": "high"})

        for change in changes:
            change_str = str(change).lower()
            for kw in HIGH_RISK_OPERATIONS:
                if kw in change_str:
                    factors.append({"factor": "high_risk_operation", "description": f"High-risk operation: {kw}", "severity": "high"})
                    break

        for device in target_devices:
            if any(kw in str(device).lower() for kw in CRITICAL_DEVICES_KEYWORDS):
                factors.append({"factor": "critical_device", "description": f"Critical device affected: {device}", "severity": "high"})
                break

        total_downtime = simulation.get("total_estimated_downtime_seconds", 0)
        if total_downtime > 120:
            factors.append({"factor": "extended_downtime", "description": f"Estimated downtime: {total_downtime}s", "severity": "critical"})
        elif total_downtime > 30:
            factors.append({"factor": "moderate_downtime", "description": f"Estimated downtime: {total_downtime}s", "severity": "medium"})

        if not factors:
            factors.append({"factor": "low_risk", "description": "No significant risk factors identified", "severity": "low"})

        return factors

    def _determine_risk_level(self, risk_factors: list) -> str:
        severities = [f["severity"] for f in risk_factors]
        if "critical" in severities:
            return "critical"
        if "high" in severities:
            return "high"
        if "medium" in severities:
            return "medium"
        return "low"

    async def _generate_mitigation_suggestions(self, target_devices: list, changes: list, risk_factors: list, risk_level: str) -> list:
        suggestions = []

        if risk_level in ("critical", "high"):
            suggestions.append("Consider applying changes during a maintenance window")
            suggestions.append("Implement changes in a canary/grayscale deployment pattern")

        if any(f["factor"] == "critical_device" for f in risk_factors):
            suggestions.append("Verify backup configurations before applying changes to critical devices")
            suggestions.append("Ensure rollback plan is in place for core infrastructure devices")

        if any(f["factor"] == "extended_downtime" for f in risk_factors):
            suggestions.append("Schedule changes during low-traffic periods")
            suggestions.append("Prepare redundant paths to minimize service disruption")

        if any(f["factor"] == "large_scope" for f in risk_factors):
            suggestions.append("Apply changes in batches rather than all at once")
            suggestions.append("Monitor each batch before proceeding to the next")

        try:
            from backend.agents.llm_gateway import get_llm_gateway, TaskType
            gateway = get_llm_gateway()
            prompt = (
                f"Analyze the following network configuration changes and provide mitigation suggestions.\n"
                f"Target devices: {json.dumps(target_devices)}\n"
                f"Proposed changes: {json.dumps(changes)}\n"
                f"Risk factors: {json.dumps(risk_factors)}\n"
                f"Risk level: {risk_level}\n"
                f"Provide 3-5 specific, actionable mitigation suggestions in JSON array format."
            )
            messages = [{"role": "user", "content": prompt}]
            result = await gateway.chat(messages, task_type=TaskType.FAULT_DIAGNOSE, temperature=0.3, max_tokens=1024)
            content = result.get("content", "")
            try:
                llm_suggestions = json.loads(content)
                if isinstance(llm_suggestions, list):
                    suggestions.extend(llm_suggestions)
            except json.JSONDecodeError:
                if content.strip():
                    suggestions.append(content.strip())
        except Exception as e:
            logger.warning(f"LLM mitigation generation failed: {e}")

        if not suggestions:
            suggestions.append("Review changes manually before applying")

        return suggestions

    async def get_analysis(self, analysis_id: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(ChangeImpactAnalysis).where(ChangeImpactAnalysis.analysis_id == analysis_id)
            )
            analysis = result.scalars().first()
            if not analysis:
                return {"status": "error", "message": f"Analysis {analysis_id} not found"}

            return {
                "analysis_id": analysis.analysis_id,
                "intent_id": analysis.intent_id,
                "target_devices": analysis.target_devices,
                "proposed_changes": analysis.proposed_changes,
                "simulated_impact": analysis.simulated_impact,
                "affected_services": analysis.affected_services,
                "risk_level": analysis.risk_level,
                "risk_factors": analysis.risk_factors,
                "mitigation_suggestions": analysis.mitigation_suggestions,
                "analyzed_by": analysis.analyzed_by,
                "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
            }

    async def list_analyses(self, risk_level: str = None, limit: int = 20) -> list:
        async with async_session_maker() as session:
            query = select(ChangeImpactAnalysis).order_by(desc(ChangeImpactAnalysis.created_at))
            if risk_level:
                query = query.where(ChangeImpactAnalysis.risk_level == risk_level)
            query = query.limit(limit)

            result = await session.execute(query)
            analyses = result.scalars().all()

            return [
                {
                    "analysis_id": a.analysis_id,
                    "intent_id": a.intent_id,
                    "target_devices": a.target_devices,
                    "risk_level": a.risk_level,
                    "affected_services": a.affected_services,
                    "analyzed_by": a.analyzed_by,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in analyses
            ]


_change_impact_analyzer_instance = None


def get_change_impact_analyzer() -> ChangeImpactAnalyzer:
    global _change_impact_analyzer_instance
    if _change_impact_analyzer_instance is None:
        _change_impact_analyzer_instance = ChangeImpactAnalyzer()
    return _change_impact_analyzer_instance
