from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from . import (
    intents, events, agents, auth,
    validation, fuse, locks, commit, mcp_tools, rate_limit,
    topology, cross_domain, telemetry, knowledge, workflow,
    compute, map, clarification, observability, failed_intents,
    llm_router, scheduler, sla, intent_templates, playbooks,
    grayscale_healing, webhooks, metrics, agent_management,
    terraform, audit_logs, v2,
)
from .websocket import websocket_endpoint
from ..core.config import settings
from ..database.connection import engine, async_session_maker
from ..database.models import Base, User, UserRole
from ..core.security.jwt import hash_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: auto-create tables and seed default admin user
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            admin = User(
                username="admin",
                hashed_password=hash_password("admin123"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            session.add(admin)
            await session.commit()

    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于大模型多智能体的意图驱动网络自愈与运维系统",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(intents.router, prefix="/api/v1/intents", tags=["intents"])
app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(validation.router, prefix="/api/v1/validation", tags=["validation"])
app.include_router(fuse.router, prefix="/api/v1/fuse", tags=["fuse"])
app.include_router(locks.router, prefix="/api/v1/locks", tags=["locks"])
app.include_router(commit.router, prefix="/api/v1/commit", tags=["commit"])
app.include_router(mcp_tools.router, prefix="/api/v1/mcp-tools", tags=["mcp_tools"])
app.include_router(rate_limit.router, prefix="/api/v1/rate-limit", tags=["rate_limit"])
app.include_router(topology.router, prefix="/api/v1/topology", tags=["topology"])
app.include_router(cross_domain.router, prefix="/api/v1/cross-domain", tags=["cross_domain"])
app.include_router(telemetry.router, prefix="/api/v1/telemetry", tags=["telemetry"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(workflow.router, prefix="/api/v1/workflow", tags=["workflow"])
app.include_router(compute.router, prefix="/api/v1/compute", tags=["compute"])
app.include_router(map.router, prefix="/api/v1/map", tags=["map"])
app.include_router(clarification.router, prefix="/api/v1/clarification", tags=["clarification"])
app.include_router(observability.router, prefix="/api/v1/observability", tags=["observability"])
app.include_router(failed_intents.router, prefix="/api/v1/failed-intents", tags=["failed_intents"])
app.include_router(llm_router.router, prefix="/api/v1/llm-router", tags=["llm_router"])
app.include_router(scheduler.router, prefix="/api/v1/scheduler", tags=["scheduler"])
app.include_router(sla.router, prefix="/api/v1/sla", tags=["sla"])
app.include_router(intent_templates.router, prefix="/api/v1/intent-templates", tags=["intent_templates"])
app.include_router(playbooks.router, prefix="/api/v1/playbooks", tags=["playbooks"])
app.include_router(grayscale_healing.router, prefix="/api/v1/grayscale-healing", tags=["grayscale_healing"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["metrics"])
app.include_router(agent_management.router, prefix="/api/v1/agent-management", tags=["agent_management"])
app.include_router(terraform.router, prefix="/api/v1/terraform", tags=["terraform"])
app.include_router(audit_logs.router, prefix="/api/v1/audit-logs", tags=["audit_logs"])
app.include_router(v2.router, prefix="/api/v2", tags=["v2"])


@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "service": settings.app_name, "version": settings.app_version}


app.websocket("/ws")(websocket_endpoint)