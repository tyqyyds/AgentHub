import streamlit as st
from typing import Dict, List, Any

def render_header():
    """渲染页面头部"""
    st.set_page_config(
        page_title="算力网络多智能体协同调度系统",
        page_icon="🚀",
        layout="wide"
    )
    
    st.markdown("""
        <style>
        .main-header {
            font-size: 28px;
            font-weight: bold;
            color: #1a73e8;
            margin-bottom: 10px;
        }
        .sub-header {
            font-size: 14px;
            color: #666;
            margin-bottom: 20px;
        }
        .status-running {
            color: #10b981;
        }
        .status-pending {
            color: #f59e0b;
        }
        .status-completed {
            color: #3b82f6;
        }
        .status-failed {
            color: #ef4444;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="main-header">🚀 算力网络多智能体协同调度系统</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">基于 LangChain + LangGraph 的智能调度平台</div>', unsafe_allow_html=True)

def render_intent_input() -> str:
    """渲染意图输入框"""
    st.subheader("💡 用户意图输入")
    
    user_intent = st.text_area(
        "请输入您的任务需求",
        placeholder="例如：在上海区域使用GPU节点训练一个AI模型，需要4核CPU、16GB内存、1块GPU",
        height=100
    )
    
    if st.button("执行调度", type="primary"):
        if user_intent.strip():
            return user_intent.strip()
    
    return ""

def render_node_card(node: Dict[str, Any]):
    """渲染单个节点卡片"""
    node_type_emoji = {
        "gpu": "🎮",
        "cpu": "💻",
        "edge": "🌐"
    }
    
    region_name = {
        "beijing": "北京",
        "shanghai": "上海",
        "hangzhou": "杭州",
        "guangzhou": "广州",
        "chengdu": "成都"
    }
    
    with st.container():
        st.markdown(f"""
            <div style="border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div style="display: flex; align-items: center;">
                        <span style="font-size: 24px; margin-right: 12px;">{node_type_emoji.get(node['node_type'], '💻')}</span>
                        <div>
                            <div style="font-weight: bold; font-size: 16px;">{node['node_id']}</div>
                            <div style="font-size: 12px; color: #666;">{region_name.get(node['region'], node['region'])}</div>
                        </div>
                    </div>
                    <span style="padding: 4px 12px; border-radius: 20px; font-size: 12px; background-color: {'#d1fae5' if node['status'] == 'online' else '#fee2e2'}; color: {'#065f46' if node['status'] == 'online' else '#991b1b'};">
                        {'在线' if node['status'] == 'online' else '离线'}
                    </span>
                </div>
                
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;">
                    <div style="text-align: center; padding: 8px; background-color: #f9fafb; border-radius: 8px;">
                        <div style="font-size: 14px; font-weight: bold;">{node['available_cpu']}</div>
                        <div style="font-size: 11px; color: #666;">CPU核数</div>
                    </div>
                    <div style="text-align: center; padding: 8px; background-color: #f9fafb; border-radius: 8px;">
                        <div style="font-size: 14px; font-weight: bold;">{node['available_memory'] // 1024}GB</div>
                        <div style="font-size: 11px; color: #666;">内存</div>
                    </div>
                    <div style="text-align: center; padding: 8px; background-color: #f9fafb; border-radius: 8px;">
                        <div style="font-size: 14px; font-weight: bold;">{node['gpu_count']}</div>
                        <div style="font-size: 11px; color: #666;">GPU数量</div>
                    </div>
                    <div style="text-align: center; padding: 8px; background-color: #f9fafb; border-radius: 8px;">
                        <div style="font-size: 14px; font-weight: bold;">{int(node['current_load'] * 100)}%</div>
                        <div style="font-size: 11px; color: #666;">负载</div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

def render_resource_panel(resources: List[Dict[str, Any]]):
    """渲染资源面板"""
    st.subheader("🔧 可用算力节点")
    
    if not resources:
        st.info("暂无可用算力节点")
        return
    
    for node in resources:
        render_node_card(node)

def render_scheduling_result(result: Dict[str, Any]):
    """渲染调度结果"""
    st.subheader("📋 调度结果")
    
    if result.get("error_message"):
        st.error(f"❌ 调度失败: {result['error_message']}")
        return
    
    if not result.get("selected_node"):
        st.warning("⚠️ 未选中任何节点")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🎯 选中节点")
        st.info(f"**节点ID:** {result['selected_node']}")
        
        if result.get("task_id"):
            st.success(f"**任务ID:** {result['task_id']}")
        
        if result.get("execution_status"):
            status_color = "green" if result["execution_status"] == "success" else "red"
            st.markdown(f"**执行状态:** <span style='color: {status_color}; font-weight: bold;'>{result['execution_status']}</span>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("### 📊 意图达成")
        achieved = result.get("intent_achieved")
        if achieved is True:
            st.success("✅ 意图已达成")
        elif achieved is False:
            st.error("❌ 意图未达成")
        else:
            st.info("⏳ 验证中")
    
    if result.get("structured_requirement"):
        st.markdown("### 📝 任务需求")
        st.json(result["structured_requirement"])

def render_workflow_visualization(workflow_status: Dict[str, str]):
    """渲染工作流可视化"""
    st.subheader("🔄 工作流状态")
    
    stages = ["意图解析", "资源发现", "调度决策", "策略执行", "遥测验证"]
    
    status_colors = {
        "running": "#10b981",
        "pending": "#f59e0b",
        "completed": "#3b82f6",
        "failed": "#ef4444"
    }
    
    status_emojis = {
        "running": "🔄",
        "pending": "⏳",
        "completed": "✅",
        "failed": "❌"
    }
    
    st.markdown('<div style="display: flex; align-items: center; justify-content: center; gap: 24px; padding: 20px; background-color: #f9fafb; border-radius: 12px;">', unsafe_allow_html=True)
    
    for i, stage in enumerate(stages):
        status = workflow_status.get(stage, "pending")
        color = status_colors[status]
        emoji = status_emojis[status]
        
        st.markdown(f"""
            <div style="display: flex; flex-direction: column; align-items: center;">
                <div style="width: 50px; height: 50px; border-radius: 50%; background-color: {color}; display: flex; align-items: center; justify-content: center; font-size: 24px; margin-bottom: 8px;">
                    {emoji}
                </div>
                <div style="font-size: 13px; text-align: center; max-width: 80px;">{stage}</div>
            </div>
        """, unsafe_allow_html=True)
        
        if i < len(stages) - 1:
            st.markdown('<div style="width: 40px; height: 2px; background-color: #e5e7eb;"></div>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)