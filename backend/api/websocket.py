"""
智维 AgentHub WebSocket 服务模块

提供完整的 WebSocket 功能：
- JWT 认证（连接时验证 token）
- 15 种消息类型枚举
- 连接数限制（全局 + 每用户）
- 心跳机制（PING/PONG）
- 自动重连支持
- 消息广播与定向发送
- 用户连接管理
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect, Query, status

from ..core.config import settings
from ..core.security.jwt import decode_token

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 消息类型枚举
# ---------------------------------------------------------------------------

class MessageType(str, Enum):
    """WebSocket 消息类型枚举（共 15 种，与 README 规范对齐）"""
    CONNECTION_ESTABLISHED = "connection_established"
    MESSAGE = "message"
    NOTIFICATION = "notification"
    STATUS_UPDATE = "status_update"
    TOPOLOGY_UPDATE = "topology_update"
    DEVICE_UPDATE = "device_update"
    ALERT = "alert"
    INTENT_UPDATE = "intent_update"
    ASSISTANT_ACTION = "assistant_action"
    PROACTIVE_NOTIFICATION = "proactive_notification"
    PLAYBOOK_STEP = "playbook_step"
    GRAYSCALE_PROGRESS = "grayscale_progress"
    SLA_ALERT = "sla_alert"
    EMERGENCY_FUSE = "emergency_fuse"
    PING_PONG = "ping_pong"


# ---------------------------------------------------------------------------
# 消息数据类
# ---------------------------------------------------------------------------

@dataclass
class WebSocketMessage:
    """标准 WebSocket 消息格式"""
    type: str
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# ---------------------------------------------------------------------------
# 连接信息数据类
# ---------------------------------------------------------------------------

@dataclass
class ConnectionInfo:
    """单个 WebSocket 连接的元信息"""
    websocket: WebSocket = field(repr=False)
    user_id: str = ""
    role: str = ""
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# 增强型连接管理器
# ---------------------------------------------------------------------------

class EnhancedConnectionManager:
    """
    增强型 WebSocket 连接管理器

    功能：
    - 全局 / 每用户连接数限制
    - 用户 → 连接映射
    - 消息广播 / 定向发送
    - 心跳管理
    - 用户上线 / 下线事件
    """

    def __init__(self):
        # user_id → list[ConnectionInfo]
        self._user_connections: dict[str, list[ConnectionInfo]] = {}
        # 全局活跃连接列表
        self._all_connections: list[ConnectionInfo] = []
        # 心跳任务
        self._heartbeat_tasks: dict[str, asyncio.Task] = {}
        # 运行标志
        self._running = False

    # ---- 连接数统计 ----

    @property
    def total_connections(self) -> int:
        return len(self._all_connections)

    def user_connection_count(self, user_id: str) -> int:
        return len(self._user_connections.get(user_id, []))

    # ---- 连接 / 断开 ----

    async def connect(self, websocket: WebSocket, user_id: str, role: str = "") -> bool:
        """
        接受 WebSocket 连接并注册到管理器。

        Returns:
            True 表示连接成功，False 表示被拒绝（超限等）
        """
        # 全局连接数限制
        max_global = getattr(settings, "ws_max_connections", 1000)
        if self.total_connections >= max_global:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="全局连接数已达上限")
            logger.warning("WebSocket 连接被拒绝：全局连接数已达上限 (%d)", max_global)
            return False

        # 每用户连接数限制
        max_per_user = getattr(settings, "ws_max_connections_per_user", 5)
        if self.user_connection_count(user_id) >= max_per_user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="用户连接数已达上限")
            logger.warning("WebSocket 连接被拒绝：用户 %s 连接数已达上限 (%d)", user_id, max_per_user)
            return False

        # 接受连接
        await websocket.accept()

        conn_info = ConnectionInfo(
            websocket=websocket,
            user_id=user_id,
            role=role,
        )
        self._all_connections.append(conn_info)
        self._user_connections.setdefault(user_id, []).append(conn_info)

        logger.info("WebSocket 连接建立：user=%s, role=%s, 全局连接数=%d", user_id, role, self.total_connections)

        # 广播用户上线事件
        await self.broadcast(WebSocketMessage(
            type=MessageType.STATUS_UPDATE,
            data={"user_id": user_id, "status": "online", "role": role},
        ))

        return True

    async def disconnect(self, websocket: WebSocket, send_reconnect: bool = False):
        """断开连接并清理资源"""
        conn_info = self._find_connection(websocket)
        if conn_info is None:
            return

        user_id = conn_info.user_id

        # 可选：在断开前发送 RECONNECT 消息
        if send_reconnect:
            try:
                await websocket.send_json(WebSocketMessage(
                    type=MessageType.ALERT,
                    data={"action": "RECONNECT", "reason": "服务器即将断开连接，请重连"},
                ).to_dict())
            except Exception:
                pass

        # 从列表中移除
        self._all_connections.remove(conn_info)
        user_conns = self._user_connections.get(user_id, [])
        if conn_info in user_conns:
            user_conns.remove(conn_info)
        if not user_conns:
            self._user_connections.pop(user_id, None)

        # 取消心跳任务
        conn_key = str(id(websocket))
        task = self._heartbeat_tasks.pop(conn_key, None)
        if task and not task.done():
            task.cancel()

        # 广播用户下线事件（仅当该用户无剩余连接时）
        if user_id not in self._user_connections:
            await self.broadcast(WebSocketMessage(
                type=MessageType.STATUS_UPDATE,
            data={"user_id": user_id, "status": "offline"},
            ))

        logger.info("WebSocket 连接断开：user=%s, 全局连接数=%d", user_id, self.total_connections)

    # ---- 消息发送 ----

    async def send_to_connection(self, message: WebSocketMessage, websocket: WebSocket):
        """向单个连接发送消息"""
        try:
            await websocket.send_json(message.to_dict())
        except Exception:
            logger.warning("发送消息失败，连接可能已断开")

    async def send_to_user(self, message: WebSocketMessage, user_id: str):
        """向特定用户的所有连接发送消息"""
        conns = self._user_connections.get(user_id, [])
        for conn in conns:
            await self.send_to_connection(message, conn.websocket)

    async def send_to_role(self, message: WebSocketMessage, role: str):
        """向特定角色的所有连接发送消息"""
        for conn in self._all_connections:
            if conn.role == role:
                await self.send_to_connection(message, conn.websocket)

    async def broadcast(self, message: WebSocketMessage):
        """广播消息给所有连接"""
        dead_conns: list[ConnectionInfo] = []
        for conn in self._all_connections:
            try:
                await conn.websocket.send_json(message.to_dict())
            except Exception:
                dead_conns.append(conn)
        # 清理已断开的连接
        for conn in dead_conns:
            self._all_connections.remove(conn)
            user_conns = self._user_connections.get(conn.user_id, [])
            if conn in user_conns:
                user_conns.remove(conn)

    # ---- 心跳机制 ----

    async def start_heartbeat(self, websocket: WebSocket):
        """为指定连接启动心跳任务"""
        interval = getattr(settings, "ws_heartbeat_interval", 30)
        timeout = getattr(settings, "ws_heartbeat_timeout", 10)
        conn_key = str(id(websocket))

        async def _heartbeat_loop():
            try:
                while True:
                    await asyncio.sleep(interval)
                    conn_info = self._find_connection(websocket)
                    if conn_info is None:
                        break

                    # 发送 PING
                    try:
                        await websocket.send_json(WebSocketMessage(
                            type=MessageType.PING_PONG,
                            data={"action": "PING"},
                        ).to_dict())
                    except Exception:
                        break

                    # 等待 PONG
                    conn_info.last_heartbeat = time.time()
                    await asyncio.sleep(timeout)

                    # 超时检查：如果 last_heartbeat 没有被更新，则断开
                    if conn_info.last_heartbeat < time.time() - timeout - 1:
                        logger.info("心跳超时，断开连接：user=%s", conn_info.user_id)
                        await self.disconnect(websocket, send_reconnect=True)
                        try:
                            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="心跳超时")
                        except Exception:
                            pass
                        break
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error("心跳任务异常: %s", e)

        task = asyncio.create_task(_heartbeat_loop())
        self._heartbeat_tasks[conn_key] = task

    def update_heartbeat(self, websocket: WebSocket):
        """收到 PONG 时更新心跳时间戳"""
        conn_info = self._find_connection(websocket)
        if conn_info:
            conn_info.last_heartbeat = time.time()

    # ---- 内部工具 ----

    def _find_connection(self, websocket: WebSocket) -> Optional[ConnectionInfo]:
        """根据 WebSocket 对象查找连接信息"""
        for conn in self._all_connections:
            if conn.websocket is websocket:
                return conn
        return None


# ---------------------------------------------------------------------------
# 全局管理器实例
# ---------------------------------------------------------------------------

manager = EnhancedConnectionManager()


# ---------------------------------------------------------------------------
# JWT 认证辅助
# ---------------------------------------------------------------------------

async def authenticate_websocket(token: str) -> Optional[dict]:
    """
    验证 WebSocket 连接的 JWT token。

    Returns:
        解码后的 payload dict，验证失败返回 None
    """
    payload = decode_token(token)
    if payload is None:
        return None

    # 检查 token 类型
    if payload.get("type") != "access":
        return None

    # 检查是否过期（decode_token 内部已通过 exp 校验，这里做双重保障）
    exp = payload.get("exp")
    if exp and time.time() > exp:
        return None

    return payload


# ---------------------------------------------------------------------------
# WebSocket 端点
# ---------------------------------------------------------------------------

async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    """
    WebSocket 主端点

    连接方式：ws://host/ws?token=<jwt_access_token>
    """
    # 1. JWT 认证
    payload = await authenticate_websocket(token)
    if payload is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="认证失败：无效或过期的 token")
        return

    user_id = str(payload.get("sub", ""))
    role = str(payload.get("role", ""))
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="认证失败：token 中缺少用户标识")
        return

    # 2. 注册连接
    connected = await manager.connect(websocket, user_id=user_id, role=role)
    if not connected:
        return

    # 3. 启动心跳
    await manager.start_heartbeat(websocket)

    # 4. 消息循环
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_to_connection(
                    WebSocketMessage(type=MessageType.ALERT, data={"error": "无效的 JSON 格式"}),
                    websocket,
                )
                continue

            msg_type = data.get("type", "")

            # 处理 PONG 心跳回复
            if msg_type == MessageType.PING_PONG and data.get("data", {}).get("action") == "PONG":
                manager.update_heartbeat(websocket)
                continue

            # 处理 MESSAGE：广播给所有连接
            if msg_type == MessageType.MESSAGE:
                await manager.broadcast(WebSocketMessage(
                    type=MessageType.MESSAGE,
                    data={**data.get("data", {}), "from": user_id},
                ))
                continue

            # 其他消息类型：原样广播（可按业务需求扩展）
            await manager.broadcast(WebSocketMessage(
                type=msg_type,
                data=data.get("data", {}),
            ))

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket 异常断开：user=%s, error=%s", user_id, e)
        await manager.disconnect(websocket, send_reconnect=True)
