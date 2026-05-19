"""
LangGraph 调度工作流状态定义

使用 TypedDict 定义状态结构，支持消息累积和状态流转。
"""

from typing import TypedDict, Optional, List, Dict, Any, Annotated
from langgraph.graph import add_messages


class SchedulingState(TypedDict):
    """
    算力网络多智能体协同调度系统的状态定义

    状态字段说明（精简版）：
    - user_intent: 用户输入的自然语言意图
    - structured_requirement: 意图解析后的结构化任务需求
    - available_resources: 资源发现阶段获取的所有可用算力节点
    - candidate_nodes: 根据需求筛选后的候选节点列表
    - scheduled_node: 调度决策选中的目标节点ID
    - task_id: 策略执行后的任务ID
    - execution_result: 策略执行后的结果
    - verification_result: 遥测验证结果
    - retry_count: 重试次数
    - failed_nodes: 验证失败的节点列表
    - messages: 对话消息历史，支持累积追加
    """

    user_intent: str
    structured_requirement: Optional[Dict[str, Any]]
    available_resources: List[Dict[str, Any]]
    candidate_nodes: List[Dict[str, Any]]
    scheduled_node: Optional[str]
    task_id: Optional[str]
    execution_result: Optional[Dict[str, Any]]
    verification_result: Optional[Dict[str, Any]]
    retry_count: int
    failed_nodes: List[str]
    messages: Annotated[list, add_messages]