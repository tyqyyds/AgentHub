from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import async_session_maker
from backend.database.models import AgentCapabilityScore
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

EXECUTION_TIME_BASELINE_MS = 5000.0


class AgentCapabilityScorer:

    async def score_agent(self, agent_id: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentCapabilityScore).where(AgentCapabilityScore.agent_id == agent_id)
            )
            score = result.scalars().first()
            if not score:
                return {"agent_id": agent_id, "overall_score": 0.0, "message": "No score data available"}

            success_rate_score = score.success_rate
            efficiency_score = max(0.0, 1.0 - (score.avg_execution_time_ms / EXECUTION_TIME_BASELINE_MS))
            resource_score = score.resource_efficiency

            overall_score = (success_rate_score * 0.4) + (efficiency_score * 0.3) + (resource_score * 0.3)
            overall_score = round(min(1.0, max(0.0, overall_score)), 4)

            return {
                "agent_id": agent_id,
                "overall_score": overall_score,
                "components": {
                    "success_rate": round(success_rate_score, 4),
                    "efficiency": round(efficiency_score, 4),
                    "resource_efficiency": round(resource_score, 4),
                },
                "weights": {"success_rate": 0.4, "efficiency": 0.3, "resource_efficiency": 0.3},
                "performance_trend": score.performance_trend,
                "total_tasks": score.total_tasks,
                "successful_tasks": score.successful_tasks,
                "failed_tasks": score.failed_tasks,
                "capability_tags": score.capability_tags,
                "last_scored_at": score.last_scored_at.isoformat() if score.last_scored_at else None,
                "score_version": score.score_version,
            }

    async def update_agent_score(self, agent_id: str, task_success: bool, execution_time_ms: float, resource_usage: float = None) -> None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentCapabilityScore).where(AgentCapabilityScore.agent_id == agent_id)
            )
            score = result.scalars().first()

            if not score:
                score = AgentCapabilityScore(agent_id=agent_id)
                session.add(score)
                await session.flush()

            score.total_tasks += 1
            if task_success:
                score.successful_tasks += 1
            else:
                score.failed_tasks += 1

            score.success_rate = score.successful_tasks / score.total_tasks if score.total_tasks > 0 else 0.0

            total_exec_time = score.avg_execution_time_ms * (score.total_tasks - 1) + execution_time_ms
            score.avg_execution_time_ms = total_exec_time / score.total_tasks

            if resource_usage is not None:
                if resource_usage > 0:
                    score.resource_efficiency = min(1.0, score.successful_tasks / (resource_usage * score.total_tasks)) if score.total_tasks > 0 else 0.0
                else:
                    score.resource_efficiency = 1.0 if task_success else 0.0

            score.performance_trend = await self._compute_trend(session, agent_id, score)
            score.last_scored_at = datetime.now(timezone.utc)
            score.score_version += 1

            await session.commit()

    async def _compute_trend(self, session: AsyncSession, agent_id: str, score: AgentCapabilityScore) -> str:
        if score.total_tasks < 10:
            return "stable"

        recent_success_rate = score.success_rate
        if recent_success_rate >= 0.9:
            return "improving"
        elif recent_success_rate <= 0.5:
            return "declining"
        return "stable"

    async def get_agent_score(self, agent_id: str) -> dict:
        return await self.score_agent(agent_id)

    async def get_top_agents(self, capability_tag: str = None, limit: int = 10) -> list:
        async with async_session_maker() as session:
            query = select(AgentCapabilityScore).order_by(desc(AgentCapabilityScore.success_rate))
            if capability_tag:
                query = query.where(AgentCapabilityScore.capability_tags.contains([capability_tag]))
            query = query.limit(limit)

            result = await session.execute(query)
            scores = result.scalars().all()

            top_agents = []
            for s in scores:
                score_data = await self.score_agent(s.agent_id)
                top_agents.append(score_data)
            return top_agents

    async def get_agent_recommendations(self, task_type: str) -> list:
        async with async_session_maker() as session:
            query = (
                select(AgentCapabilityScore)
                .where(AgentCapabilityScore.capability_tags.contains([task_type]))
                .order_by(desc(AgentCapabilityScore.success_rate))
            )
            result = await session.execute(query)
            agents = result.scalars().all()

            recommendations = []
            for a in agents:
                score_data = await self.score_agent(a.agent_id)
                score_data["match_reason"] = f"Capability tag '{task_type}' matched"
                recommendations.append(score_data)
            return recommendations

    async def recalculate_all_scores(self) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(select(AgentCapabilityScore))
            scores = result.scalars().all()

            recalculated = 0
            for score in scores:
                score.performance_trend = await self._compute_trend(session, score.agent_id, score)
                score.last_scored_at = datetime.now(timezone.utc)
                score.score_version += 1
                recalculated += 1

            await session.commit()
            return {"recalculated": recalculated, "status": "success"}

    async def detect_performance_trend(self, agent_id: str) -> str:
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentCapabilityScore).where(AgentCapabilityScore.agent_id == agent_id)
            )
            score = result.scalars().first()
            if not score:
                return "stable"
            return score.performance_trend


_agent_scorer_instance = None


def get_agent_scorer() -> AgentCapabilityScorer:
    global _agent_scorer_instance
    if _agent_scorer_instance is None:
        _agent_scorer_instance = AgentCapabilityScorer()
    return _agent_scorer_instance
