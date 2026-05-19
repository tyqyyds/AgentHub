"""
算力节点工具封装 - 基于 LangChain 的 @tool 装饰器

提供与算力节点模拟器交互的工具函数，支持：
- 查询节点状态（调用模拟器 /status 接口）
- 提交任务到节点（调用模拟器 /submit_task 接口）

使用 httpx 作为异步 HTTP 客户端，提供完善的错误处理和类型提示。
"""

import os
from typing import Dict, Any, Optional
from langchain.tools import tool
import httpx

# 从环境变量读取模拟器服务配置
SIMULATOR_BASE_URL = os.getenv("SIMULATOR_BASE_URL", "http://localhost")


@tool
async def query_node_status(node_id: str) -> Dict[str, Any]:
    """
    查询指定算力节点的实时状态信息。
    
    调用模拟器的 /status 接口，获取节点的 CPU 利用率、内存使用、GPU 信息、
    网络延迟等实时状态数据。
    
    Args:
        node_id: 节点标识符，格式为 "node-<type>-<region>-<number>"，
                 例如 "node-gpu-beijing-01"。节点的端口通过 node_id 
                 推断，格式为 "node-<type>-<region>-<number>:<port>"，
                 或默认使用环境变量 SIMULATOR_BASE_URL 指定的地址。
    
    Returns:
        节点状态字典，包含以下字段：
        - node_id: 节点ID
        - node_type: 节点类型（cpu/gpu/edge）
        - region: 节点地域
        - status: 节点状态（online/offline）
        - cpu_usage: CPU利用率（百分比，20-80%波动）
        - total_cpu: 总CPU核心数
        - memory_used: 已用内存（MB）
        - total_memory: 总内存（MB）
        - gpu_count: GPU数量
        - gpu_type: GPU类型（如 NVIDIA A100）
        - gpu_memory_used: 已用显存（MB）
        - total_gpu_memory: 总显存（MB）
        - network_latency_ms: 网络延迟（毫秒，10-100ms波动）
        - running_tasks: 运行中任务数
    
    Examples:
        >>> await query_node_status("node-gpu-beijing-01")
        {
            "node_id": "node-gpu-beijing-01",
            "node_type": "gpu",
            "region": "beijing",
            "status": "online",
            "cpu_usage": 45.2,
            "total_cpu": 32,
            "memory_used": 65536.0,
            "total_memory": 131072.0,
            "gpu_count": 4,
            "gpu_type": "NVIDIA A100",
            "gpu_memory_used": 16384.0,
            "total_gpu_memory": 327680.0,
            "network_latency_ms": 25.5,
            "running_tasks": 2
        }
    
    Raises:
        httpx.HTTPError: 当 HTTP 请求失败时抛出
        ValueError: 当节点ID格式无效时抛出
    """
    # 解析节点ID，提取端口信息
    parts = node_id.split(':')
    actual_node_id = parts[0]
    port = parts[1] if len(parts) > 1 else "8080"
    
    # 构建请求URL
    url = f"{SIMULATOR_BASE_URL}:{port}/status"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            result = response.json()
            
            # 确保返回结果包含必要字段
            if "node_id" not in result:
                result["node_id"] = actual_node_id
            
            return result
        
        except httpx.HTTPError as e:
            return {
                "error": f"查询节点状态失败: {str(e)}",
                "node_id": actual_node_id,
                "status": "unreachable"
            }
        except Exception as e:
            return {
                "error": f"查询节点状态异常: {str(e)}",
                "node_id": actual_node_id,
                "status": "error"
            }


@tool
async def submit_task_to_node(node_id: str, task_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    向指定算力节点提交计算任务。
    
    调用模拟器的 /submit_task 接口，将任务配置发送到目标节点执行。
    
    Args:
        node_id: 目标节点标识符，格式为 "node-<type>-<region>-<number>"，
                 例如 "node-gpu-shanghai-01"。节点的端口通过 node_id 
                 推断，格式为 "node-<type>-<region>-<number>:<port>"，
                 或默认使用环境变量 SIMULATOR_BASE_URL 指定的地址。
        task_config: 任务配置字典，包含以下字段：
            - task_type: 任务类型，可选值为 "training"（训练）、
                        "inference"（推理）、"data_processing"（数据处理）
            - required_cpu: 所需CPU核心数，正整数
            - required_memory: 所需内存大小，单位为MB，正整数
            - required_gpu: 所需GPU数量，非负整数（CPU节点应为0）
            - data_size_mb: 数据大小，单位为MB，可选参数
            - priority: 任务优先级，可选值为 "low"、"normal"、"high"
    
    Returns:
        任务提交结果字典，包含以下字段：
        - task_id: 任务ID，用于后续查询和管理
        - node_id: 目标节点ID
        - status: 任务状态，包括 "submitted"（已提交）、"running"（运行中）、
                  "completed"（已完成）、"failed"（失败）
        - message: 响应消息，说明提交结果或错误原因
    
    Examples:
        >>> task_config = {
        ...     "task_type": "training",
        ...     "required_cpu": 8,
        ...     "required_memory": 16384,
        ...     "required_gpu": 2,
        ...     "data_size_mb": 500,
        ...     "priority": "high"
        ... }
        >>> await submit_task_to_node("node-gpu-beijing-01:8081", task_config)
        {
            "task_id": "task-node-gpu-beijing-01-1-1779103274",
            "node_id": "node-gpu-beijing-01",
            "status": "submitted",
            "message": "任务已提交到节点 node-gpu-beijing-01"
        }
    
    Raises:
        httpx.HTTPError: 当 HTTP 请求失败时抛出
        ValueError: 当任务配置缺少必要字段时抛出
    """
    # 验证任务配置
    required_fields = ["task_type", "required_cpu", "required_memory", "required_gpu"]
    for field in required_fields:
        if field not in task_config:
            return {
                "error": f"任务配置缺少必要字段: {field}",
                "status": "failed",
                "node_id": node_id
            }
    
    # 解析节点ID，提取端口信息
    parts = node_id.split(':')
    actual_node_id = parts[0]
    port = parts[1] if len(parts) > 1 else "8080"
    
    # 构建请求URL
    url = f"{SIMULATOR_BASE_URL}:{port}/submit_task"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                json=task_config,
                timeout=10.0
            )
            response.raise_for_status()
            result = response.json()
            
            # 确保返回结果包含必要字段
            if "node_id" not in result:
                result["node_id"] = actual_node_id
            
            return result
        
        except httpx.HTTPError as e:
            # 尝试从响应中获取错误信息
            try:
                error_data = response.json()
                return {
                    "error": error_data.get("detail", str(e)),
                    "status": "failed",
                    "node_id": actual_node_id
                }
            except:
                return {
                    "error": f"提交任务失败: {str(e)}",
                    "status": "failed",
                    "node_id": actual_node_id
                }
        except Exception as e:
            return {
                "error": f"提交任务异常: {str(e)}",
                "status": "failed",
                "node_id": actual_node_id
            }


# 同步版本的工具（用于非异步上下文）
@tool
def query_node_status_sync(node_id: str) -> Dict[str, Any]:
    """
    查询指定算力节点的实时状态信息（同步版本）。
    
    调用模拟器的 /status 接口，获取节点的实时状态数据。
    
    Args:
        node_id: 节点标识符，格式为 "node-<type>-<region>-<number>"，
                 可包含端口号，如 "node-gpu-beijing-01:8081"。
    
    Returns:
        节点状态字典，包含节点ID、类型、地域、状态、资源使用等信息。
    """
    import httpx
    
    parts = node_id.split(':')
    actual_node_id = parts[0]
    port = parts[1] if len(parts) > 1 else "8080"
    
    url = f"{SIMULATOR_BASE_URL}:{port}/status"
    
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        result = response.json()
        
        if "node_id" not in result:
            result["node_id"] = actual_node_id
        
        return result
    
    except httpx.HTTPError as e:
        return {
            "error": f"查询节点状态失败: {str(e)}",
            "node_id": actual_node_id,
            "status": "unreachable"
        }
    except Exception as e:
        return {
            "error": f"查询节点状态异常: {str(e)}",
            "node_id": actual_node_id,
            "status": "error"
        }


@tool
def submit_task_to_node_sync(node_id: str, task_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    向指定算力节点提交计算任务（同步版本）。
    
    调用模拟器的 /submit_task 接口，将任务配置发送到目标节点执行。
    
    Args:
        node_id: 目标节点标识符，格式为 "node-<type>-<region>-<number>"，
                 可包含端口号，如 "node-gpu-shanghai-01:8081"。
        task_config: 任务配置字典，包含 task_type、required_cpu、
                     required_memory、required_gpu 等字段。
    
    Returns:
        任务提交结果字典，包含任务ID、节点ID、状态和消息。
    """
    import httpx
    
    required_fields = ["task_type", "required_cpu", "required_memory", "required_gpu"]
    for field in required_fields:
        if field not in task_config:
            return {
                "error": f"任务配置缺少必要字段: {field}",
                "status": "failed",
                "node_id": node_id
            }
    
    parts = node_id.split(':')
    actual_node_id = parts[0]
    port = parts[1] if len(parts) > 1 else "8080"
    
    url = f"{SIMULATOR_BASE_URL}:{port}/submit_task"
    
    try:
        response = httpx.post(url, json=task_config, timeout=10.0)
        response.raise_for_status()
        result = response.json()
        
        if "node_id" not in result:
            result["node_id"] = actual_node_id
        
        return result
    
    except httpx.HTTPError as e:
        try:
            error_data = response.json()
            return {
                "error": error_data.get("detail", str(e)),
                "status": "failed",
                "node_id": actual_node_id
            }
        except:
            return {
                "error": f"提交任务失败: {str(e)}",
                "status": "failed",
                "node_id": actual_node_id
            }
    except Exception as e:
        return {
            "error": f"提交任务异常: {str(e)}",
            "status": "failed",
            "node_id": actual_node_id
        }