from typing import Dict, Any
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def mock_verify_intent_achieved(user_intent: str, execution_result: Dict) -> bool:
    """
    模拟验证意图是否达成（基于规则引擎）
    """
    status = execution_result.get("status", "")
    if status == "success":
        return True
    return False


def verify_node(node_id: str) -> Dict[str, Any]:
    """
    验证节点执行结果（用于演示闭环重构功能）
    
    根据执行节点返回不同的验证结果：
    - 如果执行节点是 A，强制返回 {'achieved': False, 'reason': 'Latency exceeds 50ms SLA'}
    - 如果是 B，返回 {'achieved': True}
    - 其他节点随机返回
    
    Args:
        node_id: 执行任务的节点ID
        
    Returns:
        验证结果字典，包含 achieved 和 reason 字段
    """
    # 提取节点标识（假设节点ID格式为 node-xxx-A 或 node-xxx-B）
    node_suffix = node_id[-1] if node_id else ""
    
    if node_suffix == 'A' or 'node-A' in node_id.lower():
        return {
            'achieved': False,
            'reason': 'Latency exceeds 50ms SLA'
        }
    elif node_suffix == 'B' or 'node-B' in node_id.lower():
        return {
            'achieved': True,
            'reason': 'All SLAs met'
        }
    else:
        # 其他节点随机返回，50%概率成功
        import random
        if random.random() > 0.5:
            return {
                'achieved': True,
                'reason': 'All SLAs met'
            }
        else:
            return {
                'achieved': False,
                'reason': 'Performance degradation detected'
            }

def verify_intent_achieved(user_intent: str, execution_result: Dict) -> bool:
    """
    验证意图是否达成
    优先使用LLM解析，若没有API密钥则使用规则引擎模拟
    """
    try:
        from agents.intent_parser import get_llm
        llm = get_llm()
        
        if llm is None:
            return mock_verify_intent_achieved(user_intent, execution_result)
        
        from langchain_core.prompts import ChatPromptTemplate
        
        VERIFICATION_PROMPT = ChatPromptTemplate.from_messages([
            ("system", """你是一个任务达成评估专家。
请只输出"true"或"false"。"""),
            ("human", """原始意图: {user_intent}
执行结果: {execution_result}
意图是否达成？""")
        ])
        
        chain = VERIFICATION_PROMPT | llm
        response = chain.invoke({
            "user_intent": user_intent,
            "execution_result": str(execution_result)
        })
        
        result_str = response.content if hasattr(response, 'content') else str(response)
        return result_str.lower().strip() == "true"
    except Exception:
        return mock_verify_intent_achieved(user_intent, execution_result)

def collect_telemetry(node_id: str) -> Dict:
    """
    采集节点遥测数据
    
    Args:
        node_id: 节点ID
        
    Returns:
        遥测数据
    """
    from tools.mcp_tools import _get_node_status
    try:
        return _get_node_status(node_id)
    except Exception:
        return {"status": "unknown", "metrics": {}}

def evaluate_performance(telemetry: Dict) -> Dict[str, Any]:
    """
    评估节点性能指标
    
    Args:
        telemetry: 遥测数据
        
    Returns:
        性能评估结果
    """
    load = telemetry.get("current_load", 1)
    status = telemetry.get("status", "unknown")
    
    return {
        "health_score": (1 - load) * 100,
        "status": status,
        "available_cpu": telemetry.get("available_cpu", 0),
        "available_memory": telemetry.get("available_memory", 0),
        "gpu_count": telemetry.get("gpu_count", 0)
    }