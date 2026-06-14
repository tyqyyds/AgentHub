from typing import List, Dict, Any, Optional, Callable
from collections import deque
from datetime import datetime
from uuid import uuid4
from backend.agents.base import A2AMessage
import asyncio
import logging

logger = logging.getLogger(__name__)
import json

class A2ABus:
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.message_history: deque = deque(maxlen=1000)
        self._worker_started = False

    def _ensure_worker(self):
        if not self._worker_started:
            try:
                asyncio.create_task(self._process_messages())
                self._worker_started = True
            except RuntimeError:
                pass
    
    async def _process_messages(self):
        while True:
            message = await self.message_queue.get()
            await self._dispatch_message(message)
            self.message_queue.task_done()
    
    def subscribe(self, topic: str, handler: Callable) -> str:
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        
        subscriber_id = str(uuid4())
        self.subscribers[topic].append({
            "id": subscriber_id,
            "handler": handler
        })
        
        return subscriber_id
    
    def unsubscribe(self, topic: str, subscriber_id: str) -> bool:
        if topic not in self.subscribers:
            return False
        
        self.subscribers[topic] = [
            s for s in self.subscribers[topic] 
            if s["id"] != subscriber_id
        ]
        
        return True
    
    def publish(self, topic: str, content: Dict[str, Any], sender_id: str = "system") -> str:
        message = A2AMessage(
            message_id=str(uuid4()),
            sender_id=sender_id,
            receiver_id=None,
            message_type=topic,
            content=content,
            timestamp=datetime.now().isoformat()
        )
        
        self.message_history.append(message)

        try:
            asyncio.create_task(self.message_queue.put(message))
        except RuntimeError:
            pass
        
        return message.message_id
    
    async def send_direct(self, receiver_id: str, content: Dict[str, Any], sender_id: str = "system") -> A2AMessage:
        self._ensure_worker()
        message = A2AMessage(
            message_id=str(uuid4()),
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type="direct_message",
            content=content,
            timestamp=datetime.now().isoformat()
        )
        
        self.message_history.append(message)
        
        await self._dispatch_message(message)
        
        return message
    
    async def _dispatch_message(self, message: A2AMessage):
        topic = message.message_type
        
        if topic in self.subscribers:
            for subscriber in self.subscribers[topic]:
                try:
                    await subscriber["handler"](message)
                except Exception as e:
                    logger.error(f"Error handling message for {subscriber['id']}: {e}")
        
        if message.receiver_id:
            direct_topic = f"direct:{message.receiver_id}"
            if direct_topic in self.subscribers:
                for subscriber in self.subscribers[direct_topic]:
                    try:
                        await subscriber["handler"](message)
                    except Exception as e:
                        print(f"Error handling direct message: {e}")
    
    async def request(self, receiver_id: str, content: Dict[str, Any], sender_id: str = "system", timeout: int = 30) -> Any:
        response_event = asyncio.Event()
        response = None
        
        def response_handler(msg: A2AMessage):
            nonlocal response
            if msg.reply_to == content.get("request_id"):
                response = msg.content
                response_event.set()
        
        request_id = str(uuid4())
        content["request_id"] = request_id
        
        self.subscribe(f"response:{receiver_id}", response_handler)
        
        await self.send_direct(receiver_id, content, sender_id)
        
        try:
            response = await asyncio.wait_for(response_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            response = {"error": "Request timed out"}
        
        self.unsubscribe(f"response:{receiver_id}", response_handler.__name__)
        
        return response
    
    def get_history(self, limit: int = 100) -> List[A2AMessage]:
        return self.message_history[-limit:]
    
    def get_topic_stats(self) -> Dict[str, int]:
        stats = {}
        for msg in self.message_history:
            topic = msg.message_type
            stats[topic] = stats.get(topic, 0) + 1
        return stats
