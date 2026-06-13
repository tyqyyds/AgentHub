"""DeepSeek服务 - DeepSeek LLM调用封装，支持意图解析、对话增强、配置生成"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class DeepSeekConfig:
    """DeepSeek服务配置"""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: int = 30
    max_retries: int = 2
    retry_delay_ms: int = 500

    def __post_init__(self):
        if not self.api_key:
            self.api_key = settings.deepseek_api_key
        if not self.base_url:
            self.base_url = settings.deepseek_base_url
        if not self.model:
            self.model = settings.deepseek_model


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str
    content: str
    name: Optional[str] = None


@dataclass
class DeepSeekResponse:
    """DeepSeek响应"""
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    finish_reason: str = ""
    success: bool = True
    error: Optional[str] = None


class DeepSeekService:
    """DeepSeek服务 - 封装DeepSeek API调用"""

    def __init__(self, config: Optional[DeepSeekConfig] = None):
        self.config = config or DeepSeekConfig()
        self._client = None
        self._stats: dict[str, int] = {
            "total_calls": 0,
            "success_calls": 0,
            "failed_calls": 0,
            "total_tokens": 0,
        }
        logger.info(f"DeepSeek服务初始化, model={self.config.model}")

    def _get_client(self):
        """获取LangChain ChatOpenAI客户端"""
        if self._client is None:
            try:
                from langchain_community.chat_models import ChatOpenAI

                self._client = ChatOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    model=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    timeout=self.config.timeout_seconds,
                )
            except ImportError:
                logger.warning("langchain_community未安装，使用httpx直接调用")
                self._client = None
        return self._client

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> DeepSeekResponse:
        """聊天接口"""
        start_time = time.time()
        self._stats["total_calls"] += 1

        try:
            client = self._get_client()
            if client is not None:
                return await self._chat_via_langchain(
                    client, messages, temperature, max_tokens, start_time
                )
            else:
                return await self._chat_via_httpx(
                    messages, temperature, max_tokens, start_time
                )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._stats["failed_calls"] += 1
            logger.error(f"DeepSeek聊天失败: {e}")
            return DeepSeekResponse(
                content="",
                model=self.config.model,
                latency_ms=latency_ms,
                success=False,
                error=str(e),
            )

    async def _chat_via_langchain(
        self, client, messages, temperature, max_tokens, start_time
    ) -> DeepSeekResponse:
        """通过LangChain调用"""
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

        lc_messages = []
        for msg in messages:
            if msg.role == "system":
                lc_messages.append(SystemMessage(content=msg.content))
            elif msg.role == "assistant":
                lc_messages.append(AIMessage(content=msg.content))
            else:
                lc_messages.append(HumanMessage(content=msg.content))

        if temperature is not None:
            client.temperature = temperature
        if max_tokens is not None:
            client.max_tokens = max_tokens

        response = await client.ainvoke(lc_messages)
        latency_ms = (time.time() - start_time) * 1000

        self._stats["success_calls"] += 1
        return DeepSeekResponse(
            content=response.content,
            model=self.config.model,
            latency_ms=latency_ms,
            finish_reason="stop",
            success=True,
        )

    async def _chat_via_httpx(
        self, messages, temperature, max_tokens, start_time
    ) -> DeepSeekResponse:
        """通过httpx直接调用API"""
        import httpx

        url = f"{self.config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as http_client:
            resp = await http_client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        latency_ms = (time.time() - start_time) * 1000
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        self._stats["success_calls"] += 1
        self._stats["total_tokens"] += usage.get("total_tokens", 0)

        return DeepSeekResponse(
            content=content,
            model=self.config.model,
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=data.get("choices", [{}])[0].get("finish_reason", "stop"),
            success=True,
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """流式聊天接口"""
        try:
            client = self._get_client()
            if client is not None:
                from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

                lc_messages = []
                for msg in messages:
                    if msg.role == "system":
                        lc_messages.append(SystemMessage(content=msg.content))
                    elif msg.role == "assistant":
                        lc_messages.append(AIMessage(content=msg.content))
                    else:
                        lc_messages.append(HumanMessage(content=msg.content))

                client.streaming = True
                if temperature is not None:
                    client.temperature = temperature

                async for chunk in client.astream(lc_messages):
                    yield chunk.content
            else:
                import httpx

                url = f"{self.config.base_url}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.config.model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                    "temperature": temperature or self.config.temperature,
                    "stream": True,
                }

                async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as http_client:
                    async with http_client.stream("POST", url, json=payload, headers=headers) as resp:
                        async for line in resp.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str.strip() == "[DONE]":
                                    break
                                import json
                                try:
                                    data = json.loads(data_str)
                                    delta = data.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                                except json.JSONDecodeError:
                                    continue
        except Exception as e:
            logger.error(f"DeepSeek流式调用失败: {e}")
            yield f"[错误] {str(e)}"

    async def parse_intent(self, user_input: str) -> dict[str, Any]:
        """意图解析专用接口"""
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是一个网络运维意图解析专家。请将用户的自然语言输入解析为结构化意图。"
                    "输出JSON格式，包含：intent_type（意图类型）、target（目标对象）、"
                    "action（动作）、parameters（参数字典）、confidence（置信度0-1）。"
                ),
            ),
            ChatMessage(role="user", content=user_input),
        ]
        response = await self.chat(messages, temperature=0.3)
        if response.success:
            import json
            try:
                return json.loads(response.content)
            except json.JSONDecodeError:
                return {"raw_response": response.content, "parse_error": True}
        return {"error": response.error, "success": False}

    async def enhance_dialogue(self, context: str, user_input: str) -> str:
        """对话增强专用接口"""
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是一个网络运维助手，擅长用专业但易懂的语言回答网络运维问题。"
                    "请基于上下文和用户输入，提供准确、有用的回答。"
                ),
            ),
            ChatMessage(role="user", content=f"上下文：{context}\n\n用户问题：{user_input}"),
        ]
        response = await self.chat(messages)
        return response.content if response.success else f"[错误] {response.error}"

    async def generate_config(self, intent: dict[str, Any], device_info: dict[str, Any]) -> str:
        """配置生成专用接口"""
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是一个网络设备配置生成专家。根据意图和设备信息，"
                    "生成标准化的网络设备配置命令。只输出配置命令，不要解释。"
                ),
            ),
            ChatMessage(
                role="user",
                content=f"意图：{intent}\n设备信息：{device_info}",
            ),
        ]
        response = await self.chat(messages, temperature=0.2)
        return response.content if response.success else f"[错误] {response.error}"

    def get_stats(self) -> dict[str, Any]:
        """获取服务统计"""
        return {
            **self._stats,
            "model": self.config.model,
            "success_rate": (
                self._stats["success_calls"] / max(self._stats["total_calls"], 1)
            ),
        }

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Agent标准处理接口"""
        action = input_data.get("action", "chat")
        if action == "parse_intent":
            result = await self.parse_intent(input_data.get("user_input", ""))
            return {"action": "parse_intent", "result": result}
        elif action == "enhance_dialogue":
            result = await self.enhance_dialogue(
                input_data.get("context", ""),
                input_data.get("user_input", ""),
            )
            return {"action": "enhance_dialogue", "result": result}
        elif action == "generate_config":
            result = await self.generate_config(
                input_data.get("intent", {}),
                input_data.get("device_info", {}),
            )
            return {"action": "generate_config", "result": result}
        else:
            messages = [
                ChatMessage(role=m["role"], content=m["content"])
                for m in input_data.get("messages", [])
            ]
            response = await self.chat(messages)
            return {
                "action": "chat",
                "content": response.content,
                "success": response.success,
                "error": response.error,
            }

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        try:
            test_msg = [ChatMessage(role="user", content="ping")]
            response = await self.chat(test_msg, max_tokens=10)
            return {
                "status": "healthy" if response.success else "unhealthy",
                "model": self.config.model,
                "latency_ms": response.latency_ms,
                "stats": self._stats,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "model": self.config.model,
                "error": str(e),
            }
