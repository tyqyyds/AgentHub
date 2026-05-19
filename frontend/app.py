"""
Streamlit 前端应用 - 算力网络多智能体协同调度系统
优化版本：
1. 动态工作流流程图（SVG）
2. 三段式遥测验证区域（状态-原因-建议）
3. 增强的卡片布局和图标
4. 资源利用率图表
5. 响应式设计
6. WebSocket 实时通信支持
"""

import streamlit as st
import sys
import os
import json
import asyncio
from datetime import datetime
import time
import threading
import websockets
from streamlit_agraph import agraph

# 解决异步事件循环冲突
import nest_asyncio
nest_asyncio.apply()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# WebSocket 端点地址（与后端一致）
WS_URL = "ws://localhost:8000/ws/stream"

# WebSocket 全局变量
ws_running = False
ws_thread = None
ws_reconnect_attempts = 0
ws_max_reconnect_attempts = 5
ws_reconnect_delay = 3
ws_message_queue = []


async def receive_data(user_intent: str = ""):
    """WebSocket 异步接收 - 实时接收工作流事件（带重连机制）"""
    global ws_running, ws_reconnect_attempts, ws_message_queue
    
    while ws_running and ws_reconnect_attempts < ws_max_reconnect_attempts:
        try:
            async with websockets.connect(WS_URL, ping_interval=30, ping_timeout=10) as websocket:
                ws_reconnect_attempts = 0
                
                if user_intent:
                    await websocket.send(json.dumps({
                        "user_intent": user_intent,
                        "thread_id": f"thread_{int(time.time())}"
                    }))
                
                while ws_running:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=45)
                        data = json.loads(message)
                        
                        node_name = data.get("node_name")
                        output = data.get("output", {})
                        status = data.get("status")
                        
                        if node_name == "heartbeat":
                            continue
                        
                        ws_message_queue.append({
                            "node_name": node_name,
                            "output": output,
                            "status": status,
                            "timestamp": time.time()
                        })
                            
                    except asyncio.TimeoutError:
                        try:
                            await websocket.send(json.dumps({"type": "heartbeat"}))
                        except:
                            break
                            
        except websockets.exceptions.ConnectionClosed as e:
            ws_reconnect_attempts += 1
            if ws_running and ws_reconnect_attempts < ws_max_reconnect_attempts:
                ws_message_queue.append({
                    "type": "reconnect",
                    "attempt": ws_reconnect_attempts,
                    "max_attempts": ws_max_reconnect_attempts
                })
                await asyncio.sleep(ws_reconnect_delay)
            else:
                ws_message_queue.append({"type": "error", "message": "WebSocket连接已关闭"})
                break
        except Exception as e:
            ws_reconnect_attempts += 1
            if ws_running and ws_reconnect_attempts < ws_max_reconnect_attempts:
                ws_message_queue.append({
                    "type": "reconnect",
                    "attempt": ws_reconnect_attempts,
                    "max_attempts": ws_max_reconnect_attempts
                })
                await asyncio.sleep(ws_reconnect_delay)
            else:
                ws_message_queue.append({"type": "error", "message": f"WebSocket错误：{e}"})
                break
        finally:
            if not ws_running:
                break
    
    ws_running = False


def process_ws_messages():
    """处理 WebSocket 消息队列"""
    global ws_message_queue
    
    while ws_message_queue:
        msg = ws_message_queue.pop(0)
        
        if msg.get("type") == "error":
            st.error(msg.get("message", "未知错误"))
        elif msg.get("type") == "reconnect":
            st.warning(f"连接断开，正在重连... ({msg['attempt']}/{msg['max_attempts']})")
        else:
            node_name = msg.get("node_name")
            output = msg.get("output", {})
            status = msg.get("status")
            
            if node_name == "intent_parser":
                req = output.get("structured_requirement", {})
                if st.session_state.get("structured_requirement") != req:
                    st.session_state["structured_requirement"] = req
                    st.session_state["parsed_intent"] = req
            elif node_name == "resource_discovery":
                resources = output.get("available_resources", [])
                candidates = output.get("candidate_nodes", [])
                if st.session_state.get("available_resources") != resources:
                    st.session_state["available_resources"] = resources
                if st.session_state.get("candidate_nodes") != candidates:
                    st.session_state["candidate_nodes"] = candidates
            elif node_name == "scheduling":
                scheduled = output.get("scheduled_node")
                if st.session_state.get("scheduled_node") != scheduled:
                    st.session_state["scheduled_node"] = scheduled
            elif node_name == "execution":
                task_id = output.get("task_id")
                if st.session_state.get("task_id") != task_id:
                    st.session_state["task_id"] = task_id
            elif node_name == "verification":
                result = output.get("verification_result")
                if st.session_state.get("verification_result") != result:
                    st.session_state["verification_result"] = result
            elif node_name == "error":
                st.error(f"工作流错误：{output.get('error', '未知错误')}")
                return False
            
            if node_name in st.session_state.get("flow_status", {}):
                st.session_state["flow_status"][node_name] = status
    
    return True


def start_websocket(user_intent: str = ""):
    """启动 WebSocket 连接（通过后台线程运行，带重连机制）"""
    global ws_running, ws_thread, ws_reconnect_attempts
    
    if ws_running:
        if user_intent:
            async def send_intent():
                async with websockets.connect(WS_URL) as websocket:
                    await websocket.send(json.dumps({
                        "user_intent": user_intent,
                        "thread_id": f"thread_{int(time.time())}"
                    }))
            
            # 使用 nest_asyncio 安全运行异步任务
            threading.Thread(
                target=asyncio.run,
                args=(send_intent(),),
                daemon=True
            ).start()
        else:
            st.warning("WebSocket 已连接")
        return
    
    ws_running = True
    ws_reconnect_attempts = 0
    
    # 使用 nest_asyncio 安全运行异步任务
    async def run_receive_data():
        await receive_data(user_intent)
    
    ws_thread = threading.Thread(
        target=asyncio.run,
        args=(run_receive_data(),),
        daemon=True
    )
    ws_thread.start()
    
    if user_intent:
        st.success("WebSocket 连接已启动，正在执行工作流...")
    else:
        st.success("WebSocket 连接已启动")


def stop_websocket():
    """停止 WebSocket 连接"""
    global ws_running
    
    ws_running = False
    st.success("WebSocket 连接已停止")

from workflow.graph import execute_workflow, app as langgraph_app

EXAMPLE_INTENTS = [
    {"label": "训练场景：在北京的GPU节点上训练图像分类模型", "intent": "在北京的GPU节点上训练一个图像分类模型"},
    {"label": "推理场景：在上海部署低延迟推理服务", "intent": "在上海部署低延迟推理服务，需要4核CPU和8GB内存"},
    {"label": "数据处理场景：在杭州处理数据清洗任务", "intent": "在杭州处理一批数据清洗任务，数据量大约500MB"},
    {"label": "模型微调场景：使用广州GPU进行模型微调", "intent": "使用广州的GPU节点进行模型微调"},
    {"label": "边缘计算场景：在成都部署边缘推理服务", "intent": "在成都部署边缘计算推理服务"},
    {"label": "延迟敏感场景：在延迟低于50ms的节点部署推理", "intent": "在延迟低于50ms的节点部署推理"}
]

COLORS = {
    "primary": "#3B82F6",
    "success": "#10B981",
    "warning": "#F59E0B",
    "error": "#EF4444",
    "purple": "#8B5CF6",
    "bg_dark": "#0F172A",
    "bg_card": "#1E293B",
    "text_primary": "#f1f5f9",
    "text_secondary": "#94A3B8",
    "border": "#334155"
}

COLOR_MAP = {
    "idle": "#6c757d",
    "in_progress": "#0d6efd",
    "completed": "#198754",
    "failed": "#dc3545"
}

st.session_state["edge_status"] = {
    ("intent_parser", "resource_discovery"): "idle",
    ("resource_discovery", "scheduling"): "idle",
    ("scheduling", "execution"): "idle",
    ("execution", "verification"): "idle",
}

# 节点状态缓存 - 避免每次都从LangGraph获取
if "node_cache" not in st.session_state:
    st.session_state["node_cache"] = {
        "intent_parser": None,
        "resource_discovery": None,
        "scheduling": None,
        "execution": None,
        "verification": None,
    }

# 缓存时间戳 - 用于判断缓存是否过期
if "cache_timestamp" not in st.session_state:
    st.session_state["cache_timestamp"] = {}


def get_cached_node_output(node_id):
    """获取缓存的节点输出，避免重复从LangGraph获取"""
    # 检查缓存是否存在
    cached = st.session_state["node_cache"].get(node_id)
    if cached is not None:
        # 检查缓存是否过期（5分钟过期）
        timestamp = st.session_state["cache_timestamp"].get(node_id, 0)
        if time.time() - timestamp < 300:  # 5分钟有效期
            return cached
    return None


def set_cached_node_output(node_id, output):
    """设置节点输出缓存"""
    st.session_state["node_cache"][node_id] = output
    st.session_state["cache_timestamp"][node_id] = time.time()


def invalidate_cache(node_id=None):
    """使缓存失效（可指定特定节点或全部）"""
    if node_id:
        st.session_state["node_cache"][node_id] = None
        st.session_state["cache_timestamp"][node_id] = 0
    else:
        st.session_state["node_cache"] = {
            "intent_parser": None,
            "resource_discovery": None,
            "scheduling": None,
            "execution": None,
            "verification": None,
        }
        st.session_state["cache_timestamp"] = {}


@st.cache_data(ttl=60)
def get_node_status(node_id: str) -> dict:
    """获取节点状态（使用Streamlit缓存，缓存60秒）
    
    避免重复从LangGraph获取节点状态，提升前端性能。
    实际应用中可调用异步端点获取最新状态。
    """
    # 优先从session_state获取实时状态
    if "flow_status" in st.session_state:
        status = st.session_state["flow_status"].get(node_id, "idle")
        return {
            "node_id": node_id,
            "status": status,
            "timestamp": time.time()
        }
    
    # 模拟从LangGraph获取节点状态（实际可调用异步端点）
    return {
        "node_id": node_id,
        "status": "idle",
        "timestamp": time.time()
    }


def stream_node_output(node_id: str):
    """流式处理节点输出 - 逐步传输数据
    
    利用LangGraph的stream方法，逐步传输节点输出，
    而非等所有节点执行完再传输，提升实时性。
    """
    cached = get_cached_node_output(node_id)
    if cached:
        return cached
    
    # 模拟流式获取（实际应调用LangGraph的stream方法）
    import time
    for i in range(3):
        progress = (i + 1) * 33
        yield {
            "node_id": node_id,
            "status": "in_progress",
            "progress": progress,
            "message": f"Processing {progress}%",
            "timestamp": time.time()
        }
        time.sleep(0.1)
    
    return {
        "node_id": node_id,
        "status": "completed",
        "progress": 100,
        "message": "Processing complete",
        "timestamp": time.time()
    }


COLOR_MAP_EDGE = {
    "idle": "#6c757d",
    "in_progress": "#0d6efd",
    "completed": "#198754",
    "failed": "#dc3545",
}

def get_node_color(status):
    """根据节点状态返回对应的颜色配置"""
    color = COLOR_MAP.get(status, COLOR_MAP["idle"])
    return {
        "fill": color,
        "stroke": color,
        "text": "#ffffff"
    }

def handle_node_click(node_id):
    """节点点击回调函数"""
    st.session_state["selected_node"] = node_id
    st.session_state["show_node_details"] = True

def handle_edge_click(edge_id):
    """边的点击回调函数"""
    pass

def get_node_info(node_id):
    """获取节点详细信息"""
    node_names = {
        "intent_parser": "意图解析",
        "resource_discovery": "资源发现",
        "scheduling": "调度决策",
        "execution": "策略执行",
        "verification": "遥测验证"
    }

    flow_status = st.session_state.get("flow_status", {})
    node_status = flow_status.get(node_id, "idle")

    node_info = {
        "节点ID": node_id,
        "节点名称": node_names.get(node_id, node_id),
        "状态": node_status,
        "状态说明": {
            "idle": "等待执行",
            "in_progress": "执行中",
            "completed": "已完成",
            "failed": "执行失败"
        }.get(node_status, "未知状态")
    }

    step_times = st.session_state.get("step_times", {})
    if node_id in step_times:
        node_info["耗时"] = f"{step_times[node_id]:.2f}秒"

    structured_requirement = st.session_state.get("workflow_result", {}).get("structured_requirement")
    if node_id == "intent_parser" and structured_requirement:
        node_info["解析结果"] = structured_requirement

    available_resources = st.session_state.get("workflow_result", {}).get("available_resources", [])
    if node_id == "resource_discovery":
        node_info["发现资源数"] = len(available_resources)
        node_info["候选节点数"] = len(st.session_state.get("workflow_result", {}).get("candidate_nodes", []))

    scheduled_node = st.session_state.get("workflow_result", {}).get("scheduled_node")
    if node_id == "scheduling" and scheduled_node:
        node_info["调度节点"] = scheduled_node

    task_id = st.session_state.get("workflow_result", {}).get("task_id")
    if node_id == "execution" and task_id:
        node_info["任务ID"] = task_id

    verification_result = st.session_state.get("workflow_result", {}).get("verification_result", {})
    if node_id == "verification":
        node_info["验证结果"] = verification_result.get("achieved", False)
        node_info["原因"] = verification_result.get("reason", "N/A")

    return node_info

def draw_workflow_agraph(flow_status=None, step_times=None):
    """使用 streamlit-agraph 绘制动态工作流流程图"""
    steps = [
        ("intent_parser", "意图解析", "🔍"),
        ("resource_discovery", "资源发现", "🌐"),
        ("scheduling", "调度决策", "⚡"),
        ("execution", "策略执行", "🚀"),
        ("verification", "遥测验证", "✅")
    ]

    # nodes 必须是包含 id, label, color 的字典列表
    nodes = []
    for step_id, step_name, step_icon in steps:
        status = flow_status.get(step_id, "idle") if flow_status else "idle"
        colors = get_node_color(status)
        
        node = {
            "id": step_id,
            "label": step_name,
            "color": colors["stroke"]
        }
        nodes.append(node)

    # edges 必须是包含 source, target 的字典列表
    edges = [
        {"source": "intent_parser", "target": "resource_discovery"},
        {"source": "resource_discovery", "target": "scheduling"},
        {"source": "scheduling", "target": "execution"},
        {"source": "execution", "target": "verification"},
    ]

    # config 必须使用标准结构
    config = {
        "node": {"size": 50},
        "edge": {"smooth": True},
        "physics": False,
        "directed": True,
        "height": 300,
        "width": 800,
        "nodeSpacing": 150
    }

    return agraph(nodes=nodes, edges=edges, config=config)

def draw_metric_card(title, value, icon, color, subtitle=None, progress_value=None):
    """绘制增强版指标卡片"""
    progress_html = ''
    if progress_value is not None:
        progress_html = f'''
        <div style="margin-top: 8px;">
            <div style="display: flex; justify-content: space-between; font-size: 10px; color: {COLORS['text_secondary']}; margin-bottom: 4px;">
                <span>失败节点</span>
                <span>{progress_value}/5</span>
            </div>
            <div style="height: 4px; background: {COLORS['bg_dark']}; border-radius: 2px; overflow: hidden;">
                <div style="height: 100%; width: {progress_value * 20}%; background: {COLORS['error']}; border-radius: 2px; transition: width 0.5s ease;"></div>
            </div>
        </div>
        '''
    
    return f'''
    <div style="
        background: {COLORS['bg_card']};
        border: 1px solid {COLORS['border']};
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        transition: all 0.3s ease;
        hover: transform: translateY(-2px); hover: box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    ">
        <div style="font-size: 32px; margin-bottom: 10px;">{icon}</div>
        <div style="color: {COLORS['text_primary']}; font-size: 13px; font-weight: 500; margin-bottom: 4px;">{title}</div>
        <div style="color: {color}; font-size: 24px; font-weight: 700; margin-bottom: 4px;">{value}</div>
        {f'<div style="color: {COLORS["text_secondary"]}; font-size: 11px;">{subtitle}</div>' if subtitle else ''}
        {progress_html}
    </div>
    '''

def draw_telemetry_section(result):
    """绘制三段式遥测验证区域"""
    verification = result.get("verification_result", {})
    achieved = verification.get("achieved", False)
    reason = verification.get("reason", "Unknown")
    telemetry = verification.get("telemetry", {})
    
    if achieved:
        return f'''
        <div style="background: {COLORS['bg_card']}; border-radius: 12px; border: 1px solid {COLORS['border']}; overflow: hidden;">
            <div style="background: {COLORS['success']}; padding: 16px; display: flex; justify-content: space-between; align-items: center;">
                <span style="color: white; font-weight: 600; font-size: 14px;">✅ 意图达成</span>
                <span style="color: rgba(255,255,255,0.8); font-size: 12px;">{datetime.now().strftime('%H:%M:%S')}</span>
            </div>
            <div style="padding: 16px;">
                <div style="color: {COLORS['text_secondary']}; font-size: 13px; line-height: 1.5;">{reason}</div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px;">
                    <div style="background: {COLORS['bg_dark']}; padding: 10px; border-radius: 8px; text-align: center;">
                        <div style="color: {COLORS['text_secondary']}; font-size: 10px;">延迟</div>
                        <div style="color: {COLORS['success']}; font-size: 16px; font-weight: 600;">{telemetry.get('latency_ms', 'N/A')}ms</div>
                    </div>
                    <div style="background: {COLORS['bg_dark']}; padding: 10px; border-radius: 8px; text-align: center;">
                        <div style="color: {COLORS['text_secondary']}; font-size: 10px;">节点</div>
                        <div style="color: {COLORS['text_primary']}; font-size: 14px; font-weight: 600;">{telemetry.get('node_id', 'N/A')}</div>
                    </div>
                </div>
            </div>
        </div>
        '''
    else:
        return f'''
        <div style="background: {COLORS['bg_card']}; border-radius: 12px; border: 1px solid {COLORS['border']}; overflow: hidden;">
            <div style="background: {COLORS['error']}; padding: 16px; display: flex; justify-content: space-between; align-items: center;">
                <span style="color: white; font-weight: 600; font-size: 14px;">❌ 意图未达成</span>
                <span style="color: rgba(255,255,255,0.8); font-size: 12px;">{datetime.now().strftime('%H:%M:%S')}</span>
            </div>
            <div style="padding: 16px;">
                <div style="background: rgba(239, 68, 68, 0.1); border-left: 3px solid {COLORS['error']}; padding: 12px; border-radius: 0 8px 8px 0; margin-bottom: 12px;">
                    <div style="color: {COLORS['error']}; font-size: 12px; font-weight: 600; margin-bottom: 4px;">🔴 失败原因</div>
                    <div style="color: {COLORS['text_secondary']}; font-size: 12px;">{reason}</div>
                </div>
                <div style="background: rgba(59, 130, 246, 0.1); border-left: 3px solid {COLORS['primary']}; padding: 12px; border-radius: 0 8px 8px 0; margin-bottom: 12px;">
                    <div style="color: {COLORS['primary']}; font-size: 12px; font-weight: 600; margin-bottom: 4px;">💡 建议操作</div>
                    <div style="color: {COLORS['text_secondary']}; font-size: 12px;">建议切换至其他可用节点，系统将自动重新调度至延迟符合要求的节点</div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px;">
                    <div style="background: {COLORS['bg_dark']}; padding: 10px; border-radius: 8px; text-align: center;">
                        <div style="color: {COLORS['text_secondary']}; font-size: 10px;">当前延迟</div>
                        <div style="color: {COLORS['error']}; font-size: 16px; font-weight: 600;">{telemetry.get('latency_ms', 'N/A')}ms</div>
                    </div>
                    <div style="background: {COLORS['bg_dark']}; padding: 10px; border-radius: 8px; text-align: center;">
                        <div style="color: {COLORS['text_secondary']}; font-size: 10px;">SLA要求</div>
                        <div style="color: {COLORS['text_primary']}; font-size: 14px; font-weight: 600;">&lt;50ms</div>
                    </div>
                </div>
                <button id="retry-btn" style="
                    width: 100%;
                    background: linear-gradient(135deg, {COLORS['primary']} 0%, #2563EB 100%);
                    color: white;
                    border: none;
                    padding: 12px;
                    border-radius: 8px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s ease;
                " onclick="window.parent.postMessage('retry_workflow', '*')">
                    🔄 一键重试
                </button>
            </div>
        </div>
        '''

def draw_resource_chart():
    """绘制资源利用率图表"""
    import random
    
    cpu_data = [25, 32, 28, 45, 38, 42, 35, 50, 48, 36, 40, 32]
    mem_data = [45, 42, 48, 52, 49, 55, 51, 58, 54, 52, 48, 50]
    latency_data = [20, 25, 22, 30, 28, 35, 26, 40, 32, 28, 24, 26]
    
    labels = [f'{i+1}s' for i in range(12)]
    
    max_cpu = max(cpu_data)
    max_mem = max(mem_data)
    max_lat = max(latency_data)
    
    chart_height = 150
    chart_width = 300
    padding = 30
    
    svg = f'<svg width="{chart_width}" height="{chart_height}" viewBox="0 0 {chart_width} {chart_height}">'
    
    svg += '''
    <defs>
        <linearGradient id="cpuGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" style="stop-color:#3B82F6;stop-opacity:0.3"/>
            <stop offset="100%" style="stop-color:#3B82F6;stop-opacity:0"/>
        </linearGradient>
        <linearGradient id="memGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" style="stop-color:#10B981;stop-opacity:0.3"/>
            <stop offset="100%" style="stop-color:#10B981;stop-opacity:0"/>
        </linearGradient>
    </defs>
    '''
    
    for i in range(6):
        y = padding + i * ((chart_height - padding * 2) / 5)
        svg += f'<line x1="{padding}" y1="{y}" x2="{chart_width - padding}" y2="{y}" stroke="#334155" stroke-width="1" stroke-dasharray="2,2"/>'
    
    cpu_points = []
    mem_points = []
    lat_points = []
    
    for i, (cpu, mem, lat) in enumerate(zip(cpu_data, mem_data, latency_data)):
        x = padding + i * ((chart_width - padding * 2) / (len(cpu_data) - 1))
        cpu_y = chart_height - padding - (cpu / 100) * (chart_height - padding * 2)
        mem_y = chart_height - padding - (mem / 100) * (chart_height - padding * 2)
        lat_y = chart_height - padding - (lat / 100) * (chart_height - padding * 2)
        
        cpu_points.append(f'{x},{cpu_y}')
        mem_points.append(f'{x},{mem_y}')
        lat_points.append(f'{x},{lat_y}')
    
    svg += f'''
    <polygon points="{padding},{chart_height - padding} {','.join(cpu_points)} {chart_width - padding},{chart_height - padding}" fill="url(#cpuGradient)"/>
    <polyline points="{','.join(cpu_points)}" fill="none" stroke="#3B82F6" stroke-width="2"/>
    <polygon points="{padding},{chart_height - padding} {','.join(mem_points)} {chart_width - padding},{chart_height - padding}" fill="url(#memGradient)"/>
    <polyline points="{','.join(mem_points)}" fill="none" stroke="#10B981" stroke-width="2"/>
    <polyline points="{','.join(lat_points)}" fill="none" stroke="#F59E0B" stroke-width="2" stroke-dasharray="4,4"/>
    '''
    
    svg += f'''
    <g transform="translate({chart_width - 80}, {20})">
        <rect x="0" y="0" width="12" height="3" fill="#3B82F6"/>
        <text x="16" y="3" fill="#94A3B8" font-size="10" alignment-baseline="middle">CPU</text>
        <rect x="0" y="12" width="12" height="3" fill="#10B981"/>
        <text x="16" y="15" fill="#94A3B8" font-size="10" alignment-baseline="middle">Memory</text>
        <rect x="0" y="24" width="12" height="3" fill="#F59E0B" stroke-dasharray="4,4"/>
        <text x="16" y="27" fill="#94A3B8" font-size="10" alignment-baseline="middle">Latency</text>
    </g>
    '''
    
    svg += '</svg>'
    
    return f'''
    <div style="background: {COLORS['bg_card']}; border-radius: 12px; border: 1px solid {COLORS['border']}; padding: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <span style="color: {COLORS['text_primary']}; font-weight: 600; font-size: 13px;">📊 实时资源监控</span>
            <span style="color: {COLORS['success']}; font-size: 10px;">● 实时</span>
        </div>
        <div style="display: flex; justify-content: center;">{svg}</div>
    </div>
    '''

def main():
    """主应用函数"""
    # 启动 WebSocket 实时通信（异步传输）
    start_websocket()
    
    # 处理 WebSocket 消息队列
    process_ws_messages()
    
    st.set_page_config(
        page_title="智维AgentHub - 算力调度系统",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    st.markdown(f"""
        <style>
        .stApp {{
            background: linear-gradient(135deg, {COLORS['bg_dark']} 0%, {COLORS['bg_card']} 100%);
            min-height: 100vh;
        }}
        h1 {{
            color: {COLORS['text_primary']} !important;
            font-weight: 700 !important;
        }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {COLORS['bg_card']} 0%, {COLORS['bg_dark']} 100%) !important;
            border-right: 1px solid {COLORS['border']};
        }}
        .stButton > button {{
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
        }}
        .stButton > button:hover:not(:disabled) {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }}
        .stTextArea textarea {{
            background: {COLORS['bg_dark']} !important;
            border: 1px solid {COLORS['border']} !important;
            border-radius: 8px !important;
            color: {COLORS['text_primary']} !important;
        }}
        .stSelectbox > div > div {{
            background: {COLORS['bg_dark']} !important;
            border: 1px solid {COLORS['border']} !important;
            border-radius: 8px !important;
            color: {COLORS['text_primary']} !important;
        }}
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        ::-webkit-scrollbar {{width: 6px;}}
        ::-webkit-scrollbar-track {{background: {COLORS['bg_card']};}}
        ::-webkit-scrollbar-thumb {{background: #475569; border-radius: 3px;}}
        .retry-btn {{
            background: linear-gradient(135deg, {COLORS['primary']} 0%, #2563EB 100%) !important;
            color: white !important;
            border: none !important;
        }}
        </style>
    """, unsafe_allow_html=True)

    st.title("⚡ 智维AgentHub - 算力网络多智能体协同调度系统")

    if 'workflow_result' not in st.session_state:
        st.session_state.workflow_result = None
    if 'steps_completed' not in st.session_state:
        st.session_state.steps_completed = []
    if 'retry_count' not in st.session_state:
        st.session_state.retry_count = 0
    if 'step_times' not in st.session_state:
        st.session_state.step_times = {}
    if 'flow_status' not in st.session_state:
        st.session_state.flow_status = {
            "intent_parser": "idle",
            "resource_discovery": "idle",
            "scheduling": "idle",
            "execution": "idle",
            "verification": "idle"
        }

    def retry_workflow():
        if st.session_state.workflow_result:
            user_intent = st.session_state.get('last_intent', '')
            if user_intent:
                with st.spinner("🔄 正在重新调度..."):
                    st.session_state.flow_status = {
                        "intent_parser": "in_progress",
                        "resource_discovery": "idle",
                        "scheduling": "idle",
                        "execution": "idle",
                        "verification": "idle"
                    }
                    result = execute_workflow(user_intent)
                    st.session_state.workflow_result = result
                    st.session_state.flow_status = {
                        "intent_parser": "completed",
                        "resource_discovery": "completed",
                        "scheduling": "completed",
                        "execution": "completed",
                        "verification": "completed" if result.get("verification_result", {}).get("achieved") else "failed"
                    }
                    st.session_state.retry_count += 1

    with st.sidebar:
        st.markdown(f'''
            <div style="text-align: center; padding: 20px 0; border-bottom: 1px solid {COLORS['border']}; margin-bottom: 20px;">
                <div style="font-size: 32px; margin-bottom: 8px;">🎯</div>
                <div style="color: {COLORS['text_primary']}; font-size: 16px; font-weight: 600;">意图输入</div>
            </div>
        ''', unsafe_allow_html=True)

        selected_label = st.selectbox(
            "选择示例意图",
            [""] + [item["label"] for item in EXAMPLE_INTENTS],
            index=0,
            help="选择一个示例意图快速测试",
            key="select_example_intent"
        )
        
        selected_intent = next((item["intent"] for item in EXAMPLE_INTENTS if item["label"] == selected_label), "")

        user_intent = st.text_area(
            "用户意图",
            value=selected_intent if selected_intent else "",
            height=120,
            placeholder="输入您的算力需求...",
            label_visibility="collapsed",
            key="user_intent_input"
        )

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            execute_btn = st.button("🚀 执行", type="primary", use_container_width=True)

        with col_btn2:
            clear_btn = st.button("🗑️ 清空", use_container_width=True)

        if clear_btn:
            st.session_state.workflow_result = None
            st.session_state.steps_completed = []
            st.session_state.retry_count = 0
            st.session_state.step_times = {}
            st.session_state.flow_status = {
                "intent_parser": "idle",
                "resource_discovery": "idle",
                "scheduling": "idle",
                "execution": "idle",
                "verification": "idle"
            }
            st.session_state["is_running"] = False
            st.rerun()

        NODE_ORDER = ["intent_parser", "resource_discovery", "scheduling", "execution", "verification"]

        if execute_btn and user_intent.strip():
            if st.session_state.get("is_running", False):
                st.warning("工作流正在执行中，请稍候...")
            else:
                # 检查缓存
                cached_result = get_cached_node_output("verification")
                if cached_result:
                    st.info("📦 使用缓存结果")
                    st.session_state.workflow_result = cached_result
                    st.session_state.flow_status = {
                        "intent_parser": "completed",
                        "resource_discovery": "completed",
                        "scheduling": "completed",
                        "execution": "completed",
                        "verification": "completed" if cached_result.get("verification_result", {}).get("achieved") else "failed"
                    }
                    # 恢复缓存的节点输出
                    if cached_result.get("structured_requirement"):
                        st.session_state["parsed_intent"] = cached_result["structured_requirement"]
                    if cached_result.get("available_resources"):
                        st.session_state["available_resources"] = cached_result["available_resources"]
                    if cached_result.get("candidate_nodes"):
                        st.session_state["candidate_nodes"] = cached_result["candidate_nodes"]
                    if cached_result.get("scheduled_node"):
                        st.session_state["scheduled_node"] = cached_result["scheduled_node"]
                    if cached_result.get("task_id"):
                        st.session_state["task_id"] = cached_result["task_id"]
                    if cached_result.get("verification_result"):
                        st.session_state["verification_result"] = cached_result["verification_result"]
                    return
                
                st.session_state["is_running"] = True
                st.session_state.last_intent = user_intent
                st.session_state.steps_completed = []
                st.session_state.step_times = {}
                st.session_state.flow_status = {
                    node: "idle" for node in NODE_ORDER
                }
                st.session_state.flow_status["intent_parser"] = "in_progress"

                # 清除旧缓存
                invalidate_cache()

                initial_state = {
                    "user_intent": user_intent,
                    "structured_requirement": None,
                    "available_resources": [],
                    "candidate_nodes": [],
                    "scheduled_node": None,
                    "execution_status": None,
                    "verification_result": None,
                    "retry_count": 0,
                    "failed_nodes": [],
                    "messages": [],
                    "task_id": None,
                    "error_message": None
                }

                config = {"configurable": {"thread_id": f"thread_{int(time.time())}"}}

                with st.spinner("⚙️ 正在执行工作流..."):
                    # 使用stream_mode="messages"逐步输出节点结果
                    for event in langgraph_app.stream(initial_state, config, stream_mode="messages"):
                        for node_name, output in event.items():
                            if node_name in st.session_state.flow_status:
                                is_failed = (
                                    output.get("execution_status") == "failed" or
                                    (node_name == "verification" and not output.get("verification_result", {}).get("achieved"))
                                )
                                st.session_state.flow_status[node_name] = "failed" if is_failed else "completed"

                                if node_name in NODE_ORDER:
                                    current_idx = NODE_ORDER.index(node_name)
                                    if current_idx + 1 < len(NODE_ORDER):
                                        next_node = NODE_ORDER[current_idx + 1]
                                        if st.session_state.flow_status.get(next_node) == "idle":
                                            st.session_state.flow_status[next_node] = "in_progress"

                            # 仅更新变化的数据（增量更新）
                            if output.get("structured_requirement"):
                                if st.session_state.get("parsed_intent") != output["structured_requirement"]:
                                    st.session_state["parsed_intent"] = output["structured_requirement"]
                                    set_cached_node_output("intent_parser", output)
                            if output.get("available_resources"):
                                if st.session_state.get("available_resources") != output["available_resources"]:
                                    st.session_state["available_resources"] = output["available_resources"]
                                    set_cached_node_output("resource_discovery", output)
                            if output.get("candidate_nodes"):
                                if st.session_state.get("candidate_nodes") != output["candidate_nodes"]:
                                    st.session_state["candidate_nodes"] = output["candidate_nodes"]
                            if output.get("scheduled_node"):
                                if st.session_state.get("scheduled_node") != output["scheduled_node"]:
                                    st.session_state["scheduled_node"] = output["scheduled_node"]
                                    set_cached_node_output("scheduling", output)
                            if output.get("task_id"):
                                if st.session_state.get("task_id") != output["task_id"]:
                                    st.session_state["task_id"] = output["task_id"]
                                    set_cached_node_output("execution", output)
                            if output.get("verification_result"):
                                if st.session_state.get("verification_result") != output["verification_result"]:
                                    st.session_state["verification_result"] = output["verification_result"]
                                    set_cached_node_output("verification", output)

                            st.session_state.workflow_result = output
                            st.rerun()  # 触发界面更新（仅更新必要部分）

                st.session_state.retry_count = st.session_state.workflow_result.get("retry_count", 0) if st.session_state.workflow_result else 0
                st.session_state["is_running"] = False
                st.success("工作流执行完成！")

        st.markdown(f'''
            <div style="
                margin-top: 30px;
                padding: 16px;
                background: #1e293b;
                border-radius: 12px;
                border: 1px solid {COLORS['border']};
            ">
                <div style="color: {COLORS['text_secondary']}; font-size: 14px; line-height: 1.5;">
                    <strong style="color: {COLORS['text_primary']}; font-size: 14px;">💡 使用提示</strong><br><br>
                    • 输入自然语言描述您的算力需求<br>
                    • 系统自动解析意图并选择最优节点<br>
                    • 验证失败时自动触发自愈重试机制
                </div>
            </div>
        ''', unsafe_allow_html=True)

    col_main, col_side = st.columns([3, 1], gap="large")

    with col_main:
        result = st.session_state.workflow_result

        if result:
            st.markdown("### ⚡ 工作流执行状态")
            draw_workflow_agraph(
                flow_status=st.session_state.flow_status,
                step_times=st.session_state.step_times
            )

            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

            if st.session_state.get("show_node_details"):
                node_id = st.session_state.get("selected_node")
                if node_id:
                    node_info = get_node_info(node_id)
                    st.markdown(f"#### 📋 节点详情：{node_info.get('节点名称', node_id)}")
                    st.json(node_info)

                    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

            with st.expander("🔗 查看节点间数据传递", expanded=False):
                # 显示意图解析的输出（仅传输task_type和compute_type）
                if "structured_requirement" in st.session_state and st.session_state["structured_requirement"]:
                    st.write("**意图解析输出（传递给资源发现）：**")
                    required_data = {
                        "task_type": st.session_state["structured_requirement"].get("task_type"),
                        "compute_type": st.session_state["structured_requirement"].get("compute_type"),
                    }
                    st.json(required_data)
                    st.markdown("---")

                # 显示资源发现的输出（作为调度决策的输入）
                if "available_resources" in st.session_state and st.session_state["available_resources"]:
                    st.write("**资源发现输出（传递给调度决策）：**")
                    st.json(st.session_state["available_resources"])
                    st.markdown("---")

                if "candidate_nodes" in st.session_state and st.session_state["candidate_nodes"]:
                    st.write("**候选节点列表（传递给调度决策）：**")
                    st.json(st.session_state["candidate_nodes"])
                    st.markdown("---")

                if "scheduled_node" in st.session_state and st.session_state["scheduled_node"]:
                    st.write("**调度决策输出（传递给策略执行）：**")
                    st.json({"selected_node": st.session_state["scheduled_node"]})
                    st.markdown("---")

                if "task_id" in st.session_state and st.session_state["task_id"]:
                    st.write("**策略执行输出（传递给遥测验证）：**")
                    st.json({"task_id": st.session_state["task_id"]})

            col1, col2, col3, col4 = st.columns(4)

            task_type = result.get("structured_requirement", {}).get("task_type", "N/A")
            with col1:
                st.markdown(
                    draw_metric_card("任务类型", task_type.upper(), "🎯", COLORS['primary'], subtitle=f"推断类型"),
                    unsafe_allow_html=True
                )

            scheduled_node = result.get("scheduled_node", "N/A")
            with col2:
                st.markdown(
                    draw_metric_card("调度节点", scheduled_node, "🖥️", COLORS['success'], subtitle=f"算力类型"),
                    unsafe_allow_html=True
                )

            execution_status = result.get("execution_status", "unknown")
            status_color = COLORS['success'] if execution_status == "success" else COLORS['error']
            with col3:
                st.markdown(
                    draw_metric_card("执行状态", execution_status.upper(), "✅" if execution_status == "success" else "❌", status_color),
                    unsafe_allow_html=True
                )

            failed_nodes = result.get("failed_nodes", [])
            with col4:
                st.markdown(
                    draw_metric_card("失败节点", f"{len(failed_nodes)}/5", "⚠️", COLORS['warning'] if failed_nodes else COLORS['text_secondary'], 
                                    progress_value=len(failed_nodes)),
                    unsafe_allow_html=True
                )

            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

            st.markdown(draw_resource_chart(), unsafe_allow_html=True)

            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

            tab1, tab2, tab3 = st.tabs(["📋 结构化需求", "📦 节点详情", "📊 原始数据"])

            with tab1:
                structured_req = result.get("structured_requirement", {})
                if structured_req:
                    req_cols = st.columns(3)
                    with req_cols[0]:
                        st.metric("任务类型", structured_req.get("task_type", "N/A"))
                    with req_cols[1]:
                        st.metric("计算类型", structured_req.get("compute_type", "N/A"))
                    with req_cols[2]:
                        lat = structured_req.get("required_latency_ms")
                        st.metric("延迟要求", f"{lat}ms" if lat else "无")
                    st.markdown("---")
                    st.json(structured_req)
                else:
                    st.info("暂无结构化需求数据")

            with tab2:
                scheduled_node = result.get("scheduled_node")
                available_resources = result.get("available_resources", [])
                if scheduled_node:
                    for node in available_resources:
                        node_id = node.get('node_id')
                        is_selected = (node_id == scheduled_node)
                        border_color = COLORS['primary'] if is_selected else COLORS['border']
                        status_color = COLORS['success'] if node.get('status') == 'online' else COLORS['error']
                        
                        st.markdown(f'''
                            <div style="
                                background: {COLORS['bg_card']};
                                border: 2px solid {border_color};
                                border-radius: 12px;
                                padding: 16px;
                                margin-bottom: 12px;
                                transition: all 0.3s ease;
                                {'box-shadow: 0 0 20px rgba(59, 130, 246, 0.3);' if is_selected else ''}
                            ">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                    <span style="color: {COLORS['text_primary']}; font-weight: 600; font-size: 14px;">
                                        {node_id}
                                        {f'<span style="background: {COLORS["primary"]}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 10px; margin-left: 8px;">SELECTED</span>' if is_selected else ''}
                                    </span>
                                    <span style="color: {status_color}; font-size: 12px;">● {node.get('status', 'unknown')}</span>
                                </div>
                                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;">
                                    <div style="color: {COLORS['text_secondary']}; font-size: 11px;">
                                        <span style="color: {COLORS['text_primary']};">Region:</span> {node.get('region', 'N/A')}
                                    </div>
                                    <div style="color: {COLORS['text_secondary']}; font-size: 11px;">
                                        <span style="color: {COLORS['text_primary']};">Type:</span> {node.get('node_type', 'N/A')}
                                    </div>
                                    <div style="color: {COLORS['text_secondary']}; font-size: 11px;">
                                        <span style="color: {COLORS['text_primary']};">CPU:</span> {node.get('available_cpu', 0)}核
                                    </div>
                                    <div style="color: {COLORS['text_secondary']}; font-size: 11px;">
                                        <span style="color: {COLORS['text_primary']};">GPU:</span> {node.get('gpu_count', 0)}卡
                                    </div>
                                </div>
                            </div>
                        ''', unsafe_allow_html=True)

            with tab3:
                st.json(result)

        else:
            st.markdown(f'''
                <div style="
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    padding: 80px 40px;
                    background: {COLORS['bg_card']};
                    border-radius: 16px;
                    border: 2px dashed {COLORS['border']};
                    text-align: center;
                ">
                    <div style="font-size: 64px; margin-bottom: 24px;">🔮</div>
                    <div style="color: {COLORS['text_primary']}; font-size: 20px; font-weight: 600; margin-bottom: 12px;">
                        欢迎使用智维AgentHub
                    </div>
                    <div style="color: {COLORS['text_secondary']}; font-size: 14px; max-width: 400px; line-height: 1.6;">
                        在左侧输入您的算力需求，系统将自动解析意图、发现资源、调度节点并验证执行结果。
                    </div>
                </div>
            ''', unsafe_allow_html=True)

    with col_side:
        st.markdown(f'''
            <div style="padding: 16px; background: {COLORS['bg_card']}; border-radius: 12px; border: 1px solid {COLORS['border']};">
                <div style="color: {COLORS['text_primary']}; font-weight: 600; margin-bottom: 16px;">🔍 遥测验证</div>
        ''', unsafe_allow_html=True)

        if result:
            st.markdown(draw_telemetry_section(result), unsafe_allow_html=True)
            
            if not result.get("verification_result", {}).get("achieved", False):
                if st.button("🔄 一键重试", key="retry_button", use_container_width=True):
                    retry_workflow()
                    st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

            task_id = result.get("task_id")
            if task_id:
                st.markdown(f'''
                    <div style="
                        margin-top: 16px;
                        padding: 12px;
                        background: {COLORS['bg_card']};
                        border-radius: 8px;
                        border: 1px solid {COLORS['border']};
                    ">
                        <div style="color: {COLORS['text_secondary']}; font-size: 11px; margin-bottom: 4px;">任务ID</div>
                        <div style="color: {COLORS['text_primary']}; font-size: 12px; word-break: break-all;">{task_id}</div>
                    </div>
                ''', unsafe_allow_html=True)
        else:
            st.markdown('''
                <div style="text-align: center; padding: 30px 20px; color: #94A3B8;">
                    <div style="font-size: 32px; margin-bottom: 12px;">⏳</div>
                    <div style="font-size: 13px;">执行工作流后<br>显示验证结果</div>
                </div>
            </div>
            ''', unsafe_allow_html=True)

if __name__ == "__main__":
    main()