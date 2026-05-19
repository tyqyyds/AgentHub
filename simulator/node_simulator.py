import asyncio
import random
from typing import Dict, Any
from fastapi import FastAPI
import uvicorn

class NodeSimulator:
    """
    算力节点模拟器
    
    模拟真实算力节点的行为，包括：
    - 任务接收和执行
    - 资源状态管理
    - 遥测数据采集
    """
    
    def __init__(self, node_id: str, region: str, node_type: str = "cpu"):
        self.node_id = node_id
        self.region = region
        self.node_type = node_type
        
        # 资源配置
        self.total_cpu = 16 if node_type == "cpu" else 32
        self.total_memory = 32 * 1024 if node_type == "cpu" else 128 * 1024
        self.total_gpu = 0 if node_type == "cpu" else 4
        
        # 当前状态
        self.current_cpu = self.total_cpu
        self.current_memory = self.total_memory
        self.current_gpu = self.total_gpu
        self.current_load = 0.0
        
        # 任务队列
        self.tasks = {}
        
        # 运行状态
        self.status = "online"
        
    def get_status(self) -> Dict[str, Any]:
        """获取节点状态"""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "region": self.region,
            "available_cpu": self.current_cpu,
            "available_memory": self.current_memory,
            "gpu_count": self.current_gpu,
            "current_load": self.current_load,
            "status": self.status
        }
    
    def submit_task(self, task_config: Dict[str, Any]) -> Dict[str, Any]:
        """提交任务"""
        required_cpu = task_config.get("required_cpu", 1)
        required_memory = task_config.get("required_memory", 1024)
        required_gpu = task_config.get("required_gpu", 0)
        
        if self.status != "online":
            return {"error": "Node is offline", "status": "failed"}
        
        if required_cpu > self.current_cpu:
            return {"error": "Insufficient CPU resources", "status": "failed"}
        
        if required_memory > self.current_memory:
            return {"error": "Insufficient memory", "status": "failed"}
        
        if required_gpu > self.current_gpu:
            return {"error": "Insufficient GPU resources", "status": "failed"}
        
        # 分配资源
        self.current_cpu -= required_cpu
        self.current_memory -= required_memory
        self.current_gpu -= required_gpu
        self.current_load = 1 - (self.current_cpu / self.total_cpu)
        
        # 创建任务
        task_id = f"task_{self.node_id}_{len(self.tasks) + 1}"
        self.tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "config": task_config,
            "progress": 0
        }
        
        return {
            "task_id": task_id,
            "node_id": self.node_id,
            "status": "submitted",
            "message": f"Task submitted to {self.node_id}"
        }
    
    def update_task_progress(self):
        """更新任务进度（模拟）"""
        completed_tasks = []
        
        for task_id, task in self.tasks.items():
            if task["status"] == "running":
                task["progress"] += random.randint(5, 20)
                
                if task["progress"] >= 100:
                    task["status"] = "completed"
                    completed_tasks.append(task_id)
                    
                    # 释放资源
                    config = task["config"]
                    self.current_cpu += config.get("required_cpu", 1)
                    self.current_memory += config.get("required_memory", 1024)
                    self.current_gpu += config.get("required_gpu", 0)
                    self.current_load = 1 - (self.current_cpu / self.total_cpu)
        
        # 清理已完成任务
        for task_id in completed_tasks:
            del self.tasks[task_id]
    
    async def simulate(self, interval: int = 1):
        """启动模拟循环"""
        while self.status == "online":
            self.update_task_progress()
            await asyncio.sleep(interval)


# FastAPI应用
app = FastAPI(title="算力节点模拟器")
simulator = None

@app.post("/api/task")
async def submit_task(task_config: Dict[str, Any]):
    """接收任务提交"""
    if not simulator:
        return {"error": "Simulator not initialized", "status": "failed"}
    
    return simulator.submit_task(task_config)

@app.get("/api/status")
async def get_status():
    """获取节点状态"""
    if not simulator:
        return {"error": "Simulator not initialized"}
    
    return simulator.get_status()

@app.get("/api/tasks")
async def get_tasks():
    """获取任务列表"""
    if not simulator:
        return {"error": "Simulator not initialized"}
    
    return {"tasks": list(simulator.tasks.values())}

@app.post("/api/shutdown")
async def shutdown():
    """关闭模拟器"""
    global simulator
    if simulator:
        simulator.status = "offline"
    return {"message": "Simulator shutdown"}


def start_simulator(node_id: str, region: str, node_type: str = "cpu", port: int = 8080):
    """启动节点模拟器"""
    global simulator
    simulator = NodeSimulator(node_id, region, node_type)
    
    # 启动模拟循环
    import threading
    def run_simulation():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(simulator.simulate())
    
    thread = threading.Thread(target=run_simulation, daemon=True)
    thread.start()
    
    # 启动FastAPI服务器
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="算力节点模拟器")
    parser.add_argument("--node-id", required=True, help="节点ID")
    parser.add_argument("--region", required=True, help="节点地域")
    parser.add_argument("--type", default="cpu", choices=["cpu", "gpu", "edge"], help="节点类型")
    parser.add_argument("--port", type=int, default=8080, help="服务端口")
    
    args = parser.parse_args()
    start_simulator(args.node_id, args.region, args.type, args.port)