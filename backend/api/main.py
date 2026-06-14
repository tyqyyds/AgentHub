from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.security.rate_limiter_middleware import RateLimitMiddleware
from contextlib import asynccontextmanager
from backend.api import intents, events, agents, validation, fuse, locks, commit, mcp_tools, rate_limit, v2, topology, auth, telemetry, cross_domain, knowledge, workflow, compute, map, clarification, observability, failed_intents, llm_router, intent_scheduler, sla_prediction, playbooks, intent_templates, agent_management, grayscale_healing, webhooks, metrics, terraform, audit_logs
from backend.core.config import settings
from backend.core.websocket_manager import manager
import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.database.connection import init_db
    await init_db()
    logger.info("Application startup complete - database initialized")

    from backend.database.seed_data import seed_all
    await seed_all()
    logger.info("Seed data initialized")

    from backend.observability.tracing import setup_tracing, seed_trace_data
    setup_tracing(
        app=app,
        service_name=settings.otel_service_name,
        exporter_endpoint=settings.otel_exporter_endpoint,
        enabled=settings.otel_enabled,
    )
    seed_trace_data()

    from backend.observability.metrics import seed_metrics_data
    seed_metrics_data()

    from backend.observability.health import get_health_monitor
    monitor = get_health_monitor()
    await monitor.start_periodic_check()

    from backend.compute.task_scheduler import task_scheduler
    await task_scheduler.init_db()
    logger.info("Task scheduler database initialized")

    from backend.agents.proactive_notifier import get_proactive_notifier
    notifier = get_proactive_notifier()
    notifier.set_ws_manager(manager)

    from backend.telemetry.sla_evaluator import get_sla_evaluator
    sla_evaluator = get_sla_evaluator()
    await sla_evaluator.start_periodic_evaluation(interval_seconds=60)
    logger.info("SLA periodic evaluation started (60s interval)")

    yield

    await sla_evaluator.stop_periodic_evaluation()
    await task_scheduler.close()
    await monitor.stop()
    logger.info("Application shutdown")


docs_url = "/docs" if settings.environment != "production" else None
redoc_url = "/redoc" if settings.environment != "production" else None
openapi_url = "/openapi.json" if settings.environment != "production" else None

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于大模型多智能体的意图驱动网络自愈与运维系统",
    lifespan=lifespan,
    redirect_slashes=False,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(",") if hasattr(settings, 'cors_origins') else ["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

app.add_middleware(RateLimitMiddleware)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(intents.router, prefix="/api/v1/intents", tags=["intents"])
app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(validation.router, prefix="/api/v1/validation", tags=["validation"])
app.include_router(fuse.router, prefix="/api/v1/system", tags=["system"])
app.include_router(locks.router, prefix="/api/v1/locks", tags=["locks"])
app.include_router(commit.router, prefix="/api/v1/commit", tags=["commit"])
app.include_router(mcp_tools.router, prefix="/api/v1/mcp-tools", tags=["mcp-tools"])
app.include_router(rate_limit.router, prefix="/api/v1/rate-limit", tags=["rate-limit"])
app.include_router(topology.router, prefix="/api/v1/topology", tags=["topology"])
app.include_router(cross_domain.router, prefix="/api/v1/cross-domain", tags=["cross-domain"])
app.include_router(telemetry.router, prefix="/api/v1/telemetry", tags=["telemetry"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(workflow.router, prefix="/api/v1/workflow", tags=["workflow"])
app.include_router(compute.router, prefix="/api/v1/compute", tags=["compute"])
app.include_router(map.router, prefix="/api/v1/map", tags=["map"])
app.include_router(clarification.router, prefix="/api/v1/clarification", tags=["clarification"])
app.include_router(observability.router, prefix="/api/v1/observability", tags=["observability"])
app.include_router(failed_intents.router, prefix="/api/v1/failed-intents", tags=["failed-intents"])
app.include_router(llm_router.router, prefix="/api/v1/llm-router", tags=["llm-router"])
app.include_router(intent_scheduler.router, prefix="/api/v1/scheduler", tags=["scheduler"])
app.include_router(sla_prediction.router, prefix="/api/v1/sla", tags=["sla"])
app.include_router(intent_templates.router, prefix="/api/v1/intent-templates", tags=["intent-templates"])
app.include_router(playbooks.router, prefix="/api/v1/playbooks", tags=["playbooks"])
app.include_router(grayscale_healing.router, prefix="/api/v1/grayscale-healing", tags=["grayscale-healing"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(metrics.router)
app.include_router(agent_management.router, prefix="/api/v1/agent-management", tags=["agent-management"])
app.include_router(terraform.router, prefix="/api/v1/terraform", tags=["terraform"])
app.include_router(audit_logs.router, prefix="/api/v1/audit-logs", tags=["audit-logs"])
app.include_router(v2.router, tags=["v2"])


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": settings.app_name, "version": settings.app_version}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    if not token:
        await websocket.accept()
        await websocket.close(code=4001, reason="Authentication required")
        return

    from backend.core.security.rbac import decode_token
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await websocket.accept()
        await websocket.close(code=4003, reason="Invalid token")
        return

    username = payload.get("sub", "unknown")
    role = payload.get("role", "viewer")

    # Check connection limits before accepting
    async with manager._lock:
        if len(manager.active_connections) >= manager.max_connections:
            await websocket.accept()
            await websocket.close(code=1013, reason="Too many connections")
            return
        user_conn_count = sum(1 for _, u in manager.active_connections if u == username)
        if user_conn_count >= manager.max_per_user:
            await websocket.accept()
            await websocket.close(code=1013, reason="Too many connections for this user")
            return

    await websocket.accept()
    async with manager._lock:
        manager.active_connections.append((websocket, username))
    logger.info(f"WebSocket connected: {username} (total: {len(manager.active_connections)})")

    try:
        await manager.send_personal_message({
            "type": "connection_established",
            "data": {"username": username, "role": role, "active_connections": len(manager.active_connections)}
        }, websocket)
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=60)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                    pong = await asyncio.wait_for(websocket.receive_json(), timeout=10)
                    if pong.get("type") != "pong":
                        break
                except:
                    break
                continue
            if len(json.dumps(data)) > 65536:
                await websocket.send_json({"type": "error", "message": "Message too large"})
                continue
            if not isinstance(data, dict):
                continue
            msg_type = data.get("type", "message")
            if msg_type in ["message", "notification", "status_update", "topology_update",
                            "alert", "intent_update", "device_update",
                            "react_step", "emergency_fuse", "proactive_push",
                            "playbook_step", "grayscale_progress", "sla_alert",
                            "assistant_action", "command_result"]:
                data["sender"] = username
                data["role"] = role
                await manager.broadcast(data)
            elif msg_type == "ping":
                await manager.send_personal_message({"type": "pong", "timestamp": data.get("timestamp")}, websocket)
            elif msg_type == "agent_hello":
                logger.info(f"Agent registration from {username}: {data.get('agent_id', 'unknown')}")
                await manager.send_personal_message({
                    "type": "connection_established",
                    "data": {"agent_id": data.get("agent_id"), "status": "registered"}
                }, websocket)
            elif msg_type == "agent_health":
                logger.debug(f"Agent health report from {username}: {data.get('agent_id', 'unknown')}")
            elif msg_type == "device_info":
                logger.debug(f"Device info from {username}: {data.get('device_id', 'unknown')}")
    except WebSocketDisconnect:
        await manager.disconnect(websocket, username)
    except Exception:
        await manager.disconnect(websocket, username)