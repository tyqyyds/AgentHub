import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflow.graph import build_workflow
from frontend.components import (
    render_header,
    render_intent_input,
    render_resource_panel,
    render_scheduling_result,
    render_workflow_visualization,
    render_node_card
)
from agents.resource_discovery import discover_resources

def main():
    render_header()
    
    if "workflow_status" not in st.session_state:
        st.session_state.workflow_status = {}
    if "scheduling_result" not in st.session_state:
        st.session_state.scheduling_result = None
    
    with st.sidebar:
        st.header("📊 系统状态")
        
        if st.button("🔄 刷新资源状态"):
            with st.spinner("正在发现算力节点..."):
                resources = discover_resources()
                st.session_state.resources = resources
        
        if "resources" in st.session_state:
            render_resource_panel(st.session_state.resources)
    
    user_intent = render_intent_input()
    
    if user_intent:
        with st.spinner("🚀 正在执行多智能体调度..."):
            st.session_state.workflow_status = {
                "意图解析": "running",
                "资源发现": "pending",
                "调度决策": "pending",
                "策略执行": "pending",
                "遥测验证": "pending"
            }
            
            workflow = build_workflow()
            app = workflow.compile()
            
            initial_state = {
                "user_intent": user_intent,
                "structured_requirement": None,
                "available_resources": [],
                "selected_node": None,
                "execution_status": None,
                "intent_achieved": None,
                "error_message": None,
                "retry_count": 0,
                "task_id": None,
                "execution_result": None
            }
            
            result = app.invoke(initial_state)
            st.session_state.scheduling_result = result
            
            st.session_state.workflow_status = {
                stage: "completed" for stage in st.session_state.workflow_status
            }
        
        render_scheduling_result(st.session_state.scheduling_result)
    
    if st.session_state.scheduling_result:
        render_workflow_visualization(st.session_state.workflow_status)

if __name__ == "__main__":
    main()