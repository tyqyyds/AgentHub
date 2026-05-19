from typing import List, Dict, Optional, Any
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.mcp_tools import _query_compute_nodes

def discover_resources(region: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    发现网络中的可用算力节点
    
    Args:
        region: 地域筛选条件（如"beijing"、"shanghai"），为空则返回全部
        
    Returns:
        算力节点列表
    """
    return _query_compute_nodes(region)

def get_node_details(node_id: str) -> Optional[Dict[str, Any]]:
    """
    获取指定节点的详细信息
    
    Args:
        node_id: 节点ID
        
    Returns:
        节点详细信息，未找到返回None
    """
    nodes = _query_compute_nodes()
    for node in nodes:
        if node.get("node_id") == node_id:
            return node
    return None

def filter_nodes_by_requirements(
    nodes: List[Dict[str, Any]],
    required_cpu: int = 0,
    required_memory: int = 0,
    required_gpu: int = 0
) -> List[Dict[str, Any]]:
    """
    根据资源需求筛选节点
    
    Args:
        nodes: 节点列表
        required_cpu: 所需CPU核心数
        required_memory: 所需内存(MB)
        required_gpu: 所需GPU数量
        
    Returns:
        满足需求的节点列表
    """
    filtered = []
    for node in nodes:
        if (node.get("available_cpu", 0) >= required_cpu and
            node.get("available_memory", 0) >= required_memory and
            node.get("gpu_count", 0) >= required_gpu and
            node.get("status") == "online"):
            filtered.append(node)
    return filtered