import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum as PyEnum

from ..core.config import settings
from ..database.models import AgentHealthStatus

logger = logging.getLogger(__name__)


class ScoreDimension(PyEnum):
    """评分维度"""
    ACCURACY = "accuracy"
    LATENCY = "latency"
    RELIABILITY = "reliability"
    CAPABILITY_BREADTH = "capability_breadth"
    ERROR_RATE = "error_rate"


class EvaluationMethod(PyEnum):
    """评估方法"""
    AUTOMATED = "automated"
    MANUAL = "manual"
    BENCHMARK = "benchmark"
    FEEDBACK_BASED = "feedback_based"


@dataclass
class DimensionScore:
    """维度评分"""
    dimension: ScoreDimension = ScoreDimension.ACCURACY
    score: float = 0.0
    weight: float = 1.0
    sample_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentScoreResult:
    """Agent评分结果"""
    agent_id: str = ""
    overall_score: float = 0.0
    dimension_scores: List[DimensionScore] = field(default_factory=list)
    evaluated_at: str = ""
    evaluation_method: EvaluationMethod = EvaluationMethod.AUTOMATED
    health_status: AgentHealthStatus = AgentHealthStatus.HEALTHY


# ── 维度权重配置 ──
DEFAULT_DIMENSION_WEIGHTS: Dict[ScoreDimension, float] = {
    ScoreDimension.ACCURACY: 0.30,
    ScoreDimension.LATENCY: 0.20,
    ScoreDimension.RELIABILITY: 0.25,
    ScoreDimension.CAPABILITY_BREADTH: 0.10,
    ScoreDimension.ERROR_RATE: 0.15,
}

# ── 评分等级阈值 ──
SCORE_THRESHOLDS = {
    "excellent": 90.0,
    "good": 75.0,
    "acceptable": 60.0,
    "poor": 40.0,
    "critical": 0.0,
}


@dataclass
class AgentScorerConfig:
    """Agent评分器配置"""
    evaluation_interval_seconds: int = 3600
    min_sample_count: int = 10
    score_decay_factor: float = 0.95
    latency_threshold_ms: float = 3000.0
    error_rate_threshold: float = 0.1
    reliability_threshold: float = 0.95
    dimension_weights: Dict[ScoreDimension, float] = field(
        default_factory=lambda: dict(DEFAULT_DIMENSION_WEIGHTS)
    )


class AgentScorer:
    """Agent评分器：基于多维度指标评估Agent能力

    评分维度：
    - accuracy: 输出准确率（基于历史任务结果）
    - latency: 响应延迟（基于平均处理时间）
    - reliability: 可靠性（基于成功率）
    - capability_breadth: 能力广度（基于可处理任务类型数）
    - error_rate: 错误率（基于失败任务占比）
    """

    def __init__(self, config: Optional[AgentScorerConfig] = None):
        self.config = config or AgentScorerConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._score_cache: Dict[str, AgentScoreResult] = {}
        self._metric_history: Dict[str, List[Dict[str, Any]]] = {}

    def _score_accuracy(self, metrics: List[Dict[str, Any]]) -> DimensionScore:
        """计算准确率评分"""
        if not metrics:
            return DimensionScore(
                dimension=ScoreDimension.ACCURACY,
                score=50.0,
                weight=self.config.dimension_weights[ScoreDimension.ACCURACY],
            )

        correct_count = sum(1 for m in metrics if m.get("output_correct", False))
        total = len(metrics)
        accuracy_rate = correct_count / total if total > 0 else 0.0
        score = accuracy_rate * 100.0

        return DimensionScore(
            dimension=ScoreDimension.ACCURACY,
            score=score,
            weight=self.config.dimension_weights[ScoreDimension.ACCURACY],
            sample_count=total,
            details={
                "correct_count": correct_count,
                "total_count": total,
                "accuracy_rate": round(accuracy_rate, 4),
            },
        )

    def _score_latency(self, metrics: List[Dict[str, Any]]) -> DimensionScore:
        """计算延迟评分"""
        if not metrics:
            return DimensionScore(
                dimension=ScoreDimension.LATENCY,
                score=50.0,
                weight=self.config.dimension_weights[ScoreDimension.LATENCY],
            )

        latencies = [m.get("duration_ms", 0) for m in metrics if m.get("duration_ms")]
        if not latencies:
            return DimensionScore(
                dimension=ScoreDimension.LATENCY,
                score=50.0,
                weight=self.config.dimension_weights[ScoreDimension.LATENCY],
            )

        avg_latency = sum(latencies) / len(latencies)
        threshold = self.config.latency_threshold_ms

        if avg_latency <= threshold * 0.3:
            score = 100.0
        elif avg_latency <= threshold:
            score = 100.0 * (1 - (avg_latency - threshold * 0.3) / (threshold * 0.7))
        else:
            score = max(0.0, 30.0 * (1 - (avg_latency - threshold) / threshold))

        return DimensionScore(
            dimension=ScoreDimension.LATENCY,
            score=score,
            weight=self.config.dimension_weights[ScoreDimension.LATENCY],
            sample_count=len(latencies),
            details={
                "avg_latency_ms": round(avg_latency, 2),
                "p99_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.99)], 2)
                if len(latencies) > 1 else round(avg_latency, 2),
                "threshold_ms": threshold,
            },
        )

    def _score_reliability(self, metrics: List[Dict[str, Any]]) -> DimensionScore:
        """计算可靠性评分"""
        if not metrics:
            return DimensionScore(
                dimension=ScoreDimension.RELIABILITY,
                score=50.0,
                weight=self.config.dimension_weights[ScoreDimension.RELIABILITY],
            )

        success_count = sum(1 for m in metrics if m.get("success", True))
        total = len(metrics)
        success_rate = success_count / total if total > 0 else 0.0

        if success_rate >= self.config.reliability_threshold:
            score = 100.0
        else:
            score = success_rate / self.config.reliability_threshold * 100.0

        return DimensionScore(
            dimension=ScoreDimension.RELIABILITY,
            score=score,
            weight=self.config.dimension_weights[ScoreDimension.RELIABILITY],
            sample_count=total,
            details={
                "success_count": success_count,
                "total_count": total,
                "success_rate": round(success_rate, 4),
            },
        )

    def _score_capability_breadth(
        self, metrics: List[Dict[str, Any]], agent_info: Dict[str, Any]
    ) -> DimensionScore:
        """计算能力广度评分"""
        capabilities = agent_info.get("capabilities", [])
        task_types_seen = set()
        for m in metrics:
            task_type = m.get("task_type")
            if task_type:
                task_types_seen.add(task_type)

        cap_count = len(capabilities)
        task_coverage = len(task_types_seen)

        cap_score = min(100.0, cap_count * 10.0)
        coverage_score = min(100.0, task_coverage * 15.0)
        score = cap_score * 0.6 + coverage_score * 0.4

        return DimensionScore(
            dimension=ScoreDimension.CAPABILITY_BREADTH,
            score=score,
            weight=self.config.dimension_weights[ScoreDimension.CAPABILITY_BREADTH],
            sample_count=task_coverage,
            details={
                "declared_capabilities": cap_count,
                "task_types_covered": task_coverage,
                "task_types": list(task_types_seen),
            },
        )

    def _score_error_rate(self, metrics: List[Dict[str, Any]]) -> DimensionScore:
        """计算错误率评分"""
        if not metrics:
            return DimensionScore(
                dimension=ScoreDimension.ERROR_RATE,
                score=50.0,
                weight=self.config.dimension_weights[ScoreDimension.ERROR_RATE],
            )

        error_count = sum(1 for m in metrics if m.get("error"))
        total = len(metrics)
        error_rate = error_count / total if total > 0 else 0.0

        if error_rate <= self.config.error_rate_threshold * 0.1:
            score = 100.0
        elif error_rate <= self.config.error_rate_threshold:
            score = 100.0 * (1 - error_rate / self.config.error_rate_threshold) * 0.7 + 30.0
        else:
            score = max(0.0, 30.0 * (1 - (error_rate - self.config.error_rate_threshold) / 0.5))

        return DimensionScore(
            dimension=ScoreDimension.ERROR_RATE,
            score=score,
            weight=self.config.dimension_weights[ScoreDimension.ERROR_RATE],
            sample_count=total,
            details={
                "error_count": error_count,
                "total_count": total,
                "error_rate": round(error_rate, 4),
            },
        )

    def _determine_health(self, overall_score: float) -> AgentHealthStatus:
        """根据总分判定健康状态"""
        if overall_score >= SCORE_THRESHOLDS["good"]:
            return AgentHealthStatus.HEALTHY
        elif overall_score >= SCORE_THRESHOLDS["acceptable"]:
            return AgentHealthStatus.DEGRADED
        else:
            return AgentHealthStatus.UNHEALTHY

    def _get_score_level(self, score: float) -> str:
        """获取评分等级"""
        for level, threshold in SCORE_THRESHOLDS.items():
            if score >= threshold:
                return level
        return "critical"

    def record_metric(self, agent_id: str, metric: Dict[str, Any]) -> None:
        """记录Agent指标数据"""
        if agent_id not in self._metric_history:
            self._metric_history[agent_id] = []
        self._metric_history[agent_id].append({
            **metric,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })

    def evaluate_agent(
        self, agent_id: str, agent_info: Optional[Dict[str, Any]] = None
    ) -> AgentScoreResult:
        """评估单个Agent"""
        metrics = self._metric_history.get(agent_id, [])
        info = agent_info or {}

        dim_scores = [
            self._score_accuracy(metrics),
            self._score_latency(metrics),
            self._score_reliability(metrics),
            self._score_capability_breadth(metrics, info),
            self._score_error_rate(metrics),
        ]

        total_weight = sum(d.weight for d in dim_scores)
        overall = (
            sum(d.score * d.weight for d in dim_scores) / total_weight
            if total_weight > 0 else 0.0
        )

        health = self._determine_health(overall)
        result = AgentScoreResult(
            agent_id=agent_id,
            overall_score=round(overall, 2),
            dimension_scores=dim_scores,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            evaluation_method=EvaluationMethod.AUTOMATED,
            health_status=health,
        )
        self._score_cache[agent_id] = result
        return result

    def get_score(self, agent_id: str) -> Optional[AgentScoreResult]:
        """获取缓存的评分结果"""
        return self._score_cache.get(agent_id)

    def get_leaderboard(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取评分排行榜"""
        sorted_scores = sorted(
            self._score_cache.values(),
            key=lambda s: s.overall_score,
            reverse=True,
        )
        return [
            {
                "rank": i + 1,
                "agent_id": s.agent_id,
                "overall_score": s.overall_score,
                "level": self._get_score_level(s.overall_score),
                "health_status": s.health_status.value,
            }
            for i, s in enumerate(sorted_scores[:top_n])
        ]

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行Agent评分

        输入:
            agent_id: 单个Agent ID（可选）
            agent_ids: 多个Agent ID列表（可选）
            agent_info: Agent信息字典（可选）
            action: 操作类型 - evaluate/leaderboard/record
            metric: 指标数据（record操作时使用）
        """
        action = input_data.get("action", "evaluate")

        if action == "record":
            agent_id = input_data.get("agent_id", "")
            metric = input_data.get("metric", {})
            if not agent_id or not metric:
                return {"status": "failed", "error": "缺少agent_id或metric"}
            self.record_metric(agent_id, metric)
            return {"status": "success", "agent_id": agent_id, "recorded": True}

        if action == "leaderboard":
            top_n = input_data.get("top_n", 10)
            board = self.get_leaderboard(top_n)
            return {
                "status": "success",
                "leaderboard": board,
                "total_scored_agents": len(self._score_cache),
            }

        # ── evaluate ──
        agent_ids = input_data.get("agent_ids", [])
        single_id = input_data.get("agent_id")
        if single_id:
            agent_ids = [single_id]

        if not agent_ids:
            agent_ids = list(self._metric_history.keys())

        if not agent_ids:
            return {"status": "failed", "error": "无Agent可评估"}

        results = []
        for aid in agent_ids:
            info = input_data.get("agent_info", {}).get(aid, {})
            result = self.evaluate_agent(aid, info)
            results.append({
                "agent_id": result.agent_id,
                "overall_score": result.overall_score,
                "level": self._get_score_level(result.overall_score),
                "health_status": result.health_status.value,
                "dimensions": {
                    d.dimension.value: {
                        "score": round(d.score, 2),
                        "weight": d.weight,
                        "sample_count": d.sample_count,
                    }
                    for d in result.dimension_scores
                },
            })

        return {
            "status": "success",
            "evaluated_count": len(results),
            "results": results,
        }

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "agent": self.__class__.__name__,
            "scored_agents": len(self._score_cache),
            "tracked_agents": len(self._metric_history),
            "total_metric_records": sum(
                len(v) for v in self._metric_history.values()
            ),
            "dimension_weights": {
                d.value: w for d, w in self.config.dimension_weights.items()
            },
        }
