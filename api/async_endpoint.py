"""
FastAPI 异步流式端点 - 实时传输 LangGraph 工作流输出

使用 WebSocket 实现异步流式输出，避免阻塞主线程
- 重连机制
- 数据过滤（仅发送变化的数据）
- 心跳检测
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain_core.runnables import RunnableConfig
from typing import Dict, Any, Optional
import json
import asyncio
import time

# 延迟导入避免循环依赖
app = FastAPI(title="工作流异步流式服务")

# 心跳配置
HEARTBEAT_INTERVAL = 30
HEARTBEAT_TIMEOUT = 10


@app.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 端点 - 将 LangGraph 的流式输出实时发送给前端
    
    特性：
    - 重连机制：客户端自动重连
    - 数据过滤：仅发送变化的数据
    - 心跳检测：保持连接活跃
    """
    await websocket.accept()
    
    last_sent_data = {}
    heartbeat_task = None
    
    async def send_heartbeat():
        """定时发送心跳消息"""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await websocket.send_json({
                    "node_name": "heartbeat",
                    "output": {"timestamp": time.time()},
                    "status": "alive"
                })
            except:
                break
    
    try:
        data = await websocket.receive_json()
        
        user_intent = data.get("user_intent", "")
        thread_id = data.get("thread_id", f"thread_{int(time.time())}")
        
        if not user_intent:
            await websocket.send_json({
                "node_name": "error",
                "output": {"error": "user_intent is required"},
                "status": "failed"
            })
            return
        
        initial_state = {
            "user_intent": user_intent,
            "structured_requirement": None,
            "available_resources": [],
            "candidate_nodes": [],
            "scheduled_node": None,
            "task_id": None,
            "verification_result": None,
            "retry_count": 0,
            "failed_nodes": [],
            "messages": []
        }
        
        config = RunnableConfig(configurable={"thread_id": thread_id})
        
        from workflow.graph import app as langgraph_app
        
        heartbeat_task = asyncio.create_task(send_heartbeat())
        
        async for event in langgraph_app.astream(initial_state, config):
            for node_name, output in event.items():
                event_data = {
                    "node_name": node_name,
                    "output": {},
                    "status": output.get("execution_status", "completed")
                }
                
                changed = False
                
                if output.get("structured_requirement"):
                    new_req = {
                        "task_type": output["structured_requirement"].get("task_type"),
                        "compute_type": output["structured_requirement"].get("compute_type"),
                        "region": output["structured_requirement"].get("region")
                    }
                    if new_req != last_sent_data.get("structured_requirement"):
                        event_data["output"]["structured_requirement"] = new_req
                        last_sent_data["structured_requirement"] = new_req
                        changed = True
                
                if output.get("available_resources"):
                    new_resources = output["available_resources"]
                    if new_resources != last_sent_data.get("available_resources"):
                        event_data["output"]["available_resources"] = new_resources
                        last_sent_data["available_resources"] = new_resources
                        changed = True
                
                if output.get("candidate_nodes"):
                    new_candidates = output["candidate_nodes"]
                    if new_candidates != last_sent_data.get("candidate_nodes"):
                        event_data["output"]["candidate_nodes"] = new_candidates
                        last_sent_data["candidate_nodes"] = new_candidates
                        changed = True
                
                if output.get("scheduled_node"):
                    new_scheduled = output["scheduled_node"]
                    if new_scheduled != last_sent_data.get("scheduled_node"):
                        event_data["output"]["scheduled_node"] = new_scheduled
                        last_sent_data["scheduled_node"] = new_scheduled
                        changed = True
                
                if output.get("task_id"):
                    new_task_id = output["task_id"]
                    if new_task_id != last_sent_data.get("task_id"):
                        event_data["output"]["task_id"] = new_task_id
                        last_sent_data["task_id"] = new_task_id
                        changed = True
                
                if output.get("verification_result"):
                    new_result = output["verification_result"]
                    if new_result != last_sent_data.get("verification_result"):
                        event_data["output"]["verification_result"] = new_result
                        last_sent_data["verification_result"] = new_result
                        changed = True
                
                if changed and event_data["output"]:
                    await websocket.send_json(event_data)
    
    except WebSocketDisconnect:
        print("WebSocket connection closed by client")
    except json.JSONDecodeError:
        await websocket.send_json({
            "node_name": "error",
            "output": {"error": "Invalid JSON format"},
            "status": "failed"
        })
    except Exception as e:
        await websocket.send_json({
            "node_name": "error",
            "output": {"error": str(e)},
            "status": "failed"
        })
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
        await websocket.close()


@app.websocket("/stream")
async def stream_workflow(websocket: WebSocket):
    """兼容旧版本的 WebSocket 流式端点"""
    await websocket_endpoint(websocket)


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "running", "service": "workflow-streaming"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)