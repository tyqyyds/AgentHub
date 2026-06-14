import functools
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_otel_available = False
_tracer_provider = None
_tracer = None

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
    _otel_available = True
except ImportError:
    pass

if _otel_available:
    _StatusCode = trace.StatusCode
else:
    class _StatusCode:
        OK = "OK"
        ERROR = "ERROR"

_span_store: dict[str, dict] = {}
_span_store_max = 1000


def setup_tracing(app=None, service_name: str = "agenthub", exporter_endpoint: str = "http://localhost:4317", enabled: bool = False):
    global _tracer_provider, _tracer

    if not enabled:
        logger.info("OpenTelemetry tracing is disabled")
        return

    if not _otel_available:
        logger.warning("OpenTelemetry packages not installed, tracing disabled")
        return

    try:
        resource = Resource.create({"service.name": service_name})
        _tracer_provider = TracerProvider(
            resource=resource,
            sampler=ParentBasedTraceIdRatio(rate=1.0),
        )

        exporter = OTLPSpanExporter(endpoint=exporter_endpoint, insecure=True)
        _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(_tracer_provider)
        _tracer = trace.get_tracer(service_name)

        if app is not None:
            FastAPIInstrumentor.instrument_app(app)

        logger.info(f"OpenTelemetry tracing initialized, exporter: {exporter_endpoint}")
    except Exception as e:
        logger.warning(f"Failed to initialize OpenTelemetry tracing: {e}")
        _tracer = None


def get_tracer():
    if _otel_available and _tracer is not None:
        return _tracer
    return None


def _store_span(span_data: dict):
    if len(_span_store) >= _span_store_max:
        oldest_key = next(iter(_span_store))
        del _span_store[oldest_key]
    _span_store[span_data["span_id"]] = span_data


def trace_agent_call(agent_id: str, operation: str = "call", attributes: Optional[dict] = None):
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            span_id = str(uuid.uuid4())
            trace_id = str(uuid.uuid4())
            parent_span_id = kwargs.pop("_parent_span_id", None)

            span_data = {
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "agent_id": agent_id,
                "operation": operation,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "end_time": None,
                "duration_ms": None,
                "status": "ok",
                "attributes": attributes or {},
            }

            tracer = get_tracer()
            otel_span = None

            if tracer:
                try:
                    otel_span = tracer.start_span(
                        f"agent.{agent_id}.{operation}",
                        attributes={
                            "agent.id": agent_id,
                            "operation": operation,
                            **(attributes or {}),
                        },
                    )
                except Exception:
                    otel_span = None

            start = datetime.now(timezone.utc)
            try:
                result = await func(*args, **kwargs)
                span_data["status"] = "ok"
                if otel_span:
                    otel_span.set_status(_StatusCode.OK)
                return result
            except Exception as e:
                span_data["status"] = "error"
                span_data["attributes"]["error.message"] = str(e)
                if otel_span:
                    otel_span.set_status(_StatusCode.ERROR, str(e))
                    otel_span.record_exception(e)
                raise
            finally:
                end = datetime.now(timezone.utc)
                duration = (end - start).total_seconds() * 1000
                span_data["end_time"] = end.isoformat()
                span_data["duration_ms"] = round(duration)
                if otel_span:
                    try:
                        otel_span.end()
                    except Exception:
                        pass
                _store_span(span_data)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            span_id = str(uuid.uuid4())
            trace_id = str(uuid.uuid4())
            parent_span_id = kwargs.pop("_parent_span_id", None)

            span_data = {
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "agent_id": agent_id,
                "operation": operation,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "end_time": None,
                "duration_ms": None,
                "status": "ok",
                "attributes": attributes or {},
            }

            start = datetime.now(timezone.utc)
            try:
                result = func(*args, **kwargs)
                span_data["status"] = "ok"
                return result
            except Exception as e:
                span_data["status"] = "error"
                span_data["attributes"]["error.message"] = str(e)
                raise
            finally:
                end = datetime.now(timezone.utc)
                duration = (end - start).total_seconds() * 1000
                span_data["end_time"] = end.isoformat()
                span_data["duration_ms"] = round(duration)
                _store_span(span_data)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def trace_intent_pipeline(intent_name: str, attributes: Optional[dict] = None):
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            span_id = str(uuid.uuid4())
            trace_id = str(uuid.uuid4())

            span_data = {
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": None,
                "agent_id": "intent_pipeline",
                "operation": f"intent.{intent_name}",
                "start_time": datetime.now(timezone.utc).isoformat(),
                "end_time": None,
                "duration_ms": None,
                "status": "ok",
                "attributes": attributes or {},
            }

            tracer = get_tracer()
            otel_span = None

            if tracer:
                try:
                    otel_span = tracer.start_span(
                        f"intent.pipeline.{intent_name}",
                        attributes={
                            "intent.name": intent_name,
                            **(attributes or {}),
                        },
                    )
                except Exception:
                    otel_span = None

            start = datetime.now(timezone.utc)
            try:
                result = await func(*args, **kwargs)
                span_data["status"] = "ok"
                if otel_span:
                    otel_span.set_status(_StatusCode.OK)
                return result
            except Exception as e:
                span_data["status"] = "error"
                span_data["attributes"]["error.message"] = str(e)
                if otel_span:
                    otel_span.set_status(_StatusCode.ERROR, str(e))
                    otel_span.record_exception(e)
                raise
            finally:
                end = datetime.now(timezone.utc)
                duration = (end - start).total_seconds() * 1000
                span_data["end_time"] = end.isoformat()
                span_data["duration_ms"] = round(duration)
                if otel_span:
                    try:
                        otel_span.end()
                    except Exception:
                        pass
                _store_span(span_data)

        return async_wrapper

    return decorator


def get_recent_traces(limit: int = 50) -> list[dict]:
    traces = {}
    for span in _span_store.values():
        tid = span["trace_id"]
        if tid not in traces:
            traces[tid] = {"trace_id": tid, "spans": [], "start_time": None, "duration_ms": 0, "status": "ok"}
        traces[tid]["spans"].append(span)
        if span["start_time"] and (traces[tid]["start_time"] is None or span["start_time"] < traces[tid]["start_time"]):
            traces[tid]["start_time"] = span["start_time"]
        if span["duration_ms"] and span["duration_ms"] > traces[tid]["duration_ms"]:
            traces[tid]["duration_ms"] = span["duration_ms"]
        if span["status"] == "error":
            traces[tid]["status"] = "error"

    result = sorted(traces.values(), key=lambda x: x["start_time"] or "", reverse=True)
    return result[:limit]


def get_trace_detail(trace_id: str) -> Optional[dict]:
    spans = [s for s in _span_store.values() if s["trace_id"] == trace_id]
    if not spans:
        return None

    trace_info = {
        "trace_id": trace_id,
        "spans": sorted(spans, key=lambda x: x["start_time"] or ""),
        "start_time": min(s["start_time"] for s in spans if s["start_time"]),
        "duration_ms": max(s["duration_ms"] for s in spans if s["duration_ms"] is not None) if any(s["duration_ms"] is not None for s in spans) else 0,
        "status": "error" if any(s["status"] == "error" for s in spans) else "ok",
        "span_count": len(spans),
    }
    return trace_info


def seed_trace_data():
    """为可观测性模块填充演示链路追踪数据"""
    if len(_span_store) > 0:
        return

    import random as _random
    _random.seed(42)

    agent_ids = [
        "agent_bandwidth_guarantor", "agent_fault_diagnostician",
        "agent_config_generator", "agent_security_scanner",
        "agent_healing_executor", "agent_topology_analyzer",
        "agent_sla_predictor", "agent_intent_parser",
    ]
    operations = [
        "intent.parse", "intent.execute", "intent.approve",
        "healing.diagnose", "healing.execute", "healing.rollback",
        "config.generate", "config.deploy",
        "topology.discover", "topology.analyze",
        "security.scan", "security.enforce",
        "sla.predict", "sla.evaluate",
    ]

    now = datetime.now(timezone.utc)
    for i in range(30):
        trace_id = f"trace_{_random.randint(100000, 999999)}"
        num_spans = _random.randint(2, 5)
        base_time = now - timedelta(minutes=_random.randint(1, 120))

        for j in range(num_spans):
            span_id = f"span_{_random.randint(1000000, 9999999)}"
            parent_span_id = f"span_{_random.randint(1000000, 9999999)}" if j > 0 else None
            agent_id = _random.choice(agent_ids)
            operation = _random.choice(operations)
            duration = _random.randint(50, 5000)
            is_error = _random.random() < 0.1

            span_data = {
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "agent_id": agent_id,
                "operation": operation,
                "start_time": (base_time + timedelta(seconds=j * 2)).isoformat(),
                "end_time": (base_time + timedelta(seconds=j * 2, milliseconds=duration)).isoformat(),
                "duration_ms": duration,
                "status": "error" if is_error else "ok",
                "attributes": {"iteration": j, "task_type": operation.split(".")[0]},
            }
            _store_span(span_data)

    logger.info(f"Seeded {len(_span_store)} trace spans for observability")
