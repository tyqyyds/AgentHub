from langchain.tools import tool
from typing import Dict, List, Any
import time

COMPUTE_NODES = {
    "node-A": {
        "node_id": "node-A",
        "node_type": "gpu",
        "region": "beijing",
        "available_cpu": 64,
        "available_memory": 128000,
        "gpu_count": 4,
        "gpu_memory": 24000,
        "current_load": 0.05,
        "status": "online",
        "endpoint": "http://localhost:8001/api/task",
        "latency_ms": 20
    },
    "node-B": {
        "node_id": "node-B",
        "node_type": "gpu",
        "region": "shanghai",
        "available_cpu": 32,
        "available_memory": 128000,
        "gpu_count": 4,
        "gpu_memory": 24000,
        "current_load": 0.1,
        "status": "online",
        "endpoint": "http://localhost:8002/api/task",
        "latency_ms": 30
    },
    "node-gpu-beijing": {
        "node_id": "node-gpu-beijing",
        "node_type": "gpu",
        "region": "beijing",
        "available_cpu": 32,
        "available_memory": 128000,
        "gpu_count": 4,
        "gpu_memory": 24000,
        "current_load": 0.2,
        "status": "online",
        "endpoint": "http://localhost:8001/api/task"
    },
    "node-edge-shanghai": {
        "node_id": "node-edge-shanghai",
        "node_type": "edge",
        "region": "shanghai",
        "available_cpu": 8,
        "available_memory": 16000,
        "gpu_count": 0,
        "gpu_memory": 0,
        "current_load": 0.1,
        "status": "online",
        "endpoint": "http://localhost:8002/api/task"
    },
    "node-cpu-hangzhou": {
        "node_id": "node-cpu-hangzhou",
        "node_type": "cpu",
        "region": "hangzhou",
        "available_cpu": 64,
        "available_memory": 256000,
        "gpu_count": 0,
        "gpu_memory": 0,
        "current_load": 0.05,
        "status": "online",
        "endpoint": "http://localhost:8003/api/task"
    },
    "node-gpu-guangzhou": {
        "node_id": "node-gpu-guangzhou",
        "node_type": "gpu",
        "region": "guangzhou",
        "available_cpu": 24,
        "available_memory": 96000,
        "gpu_count": 2,
        "gpu_memory": 24000,
        "current_load": 0.3,
        "status": "online",
        "endpoint": "http://localhost:8004/api/task"
    },
    "node-cpu-chengdu": {
        "node_id": "node-cpu-chengdu",
        "node_type": "cpu",
        "region": "chengdu",
        "available_cpu": 16,
        "available_memory": 32000,
        "gpu_count": 0,
        "gpu_memory": 0,
        "current_load": 0.15,
        "status": "online",
        "endpoint": "http://localhost:8005/api/task"
    }
}

def _query_compute_nodes(region: str = None) -> List[Dict]:
    nodes = list(COMPUTE_NODES.values())
    if region:
        nodes = [node for node in nodes if node["region"] == region]
    return nodes

def _get_node_status(node_id: str) -> Dict:
    node = COMPUTE_NODES.get(node_id)
    if not node:
        return {"error": f"Node {node_id} not found"}
    return node

def _submit_task_to_node(node_id: str, task_config: Dict) -> Dict:
    node = COMPUTE_NODES.get(node_id)
    if not node:
        return {"error": f"Node {node_id} not found", "status": "failed"}

    if node["status"] != "online":
        return {"error": f"Node {node_id} is offline", "status": "failed"}

    if task_config.get("required_gpu", 0) > node["gpu_count"]:
        return {"error": "Insufficient GPU resources", "status": "failed"}

    return {
        "task_id": f"task_{node_id}_{time.time()}",
        "node_id": node_id,
        "status": "submitted",
        "message": f"Task submitted to {node_id}"
    }

@tool
def query_compute_nodes(region: str = None) -> List[Dict]:
    """查询所有可用的算力节点，可按地域筛选"""
    return _query_compute_nodes(region)

@tool
def get_node_status(node_id: str) -> Dict:
    """获取指定算力节点的实时状态"""
    return _get_node_status(node_id)

@tool
def submit_task_to_node(node_id: str, task_config: Dict) -> Dict:
    """向指定的算力节点提交计算任务"""
    return _submit_task_to_node(node_id, task_config)

query_compute_nodes_direct = _query_compute_nodes
get_node_status_direct = _get_node_status
submit_task_to_node_direct = _submit_task_to_node