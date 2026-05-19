"""
WebSocket 客户端工具 - 用于 LangGraph 节点发送实时事件
"""

import asyncio
import httpx
from typing import Dict, Any, Optional


async def send_workflow_event_async(node_name: str, output: Dict[str, Any], status: str = "completed"):
    """异步发送工作流事件到 WebSocket 服务"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8000/api/workflow/event",
                json={
                    "node_name": node_name,
                    "output": output,
                    "status": status
                }
            )
            return response.status_code == 200
    except Exception:
        return False


def send_workflow_event_sync(node_name: str, output: Dict[str, Any], status: str = "completed"):
    """同步发送工作流事件到 WebSocket 服务"""
    try:
        with httpx.Client() as client:
            response = client.post(
                "http://localhost:8000/api/workflow/event",
                json={
                    "node_name": node_name,
                    "output": output,
                    "status": status
                }
            )
            return response.status_code == 200
    except Exception:
        return False


# 示例使用
if __name__ == "__main__":
    # 同步调用
    result = send_workflow_event_sync(
        node_name="intent_parser",
        output={"task_type": "inference", "compute_type": "GPU"},
        status="completed"
    )
    print(f"Event sent: {result}")
    
    # 异步调用
    asyncio.run(send_workflow_event_async(
        node_name="resource_discovery",
        output={"available_resources": ["node1", "node2"]},
        status="completed"
    ))