from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.api import intents, events, agents
from backend.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于大模型多智能体的意图驱动网络自愈与运维系统"
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


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": settings.app_name, "version": settings.app_version}


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)