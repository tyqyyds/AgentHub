"""
意图解析器模块

提供基于大模型的意图解析功能，支持将自然语言转换为结构化任务需求。
使用 LangChain 的 ChatPromptTemplate 和 PydanticOutputParser 确保输出格式。
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
import os
import re
from typing import Dict, Any, Optional
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.state import SchedulingState


class TaskRequirement(BaseModel):
    """
    任务需求的结构化定义 - Pydantic模型

    用于确保大模型输出符合固定的JSON Schema格式。
    """
    task_type: str = Field(description="任务类型：训练（training）、推理（inference）、数据处理（data_processing）")
    compute_type: str = Field(description="计算类型：CPU、GPU、NPU")
    sla_requirement: str = Field(description="SLA要求：延迟要求（如'低延迟'、'<100ms'）或带宽要求（如'高带宽'、'>10Gbps'）")
    region: Optional[str] = Field(description="地域：北京（beijing）、上海（shanghai）、杭州（hangzhou）、广州（guangzhou）、成都（chengdu），无地域偏好时为null")
    required_cpu: int = Field(default=4, description="所需CPU核心数")
    required_memory: int = Field(default=8192, description="所需内存（MB）")
    required_gpu: int = Field(default=0, description="所需GPU数量")
    required_latency_ms: Optional[int] = Field(default=None, description="所需最大延迟（毫秒），如50表示延迟需低于50ms")


class MockIntentParser:
    """
    基于规则的意图解析器，用于模拟测试环境
    """

    TASK_TYPE_KEYWORDS = {
        "training": ["训练", "微调", "fine-tune", "train", "training", "模型训练"],
        "inference": ["推理", "调用", "执行模型", "inference", "predict", "服务部署", "部署"],
        "data_processing": ["处理", "清洗", "分析数据", "data", "process", "ETL"],
    }

    COMPUTE_TYPE_KEYWORDS = {
        "GPU": ["GPU", "显卡", "GPU训练", "GPU推理"],
        "NPU": ["NPU", "昇腾"],
        "CPU": ["CPU", "核", "核心", "处理器"]
    }

    REGION_KEYWORDS = {
        "beijing": ["北京", "华北", "北方"],
        "shanghai": ["上海", "华东", "长三角"],
        "hangzhou": ["杭州", "浙江"],
        "guangzhou": ["广州", "华南"],
        "chengdu": ["成都", "西南"],
    }

    @staticmethod
    def detect_task_type(intent: str) -> str:
        for task_type, keywords in MockIntentParser.TASK_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in intent:
                    return task_type
        return "data_processing"

    @staticmethod
    def detect_compute_type(intent: str) -> str:
        for compute_type, keywords in MockIntentParser.COMPUTE_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in intent:
                    return compute_type
        return "CPU"

    @staticmethod
    def detect_region(intent: str) -> Optional[str]:
        for region, keywords in MockIntentParser.REGION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in intent:
                    return region
        return None

    @staticmethod
    def extract_number(intent: str, keywords: list) -> int:
        for keyword in keywords:
            pattern = rf'(\d+)\s*{keyword}'
            match = re.search(pattern, intent)
            if match:
                return int(match.group(1))
        return 0

    @staticmethod
    def detect_sla(intent: str) -> str:
        if any(k in intent for k in ["低延迟", "实时", "毫秒级", "<100ms"]):
            return "低延迟(<100ms)"
        elif any(k in intent for k in ["高带宽", "大流量", "高速"]):
            return "高带宽(>10Gbps)"
        else:
            return "标准延迟"

    @staticmethod
    def detect_latency_requirement(intent: str) -> Optional[int]:
        """检测延迟要求，返回延迟阈值（毫秒）"""
        patterns = [
            r'延迟\s*[低小于]\s*(\d+)\s*ms',
            r'延迟\s*[低小于]\s*(\d+)\s*毫秒',
            r'延迟\s*要求\s*[<≤]\s*(\d+)',
            r'<(\d+)ms',
            r'延迟\s*(\d+)\s*ms',
            r'延迟\s*(\d+)\s*毫秒',
            r'低于\s*(\d+)\s*ms',
            r'低于\s*(\d+)\s*毫秒',
        ]
        for pattern in patterns:
            match = re.search(pattern, intent)
            if match:
                return int(match.group(1))

        if "低延迟" in intent or "实时" in intent or "毫秒级" in intent:
            return 50
        return None

    @staticmethod
    def parse(intent: str) -> Dict[str, Any]:
        result = {
            "task_type": MockIntentParser.detect_task_type(intent),
            "compute_type": MockIntentParser.detect_compute_type(intent),
            "sla_requirement": MockIntentParser.detect_sla(intent),
            "region": MockIntentParser.detect_region(intent),
            "required_cpu": MockIntentParser.extract_number(intent, ["核", "CPU", "核心", "core"]) or 4,
            "required_memory": MockIntentParser.extract_number(intent, ["GB"]) * 1024 or 8192,
            "required_gpu": MockIntentParser.extract_number(intent, ["GPU", "显卡", "卡"]) or 0,
            "required_latency_ms": MockIntentParser.detect_latency_requirement(intent)
        }
        return result


def get_llm():
    """根据环境配置选择大模型"""
    if os.getenv("DASHSCOPE_API_KEY"):
        from langchain_community.llms import Tongyi
        return Tongyi(model="qwen-max", api_key=os.getenv("DASHSCOPE_API_KEY"))
    elif os.getenv("OPENAI_API_KEY"):
        return ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
    else:
        return None


parser = PydanticOutputParser(pydantic_object=TaskRequirement)

INTENT_PARSING_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个专业的算力任务意图解析专家。请将用户的自然语言意图解析为结构化的任务需求。

任务类型（task_type）：
- training: 模型训练任务
- inference: 推理服务部署
- data_processing: 数据处理任务

计算类型（compute_type）：
- CPU: CPU计算
- GPU: GPU加速计算
- NPU: NPU神经网络处理器

SLA要求（sla_requirement）：
- 低延迟(<100ms): 实时推理、低延迟场景
- 高带宽(>10Gbps): 大流量数据传输
- 标准延迟: 普通计算任务

地域（region）：
- beijing: 北京
- shanghai: 上海
- hangzhou: 杭州
- guangzhou: 广州
- chengdu: 成都
- null: 无地域偏好

请严格按照给定的JSON格式输出，不要添加额外内容：
{output_format}"""),
    ("human", "{user_intent}")
])


def parse_intent(user_intent: str) -> Dict[str, Any]:
    """
    解析用户自然语言意图，返回结构化的任务需求
    优先使用LLM解析，若没有API密钥则使用规则引擎模拟
    """
    llm = get_llm()

    if llm is None:
        return MockIntentParser.parse(user_intent)

    prompt = INTENT_PARSING_PROMPT.partial(output_format=parser.get_format_instructions())
    chain = prompt | llm | parser

    try:
        result = chain.invoke({"user_intent": user_intent})
        if isinstance(result, BaseModel):
            return result.dict()
        return result
    except Exception as e:
        print(f"LLM解析失败，使用规则引擎: {str(e)}")
        return MockIntentParser.parse(user_intent)


def parse_intent_node(state: SchedulingState) -> dict:
    """
    LangGraph 意图解析节点函数

    使用 LangChain 的 ChatPromptTemplate 和 PydanticOutputParser，
    将用户的自然语言意图解析为固定的 JSON Schema。
    """
    user_intent = state.get("user_intent", "")

    if not user_intent:
        return {
            **state,
            "structured_requirement": None,
            "error_message": "用户意图为空",
            "execution_status": "failed",
            "messages": [{"role": "system", "content": "解析失败：用户意图为空"}]
        }

    try:
        llm = get_llm()

        if llm is None:
            structured_requirement = MockIntentParser.parse(user_intent)
        else:
            prompt = INTENT_PARSING_PROMPT.partial(output_format=parser.get_format_instructions())
            chain = prompt | llm | parser
            result = chain.invoke({"user_intent": user_intent})

            if isinstance(result, BaseModel):
                structured_requirement = result.dict()
            else:
                structured_requirement = json.loads(result) if isinstance(result, str) else result

        latency_info = ""
        if structured_requirement.get("required_latency_ms"):
            latency_info = f", 延迟要求=<{structured_requirement.get('required_latency_ms')}ms"

        return {
            **state,
            "structured_requirement": structured_requirement,
            "messages": [{"role": "system", "content": f"意图解析完成：任务类型={structured_requirement.get('task_type')}, 计算类型={structured_requirement.get('compute_type')}, 地域={structured_requirement.get('region')}{latency_info}"}]
        }

    except json.JSONDecodeError as e:
        print(f"JSON解析失败，使用规则引擎: {str(e)}")
        structured_requirement = MockIntentParser.parse(user_intent)
        return {
            **state,
            "structured_requirement": structured_requirement,
            "messages": [{"role": "system", "content": f"意图解析完成（规则引擎）：任务类型={structured_requirement.get('task_type')}"}]
        }
    except Exception as e:
        print(f"意图解析异常: {str(e)}")
        return {
            **state,
            "structured_requirement": None,
            "error_message": str(e),
            "execution_status": "failed",
            "messages": [{"role": "system", "content": f"意图解析失败: {str(e)}"}]
        }