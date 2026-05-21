from langchain.chat_models import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import List, Optional
from backend.core.config import settings

class ActionItem(BaseModel):
    type: str = Field(description="操作类型，如qos、acl、route等")
    params: dict = Field(description="操作参数")

class StructuredIntent(BaseModel):
    intent_name: str = Field(description="意图名称")
    targets: List[str] = Field(description="目标设备或网络")
    conditions: Optional[List[str]] = Field(description="条件列表")
    actions: List[ActionItem] = Field(description="动作列表")

class IntentParserAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout
        )
        self.parser = PydanticOutputParser(pydantic_object=StructuredIntent)
        
        self.prompt_template = """
        你是一个网络运维意图解析专家。请将用户的自然语言输入解析为结构化的网络意图。
        
        解析规则：
        1. 必须输出符合JSON Schema的结构化数据
        2. 意图名称必须清晰表达核心需求
        3. 目标必须明确指向具体的设备或网络
        4. 动作类型必须是标准网络操作（如qos、acl、route、interface等）
        5. 参数必须包含执行该动作所需的所有必要信息
        
        示例：
        用户输入："保证研发子网视频会议流量最小200M带宽"
        输出：
        {{
            "intent_name": "bandwidth_guarantee",
            "targets": ["研发子网"],
            "conditions": [],
            "actions": [{{"type": "qos", "params": {{"min_bw": "200M", "traffic_type": "video"}}}}]
        }}
        
        现在解析以下用户输入：
        {user_input}
        
        {format_instructions}
        """
    
    async def parse(self, user_input: str) -> dict:
        prompt = self.prompt_template.format(
            user_input=user_input,
            format_instructions=self.parser.get_format_instructions()
        )
        
        response = await self.llm.apredict(prompt)
        
        try:
            parsed = self.parser.parse(response)
            return parsed.dict()
        except Exception:
            return {
                "intent_name": "unknown",
                "targets": [],
                "conditions": [],
                "actions": []
            }