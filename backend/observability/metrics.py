import threading
import time
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class _SlidingWindow:
    def __init__(self, window_seconds: int = 300, max_entries: int = 10000):
        self._window_seconds = window_seconds
        self._max_entries = max_entries
        self._entries: list[tuple[float, float]] = []
        self._lock = threading.Lock()

    def add(self, value: float):
        now = time.time()
        with self._lock:
            self._entries.append((now, value))
            self._cleanup(now)

    def _cleanup(self, now: float):
        cutoff = now - self._window_seconds
        self._entries = [(t, v) for t, v in self._entries if t > cutoff]
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

    def get_values(self) -> list[float]:
        now = time.time()
        with self._lock:
            self._cleanup(now)
            return [v for _, v in self._entries]

    def count(self) -> int:
        now = time.time()
        with self._lock:
            self._cleanup(now)
            return len(self._entries)


class AgentMetricsCollector:
    def __init__(self, window_seconds: int = 300):
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._durations: dict[str, _SlidingWindow] = defaultdict(lambda: _SlidingWindow(window_seconds))
        self._errors: dict[str, _SlidingWindow] = defaultdict(lambda: _SlidingWindow(window_seconds))
        self._calls: dict[str, _SlidingWindow] = defaultdict(lambda: _SlidingWindow(window_seconds))
        self._reasoning_rounds: dict[str, _SlidingWindow] = defaultdict(lambda: _SlidingWindow(window_seconds))

    def record_call(self, agent_id: str, duration_ms: float, success: bool, reasoning_rounds: Optional[int] = None):
        now = time.time()
        self._durations[agent_id].add(duration_ms)
        self._calls[agent_id].add(1)
        if not success:
            self._errors[agent_id].add(1)
        if reasoning_rounds is not None:
            self._reasoning_rounds[agent_id].add(reasoning_rounds)

    @staticmethod
    def _percentile(sorted_values: list[float], p: float) -> float:
        if not sorted_values:
            return 0.0
        idx = int(len(sorted_values) * p / 100.0)
        idx = min(idx, len(sorted_values) - 1)
        return sorted_values[idx]

    def _calc_qps(self, agent_id: str) -> float:
        call_count = self._calls[agent_id].count()
        window = self._window_seconds
        if window == 0:
            return 0.0
        return round(call_count / window, 2)

    def _calc_error_rate(self, agent_id: str) -> float:
        total = self._calls[agent_id].count()
        if total == 0:
            return 0.0
        error_count = self._errors[agent_id].count()
        return round(error_count / total * 100, 2)

    def get_agent_health(self, agent_id: str) -> dict:
        durations = sorted(self._durations[agent_id].get_values())
        reasoning_values = self._reasoning_rounds[agent_id].get_values()

        return {
            "agent_id": agent_id,
            "qps": self._calc_qps(agent_id),
            "latency_p50": self._percentile(durations, 50),
            "latency_p95": self._percentile(durations, 95),
            "latency_p99": self._percentile(durations, 99),
            "error_rate": self._calc_error_rate(agent_id),
            "total_calls": self._calls[agent_id].count(),
            "reasoning_rounds_avg": round(sum(reasoning_values) / len(reasoning_values), 2) if reasoning_values else None,
            "window_seconds": self._window_seconds,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def get_all_agents_health(self) -> dict[str, dict]:
        all_agent_ids = set()
        all_agent_ids.update(self._durations.keys())
        all_agent_ids.update(self._calls.keys())
        return {aid: self.get_agent_health(aid) for aid in all_agent_ids}

    def get_system_overview(self) -> dict:
        all_agent_ids = set()
        all_agent_ids.update(self._durations.keys())
        all_agent_ids.update(self._calls.keys())

        total_calls = sum(self._calls[aid].count() for aid in all_agent_ids)
        total_errors = sum(self._errors[aid].count() for aid in all_agent_ids)

        all_durations = []
        for aid in all_agent_ids:
            all_durations.extend(self._durations[aid].get_values())
        all_durations.sort()

        total_qps = sum(self._calc_qps(aid) for aid in all_agent_ids)

        return {
            "total_agents": len(all_agent_ids),
            "total_calls": total_calls,
            "total_errors": total_errors,
            "system_error_rate": round(total_errors / total_calls * 100, 2) if total_calls > 0 else 0.0,
            "system_qps": round(total_qps, 2),
            "system_latency_p50": self._percentile(all_durations, 50),
            "system_latency_p95": self._percentile(all_durations, 95),
            "system_latency_p99": self._percentile(all_durations, 99),
            "window_seconds": self._window_seconds,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }


_metrics_collector: Optional[AgentMetricsCollector] = None


def get_metrics_collector() -> AgentMetricsCollector:
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = AgentMetricsCollector()
    return _metrics_collector


def seed_metrics_data():
    """为可观测性模块填充演示指标数据"""
    collector = get_metrics_collector()
    if collector._durations or collector._calls:
        return

    import random as _random
    _random.seed(42)

    agent_configs = {
        "agent_bandwidth_guarantor": {"base_latency": 1200, "error_rate": 0.05, "qps_scale": 2.0},
        "agent_fault_diagnostician": {"base_latency": 3500, "error_rate": 0.08, "qps_scale": 1.5},
        "agent_config_generator": {"base_latency": 2800, "error_rate": 0.11, "qps_scale": 1.0},
        "agent_security_scanner": {"base_latency": 800, "error_rate": 0.03, "qps_scale": 3.0},
        "agent_healing_executor": {"base_latency": 4500, "error_rate": 0.15, "qps_scale": 0.8},
        "agent_topology_analyzer": {"base_latency": 1800, "error_rate": 0.07, "qps_scale": 2.0},
        "agent_sla_predictor": {"base_latency": 2200, "error_rate": 0.12, "qps_scale": 1.2},
        "agent_intent_parser": {"base_latency": 1500, "error_rate": 0.09, "qps_scale": 4.0},
    }

    for agent_id, config in agent_configs.items():
        num_calls = int(50 * config["qps_scale"])
        for _ in range(num_calls):
            duration = config["base_latency"] + _random.gauss(0, config["base_latency"] * 0.3)
            duration = max(50, duration)
            success = _random.random() > config["error_rate"]
            collector.record_call(agent_id, duration, success)

    logger.info(f"Seeded metrics data for {len(agent_configs)} agents")
