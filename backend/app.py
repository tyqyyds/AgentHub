"""
FastAPI 后端服务 - 支持 WebSocket 实时通信

用于 Streamlit 前端与 LangGraph 工作流之间的异步数据传输
"""

import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Dict, Any, Optional

app = FastAPI(title="调度工作流 WebSocket 服务")

# 存储活动的 WebSocket 连接
active_connections: set[WebSocket] = set()


class WorkflowEvent(BaseModel):
    """工作流事件模型"""
    node_name: str
    output: Dict[str, Any]
    status: str


@app.websocket("/ws/workflow")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点 - 用于实时接收工作流事件"""
    await websocket.accept()
    active_connections.add(websocket)
    
    try:
        while True:
            # 保持连接活跃
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        active_connections.remove(websocket)


async def broadcast_workflow_event(event: WorkflowEvent):
    """向所有连接的客户端广播工作流事件"""
    for connection in active_connections:
        try:
            await connection.send_json(event.dict())
        except Exception:
            # 移除无效连接
            active_connections.discard(connection)


@app.post("/api/workflow/event")
async def send_workflow_event(event: WorkflowEvent):
    """HTTP 端点 - 发送工作流事件到 WebSocket"""
    await broadcast_workflow_event(event)
    return {"status": "success", "message": "Event broadcasted"}


@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {"status": "running", "active_connections": len(active_connections)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)