"""A2A消息总线 - Agent间跨域通信，JSON-RPC 2.0协议，发布-订阅模式"""

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    BROADCAST = "broadcast"
    ERROR = "error"


class MessagePriority(Enum):
    """消息优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class A2AMessage:
    """A2A消息 - JSON-RPC 2.0格式"""
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: Optional[str] = None
    params: dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[dict[str, Any]] = None
    message_type: MessageType = MessageType.REQUEST
    priority: MessagePriority = MessagePriority.NORMAL
    source_agent: str = ""
    target_agent: str = ""
    timestamp: float = 0.0
    ttl_seconds: int = 300

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "method": self.method,
            "params": self.params,
            "result": self.result,
            "error": self.error,
            "message_type": self.message_type.value,
            "priority": self.priority.value,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "A2AMessage":
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params", {}),
            result=data.get("result"),
            error=data.get("error"),
            message_type=MessageType(data.get("message_type", "request")),
            priority=MessagePriority(data.get("priority", 1)),
            source_agent=data.get("source_agent", ""),
            target_agent=data.get("target_agent", ""),
            timestamp=data.get("timestamp", time.time()),
        )


@dataclass
class Subscription:
    """订阅信息"""
    subscriber_id: str
    topic: str
    callback: Optional[Callable[[A2AMessage], Coroutine[Any, Any, None]]] = None
    filter_rules: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class A2ABusConfig:
    """A2A消息总线配置"""
    max_queue_size: int = 1000
    max_subscribers_per_topic: int = 50
    message_ttl_seconds: int = 300
    enable_persistence: bool = False
    retry_count: int = 3
    retry_delay_ms: int = 200
    max_history_size: int = 1000


class A2ABus:
    """A2A消息总线 - Agent间跨域通信"""

    def __init__(self, config: Optional[A2ABusConfig] = None):
        self.config = config or A2ABusConfig()
        self._subscribers: dict[str, list[Subscription]] = defaultdict(list)
        self._message_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.config.max_queue_size
        )
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._agent_registry: dict[str, dict[str, Any]] = {}
        self._history: list[A2AMessage] = []
        self._stats: dict[str, int] = {
            "messages_sent": 0,
            "messages_received": 0,
            "messages_broadcast": 0,
            "messages_dropped": 0,
            "subscriptions_total": 0,
            "errors": 0,
        }
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        logger.info("A2A消息总线初始化完成")

    async def start(self):
        """启动消息总线处理器"""
        if self._running:
            return
        self._running = True
        self._processor_task = asyncio.create_task(self._process_messages())
        logger.info("A2A消息总线已启动")

    async def stop(self):
        """停止消息总线"""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("A2A消息总线已停止")

    def register_agent(self, agent_id: str, capabilities: list[str], metadata: Optional[dict] = None):
        """注册Agent到总线"""
        self._agent_registry[agent_id] = {
            "capabilities": capabilities,
            "metadata": metadata or {},
            "registered_at": time.time(),
            "status": "active",
        }
        logger.info(f"Agent注册: {agent_id}, 能力: {capabilities}")

    def unregister_agent(self, agent_id: str):
        """注销Agent"""
        if agent_id in self._agent_registry:
            del self._agent_registry[agent_id]
            topics_to_clean = []
            for topic, subs in self._subscribers.items():
                self._subscribers[topic] = [
                    s for s in subs if s.subscriber_id != agent_id
                ]
                if not self._subscribers[topic]:
                    topics_to_clean.append(topic)
            for topic in topics_to_clean:
                del self._subscribers[topic]
            logger.info(f"Agent注销: {agent_id}")

    def subscribe(
        self,
        subscriber_id: str,
        topic: str,
        callback: Optional[Callable[[A2AMessage], Coroutine[Any, Any, None]]] = None,
        filter_rules: Optional[dict] = None,
    ) -> bool:
        """订阅主题"""
        subs = self._subscribers[topic]
        if len(subs) >= self.config.max_subscribers_per_topic:
            logger.warning(f"主题 {topic} 订阅数已达上限")
            return False

        existing = [s for s in subs if s.subscriber_id == subscriber_id]
        if existing:
            logger.warning(f"Agent {subscriber_id} 已订阅主题 {topic}")
            return False

        sub = Subscription(
            subscriber_id=subscriber_id,
            topic=topic,
            callback=callback,
            filter_rules=filter_rules or {},
        )
        subs.append(sub)
        self._stats["subscriptions_total"] += 1
        logger.info(f"订阅: {subscriber_id} -> {topic}")
        return True

    def unsubscribe(self, subscriber_id: str, topic: str):
        """取消订阅"""
        if topic in self._subscribers:
            self._subscribers[topic] = [
                s for s in self._subscribers[topic]
                if s.subscriber_id != subscriber_id
            ]

    async def publish(self, message: A2AMessage) -> bool:
        """发布消息到总线"""
        if message.is_expired():
            self._stats["messages_dropped"] += 1
            logger.warning(f"消息已过期，丢弃: {message.id}")
            return False

        try:
            self._message_queue.put_nowait(message)
            self._stats["messages_sent"] += 1
            return True
        except asyncio.QueueFull:
            self._stats["messages_dropped"] += 1
            logger.warning("消息队列已满，丢弃消息")
            return False

    async def send_request(
        self,
        source_agent: str,
        target_agent: str,
        method: str,
        params: dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> Optional[A2AMessage]:
        """发送请求并等待响应"""
        message = A2AMessage(
            method=method,
            params=params,
            message_type=MessageType.REQUEST,
            source_agent=source_agent,
            target_agent=target_agent,
        )

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[message.id] = future

        await self.publish(message)

        try:
            response = await asyncio.wait_for(future, timeout=timeout_seconds)
            return response
        except asyncio.TimeoutError:
            logger.warning(f"请求超时: {message.id}, method={method}")
            return None
        finally:
            self._pending_requests.pop(message.id, None)

    async def send_response(
        self,
        request_id: str,
        source_agent: str,
        target_agent: str,
        result: Any = None,
        error: Optional[dict] = None,
    ):
        """发送响应"""
        message = A2AMessage(
            id=request_id,
            result=result,
            error=error,
            message_type=MessageType.RESPONSE,
            source_agent=source_agent,
            target_agent=target_agent,
        )
        await self.publish(message)

    async def broadcast(
        self,
        source_agent: str,
        topic: str,
        method: str,
        params: dict[str, Any],
    ):
        """广播消息"""
        message = A2AMessage(
            method=method,
            params=params,
            message_type=MessageType.BROADCAST,
            source_agent=source_agent,
            target_agent=topic,
        )
        await self.publish(message)
        self._stats["messages_broadcast"] += 1

    async def _process_messages(self):
        """消息处理循环"""
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(), timeout=1.0
                )
                await self._dispatch_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self._stats["errors"] += 1
                logger.error(f"消息处理错误: {e}")

    async def _dispatch_message(self, message: A2AMessage):
        """分发消息"""
        self._stats["messages_received"] += 1

        if self.config.enable_persistence:
            self._history.append(message)
            if len(self._history) > self.config.max_history_size:
                self._history = self._history[-self.config.max_history_size:]

        if message.message_type == MessageType.RESPONSE:
            future = self._pending_requests.get(message.id)
            if future and not future.done():
                future.set_result(message)
            return

        if message.message_type == MessageType.BROADCAST:
            topic = message.target_agent
            subs = self._subscribers.get(topic, [])
            for sub in subs:
                if self._match_filter(message, sub.filter_rules):
                    if sub.callback:
                        try:
                            await sub.callback(message)
                        except Exception as e:
                            logger.error(f"回调执行失败: {sub.subscriber_id}, {e}")
            return

        if message.message_type == MessageType.REQUEST:
            target = message.target_agent
            subs = self._subscribers.get(target, [])
            for sub in subs:
                if sub.callback:
                    try:
                        await sub.callback(message)
                    except Exception as e:
                        logger.error(f"回调执行失败: {sub.subscriber_id}, {e}")

    def _match_filter(self, message: A2AMessage, filter_rules: dict) -> bool:
        """消息过滤匹配"""
        if not filter_rules:
            return True
        for key, value in filter_rules.items():
            if key == "source_agent" and message.source_agent != value:
                return False
            if key == "method" and message.method != value:
                return False
            if key == "priority_min":
                if message.priority.value < value:
                    return False
        return True

    def get_stats(self) -> dict[str, Any]:
        """获取总线统计"""
        return {
            **self._stats,
            "registered_agents": len(self._agent_registry),
            "topics": list(self._subscribers.keys()),
            "pending_requests": len(self._pending_requests),
            "queue_size": self._message_queue.qsize(),
        }

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Agent标准处理接口"""
        action = input_data.get("action", "publish")

        if action == "publish":
            message = A2AMessage.from_dict(input_data.get("message", {}))
            success = await self.publish(message)
            return {"action": "publish", "success": success, "message_id": message.id}

        elif action == "request":
            response = await self.send_request(
                source_agent=input_data.get("source_agent", ""),
                target_agent=input_data.get("target_agent", ""),
                method=input_data.get("method", ""),
                params=input_data.get("params", {}),
                timeout_seconds=input_data.get("timeout", 30.0),
            )
            return {
                "action": "request",
                "response": response.to_dict() if response else None,
            }

        elif action == "broadcast":
            await self.broadcast(
                source_agent=input_data.get("source_agent", ""),
                topic=input_data.get("topic", ""),
                method=input_data.get("method", ""),
                params=input_data.get("params", {}),
            )
            return {"action": "broadcast", "success": True}

        elif action == "subscribe":
            success = self.subscribe(
                subscriber_id=input_data.get("subscriber_id", ""),
                topic=input_data.get("topic", ""),
            )
            return {"action": "subscribe", "success": success}

        else:
            return {"action": action, "error": "未知操作"}

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy" if self._running else "stopped",
            "registered_agents": len(self._agent_registry),
            "active_subscriptions": sum(
                len(subs) for subs in self._subscribers.values()
            ),
            "pending_requests": len(self._pending_requests),
            "queue_size": self._message_queue.qsize(),
            "stats": self._stats,
        }

    async def agent_discover(self, capability: str = None, agent_type: str = None) -> list[dict]:
        """发现具有特定能力或类型的Agent (JSON-RPC: agent.discover)"""
        discovered = []
        for agent_id, info in self._agent_registry.items():
            if capability and capability not in info.get("capabilities", []):
                continue
            if agent_type and info.get("metadata", {}).get("type") != agent_type:
                continue
            # 判断Agent是否活跃：有订阅记录即视为active
            is_active = any(
                s.subscriber_id == agent_id
                for subs in self._subscribers.values()
                for s in subs
            )
            discovered.append({
                "agent_id": agent_id,
                "type": info.get("metadata", {}).get("type"),
                "capabilities": info.get("capabilities", []),
                "status": "active" if is_active else "inactive",
            })
        return discovered

    async def agent_call(self, target_agent: str, method: str, params: dict = None) -> Any:
        """跨域调用Agent方法 (JSON-RPC: agent.call)"""
        if target_agent not in self._agent_registry:
            raise ValueError(f"Agent '{target_agent}' not registered")

        request_id = str(uuid.uuid4())
        message = A2AMessage(
            jsonrpc="2.0",
            method="agent.call",
            params={
                "target_agent": target_agent,
                "method": method,
                "params": params or {},
            },
            id=request_id,
        )

        # 创建Future等待响应
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        await self.publish(message)

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"Agent call to '{target_agent}' timed out")

    async def agent_status(self, agent_id: str = None) -> dict | list[dict]:
        """查询Agent状态 (JSON-RPC: agent.status)"""
        if agent_id:
            if agent_id not in self._agent_registry:
                raise ValueError(f"Agent '{agent_id}' not registered")
            info = self._agent_registry[agent_id]
            # 收集该Agent的所有订阅主题
            subscribed_topics = set()
            for topic, subs in self._subscribers.items():
                for s in subs:
                    if s.subscriber_id == agent_id:
                        subscribed_topics.add(topic)
            return {
                "agent_id": agent_id,
                "type": info.get("metadata", {}).get("type"),
                "capabilities": info.get("capabilities", []),
                "status": info.get("status", "unknown"),
                "subscriptions": list(subscribed_topics),
                "last_activity": info.get("metadata", {}).get("last_activity"),
            }
        else:
            # 返回所有Agent状态
            return [
                {
                    "agent_id": aid,
                    "type": info.get("metadata", {}).get("type"),
                    "capabilities": info.get("capabilities", []),
                    "status": info.get("status", "unknown"),
                }
                for aid, info in self._agent_registry.items()
            ]
