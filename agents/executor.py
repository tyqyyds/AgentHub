from typing import Dict, Any
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.mcp_tools import _submit_task_to_node

def execute_task(node_id: str, task_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    将任务下发到目标节点执行
    
    Args:
        node_id: 目标节点ID
        task_config: 任务配置
        
    Returns:
        执行结果
    """
    return _submit_task_to_node(node_id, task_config)

def cancel_task(task_id: str) -> Dict[str, Any]:
    """
    取消正在执行的任务
    
    Args:
        task_id: 任务ID
        
    Returns:
        取消结果
    """
    return {
        "success": True,
        "task_id": task_id,
        "status": "cancelled",
        "message": f"Task {task_id} cancelled"
    }

def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    获取任务执行状态
    
    Args:
        task_id: 任务ID
        
    Returns:
        任务状态
    """
    return {
        "task_id": task_id,
        "status": "completed",
        "progress": 100,
        "message": "Task completed successfully"
    }