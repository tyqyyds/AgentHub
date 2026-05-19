"""
算力节点模拟器 - FastAPI服务

模拟真实算力节点的行为，支持：
- 节点状态查询 (/status)
- 任务提交 (/submit_task)
- 数据用随机数模拟，具有真实感
- 端口从环境变量读取，方便启动多个实例
"""

import os
import random
import time
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 从环境变量读取配置
NODE_ID = os.getenv("NODE_ID", "node-sim-001")
NODE_REGION = os.getenv("NODE_REGION", "beijing")
NODE_TYPE = os.getenv("NODE_TYPE", "cpu")  # cpu, gpu, edge
PORT = int(os.getenv("NODE_PORT", 8080))

app = FastAPI(
    title=f"算力节点模拟器 - {NODE_ID}",
    description=f"模拟{NODE_TYPE}类型算力节点，位于{NODE_REGION}地区"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 节点配置（根据节点类型设置不同参数）
NODE_CONFIG = {
    "cpu": {
        "total_cpu": 64,
        "total_memory": 256 * 1024,  # MB
        "gpu_count": 0,
        "gpu_type": None,
        "total_gpu_memory": 0,
    },
    "gpu": {
        "total_cpu": 32,
        "total_memory": 128 * 1024,
        "gpu_count": 4,
        "gpu_type": "NVIDIA A100",
        "total_gpu_memory": 80 * 1024,  # MB per GPU
    },
    "edge": {
        "total_cpu": 8,
        "total_memory": 16 * 1024,
        "gpu_count": 0,
        "gpu_type": None,
        "total_gpu_memory": 0,
    }
}

config = NODE_CONFIG.get(NODE_TYPE, NODE_CONFIG["cpu"])

# 节点状态（模拟动态变化）
node_state = {
    "cpu_usage": random.uniform(20, 80),
    "memory_used": random.uniform(config["total_memory"] * 0.2, config["total_memory"] * 0.7),
    "gpu_memory_used": 0,
    "network_latency_ms": random.uniform(10, 50),
    "status": "online",
    "running_tasks": []
}

# 任务ID计数器
task_counter = 0


class TaskConfig(BaseModel):
    """任务配置模型"""
    task_type: str = Field(..., description="任务类型：training/inference/data_processing")
    required_cpu: int = Field(1, ge=1, description="所需CPU核心数")
    required_memory: int = Field(1024, ge=1024, description="所需内存(MB)")
    required_gpu: int = Field(0, ge=0, description="所需GPU数量")
    data_size_mb: Optional[int] = Field(100, description="数据大小(MB)")
    priority: str = Field("normal", description="任务优先级：low/normal/high")


class TaskResponse(BaseModel):
    """任务提交响应模型"""
    task_id: str = Field(..., description="任务ID")
    node_id: str = Field(..., description="节点ID")
    status: str = Field(..., description="任务状态：submitted/running/completed/failed")
    message: str = Field(..., description="响应消息")


class StatusResponse(BaseModel):
    """节点状态响应模型"""
    node_id: str = Field(..., description="节点ID")
    node_type: str = Field(..., description="节点类型")
    region: str = Field(..., description="节点地域")
    status: str = Field(..., description="节点状态")
    cpu_usage: float = Field(..., description="CPU利用率(%)")
    total_cpu: int = Field(..., description="总CPU核心数")
    memory_used: float = Field(..., description="已用内存(MB)")
    total_memory: float = Field(..., description="总内存(MB)")
    gpu_count: int = Field(..., description="GPU数量")
    gpu_type: Optional[str] = Field(None, description="GPU类型")
    gpu_memory_used: float = Field(..., description="已用显存(MB)")
    total_gpu_memory: float = Field(..., description="总显存(MB)")
    network_latency_ms: float = Field(..., description="网络延迟(ms)")
    running_tasks: int = Field(..., description="运行中任务数")


def update_state():
    """更新节点状态（模拟真实变化）"""
    global node_state
    
    # CPU利用率在20-80%之间波动
    node_state["cpu_usage"] = max(20, min(80, 
        node_state["cpu_usage"] + random.uniform(-5, 5)
    ))
    
    # 内存使用在20-70%之间波动
    target_memory = random.uniform(config["total_memory"] * 0.2, config["total_memory"] * 0.7)
    node_state["memory_used"] = node_state["memory_used"] + (target_memory - node_state["memory_used"]) * 0.1
    
    # GPU显存使用（仅GPU节点）
    if config["gpu_count"] > 0:
        node_state["gpu_memory_used"] = max(0, min(
            config["gpu_count"] * config["total_gpu_memory"],
            node_state["gpu_memory_used"] + random.uniform(-100, 100)
        ))
    
    # 网络延迟在10-100ms之间波动
    node_state["network_latency_ms"] = max(10, min(100,
        node_state["network_latency_ms"] + random.uniform(-5, 5)
    ))


@app.get("/status", response_model=StatusResponse, summary="获取节点状态")
async def get_status():
    """
    获取算力节点的实时状态信息
    """
    update_state()
    
    return {
        "node_id": NODE_ID,
        "node_type": NODE_TYPE,
        "region": NODE_REGION,
        "status": node_state["status"],
        "cpu_usage": round(node_state["cpu_usage"], 2),
        "total_cpu": config["total_cpu"],
        "memory_used": round(node_state["memory_used"], 2),
        "total_memory": config["total_memory"],
        "gpu_count": config["gpu_count"],
        "gpu_type": config["gpu_type"],
        "gpu_memory_used": round(node_state["gpu_memory_used"], 2),
        "total_gpu_memory": config["gpu_count"] * config["total_gpu_memory"],
        "network_latency_ms": round(node_state["network_latency_ms"], 2),
        "running_tasks": len(node_state["running_tasks"])
    }


@app.post("/submit_task", response_model=TaskResponse, summary="提交任务")
async def submit_task(task: TaskConfig):
    """
    向算力节点提交计算任务
    
    参数：
    - task_type: 任务类型（training/inference/data_processing）
    - required_cpu: 所需CPU核心数
    - required_memory: 所需内存(MB)
    - required_gpu: 所需GPU数量
    - data_size_mb: 数据大小(MB)
    - priority: 任务优先级
    """
    global task_counter
    
    # 检查节点状态
    if node_state["status"] != "online":
        raise HTTPException(status_code=503, detail="节点当前不可用")
    
    # 检查资源是否足够
    if task.required_cpu > config["total_cpu"] * (1 - node_state["cpu_usage"] / 100):
        raise HTTPException(status_code=400, detail="CPU资源不足")
    
    if task.required_memory > (config["total_memory"] - node_state["memory_used"]):
        raise HTTPException(status_code=400, detail="内存资源不足")
    
    if task.required_gpu > config["gpu_count"]:
        raise HTTPException(status_code=400, detail="GPU资源不足")
    
    # 创建任务
    task_counter += 1
    task_id = f"task-{NODE_ID}-{task_counter}-{int(time.time())}"
    
    # 更新节点状态（模拟任务占用资源）
    node_state["cpu_usage"] = min(95, node_state["cpu_usage"] + task.required_cpu * 5)
    node_state["memory_used"] = min(config["total_memory"] * 0.9, 
                                    node_state["memory_used"] + task.required_memory)
    if task.required_gpu > 0:
        node_state["gpu_memory_used"] = min(config["gpu_count"] * config["total_gpu_memory"] * 0.9,
                                            node_state["gpu_memory_used"] + task.required_memory)
    
    # 添加到运行任务列表
    node_state["running_tasks"].append({
        "task_id": task_id,
        "task_type": task.task_type,
        "submit_time": time.time(),
        "status": "running"
    })
    
    return {
        "task_id": task_id,
        "node_id": NODE_ID,
        "status": "submitted",
        "message": f"任务已提交到节点 {NODE_ID}"
    }


@app.get("/tasks", summary="获取任务列表")
async def get_tasks():
    """
    获取节点上正在运行的任务列表
    """
    return {
        "node_id": NODE_ID,
        "running_tasks": node_state["running_tasks"],
        "total_count": len(node_state["running_tasks"])
    }


@app.delete("/tasks/{task_id}", summary="取消任务")
async def cancel_task(task_id: str):
    """
    取消指定的任务
    """
    task_index = None
    for i, task in enumerate(node_state["running_tasks"]):
        if task["task_id"] == task_id:
            task_index = i
            break
    
    if task_index is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    removed_task = node_state["running_tasks"].pop(task_index)
    
    # 释放资源（模拟）
    node_state["cpu_usage"] = max(20, node_state["cpu_usage"] - 10)
    node_state["memory_used"] = max(config["total_memory"] * 0.2, 
                                    node_state["memory_used"] - 1024)
    
    return {
        "task_id": task_id,
        "status": "cancelled",
        "message": f"任务 {task_id} 已取消"
    }


@app.get("/", summary="健康检查")
async def health_check():
    """
    健康检查接口
    """
    return {
        "node_id": NODE_ID,
        "node_type": NODE_TYPE,
        "region": NODE_REGION,
        "status": "healthy"
    }


if __name__ == "__main__":
    print(f"🚀 启动算力节点模拟器 {NODE_ID}")
    print(f"📍 节点类型: {NODE_TYPE}")
    print(f"🌍 节点地域: {NODE_REGION}")
    print(f"🔌 监听端口: {PORT}")
    print("=" * 50)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )