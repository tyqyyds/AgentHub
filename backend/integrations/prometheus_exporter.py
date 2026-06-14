import threading
import time
import logging
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class PrometheusExporter:
    def __init__(self):
        self._start_time = time.time()
        self._lock = threading.Lock()
        self._gauges: dict[str, dict[str, float]] = defaultdict(dict)
        self._counters: dict[str, dict[str, float]] = defaultdict(dict)
        self._histograms: dict[str, dict[str, list[float]]] = defaultdict(dict)
        self._metric_metadata: dict[str, dict] = {
            "agenthub_uptime_seconds": {"type": "gauge", "help": "System uptime in seconds"},
            "agenthub_active_intents_total": {"type": "gauge", "help": "Number of active intents"},
            "agenthub_completed_intents_total": {"type": "counter", "help": "Total completed intents"},
            "agenthub_agent_health_status": {"type": "gauge", "help": "Agent health status (1=healthy, 0=unhealthy)"},
            "agenthub_agent_qps": {"type": "gauge", "help": "Agent queries per second"},
            "agenthub_agent_latency_seconds": {"type": "histogram", "help": "Agent latency in seconds"},
            "agenthub_agent_error_rate": {"type": "gauge", "help": "Agent error rate"},
            "agenthub_sla_achieving_total": {"type": "counter", "help": "Total SLA achieving events"},
            "agenthub_sla_deviating_total": {"type": "counter", "help": "Total SLA deviating events"},
            "agenthub_sla_violation_predicted": {"type": "gauge", "help": "Predicted SLA violation flag"},
            "agenthub_healing_events_total": {"type": "counter", "help": "Total self-healing events"},
            "agenthub_healing_success_total": {"type": "counter", "help": "Total successful healing events"},
            "agenthub_healing_failed_total": {"type": "counter", "help": "Total failed healing events"},
            "agenthub_knowledge_documents_total": {"type": "gauge", "help": "Total knowledge documents"},
            "agenthub_knowledge_queries_total": {"type": "counter", "help": "Total knowledge queries"},
            "agenthub_llm_requests_total": {"type": "counter", "help": "Total LLM requests"},
            "agenthub_llm_tokens_used_total": {"type": "counter", "help": "Total LLM tokens used"},
            "agenthub_llm_latency_seconds": {"type": "histogram", "help": "LLM request latency in seconds"},
            "agenthub_scheduler_queue_size": {"type": "gauge", "help": "Scheduler queue size"},
            "agenthub_scheduler_active_intents": {"type": "gauge", "help": "Active intents in scheduler"},
        }

    def update_metric(self, name: str, labels: dict, value: float) -> None:
        label_key = self._labels_to_key(labels)
        with self._lock:
            if name not in self._metric_metadata:
                self._metric_metadata[name] = {"type": "gauge", "help": f"Custom metric {name}"}
            self._gauges[name][label_key] = value

    def increment_counter(self, name: str, labels: dict, value: float = 1) -> None:
        label_key = self._labels_to_key(labels)
        with self._lock:
            if name not in self._metric_metadata:
                self._metric_metadata[name] = {"type": "counter", "help": f"Custom counter {name}"}
            self._counters[name][label_key] = self._counters[name].get(label_key, 0.0) + value

    def observe_histogram(self, name: str, labels: dict, value: float) -> None:
        label_key = self._labels_to_key(labels)
        with self._lock:
            if name not in self._metric_metadata:
                self._metric_metadata[name] = {"type": "histogram", "help": f"Custom histogram {name}"}
            if label_key not in self._histograms[name]:
                self._histograms[name][label_key] = []
            self._histograms[name][label_key].append(value)

    def generate_metrics(self) -> str:
        with self._lock:
            lines = []
            self._generate_uptime(lines)

            for name, meta in sorted(self._metric_metadata.items()):
                if name == "agenthub_uptime_seconds":
                    continue

                metric_type = meta["type"]
                help_text = meta["help"]

                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} {metric_type}")

                if metric_type == "gauge":
                    for label_key, value in self._gauges.get(name, {}).items():
                        labels = self._key_to_labels(label_key)
                        lines.append(f'{name}{{{self._format_labels(labels)}}} {value}')
                elif metric_type == "counter":
                    for label_key, value in self._counters.get(name, {}).items():
                        labels = self._key_to_labels(label_key)
                        lines.append(f'{name}{{{self._format_labels(labels)}}} {value}')
                elif metric_type == "histogram":
                    buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
                    for label_key, values in self._histograms.get(name, {}).items():
                        labels = self._key_to_labels(label_key)
                        sorted_values = sorted(values)
                        bucket_counts = []
                        for b in buckets:
                            count = sum(1 for v in sorted_values if v <= b)
                            bucket_counts.append(count)
                        for i, b in enumerate(buckets):
                            lines.append(f'{name}_bucket{{le="{b}",{self._format_labels(labels)}}} {bucket_counts[i]}')
                        lines.append(f'{name}_bucket{{le="+Inf",{self._format_labels(labels)}}} {len(sorted_values)}')
                        lines.append(f'{name}_sum{{{self._format_labels(labels)}}} {sum(sorted_values)}')
                        lines.append(f'{name}_count{{{self._format_labels(labels)}}} {len(sorted_values)}')

                if (metric_type == "gauge" and name not in self._gauges) or \
                   (metric_type == "counter" and name not in self._counters) or \
                   (metric_type == "histogram" and name not in self._histograms):
                    if metric_type in ("gauge", "counter"):
                        lines.append(f'{name}{{}} 0')

            return "\n".join(lines) + "\n"

    def _generate_uptime(self, lines: list[str]) -> None:
        uptime = time.time() - self._start_time
        lines.append("# HELP agenthub_uptime_seconds System uptime in seconds")
        lines.append("# TYPE agenthub_uptime_seconds gauge")
        lines.append(f"agenthub_uptime_seconds{{}} {uptime:.2f}")

    @staticmethod
    def _labels_to_key(labels: dict) -> str:
        if not labels:
            return ""
        return "|".join(f"{k}={v}" for k, v in sorted(labels.items()))

    @staticmethod
    def _key_to_labels(key: str) -> dict:
        if not key:
            return {}
        result = {}
        for pair in key.split("|"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                result[k] = v
        return result

    @staticmethod
    def _format_labels(labels: dict) -> str:
        if not labels:
            return ""
        return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))


_prometheus_exporter: Optional[PrometheusExporter] = None


def get_prometheus_exporter() -> PrometheusExporter:
    global _prometheus_exporter
    if _prometheus_exporter is None:
        _prometheus_exporter = PrometheusExporter()
    return _prometheus_exporter
