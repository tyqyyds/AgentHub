from typing import List, Dict, Any, Optional

def calculate_resource_score(node: Dict[str, Any], requirement: Dict[str, Any]) -> float:
    """
    计算节点的资源匹配度得分（0-100）

    Args:
        node: 算力节点信息
        requirement: 任务资源需求

    Returns:
        匹配度得分
    """
    score = 0

    required_cpu = requirement.get("required_cpu", 1)
    available_cpu = node.get("available_cpu", 0)
    cpu_score = min(available_cpu / required_cpu, 1) * 100
    score += cpu_score * 0.4

    required_memory = requirement.get("required_memory", 1)
    available_memory = node.get("available_memory", 0)
    memory_score = min(available_memory / required_memory, 1) * 100
    score += memory_score * 0.4

    required_gpu = requirement.get("required_gpu", 0)
    available_gpu = node.get("gpu_count", 0)
    if required_gpu > 0:
        gpu_score = min(available_gpu / required_gpu, 1) * 100
        score += gpu_score * 0.2
    else:
        score += 100 * 0.2

    return score


def calculate_load_score(node: Dict[str, Any]) -> float:
    """
    计算节点负载得分（负载越低得分越高）

    Args:
        node: 算力节点信息

    Returns:
        负载得分（0-100）
    """
    load = node.get("current_load", 1)
    return (1 - load) * 100


def calculate_region_score(node: Dict[str, Any], requirement: Dict[str, Any]) -> float:
    """
    计算地域偏好得分

    Args:
        node: 算力节点信息
        requirement: 任务需求（含地域偏好）

    Returns:
        地域得分（0-100）
    """
    preferred_region = requirement.get("region_preference")
    if not preferred_region:
        return 100

    node_region = node.get("region")
    if node_region == preferred_region:
        return 100
    else:
        return 50


def calculate_latency_score(node: Dict[str, Any], requirement: Dict[str, Any]) -> float:
    """
    计算延迟得分（延迟越低得分越高）

    Args:
        node: 算力节点信息
        requirement: 任务需求（含延迟要求）

    Returns:
        延迟得分（0-100）
    """
    required_latency = requirement.get("required_latency_ms")
    if required_latency is None:
        return 100

    node_latency = node.get("latency_ms", 1000)
    if node_latency <= required_latency:
        return 100 * (1 - node_latency / required_latency) + 1
    else:
        return 0


def select_optimal_node(nodes: List[Dict[str, Any]], requirement: Dict[str, Any]) -> Optional[str]:
    """
    选择最优算力节点

    Args:
        nodes: 可用节点列表
        requirement: 任务需求

    Returns:
        最优节点ID，无可用节点返回None
    """
    if not nodes:
        return None

    best_node = None
    best_score = -1

    required_cpu = requirement.get("required_cpu", 0)
    required_memory = requirement.get("required_memory", 0)
    required_gpu = requirement.get("required_gpu", 0)

    for node in nodes:
        if node.get("status") != "online":
            continue

        if (node.get("available_cpu", 0) < required_cpu or
            node.get("available_memory", 0) < required_memory or
            node.get("gpu_count", 0) < required_gpu):
            continue

        resource_score = calculate_resource_score(node, requirement)
        region_score = calculate_region_score(node, requirement)
        load_score = calculate_load_score(node)
        latency_score = calculate_latency_score(node, requirement)

        total_score = resource_score * 0.6 + region_score * 0.1 + load_score * 0.1 + latency_score * 0.2

        if total_score > best_score:
            best_score = total_score
            best_node = node.get("node_id")

    return best_node


def schedule_task(nodes: List[Dict[str, Any]], requirement: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行调度决策，选择最优算力节点

    Args:
        nodes: 可用算力节点列表
        requirement: 任务需求

    Returns:
        调度决策结果
    """
    if not nodes:
        return {"success": False, "error": "No available nodes"}

    selected_node = select_optimal_node(nodes, requirement)

    if selected_node:
        return {
            "success": True,
            "selected_node": selected_node,
            "message": f"Selected node: {selected_node}"
        }
    else:
        return {"success": False, "error": "No suitable node found"}