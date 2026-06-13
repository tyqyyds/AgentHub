"""智谱GLM服务 - 智谱GLM LLM调用封装，支持Function Calling、流式对话"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FunctionDefinition:
    """函数定义"""
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    """工具调用"""
    id: str
    function_name: str
    arguments: dict[str, Any]


@dataclass
class ZhipuConfig:
    """智谱GLM服务配置"""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: int = 30
    max_retries: int = 2

    def __post_init__(self):
        if not self.api_key:
            self.api_key = settings.zhipu_api_key
        if not self.base_url:
            self.base_url = settings.zhipu_base_url
        if not self.model:
            self.model = settings.zhipu_model


@dataclass
class ZhipuResponse:
    """智谱GLM响应"""
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    success: bool = True
    error: Optional[str] = None


class ZhipuService:
    """智谱GLM服务 - 封装智谱GLM API调用，支持Function Calling"""

    def __init__(self, config: Optional[ZhipuConfig] = None):
        self.config = config or ZhipuConfig()
        self._http_client = None
        self._registered_tools: dict[str, FunctionDefinition] = {}
        self._stats: dict[str, int] = {
            "total_calls": 0,
            "success_calls": 0,
            "failed_calls": 0,
            "tool_calls_count": 0,
            "total_tokens": 0,
        }
        logger.info(f"智谱GLM服务初始化, model={self.config.model}")

    def _get_http_client(self):
        """获取httpx客户端"""
        if self._http_client is None:
            try:
                import httpx
                self._http_client = httpx.AsyncClient(timeout=self.config.timeout_seconds)
            except ImportError:
                logger.error("httpx未安装，无法调用智谱GLM API")
                return None
        return self._http_client

    def register_tool(self, tool: FunctionDefinition):
        """注册工具函数"""
        self._registered_tools[tool.name] = tool
        logger.info(f"注册工具: {tool.name}")

    def unregister_tool(self, name: str):
        """注销工具函数"""
        if name in self._registered_tools:
            del self._registered_tools[name]
            logger.info(f"注销工具: {name}")

    def _build_tools_payload(self) -> list[dict]:
        """构建tools参数"""
        tools = []
        for tool in self._registered_tools.values():
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return tools

    def _parse_tool_calls(self, data: dict) -> list[ToolCall]:
        """解析工具调用"""
        tool_calls = []
        message = data.get("choices", [{}])[0].get("message", {})
        raw_calls = message.get("tool_calls", [])
        for call in raw_calls:
            func = call.get("function", {})
            try:
                args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {"raw": func.get("arguments", "")}
            tool_calls.append(ToolCall(
                id=call.get("id", ""),
                function_name=func.get("name", ""),
                arguments=args,
            ))
        return tool_calls

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_tools: bool = False,
    ) -> ZhipuResponse:
        """聊天接口"""
        start_time = time.time()
        self._stats["total_calls"] += 1

        try:
            client = self._get_http_client()
            if client is None:
                return ZhipuResponse(
                    content="",
                    model=self.config.model,
                    success=False,
                    error="httpx客户端未初始化",
                )

            url = f"{self.config.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            }
            payload: dict[str, Any] = {
                "model": self.config.model,
                "messages": messages,
                "temperature": temperature or self.config.temperature,
                "max_tokens": max_tokens or self.config.max_tokens,
                "stream": False,
            }

            if use_tools and self._registered_tools:
                payload["tools"] = self._build_tools_payload()

            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            latency_ms = (time.time() - start_time) * 1000
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            tool_calls = self._parse_tool_calls(data)
            finish_reason = data.get("choices", [{}])[0].get("finish_reason", "stop")

            self._stats["success_calls"] += 1
            self._stats["total_tokens"] += usage.get("total_tokens", 0)
            if tool_calls:
                self._stats["tool_calls_count"] += len(tool_calls)

            return ZhipuResponse(
                content=content,
                model=self.config.model,
                usage=usage,
                latency_ms=latency_ms,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                success=True,
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._stats["failed_calls"] += 1
            logger.error(f"智谱GLM聊天失败: {e}")
            return ZhipuResponse(
                content="",
                model=self.config.model,
                latency_ms=latency_ms,
                success=False,
                error=str(e),
            )

    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tool_executor: Optional[callable] = None,
        max_rounds: int = 5,
    ) -> ZhipuResponse:
        """带工具调用的多轮对话"""
        current_messages = list(messages)

        for round_idx in range(max_rounds):
            response = await self.chat(current_messages, use_tools=True)

            if not response.success:
                return response

            if not response.tool_calls:
                return response

            current_messages.append({
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function_name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ],
            })

            for tc in response.tool_calls:
                if tool_executor:
                    try:
                        result = await tool_executor(tc.function_name, tc.arguments)
                    except Exception as e:
                        result = {"error": str(e)}
                else:
                    result = {"status": "mock", "message": f"工具 {tc.function_name} 模拟执行成功"}

                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                })

        return response

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """流式聊天接口"""
        try:
            import httpx

            url = f"{self.config.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.config.model,
                "messages": messages,
                "temperature": temperature or self.config.temperature,
                "stream": True,
            }

            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    async for line in resp.aiter_lines():
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
        except Exception as e:
            logger.error(f"智谱GLM流式调用失败: {e}")
            yield f"[错误] {str(e)}"

    async def function_call(
        self,
        messages: list[dict[str, str]],
        functions: list[FunctionDefinition],
    ) -> ZhipuResponse:
        """Function Calling专用接口"""
        for func in functions:
            self.register_tool(func)

        response = await self.chat(messages, use_tools=True)

        for func in functions:
            self.unregister_tool(func.name)

        return response

    def get_stats(self) -> dict[str, Any]:
        """获取服务统计"""
        return {
            **self._stats,
            "model": self.config.model,
            "registered_tools": list(self._registered_tools.keys()),
            "success_rate": (
                self._stats["success_calls"] / max(self._stats["total_calls"], 1)
            ),
        }

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Agent标准处理接口"""
        action = input_data.get("action", "chat")
        messages = input_data.get("messages", [])

        if action == "function_call":
            functions = [
                FunctionDefinition(**f) for f in input_data.get("functions", [])
            ]
            response = await self.function_call(messages, functions)
        elif action == "chat_with_tools":
            tool_executor = input_data.get("tool_executor")
            max_rounds = input_data.get("max_rounds", settings.react_max_iterations)
            response = await self.chat_with_tools(messages, tool_executor, max_rounds)
        else:
            response = await self.chat(messages)

        return {
            "action": action,
            "content": response.content,
            "tool_calls": [
                {"name": tc.function_name, "arguments": tc.arguments}
                for tc in response.tool_calls
            ],
            "success": response.success,
            "error": response.error,
        }

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        try:
            response = await self.chat(
                [{"role": "user", "content": "ping"}],
                max_tokens=10,
            )
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
