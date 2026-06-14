import asyncio
import random
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

DEVICE_IDS = [
    "core-router-01",
    "core-router-02",
    "edge-switch-01",
    "edge-switch-02",
    "firewall-01",
    "server-01",
]

METRIC_RANGES = {
    "bandwidth_mbps": (100, 10000),
    "latency_ms": (1, 50),
    "packet_loss_pct": (0, 5),
    "cpu_usage_pct": (10, 90),
    "memory_usage_pct": (20, 80),
}

ANOMALY_CHANCE = 0.05

ANOMALY_TYPES = {
    "latency_ms": lambda v: min(v * random.uniform(5, 20), 500),
    "packet_loss_pct": lambda v: min(v + random.uniform(15, 40), 100),
    "cpu_usage_pct": lambda v: min(v + random.uniform(30, 50), 100),
}


class TelemetryCollector:
    def __init__(self):
        self._lock = threading.Lock()
        self._history: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        self._max_history_per_metric = 180
        self._baselines: dict[str, dict[str, float]] = {}
        self._init_baselines()

    def _init_baselines(self):
        for device_id in DEVICE_IDS:
            self._baselines[device_id] = {}
            for metric, (low, high) in METRIC_RANGES.items():
                mid = (low + high) / 2
                self._baselines[device_id][metric] = random.uniform(
                    mid - (high - low) * 0.2, mid + (high - low) * 0.2
                )

    def _generate_metric_value(self, device_id: str, metric: str) -> float:
        baseline = self._baselines[device_id][metric]
        low, high = METRIC_RANGES[metric]
        noise_range = (high - low) * 0.1
        value = baseline + random.uniform(-noise_range, noise_range)
        value = max(low, min(high, value))

        if random.random() < ANOMALY_CHANCE and metric in ANOMALY_TYPES:
            value = ANOMALY_TYPES[metric](value)
            value = max(low, min(high * 3, value))

        if metric in ("bandwidth_mbps",):
            return round(value, 1)
        if metric in ("packet_loss_pct",):
            return round(value, 2)
        return round(value, 2)

    async def collect_device_metrics(self, device_id: str) -> Optional[dict]:
        if device_id not in DEVICE_IDS:
            return None

        metrics = {}
        timestamp = datetime.now(timezone.utc).isoformat()
        for metric in METRIC_RANGES:
            metrics[metric] = self._generate_metric_value(device_id, metric)

        metrics["device_id"] = device_id
        metrics["timestamp"] = timestamp

        with self._lock:
            for metric_name, value in metrics.items():
                if metric_name in METRIC_RANGES:
                    history_list = self._history[device_id][metric_name]
                    history_list.append({"timestamp": timestamp, "value": value})
                    if len(history_list) > self._max_history_per_metric:
                        self._history[device_id][metric_name] = history_list[-self._max_history_per_metric:]

        return metrics

    async def collect_all_devices(self) -> dict[str, dict]:
        results = {}
        tasks = [self.collect_device_metrics(did) for did in DEVICE_IDS]
        responses = await asyncio.gather(*tasks)
        for device_id, metrics in zip(DEVICE_IDS, responses):
            if metrics is not None:
                results[device_id] = metrics
        return results

    async def get_metric_history(
        self, device_id: str, metric_name: str, minutes: int = 30
    ) -> list[dict]:
        if device_id not in DEVICE_IDS:
            return []
        if metric_name not in METRIC_RANGES:
            return []

        with self._lock:
            history = list(self._history[device_id].get(metric_name, []))

        if not history:
            now = datetime.now(timezone.utc)
            for i in range(min(minutes, 30)):
                ts = now - __import__("datetime").timedelta(minutes=minutes - i)
                low, high = METRIC_RANGES[metric_name]
                mid = self._baselines.get(device_id, {}).get(metric_name, (low + high) / 2)
                noise_range = (high - low) * 0.1
                value = round(mid + random.uniform(-noise_range, noise_range), 2)
                value = max(low, min(high, value))
                history.append({"timestamp": ts.isoformat(), "value": value})

        return history


_collector_instance: Optional[TelemetryCollector] = None


def get_telemetry_collector() -> TelemetryCollector:
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = TelemetryCollector()
    return _collector_instance
