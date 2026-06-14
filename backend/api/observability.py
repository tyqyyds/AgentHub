from fastapi import APIRouter, Depends, HTTPException, Query
from backend.observability.tracing import get_recent_traces, get_trace_detail
from backend.observability.metrics import get_metrics_collector
from backend.observability.health import get_health_monitor
from backend.core.security.rbac import get_current_user, requires_permission
from backend.api.response import success_response

router = APIRouter()


@router.get("/traces")
async def list_traces(
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user),
):
    traces = get_recent_traces(limit=limit)
    return success_response(data=traces)


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    current_user=Depends(get_current_user),
):
    trace = get_trace_detail(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return success_response(data=trace)


@router.get("/agents/health")
async def get_all_agents_health(current_user=Depends(get_current_user)):
    monitor = get_health_monitor()
    health_data = monitor.get_all_status()
    return success_response(data=health_data)


@router.get("/agents/{agent_id}/health")
async def get_agent_health(
    agent_id: str,
    current_user=Depends(get_current_user),
):
    monitor = get_health_monitor()
    health_data = await monitor.check_agent_health(agent_id)
    return success_response(data=health_data)


@router.get("/metrics/overview")
async def get_system_metrics(current_user=Depends(get_current_user)):
    collector = get_metrics_collector()
    overview = collector.get_system_overview()
    return success_response(data=overview)


@router.get("/metrics/agent/{agent_id}")
async def get_agent_metrics(
    agent_id: str,
    current_user=Depends(get_current_user),
):
    collector = get_metrics_collector()
    metrics = collector.get_agent_health(agent_id)
    return success_response(data=metrics)


@router.post("/health-check")
async def trigger_health_check(current_user=Depends(get_current_user), _: None = Depends(requires_permission("system:manage"))):
    monitor = get_health_monitor()
    results = await monitor.check_all_agents()
    return success_response(data=results)
