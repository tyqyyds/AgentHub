from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from ..agents import (
    parse_intent,
    discover_resources,
    schedule_task,
    execute_task,
    verify_intent_achieved,
    collect_telemetry
)
from ..workflow.graph import execute_workflow

router = APIRouter()

@router.post("/intent/parse")
async def parse_intent_endpoint(request: Dict[str, Any]):
    """解析用户意图"""
    user_intent = request.get("user_intent")
    if not user_intent:
        raise HTTPException(status_code=400, detail="user_intent is required")
    
    try:
        result = parse_intent(user_intent)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/resources")
async def get_resources(region: str = None):
    """获取可用算力节点"""
    try:
        resources = discover_resources(region)
        return {"success": True, "data": resources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/resources/{node_id}")
async def get_node_details(node_id: str):
    """获取指定节点详细信息"""
    try:
        resources = discover_resources()
        node = next((n for n in resources if n["node_id"] == node_id), None)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        return {"success": True, "data": node}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schedule")
async def schedule_endpoint(request: Dict[str, Any]):
    """执行调度决策"""
    resources = request.get("resources", [])
    requirement = request.get("requirement", {})
    
    try:
        result = schedule_task(resources, requirement)
        return {"success": result["success"], "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/execute")
async def execute_endpoint(request: Dict[str, Any]):
    """执行任务"""
    node_id = request.get("node_id")
    task_config = request.get("task_config", {})
    
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id is required")
    
    try:
        result = execute_task(node_id, task_config)
        return {"success": result.get("status") == "submitted", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verify")
async def verify_endpoint(request: Dict[str, Any]):
    """验证意图达成"""
    user_intent = request.get("user_intent")
    execution_result = request.get("execution_result", {})
    
    if not user_intent:
        raise HTTPException(status_code=400, detail="user_intent is required")
    
    try:
        achieved = verify_intent_achieved(user_intent, execution_result)
        return {"success": True, "data": {"intent_achieved": achieved}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/telemetry/{node_id}")
async def get_telemetry(node_id: str):
    """获取节点遥测数据"""
    try:
        telemetry = collect_telemetry(node_id)
        return {"success": True, "data": telemetry}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/workflow/execute")
async def execute_workflow_endpoint(request: Dict[str, Any]):
    """执行完整调度工作流"""
    user_intent = request.get("user_intent")
    
    if not user_intent:
        raise HTTPException(status_code=400, detail="user_intent is required")
    
    try:
        result = execute_workflow(user_intent)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))