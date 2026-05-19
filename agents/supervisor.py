from typing import Dict, Any, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

class Supervisor:
    """
    监督智能体，负责协调各Worker智能体的协作流程
    
    职责：
    - 接收用户意图
    - 决策调用哪个Worker
    - 汇总各Worker的执行结果
    - 判断任务是否完成
    """
    
    def __init__(self):
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个算力网络多智能体系统的监督者。
你的任务是根据当前系统状态和用户意图，决定下一步应该调用哪个智能体。

可用的智能体：
1. intent_parser: 解析用户自然语言意图
2. resource_discovery: 发现可用的算力节点资源
3. scheduler: 调度决策，选择最优算力节点
4. executor: 执行任务下发
5. verifier: 遥测验证，确认任务完成

请分析当前状态并返回下一步应该调用的智能体名称。

输出格式：{"next_agent": "智能体名称"}"""),
            ("human", "用户意图: {user_intent}\n当前状态: {current_state}")
        ])
        self.parser = JsonOutputParser()
    
    def decide_next_step(self, user_intent: str, current_state: Dict[str, Any]) -> str:
        """
        根据用户意图和当前状态决定下一步调用的智能体
        
        Args:
            user_intent: 用户输入的自然语言意图
            current_state: 当前系统状态
            
        Returns:
            下一步应调用的智能体名称
        """
        # 简化版本：按照固定流程执行
        # 完整版本：使用LLM进行决策
        
        if not current_state.get("structured_requirement"):
            return "intent_parser"
        elif not current_state.get("available_resources"):
            return "resource_discovery"
        elif not current_state.get("selected_node"):
            return "scheduler"
        elif current_state.get("execution_status") != "success":
            return "executor"
        else:
            return "verifier"
    
    def summarize_result(self, final_state: Dict[str, Any]) -> str:
        """
        汇总最终执行结果
        
        Args:
            final_state: 最终系统状态
            
        Returns:
            结果汇总字符串
        """
        result = f"任务执行结果:\n"
        result += f"状态: {'成功' if final_state.get('intent_achieved') else '失败'}\n"
        
        if final_state.get("selected_node"):
            result += f"选中节点: {final_state['selected_node']}\n"
        
        if final_state.get("task_id"):
            result += f"任务ID: {final_state['task_id']}\n"
        
        if final_state.get("error_message"):
            result += f"错误信息: {final_state['error_message']}\n"
        
        return result