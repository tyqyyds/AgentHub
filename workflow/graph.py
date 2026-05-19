"""
LangGraph 工作流定义

构建算力网络多智能体协同调度的状态机工作流，包含：
- 意图解析 → 资源发现 → 调度决策 → 策略执行 → 遥测验证

节点配置：
- intent_parser: 意图解析节点
- resource_discovery: 资源发现节点
- scheduling: 调度决策节点
- execution: 策略执行节点
- verification: 遥测验证节点

条件分支：
- 从 verification 出发，如果 state.verification_result['achieved'] 为 False 且 state.retry_count < 2，则路由回 scheduling
- 否则路由到 END
"""

from langgraph.graph import StateGraph, END
from typing import Dict, Any, List
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.state import SchedulingState
from agents.intent_parser import parse_intent_node
from agents.resource_discovery import discover_resources, filter_nodes_by_requirements
from agents.scheduler import schedule_task
from agents.executor import execute_task
from agents.verifier import verify_intent_achieved, collect_telemetry, verify_node


def intent_parser(state: SchedulingState) -> SchedulingState:
    """意图解析节点 - 将自然语言意图转换为结构化需求（支持流式输出）"""
    try:
        import streamlit as st
        st.session_state["edge_status"][("intent_parser", "resource_discovery")] = "in_progress"

        from agents.intent_parser import parse_intent
        
        # 使用流式输出逐步更新结果
        result = {}
        accumulated_content = ""
        
        # 尝试使用astream逐步输出（如果可用）
        try:
            from agents.intent_parser import parse_intent_stream
            
            # 流式解析意图，逐步更新界面
            for chunk in parse_intent_stream(state["user_intent"]):
                accumulated_content += chunk.get("content", "")
                
                # 尝试解析部分结果
                if chunk.get("structured_requirement"):
                    result = chunk["structured_requirement"]
                    # 实时更新界面
                    current_requirement = st.session_state.get("structured_requirement")
                    if result != current_requirement:
                        st.session_state["parsed_intent"] = result
                        st.session_state["structured_requirement"] = result
                        st.rerun()  # 触发界面更新
        except ImportError:
            # 回退到普通解析
            result = parse_intent(state["user_intent"])

        st.session_state["edge_status"][("intent_parser", "resource_discovery")] = "completed"
        st.session_state["node_data"] = {
            "intent_parser": {
                "input": {"user_intent": state["user_intent"]},
                "output": {"structured_requirement": result},
                "status": "completed"
            }
        }
        
        # 仅当数据变化时更新st.session_state
        current_requirement = st.session_state.get("structured_requirement")
        if result != current_requirement:
            st.session_state["parsed_intent"] = result
            st.session_state["structured_requirement"] = result

        return {
            **state,
            "structured_requirement": result,
            "execution_status": "success",
            "messages": [{"role": "system", "content": f"已解析用户意图: {result}"}]
        }
    except Exception as e:
        try:
            import streamlit as st
            st.session_state["edge_status"][("intent_parser", "resource_discovery")] = "failed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["intent_parser"] = {
                "input": {"user_intent": state.get("user_intent", "")},
                "output": None,
                "status": "failed",
                "error": str(e)
            }
            st.session_state["parsed_intent"] = None
        except:
            pass

        return {
            **state,
            "error_message": str(e),
            "execution_status": "failed",
            "messages": [{"role": "system", "content": f"意图解析失败: {str(e)}"}]
        }


def resource_discovery(state: SchedulingState) -> SchedulingState:
    """资源发现节点 - 获取可用算力节点列表"""
    try:
        import streamlit as st
        st.session_state["edge_status"][("resource_discovery", "scheduling")] = "in_progress"

        region = state["structured_requirement"].get("region") if state["structured_requirement"] else None
        resources = discover_resources(region)

        candidate_nodes = []
        if state["structured_requirement"]:
            req = state["structured_requirement"]
            candidate_nodes = filter_nodes_by_requirements(
                resources,
                req.get("required_cpu", 0),
                req.get("required_memory", 0),
                req.get("required_gpu", 0)
            )

        st.session_state["edge_status"][("resource_discovery", "scheduling")] = "completed"

        if "node_data" not in st.session_state:
            st.session_state["node_data"] = {}
        st.session_state["node_data"]["resource_discovery"] = {
            "input": {"structured_requirement": state.get("structured_requirement")},
            "output": {
                "available_resources": resources,
                "candidate_nodes": candidate_nodes,
                "region": region
            },
            "status": "completed"
        }
        
        # 仅当数据变化时更新st.session_state
        current_resources = st.session_state.get("available_resources")
        current_candidates = st.session_state.get("candidate_nodes")
        if resources != current_resources:
            st.session_state["available_resources"] = resources
        if candidate_nodes != current_candidates:
            st.session_state["candidate_nodes"] = candidate_nodes

        return {
            **state,
            "available_resources": resources,
            "candidate_nodes": candidate_nodes,
            "execution_status": "success",
            "messages": [{"role": "system", "content": f"发现 {len(resources)} 个可用节点，筛选出 {len(candidate_nodes)} 个候选节点"}]
        }
    except Exception as e:
        try:
            import streamlit as st
            st.session_state["edge_status"][("resource_discovery", "scheduling")] = "failed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["resource_discovery"] = {
                "input": {"structured_requirement": state.get("structured_requirement")},
                "output": None,
                "status": "failed",
                "error": str(e)
            }
            st.session_state["available_resources"] = []
            st.session_state["candidate_nodes"] = []
        except:
            pass

        return {
            **state,
            "error_message": str(e),
            "execution_status": "failed",
            "messages": [{"role": "system", "content": f"资源发现失败: {str(e)}"}]
        }


def scheduling(state: SchedulingState) -> SchedulingState:
    """调度决策节点 - 选择最优算力节点"""
    try:
        import streamlit as st
        st.session_state["edge_status"][("scheduling", "execution")] = "in_progress"

        if not state["structured_requirement"]:
            st.session_state["edge_status"][("scheduling", "execution")] = "failed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["scheduling"] = {
                "input": {"candidate_nodes": state.get("candidate_nodes")},
                "output": None,
                "status": "failed",
                "error": "No structured requirement"
            }
            return {
                **state,
                "error_message": "No structured requirement",
                "execution_status": "failed",
                "messages": [{"role": "system", "content": "调度失败: 缺少结构化需求"}]
            }

        if not state["candidate_nodes"]:
            st.session_state["edge_status"][("scheduling", "execution")] = "failed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["scheduling"] = {
                "input": {"candidate_nodes": state.get("candidate_nodes")},
                "output": None,
                "status": "failed",
                "error": "No candidate nodes available"
            }
            return {
                **state,
                "error_message": "No candidate nodes available",
                "execution_status": "failed",
                "messages": [{"role": "system", "content": "调度失败: 没有可用的候选节点"}]
            }

        failed_nodes = state.get("failed_nodes", [])

        retry_count = state.get("retry_count", 0)
        if retry_count > 0 and failed_nodes:
            filtered_candidates = [
                node for node in state["candidate_nodes"]
                if node.get("node_id") not in failed_nodes
            ]
        else:
            filtered_candidates = state["candidate_nodes"]

        if not filtered_candidates:
            st.session_state["edge_status"][("scheduling", "execution")] = "failed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["scheduling"] = {
                "input": {"candidate_nodes": state.get("candidate_nodes")},
                "output": None,
                "status": "failed",
                "error": "No available nodes after filtering"
            }
            return {
                **state,
                "error_message": "No available nodes after filtering failed ones",
                "execution_status": "failed",
                "messages": [{"role": "system", "content": "调度失败: 所有候选节点都已验证失败"}]
            }

        result = schedule_task(filtered_candidates, state["structured_requirement"])

        if result["success"]:
            st.session_state["edge_status"][("scheduling", "execution")] = "completed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["scheduling"] = {
                "input": {"candidate_nodes": filtered_candidates},
                "output": {"scheduled_node": result["selected_node"]},
                "status": "completed"
            }
            
            # 仅当数据变化时更新st.session_state
            current_scheduled = st.session_state.get("scheduled_node")
            if result["selected_node"] != current_scheduled:
                st.session_state["scheduled_node"] = result["selected_node"]

            return {
                **state,
                "scheduled_node": result["selected_node"],
                "execution_status": "success",
                "messages": [{"role": "system", "content": f"已选择节点: {result['selected_node']}"}]
            }
        else:
            st.session_state["edge_status"][("scheduling", "execution")] = "failed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["scheduling"] = {
                "input": {"candidate_nodes": filtered_candidates},
                "output": None,
                "status": "failed",
                "error": result.get("error")
            }
            return {
                **state,
                "error_message": result.get("error"),
                "execution_status": "failed",
                "messages": [{"role": "system", "content": f"调度失败: {result.get('error')}"}]
            }
    except Exception as e:
        try:
            import streamlit as st
            st.session_state["edge_status"][("scheduling", "execution")] = "failed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["scheduling"] = {
                "input": {"candidate_nodes": state.get("candidate_nodes")},
                "output": None,
                "status": "failed",
                "error": str(e)
            }
        except:
            pass

        return {
            **state,
            "error_message": str(e),
            "execution_status": "failed",
            "messages": [{"role": "system", "content": f"调度异常: {str(e)}"}]
        }


def execution(state: SchedulingState) -> SchedulingState:
    """策略执行节点 - 在选中节点上执行任务"""
    try:
        import streamlit as st
        st.session_state["edge_status"][("execution", "verification")] = "in_progress"

        if not state["scheduled_node"]:
            st.session_state["edge_status"][("execution", "verification")] = "failed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["execution"] = {
                "input": {"scheduled_node": None},
                "output": None,
                "status": "failed",
                "error": "No node scheduled"
            }
            return {
                **state,
                "error_message": "No node scheduled",
                "execution_status": "failed",
                "messages": [{"role": "system", "content": "执行失败: 未选择目标节点"}]
            }

        task_config = state["structured_requirement"] if state["structured_requirement"] else {}
        result = execute_task(state["scheduled_node"], task_config)

        if result.get("status") == "submitted":
            st.session_state["edge_status"][("execution", "verification")] = "completed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["execution"] = {
                "input": {"scheduled_node": state["scheduled_node"], "task_config": task_config},
                "output": {"task_id": result.get("task_id"), "status": result.get("status")},
                "status": "completed"
            }
            
            # 仅当数据变化时更新st.session_state
            current_task_id = st.session_state.get("task_id")
            if result.get("task_id") != current_task_id:
                st.session_state["task_id"] = result.get("task_id")

            return {
                **state,
                "execution_status": "success",
                "task_id": result.get("task_id"),
                "messages": [{"role": "system", "content": f"任务已提交，任务ID: {result.get('task_id')}"}]
            }
        else:
            st.session_state["edge_status"][("execution", "verification")] = "failed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["execution"] = {
                "input": {"scheduled_node": state["scheduled_node"]},
                "output": None,
                "status": "failed",
                "error": result.get("error")
            }
            return {
                **state,
                "error_message": result.get("error"),
                "execution_status": "failed",
                "messages": [{"role": "system", "content": f"任务提交失败: {result.get('error')}"}]
            }
    except Exception as e:
        try:
            import streamlit as st
            st.session_state["edge_status"][("execution", "verification")] = "failed"
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["execution"] = {
                "input": {"scheduled_node": state.get("scheduled_node")},
                "output": None,
                "status": "failed",
                "error": str(e)
            }
        except:
            pass

        return {
            **state,
            "error_message": str(e),
            "execution_status": "failed",
            "messages": [{"role": "system", "content": f"执行异常: {str(e)}"}]
        }


def verification(state: SchedulingState) -> SchedulingState:
    """遥测验证节点 - 验证任务执行结果是否达成用户意图

    使用 verify_node 函数进行验证：
    - 如果执行节点是 A，强制返回 {'achieved': False, 'reason': 'Latency exceeds 50ms SLA'}
    - 如果是 B，返回 {'achieved': True}
    - 其他节点随机返回
    """
    try:
        import streamlit as st

        if state["execution_status"] != "success":
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["verification"] = {
                "input": {"execution_status": state["execution_status"]},
                "output": None,
                "status": "failed",
                "error": "Execution failed"
            }
            return {
                **state,
                "verification_result": {"achieved": False, "reason": "任务执行失败"},
                "execution_status": "failed"
            }

        telemetry_data = collect_telemetry(state["scheduled_node"])

        node_result = verify_node(state["scheduled_node"])
        achieved = node_result.get("achieved", False)
        reason = node_result.get("reason", "Unknown")

        if not achieved:
            failed_nodes = state.get("failed_nodes", [])
            failed_nodes.append(state["scheduled_node"])

            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["verification"] = {
                "input": {"scheduled_node": state["scheduled_node"], "telemetry": telemetry_data},
                "output": {"achieved": achieved, "reason": reason},
                "status": "failed"
            }

            return {
                **state,
                "verification_result": {
                    "achieved": achieved,
                    "telemetry": telemetry_data,
                    "reason": reason
                },
                "execution_status": "failed",
                "retry_count": state.get("retry_count", 0) + 1,
                "failed_nodes": failed_nodes,
                "messages": [{"role": "system", "content": f"遥测验证完成，意图达成: {achieved}，原因: {reason}，重试次数: {state.get('retry_count', 0) + 1}，已失败节点: {failed_nodes}"}]
            }

        if "node_data" not in st.session_state:
            st.session_state["node_data"] = {}
        st.session_state["node_data"]["verification"] = {
            "input": {"scheduled_node": state["scheduled_node"], "telemetry": telemetry_data},
            "output": {"achieved": achieved, "reason": reason, "telemetry": telemetry_data},
            "status": "completed"
        }

        return {
            **state,
            "verification_result": {
                "achieved": achieved,
                "telemetry": telemetry_data,
                "reason": reason
            },
            "execution_status": "success" if achieved else "failed",
            "messages": [{"role": "system", "content": f"遥测验证完成，意图达成: {achieved}，原因: {reason}"}]
        }
    except Exception as e:
        try:
            import streamlit as st
            if "node_data" not in st.session_state:
                st.session_state["node_data"] = {}
            st.session_state["node_data"]["verification"] = {
                "input": {"scheduled_node": state.get("scheduled_node")},
                "output": None,
                "status": "failed",
                "error": str(e)
            }
        except:
            pass

        return {
            **state,
            "error_message": str(e),
            "verification_result": {"achieved": False, "reason": f"验证异常: {str(e)}"},
            "execution_status": "failed",
            "retry_count": state.get("retry_count", 0) + 1,
            "messages": [{"role": "system", "content": f"验证异常: {str(e)}"}]
        }


def routing_decision(state: SchedulingState) -> str:
    """
    路由决策函数 - 从 verification 节点出发的条件分支

    如果 state.verification_result['achieved'] 为 False 且 state.retry_count < 2，
    则路由回 scheduling 重新选择节点；否则路由到 END。
    """
    verification_result = state.get("verification_result", {})
    achieved = verification_result.get("achieved", True)
    retry_count = state.get("retry_count", 0)

    # 如果验证未达成且重试次数小于2，路由回 scheduling
    if not achieved and retry_count < 2:
        return "scheduling"

    # 否则结束
    return END


# 构建状态图
graph = StateGraph(SchedulingState)

# 添加节点
graph.add_node("intent_parser", intent_parser)
graph.add_node("resource_discovery", resource_discovery)
graph.add_node("scheduling", scheduling)
graph.add_node("execution", execution)
graph.add_node("verification", verification)

# 设置入口点
graph.set_entry_point("intent_parser")

# 添加边：intent_parser -> resource_discovery -> scheduling -> execution -> verification
graph.add_edge("intent_parser", "resource_discovery")
graph.add_edge("resource_discovery", "scheduling")
graph.add_edge("scheduling", "execution")
graph.add_edge("execution", "verification")

# 添加条件边：从 verification 出发的条件分支
graph.add_conditional_edges(
    "verification",
    routing_decision,
    {
        "scheduling": "scheduling",  # 验证失败且重试次数<2，重新调度
        END: END                       # 验证成功或重试次数已满，结束
    }
)

# 编译图
app = graph.compile()


def build_workflow() -> StateGraph:
    """构建LangGraph工作流（兼容旧接口）"""
    return graph


def execute_workflow(user_intent: str) -> Dict[str, Any]:
    """执行完整工作流"""
    initial_state: SchedulingState = {
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

    result = app.invoke(initial_state)
    return result