import asyncio
import json
import logging
from typing import Dict, List, Tuple, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self, max_connections: int = 1000, max_per_user: int = 5):
        self.active_connections: List[Tuple[WebSocket, str]] = []
        self.max_connections = max_connections
        self.max_per_user = max_per_user
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, username: str) -> bool:
        async with self._lock:
            if len(self.active_connections) >= self.max_connections:
                await websocket.close(code=1013, reason="Too many connections")
                return False
            user_conn_count = sum(1 for _, u in self.active_connections if u == username)
            if user_conn_count >= self.max_per_user:
                await websocket.close(code=1013, reason="Too many connections for this user")
                return False
        await websocket.accept()
        async with self._lock:
            self.active_connections.append((websocket, username))
        logger.info(f"WebSocket connected: {username} (total: {len(self.active_connections)})")
        return True

    async def disconnect(self, websocket: WebSocket, username: str = None):
        async with self._lock:
            before = len(self.active_connections)
            self.active_connections = [(ws, u) for ws, u in self.active_connections if ws != websocket]
            if len(self.active_connections) < before:
                logger.info(f"WebSocket disconnected: {username or 'unknown'}, {len(self.active_connections)} active connections")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        async with self._lock:
            connections = list(self.active_connections)
        disconnected = []
        for websocket, username in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append((websocket, username))
        if disconnected:
            async with self._lock:
                for item in disconnected:
                    if item in self.active_connections:
                        self.active_connections.remove(item)

    async def send_to_user(self, username: str, message: dict):
        async with self._lock:
            connections = [(ws, u) for ws, u in self.active_connections if u == username]
        for websocket, user in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                async with self._lock:
                    if (websocket, user) in self.active_connections:
                        self.active_connections.remove((websocket, user))

    async def send_proactive_push(self, username: str, push_type: str, data: dict):
        message = {
            "type": "proactive_push",
            "data": {
                "push_type": push_type,
                **data,
            }
        }
        await self.send_to_user(username, message)

    async def broadcast_proactive_push(self, push_type: str, data: dict):
        message = {
            "type": "proactive_push",
            "data": {
                "push_type": push_type,
                **data,
            }
        }
        await self.broadcast(message)

    def get_connection_count(self) -> int:
        return len(self.active_connections)


manager = ConnectionManager()
