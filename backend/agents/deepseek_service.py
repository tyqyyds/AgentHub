import json
import time
import httpx
import asyncio
from typing import Dict, Any, Optional, List, AsyncGenerator
from dataclasses import dataclass, field

from backend.core.config import settings

DEEPSEEK_API_URL = settings.deepseek_api_url
DEEPSEEK_API_KEY = settings.deepseek_api_key
DEEPSEEK_MODEL = settings.deepseek_model

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 60.0
MAX_CONTEXT_MESSAGES = 20
MAX_CONTEXT_CHARS = 8000

@dataclass
class DeepSeekMessage:
    role: str
    content: str

@dataclass
class CallStats:
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    total_latency_ms: float = 0.0
    last_call_time: Optional[float] = None
    last_error: Optional[str] = None

class DeepSeekService:
    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.model = model or DEEPSEEK_MODEL
        self.api_url = DEEPSEEK_API_URL
        self.available = bool(self.api_key)
        self.stats = CallStats()
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=30.0, pool=30.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
            )
        return self._client
    
    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def _build_payload(
        self,
        messages: List[DeepSeekMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False
    ) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
    
    def _trim_context(self, messages: List[DeepSeekMessage], max_chars: int = MAX_CONTEXT_CHARS) -> List[DeepSeekMessage]:
        total_chars = sum(len(m.content) for m in messages)
        if total_chars <= max_chars:
            return messages
        
        system_msgs = [m for m in messages if m.role == "system"]
        other_msgs = [m for m in messages if m.role != "system"]
        
        while total_chars > max_chars and len(other_msgs) > 2:
            removed = other_msgs.pop(0)
            total_chars -= len(removed.content)
        
        return system_msgs + other_msgs
    
    async def chat(
        self,
        messages: List[DeepSeekMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        if not self.available:
            raise ValueError("DeepSeek API Key 未配置")
        
        messages = self._trim_context(messages)
        payload = self._build_payload(messages, temperature, max_tokens, stream=False)
        
        last_error = None
        for attempt in range(MAX_RETRIES):
            start_time = time.time()
            try:
                client = await self._get_client()
                response = await client.post(
                    self.api_url,
                    headers=self._build_headers(),
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                latency = (time.time() - start_time) * 1000
                self.stats.total_calls += 1
                self.stats.success_calls += 1
                self.stats.total_latency_ms += latency
                self.stats.last_call_time = time.time()
                
                return content
                
            except httpx.TimeoutException as e:
                last_error = f"请求超时: {str(e)}"
                self.stats.last_error = last_error
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)] * 2
                    last_error = f"速率限制，等待{wait}秒后重试"
                    self.stats.last_error = last_error
                    await asyncio.sleep(wait)
                    continue
                elif e.response.status_code >= 500:
                    last_error = f"服务端错误: {e.response.status_code}"
                    self.stats.last_error = last_error
                else:
                    last_error = f"HTTP错误: {e.response.status_code}"
                    self.stats.last_error = last_error
                    break
            except Exception as e:
                last_error = f"请求异常: {str(e)}"
                self.stats.last_error = last_error
            
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])
        
        self.stats.total_calls += 1
        self.stats.failed_calls += 1
        raise RuntimeError(f"DeepSeek调用失败(重试{MAX_RETRIES}次): {last_error}")
    
    async def chat_stream(
        self,
        messages: List[DeepSeekMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> AsyncGenerator[str, None]:
        if not self.available:
            raise ValueError("DeepSeek API Key 未配置")
        
        messages = self._trim_context(messages)
        payload = self._build_payload(messages, temperature, max_tokens, stream=True)
        
        last_error = None
        for attempt in range(MAX_RETRIES):
            start_time = time.time()
            try:
                client = await self._get_client()
                async with client.stream(
                    "POST",
                    self.api_url,
                    headers=self._build_headers(),
                    json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except json.JSONDecodeError:
                                continue
                
                latency = (time.time() - start_time) * 1000
                self.stats.total_calls += 1
                self.stats.success_calls += 1
                self.stats.total_latency_ms += latency
                self.stats.last_call_time = time.time()
                return
                
            except httpx.TimeoutException as e:
                last_error = f"流式请求超时: {str(e)}"
                self.stats.last_error = last_error
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)] * 2
                    last_error = f"流式请求速率限制，等待{wait}秒后重试"
                    self.stats.last_error = last_error
                    await asyncio.sleep(wait)
                    continue
                elif e.response.status_code >= 500:
                    last_error = f"流式请求服务端错误: {e.response.status_code}"
                    self.stats.last_error = last_error
                else:
                    last_error = f"流式请求HTTP错误: {e.response.status_code}"
                    self.stats.last_error = last_error
                    break
            except httpx.ConnectError as e:
                last_error = f"连接失败: {str(e)}"
                self.stats.last_error = last_error
            except Exception as e:
                last_error = f"流式请求异常: {str(e)}"
                self.stats.last_error = last_error
            
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])
        
        self.stats.total_calls += 1
        self.stats.failed_calls += 1
        raise RuntimeError(f"DeepSeek流式调用失败(重试{MAX_RETRIES}次): {last_error}")
    
    def get_stats(self) -> Dict[str, Any]:
        avg_latency = (
            self.stats.total_latency_ms / self.stats.success_calls
            if self.stats.success_calls > 0
            else 0
        )
        return {
            "available": self.available,
            "model": self.model,
            "total_calls": self.stats.total_calls,
            "success_calls": self.stats.success_calls,
            "failed_calls": self.stats.failed_calls,
            "avg_latency_ms": round(avg_latency, 1),
            "last_call_time": self.stats.last_call_time,
            "last_error": self.stats.last_error
        }

_deepseek_instance: Optional[DeepSeekService] = None
_instance_lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None


def get_deepseek_service() -> DeepSeekService:
    global _deepseek_instance
    if _deepseek_instance is None:
        _deepseek_instance = DeepSeekService()
    return _deepseek_instance
