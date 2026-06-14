import json
import time
import httpx
import asyncio
import logging
from typing import Dict, Any, Optional, List, AsyncGenerator
from dataclasses import dataclass

from backend.core.config import settings

logger = logging.getLogger(__name__)

ZHIPU_API_URL = settings.zhipu_api_url
ZHIPU_API_KEY = settings.zhipu_api_key
ZHIPU_MODEL = settings.zhipu_model

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 60.0


@dataclass
class ZhiPuMessage:
    role: str
    content: str


@dataclass
class ZhiPuCallStats:
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    total_latency_ms: float = 0.0
    last_call_time: Optional[float] = None
    last_error: Optional[str] = None


class ZhiPuService:
    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or ZHIPU_API_KEY
        self.model = model or ZHIPU_MODEL
        self.api_url = ZHIPU_API_URL
        self.available = bool(self.api_key)
        self.stats = ZhiPuCallStats()
        self._client: Optional[httpx.AsyncClient] = None

        if self.available:
            logger.info(f"ZhiPu服务已初始化, 模型: {self.model}")
        else:
            logger.info("ZhiPu API Key 未配置，服务不可用")

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
        messages: List[ZhiPuMessage],
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

    async def chat(
        self,
        messages: List[ZhiPuMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        if not self.available:
            raise ValueError("ZhiPu API Key 未配置")

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
                # Check for API error codes in response body (e.g., 3003 rate limit)
                if "error" in data and isinstance(data["error"], dict):
                    error_code = str(data["error"].get("code", ""))
                    error_msg = data["error"].get("message", "未知错误")
                    if error_code in ("3003", "1002", "1004", "1122", "1212"):
                        raise httpx.HTTPStatusError(
                            f"ZhiPu API error {error_code}: {error_msg}",
                            request=response.request,
                            response=response,
                        )
                content = data["choices"][0]["message"]["content"]

                latency = (time.time() - start_time) * 1000
                self.stats.total_calls += 1
                self.stats.success_calls += 1
                self.stats.total_latency_ms += latency
                self.stats.last_call_time = time.time()

                return content

            except httpx.TimeoutException as e:
                last_error = f"ZhiPu请求超时: {str(e)}"
                self.stats.last_error = last_error
            except httpx.HTTPStatusError as e:
                err_msg = str(e)
                if e.response.status_code == 429 or "3003" in err_msg or "1002" in err_msg:
                    wait = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)] * 2
                    last_error = f"ZhiPu速率限制，等待{wait}秒后重试: {err_msg}"
                    self.stats.last_error = last_error
                    await asyncio.sleep(wait)
                    continue
                elif e.response.status_code >= 500:
                    last_error = f"ZhiPu服务端错误: {e.response.status_code}"
                    self.stats.last_error = last_error
                else:
                    last_error = f"ZhiPu HTTP错误: {e.response.status_code}"
                    self.stats.last_error = last_error
                    break
            except Exception as e:
                last_error = f"ZhiPu请求异常: {str(e)}"
                self.stats.last_error = last_error

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])

        self.stats.total_calls += 1
        self.stats.failed_calls += 1
        raise RuntimeError(f"ZhiPu调用失败(重试{MAX_RETRIES}次): {last_error}")

    async def chat_stream(
        self,
        messages: List[ZhiPuMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> AsyncGenerator[str, None]:
        if not self.available:
            raise ValueError("ZhiPu API Key 未配置")

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
                                # Check for API error codes in response body (e.g., 3003 rate limit)
                                if "error" in data and isinstance(data["error"], dict):
                                    error_code = data["error"].get("code", "")
                                    error_msg = data["error"].get("message", "未知错误")
                                    if error_code in ("3003", "1002", "1004", "1122", "1212"):
                                        raise httpx.HTTPStatusError(
                                            f"ZhiPu API error {error_code}: {error_msg}",
                                            request=response.request,
                                            response=response,
                                        )
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
                last_error = f"ZhiPu流式请求超时: {str(e)}"
                self.stats.last_error = last_error
            except httpx.HTTPStatusError as e:
                err_msg = str(e)
                if e.response.status_code == 429 or "3003" in err_msg or "1002" in err_msg:
                    wait = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)] * 2
                    last_error = f"ZhiPu流式速率限制，等待{wait}秒后重试: {err_msg}"
                    self.stats.last_error = last_error
                    await asyncio.sleep(wait)
                    continue
                elif e.response.status_code >= 500:
                    last_error = f"ZhiPu流式服务端错误: {e.response.status_code}"
                    self.stats.last_error = last_error
                else:
                    last_error = f"ZhiPu流式HTTP错误: {e.response.status_code}"
                    self.stats.last_error = last_error
                    break
            except httpx.ConnectError as e:
                last_error = f"ZhiPu连接失败: {str(e)}"
                self.stats.last_error = last_error
            except Exception as e:
                last_error = f"ZhiPu流式请求异常: {str(e)}"
                self.stats.last_error = last_error

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])

        self.stats.total_calls += 1
        self.stats.failed_calls += 1
        raise RuntimeError(f"ZhiPu流式调用失败(重试{MAX_RETRIES}次): {last_error}")

    def get_stats(self) -> Dict[str, Any]:
        avg_latency = (
            self.stats.total_latency_ms / self.stats.success_calls
            if self.stats.success_calls > 0
            else 0
        )
        return {
            "available": self.available,
            "model": self.model,
            "provider": "zhipu",
            "total_calls": self.stats.total_calls,
            "success_calls": self.stats.success_calls,
            "failed_calls": self.stats.failed_calls,
            "avg_latency_ms": round(avg_latency, 1),
            "last_call_time": self.stats.last_call_time,
            "last_error": self.stats.last_error
        }


_zhipu_instance: Optional[ZhiPuService] = None


def get_zhipu_service() -> ZhiPuService:
    global _zhipu_instance
    if _zhipu_instance is None:
        _zhipu_instance = ZhiPuService()
    return _zhipu_instance
